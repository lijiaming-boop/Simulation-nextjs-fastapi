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
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .deps import PROJECT_ROOT, get_current_user, session_store
from .agent_service import is_agent_running, start_agent_run
from .services import (
    ensure_ai_queue,
    get_ai_queue,
    is_extract_running,
    is_calculate_running,
    is_suggest_running,
    is_sim_running,
    is_quote_extract_running,
    is_quote_generate_running,
    is_quote_calculate_running,
    start_extract,
    start_calculate,
    start_suggest,
    start_sim_topology_extract,
    start_sim_topology_parse,
    start_sim_cop_parse,
    start_sim_operating_generate,
    start_sim_execute,
    save_sim_baseline,
    save_sim_schemes,
    _generate_default_cop_table,
    start_quote_extract,
    start_quote_generate,
    start_quote_calculate,
)


router = APIRouter()


# ==================== 公共工具 ====================


def _recover_multipart_filename(raw: str) -> str:
    """恢复 python-multipart 误按 Latin-1 解码的中文文件名。

    python-multipart 把 multipart header 的 filename 字节流按 Latin-1 解码，
    导致 UTF-8 或 GBK 编码的中文变成乱码码位（每个码位 <= 0xFF）。
    逐个尝试 UTF-8（现代浏览器/RFC 5987）、GBK/GB18030（Windows curl），
    取第一个成功且包含非 ASCII 字符的结果。全部失败则返回原值。
    """
    if raw is None:
        return raw
    if any(ord(c) > 0xFF for c in raw):
        return raw
    try:
        raw_bytes = raw.encode('latin-1')
    except UnicodeEncodeError:
        return raw
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            decoded = raw_bytes.decode(enc)
            if any(ord(c) > 0x7F for c in decoded):
                return decoded
        except UnicodeDecodeError:
            continue
    return raw


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
    ai_logs: list = Field(default_factory=list, description="AI 日志明细（调试用）")
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

    # 4. 流式保存文件到会话目录（修复 python-multipart 的 Latin-1 编码问题）
    #    python-multipart 0.0.19+ 会把 multipart header 中的 filename 字节
    #    按 Latin-1 解码为 Python 字符串。实际字节可能是 GBK（Windows curl）
    #    或 UTF-8（现代浏览器/RFC 5987）。我们逐个尝试恢复原始字符串。
    filename = _recover_multipart_filename(file.filename)
    saved_path = session_dir / filename
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
        original_filename=filename,
        user_id=user.get("sub") or user.get("id"),
        module_type=module_type,
    )

    return UploadResponse(
        session_id=session_id,
        module_type=module_type,
        original_filename=filename,
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
        ai_logs=s["ai_logs"],
    )


@router.get("/session/{session_id}/extracted", tags=["session"])
def get_extracted(session_id: str):
    """返回提取后的结构化数据（extract 阶段产出）"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    ed = s.get("extracted_data")
    if ed is None:
        raise HTTPException(status_code=404, detail="extracted_data 尚未生成，请先调用 /extract")
    return ed


# ==================== /llm（直连 Messages API） ====================


class ChatRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    max_tokens: int = Field(default=1024, ge=1, le=8192)


@router.post("/llm/chat", tags=["llm"])
def llm_chat(body: ChatRequest):
    """直连 Anthropic Messages API（绕过 claude-agent-sdk）

    用于验证 LLM 代理可用，或在需要纯对话能力时使用。
    """
    from core.skill_caller import SkillCaller, SkillError

    try:
        caller = SkillCaller(project_root=PROJECT_ROOT)
    except SkillError as e:
        raise HTTPException(status_code=500, detail=f"SkillCaller 初始化失败: {e}")

    try:
        text = caller.create_message(
            body.prompt, system=body.system, max_tokens=body.max_tokens
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {type(e).__name__}: {e}")

    return {
        "model": caller.api_key and "(configured)",
        "prompt_len": len(body.prompt),
        "response": text,
    }


# ==================== 骨架端点（501） ====================


@router.post("/extract/{session_id}", tags=["extract"])
async def extract_data(session_id: str):
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

    # async 端点能直接拿到主事件循环
    main_loop = asyncio.get_running_loop()

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

    # 判断是否有任务在运行（extract / suggest / calculate 任一）
    any_running = (
        is_extract_running(session_id)
        or is_calculate_running(session_id)
        or is_suggest_running(session_id)
        or is_quote_extract_running(session_id)
        or is_quote_generate_running(session_id)
    )

    async def event_generator():
        if not any_running:
            # 排空队列中残留的事件（线程已完成但事件尚未消费）
            while True:
                try:
                    event = queue.get_nowait()
                    yield {
                        "event": "message",
                        "data": json.dumps(event, ensure_ascii=False),
                    }
                    if event.get("type") in ("done", "complete", "error"):
                        return
                except asyncio.QueueEmpty:
                    break
            # 队列已空但没有终止事件，补发一个
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "complete", "timestamp": datetime.now().strftime("%H:%M:%S"), "message": "任务已完成"},
                    ensure_ascii=False,
                ),
            }
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}
                continue

            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }
            if event.get("type") in ("done", "complete", "error"):
                return

    return EventSourceResponse(event_generator())


@router.post("/calculate/{session_id}", tags=["calculate"])
async def calculate(session_id: str, body: dict = None):
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

    # 拦截不支持的站房类型
    station_type = (extracted_data.get("station_type") or "").lower()
    if station_type == "unsupported":
        reason = extracted_data.get("station_type_reason", "该站房类型不在自动评估范围内")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的站房类型：{reason}",
        )

    filling_suggestions = (body or {}).get("filling_suggestions")
    main_loop = asyncio.get_running_loop()

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
      "stage": "result" | "error",
      "result": {...},             # ExcelCalculator 的原始结果
      "formatted_result": {...},   # 格式化后的报告
      "filling_suggestions": {...},
      "error": "..."               # 仅 stage=error 时存在
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

    # 计算失败：返回错误详情（200，让前端能读到错误信息）
    if s.get("stage") == "error":
        return {
            "session_id": session_id,
            "stage": "error",
            "module_type": s.get("module_type"),
            "error": s.get("calc_error", "计算过程发生未知错误"),
            "result": None,
            "formatted_result": None,
            "filling_suggestions": None,
        }

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


# 允许下载的结果文件白名单
_RESULT_DOWNLOAD_WHITELIST = {
    "simplified_result.xlsx",       # 空调简化版
    "calculation_result.xlsx",      # 空调完整版（需密码）
    "air_compressor_quotation.xlsx",  # 空压机报价单
    "air_compressor_scheme.docx",   # 空压机方案文档
    "ac_quotation.xlsx",            # 空调报价单
    "ac_scheme.docx",               # 空调方案文档
}
# 完整计算表格需管理员密码（可用环境变量覆盖）
_ADMIN_DOWNLOAD_PASSWORD = os.getenv("ADMIN_DOWNLOAD_PASSWORD", "admin123")


@router.get("/download/{session_id}/{filename}", tags=["calculate"])
def download_result(
    session_id: str,
    filename: str,
    password: Optional[str] = Query(default=None),
):
    """下载计算结果 Excel 文件

    - simplified_result.xlsx：简化版，直接下载
    - calculation_result.xlsx：完整版，需 password 校验
    """
    from fastapi.responses import FileResponse

    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if filename not in _RESULT_DOWNLOAD_WHITELIST:
        raise HTTPException(status_code=404, detail=f"不允许下载的文件: {filename}")
    if filename == "calculation_result.xlsx" and password != _ADMIN_DOWNLOAD_PASSWORD:
        raise HTTPException(status_code=403, detail="密码错误或缺失")
    fpath = s["session_dir"] / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    return FileResponse(str(fpath), filename=filename)


# ==================== /suggest（规则 + LLM 增强填充建议） ====================


class SuggestRequest(BaseModel):
    use_llm: bool = Field(
        default=True,
        description="是否用 LLM 对规则建议做智能增强",
    )


@router.post("/suggest/{session_id}", tags=["suggest"])
async def suggest(session_id: str, body: SuggestRequest = SuggestRequest()):
    """生成数据填充建议

    流程：
      1. subprocess 调规则脚本（suggest_data_filling.py）
      2. use_llm=True 时，用 DirectLLMClient 对规则建议做智能增强
    """
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    if is_suggest_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session {session_id!r} 的建议任务已在运行",
        )

    if s.get("extracted_data") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="extracted_data 缺失：请先调用 /extract",
        )

    main_loop = asyncio.get_running_loop()
    try:
        start_suggest(
            session_id=session_id,
            module_type=s["module_type"],
            use_llm=body.use_llm,
            main_loop=main_loop,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动建议任务失败: {type(e).__name__}: {e}",
        )

    return {
        "session_id": session_id,
        "status": "suggesting",
        "use_llm": body.use_llm,
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.get("/suggest/{session_id}", tags=["suggest"])
def get_suggest(session_id: str):
    """返回已生成的填充建议"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_suggest_running(session_id):
        raise HTTPException(status_code=409, detail="建议任务仍在运行")
    fs = s.get("filling_suggestions")
    if fs is None:
        raise HTTPException(status_code=404, detail="filling_suggestions 尚未生成，请先调用 POST /suggest")
    return fs


# ==================== /sim（仿真模块） ====================


class SimInitRequest(BaseModel):
    sim_mode: str = Field(default="new_station", description="new_station | old_station")
    source_session_id: Optional[str] = Field(default=None, description="关联的空调 session，自动复制调研表")


class SimTopologyParseRequest(BaseModel):
    text: str = Field(..., description="拓扑文本描述")
    project_name: str = Field(default="", description="项目名称")


class SimOperatingRequest(BaseModel):
    text: str = Field(..., description="运行工况文本描述")


@router.post("/sim/init", tags=["simulation"])
async def sim_init(body: SimInitRequest, user: dict = Depends(get_current_user)):
    """创建仿真专用 session（无需上传调研表）

    如果传入 source_session_id，自动从空调 session 复制调研表并触发拓扑识别。
    """
    session_id = session_store.init_sim_session(
        user_id=user.get("sub") or user.get("id"),
        sim_mode=body.sim_mode,
    )

    # 如果有关联的空调 session，自动复制调研表并触发拓扑提取
    if body.source_session_id:
        src = session_store.get(body.source_session_id)
        if src:
            src_dir: Path = src["session_dir"]
            dst_dir: Path = session_store.get(session_id)["session_dir"]
            # 查找源 session 中的调研表文件
            survey_candidates = list(src_dir.glob("*.xlsx")) + list(src_dir.glob("*.xls"))
            if survey_candidates:
                import shutil
                src_file = survey_candidates[0]
                dst_file = dst_dir / "upload_survey.xlsx"
                shutil.copy2(str(src_file), str(dst_file))
                # 自动触发拓扑提取
                main_loop = asyncio.get_running_loop()
                start_sim_topology_extract(session_id, dst_file, main_loop)
                return {
                    "session_id": session_id,
                    "sim_mode": body.sim_mode,
                    "sim_stage": "topology",
                    "status": "extracting_topology",
                    "stream_url": f"/api/extract/{session_id}/stream",
                }

    return {
        "session_id": session_id,
        "sim_mode": body.sim_mode,
        "sim_stage": "topology",
    }


@router.get("/sim/state/{session_id}", tags=["simulation"])
def sim_state(session_id: str):
    """获取仿真模块全部状态"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    return {
        "session_id": session_id,
        "sim_stage": s.get("sim_stage", "topology"),
        "sim_mode": s.get("sim_mode", "new_station"),
        "sim_topology": s.get("sim_topology"),
        "sim_cop_data": s.get("sim_cop_data", {}),
        "sim_operating_conditions": s.get("sim_operating_conditions"),
        "sim_result": s.get("sim_result"),
        "sim_project_name": s.get("sim_project_name", ""),
        "sim_baseline_power_kwh": s.get("sim_baseline_power_kwh"),
        "sim_schemes": s.get("sim_schemes"),
        "is_running": is_sim_running(session_id),
    }


@router.put("/sim/stage/{session_id}", tags=["simulation"])
def sim_set_stage(session_id: str, stage: str):
    """手动推进仿真阶段（如 COP确认 → operating, 工况确认 → simulate）"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    valid_stages = {"topology", "cop_curves", "operating", "simulate", "done"}
    if stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"无效阶段: {stage}")
    s["sim_stage"] = stage
    return {"status": "ok", "sim_stage": stage}


@router.post("/sim/topology/extract/{session_id}", tags=["simulation"])
async def sim_topology_extract(session_id: str, file: UploadFile = File(...)):
    """从调研表 Excel 提取拓扑"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_sim_running(session_id):
        raise HTTPException(status_code=409, detail="仿真任务仍在运行")

    # 保存上传的调研表
    session_dir = s["session_dir"]
    upload_path = session_dir / "upload_survey.xlsx"
    content = file.file.read()
    with open(upload_path, "wb") as f:
        f.write(content)

    main_loop = asyncio.get_running_loop()
    start_sim_topology_extract(session_id, upload_path, main_loop)

    return {
        "session_id": session_id,
        "status": "extracting_topology",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.post("/sim/topology/parse/{session_id}", tags=["simulation"])
async def sim_topology_parse(session_id: str, body: SimTopologyParseRequest):
    """文本解析拓扑"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_sim_running(session_id):
        raise HTTPException(status_code=409, detail="仿真任务仍在运行")

    main_loop = asyncio.get_running_loop()
    start_sim_topology_parse(session_id, body.text, body.project_name, main_loop)

    return {
        "session_id": session_id,
        "status": "parsing_topology",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.put("/sim/topology/{session_id}", tags=["simulation"])
def sim_save_topology(session_id: str, body: dict):
    """保存编辑后的拓扑数据"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    s["sim_topology"] = body
    if body.get("project_name"):
        s["sim_project_name"] = body["project_name"]
    return {"status": "ok", "sim_topology": body}


@router.post("/sim/cop/parse/{session_id}/{idx}", tags=["simulation"])
async def sim_cop_parse(
    session_id: str,
    idx: int,
    model_name: str = Query(...),
    rated_cop: float = Query(...),
    file: UploadFile = File(...),
):
    """图片识别 COP 曲线"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_sim_running(session_id):
        raise HTTPException(status_code=409, detail="仿真任务仍在运行")

    session_dir = s["session_dir"]
    img_path = session_dir / f"cop_curve_{idx}_{file.filename}"
    content = file.file.read()
    with open(img_path, "wb") as f:
        f.write(content)

    main_loop = asyncio.get_running_loop()
    start_sim_cop_parse(session_id, img_path, idx, model_name, rated_cop, main_loop)

    return {
        "session_id": session_id,
        "status": "parsing_cop",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.post("/sim/cop/default/{session_id}/{idx}", tags=["simulation"])
def sim_cop_default(session_id: str, idx: int, model_name: str = Query(...), rated_cop: float = Query(...)):
    """使用默认 COP 曲线（跳过图片识别）"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    default_cop = _generate_default_cop_table(rated_cop)
    default_cop["_source"] = "skip_default"
    s["sim_cop_data"][model_name] = default_cop

    return {
        "status": "ok",
        "model_name": model_name,
        "cop_data": default_cop,
    }


@router.post("/sim/operating/generate/{session_id}", tags=["simulation"])
async def sim_operating_generate(session_id: str, body: SimOperatingRequest):
    """生成工况需求"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_sim_running(session_id):
        raise HTTPException(status_code=409, detail="仿真任务仍在运行")

    main_loop = asyncio.get_running_loop()
    start_sim_operating_generate(session_id, body.text, main_loop)

    return {
        "session_id": session_id,
        "status": "generating_operating",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.put("/sim/operating/{session_id}", tags=["simulation"])
def sim_save_operating(session_id: str, body: dict):
    """保存编辑后的工况数据"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    s["sim_operating_conditions"] = body
    return {"status": "ok"}


class BaselineBody(BaseModel):
    baseline_power_kwh: float = Field(..., gt=0, description="基准工况年总耗电量，单位 kWh")


@router.put("/sim/baseline/{session_id}", tags=["simulation"])
def sim_save_baseline(session_id: str, body: BaselineBody):
    """保存基准工况年耗电量（仅 old_station 模式）"""
    try:
        save_sim_baseline(session_id, body.baseline_power_kwh)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "baseline_power_kwh": body.baseline_power_kwh}


class SchemeItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=4, description="字母标识 A/B/C...")
    name: str = Field(..., min_length=1, max_length=100, description="方案中文名称")
    description: str = Field("", description="改造措施描述")
    target_saving_rate_pct: float = Field(..., gt=0, lt=100, description="期望节能率（%）")
    intervention_tags: list[str] = Field(default_factory=list)


class SchemesBody(BaseModel):
    schemes: list[SchemeItem]


@router.put("/sim/schemes/{session_id}", tags=["simulation"])
def sim_save_schemes(session_id: str, body: SchemesBody):
    """保存优化方案列表（仅 old_station 模式）"""
    try:
        save_sim_schemes(session_id, [s.model_dump() for s in body.schemes])
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "count": len(body.schemes)}


@router.post("/sim/execute/{session_id}", tags=["simulation"])
async def sim_execute(session_id: str):
    """执行仿真"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_sim_running(session_id):
        raise HTTPException(status_code=409, detail="仿真任务仍在运行")

    if not all([s.get("sim_topology"), s.get("sim_cop_data"), s.get("sim_operating_conditions")]):
        raise HTTPException(status_code=400, detail="前置数据不完整")

    # old_station 多方案模式：严格要求 baseline + schemes
    if s.get("sim_mode") == "old_station":
        baseline = s.get("sim_baseline_power_kwh")
        schemes = s.get("sim_schemes") or []
        if not baseline or baseline <= 0:
            raise HTTPException(status_code=400, detail="old_station 模式必须先设置基准工况耗电量")
        if not schemes:
            raise HTTPException(status_code=400, detail="old_station 模式必须先定义至少一个优化方案")

    main_loop = asyncio.get_running_loop()
    start_sim_execute(session_id, main_loop)

    return {
        "session_id": session_id,
        "status": "simulating",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.get("/sim/result/{session_id}", tags=["simulation"])
def sim_result(session_id: str):
    """获取仿真结果"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_sim_running(session_id):
        raise HTTPException(status_code=409, detail="仿真仍在运行")
    result = s.get("sim_result")
    if not result:
        raise HTTPException(status_code=404, detail="仿真结果不存在")
    return result


@router.get("/sim/download/{session_id}/{filename}", tags=["simulation"])
def sim_download(session_id: str, filename: str):
    """下载仿真结果文件"""
    from fastapi.responses import FileResponse
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    output_dir = s["session_dir"] / "sim_output"
    fpath = output_dir / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    return FileResponse(str(fpath), filename=filename)


# ==================== 报价模块端点 ====================


class QuoteAuditRequest(BaseModel):
    item_key: str = Field(..., description="项目键，如 sw_3, hw_12, ct_0")
    action: str = Field(..., description="操作类型: approve | reject | nstd | select_candidate | update_price")
    candidate_index: Optional[int] = Field(default=None, description="候选项索引（select_candidate 时使用）")
    standard_price: Optional[float] = Field(default=None, description="标准价格（update_price 时使用）")
    channel_price: Optional[float] = Field(default=None, description="渠道价格（update_price 时使用）")


@router.post("/quote/upload", tags=["quote"])
async def quote_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """上传报价调研表"""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="文件缺少文件名")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail=f"仅支持 .xlsx / .xls，收到 {suffix!r}")

    session_id = session_store.init_quote_session(
        user_id=user.get("sub") or user.get("id"),
    )

    s = session_store.get(session_id)
    session_dir = s["session_dir"]

    filename = _recover_multipart_filename(file.filename)
    saved_path = session_dir / filename

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    with open(saved_path, "wb") as f:
        f.write(content)

    s["original_filename"] = filename
    s["quote_survey_path"] = str(saved_path)
    session_store.update_stage(session_id, "uploaded")

    return {
        "session_id": session_id,
        "module_type": "quote",
        "original_filename": filename,
        "saved_path": str(saved_path),
        "session_dir": str(session_dir),
        "created_at": datetime.now().isoformat(),
    }


@router.post("/quote/precheck/{session_id}", tags=["quote"])
async def quote_precheck(session_id: str):
    """AI 快速预检调研表质量问题"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session 不存在")
    if s.get("module_type") != "quote":
        raise HTTPException(status_code=400, detail="非报价类型 session")
    survey_path = s.get("quote_survey_path")
    if not survey_path:
        raise HTTPException(status_code=400, detail="未上传调研表")

    from quote_module.ai_client import read_survey_with_ai
    try:
        preview_result = await asyncio.to_thread(
            read_survey_with_ai,
            str(survey_path), None, True,
        )
        detected_issues = preview_result.get("detected_issues", [])
        summary = preview_result.get("summary", "")
    except Exception as e:
        detected_issues = []
        summary = f"预检跳过: {e}"

    s["quote_precheck_issues"] = detected_issues
    s["quote_precheck_summary"] = summary

    return {
        "session_id": session_id,
        "detected_issues": detected_issues,
        "summary": summary,
    }


@router.post("/quote/extract/{session_id}", tags=["quote"])
async def quote_extract_start(session_id: str, user: dict = Depends(get_current_user)):
    """触发报价调研表 AI 解析"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if s.get("module_type") != "quote":
        raise HTTPException(status_code=400, detail="非报价类型 session")
    if is_quote_extract_running(session_id):
        raise HTTPException(status_code=409, detail="提取任务仍在运行")
    if not s.get("quote_survey_path"):
        raise HTTPException(status_code=400, detail="未上传调研表")

    main_loop = asyncio.get_running_loop()
    start_quote_extract(session_id, main_loop)

    return {
        "session_id": session_id,
        "status": "extracting",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.get("/quote/extract/{session_id}", tags=["quote"])
def quote_extract_result(session_id: str):
    """获取报价调研表解析结果"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_quote_extract_running(session_id):
        raise HTTPException(status_code=409, detail="提取任务仍在运行")

    project_data = s.get("quote_project_data")
    if not project_data:
        raise HTTPException(status_code=404, detail="解析结果不存在")

    return {
        "session_id": session_id,
        "stage": s.get("stage"),
        "parse_mode": s.get("quote_parse_mode"),
        "project_data": project_data,
        "data_warnings": project_data.get("data_warnings", []),
    }


@router.post("/quote/calculate/{session_id}", tags=["quote"])
async def quote_calculate_start(session_id: str):
    """触发报价计算（异步，通过 SSE 推送进度日志）"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if s.get("module_type") != "quote":
        raise HTTPException(status_code=400, detail="非报价类型 session")
    if is_quote_calculate_running(session_id):
        raise HTTPException(status_code=409, detail="计算任务仍在运行")
    if not s.get("quote_project_data"):
        raise HTTPException(status_code=400, detail="缺少项目数据，请先完成提取")

    main_loop = asyncio.get_running_loop()
    start_quote_calculate(session_id, main_loop)

    return {
        "session_id": session_id,
        "status": "calculating",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.get("/quote/calculate/{session_id}", tags=["quote"])
def quote_calculate_result(session_id: str):
    """获取报价计算结果（含审核台数据）"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_quote_calculate_running(session_id):
        raise HTTPException(status_code=409, detail="计算任务仍在运行")

    bottom_sheet = s.get("quote_bottom_sheet")
    if not bottom_sheet:
        raise HTTPException(status_code=404, detail="计算结果不存在")

    return {
        "session_id": session_id,
        "stage": s.get("stage"),
        "bottom_sheet": bottom_sheet,
        "section9_result": s.get("quote_section9_result"),
        "edited_items": s.get("quote_edited_items", {}),
    }


@router.put("/quote/audit/{session_id}", tags=["quote"])
def quote_audit(session_id: str, body: QuoteAuditRequest):
    """审核操作：批准/驳回/非标/选择候选/更新价格"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    bottom_sheet = s.get("quote_bottom_sheet")
    if not bottom_sheet:
        raise HTTPException(status_code=400, detail="缺少计算结果")

    item_key = body.item_key
    action = body.action

    prefix, idx_str = item_key.rsplit("_", 1)
    idx = int(idx_str)

    zone_map = {"sw": "software_items", "hw": "hardware_items", "ct": "construction_items"}
    zone_name = zone_map.get(prefix)
    if not zone_name:
        raise HTTPException(status_code=400, detail=f"未知的项目前缀: {prefix}")

    items = bottom_sheet.get(zone_name, [])
    if idx >= len(items):
        raise HTTPException(status_code=404, detail=f"项目索引越界: {item_key}")

    item = items[idx]

    if action == "approve":
        item["status"] = "AUTO"
    elif action == "reject":
        item["status"] = "BLOCKED"
    elif action in ("nstd", "mark_nonstandard"):
        item["status"] = "NONSTANDARD"
    elif action == "select_candidate":
        if body.candidate_index is None:
            raise HTTPException(status_code=400, detail="缺少 candidate_index")
        candidates = item.get("candidates", [])
        if body.candidate_index >= len(candidates):
            raise HTTPException(status_code=400, detail="候选项索引越界")
        c = candidates[body.candidate_index]
        item["brand"] = c.get("brand", item.get("brand"))
        item["model"] = c.get("model", item.get("model"))
        item["standard_price"] = c.get("standard_price", item.get("standard_price"))
        item["channel_price"] = c.get("channel_price", item.get("channel_price"))
        item["status"] = "AUTO"
    elif action == "update_price":
        if body.standard_price is not None:
            item["standard_price"] = body.standard_price
        if body.channel_price is not None:
            item["channel_price"] = body.channel_price
        item["status"] = "AUTO"
    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")

    s["quote_edited_items"][item_key] = item["status"]

    status_summary = {"AUTO": 0, "CONFIRM": 0, "INQUIRY": 0, "NONSTANDARD": 0, "BLOCKED": 0}
    for z in ["software_items", "hardware_items", "construction_items"]:
        for it in bottom_sheet.get(z, []):
            st = it.get("status", "AUTO")
            if st in status_summary:
                status_summary[st] += 1
    bottom_sheet["status_summary"] = status_summary

    bottom_path = s["session_dir"] / f"bottom_sheet_{session_id}.json"
    with open(bottom_path, "w", encoding="utf-8") as f:
        json.dump(bottom_sheet, f, ensure_ascii=False, indent=2)

    return {
        "session_id": session_id,
        "item_key": item_key,
        "new_status": item["status"],
        "status_summary": status_summary,
        "updated_fields": {
            "brand": item.get("brand"),
            "model": item.get("model"),
            "standard_price": item.get("standard_price"),
            "channel_price": item.get("channel_price"),
        },
    }


@router.post("/quote/generate/{session_id}", tags=["quote"])
async def quote_generate_start(session_id: str):
    """生成报价表 + 方案文档"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_quote_generate_running(session_id):
        raise HTTPException(status_code=409, detail="生成任务仍在运行")
    if not s.get("quote_bottom_sheet"):
        raise HTTPException(status_code=400, detail="缺少计算结果，请先完成计算")

    main_loop = asyncio.get_running_loop()
    start_quote_generate(session_id, main_loop)

    return {
        "session_id": session_id,
        "status": "generating",
        "stream_url": f"/api/extract/{session_id}/stream",
    }


@router.get("/quote/generate/{session_id}", tags=["quote"])
def quote_generate_result(session_id: str):
    """获取生成结果"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if is_quote_generate_running(session_id):
        raise HTTPException(status_code=409, detail="生成任务仍在运行")

    generated_files = s.get("quote_generated_files", [])
    if not generated_files:
        error = s.get("quote_error")
        if error:
            raise HTTPException(status_code=500, detail=f"生成失败: {error}")
        raise HTTPException(status_code=404, detail="生成结果不存在")

    file_names = [Path(f).name for f in generated_files]
    return {
        "session_id": session_id,
        "stage": s.get("stage"),
        "files": file_names,
    }


@router.get("/quote/download/{session_id}/{filename}", tags=["quote"])
def quote_download(session_id: str, filename: str):
    """下载报价生成文件"""
    from fastapi.responses import FileResponse
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    output_dir = s["session_dir"] / f"generated_{session_id}"
    fpath = output_dir / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    return FileResponse(str(fpath), filename=filename)



# ==================== Agent 模式端点 ====================


class AgentRunResponse(BaseModel):
    session_id: str
    status: str
    mode: str
    stream_url: str
    trace_url: str


@router.post("/agent/run/{session_id}", response_model=AgentRunResponse, tags=["agent"])
async def agent_run(
    session_id: str,
    mode: str = Query(default="auto", description="决策模式：auto（有 Key 用 LLM）| deterministic（零成本规则策略）"),
):
    """以 Agent 模式执行完整测算主线（提取→质检→填充→计算→结论）

    与分阶段端点（/extract → /suggest → /calculate）不同，本端点由
    AgentOrchestrator 自主编排：每一步由决策核心在硬约束白名单内选择工具，
    过程通过 /agent/{session_id}/stream 的 SSE 实时推送，完整轨迹
    （含每步工具、参数、观察、token 用量）落盘 agent_trace.json。
    """
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    if s["module_type"] != "air_conditioner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent 模式当前支持 air_conditioner 模块",
        )
    if mode not in ("auto", "deterministic"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"mode 只能是 auto 或 deterministic，收到 {mode!r}",
        )
    if is_agent_running(session_id):
        raise HTTPException(status_code=409, detail=f"session {session_id!r} 的 agent 任务已在运行")

    main_loop = asyncio.get_running_loop()
    try:
        trace_path = start_agent_run(session_id, mode=None if mode == "auto" else mode,
                                     main_loop=main_loop)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动 agent 失败: {type(e).__name__}: {e}")

    effective_mode = "deterministic" if mode == "deterministic" else "auto"
    return AgentRunResponse(
        session_id=session_id,
        status="running",
        mode=effective_mode,
        stream_url=f"/api/agent/{session_id}/stream",
        trace_url=f"/api/agent/{session_id}/trace",
    )


@router.get("/agent/{session_id}/stream", tags=["agent"])
async def agent_stream(session_id: str):
    """SSE 推送 agent 轨迹事件

    事件类型：run_start / thinking / tool_start / tool_end / final / error / done
    """
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")

    queue = ensure_ai_queue(session_id)
    running = is_agent_running(session_id)

    async def event_generator():
        if not running:
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "complete", "message": "agent 任务未在运行，请查看 /agent/{id}/trace"},
                    ensure_ascii=False,
                ),
            }
            return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}
                continue
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }
            if event.get("type") in ("done", "error"):
                return

    return EventSourceResponse(event_generator())


@router.get("/agent/{session_id}/trace", tags=["agent"])
async def agent_trace(session_id: str):
    """返回本次运行的完整 agent 轨迹（可观测性端点）"""
    s = session_store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} 不存在")
    trace_path = s["session_dir"] / "agent_trace.json"
    if not trace_path.exists():
        raise HTTPException(status_code=404, detail="轨迹文件不存在（agent 尚未运行或未产生轨迹）")
    with open(trace_path, "r", encoding="utf-8") as f:
        return json.load(f)
