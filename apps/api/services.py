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
            # === 空压场景：subprocess 文本提取 + DirectLLMClient 结构化分析 ===
            session_dir = session_store.get(session_id)["session_dir"]
            text_json_path = session_dir / "extracted_air_compressor_text.json"

            ai_callback(datetime.now().strftime("%H:%M:%S"), "🚀 [空压] Step 1: 文本提取（subprocess）...")
            text_script = (
                PROJECT_ROOT
                / ".claude"
                / "skills"
                / "extract-air-compressor-data-llm"
                / "scripts"
                / "extract_air_compressor_data_llm.py"
            )
            cmd = [
                sys.executable,
                str(text_script),
                str(input_path),
                str(text_json_path),
                original_filename,
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
                    ai_callback(datetime.now().strftime("%H:%M:%S"), line)
            proc.wait()
            if proc.returncode != 0:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise SkillError(f"文本提取脚本退出码 {proc.returncode}: {stderr[:500]}")
            if not text_json_path.exists():
                raise SkillError("文本提取脚本执行完成但未生成输出")

            # 读取提取的文本
            with open(text_json_path, "r", encoding="utf-8") as f:
                text_data = json.load(f)
            text_content = text_data.get("text_content", "")
            ai_callback(
                datetime.now().strftime("%H:%M:%S"),
                f"✅ 文本提取完成（{len(text_content)} 字符）",
            )

            # Step 2: LLM 结构化分析
            ai_callback(datetime.now().strftime("%H:%M:%S"), "🤖 [空压] Step 2: LLM 结构化分析...")
            from core.llm_client import DirectLLMClient

            client = DirectLLMClient()
            system_prompt = _build_air_compressor_extract_prompt()
            user_prompt = (
                f"以下是空压机调研表的文本内容，请按照系统指令提取结构化数据并以 JSON 格式输出。\n\n"
                f"原始文件名: {original_filename}\n\n"
                f"【文本内容】\n{text_content[:6000]}"
            )
            llm_text = client.create_message(
                user_prompt,
                system=system_prompt,
                max_tokens=2000,
            )
            ai_callback(
                datetime.now().strftime("%H:%M:%S"),
                f"✅ LLM 分析完成（{len(llm_text)} 字符）",
            )

            # 解析 LLM 输出为 JSON
            extracted_json = _parse_llm_json_output(llm_text)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(extracted_json, f, ensure_ascii=False, indent=2)
            ai_callback(
                datetime.now().strftime("%H:%M:%S"),
                "✅ 结构化数据已写入 " + output_json_path.name,
            )

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

        if module_type == "air_compressor":
            # ==================== 空压机计算路径 ====================
            from core.air_compressor_calculator import AirCompressorCalculator

            # 1. 将 LLM 提取结构映射为 Calculator 期望的格式
            emit("log", "📄 映射空压机数据结构...")
            project_level = extracted_data.get("projectLevel", {}) if isinstance(extracted_data, dict) else {}
            raw_equipment = extracted_data.get("equipmentLevel", []) if isinstance(extracted_data, dict) else []

            # 设备类型名映射：螺杆→螺杆式、离心→离心式
            type_map = {"螺杆": "螺杆式", "离心": "离心式"}
            equipment_list = []
            for eq in (raw_equipment if isinstance(raw_equipment, list) else []):
                mapped = dict(eq)
                et = mapped.get("equipmentType", "")
                if et in type_map:
                    mapped["equipmentType"] = type_map[et]
                equipment_list.append(mapped)

            calculator_input = {
                "system_info": {
                    "project_name": project_level.get("projectName", ""),
                    "customer_name": project_level.get("companyName", ""),
                    "contact_person": "",
                    "contact_phone": "",
                },
                "equipment_list": equipment_list,
                "operation_data": {
                    "annual_operating_hours": (
                        (project_level.get("dailyRunningHours") or 10)
                        * (project_level.get("annualRunningDays") or 330)
                    ),
                },
                "completeness": 1.0,
                "filled_count": 0,
                "session_dir": str(session_dir),
                "original_filename": s.get("original_filename", ""),
            }

            filled_path = session_dir / "compressor_filled_data.json"
            with open(filled_path, "w", encoding="utf-8") as f:
                json.dump(calculator_input, f, ensure_ascii=False, indent=2)

            # 2. 应用填充建议（如果有）
            if filling_suggestions and filling_suggestions.get("fillable_suggestions"):
                emit("log", "📝 应用空压填充建议...")
                for sug in filling_suggestions.get("fillable_suggestions", []):
                    field = sug.get("field", "")
                    value = sug.get("suggested_value")
                    if value is not None and field and not field.startswith("equipmentList["):
                        calculator_input[field] = value
                with open(filled_path, "w", encoding="utf-8") as f:
                    json.dump(calculator_input, f, ensure_ascii=False, indent=2)

            # 3. AirCompressorCalculator 计算
            emit("log", "⚙️ 运行空压机节能计算...")
            calculator = AirCompressorCalculator()
            result_path = str(session_dir / "compressor_result.json")
            calculator.calculate(str(filled_path), result_path)
            emit("log", "✅ 计算完成")

            # 4. 读取结果
            with open(result_path, "r", encoding="utf-8") as f:
                result = json.load(f)
            with open(filled_path, "r", encoding="utf-8") as f:
                filled_data = json.load(f)

            formatted = calculator.format_export_results(filled_data, result)

            # 5. 写回 session_store
            s["filling_suggestions"] = filling_suggestions
            s["result"] = result
            s["formatted_result"] = formatted
            session_store.update_stage(session_id, "result")

        else:
            # ==================== 空调计算路径（原有逻辑） ====================

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
        prefix = "compressor_" if module_type == "air_compressor" else "ac_"
        extracted_path = session_dir / f"{prefix}extracted_data.json"
        with open(extracted_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)
        quality_path = session_dir / f"{prefix}quality_report.json"
        with open(quality_path, "w", encoding="utf-8") as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)
        suggestions_path = session_dir / f"{prefix}filling_suggestions.json"

        # 2. 规则脚本（按模块类型分发）
        if module_type == "air_compressor":
            skill_dir = "suggest-air-compressor-data-filling"
            script_name = "suggest_air_compressor_data_filling.py"
            emit("log", "🔧 调用空压规则脚本 suggest_air_compressor_data_filling.py ...")
        else:
            skill_dir = "suggest-data-filling"
            script_name = "suggest_data_filling.py"
            emit("log", "🔧 调用空调规则脚本 suggest_data_filling.py ...")
        script = PROJECT_ROOT / ".claude" / "skills" / skill_dir / "scripts" / script_name
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
                if module_type == "air_compressor":
                    prompt = (
                        "你是一位空压机节能测算顾问。下面是某空压机项目的提取数据、质量报告以及基于规则生成的填充建议。\n"
                        f"【提取数据】\n{json.dumps(extracted_data, ensure_ascii=False)[:1800]}\n\n"
                        f"【质量报告】\n{json.dumps(quality_report, ensure_ascii=False)[:600]}\n\n"
                        f"【规则建议】\n{json.dumps(suggestions, ensure_ascii=False)[:1800]}\n\n"
                        "请给出 2-4 条更智能的填充建议（例如行业默认压力范围、设备效率曲线、联控策略），"
                        "每条建议一行，限 200 字以内。"
                    )
                else:
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


# ==================== 空压机辅助函数 ====================

def _build_air_compressor_extract_prompt() -> str:
    """构建空压机数据提取的 LLM 系统提示词

    内容基于 .claude/skills/extract-air-compressor-data-llm/SKILL.md
    """
    return """你是空压机调研表数据提取专家。请从用户提供的文本内容中提取结构化数据。

## 输出格式
严格按以下 JSON 格式输出：
{
  "rawData": {
    "projectLevel": {
      "companyName": "企业名称",
      "companyShortName": "企业简称",
      "projectName": "项目名称",
      "projectLocation": "项目所在地",
      "industryType": "行业类型",
      "totalAnnualEnergyConsumption": 数值,
      "electricityPrice": 数值,
      "alarmPressureLowerLimit": 数值,
      "averagePressure": 数值,
      "dailyRunningHours": 数值,
      "annualRunningDays": 数值
    },
    "equipmentLevel": [
      {
        "stationId": "站房编码",
        "equipmentId": "设备编码",
        "equipmentType": "螺杆|离心",
        "brand": "品牌",
        "model": "型号",
        "manufactureYear": 数值,
        "runningStatus": "运行|备用|故障|停用",
        "ratedPower": 数值(kW),
        "ratedFlow": 数值(m³/min)
      }
    ]
  },
  "rejectionCheck": {
    "shouldReject": false,
    "criticalIssues": [],
    "highSeverityIssues": []
  },
  "quality_report": {
    "completeness": 0.85,
    "confidence": "high|medium|low",
    "issues": []
  }
}

## 提取规则
1. 数值字段只提取纯数字，缺失设null
2. industryType 必须为: 电池|整车及电子|钢铁有色|其他
3. 设备runningStatus: 运行|备用|故障|停用
4. equipmentType: 螺杆|离心

## 行业归类
- 电池/锂电/储能 → 电池
- 整车/汽车/电子制造 → 整车及电子
- 钢铁/冶金/有色 → 钢铁有色
- 其他所有 → 其他

## 打回条件（shouldReject=true）
1. alarmPressureLowerLimit 空或≤0
2. averagePressure 空或≤0
3. totalAnnualEnergyConsumption 空或≤0
4. 无运行/备用设备
5. stationId 为空
6. equipmentId 重复或空

## 电价参考（元/kWh）
广东0.69 江苏0.70 浙江0.73 上海0.75 山东0.74
四川0.52 重庆0.70 福建0.63 湖北0.64 湖南0.65

## 功率因子查表
三星/国产/复盛 机龄>10年: 0.32
寿力/韩华: 0.34
阿特拉斯/英格索兰 5-10年: 0.35, <5年: 0.36
默认: 0.35

## 比功率计算
specificPower = (ratedPower × 1.1) / ratedFlow

## 置信度
从100%起扣: 压力数据<14天-5%, 行业缺失-15%, 电价缺失-10%, 每天开机时间缺失-5%, 年运行天数缺失-5%
≥80%=high, 60-79%=medium, <60%=low

只输出 JSON，不要其他文字。"""


def _parse_llm_json_output(llm_text: str) -> dict:
    """从 LLM 输出中解析 JSON，支持代码块包裹"""
    import re

    text = llm_text.strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从 ```json ... ``` 中提取
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    # 兆底：返回空结构
    return {
        "rawData": {"projectLevel": {}, "equipmentLevel": []},
        "rejectionCheck": {
            "shouldReject": True,
            "criticalIssues": ["LLM 输出无法解析为 JSON"],
            "highSeverityIssues": [],
        },
        "quality_report": {
            "completeness": 0,
            "confidence": "low",
            "issues": [{"field": "system", "severity": "critical", "description": "LLM 输出解析失败"}],
        },
    }
