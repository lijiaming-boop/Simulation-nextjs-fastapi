"""Agent 模式服务层：桥接 AgentOrchestrator 与 FastAPI

职责：
1. 按环境选择决策核心（配置了 API Key → LLMBrain；否则零成本 RuleBrain）
2. 在后台线程运行 agent 循环，事件经 asyncio.Queue 供 SSE 消费
3. 运行结束后把产物同步回 session_store，兼容既有 /result、/download 端点
"""
import asyncio
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent import AgentOrchestrator, RuleBrain
from .deps import PROJECT_ROOT, session_store

# session_id → agent 后台 thread
_agent_tasks: dict = {}


def _select_brain(mode: Optional[str] = None):
    """选择决策核心

    - mode="deterministic" 或未配置 API Key → RuleBrain（零 LLM 成本）
    - 其余 → LLMBrain
    返回 None 表示由 orchestrator 回退到 RuleBrain。
    """
    if mode == "deterministic":
        return RuleBrain()
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from agent import LLMBrain
            from core.llm_client import DirectLLMClient
            return LLMBrain(client=DirectLLMClient())
        except Exception:
            return None
    return None


def is_agent_running(session_id: str) -> bool:
    t = _agent_tasks.get(session_id)
    return t is not None and t.is_alive()


def start_agent_run(
    session_id: str,
    mode: Optional[str] = None,
    main_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Path:
    """启动 agent 运行线程，返回轨迹文件路径

    要求 session 已通过 /upload 上传调研表。
    """
    s = session_store.get(session_id)
    if s is None:
        raise RuntimeError(f"session {session_id!r} 不存在")
    if is_agent_running(session_id):
        raise RuntimeError(f"session {session_id!r} 已有 agent 任务在运行")

    session_dir: Path = s["session_dir"]
    original_filename: str = s["original_filename"] or ""
    survey_path = session_dir / original_filename
    if not survey_path.exists():
        raise RuntimeError(f"调研表文件缺失: {survey_path.name}")

    trace_path = session_dir / "agent_trace.json"
    brain = _select_brain(mode)
    loop = main_loop

    def worker() -> None:
        def on_event(event: dict) -> None:
            """orchestrator 事件 → ai_logs + SSE 队列"""
            ts = datetime.now().strftime("%H:%M:%S")
            # 面向日志的人类可读消息
            etype = event.get("type", "")
            if etype == "thinking":
                msg = f"🧠 {event.get('message', '')}"
            elif etype == "tool_start":
                msg = f"🔧 调用工具 {event.get('tool')}"
            elif etype == "tool_end":
                mark = "✅" if event.get("ok") else "❌"
                msg = f"{mark} 工具 {event.get('tool')} 执行完成"
                obs = event.get("observation") or {}
                if not event.get("ok") and obs.get("error"):
                    msg += f"：{obs['error'][:200]}"
            elif etype in ("final", "error", "run_start"):
                msg = f"ℹ️ {event.get('message', '')}"
            else:
                msg = json_safe(event)
            session_store.append_ai_log(session_id, ts, msg)

            if loop is not None:
                from apps.api.services import get_ai_queue
                q = get_ai_queue(session_id)
                if q is not None:
                    payload = {"type": etype, "timestamp": ts, **{
                        k: v for k, v in event.items() if k != "type"
                    }}
                    loop.call_soon_threadsafe(q.put_nowait, payload)

        try:
            orchestrator = AgentOrchestrator(
                session_id=session_id,
                session_dir=session_dir,
                survey_path=survey_path,
                original_filename=original_filename,
                brain=brain,
                on_event=on_event,
            )
            final = orchestrator.run()

            # 产物同步回 session_store，兼容既有 /result、/download 端点
            s_live = session_store.get(session_id)
            if s_live is not None:
                s_live["extracted_data"] = orchestrator.ctx.get("extracted_data")
                s_live["quality_report"] = orchestrator.ctx.get("quality_report")
                s_live["filling_suggestions"] = orchestrator.ctx.get("suggestions")
                s_live["result"] = orchestrator.ctx.get("result")
                s_live["formatted_result"] = orchestrator.ctx.get("formatted_result")
                stage = {"completed": "result", "needs_input": "suggest"}.get(
                    final["status"], "error"
                )
                session_store.update_stage(session_id, stage)

            # 终止事件进 SSE 队列
            if loop is not None:
                from apps.api.services import get_ai_queue
                q = get_ai_queue(session_id)
                if q is not None:
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "done" if final["status"] != "error" else "error",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "status": final["status"],
                        "message": final.get("summary", ""),
                    })
        except Exception as e:  # 兜底：线程内未捕获异常
            session_store.append_ai_log(
                session_id, datetime.now().strftime("%H:%M:%S"),
                f"❌ Agent 运行异常: {type(e).__name__}: {e}",
            )
            session_store.update_stage(session_id, "error")
            if loop is not None:
                from apps.api.services import get_ai_queue
                q = get_ai_queue(session_id)
                if q is not None:
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "error",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "message": f"{type(e).__name__}: {e}",
                    })

    t = threading.Thread(target=worker, daemon=True, name=f"agent-{session_id}")
    t.start()
    _agent_tasks[session_id] = t
    session_store.update_stage(session_id, "agent_running")
    return trace_path


def json_safe(event: dict) -> str:
    """事件兜底序列化（截断）"""
    try:
        import json
        return json.dumps(event, ensure_ascii=False)[:300]
    except Exception:
        return str(event)[:300]
