"""API 路由：P1 骨架 + /upload + /extract 完整跑通

完整端点（已实现）：
  GET  /api/health                   健康检查
  POST /api/upload                   上传调研表，创建 session
  GET  /api/session/{session_id}     查询 session 元数据
  GET  /api/sessions                 列出全部 session
  POST /api/extract/{session_id}     触发数据提取 + AI 质量检查
  GET  /api/extract/{session_id}/stream   AI 日志 SSE 流

骨架端点（返回 501，下一轮实现）：
  POST /api/calculate/{session_id}   触发公式计算
  GET  /api/result/{session_id}      返回最终结果 JSON
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .deps import PROJECT_ROOT, get_current_user, session_store
from .services import (
    ensure_ai_queue,
    get_ai_queue,
    is_extract_running,
    is_calculate_running,
    start_extract,
    start_calculate,
)


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
    """触发数据提取 + AI 质量检查

    启动后台线程调用 SkillCaller（extract-and-check-data 或
    extract-air-compressor-data-llm），通过 /extract/{id}/stream 接收 SSE 日志。
    本端点立即返回任务启动状态，不阻塞等待提取完成。
    """
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    if is_extract_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session {session_id!r} 的提取任务已在运行",
        )

    session_dir: Path = s["session_dir"]
    original_filename = s["original_filename"]
    input_path = session_dir / original_filename
    if not input_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"输入文件缺失: {input_path.name}",
        )

    # 主线程事件循环（线程内 put_nowait 需要用）
    try:
        main_loop = asyncio.get_running_loop()
    except RuntimeError:
        main_loop = asyncio.get_event_loop()

    try:
        output_json_path = start_extract(
            session_id=session_id,
            module_type=s["module_type"],
            input_path=input_path,
            original_filename=original_filename,
            main_loop=main_loop,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动提取任务失败: {type(e).__name__}: {e}",
        )

    return {
        "session_id": session_id,
        "status": "extracting",
        "module_type": s["module_type"],
        "input_file": input_path.name,
        "output_json": str(output_json_path),
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.get("/extract/{session_id}/stream", tags=["extract"])
async def extract_stream(session_id: str):
    """SSE 推送 AI 流式日志

    事件格式：
      data: {"type": "log",   "timestamp": "HH:MM:SS", "message": "..."}
      data: {"type": "done",  "timestamp": "HH:MM:SS"}
      data: {"type": "error", "timestamp": "HH:MM:SS", "message": "..."}
    """
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    queue = ensure_ai_queue(session_id)

    async def event_generator():
        # 先回放历史日志（供晚连接的客户端看到进度）
        for log in list(s.get("ai_logs", [])):
            yield {
                "event": "message",
                "data": json.dumps({"type": "log", **log}, ensure_ascii=False),
            }

        # 如果任务已经结束且队列空了，直接发 done
        if not is_extract_running(session_id):
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "done", "timestamp": datetime.now().strftime("%H:%M:%S")},
                    ensure_ascii=False,
                ),
            }
            return

        # 实时推送新事件直到 done/error
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # 心跳保活
                yield {"event": "ping", "data": ""}
                continue

            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }
            if event.get("type") in ("done", "error"):
                return

    return EventSourceResponse(event_generator())


@router.post("/calculate/{session_id}", tags=["calculate"])
def calculate(session_id: str, body: dict = None):
    """触发回填 + Excel 公式计算

    body（可选）：
      {"extracted_data": {...}, "filling_suggestions": {...}}

    如果未传 extracted_data，将读取 session 中 extract 阶段缓存的数据。
    filling_suggestions 未传则使用空建议（等价于“数据完整，无需填充”）。
    """
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    if is_calculate_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session {session_id!r} 的计算任务已在运行",
        )

    # 解析 extracted_data：优先用请求体，其次从 session_store 拿
    extracted_data = (body or {}).get("extracted_data") or s.get("extracted_data")
    if not extracted_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少 extracted_data：请先调用 /extract 或在请求体中提供",
        )

    filling_suggestions = (body or {}).get("filling_suggestions")

    try:
        main_loop = asyncio.get_running_loop()
    except RuntimeError:
        main_loop = asyncio.get_event_loop()

    try:
        start_calculate(
            session_id=session_id,
            module_type=s["module_type"],
            extracted_data=extracted_data,
            filling_suggestions=filling_suggestions,
            main_loop=main_loop,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动计算任务失败: {type(e).__name__}: {e}",
        )

    return {
        "session_id": session_id,
        "status": "calculating",
        "module_type": s["module_type"],
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.get("/result/{session_id}", tags=["calculate"])
def get_result(session_id: str):
    """返回最终结果 JSON

    返回结构：
    {
      "session_id": "...",
      "stage": "result",
      "result": {...},             # ExcelCalculator 的原始结果
      "formatted_result": {...},   # 格式化后的报告
      "filling_suggestions": {...}
    }
    """
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    if is_calculate_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="计算任务仍在运行，请稍后再查询",
        )

    if s.get("result") is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="计算结果不存在：请先调用 /calculate",
        )

    return {
        "session_id": session_id,
        "stage": s.get("stage"),
        "module_type": s.get("module_type"),
        "result": s.get("result"),
        "formatted_result": s.get("formatted_result"),
        "filling_suggestions": s.get("filling_suggestions"),
    }
