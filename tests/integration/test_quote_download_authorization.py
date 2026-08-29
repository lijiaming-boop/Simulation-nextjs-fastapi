"""Authorization regression tests for session-scoped quote downloads."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.deps import session_store
from apps.api.main import app


@pytest.mark.parametrize(
    ("route_template", "relative_file"),
    [
        (
            "/api/quote/download/{session_id}/报价_渠道价.xlsx",
            "quote_output/报价_渠道价.xlsx",
        ),
        (
            "/api/download/{session_id}/air_compressor_quotation.xlsx",
            "air_compressor_quotation.xlsx",
        ),
    ],
)
def test_quote_download_requires_session_owner(
    tmp_path,
    route_template,
    relative_file,
):
    session_id = f"session_auth_{uuid4().hex}"
    target = tmp_path / relative_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"private quote")
    session_store._sessions[session_id] = {
        "session_id": session_id,
        "session_dir": tmp_path,
        "user_id": "owner-user",
    }

    client = TestClient(app)
    route = route_template.format(session_id=session_id)
    try:
        anonymous = client.get(route)
        assert anonymous.status_code == 403

        intruder = client.get(
            route,
            headers={"X-User-Info": json.dumps({"sub": "intruder-user"})},
        )
        assert intruder.status_code == 403

        owner = client.get(
            route,
            headers={"X-User-Info": json.dumps({"sub": "owner-user"})},
        )
        assert owner.status_code == 200
        assert owner.content == b"private quote"
    finally:
        session_store._sessions.pop(session_id, None)


def test_quote_result_requires_session_owner(tmp_path):
    session_id = f"session_auth_{uuid4().hex}"
    session_store._sessions[session_id] = {
        "session_id": session_id,
        "session_dir": tmp_path,
        "user_id": "owner-user",
        "stage": "quote_done",
        "result": {"totals": {"grand_total_channel": 123.45}},
        "quote_status": "AUTO",
        "release_ready": True,
        "quote_section9_analysis": None,
        "quote_files": {},
    }

    client = TestClient(app)
    route = f"/api/quote/result/{session_id}"
    try:
        intruder = client.get(
            route,
            headers={"X-User-Info": json.dumps({"sub": "intruder-user"})},
        )
        assert intruder.status_code == 403

        owner = client.get(
            route,
            headers={"X-User-Info": json.dumps({"sub": "owner-user"})},
        )
        assert owner.status_code == 200
        assert owner.json()["result"]["totals"]["grand_total_channel"] == 123.45
    finally:
        session_store._sessions.pop(session_id, None)


@pytest.mark.parametrize(
    "route_template",
    [
        "/api/quote/extract/{session_id}",
        "/api/quote/calculate/{session_id}",
    ],
)
def test_quote_actions_reject_cross_user_access(tmp_path, route_template):
    session_id = f"session_auth_{uuid4().hex}"
    session_store._sessions[session_id] = {
        "session_id": session_id,
        "session_dir": tmp_path,
        "original_filename": "survey.xlsx",
        "user_id": "owner-user",
        "module_type": "standard_quote",
    }

    client = TestClient(app)
    try:
        response = client.post(
            route_template.format(session_id=session_id),
            headers={"X-User-Info": json.dumps({"sub": "intruder-user"})},
        )
        assert response.status_code == 403
    finally:
        session_store._sessions.pop(session_id, None)
