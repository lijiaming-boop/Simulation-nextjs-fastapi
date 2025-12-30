"""端到端测试：会话目录隔离"""
import pytest
from pathlib import Path
from core.session_manager import SessionManager


def test_multiple_sessions_isolated():
    """测试多个会话完全隔离"""
    import time

    manager = SessionManager()

    # 会话1
    session1 = manager.create_session_directory()
    file1 = session1 / "test.txt"
    file1.write_text("session 1 data")

    # 等待确保时间戳不同
    time.sleep(1.1)

    # 会话2
    session2 = manager.create_session_directory()
    file2 = session2 / "test.txt"
    file2.write_text("session 2 data")

    # 验证隔离
    assert file1.read_text() == "session 1 data"
    assert file2.read_text() == "session 2 data"
    assert session1 != session2

    # 清理
    manager.cleanup_session(session1)
    manager.cleanup_session(session2)


def test_session_directory_lifecycle():
    """测试会话目录完整生命周期"""
    manager = SessionManager()

    # 创建会话
    session_dir = manager.create_session_directory()
    assert session_dir.exists()

    # 创建文件
    test_files = [
        "upload_survey.xlsx",
        "extract_check_result.json",
        "extracted_data.json",
        "quality_report.json",
        "filling_suggestions.json",
        "filled_data.json",
        "result_data.json",
        "calculation_result.xlsx"
    ]

    for filename in test_files:
        filepath = session_dir / filename
        filepath.write_text(f"test data for {filename}")

    # 验证所有文件存在
    for filename in test_files:
        assert (session_dir / filename).exists()

    # 清理会话
    manager.cleanup_session(session_dir)

    # 验证目录和所有文件都被删除
    assert not session_dir.exists()
    for filename in test_files:
        assert not (session_dir / filename).exists()


def test_cleanup_old_sessions_preserves_recent():
    """测试清理旧会话时保留最近的"""
    import time
    import tempfile
    from pathlib import Path

    # 使用独立的临时目录进行测试，避免影响主目录
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(base_dir=Path(tmpdir))

        # 创建15个会话
        sessions = []
        for i in range(15):
            session = manager.create_session_directory()
            (session / f"file_{i}.txt").write_text(f"session {i}")
            sessions.append(session)
            # 确保时间戳不同（较短的时间间隔）
            time.sleep(0.05)

        # 验证所有15个会话都已创建
        all_sessions_before = manager.list_all_sessions()
        assert len(all_sessions_before) == 15

        # 清理，保留最近10个
        deleted_count = manager.cleanup_old_sessions(keep_count=10)

        # 验证删除了5个
        assert deleted_count == 5

        # 验证最近10个还在
        remaining_sessions = manager.list_all_sessions()
        assert len(remaining_sessions) == 10

        # 验证最早的5个被删除（sessions[0:5]）
        for session in sessions[:5]:
            assert not session.exists()

        # 验证最近的10个还在（sessions[5:15]）
        for session in sessions[5:15]:
            assert session.exists()
