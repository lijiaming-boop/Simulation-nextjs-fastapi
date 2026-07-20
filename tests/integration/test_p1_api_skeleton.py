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
    """测试 extract 端点返回 501"""
    client = TestClient(app)
    resp = client.post(f"/api/extract/{session_id}")
    assert resp.status_code == 501, f"extract 应返回 501，实际: {resp.status_code}"
    print(f"✅ /api/extract/{{session_id}} 正确返回 501（骨架）")


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

    print("=" * 60)
    print("  ✅ 全部测试通过")
    print("=" * 60)
