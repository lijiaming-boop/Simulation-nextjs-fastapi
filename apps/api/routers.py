"""API 路由：P1 骨架 + /upload 完整跑通

完整端点（已实现）：
  GET  /api/health                   健康检查
  POST /api/upload                   上传调研表，创建 session
  GET  /api/session/{session_id}     查询 session 元数据
  GET  /api/sessions                 列出全部 session

骨架端点（返回 501，下一轮实现）：
  POST /api/extract/{session_id}     触发数据提取 + AI 质量检查
  GET  /api/extract/{session_id}/stream   AI 日志 SSE 流
  POST /api/calculate/{session_id}   触发公式计算
  GET  /api/result/{session_id}      返回最终结果 JSON
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from .deps import PROJECT_ROOT, get_current_user, session_store


router = APIRouter()


# ==================== 响应模型 ====================

class HealthResponse(BaseModel):
    status: str = "ok"
    api: str = "conditioner-saving-api"
    project_root: str
    skills_dir_exists: bool
    anthropic_configured: bool


class UploadResponse(BaseModel):
    session_id: str
    module_type: str
    original_filename: str
    saved_path: str
    session_dir: str
    created_at: str


class SessionInfo(BaseModel):
    session_id: str
    module_type: str
    original_filename: Optional[str]
    user_id: Optional[str]
    stage: str
    ai_logs_count: int
    created_at: Optional[str] = None


# ==================== /health ====================


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    """健康检查"""
    import os
    skills_dir = PROJECT_ROOT / ".claude" / "skills"
    return HealthResponse(
        status="ok",
        api="conditioner-saving-api",
        project_root=str(PROJECT_ROOT),
        skills_dir_exists=skills_dir.exists(),
        anthropic_configured=bool(os.getenv("ANTHROPIC_API_KEY")),
    )


# ==================== /upload ====================


@router.post("/upload", response_model=UploadResponse, tags=["session"])
def upload_survey(
    file: UploadFile = File(..., description="空调或空压机调研表 (.xlsx/.xls)"),
    module_type: str = Query(
        default="air_conditioner",
        description="模块类型：air_conditioner（空调）| air_compressor（空压）",
    ),
    user: dict = Depends(get_current_user),
):
    """上传调研表，创建独立会话目录

    与 Streamlit `app.py` 的 upload 阶段保持一致：
    - 校验文件扩展名（.xlsx / .xls）
    - 在 tmp/ 下创建 session_xxx 目录
    - 把文件以原始文件名保存至目录
    - 返回 session_id 供后续 extract/calculate 使用
    """
    # 1. 校验模块类型
    if module_type not in ("air_conditioner", "air_compressor"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"module_type 只能是 air_conditioner 或 air_compressor，收到 {module_type!r}",
        )

    # 2. 校验文件扩展名
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件缺少文件名",
        )
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".xlsx", ".xls"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 .xlsx / .xls，收到 {suffix!r}",
        )

    # 3. 创建会话目录（复用 core.SessionManager）
    session_dir = session_store.manager.create_session_directory()

    # 4. 流式保存文件到会话目录
    saved_path = session_dir / file.filename
    try:
        content = file.file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="上传文件为空",
            )
        with open(saved_path, "wb") as f:
            f.write(content)
    finally:
        file.file.close()

    # 5. 注册会话（内存）
    session_id = session_store.register(
        session_dir=session_dir,
        original_filename=file.filename,
        user_id=user.get("sub") or user.get("id"),
        module_type=module_type,
    )

    return UploadResponse(
        session_id=session_id,
        module_type=module_type,
        original_filename=file.filename,
        saved_path=str(saved_path),
        session_dir=str(session_dir),
        created_at=datetime.now().isoformat(),
    )


# ==================== /session ====================


@router.get("/sessions", response_model=list, tags=["session"])
def list_sessions():
    """列出当前进程内的全部 session（POC 调试用）"""
    sessions = session_store.list_sessions()
    return [
        {
            "session_id": s["session_id"],
            "module_type": s["module_type"],
            "stage": s["stage"],
            "original_filename": s["original_filename"],
            "ai_logs_count": len(s["ai_logs"]),
        }
        for s in sessions
    ]


@router.get("/session/{session_id}", response_model=SessionInfo, tags=["session"])
def get_session(session_id: str):
    """查询 session 元数据"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    return SessionInfo(
        session_id=s["session_id"],
        module_type=s["module_type"],
        original_filename=s["original_filename"],
        user_id=s["user_id"],
        stage=s["stage"],
        ai_logs_count=len(s["ai_logs"]),
    )


# ==================== 骨架端点（501） ====================


@router.post("/extract/{session_id}", tags=["extract"])
def extract_data(session_id: str):
    """[骨架] 触发数据提取 + AI 质量检查

    下一轮实现：调用 SkillCaller('extract-and-check-data') 或
    ('extract-air-compressor-data-llm')，结果写回 session_store。
    """
    raise HTTPException(status_code=501, detail="extract 端点尚未实现（P1 第二轮）")


@router.get("/extract/{session_id}/stream", tags=["extract"])
def extract_stream(session_id: str):
    """[骨架] SSE 推送 AI 流式日志"""
    raise HTTPException(status_code=501, detail="SSE 流端点尚未实现（P1 第二轮）")


@router.post("/calculate/{session_id}", tags=["calculate"])
def calculate(session_id: str):
    """[骨架] 触发回填 + 公式计算"""
    raise HTTPException(status_code=501, detail="calculate 端点尚未实现（P1 第三轮）")


@router.get("/result/{session_id}", tags=["calculate"])
def get_result(session_id: str):
    """[骨架] 返回最终结果 JSON"""
    raise HTTPException(status_code=501, detail="result 端点尚未实现（P1 第三轮）")
