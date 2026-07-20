"""业务服务层：封装 core 模块，供 FastAPI 路由调用"""
import asyncio
import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.skill_caller import SkillCaller, SkillError
from core.data_filler import DataFiller
from core.excel_calculator import ExcelCalculator
from config import WeatherService

from .deps import PROJECT_ROOT, session_store


# ==================== 任务注册表（后台线程） ====================

# session_id → 后台 thread 对象
_extract_tasks: dict = {}
# session_id → calculate 后台 thread
_calculate_tasks: dict = {}
# session_id → suggest 后台 thread
_suggest_tasks: dict = {}


def is_extract_running(session_id: str) -> bool:
    """查询提取任务是否仍在运行"""
    t = _extract_tasks.get(session_id)
    return t is not None and t.is_alive()


def is_calculate_running(session_id: str) -> bool:
    t = _calculate_tasks.get(session_id)
    return t is not None and t.is_alive()


def is_suggest_running(session_id: str) -> bool:
    t = _suggest_tasks.get(session_id)
    return t is not None and t.is_alive()


# ==================== AI 事件通道 ====================

def ensure_ai_queue(session_id: str) -> asyncio.Queue:
    """为 session 创建/复用 AI 事件 Queue"""
    s = session_store.get(session_id)
    if s is None:
        raise RuntimeError(f"session {session_id!r} 不存在")
    if "ai_queue" not in s:
        # 注意：必须在主线程事件循环中创建，才能被 SSE 端点消费
        s["ai_queue"] = asyncio.Queue()
    return s["ai_queue"]


def get_ai_queue(session_id: str) -> Optional[asyncio.Queue]:
    s = session_store.get(session_id)
    return s.get("ai_queue") if s else None


# ==================== 提取任务（在线程中执行） ====================

def _run_extract_in_thread(
    session_id: str,
    module_type: str,
    input_path: Path,
    output_json_path: Path,
    original_filename: str,
) -> None:
    """在线程中调用 SkillCaller 完成数据提取

    所有 AI 消息通过 asyncio.Queue 推送给 SSE 端点
    """
    # 拿到主线程事件循环（用于 put_nowait）
    loop = session_store._main_loop  # 由 extract() 端点注入

    def ai_callback(timestamp: str, message: str) -> None:
        """SkillCaller 回调：推事件到 AI Queue + 累积到 ai_logs"""
        session_store.append_ai_log(session_id, timestamp, message)
        event = {"type": "log", "timestamp": timestamp, "message": message}
        q = get_ai_queue(session_id)
        if q is not None:
            loop.call_soon_threadsafe(q.put_nowait, event)

    try:
        # === 空调场景：直接 subprocess 调脚本 ===
        # 绕过 Claude Agent SDK（SDK 的认证与自定义代理端点不兼容）
        # 脚本 extract_and_check_data.py 是纯 Python + openpyxl，无需 LLM
        if module_type == "air_conditioner":
            script = PROJECT_ROOT / ".claude" / "skills" / "extract-and-check-data" / "scripts" / "extract_and_check_data.py"
            cmd = [sys.executable, str(script), str(input_path), str(output_json_path), original_filename]

            ai_callback(datetime.now().strftime("%H:%M:%S"), "🚀 开始提取数据（subprocess 直调脚本）...")

            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # 流式读取 stdout，推送到 SSE
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line:
                    ai_callback(datetime.now().strftime("%H:%M:%S"), line)

            proc.wait()

            if proc.returncode != 0:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise SkillError(f"脚本退出码 {proc.returncode}: {stderr[:500]}")

            if not output_json_path.exists():
                raise SkillError(f"脚本执行完成但未生成输出: {output_json_path}")
        else:
            # === 空压场景：仍走 SkillCaller（暂保持现状） ===
            caller = SkillCaller(project_root=PROJECT_ROOT)
            skill_name = "extract-air-compressor-data-llm"
            args = (str(input_path), str(output_json_path), original_filename)

            start_ts = datetime.now().strftime("%H:%M:%S")
            ai_callback(start_ts, f"🚀 开始调用 {skill_name} ...")
            caller.call_skill(skill_name, *args, callback=ai_callback)

            if not output_json_path.exists():
                raise SkillError(f"Skill 执行完成，但未生成输出: {output_json_path}")

        # 读取输出 JSON
        with open(output_json_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        s = session_store.get(session_id)
        if s is not None:
            # 兼容两种 schema：带 extracted_data/quality_report 的拆分 或 整体
            if "extracted_data" in content and "quality_report" in content:
                s["extracted_data"] = content["extracted_data"]
                s["quality_report"] = content["quality_report"]
            elif "rawData" in content:  # 空压 LLM 版
                s["extracted_data"] = content.get("rawData")
                s["quality_report"] = content.get("quality_report") or content.get("rejectionCheck")
            else:
                # 兜底：整体作为 extracted_data
                s["extracted_data"] = content

        end_ts = datetime.now().strftime("%H:%M:%S")
        ai_callback(end_ts, f"✅ 提取完成，输出: {output_json_path.name}")
        session_store.update_stage(session_id, "extract_check")

        # 发 done 事件
        if (q := get_ai_queue(session_id)) is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "done", "timestamp": datetime.now().strftime("%H:%M:%S")},
            )

    except Exception as e:
        err_ts = datetime.now().strftime("%H:%M:%S")
        err_msg = f"❌ {type(e).__name__}: {e}"
        session_store.append_ai_log(session_id, err_ts, err_msg)
        if (q := get_ai_queue(session_id)) is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "error", "timestamp": err_ts, "message": err_msg},
            )
        session_store.update_stage(session_id, "error")


# ==================== 提取入口 ====================

def start_extract(
    session_id: str,
    module_type: str,
    input_path: Path,
    original_filename: str,
    main_loop: asyncio.AbstractEventLoop,
) -> Path:
    """启动后台提取任务，返回输出 JSON 路径"""
    if is_extract_running(session_id):
        raise RuntimeError(f"session {session_id!r} 已有提取任务在运行")

    # 输出 JSON 命名：沿用 Streamlit 惯例
    if module_type == "air_conditioner":
        output_json_path = session_store.get(session_id)["session_dir"] / "extracted_data.json"
    else:
        output_json_path = session_store.get(session_id)["session_dir"] / "extracted_air_compressor_text.json"

    # 注入主事件循环（线程内 put_nowait 需要用）
    session_store._main_loop = main_loop

    # 确保 AI Queue 存在
    ensure_ai_queue(session_id)

    session_store.update_stage(session_id, "extracting")

    t = threading.Thread(
        target=_run_extract_in_thread,
        args=(session_id, module_type, input_path, output_json_path, original_filename),
        daemon=True,
        name=f"extract-{session_id}",
    )
    t.start()
    _extract_tasks[session_id] = t

    return output_json_path


# ==================== 计算任务 ====================

def _run_calculate_in_thread(
    session_id: str,
    module_type: str,
    extracted_data: dict,
    filling_suggestions: Optional[dict],
) -> None:
    """后台执行 DataFiller + ExcelCalculator"""
    loop = session_store._main_loop

    def emit(event_type: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        session_store.append_ai_log(session_id, ts, message)
        q = get_ai_queue(session_id)
        if q is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": event_type, "timestamp": ts, "message": message},
            )

    try:
        s = session_store.get(session_id)
        if s is None:
            raise RuntimeError(f"session {session_id!r} 不存在")
        session_dir: Path = s["session_dir"]

        # 1. 写入提取数据文件
        emit("log", "📄 写入提取数据...")
        extracted_path = session_dir / "ac_extracted_data.json"
        with open(extracted_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)

        # 2. 写入填充建议（默认空建议）
        suggestions_path = session_dir / "ac_filling_suggestions.json"
        if filling_suggestions is None:
            filling_suggestions = {
                "can_proceed": True,
                "fillable_suggestions": [],
                "unfillable_fields": [],
            }
        with open(suggestions_path, "w", encoding="utf-8") as f:
            json.dump(filling_suggestions, f, ensure_ascii=False, indent=2)

        # 3. DataFiller 执行填充
        emit("log", "🔄 执行数据填充...")
        filler = DataFiller()
        filled_path = filler.fill_data(
            str(extracted_path),
            str(suggestions_path),
            str(session_dir / "ac_filled_data.json"),
        )
        emit("log", "✅ 填充完成")

        # 4. ExcelCalculator 执行公式计算
        emit("log", "⚙️ 运行 Excel 公式计算引擎...")
        weather = WeatherService()
        calculator = ExcelCalculator(weather_service=weather)
        result_path = calculator.calculate(
            filled_path,
            str(session_dir / "ac_result_data.json"),
        )
        emit("log", "✅ 计算完成")

        # 5. 格式化输出
        with open(filled_path, "r", encoding="utf-8") as f:
            filled_data = json.load(f)
        with open(result_path, "r", encoding="utf-8") as f:
            result = json.load(f)

        formatted = calculator.format_export_results(filled_data, result)
        formatted_path = session_dir / "ac_formatted_result.json"
        with open(formatted_path, "w", encoding="utf-8") as f:
            json.dump(formatted, f, ensure_ascii=False, indent=2)

        # 6. 写回 session_store
        s["filling_suggestions"] = filling_suggestions
        s["result"] = result
        s["formatted_result"] = formatted
        session_store.update_stage(session_id, "result")

        # 7. 完成事件
        q = get_ai_queue(session_id)
        if q is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "done", "timestamp": datetime.now().strftime("%H:%M:%S")},
            )

    except Exception as e:
        err_ts = datetime.now().strftime("%H:%M:%S")
        err_msg = f"❌ {type(e).__name__}: {e}"
        session_store.append_ai_log(session_id, err_ts, err_msg)
        if (q := get_ai_queue(session_id)) is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "error", "timestamp": err_ts, "message": err_msg},
            )
        session_store.update_stage(session_id, "error")


def start_calculate(
    session_id: str,
    module_type: str,
    extracted_data: dict,
    filling_suggestions: Optional[dict],
    main_loop: asyncio.AbstractEventLoop,
) -> None:
    """启动后台计算任务"""
    if is_calculate_running(session_id):
        raise RuntimeError(f"session {session_id!r} 已有计算任务在运行")

    session_store._main_loop = main_loop
    ensure_ai_queue(session_id)
    session_store.update_stage(session_id, "calculating")

    t = threading.Thread(
        target=_run_calculate_in_thread,
        args=(session_id, module_type, extracted_data, filling_suggestions),
        daemon=True,
        name=f"calculate-{session_id}",
    )
    t.start()
    _calculate_tasks[session_id] = t


# ==================== 填充建议任务 ====================


def _run_suggest_in_thread(
    session_id: str,
    module_type: str,
    use_llm: bool,
) -> None:
    """后台生成数据填充建议

    1. 把内存里的 extracted_data / quality_report 写盘
    2. subprocess 调脚本生成规则建议（区域电价 + 季节默认值）
    3. use_llm=True 时，再用 DirectLLMClient 对规则建议做智能增强
    """
    loop = session_store._main_loop
    s = session_store.get(session_id)
    if s is None:
        return
    session_dir = s["session_dir"]

    def emit(event_type: str, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        session_store.append_ai_log(session_id, ts, message)
        q = get_ai_queue(session_id)
        if q is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": event_type, "timestamp": ts, "message": message},
            )

    try:
        extracted_data = s.get("extracted_data")
        quality_report = s.get("quality_report") or {"completeness": 1.0, "issues": []}
        if extracted_data is None:
            raise RuntimeError("extracted_data 缺失，请先调用 /extract")

        # 1. 写盘
        emit("log", "📄 写入提取数据 + 质量报告...")
        extracted_path = session_dir / "ac_extracted_data.json"
        with open(extracted_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)
        quality_path = session_dir / "ac_quality_report.json"
        with open(quality_path, "w", encoding="utf-8") as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)
        suggestions_path = session_dir / "ac_filling_suggestions.json"

        # 2. 规则脚本
        emit("log", "🔧 调用规则脚本 suggest_data_filling.py ...")
        script = (
            PROJECT_ROOT
            / ".claude"
            / "skills"
            / "suggest-data-filling"
            / "scripts"
            / "suggest_data_filling.py"
        )
        cmd = [
            sys.executable,
            str(script),
            str(extracted_path),
            str(quality_path),
            str(suggestions_path),
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line:
                emit("log", line)
        proc.wait()
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise SkillError(
                f"规则脚本退出码 {proc.returncode}: {stderr[:500]}"
            )
        if not suggestions_path.exists():
            raise SkillError("规则脚本执行完成但未生成输出")

        with open(suggestions_path, "r", encoding="utf-8") as f:
            suggestions = json.load(f)
        emit("log", "✅ 规则建议生成完成")

        # 3. LLM 增强（可选）
        if use_llm:
            emit("log", "🤖 调用 LLM 对规则建议做智能增强...")
            try:
                from core.llm_client import DirectLLMClient

                client = DirectLLMClient()
                prompt = (
                    "你是一位暖通节能测算顾问。下面是某中央空调项目的提取数据、质量报告以及基于规则生成的填充建议。\n"
                    f"【提取数据】\n{json.dumps(extracted_data, ensure_ascii=False)[:1800]}\n\n"
                    f"【质量报告】\n{json.dumps(quality_report, ensure_ascii=False)[:600]}\n\n"
                    f"【规则建议】\n{json.dumps(suggestions, ensure_ascii=False)[:1800]}\n\n"
                    "请给出 2-4 条更智能的填充建议（例如季节插值策略、行业默认值、电价区间），"
                    "每条建议一行，限 200 字以内。"
                )
                llm_text = client.create_message(
                    prompt,
                    system="你是节能测算顾问，回复简洁专业。",
                    max_tokens=400,
                )
                suggestions["llm_enhanced_tips"] = llm_text
                emit("log", f"✅ LLM 增强完成：{llm_text[:80]}...")
            except Exception as llm_err:
                emit(
                    "log",
                    f"⚠️ LLM 增强失败（保留规则建议）：{type(llm_err).__name__}: {llm_err}",
                )

        # 4. 写回 session_store
        s["filling_suggestions"] = suggestions
        with open(suggestions_path, "w", encoding="utf-8") as f:
            json.dump(suggestions, f, ensure_ascii=False, indent=2)
        session_store.update_stage(session_id, "suggest")

        # 5. done 事件
        q = get_ai_queue(session_id)
        if q is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "done", "timestamp": datetime.now().strftime("%H:%M:%S")},
            )

    except Exception as e:
        err_ts = datetime.now().strftime("%H:%M:%S")
        err_msg = f"❌ {type(e).__name__}: {e}"
        session_store.append_ai_log(session_id, err_ts, err_msg)
        if (q := get_ai_queue(session_id)) is not None:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "error", "timestamp": err_ts, "message": err_msg},
            )
        session_store.update_stage(session_id, "error")


def start_suggest(
    session_id: str,
    module_type: str,
    use_llm: bool,
    main_loop: asyncio.AbstractEventLoop,
) -> None:
    """启动后台填充建议任务"""
    if is_suggest_running(session_id):
        raise RuntimeError(f"session {session_id!r} 已有建议任务在运行")

    session_store._main_loop = main_loop
    ensure_ai_queue(session_id)
    session_store.update_stage(session_id, "suggesting")

    t = threading.Thread(
        target=_run_suggest_in_thread,
        args=(session_id, module_type, use_llm),
        daemon=True,
        name=f"suggest-{session_id}",
    )
    t.start()
    _suggest_tasks[session_id] = t
