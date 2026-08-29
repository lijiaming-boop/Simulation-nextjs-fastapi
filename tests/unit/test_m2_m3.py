"""M2/M3 特性测试：LLM 网关、HITL 审批闭环、批量测算、历史库"""
import io
import json
import time
from pathlib import Path

import pytest

from tests.unit.test_m1_platform import fresh_store  # noqa: F401  复用隔离库 fixture


# ==================== LLM 网关 ====================

class FakeLLM:
    """可控的假 LLM 客户端"""

    def __init__(self, usage=None, fail_times=0):
        self.model = "fake-model"
        self.usage = usage or {"input_tokens": 50, "output_tokens": 20}
        self.fail_times = fail_times
        self.calls = 0

    def create_message_with_usage(self, prompt, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            from core.llm_client import LLMError
            raise LLMError("模拟上游错误")
        return "ok", dict(self.usage)


@pytest.fixture()
def gw_store(fresh_store):
    return fresh_store


def test_gateway_accounts_and_budget(gw_store):
    """计量落库 + 当日预算超额拒绝"""
    from core.llm_gateway import LLMGateway, LLMBudgetError

    gw = LLMGateway(user_id="u-budget", purpose_default="test",
                    daily_token_budget=100, client=FakeLLM(), store=gw_store)
    gw.create_message("你好")
    # 第一次已消耗 20 output token；把预算收紧到已用水平 → 下一轮超额
    gw2 = LLMGateway(user_id="u-budget", purpose_default="test",
                     daily_token_budget=20, client=FakeLLM(), store=gw_store)
    with pytest.raises(LLMBudgetError):
        gw2.create_message("再次调用")
    # 计量可查
    summary = gw_store.llm_usage_summary(user_id="u-budget")
    assert any(p["purpose"] == "test" for p in summary["by_purpose"])


def test_gateway_retries_then_succeeds(gw_store):
    from core.llm_gateway import LLMGateway

    fake = FakeLLM(fail_times=1)
    gw = LLMGateway(user_id="u-retry", client=fake, store=gw_store,
                    daily_token_budget=0)  # 0 = 不启用预算
    text = gw.create_message("hi")
    assert text == "ok"
    assert fake.calls == 2  # 1 次失败 + 重试成功


def test_gateway_breaker_opens(gw_store):
    from core.llm_client import LLMError
    from core.llm_gateway import LLMGateway, LLMGatewayError

    gw = LLMGateway(user_id="u-breaker", client=FakeLLM(fail_times=999),
                    store=gw_store, daily_token_budget=0)
    # 每次调用内部重试 2 次 = 3 次失败；2 次调用后连续 6 次 > 阈值 5 → 熔断
    for _ in range(2):
        with pytest.raises(LLMGatewayError):
            gw.create_message("hi")
    with pytest.raises(LLMGatewayError, match="熔断"):
        gw.create_message("hi")


def test_gateway_model_routing(gw_store, monkeypatch):
    from core.llm_gateway import LLMGateway

    monkeypatch.setenv("LLM_MODEL_FAST", "fast-model")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "heavy-model")
    captured = {}

    class RecordingClient(FakeLLM):
        def __init__(self):
            super().__init__()
            self._model = "fast-model"

        @property
        def model(self):
            return self._model

        @model.setter
        def model(self, v):
            self._model = v

        def create_message_with_usage(self, prompt, **kwargs):
            # 调用期捕获网关实际注入的模型（网关调用后会恢复原值）
            captured["during"] = self._model
            return "ok", {"input_tokens": 1, "output_tokens": 1}

    fake = RecordingClient()
    gw = LLMGateway(user_id="u-route", client=fake, store=gw_store,
                    daily_token_budget=0)
    gw.create_message("决策类", model_tier="fast")
    assert captured["during"] == "fast-model"
    gw.create_message("重活", model_tier="heavy")
    assert captured["during"] == "heavy-model"


# ==================== HITL 审批暂停/恢复 ====================

def test_approval_pause_and_resume(tmp_path):
    """填充占比超阈值 → 暂停待审批 → 批准后从断点恢复到完成"""
    from agent import AgentOrchestrator
    from tests.unit.test_agent_orchestrator import make_fake_registry

    session_dir = tmp_path / "hitl"
    session_dir.mkdir()

    # available_fields 限定为 total_energy：4 条建议 → 占比 4/12=33% > 25%
    registry = make_fake_registry()
    from agent import RuleBrain

    orch = AgentOrchestrator(
        session_id="s", session_dir=session_dir,
        survey_path=tmp_path / "x.xlsx", brain=RuleBrain(),
        registry=registry, require_fill_approval=True,
    )
    # 灌入状态：提取完成（available_fields 只有 total_energy）、建议可执行
    orch.ctx.set("extracted_data", {"station_type": "standard",
                                    "available_fields": ["total_energy"]})
    orch.ctx.set("quality_report", {"confidence_level": "high"})
    orch.ctx.set("suggestions", {
        "can_proceed": True,
        "fillable_suggestions": [
            {"field": f"monthly_data[{i}].total_energy", "suggested_value": 1,
             "method": "线性插值"} for i in range(4)
        ],
        "unfillable_fields": [],
    })

    # 第一段：允许走 extract…（白名单此时指向 apply/approval）→ 应请求审批
    allowed, note = orch._allowed_tools()
    assert "request_approval" in allowed
    decision = orch.brain.decide(orch._state_view(), allowed, registry)
    assert decision.tool == "request_approval"

    # 模拟审批后恢复：approval_granted=True → 白名单直通 apply_filling
    orch2 = AgentOrchestrator(
        session_id="s", session_dir=session_dir,
        survey_path=tmp_path / "x.xlsx", brain=RuleBrain(),
        registry=registry, require_fill_approval=True, approval_granted=True,
    )
    # 恢复场景：状态来自 hydrate（此处直接灌入与第一段一致的状态）
    orch2.ctx.set("extracted_data", {"station_type": "standard",
                                     "available_fields": ["total_energy"]})
    orch2.ctx.set("quality_report", {"confidence_level": "high"})
    orch2.ctx.set("suggestions", {
        "can_proceed": True,
        "fillable_suggestions": [
            {"field": f"monthly_data[{i}].total_energy", "suggested_value": 1,
             "method": "线性插值"} for i in range(4)
        ],
        "unfillable_fields": [],
    })
    allowed2, _ = orch2._allowed_tools()
    assert "apply_filling" in allowed2 and "request_approval" not in allowed2


# ==================== 批量测算 + 历史库 + 收件箱（API 级） ====================

SURVEY = "00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx"
SURVEY_BAD = "00_sample/示例调研表/【数据缺失过多 无法计算节能率】02-中央空调节能调研表（首页含问题指引）-工业板块.xlsx"


@pytest.fixture()
def api_client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from apps.api import config, db as db_mod
    from apps.api.main import app

    monkeypatch.setattr(config.settings, "database_url",
                        f"sqlite:///{tmp_path / 'm23.db'}")
    monkeypatch.setattr(db_mod, "_engine", None)
    with TestClient(app) as c:
        yield c
    monkeypatch.setattr(db_mod, "_engine", None)


def _upload(client, path):
    with open(path, "rb") as f:
        resp = client.post(
            "/api/upload?module_type=air_conditioner",
            files={"file": (Path(path).name, f, "application/vnd.ms-excel")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


def _wait_stage(client, sid, timeout=90):
    for _ in range(timeout):
        s = client.get(f"/api/session/{sid}").json()
        if s["stage"] in ("result", "error", "suggest"):
            return s["stage"]
        time.sleep(1)
    return "timeout"


def test_batch_run_and_history(api_client):
    """批量测算：两份调研表顺序跑完并产生历史记录；相似案例可查"""
    c = api_client
    resp = c.post(
        "/api/agent/batch?module_type=air_conditioner&mode=deterministic",
        files=[
            ("files", (Path(SURVEY).name, open(SURVEY, "rb"), "application/vnd.ms-excel")),
            ("files", (Path(SURVEY_BAD).name, open(SURVEY_BAD, "rb"), "application/vnd.ms-excel")),
        ],
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["batch_id"]

    batch = None
    for _ in range(120):
        batch = c.get(f"/api/agent/batch/{batch_id}").json()
        if batch["status"] == "done":
            break
        time.sleep(1)
    assert batch["status"] == "done", batch
    assert batch["completed"] == 1  # 齐全表算完
    assert batch["failed"] == 1     # 缺失表中断（needs_input 计为未完成）
    statuses = {r["status"] for r in batch["detail"]["results"]}
    assert statuses == {"completed", "needs_input"}

    # 历史库出现已完成测算
    history = c.get("/api/history?module_type=air_conditioner").json()
    assert history["count"] >= 1
    done_sid = next(
        r["session_id"] for r in batch["detail"]["results"]
        if r["status"] == "completed"
    )
    assert any(i["session_id"] == done_sid for i in history["items"])

    # 相似案例：同地区同站型历史里至少能排除自身并返回结构
    similar = c.get(f"/api/history/{done_sid}/similar").json()
    assert "items" in similar
    assert all(i["session_id"] != done_sid for i in similar["items"])


def test_inbox_needs_input_loop(api_client):
    """求助闭环：缺失表 → needs_input 待办 → 补充数据重跑 → 完成"""
    c = api_client
    sid = _upload(c, SURVEY_BAD)
    assert c.post(f"/api/agent/run/{sid}?mode=deterministic").status_code == 200
    assert _wait_stage(c, sid) == "suggest"  # needs_input 映射 stage

    inbox = c.get("/api/inbox").json()
    mine = [a for a in inbox["actions"] if a["session_id"] == sid
            and a["action_type"] == "needs_input"]
    assert mine, "应产生求助待办"

    # 上传齐全表闭环 → 重新测算 → 完成
    with open(SURVEY, "rb") as f:
        resp = c.post(f"/api/agent/{sid}/resolve?mode=deterministic",
                      files={"file": (Path(SURVEY).name, f, "application/vnd.ms-excel")})
    assert resp.status_code == 200, resp.text
    assert _wait_stage(c, sid) == "result"

    inbox_after = c.get("/api/inbox").json()
    still_pending = [a for a in inbox_after["actions"]
                     if a["session_id"] == sid and a["status"] == "pending"]
    assert not still_pending, "求助待办应已被关闭"
