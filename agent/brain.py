"""Agent 决策核心（Brain）

同一决策接口的两种实现：
- LLMBrain：调用 LLM 做工具选择决策，输出强约束 JSON，解析失败自动重试。
  每次决策只花一次小额 LLM 调用，工具执行本身零 token。
- RuleBrain：确定性规则策略，按业务流程驱动同样的工具序列，零 LLM 成本。
  用于评测模式、离线运行和无 API Key 场景。

硬约束（质量门禁、站房类型拦截、步骤预算）不在 Brain 里决策，
由 orchestrator 通过工具白名单强制执行——Brain 只能在白名单内选择。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from agent.tools import ToolRegistry


@dataclass
class BrainDecision:
    """一次决策的结果"""
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    # LLM 决策附带的元数据（规则策略为 None）
    llm_meta: Optional[Dict[str, Any]] = None


class Brain(Protocol):
    """决策核心协议：给定状态摘要和可用工具，选择下一个工具"""

    def decide(self, state: Dict[str, Any], available_tools: List[str],
               registry: ToolRegistry) -> BrainDecision:
        ...


# ==================== LLM 决策实现 ====================

SYSTEM_PROMPT = """你是"暖通节能测算 Agent"的决策核心。你的职责是根据当前状态，\
从可用工具中选择下一个要调用的工具，并给出简短的中文理由。

规则：
1. 只能输出一个 JSON 对象，格式：
   {"tool": "<工具名>", "args": {...}, "reason": "<一句话理由>"}
2. tool 必须从 available_tools 列表中选择，禁止编造工具。
3. reason 面向业务用户（销售/解决方案专家），简明专业。
4. 如果数据质量不达标或填充建议风险过高，选择 request_user_input 并说明缺什么。
5. 拿到计算结果后，用 finish 输出面向用户的结论摘要（节能率范围、分项节能量、\
数据置信度、使用建议），summary 用 3-6 句话。
6. 不要输出 JSON 以外的任何内容。"""


class LLMBrain:
    """基于 LLM 的决策核心"""

    def __init__(self, client=None, max_retries: int = 2, temperature: float = 0.0) -> None:
        if client is None:
            from core.llm_client import DirectLLMClient
            client = DirectLLMClient()
        self.client = client
        self.max_retries = max_retries
        self.temperature = temperature

    def decide(self, state: Dict[str, Any], available_tools: List[str],
               registry: ToolRegistry) -> BrainDecision:
        prompt = self._build_prompt(state, available_tools, registry)
        last_error: Optional[str] = None

        for attempt in range(self.max_retries + 1):
            text, usage = self.client.create_message_with_usage(
                prompt, system=SYSTEM_PROMPT, max_tokens=800,
                temperature=self.temperature,
            )
            parsed, err = self._parse_decision(text, available_tools)
            if parsed is not None:
                meta = {
                    "attempt": attempt + 1,
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "model": getattr(self.client, "model", None),
                }
                return BrainDecision(
                    tool=parsed["tool"], args=parsed.get("args", {}),
                    reason=parsed.get("reason", ""), llm_meta=meta,
                )
            last_error = err
            # 把上一轮的错误输出附进 prompt，引导模型修正
            prompt = (
                f"{self._build_prompt(state, available_tools, registry)}\n\n"
                f"你上一次的输出不符合要求（{err}），请严格按格式重新输出 JSON。"
            )

        raise RuntimeError(f"LLM 决策在 {self.max_retries + 1} 次尝试后仍无法解析: {last_error}")

    def _build_prompt(self, state: Dict[str, Any], available_tools: List[str],
                      registry: ToolRegistry) -> str:
        tool_views = [
            registry.get(name).compact_view()
            for name in available_tools if registry.get(name) is not None
        ]
        payload = {
            "available_tools": available_tools,
            "tool_details": tool_views,
            "current_state": state,
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _parse_decision(text: str, available_tools: List[str]):
        """解析 LLM 输出的 JSON 决策，返回 (decision_dict, None) 或 (None, 错误信息)"""
        # 剥离可能的 markdown 代码块围栏
        cleaned = text.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        else:
            # 容错：截取第一个 { 到最后一个 } 之间
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start != -1 and end > start:
                cleaned = cleaned[start:end + 1]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            return None, f"JSON 解析失败: {e}"

        if not isinstance(data, dict):
            return None, "输出不是 JSON 对象"
        tool = data.get("tool")
        if not isinstance(tool, str):
            return None, "缺少 tool 字段"
        if tool not in available_tools:
            return None, f"工具 {tool!r} 不在可用列表 {available_tools} 中"
        if not isinstance(data.get("args", {}), dict):
            return None, "args 必须是对象"
        return data, None


# ==================== 确定性规则策略 ====================

class RuleBrain:
    """零 LLM 成本的确定性策略

    复刻业务流程的标准路径：提取 → 质检门禁 → 填充建议 → 风险判断 → 填充 → 计算 → 结论。
    用于评测（保证可复现）、离线运行和无 API Key 场景。
    """

    # 若建议填充的字段数超过该比例，认为数据补全依赖过重，转人工确认
    # （12月×7字段中过半依赖估算时，人工复核成本低于结果失真风险）
    RISKY_FILL_RATIO = 0.5

    def decide(self, state: Dict[str, Any], available_tools: List[str],
               registry: ToolRegistry) -> BrainDecision:
        if "extract_survey" in available_tools:
            return BrainDecision(
                tool="extract_survey",
                args={"survey_path": state["survey_path"],
                      "original_filename": state.get("original_filename", "")},
                reason="开始提取调研表数据并做质量检查",
            )
        if "suggest_filling" in available_tools:
            return BrainDecision(
                tool="suggest_filling", args={},
                reason=f"数据质量达标（完整率 {state['extracted'].get('completeness')}），生成填充建议",
            )
        if "apply_filling" in available_tools:
            fillable = state["suggestions"].get("fillable_count", 0)
            # 风险比率 = 需估算的字段点 / 模板应有的字段点。
            # 分母用模板可用字段（available_fields），模板天生没有、只能靠
            # 行业默认值填充的点不属于数据质量风险，不计入分子。
            available = (state.get("extracted") or {}).get("available_fields")
            if available:
                available_set = set(available)
                fillable_in_template = sum(
                    1 for s in state["suggestions"].get("fillable_suggestions", [])
                    if str(s.get("field", "")).split(".")[-1] in available_set
                )
                ratio = fillable_in_template / (len(available_set) * 12)
            else:
                ratio = fillable / (12 * 7)
            if ratio > self.RISKY_FILL_RATIO:
                return BrainDecision(
                    tool="request_user_input",
                    args={"reason": f"需估算的模板字段占比过高（{ratio:.0%}），建议补充原始数据后重新测算",
                          "missing_items": state["suggestions"].get("unfillable_fields", [])},
                    reason="填充依赖过重，转人工确认",
                )
            return BrainDecision(
                tool="apply_filling", args={},
                reason=f"共 {fillable} 条填充建议，风险可控，执行填充",
            )
        if "calculate_saving_rate" in available_tools:
            return BrainDecision(
                tool="calculate_saving_rate", args={},
                reason="数据已补全，运行 Excel 公式引擎计算节能率",
            )
        if "finish" in available_tools:
            result = state.get("result", {})
            rate = result.get("energy_saving_rate_range", "未知")
            return BrainDecision(
                tool="finish",
                args={"summary": (
                    f"测算完成。节能率范围为 {rate}（下限为保守估计，上限为理想情况）。"
                    f"数据完整度 {result.get('final_completeness', '未知')*100:.0f}%。"
                    "详细分项节能量与完整计算表请查看结果面板。"
                )},
                reason="计算完成，输出结论",
            )
        # 兜底：白名单里只剩 request_user_input（门禁拦截场景）
        if "request_user_input" in available_tools:
            return BrainDecision(
                tool="request_user_input",
                args={"reason": state.get("gate_reason", "当前数据不满足继续测算的条件"),
                      "missing_items": []},
                reason="流程被质量门禁拦截，需要用户介入",
            )
        raise RuntimeError(f"规则策略无法决策，可用工具: {available_tools}")
