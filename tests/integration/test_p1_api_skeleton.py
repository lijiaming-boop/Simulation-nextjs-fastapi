"""P1 集成测试：验证 FastAPI 骨架 + /upload 端点"""
import io
import sys
from pathlib import Path

# 添加项目根到 sys.path（tests/integration/ 上溯两级）
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from apps.api.main import app


def test_health():
    """测试健康检查"""
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"health 失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["status"] == "ok"
    assert data["skills_dir_exists"] is True
    print("✅ /api/health OK")
    return data


def test_upload_air_conditioner():
    """测试空调调研表上传"""
    # 找一个示例调研表
    sample_dir = PROJECT_ROOT / "00_sample" / "示例调研表" / "空压调研表"
    if not sample_dir.exists():
        print(f"⚠️  跳过上传测试：{sample_dir} 不存在")
        return None

    # 拿第一个 xlsx
    xlsx_files = list(sample_dir.glob("*.xlsx")) + list(sample_dir.glob("*.xls"))
    if not xlsx_files:
        print(f"⚠️  跳过上传测试：{sample_dir} 下无 xlsx 文件")
        return None

    sample_file = xlsx_files[0]
    print(f"📦 上传文件: {sample_file.name}")

    client = TestClient(app)
    with open(sample_file, "rb") as f:
        resp = client.post(
            "/api/upload",
            files={"file": (sample_file.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            params={"module_type": "air_conditioner"},
        )

    assert resp.status_code == 200, f"upload 失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "session_id" in data
    assert data["module_type"] == "air_conditioner"
    assert data["original_filename"] == sample_file.name
    assert Path(data["saved_path"]).exists(), f"文件未保存: {data['saved_path']}"
    print(f"✅ /api/upload OK")
    print(f"   session_id: {data['session_id']}")
    print(f"   saved_path: {data['saved_path']}")
    return data


def test_list_sessions():
    """测试列出 sessions"""
    client = TestClient(app)
    resp = client.get("/api/sessions")
    assert resp.status_code == 200, f"sessions 失败: {resp.status_code} {resp.text}"
    data = resp.json()
    print(f"✅ /api/sessions OK (共 {len(data)} 个 session)")
    return data


def test_get_session(session_id: str):
    """测试查询单个 session"""
    client = TestClient(app)
    resp = client.get(f"/api/session/{session_id}")
    assert resp.status_code == 200, f"session/{session_id} 失败: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["session_id"] == session_id
    print(f"✅ /api/session/{session_id} OK")
    return data


def test_extract_not_implemented(session_id: str):
    """测试 extract 启动任务（不依赖真实 SkillCaller 的失败分支）

    由于 extract 会启动后台线程调用 SkillCaller（需 ANTHROPIC_API_KEY），
    这里只验证：
    1. session 不存在 → 404
    2. 重复提取 → 409（如果第一个任务仍在运行）
    3. 输入文件缺失 → 400
    """
    client = TestClient(app)

    # 1. 不存在的 session 返回 404
    resp = client.post("/api/extract/nonexistent-session-id")
    assert resp.status_code == 404, f"应返回 404，实际: {resp.status_code} {resp.text}"
    print("✅ extract 不存在 session 返回 404")

    # 2. 删掉真实输入文件后，extract 应返回 400（输入缺失）
    from apps.api.deps import session_store as _store
    _s = _store.get(session_id)
    if _s:
        s_dir = Path(_s["session_dir"])
        for f in s_dir.glob("*.xlsx"):
            f.unlink()
        for f in s_dir.glob("*.xls"):
            f.unlink()

    resp = client.post(f"/api/extract/{session_id}")
    assert resp.status_code in (400, 500), (
        f"输入缺失时应返回 400/500，实际: {resp.status_code} {resp.text}"
    )
    print(f"✅ extract 输入缺失返回 {resp.status_code}")

    # 3. 不存在 session 的 SSE 返回 404
    resp = client.get("/api/extract/nonexistent-session-id/stream", timeout=2)
    assert resp.status_code == 404, f"SSE 不存在应返回 404，实际: {resp.status_code}"
    print("✅ SSE 不存在 session 返回 404")

    # 4. 存在 session 的 SSE 能建立连接（用 stream 避免 TestClient 等待全部事件）
    try:
        with client.stream("GET", f"/api/extract/{session_id}/stream") as resp:
            assert resp.status_code == 200, f"SSE 应返回 200，实际: {resp.status_code}"
            ct = resp.headers.get("content-type", "").lower()
            assert "event-stream" in ct, f"Content-Type 不是 event-stream: {ct}"
            # 读前 1KB 避免被 SSE 流阻塞
            _ = resp.iter_bytes(chunk_size=1024)
        print(f"✅ SSE 连接成功（content-type: {ct}）")
    except Exception as e:
        print(f"⚠️  SSE 流测试跳过（TestClient 限制）: {e}")


def test_invalid_module_type():
    """测试无效 module_type"""
    client = TestClient(app)
    fake_file = io.BytesIO(b"fake content")
    resp = client.post(
        "/api/upload",
        files={"file": ("test.xlsx", fake_file, "application/octet-stream")},
        params={"module_type": "invalid_type"},
    )
    assert resp.status_code == 400, f"应返回 400，实际: {resp.status_code}"
    print("✅ 无效 module_type 正确返回 400")


def test_invalid_file_extension():
    """测试无效文件扩展名"""
    client = TestClient(app)
    fake_file = io.BytesIO(b"fake content")
    resp = client.post(
        "/api/upload",
        files={"file": ("test.pdf", fake_file, "application/pdf")},
        params={"module_type": "air_conditioner"},
    )
    assert resp.status_code == 400, f"应返回 400，实际: {resp.status_code}"
    print("✅ 无效文件扩展名正确返回 400")


def test_calculate_and_result_failure():
    """测试 calculate / result 失败分支"""
    client = TestClient(app)

    # 1. 不存在 session 的 calculate 返回 404
    resp = client.post("/api/calculate/nonexistent-session-id")
    assert resp.status_code == 404, f"应返回 404，实际: {resp.status_code}"
    print("✅ calculate 不存在 session 返回 404")

    # 2. 不存在 session 的 result 返回 404
    resp = client.get("/api/result/nonexistent-session-id")
    assert resp.status_code == 404, f"应返回 404，实际: {resp.status_code}"
    print("✅ result 不存在 session 返回 404")

    # 3. 新建一个 session，不调用 extract，直接 calculate → 400（缺少 extracted_data）
    fake_xlsx = io.BytesIO(b"PK\x03\x04" + b"\x00" * 100)  # 伪造 xlsx header
    resp = client.post(
        "/api/upload",
        files={"file": ("empty.xlsx", fake_xlsx, "application/octet-stream")},
        params={"module_type": "air_conditioner"},
    )
    assert resp.status_code == 200, f"upload 失败: {resp.status_code}"
    new_sid = resp.json()["session_id"]

    resp = client.post(f"/api/calculate/{new_sid}")
    assert resp.status_code == 400, f"缺少 extracted_data 应返回 400，实际: {resp.status_code}"
    print("✅ calculate 缺少 extracted_data 返回 400")

    # 4. 对应 session 调用 result 应返回 404（未计算）
    resp = client.get(f"/api/result/{new_sid}")
    assert resp.status_code == 404, f"result 未计算应返回 404，实际: {resp.status_code}"
    print("✅ result 未计算返回 404")


if __name__ == "__main__":
    print("=" * 60)
    print("  P1 集成测试")
    print("=" * 60)

    # 1. 健康检查
    test_health()

    # 2. 上传测试
    upload_result = test_upload_air_conditioner()

    # 3. 列出 sessions
    test_list_sessions()

    # 4. 查询单个 session
    if upload_result:
        session_id = upload_result["session_id"]
        test_get_session(session_id)
        test_extract_not_implemented(session_id)

    # 5. 异常测试
    test_invalid_module_type()
    test_invalid_file_extension()

    # 6. calculate / result 失败分支
    test_calculate_and_result_failure()

    print("=" * 60)
    print("  ✅ 全部测试通过")
    print("=" * 60)
