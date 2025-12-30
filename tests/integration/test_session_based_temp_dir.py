"""测试基于会话的临时目录集成"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# 确保可以导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_session_directory_creation_on_upload():
    """测试上传时创建会话目录"""
    # 这个测试主要验证 session_manager 已经在 init_session_state 中被创建
    # 由于 Streamlit 的 session_state 在测试环境中难以模拟，我们主要测试核心逻辑
    from core.session_manager import SessionManager

    manager = SessionManager()
    session_dir = manager.create_session_directory()

    # 验证会话管理器可以创建会话目录
    assert session_dir.exists()
    assert session_dir.name.startswith("session_")

    # 清理
    session_dir.rmdir()


def test_reset_flow_creates_new_session():
    """测试重置流程时创建新会话目录"""
    from core.session_manager import SessionManager

    manager = SessionManager()

    # 第一次创建
    first_session_dir = manager.create_session_directory()

    # 等待确保时间戳不同
    import time
    time.sleep(1)

    # 第二次创建应创建不同的目录
    second_session_dir = manager.create_session_directory()

    assert first_session_dir != second_session_dir
    assert first_session_dir.exists()
    assert second_session_dir.exists()

    # 清理
    first_session_dir.rmdir()
    second_session_dir.rmdir()


def test_uploaded_file_saved_to_session_directory():
    """测试上传文件保存到会话目录"""
    from core.session_manager import SessionManager

    manager = SessionManager()
    session_dir = manager.create_session_directory()

    # 模拟保存文件
    upload_path = manager.get_file_path("upload_survey.xlsx")
    upload_path.write_text("test data")

    # 验证文件保存到会话目录
    assert upload_path.exists()
    assert upload_path.parent == session_dir
    assert upload_path.read_text() == "test data"

    # 清理
    upload_path.unlink()
    session_dir.rmdir()
