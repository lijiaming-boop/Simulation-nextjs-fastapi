"""测试会话目录管理器"""
import pytest
from pathlib import Path
from datetime import datetime
from core.session_manager import SessionManager


def test_create_session_directory():
    """测试创建会话目录"""
    manager = SessionManager()
    session_dir = manager.create_session_directory()

    # 验证目录格式: session_YYYYMMDD_HHMMSS_mmm (mmm = 毫秒)
    assert session_dir.name.startswith("session_")
    # 格式: session_20251230_153045_123 或 session_20251230_153045_123_1 (带计数器)
    assert len(session_dir.name) >= len("session_20251230_153045_123")

    # 验证目录已创建
    assert session_dir.exists()
    assert session_dir.is_dir()

    # 清理
    session_dir.rmdir()


def test_get_file_path():
    """测试获取会话目录中的文件路径"""
    manager = SessionManager()
    session_dir = manager.create_session_directory()

    # 获取文件路径
    upload_path = manager.get_file_path("upload_survey.xlsx")

    # 验证路径正确
    assert upload_path.parent == session_dir
    assert upload_path.name == "upload_survey.xlsx"

    # 清理
    session_dir.rmdir()


def test_list_all_sessions():
    """测试列出所有会话目录"""
    import time

    manager = SessionManager()

    # 创建多个会话
    session1 = manager.create_session_directory()

    # 等待1秒确保时间戳不同
    time.sleep(1)

    session2 = manager.create_session_directory()

    # 列出所有会话
    all_sessions = manager.list_all_sessions()

    # 验证至少包含刚创建的两个
    assert session1 in all_sessions
    assert session2 in all_sessions

    # 清理（先删除session2，后删除session1）
    if session2.exists():
        session2.rmdir()
    if session1.exists():
        session1.rmdir()


def test_cleanup_old_sessions():
    """测试清理旧会话目录（可选功能）"""
    manager = SessionManager()

    # 创建会话目录
    session_dir = manager.create_session_directory()

    # 创建一些文件
    test_file = session_dir / "test.txt"
    test_file.write_text("test")

    # 清理会话
    manager.cleanup_session(session_dir)

    # 验证目录和文件都被删除
    assert not session_dir.exists()


def test_get_current_session_directory():
    """测试获取当前会话目录"""
    manager = SessionManager()

    # 首次调用应返回 None（未初始化）
    assert manager.get_current_session_directory() is None

    # 创建会话后应返回该目录
    session_dir = manager.create_session_directory()
    assert manager.get_current_session_directory() == session_dir

    # 清理
    session_dir.rmdir()
