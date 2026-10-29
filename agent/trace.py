"""Agent 轨迹记录器

记录一次 agent 运行的完整轨迹：每一步的工具调用、参数、耗时、
观察结果、LLM 决策理由与 token 用量，最终落盘为 agent_trace.json。

这是 agent 可观测性的核心：任何一次测算都可以事后逐帧复盘
"模型在想什么、调了什么工具、花了多少 token"。
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgentTrace:
    """单次 agent 运行的结构化轨迹"""

    def __init__(self, session_id: str, mode: str) -> None:
        self.session_id = session_id
        self.mode = mode  # "agent"(LLM 决策) | "deterministic"(规则策略)
        self.started_at = datetime.now().isoformat()
        self.steps: List[Dict[str, Any]] = []
        self.llm_usage = {"brain_calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.final: Dict[str, Any] = {}
        self._step_started_at: Optional[float] = None

    # ==================== 步骤记录 ====================

    def begin_step(self, step_no: int, tool: str, args: Dict[str, Any],
                   reason: str, llm_meta: Optional[Dict[str, Any]] = None) -> None:
        """记录一步的开始（含产生该决策的 LLM 元数据）"""
        self._step_started_at = time.monotonic()
        step: Dict[str, Any] = {
            "step": step_no,
            "tool": tool,
            "args": args,
            "reason": reason,
            "ok": None,
            "observation": None,
            "duration_ms": None,
        }
        if llm_meta:
            step["decision"] = llm_meta
        self.steps.append(step)

    def end_step(self, ok: bool, observation: Dict[str, Any]) -> None:
        """补全当前步骤的执行结果"""
        if not self.steps:
            return
        step = self.steps[-1]
        step["ok"] = ok
        step["observation"] = observation
        if self._step_started_at is not None:
            step["duration_ms"] = int((time.monotonic() - self._step_started_at) * 1000)

    # ==================== LLM 用量 ====================

    def add_llm_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.llm_usage["brain_calls"] += 1
        self.llm_usage["input_tokens"] += input_tokens
        self.llm_usage["output_tokens"] += output_tokens

    # ==================== 收尾与落盘 ====================

    def set_final(self, status: str, summary: str, **extra: Any) -> None:
        self.final = {"status": status, "summary": summary, **extra}
        self.finished_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": getattr(self, "finished_at", None),
            "llm_usage": self.llm_usage,
            "steps": self.steps,
            "final": self.final,
        }

    def save(self, session_dir: Path) -> Path:
        """轨迹落盘（每步结束后调用一次，崩溃也能保留已执行部分）"""
        path = Path(session_dir) / "agent_trace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path
