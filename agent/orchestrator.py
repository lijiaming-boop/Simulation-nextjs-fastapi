"""Agent 编排器

ReAct 循环：决策（Brain）→ 执行（ToolRegistry）→ 观察 → 再决策，直到
finish / request_user_input 或触发预算限制。

设计原则（agent 与传统代码的边界）：
- 硬约束在代码里：工具前置依赖、质量门禁（完整率<50%、unsupported 站房、
  不可填充字段）、步骤预算，全部由白名单机制强制执行，模型无法绕过。
- 软决策在模型里：白名单内的工具选择、每步的面向用户叙事、最终结论摘要。
- 执行零 token：所有工具都是确定性函数，LLM 成本只发生在决策点。

事件通过 on_event 回调流出（供 FastAPI SSE 桥接），完整轨迹落盘 agent_trace.json。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.brain import Brain, RuleBrain
from agent.tools import AgentToolError, ToolContext, ToolRegistry, build_default_registry
from agent.trace import AgentTrace

# 事件回调类型：(event_dict) -> None
EventCallback = Callable[[Dict[str, Any]], None]


class AgentOrchestrator:
    """测算主线 agent 编排器"""

    def __init__(
        self,
        session_id: str,
        session_dir: Path,
        survey_path: Path,
        original_filename: str = "",
        brain: Optional[Brain] = None,
        registry: Optional[ToolRegistry] = None,
        max_steps: int = 10,
        on_event: Optional[EventCallback] = None,
    ) -> None:
        self.session_id = session_id
        self.session_dir = Path(session_dir)
        self.survey_path = Path(survey_path)
        self.original_filename = original_filename
        self.brain = brain
        self.registry = registry or build_default_registry()
        self.max_steps = max_steps
        self.on_event = on_event
        self.trace = AgentTrace(session_id, mode="agent" if brain is not None else "deterministic")
        self.ctx = ToolContext(session_dir=self.session_dir, original_filename=original_filename)

    # ==================== 主循环 ====================

    def run(self) -> Dict[str, Any]:
        """执行 agent 循环，返回最终结果字典"""
        if self.brain is None:
            self.brain = RuleBrain()

        self._emit("run_start", message=f"开始测算（模式: {self.trace.mode}）",
                   survey=self.survey_path.name)

        consecutive_errors = 0
        status, summary = "error", "达到最大步数限制"
        extra: Dict[str, Any] = {}

        for step_no in range(1, self.max_steps + 1):
            allowed, gate_note = self._allowed_tools()
            state_view = self._state_view()
            if gate_note:
                state_view["gate_note"] = gate_note
            state_view["survey_path"] = str(self.survey_path)

            try:
                decision = self.brain.decide(state_view, allowed, self.registry)
            except Exception as e:
                status, summary = "error", f"决策失败: {type(e).__name__}: {e}"
                self._emit("error", message=summary)
                break

            self.trace.begin_step(step_no, decision.tool, decision.args,
                                  decision.reason, decision.llm_meta)
            if decision.llm_meta:
                self.trace.add_llm_usage(
                    decision.llm_meta.get("input_tokens") or 0,
                    decision.llm_meta.get("output_tokens") or 0,
                )
            self._emit("thinking", message=decision.reason, tool=decision.tool,
                       step=step_no)

            # ---- 硬约束兜底：决策越出白名单一律拒绝（防模型幻觉/越权） ----
            if decision.tool not in allowed:
                observation = {
                    "error": f"工具 {decision.tool!r} 不在当前可用白名单 {allowed} 中",
                    "allowed": allowed,
                }
                self.trace.end_step(False, observation)
                self._emit("tool_end", tool=decision.tool, ok=False, step=step_no,
                           observation=observation)
                self.trace.save(self.session_dir)
                continue

            # ---- 规范化 extract_survey 的入参（路径以会话记录为准） ----
            if decision.tool == "extract_survey":
                decision.args["survey_path"] = str(self.survey_path)
                decision.args.setdefault("original_filename", self.original_filename)

            # ---- 控制类工具：结束循环 ----
            tool = self.registry.get(decision.tool)
            if tool is not None and tool.control:
                if decision.tool == "finish":
                    status, summary = "completed", decision.args.get("summary", "测算完成")
                    extra["result"] = self.ctx.get("result")
                else:  # request_user_input
                    status, summary = "needs_input", decision.args.get("reason", "需要用户补充数据")
                    extra["missing_items"] = decision.args.get("missing_items", [])
                self.trace.end_step(True, {"status": status})
                self._emit("tool_end", tool=decision.tool, ok=True, step=step_no,
                           message=summary)
                break

            # ---- 确定性工具：执行并观察 ----
            self._emit("tool_start", tool=decision.tool, step=step_no,
                       args=decision.args)
            try:
                observation = self.registry.execute(decision.tool, self.ctx, decision.args)
                self.trace.end_step(True, observation)
                consecutive_errors = 0
                self._emit("tool_end", tool=decision.tool, ok=True, step=step_no,
                           observation=observation)
            except Exception as e:
                observation = {"error": f"{type(e).__name__}: {e}"}
                self.trace.end_step(False, observation)
                consecutive_errors += 1
                self._emit("tool_end", tool=decision.tool, ok=False, step=step_no,
                           observation=observation)

            self.trace.save(self.session_dir)

            if consecutive_errors >= 3:
                status, summary = "error", f"工具连续失败 {consecutive_errors} 次，中止运行"
                self._emit("error", message=summary)
                break
        else:
            self._emit("error", message="达到最大步数限制")

        self.trace.set_final(status, summary, **{
            k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items()})
            for k, v in extra.items()
        })
        trace_path = self.trace.save(self.session_dir)
        self._emit("final", status=status, message=summary, **{
            k: v for k, v in extra.items() if k != "result"
        })
        return {
            "status": status,
            "summary": summary,
            **extra,
            "trace_path": str(trace_path),
            "artifacts": self._artifact_paths(),
        }

    # ==================== 白名单与状态视图 ====================

    def _allowed_tools(self) -> tuple[List[str], Optional[str]]:
        """根据当前状态计算可用工具白名单（硬约束），返回 (白名单, 门禁说明)"""
        if self.ctx.get("result") is not None:
            return ["finish"], None
        if self.ctx.get("filled_data") is not None:
            return ["calculate_saving_rate"], None

        suggestions = self.ctx.get("suggestions")
        if suggestions is not None:
            if not suggestions.get("can_proceed", False):
                unfillable = [u.get("field", "") for u in suggestions.get("unfillable_fields", [])]
                note = f"存在不可填充字段，无法继续计算: {', '.join(unfillable[:5])}"
                return ["request_user_input"], note
            # 有建议可执行；若建议占比过高，允许模型选择转人工
            return ["apply_filling", "request_user_input"], None

        extracted = self.ctx.get("extracted_data")
        if extracted is not None:
            quality = self.ctx.get("quality_report", {})
            if quality.get("confidence_level") == "low":
                return ["request_user_input"], (
                    f"数据完整率 {quality.get('completeness')} 低于 50%，"
                    "不允许进入计算流程，需要用户补充数据后重新上传"
                )
            if extracted.get("station_type") == "unsupported":
                return ["request_user_input"], (
                    f"站房类型不支持自动测算: {extracted.get('station_type_reason', '含特殊机组')}"
                )
            return ["suggest_filling"], None

        return ["extract_survey"], None

    def _state_view(self) -> Dict[str, Any]:
        """给决策模型的紧凑状态摘要"""
        view: Dict[str, Any] = {
            "original_filename": self.original_filename or self.survey_path.name,
            "steps_done": [
                {"tool": s["tool"], "ok": s["ok"]} for s in self.trace.steps
            ],
        }
        extracted = self.ctx.get("extracted_data")
        if extracted is not None:
            quality = self.ctx.get("quality_report", {})
            view["extracted"] = {
                "project_region": extracted.get("project_region"),
                "station_type": extracted.get("station_type"),
                "completeness": quality.get("completeness"),
                "confidence_level": quality.get("confidence_level"),
                "available_fields": extracted.get("available_fields"),
            }
        suggestions = self.ctx.get("suggestions")
        if suggestions is not None:
            view["suggestions"] = {
                "can_proceed": suggestions.get("can_proceed"),
                "fillable_count": len(suggestions.get("fillable_suggestions", [])),
                "unfillable_count": len(suggestions.get("unfillable_fields", [])),
                "fillable_preview": [
                    f"{s.get('field')}: {s.get('suggested_value')} ({s.get('method')})"
                    for s in suggestions.get("fillable_suggestions", [])[:6]
                ],
            }
        filled = self.ctx.get("filled_data")
        if filled is not None:
            meta = filled.get("_metadata", {})
            view["filled"] = {
                "fill_count": meta.get("fill_count"),
                "final_completeness": meta.get("final_completeness"),
            }
        result = self.ctx.get("result")
        if result is not None:
            view["result"] = {
                "energy_saving_rate_range": result.get("energy_saving_rate_range"),
                "energy_saving_rate_min": result.get("energy_saving_rate_min"),
                "energy_saving_rate_max": result.get("energy_saving_rate_max"),
                "chiller_saving": result.get("chiller_saving"),
                "pump_saving": result.get("pump_saving"),
                "tower_saving": result.get("tower_saving"),
                "final_completeness": result.get("completeness"),
            }
        return view

    def _artifact_paths(self) -> Dict[str, str]:
        """本次运行产出的标准文件（与既有 /download 端点约定一致）"""
        names = ["extracted_data.json", "quality_report.json", "filling_suggestions.json",
                 "filled_data.json", "result_data.json", "calculation_result.xlsx",
                 "simplified_result.xlsx", "agent_trace.json"]
        return {
            n: str(self.session_dir / n)
            for n in names if (self.session_dir / n).exists()
        }

    # ==================== 事件 ====================

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event({"type": event_type, **kwargs})
        except Exception:
            # 事件消费方故障不影响主流程
            pass
