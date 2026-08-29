"""Agent 模式服务层：桥接 AgentOrchestrator 与 FastAPI

职责：
1. 按环境选择决策核心（配置了 API Key → LLMBrain 走 LLM 网关；否则零成本 RuleBrain）
2. 在后台线程运行 agent 循环，事件经 asyncio.Queue 供 SSE 消费
3. 运行与每步落库（agent_runs / agent_steps），支持进程重启后断点恢复
4. Human-in-the-loop：needs_input / pending_approval 终态创建待办（agent_actions），
   审批批准或补充数据后从断点/重跑恢复
5. 运行结束后把产物同步回 session_store，兼容既有 /result、/download 端点
"""
import asyncio
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent import AgentOrchestrator, RuleBrain
from agent.tools import build_registry_for_module
from .deps import session_store

DEFAULT_MAX_STEPS = 10

# session_id → agent 后台 thread
_agent_tasks: dict = {}


def is_agent_running(session_id: str) -> bool:
    t = _agent_tasks.get(session_id)
    return t is not None and t.is_alive()


def _select_brain(mode: Optional[str] = None, user_id: Optional[str] = None):
    """选择决策核心

    - mode="deterministic" 或未配置 API Key → RuleBrain（零 LLM 成本）
    - 其余 → LLMBrain，LLM 调用经 LLM 网关（预算/计量/熔断）
    """
    if mode == "deterministic":
        return RuleBrain(), "deterministic"
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from agent import LLMBrain
            from core.llm_client import DirectLLMClient
            from core.llm_gateway import LLMGateway
            gateway = LLMGateway(user_id=user_id, purpose_default="agent.brain",
                                 store=session_store)
            return LLMBrain(client=gateway), "llm"
        except Exception:
            return None, "deterministic"
    return None, "deterministic"


def _notify_event(session_id: str, event: dict, loop=None) -> None:
    """事件 → ai_logs + SSE 队列"""
    ts = datetime.now().strftime("%H:%M:%S")
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


def _finalize_run(run_id: str, session_id: str, orchestrator: AgentOrchestrator,
                  final: dict) -> None:
    """运行收尾：结果落库、产物同步回 session_store、创建 HITL 待办"""
    session_store.update_run(
        run_id, status=final["status"], summary=final.get("summary", ""),
        finished_at=datetime.now(), llm_usage=orchestrator.trace.llm_usage,
    )

    s_live = session_store.get(session_id)
    formatted = orchestrator.ctx.get("formatted_result")
    result = orchestrator.ctx.get("result")
    if formatted is None and result is not None:
        try:
            filled = orchestrator.ctx.get("filled_data") or {}
            from core.excel_calculator import ExcelCalculator
            formatted = ExcelCalculator().format_export_results(filled, result)
        except Exception:
            formatted = None
    if s_live is not None:
        s_live["extracted_data"] = orchestrator.ctx.get("extracted_data")
        s_live["quality_report"] = orchestrator.ctx.get("quality_report")
        s_live["filling_suggestions"] = orchestrator.ctx.get("suggestions")
        s_live["result"] = result
        s_live["formatted_result"] = formatted
        stage = {"completed": "result", "needs_input": "suggest",
                 "pending_approval": "suggest"}.get(final["status"], "error")
        session_store.update_stage(session_id, stage)

    # Human-in-the-loop：求助/审批 → 待办收件箱
    if final["status"] in ("needs_input", "pending_approval"):
        try:
            session_store.create_action(
                run_id=run_id, session_id=session_id,
                action_type="needs_input" if final["status"] == "needs_input" else "approval",
                reason=final.get("summary", ""),
                detail={"missing_items": final.get("missing_items", [])},
                user_id=(session_store.get(session_id) or {}).get("user_id"),
            )
        except Exception:
            pass

    # 通知（M3）：完成/求助/审批/失败 推送 webhook（未配置则跳过）
    try:
        from .notify import notify_run_finished
        notify_run_finished(session_id, final)
    except Exception:
        pass


def run_agent_sync(session_id: str, mode: Optional[str] = None,
                   require_fill_approval: bool = False) -> dict:
    """同步执行一次 agent 主线（批量任务用；交互路径走 start_agent_run 线程）"""
    s = session_store.get(session_id)
    if s is None:
        raise RuntimeError(f"session {session_id!r} 不存在")
    session_dir: Path = s["session_dir"]
    original_filename: str = s["original_filename"] or ""
    survey_path = session_dir / original_filename
    if not survey_path.exists():
        raise RuntimeError(f"调研表文件缺失: {survey_path.name}")

    brain, brain_label = _select_brain(mode, user_id=s.get("user_id"))
    registry = build_registry_for_module(s.get("module_type", "air_conditioner"))
    run_id = session_store.create_run(session_id, brain_label)
    session_store.update_run(run_id, mode=brain_label)

    orchestrator = AgentOrchestrator(
        session_id=session_id, session_dir=session_dir,
        survey_path=survey_path, original_filename=original_filename,
        brain=brain, registry=registry,
        require_fill_approval=require_fill_approval,
        on_step=lambda step: session_store.add_step(run_id, step),
    )
    final = orchestrator.run()
    _finalize_run(run_id, session_id, orchestrator, final)
    return final


def start_agent_run(
    session_id: str,
    mode: Optional[str] = None,
    main_loop: Optional[asyncio.AbstractEventLoop] = None,
    resume: bool = False,
    require_fill_approval: bool = False,
) -> Path:
    """启动 agent 运行线程，返回轨迹文件路径

    resume=True 时从最近一次 interrupted 的运行断点续跑
    （状态产物从会话目录文件恢复，步数与用量累计到同一 run 记录）。
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

    brain, brain_label = _select_brain(mode, user_id=s.get("user_id"))
    registry = build_registry_for_module(s.get("module_type", "air_conditioner"))
    run_id = session_store.create_run(session_id, brain_label)
    session_store.update_run(run_id, mode=brain_label)
    return _start_run_thread(
        session_id, run_id=run_id, brain=brain, registry=registry,
        require_fill_approval=require_fill_approval,
        main_loop=main_loop, survey_path=survey_path,
        original_filename=original_filename,
    )


def resume_agent_run(session_id: str, main_loop=None,
                     approval_granted: bool = False) -> Path:
    """从最近一次 interrupted / pending_approval 运行断点恢复

    approval_granted=True：恢复待审批的运行并跳过审批门（人工已批准填充）。
    """
    s = session_store.get(session_id)
    if s is None:
        raise RuntimeError(f"session {session_id!r} 不存在")
    if is_agent_running(session_id):
        raise RuntimeError(f"session {session_id!r} 已有 agent 任务在运行")

    statuses = ["interrupted", "pending_approval"] if approval_granted else ["interrupted"]
    run = session_store.get_latest_run(session_id, statuses=statuses)
    if run is None:
        raise RuntimeError("没有可恢复的中断或待审批运行")

    return _start_run_thread(
        session_id, resume_run=run, approval_granted=approval_granted,
        main_loop=main_loop,
    )


def _start_run_thread(
    session_id: str,
    run_id: Optional[str] = None,
    resume_run: Optional[dict] = None,
    brain=None,
    registry=None,
    require_fill_approval: bool = False,
    approval_granted: bool = False,
    main_loop=None,
    survey_path: Optional[Path] = None,
    original_filename: Optional[str] = None,
) -> Path:
    """组装并启动 agent 运行线程（新建运行 / 断点恢复共用）"""
    s = session_store.get(session_id)
    session_dir: Path = s["session_dir"]
    original_filename = original_filename if original_filename is not None else (s["original_filename"] or "")
    survey_path = survey_path or (session_dir / original_filename)
    trace_path = session_dir / "agent_trace.json"

    start_step = 1
    max_steps = DEFAULT_MAX_STEPS
    if resume_run is not None:
        run_id = resume_run["run_id"]
        start_step = (resume_run["step_count"] or 0) + 1
        max_steps = DEFAULT_MAX_STEPS + (resume_run["step_count"] or 0)
        approval_granted = approval_granted or resume_run["status"] == "pending_approval"
        session_store.update_run(run_id, status="running", summary=None,
                                 finished_at=None)
    else:
        session_store.update_run(run_id, mode=(brain.__class__.__name__ == "LLMBrain" and "llm" or "deterministic"))

    def worker() -> None:
        def on_event(event: dict) -> None:
            _notify_event(session_id, event, loop=main_loop)

        def on_step(step: dict) -> None:
            """每步落库（断点恢复依据 + token 计量）"""
            try:
                session_store.add_step(run_id, step)
            except Exception:
                pass

        try:
            orchestrator = AgentOrchestrator(
                session_id=session_id,
                session_dir=session_dir,
                survey_path=survey_path,
                original_filename=original_filename,
                brain=brain,
                registry=registry,
                max_steps=max_steps,
                start_step=start_step,
                require_fill_approval=require_fill_approval,
                approval_granted=approval_granted,
                on_event=on_event,
                on_step=on_step,
            )
            if resume_run is not None:
                orchestrator.hydrate_from_session()
            final = orchestrator.run()

            _finalize_run(run_id, session_id, orchestrator, final)

            # 终止事件进 SSE 队列
            if main_loop is not None:
                from apps.api.services import get_ai_queue
                q = get_ai_queue(session_id)
                if q is not None:
                    main_loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "done" if final["status"] != "error" else "error",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "status": final["status"],
                        "message": final.get("summary", ""),
                    })
        except Exception as e:  # 兜底：线程内未捕获异常
            session_store.update_run(
                run_id, status="error",
                summary=f"{type(e).__name__}: {e}", finished_at=datetime.now(),
            )
            session_store.append_ai_log(
                session_id, datetime.now().strftime("%H:%M:%S"),
                f"❌ Agent 运行异常: {type(e).__name__}: {e}",
            )
            session_store.update_stage(session_id, "error")
            if main_loop is not None:
                from apps.api.services import get_ai_queue
                q = get_ai_queue(session_id)
                if q is not None:
                    main_loop.call_soon_threadsafe(q.put_nowait, {
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
