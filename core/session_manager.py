"""会话目录管理器

为每次上传任务创建独立的临时目录，避免文件覆盖
"""
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import shutil


class SessionManager:
    """会话目录管理器"""

    def __init__(self, base_dir: Optional[Path] = None):
        """初始化会话管理器

        Args:
            base_dir: 基础目录，默认为项目根目录下的 tmp
        """
        if base_dir is None:
            # 默认使用项目根目录下的 tmp 目录
            self.base_dir = Path(__file__).parent.parent / "tmp"
        else:
            self.base_dir = Path(base_dir)

        # 确保基础目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 当前会话目录
        self._current_session_dir: Optional[Path] = None

    def create_session_directory(self) -> Path:
        """创建新的会话目录

        Returns:
            会话目录路径
        """
        # 生成目录名: session_YYYYMMDD_HHMMSS
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dir_name = f"session_{timestamp}"

        # 创建目录
        session_dir = self.base_dir / dir_name
        session_dir.mkdir(parents=True, exist_ok=True)

        # 更新当前会话目录
        self._current_session_dir = session_dir

        return session_dir

    def get_current_session_directory(self) -> Optional[Path]:
        """获取当前会话目录

        Returns:
            当前会话目录路径，如果未创建则返回 None
        """
        return self._current_session_dir

    def get_file_path(self, filename: str) -> Path:
        """获取会话目录中的文件路径

        Args:
            filename: 文件名

        Returns:
            完整文件路径

        Raises:
            RuntimeError: 如果当前会话目录未创建
        """
        if self._current_session_dir is None:
            raise RuntimeError("会话目录未创建，请先调用 create_session_directory()")

        return self._current_session_dir / filename

    def list_all_sessions(self) -> List[Path]:
        """列出所有会话目录

        Returns:
            会话目录路径列表，按时间倒序排列
        """
        # 查找所有 session_* 目录
        session_dirs = [
            d for d in self.base_dir.iterdir()
            if d.is_dir() and d.name.startswith("session_")
        ]

        # 按修改时间倒序排列（最新的在前）
        session_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

        return session_dirs

    def cleanup_session(self, session_dir: Path) -> None:
        """清理指定的会话目录

        Args:
            session_dir: 要清理的会话目录
        """
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def cleanup_old_sessions(self, keep_count: int = 10) -> int:
        """清理旧的会话目录，保留最近的 N 个

        Args:
            keep_count: 保留的会话数量

        Returns:
            清理的会话数量
        """
        all_sessions = self.list_all_sessions()

        # 保留最近的 N 个，删除其余的
        sessions_to_delete = all_sessions[keep_count:]

        for session_dir in sessions_to_delete:
            self.cleanup_session(session_dir)

        return len(sessions_to_delete)
