"""M1 平台底座测试：持久化、认证 ACL、agent 断点恢复"""
import json
from pathlib import Path

import pytest

from core.session_manager import SessionManager


# ==================== 持久化 ====================

@pytest.fixture()
def fresh_store(tmp_path, monkeypatch):
    """独立 SQLite 库 + 独立会话目录的存储实例（模拟全新进程）"""
    from apps.api import config, db as db_mod
    from apps.api.storage import PersistentSessionStore

    url = f"sqlite:///{tmp_path / 'm1.db'}"
    monkeypatch.setattr(config.settings, "database_url", url)
    monkeypatch.setattr(db_mod, "_engine", None)
    store = PersistentSessionStore(manager=SessionManager(base_dir=tmp_path / "tmp"))
    yield store
    monkeypatch.setattr(db_mod, "_engine", None)


def test_session_survives_store_restart(fresh_store, tmp_path, monkeypatch):
    """会话落库：新实例（模拟进程重启）能读回全部状态"""
    from apps.api import db as db_mod

    sid = fresh_store.register(tmp_path / "tmp" / "s1", "调研表.xlsx",
                               "user-a", "air_conditioner")
    fresh_store.update_stage(sid, "result")
    fresh_store.append_ai_log(sid, "12:00:00", "hello")

    # 模拟重启：换全新引擎 + 全新 store 实例
    monkeypatch.setattr(db_mod, "_engine", None)
    from apps.api.storage import PersistentSessionStore
    store2 = PersistentSessionStore(manager=SessionManager(base_dir=tmp_path / "tmp"))

    got = store2.get(sid)
    assert got is not None
    assert got["stage"] == "result"
    assert got["ai_logs"] == [{"timestamp": "12:00:00", "message": "hello"}]
    assert got["original_filename"] == "调研表.xlsx"
    assert got["user_id"] == "user-a"
    assert hasattr(got["session_dir"], "name")  # Path 类型保持


def test_live_session_write_through(fresh_store, tmp_path):
    """写透语义：get() 返回的 dict 赋值即落库"""
    sid = fresh_store.register(tmp_path / "tmp" / "s2", "a.xlsx", "user-a",
                               "air_conditioner")
    s = fresh_store.get(sid)
    s["result"] = {"energy_saving_rate_range": "10%-20%"}
    s["stage"] = "result"  # 同样走写透

    # 新实例读到（等价于重启后仍在）
    from apps.api.storage import PersistentSessionStore
    store2 = PersistentSessionStore(manager=SessionManager(base_dir=tmp_path / "tmp"))
    got = store2.get(sid)
    assert got["result"]["energy_saving_rate_range"] == "10%-20%"
    assert got["stage"] == "result"


def test_agent_run_steps_and_trace(fresh_store, tmp_path):
    """run/step 落库、token 计量、trace 重建"""
    sid = fresh_store.register(tmp_path / "tmp" / "s3", "a.xlsx", "user-a",
                               "air_conditioner")
    run_id = fresh_store.create_run(sid, "deterministic")
    fresh_store.add_step(run_id, {
        "step": 1, "tool": "extract_survey", "args": {}, "ok": True,
        "observation": {"completeness": 0.9},
        "decision": {"input_tokens": 100, "output_tokens": 20},
    })
    fresh_store.add_step(run_id, {
        "step": 2, "tool": "finish", "args": {}, "ok": True,
        "observation": {"status": "completed"},
    })
    fresh_store.update_run(run_id, status="completed", summary="完成")

    run = fresh_store.get_latest_run(sid)
    assert run["status"] == "completed"
    assert run["step_count"] == 2
    assert run["llm_usage"]["input_tokens"] == 100

    trace = fresh_store.trace_from_db(sid)
    assert [s["tool"] for s in trace["steps"]] == ["extract_survey", "finish"]
    assert trace["final"]["status"] == "completed"


def test_stale_run_recovery(fresh_store, tmp_path):
    """启动恢复：遗留 running 被标记 interrupted，可被 resume 发现"""
    sid = fresh_store.register(tmp_path / "tmp" / "s4", "a.xlsx", "user-a",
                               "air_conditioner")
    fresh_store.create_run(sid, "llm")

    from apps.api import config, db as db_mod
    from apps.api.db import mark_stale_runs_interrupted
    n = mark_stale_runs_interrupted()
    assert n >= 1
    run = fresh_store.get_latest_run(sid, statuses=["interrupted"])
    assert run is not None
    assert "resume" in run["summary"]


def test_audit_log_written(fresh_store, tmp_path):
    """审计：拒绝访问等敏感动作有留痕（此处验证写入口）"""
    sid = fresh_store.register(tmp_path / "tmp" / "s5", "a.xlsx", "user-a",
                               "air_conditioner")
    fresh_store.audit("user-b", "denied.access", sid, {"owner": "user-a"})
    # 无异常即写入成功；进一步验证见 ACL 测试


# ==================== 认证与 ACL ====================

@pytest.fixture()
def auth_client(monkeypatch, tmp_path):
    """require_auth=True 的 TestClient + 独立库"""
    from fastapi.testclient import TestClient

    from apps.api import config, db as db_mod
    from apps.api.main import app

    monkeypatch.setattr(config.settings, "require_auth", True)
    monkeypatch.setattr(config.settings, "database_url",
                        f"sqlite:///{tmp_path / 'acl.db'}")
    monkeypatch.setattr(db_mod, "_engine", None)

    def _header(sub, role=None):
        payload = {"sub": sub, "name": sub}
        if role:
            payload["role"] = role
        return {"X-User-Info": json.dumps(payload)}

    with TestClient(app) as client:
        yield client, _header

    monkeypatch.setattr(db_mod, "_engine", None)


def _upload(client, headers):
    import io
    resp = client.post(
        "/api/upload?module_type=air_conditioner",
        files={"file": ("表.xlsx", io.BytesIO(b"not-a-real-xlsx"), "application/octet-stream")},
        headers=headers,
    )
    return resp


def test_auth_missing_header_rejected(auth_client):
    """强制认证下，无身份头 → 401"""
    client, _ = auth_client
    resp = _upload(client, {})
    assert resp.status_code == 401


def test_owner_can_access_but_others_denied(auth_client):
    """归属人可访问，他人 403，特权角色放行"""
    client, header = auth_client
    resp = _upload(client, header("sales-a"))
    assert resp.status_code == 200
    sid = resp.json()["session_id"]

    # 归属人
    assert client.get(f"/api/session/{sid}", headers=header("sales-a")).status_code == 200
    # 他人越权
    assert client.get(f"/api/session/{sid}", headers=header("sales-b")).status_code == 403
    # 特权角色
    assert client.get(f"/api/session/{sid}", headers=header("boss", role="admin")).status_code == 200
    # 越权访问下载同样被拒
    assert client.get(
        f"/api/download/{sid}/simplified_result.xlsx",
        headers=header("sales-b"),
    ).status_code == 403


def test_dev_mode_still_open(auth_client, monkeypatch, tmp_path):
    """require_auth=False（开发模式）保持零配置可跑"""
    from fastapi.testclient import TestClient

    from apps.api import config, db as db_mod
    from apps.api.main import app

    monkeypatch.setattr(config.settings, "require_auth", False)
    monkeypatch.setattr(config.settings, "database_url",
                        f"sqlite:///{tmp_path / 'dev.db'}")
    monkeypatch.setattr(db_mod, "_engine", None)
    with TestClient(app) as client:
        resp = _upload(client, {})
        assert resp.status_code == 200


# ==================== agent 断点恢复 ====================

def _fake_registry_with_files():
    """带文件产物的假工具注册表：支持 hydrate 断点恢复"""
    from agent import Tool, ToolRegistry

    def _dump(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    registry = ToolRegistry()

    def fake_extract(ctx, args):
        extracted = {"project_region": "华南", "station_type": "standard",
                     "monthly_data": [{"month": m} for m in range(1, 13)]}
        quality = {"completeness": 0.92, "confidence_level": "high", "issues": []}
        ctx.set("extracted_data", extracted)
        ctx.set("quality_report", quality)
        _dump(ctx.session_dir / "extracted_data.json", extracted)
        _dump(ctx.session_dir / "quality_report.json", quality)
        return {"completeness": 0.92}

    def fake_suggest(ctx, args):
        suggestions = {"can_proceed": True,
                       "fillable_suggestions": [{"field": "monthly_data[1].total_energy",
                                                 "suggested_value": 1, "method": "线性插值"}],
                       "unfillable_fields": []}
        ctx.set("suggestions", suggestions)
        _dump(ctx.session_dir / "filling_suggestions.json", suggestions)
        return {"can_proceed": True}

    def fake_apply(ctx, args):
        filled = {"monthly_data": [], "_metadata": {"fill_count": 1,
                                                     "original_completeness": 0.92,
                                                     "final_completeness": 1.0}}
        ctx.set("filled_data", filled)
        _dump(ctx.session_dir / "filled_data.json", filled)
        return {"fill_count": 1}

    def fake_calculate(ctx, args):
        result = {"energy_saving_rate_range": "9.0% - 15.0%",
                  "energy_saving_rate_min": 0.09, "energy_saving_rate_max": 0.15,
                  "completeness": 1.0}
        ctx.set("result", result)
        _dump(ctx.session_dir / "result_data.json", result)
        return {"energy_saving_rate_range": result["energy_saving_rate_range"]}

    for name, handler in [("extract_survey", fake_extract),
                          ("suggest_filling", fake_suggest),
                          ("apply_filling", fake_apply),
                          ("calculate_saving_rate", fake_calculate)]:
        registry.register(Tool(name=name, description=name, input_schema={}, handler=handler))
    registry.register(Tool(name="request_user_input", description="x", input_schema={}, control=True))
    registry.register(Tool(name="finish", description="x", input_schema={}, control=True))
    return registry


def test_orchestrator_resume_from_breakpoint(tmp_path):
    """max_steps 中断后 hydrate 续跑到完成，步号延续、结果完整"""
    from agent import AgentOrchestrator

    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    registry = _fake_registry_with_files()

    # 第一段：预算 2 步后强制中断（extract → suggest）
    orch1 = AgentOrchestrator(
        session_id="s", session_dir=session_dir,
        survey_path=tmp_path / "x.xlsx", brain=None,
        registry=registry, max_steps=2,
    )
    final1 = orch1.run()
    assert final1["status"] == "error"  # 预算耗尽
    assert [s["tool"] for s in orch1.trace.steps] == ["extract_survey", "suggest_filling"]
    assert orch1.ctx.get("filled_data") is None

    # 第二段：模拟重启——全新 orchestrator，从文件恢复状态续跑
    orch2 = AgentOrchestrator(
        session_id="s", session_dir=session_dir,
        survey_path=tmp_path / "x.xlsx", brain=None,
        registry=registry, max_steps=5, start_step=3,
    )
    loaded = orch2.hydrate_from_session()
    assert loaded >= 2  # extracted_data + quality_report + suggestions
    assert orch2.ctx.get("filled_data") is None  # 未执行过的阶段不会被伪造

    final2 = orch2.run()
    assert final2["status"] == "completed"
    assert [s["tool"] for s in orch2.trace.steps] == [
        "apply_filling", "calculate_saving_rate", "finish"]
    assert [s["step"] for s in orch2.trace.steps] == [3, 4, 5]  # 步号延续
    assert final2["result"]["energy_saving_rate_range"] == "9.0% - 15.0%"
