"""共享依赖：会话存储、用户认证、配置"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

from fastapi import Depends, Header, HTTPException, status

from core.session_manager import SessionManager


# ==================== 会话存储 ====================

class SessionStore:
    """进程内会话存储（POC 级别）

    - session_id → 会话元数据（目录、文件名、阶段、用户信息、AI 日志）
    - 生产期可换 Redis，接口不变
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, dict] = {}
        self._manager: SessionManager = SessionManager()

    @property
    def manager(self) -> SessionManager:
        return self._manager

    def register(
        self,
        session_dir: Path,
        original_filename: str,
        user_id: Optional[str],
        module_type: str,
    ) -> str:
        """注册一个新会话，返回 session_id"""
        session_id = session_dir.name  # 沿用 SessionManager 命名
        self._sessions[session_id] = {
            "session_id": session_id,
            "session_dir": session_dir,
            "original_filename": original_filename,
            "user_id": user_id,
            "module_type": module_type,  # "air_conditioner" | "air_compressor" | "plant_simulation"
            "stage": "upload",
            "ai_logs": [],               # 累计 AI 消息（timestamp, message）
            "extracted_data": None,
            "quality_report": None,
            "filling_suggestions": None,
            "result": None,
            # === 仿真模块专用字段 ===
            "sim_stage": "topology",     # topology / cop_curves / operating / simulate
            "sim_mode": "new_station",   # new_station / old_station
            "sim_topology": None,
            "sim_cop_data": {},
            "sim_operating_conditions": None,
            "sim_result": None,
            "sim_project_name": "",
            # === 多方案对比（仅 old_station） ===
            "sim_baseline_power_kwh": None,
            "sim_schemes": [],
        }
        return session_id

    def init_sim_session(
        self,
        user_id: Optional[str],
        sim_mode: str = "new_station",
    ) -> str:
        """创建仿真专用 session（无需上传调研表）"""
        session_dir = self._manager.create_session_directory()
        session_id = session_dir.name
        self._sessions[session_id] = {
            "session_id": session_id,
            "session_dir": session_dir,
            "original_filename": None,
            "user_id": user_id,
            "module_type": "plant_simulation",
            "stage": "simulation",
            "ai_logs": [],
            "extracted_data": None,
            "quality_report": None,
            "filling_suggestions": None,
            "result": None,
            "sim_stage": "topology",
            "sim_mode": sim_mode,
            "sim_topology": None,
            "sim_cop_data": {},
            "sim_operating_conditions": None,
            "sim_result": None,
            "sim_project_name": "",
            "sim_baseline_power_kwh": None,
            "sim_schemes": [],
        }
        return session_id

    def get(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def update_stage(self, session_id: str, stage: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["stage"] = stage

    def append_ai_log(self, session_id: str, timestamp: str, message: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["ai_logs"].append({
                "timestamp": timestamp,
                "message": message,
            })

    def list_sessions(self) -> list:
        return list(self._sessions.values())


# 单例（进程内共享）
session_store = SessionStore()


# ==================== 用户认证 ====================

# Go proxy 转发时通过 X-User-Info header 注入 JSON 编码的用户信息
# （参见 proxy/main.go proxyToStreamlit）
# 本地直连 API 时，此 header 缺失，回退为 "anonymous"


def get_current_user(
    x_user_info: Optional[str] = Header(default=None, alias="X-User-Info"),
) -> dict:
    """从 X-User-Info header 解析用户信息

    开发期允许缺失；生产期应要求 proxy 强制注入。
    """
    if not x_user_info:
        return {"sub": "anonymous", "name": "anonymous", "email": ""}

    import json
    try:
        return json.loads(x_user_info)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid X-User-Info: {e}",
        )


# ==================== 项目根路径 ====================

# apps/api/main.py -> 上溯两级到项目根
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


# ==================== 启动生命周期 ====================


@asynccontextmanager
async def startup_banner(app):
    """启动时打印关键环境信息，便于排查"""
    print("=" * 60)
    print("  空调/空压节能测算 FastAPI 后端")
    print("=" * 60)
    print(f"  PROJECT_ROOT : {PROJECT_ROOT}")
    print(f"  ANTHROPIC_KEY: {'已配置' if os.getenv('ANTHROPIC_API_KEY') else '❌ 缺失'}")
    print(f"  ANTHROPIC_BASE_URL: {os.getenv('ANTHROPIC_BASE_URL', '(default)')}")
    skills_dir = PROJECT_ROOT / ".claude" / "skills"
    print(f"  skills 目录  : {skills_dir} ({'存在' if skills_dir.exists() else '❌ 不存在'})")
    print("=" * 60)

    yield

    print("FastAPI 已关闭")
