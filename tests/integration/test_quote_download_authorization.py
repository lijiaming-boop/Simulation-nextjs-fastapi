"""会话归属鉴权回归测试（针对真实路由语义）

验证 M1 路由级 ACL：
- require_auth=True 时，无身份头 → 401
- 非会话归属人 → 403（并写审计）
- 归属人 → 放行；特权角色（admin）→ 跨会话放行
覆盖 /api/session、/api/download（AC 结果下载白名单）、
/api/quote/download（报价生成文件下载）三类数据出口。
"""

import json

import pytest
from fastapi.testclient import TestClient

from apps.api import config
from apps.api.deps import session_store
from apps.api.main import app


@pytest.fixture(autouse=True)
def _force_auth(monkeypatch):
    """本文件所有用例都在强制认证下运行"""
    monkeypatch.setattr(config.settings, "require_auth", True)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _header(sub, role=None):
    payload = {"sub": sub, "name": sub}
    if role:
        payload["role"] = role
    return {"X-User-Info": json.dumps(payload)}


def _tmp_dir():
    from core.session_manager import SessionManager
    return SessionManager().create_session_directory()


def _seed_session(owner="owner-user", module_type="air_conditioner"):
    """走公共接口注册会话并写归属人"""
    return session_store.register(_tmp_dir(), "survey.xlsx", owner, module_type)


def test_session_info_requires_auth(client):
    """无身份头 → 401"""
    sid = _seed_session()
    assert client.get(f"/api/session/{sid}").status_code == 401


def test_session_info_rejects_cross_user(client):
    """他人访问会话元数据 → 403；归属人 → 200"""
    sid = _seed_session()
    intruder = client.get(f"/api/session/{sid}", headers=_header("intruder-user"))
    assert intruder.status_code == 403
    owner = client.get(f"/api/session/{sid}", headers=_header("owner-user"))
    assert owner.status_code == 200
    assert owner.json()["session_id"] == sid


def test_privileged_role_cross_session_allowed(client):
    """特权角色（admin）可跨会话访问"""
    sid = _seed_session(owner="someone-else")
    resp = client.get(f"/api/session/{sid}", headers=_header("boss", role="admin"))
    assert resp.status_code == 200


def test_ac_download_rejects_cross_user(client, tmp_path):
    """AC 结果下载：越权 403（ACL 先于白名单校验）；归属人文件可下载"""
    sid = _seed_session()
    (tmp_path / "simplified_result.xlsx").write_bytes(b"result-excel")
    live = session_store.get(sid)
    live["session_dir"] = tmp_path
    live.save()  # 覆盖 session_dir 为测试可控目录

    intruder = client.get(
        f"/api/download/{sid}/simplified_result.xlsx",
        headers=_header("intruder-user"),
    )
    assert intruder.status_code == 403

    owner = client.get(
        f"/api/download/{sid}/simplified_result.xlsx",
        headers=_header("owner-user"),
    )
    assert owner.status_code == 200
    assert owner.content == b"result-excel"


def test_quote_download_rejects_cross_user(client, tmp_path):
    """报价生成文件下载：越权 403，归属人 200"""
    sid = _seed_session(owner="owner-user", module_type="quote")
    generated = tmp_path / f"generated_{sid}"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "报价_渠道价.xlsx").write_bytes(b"private quote")
    live = session_store.get(sid)
    live["session_dir"] = tmp_path
    live.save()

    anonymous = client.get(f"/api/quote/download/{sid}/报价_渠道价.xlsx")
    assert anonymous.status_code == 401

    intruder = client.get(
        f"/api/quote/download/{sid}/报价_渠道价.xlsx",
        headers=_header("intruder-user"),
    )
    assert intruder.status_code == 403

    owner = client.get(
        f"/api/quote/download/{sid}/报价_渠道价.xlsx",
        headers=_header("owner-user"),
    )
    assert owner.status_code == 200
    assert owner.content == b"private quote"


def test_denied_access_is_audited(client):
    """越权访问写审计留痕"""
    from apps.api.db import make_session
    from apps.api.models import AuditLog

    sid = _seed_session()
    client.get(f"/api/session/{sid}", headers=_header("intruder-user"))
    with make_session() as db:
        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "denied.access", AuditLog.session_id == sid)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.user_id == "intruder-user"
