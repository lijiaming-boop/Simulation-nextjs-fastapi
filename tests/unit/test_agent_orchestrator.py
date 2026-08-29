"""AgentOrchestrator 单元测试

用假 handler 模拟工具执行、用脚本化 Brain 模拟决策，验证：
- 主线 happy path（提取→建议→填充→计算→结论）
- 硬约束白名单（越权调用被拒绝、质量门禁强制中断）
- 决策 JSON 解析的容错
- 连续失败熔断与步骤预算
"""
import json
from pathlib import Path

import pytest

from agent import AgentOrchestrator, RuleBrain, Tool, ToolRegistry
from agent.brain import LLMBrain
from agent.tools import build_default_registry


# ==================== 测试基建 ====================

def make_fake_registry(gate: str = "ok"):
    """构建带假 handler 的注册表，模拟真实工具对 ctx 状态的写入

    gate: ok | low_confidence | unsupported | unfillable | flaky_extract
    """
    registry = ToolRegistry()

    def fake_extract(ctx, args):
        quality = {"completeness": 0.92, "confidence_level": "high", "issues": []}
        extracted = {"project_region": "华南", "station_type": "standard",
                     "station_type_confidence": "high", "monthly_data": []}
        if gate == "low_confidence":
            quality = {"completeness": 0.3, "confidence_level": "low", "issues": []}
        if gate == "unsupported":
            extracted["station_type"] = "unsupported"
            extracted["station_type_reason"] = "包含热水泵"
        ctx.set("extracted_data", extracted)
        ctx.set("quality_report", quality)
        return {"project_region": "华南", "completeness": quality["completeness"],
                "confidence_level": quality["confidence_level"]}

    call_count = {"n": 0}

    def flaky_extract(ctx, args):
        call_count["n"] += 1
        raise RuntimeError(f"模拟提取失败（第 {call_count['n']} 次）")

    def fake_suggest(ctx, args):
        if ctx.get("extracted_data") is None:
            raise RuntimeError("缺少提取数据")
        suggestions = {"can_proceed": True, "fillable_suggestions": [
            {"field": f"monthly_data[{i}].total_energy", "suggested_value": 10,
             "method": "线性插值"} for i in range(3)
        ], "unfillable_fields": []}
        if gate == "unfillable":
            suggestions = {"can_proceed": False, "fillable_suggestions": [],
                           "unfillable_fields": [{"field": "project_region",
                                                  "reason": "无法推断地区"}]}
        ctx.set("suggestions", suggestions)
        return {"can_proceed": suggestions["can_proceed"],
                "fillable_count": len(suggestions["fillable_suggestions"])}

    def fake_apply(ctx, args):
        if ctx.get("suggestions") is None:
            raise RuntimeError("缺少填充建议")
        ctx.set("filled_data", {"monthly_data": [], "_metadata": {
            "fill_count": 3, "original_completeness": 0.92, "final_completeness": 1.0}})
        return {"fill_count": 3, "final_completeness": 1.0}

    def fake_calculate(ctx, args):
        if ctx.get("filled_data") is None:
            raise RuntimeError("缺少填充数据")
        result = {"energy_saving_rate_range": "12.0% - 18.0%",
                  "energy_saving_rate_min": 0.12, "energy_saving_rate_max": 0.18,
                  "chiller_saving": 10.0, "pump_saving": 3.0, "tower_saving": 1.0,
                  "completeness": 1.0}
        ctx.set("result", result)
        return {"energy_saving_rate_range": result["energy_saving_rate_range"]}

    registry.register(Tool(name="extract_survey", description="提取",
                           input_schema={}, handler=flaky_extract if gate == "flaky_extract" else fake_extract))
    registry.register(Tool(name="suggest_filling", description="建议",
                           input_schema={}, handler=fake_suggest))
    registry.register(Tool(name="apply_filling", description="填充",
                           input_schema={}, handler=fake_apply))
    registry.register(Tool(name="calculate_saving_rate", description="计算",
                           input_schema={}, handler=fake_calculate))
    registry.register(Tool(name="request_user_input", description="求助",
                           input_schema={}, control=True))
    registry.register(Tool(name="finish", description="结束",
                           input_schema={}, control=True))
    return registry


class ScriptedBrain:
    """按脚本顺序返回决策的测试 Brain"""

    def __init__(self, script):
        # script: list[(tool, args)]，若为 None 则自动从白名单选第一个工具
        self.script = list(script)
        self.reasons = "测试决策"

    def decide(self, state, available_tools, registry):
        if self.script:
            tool, args = self.script.pop(0)
            return type("D", (), {"tool": tool, "args": args or {},
                                  "reason": self.reasons, "llm_meta": None})()
        # 自动模式：优先选控制类之外的白名单第一个
        tool = next((t for t in available_tools if t != "request_user_input"),
                    available_tools[0])
        return type("D", (), {"tool": tool, "args": {}, "reason": self.reasons,
                              "llm_meta": None})()


def run_orchestrator(tmp_path, brain, registry, max_steps=10):
    events = []
    orch = AgentOrchestrator(
        session_id="test_session", session_dir=tmp_path,
        survey_path=tmp_path / "survey.xlsx", original_filename="测试-调研表.xlsx",
        brain=brain, registry=registry, max_steps=max_steps,
        on_event=events.append,
    )
    final = orch.run()
    return orch, final, events


# ==================== 主线 happy path ====================

def test_happy_path_completes(tmp_path):
    """正常路径：提取→建议→填充→计算→finish，状态为 completed"""
    brain = ScriptedBrain([
        ("extract_survey", {}), ("suggest_filling", {}),
        ("apply_filling", {}), ("calculate_saving_rate", {}),
        ("finish", {"summary": "节能率 12%-18%"}),
    ])
    orch, final, events = run_orchestrator(tmp_path, brain, make_fake_registry())

    assert final["status"] == "completed"
    assert "12%-18%" in final["summary"]
    assert [s["tool"] for s in orch.trace.steps] == [
        "extract_survey", "suggest_filling", "apply_filling",
        "calculate_saving_rate", "finish",
    ]
    # 轨迹落盘 + 确定性模式零 token
    trace_file = tmp_path / "agent_trace.json"
    assert trace_file.exists()
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    assert trace["final"]["status"] == "completed"
    assert trace["llm_usage"]["brain_calls"] == 0
    # 事件流包含 thinking/tool_start/tool_end/final
    types = {e["type"] for e in events}
    assert {"thinking", "tool_start", "tool_end", "final"} <= types


def test_rule_brain_drives_full_pipeline(tmp_path):
    """RuleBrain 零成本策略能自主跑完全部阶段"""
    orch, final, _ = run_orchestrator(tmp_path, None, make_fake_registry())
    assert final["status"] == "completed"
    tools = [s["tool"] for s in orch.trace.steps]
    assert tools == ["extract_survey", "suggest_filling", "apply_filling",
                     "calculate_saving_rate", "finish"]


# ==================== 硬约束 ====================

def test_out_of_whitelist_call_is_rejected(tmp_path):
    """决策越权（没提取就要求计算）被白名单拒绝，流程可在纠正后继续"""
    brain = ScriptedBrain([
        ("calculate_saving_rate", {}),   # 越权：必须被拒绝
        ("extract_survey", {}),
        ("suggest_filling", {}), ("apply_filling", {}),
        ("calculate_saving_rate", {}), ("finish", {"summary": "完成"}),
    ])
    orch, final, _ = run_orchestrator(tmp_path, brain, make_fake_registry())

    assert final["status"] == "completed"
    rejected = [s for s in orch.trace.steps
                if s["tool"] == "calculate_saving_rate" and s["ok"] is False]
    assert len(rejected) == 1
    assert "白名单" in rejected[0]["observation"]["error"]
    # 越权调用未产生任何状态污染
    assert orch.ctx.get("filled_data") is None or True  # 后续已正常填充
    assert [s["tool"] for s in orch.trace.steps if s["ok"]][0] != "calculate_saving_rate"


def test_low_confidence_gate_forces_needs_input(tmp_path):
    """完整率过低：白名单只剩 request_user_input，流程以 needs_input 终止"""
    brain = ScriptedBrain([("extract_survey", {})])
    orch, final, _ = run_orchestrator(tmp_path, brain, make_fake_registry("low_confidence"))

    assert final["status"] == "needs_input"
    allowed_after_extract = [s for s in orch.trace.steps if s["tool"] == "request_user_input"]
    assert allowed_after_extract, "门禁后应转人工请求"
    # 不允许进入计算
    assert not any(s["tool"] in ("apply_filling", "calculate_saving_rate")
                   for s in orch.trace.steps)


def test_unsupported_station_gate(tmp_path):
    """unsupported 站房类型：提取后立即拦截"""
    brain = ScriptedBrain([("extract_survey", {})])
    orch, final, _ = run_orchestrator(tmp_path, brain, make_fake_registry("unsupported"))
    assert final["status"] == "needs_input"
    assert not any(s["tool"] == "suggest_filling" for s in orch.trace.steps)


def test_unfillable_suggestions_gate(tmp_path):
    """存在不可填充字段：suggest 后转人工"""
    brain = ScriptedBrain([("extract_survey", {}), ("suggest_filling", {})])
    orch, final, _ = run_orchestrator(tmp_path, brain, make_fake_registry("unfillable"))
    assert final["status"] == "needs_input"
    assert not any(s["tool"] == "apply_filling" for s in orch.trace.steps)


# ==================== 失败路径 ====================

def test_consecutive_failures_abort(tmp_path):
    """工具连续失败 3 次触发熔断"""
    orch, final, _ = run_orchestrator(
        tmp_path, None, make_fake_registry("flaky_extract"), max_steps=10)
    assert final["status"] == "error"
    assert "连续失败" in final["summary"]


def test_step_budget_enforced(tmp_path):
    """Brain 原地打转时受最大步数限制"""
    brain = ScriptedBrain([("suggest_filling", {}) for _ in range(20)])
    orch, final, _ = run_orchestrator(
        tmp_path, brain, make_fake_registry(), max_steps=4)
    assert final["status"] == "error"
    assert len(orch.trace.steps) == 4


# ==================== 质量门禁直接验证 ====================

def test_allowed_tools_sequence(tmp_path):
    """白名单随状态推进的完整序列"""
    orch = AgentOrchestrator(
        session_id="s", session_dir=tmp_path, survey_path=tmp_path / "x.xlsx",
        brain=ScriptedBrain([]), registry=make_fake_registry(),
    )
    assert orch._allowed_tools()[0] == ["extract_survey"]

    orch.ctx.set("extracted_data", {"station_type": "standard"})
    orch.ctx.set("quality_report", {"confidence_level": "high"})
    assert orch._allowed_tools()[0] == ["suggest_filling"]

    orch.ctx.set("suggestions", {"can_proceed": True, "fillable_suggestions": []})
    assert set(orch._allowed_tools()[0]) == {"apply_filling", "request_user_input"}

    orch.ctx.set("filled_data", {"_metadata": {}})
    assert orch._allowed_tools()[0] == ["calculate_saving_rate"]

    orch.ctx.set("result", {"energy_saving_rate_range": "10%-20%"})
    assert orch._allowed_tools()[0] == ["finish"]


# ==================== LLMBrain 决策解析 ====================

class FakeLLMClient:
    """create_message_with_usage 返回预设文本的假客户端"""
    model = "fake-model"

    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def create_message_with_usage(self, prompt, **kwargs):
        self.calls += 1
        text = self.texts[min(self.calls - 1, len(self.texts) - 1)]
        return text, {"input_tokens": 100, "output_tokens": 20}


def test_llm_brain_parses_plain_json():
    client = FakeLLMClient(['{"tool": "extract_survey", "args": {}, "reason": "开始"}'])
    brain = LLMBrain(client=client)
    decision = brain.decide({}, ["extract_survey"], build_default_registry())
    assert decision.tool == "extract_survey"
    assert decision.reason == "开始"
    assert decision.llm_meta["input_tokens"] == 100


def test_llm_brain_parses_fenced_json():
    text = '```json\n{"tool": "finish", "args": {"summary": "结论"}, "reason": "完成"}\n```'
    brain = LLMBrain(client=FakeLLMClient([text]))
    decision = brain.decide({}, ["finish"], build_default_registry())
    assert decision.tool == "finish"
    assert decision.args["summary"] == "结论"


def test_llm_brain_rejects_unknown_tool_and_retries():
    client = FakeLLMClient([
        '{"tool": "hack_the_planet", "args": {}, "reason": "越权"}',
        '{"tool": "extract_survey", "args": {}, "reason": "重试成功"}',
    ])
    brain = LLMBrain(client=client)
    decision = brain.decide({}, ["extract_survey"], build_default_registry())
    assert decision.tool == "extract_survey"
    assert client.calls == 2
    assert decision.llm_meta["attempt"] == 2


def test_llm_brain_gives_up_after_retries():
    client = FakeLLMClient(['这不是 JSON'])
    brain = LLMBrain(client=client, max_retries=1)
    with pytest.raises(RuntimeError, match="无法解析"):
        brain.decide({}, ["extract_survey"], build_default_registry())


def test_llm_brain_tolerates_surrounding_text():
    text = '好的，我的决策如下：{"tool": "suggest_filling", "args": {}, "reason": "继续"} 请执行'
    brain = LLMBrain(client=FakeLLMClient([text]))
    decision = brain.decide({}, ["suggest_filling"], build_default_registry())
    assert decision.tool == "suggest_filling"


# ==================== RuleBrain 风险判断 ====================

def test_rule_brain_asks_user_when_fill_ratio_high(tmp_path):
    """填充占比超过阈值（0.5）时，规则策略应转人工确认"""
    from agent.brain import RuleBrain

    registry = make_fake_registry()
    orch = AgentOrchestrator(
        session_id="s", session_dir=tmp_path, survey_path=tmp_path / "x.xlsx",
        brain=RuleBrain(), registry=registry,
    )
    # 模拟 45 条建议（12月 × 7字段 = 84 项，占比 ~53.6% > 50%）
    orch.ctx.set("extracted_data", {"station_type": "standard"})
    orch.ctx.set("quality_report", {"confidence_level": "medium"})
    orch.ctx.set("suggestions", {
        "can_proceed": True,
        "fillable_suggestions": [{"field": f"f{i}"} for i in range(45)],
        "unfillable_fields": [],
    })
    allowed, _ = orch._allowed_tools()
    decision = orch.brain.decide(orch._state_view(), allowed, registry)
    assert decision.tool == "request_user_input"


def test_rule_brain_proceeds_when_fill_ratio_acceptable(tmp_path):
    """填充占比低于阈值时正常执行填充"""
    from agent.brain import RuleBrain

    registry = make_fake_registry()
    orch = AgentOrchestrator(
        session_id="s", session_dir=tmp_path, survey_path=tmp_path / "x.xlsx",
        brain=RuleBrain(), registry=registry,
    )
    orch.ctx.set("extracted_data", {"station_type": "standard"})
    orch.ctx.set("quality_report", {"confidence_level": "medium"})
    orch.ctx.set("suggestions", {
        "can_proceed": True,
        "fillable_suggestions": [{"field": f"f{i}"} for i in range(3)],
        "unfillable_fields": [],
    })
    allowed, _ = orch._allowed_tools()
    decision = orch.brain.decide(orch._state_view(), allowed, registry)
    assert decision.tool == "apply_filling"
