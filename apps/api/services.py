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
# session_id → 仿真任务后台 thread
_sim_tasks: dict = {}


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


def is_sim_running(session_id: str) -> bool:
    t = _sim_tasks.get(session_id)
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
                import os as _os
                emit("log", f"[DEBUG] ANTHROPIC_API_KEY={'set' if _os.getenv('ANTHROPIC_API_KEY') else 'NOT SET'}, BASE_URL={_os.getenv('ANTHROPIC_BASE_URL', 'default')}")
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


# ==================== 仿真模块服务函数 ====================


def _start_sim_task(
    session_id: str,
    task_func,
    main_loop: asyncio.AbstractEventLoop,
    **kwargs,
) -> threading.Thread:
    """启动仿真后台任务线程"""
    session_store._main_loop = main_loop
    t = threading.Thread(target=task_func, kwargs={"session_id": session_id, **kwargs}, daemon=True)
    _sim_tasks[session_id] = t
    t.start()
    return t


def _sim_callback(session_id: str, loop: asyncio.AbstractEventLoop, timestamp: str, message: str) -> None:
    """仿真任务 AI 回调"""
    session_store.append_ai_log(session_id, timestamp, message)
    event = {"type": "log", "timestamp": timestamp, "message": message}
    q = get_ai_queue(session_id)
    if q is not None:
        loop.call_soon_threadsafe(q.put_nowait, event)


def _sim_done(session_id: str, loop: asyncio.AbstractEventLoop, error: str = None) -> None:
    """仿真任务完成事件"""
    event = {
        "type": "error" if error else "done",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    if error:
        event["message"] = error
    q = get_ai_queue(session_id)
    if q is not None:
        loop.call_soon_threadsafe(q.put_nowait, event)


# --- 拓扑提取 ---

def _run_topology_extraction(session_id: str, upload_path: str, loop: asyncio.AbstractEventLoop) -> None:
    """后台线程：从调研表提取拓扑"""
    s = session_store.get(session_id)
    session_dir = s["session_dir"]
    output_path = session_dir / "sim_topology.json"

    def cb(ts, msg):
        _sim_callback(session_id, loop, ts, msg)

    try:
        caller = SkillCaller(timeout=300)
        cb(datetime.now().strftime("%H:%M:%S"), "🚀 开始从调研表提取设备拓扑...")

        skill_result = caller.call_skill(
            "plant-simulation",
            str(upload_path),
            str(output_path),
            "extract_topology",
            callback=cb,
        )

        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            topology = _normalize_topology(raw)
            s["sim_topology"] = topology
            s["sim_project_name"] = topology.get("project_name", "未知项目")
            s["sim_stage"] = "cop_curves"
            cb(datetime.now().strftime("%H:%M:%S"), f"✅ 拓扑识别完成：{len(topology.get('chillers',[]))} 台主机")
            _sim_done(session_id, loop)
        else:
            _sim_done(session_id, loop, "拓扑识别完成但未生成输出文件")
    except Exception as e:
        _sim_done(session_id, loop, f"拓扑提取失败: {e}")


def _run_topology_parse(session_id: str, text_input: str, project_name: str, loop: asyncio.AbstractEventLoop) -> None:
    """后台线程：文本解析拓扑"""
    s = session_store.get(session_id)
    session_dir = s["session_dir"]
    input_path = session_dir / "sim_topology_input.txt"
    output_path = session_dir / "sim_topology.json"

    def cb(ts, msg):
        _sim_callback(session_id, loop, ts, msg)

    try:
        input_path.write_text(text_input, encoding="utf-8")
        caller = SkillCaller(timeout=180)
        cb(datetime.now().strftime("%H:%M:%S"), "🚀 开始解析拓扑文本...")

        caller.call_skill(
            "plant-simulation",
            str(input_path),
            str(output_path),
            "parse_topology",
            callback=cb,
        )

        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            topology = _normalize_topology(raw)
            s["sim_topology"] = topology
            s["sim_project_name"] = topology.get("project_name", project_name or "未知项目")
            s["sim_stage"] = "cop_curves"
            cb(datetime.now().strftime("%H:%M:%S"), "✅ 拓扑解析完成")
            _sim_done(session_id, loop)
        else:
            _sim_done(session_id, loop, "拓扑解析完成但未生成输出")
    except Exception as e:
        _sim_done(session_id, loop, f"拓扑解析失败: {e}")


# --- COP 曲线解析 ---

def _run_cop_parse(session_id: str, img_path: str, idx: int, model_name: str, rated_cop: float, loop: asyncio.AbstractEventLoop) -> None:
    """后台线程：图片识别 COP 曲线"""
    s = session_store.get(session_id)
    session_dir = s["session_dir"]
    output_path = session_dir / f"sim_cop_{idx}.json"

    def cb(ts, msg):
        _sim_callback(session_id, loop, ts, msg)

    try:
        caller = SkillCaller(timeout=300)
        cb(datetime.now().strftime("%H:%M:%S"), f"🚀 开始识别 {model_name} COP 曲线...")

        caller.call_skill(
            "plant-simulation",
            str(img_path),
            str(output_path),
            "parse_cop_curve",
            callback=cb,
        )

        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                cop_data = json.load(f)
            cw_temps = cop_data.get("cw_temps", [])
            load_ratios = cop_data.get("load_ratios", [])
            cop_table = cop_data.get("cop_table", [])
            if not cw_temps or not load_ratios or not cop_table:
                # fallback to default
                default_cop = _generate_default_cop_table(rated_cop)
                default_cop["_source"] = "auto_fallback"
                s["sim_cop_data"][model_name] = default_cop
                cb(datetime.now().strftime("%H:%M:%S"), "ℹ️ 图片识别未返回有效数据，已使用默认曲线")
            else:
                s["sim_cop_data"][model_name] = cop_data
                cb(datetime.now().strftime("%H:%M:%S"), f"✅ COP 数据已收集 ({len(cw_temps)}×{len(load_ratios)})")
            s["sim_stage"] = "cop_curves"
            _sim_done(session_id, loop)
        else:
            _sim_done(session_id, loop, "COP 识别完成但未生成输出")
    except Exception as e:
        _sim_done(session_id, loop, f"COP 识别失败: {e}")


# --- 工况生成 ---

def _run_operating_generate(session_id: str, text_input: str, loop: asyncio.AbstractEventLoop) -> None:
    """后台线程：生成月度运行工况"""
    s = session_store.get(session_id)
    session_dir = s["session_dir"]
    input_path = session_dir / "sim_operating_input.txt"
    output_path = session_dir / "sim_operating.json"

    def cb(ts, msg):
        _sim_callback(session_id, loop, ts, msg)

    try:
        input_path.write_text(text_input, encoding="utf-8")
        caller = SkillCaller(timeout=300)
        cb(datetime.now().strftime("%H:%M:%S"), "🚀 开始生成月度运行工况...")

        caller.call_skill(
            "plant-simulation",
            str(input_path),
            str(output_path),
            "generate_operating",
            callback=cb,
        )

        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                operating = json.load(f)
            s["sim_operating_conditions"] = operating
            s["sim_stage"] = "simulate"
            cb(datetime.now().strftime("%H:%M:%S"), "✅ 工况数据已生成")
            _sim_done(session_id, loop)
        else:
            _sim_done(session_id, loop, "工况生成完成但未生成输出")
    except Exception as e:
        _sim_done(session_id, loop, f"工况生成失败: {e}")


# --- 仿真执行 ---

def _run_simulation(session_id: str, loop: asyncio.AbstractEventLoop) -> None:
    """后台线程：执行仿真"""
    s = session_store.get(session_id)
    session_dir = s["session_dir"]
    sim_mode = s["sim_mode"]

    def cb(ts, msg):
        _sim_callback(session_id, loop, ts, msg)

    try:
        # 打包输入
        sim_input = {
            "project_name": s.get("sim_project_name", ""),
            "sim_mode": sim_mode,
            "topology": s.get("sim_topology"),
            "cop_data": s.get("sim_cop_data", {}),
            "operating_conditions": s.get("sim_operating_conditions"),
        }

        input_path = session_dir / "sim_input_all.json"
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(sim_input, f, ensure_ascii=False, indent=2)

        output_dir = session_dir / "sim_output"
        output_dir.mkdir(exist_ok=True)

        caller = SkillCaller(timeout=600)
        cb(datetime.now().strftime("%H:%M:%S"), f"🚀 开始仿真（{sim_mode}）...")

        caller.call_skill(
            "plant-simulation",
            str(input_path),
            str(output_dir),
            sim_mode,
            callback=cb,
            max_retries=2,
        )

        # 收集结果
        result = {"success": True, "output_dir": str(output_dir), "files": []}
        for f in output_dir.iterdir():
            result["files"].append(f.name)

        report_files = list(output_dir.glob("*报告*.md")) + list(output_dir.glob("*report*.md"))
        if report_files:
            result["report"] = report_files[0].read_text(encoding="utf-8")

        summary_files = list(output_dir.glob("*汇总*.json")) + list(output_dir.glob("*summary*.json"))
        if summary_files:
            with open(summary_files[0], "r", encoding="utf-8") as f:
                result["summary"] = json.load(f)

        s["sim_result"] = result
        s["sim_stage"] = "done"
        cb(datetime.now().strftime("%H:%M:%S"), "✅ 仿真完成")
        _sim_done(session_id, loop)
    except Exception as e:
        _sim_done(session_id, loop, f"仿真执行失败: {e}")


# --- 启动仿真任务的入口函数 ---

def start_sim_topology_extract(session_id: str, upload_path: Path, main_loop) -> None:
    ensure_ai_queue(session_id)
    session_store._main_loop = main_loop
    _start_sim_task(session_id, _run_topology_extraction, main_loop, upload_path=str(upload_path), loop=main_loop)


def start_sim_topology_parse(session_id: str, text_input: str, project_name: str, main_loop) -> None:
    ensure_ai_queue(session_id)
    session_store._main_loop = main_loop
    _start_sim_task(session_id, _run_topology_parse, main_loop, text_input=text_input, project_name=project_name, loop=main_loop)


def start_sim_cop_parse(session_id: str, img_path: Path, idx: int, model_name: str, rated_cop: float, main_loop) -> None:
    ensure_ai_queue(session_id)
    session_store._main_loop = main_loop
    _start_sim_task(session_id, _run_cop_parse, main_loop, img_path=str(img_path), idx=idx, model_name=model_name, rated_cop=rated_cop, loop=main_loop)


def start_sim_operating_generate(session_id: str, text_input: str, main_loop) -> None:
    ensure_ai_queue(session_id)
    session_store._main_loop = main_loop
    _start_sim_task(session_id, _run_operating_generate, main_loop, text_input=text_input, loop=main_loop)


def start_sim_execute(session_id: str, main_loop) -> None:
    ensure_ai_queue(session_id)
    session_store._main_loop = main_loop
    _start_sim_task(session_id, _run_simulation, main_loop, loop=main_loop)


# ==================== 仿真辅助函数（从 simulation_ui.py 迁移） ====================

_INVALID_TEXT_PATTERNS = [
    "例如：", "示例:", "选填", "选框勾选", "是否", "有没有",
    "请注意", "举例", "需要让运维", "询问运维", "各设备铭牌",
    "描述一下", "客户", "末端", "该项目", "涉及", "整体情况",
    "运行规律", "特殊情况说明", "设备启停方式", "末端设备数量",
    "通讯接口", "供水温度", "运行台数", "运行频率", "出水温度",
    "工频运行则为", "变频运行可填写", "整个冷站", "填写大致的范围",
]


def _is_real_equipment(entry: dict) -> bool:
    """判断一条记录是否是真实设备数据"""
    brand = str(entry.get("brand", "") or "")
    model = str(entry.get("model", "") or "")
    if len(brand) > 40:
        return False
    combined = brand + model
    for pattern in _INVALID_TEXT_PATTERNS:
        if pattern in combined:
            return False
    capacity = entry.get("capacity_kw") or entry.get("额定制冷量") or entry.get("制冷量") or 0
    power = entry.get("power_kw") or entry.get("额定功率") or entry.get("功率") or 0
    cop = entry.get("rated_cop") or entry.get("COP") or entry.get("cop") or 0
    fan_power = entry.get("fan_power_kw") or entry.get("风机功率") or 0
    try:
        if float(capacity) > 0 or float(power) > 0 or float(cop) > 0 or float(fan_power) > 0:
            return True
    except (ValueError, TypeError):
        pass
    if brand and model:
        return True
    if brand and len(brand) <= 20 and not any(p in brand for p in ["类型", "否", "是", "/"]):
        return True
    if model and len(model) <= 60:
        return True
    return False


def _normalize_topology(raw: dict) -> dict:
    """标准化 AI 输出的拓扑 JSON"""
    if "topology" in raw and isinstance(raw["topology"], dict):
        inner = raw["topology"]
        project_name = raw.get("project_name", inner.get("project_name", raw.get("项目名称", "未知项目")))
        raw = inner
    else:
        project_name = raw.get("project_name", raw.get("项目名称", "未知项目"))

    topology = {"project_name": project_name}

    # 冷水主机
    chillers = (
        raw.get("chillers") or raw.get("冷水主机") or raw.get("主机") or
        raw.get("chiller") or raw.get("冷水机组") or []
    )
    normalized_chillers = []
    for ch in chillers:
        if not isinstance(ch, dict) or not _is_real_equipment(ch):
            continue
        normalized_chillers.append({
            "brand": ch.get("brand", ch.get("品牌", "")) or "",
            "model": ch.get("model", ch.get("型号", "")) or "",
            "type": ch.get("type", ch.get("类型", "")) or "",
            "count": int(ch.get("count", ch.get("台数", ch.get("数量", 1))) or 1),
            "capacity_kw": float(ch.get("capacity_kw", ch.get("额定制冷量", ch.get("制冷量", 0))) or 0),
            "power_kw": float(ch.get("power_kw", ch.get("额定功率", ch.get("功率", 0))) or 0),
            "rated_cop": float(ch.get("rated_cop", ch.get("COP", ch.get("额定COP", ch.get("cop", 0)))) or 0),
            "vfd": ch.get("vfd", ch.get("变频", True)),
        })

    # 纠正水泵误分类
    misclassified_pumps = []
    real_chillers = []
    for ch in normalized_chillers:
        cop = ch.get("rated_cop", 0)
        power = ch.get("power_kw", 0)
        capacity = ch.get("capacity_kw", 0)
        computed_ratio = capacity / power if power > 0 else 0
        if cop > 10 or (computed_ratio > 10 and power <= 200):
            misclassified_pumps.append(ch)
        else:
            real_chillers.append(ch)
    topology["chillers"] = real_chillers

    extra_chilled_pumps = [
        {"power_kw": p.get("power_kw", 0), "count": p.get("count", 1), "vfd": p.get("vfd", True)}
        for p in misclassified_pumps
    ]

    # 冷却泵
    cooling_pumps = raw.get("cooling_pumps") or raw.get("冷却泵") or []
    topology["cooling_pumps"] = [
        {
            "brand": p.get("brand", p.get("品牌", "")) or "",
            "model": p.get("model", p.get("型号", "")) or "",
            "power_kw": float(p.get("power_kw", p.get("功率", 0)) or 0),
            "count": int(p.get("count", p.get("台数", 1)) or 1),
            "vfd": p.get("vfd", p.get("变频", True)),
            "flow_rate_m3h": float(p.get("flow_rate_m3h", p.get("流量", p.get("额定流量", 0))) or 0),
            "head_m": float(p.get("head_m", p.get("扬程", p.get("压头", 0))) or 0),
        }
        for p in cooling_pumps if isinstance(p, dict) and _is_real_equipment(p)
    ]

    # 冷冻泵
    chilled_pumps = raw.get("chilled_pumps") or raw.get("冷冻泵") or []
    normalized_chilled = [
        {
            "brand": p.get("brand", p.get("品牌", "")) or "",
            "model": p.get("model", p.get("型号", "")) or "",
            "power_kw": float(p.get("power_kw", p.get("功率", 0)) or 0),
            "count": int(p.get("count", p.get("台数", 1)) or 1),
            "vfd": p.get("vfd", p.get("变频", True)),
            "flow_rate_m3h": float(p.get("flow_rate_m3h", p.get("流量", p.get("额定流量", 0))) or 0),
            "head_m": float(p.get("head_m", p.get("扬程", p.get("压头", 0))) or 0),
        }
        for p in chilled_pumps if isinstance(p, dict) and _is_real_equipment(p)
    ]
    existing_powers = {p["power_kw"] for p in normalized_chilled}
    for ep in extra_chilled_pumps:
        if ep["power_kw"] not in existing_powers:
            normalized_chilled.append(ep)
    topology["chilled_pumps"] = normalized_chilled

    # 冷却塔
    towers = raw.get("towers") or raw.get("冷却塔") or []
    topology["towers"] = [
        {
            "brand": t.get("brand", t.get("品牌", "")) or "",
            "model": t.get("model", t.get("型号", "")) or "",
            "fan_power_kw": float(t.get("fan_power_kw", t.get("风机功率", t.get("功率", 0))) or 0),
            "count": int(t.get("count", t.get("台数", 1)) or 1),
            "vfd": t.get("vfd", t.get("变频", True)),
            "type": t.get("type", t.get("类型", "开式")),
            "flow_rate_m3h": float(t.get("flow_rate_m3h", t.get("流量", t.get("额定流量", 0))) or 0),
        }
        for t in towers if isinstance(t, dict) and _is_real_equipment(t)
    ]

    # 特殊结构
    special = raw.get("special") or raw.get("特殊结构") or {"type": "none"}
    if isinstance(special, dict):
        sp_type = special.get("type", "none")
        if isinstance(sp_type, str) and len(sp_type) > 20:
            detected = []
            if "热回收" in sp_type:
                detected.append("heat_recovery")
            if "蓄冷" in sp_type or "蓄冰" in sp_type:
                detected.append("storage")
            sp_type = "_and_".join(detected) if detected else "none"
        special["type"] = sp_type
    elif isinstance(special, str):
        special = {"type": special if len(special) <= 20 else "none"}
    else:
        special = {"type": "none"}
    topology["special"] = special

    return topology


def _generate_default_cop_table(rated_cop: float) -> dict:
    """基于额定 COP 生成典型部分负荷曲线"""
    cw_temps = list(range(18, 34))
    load_ratios = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]
    plr_factors = [1.00, 1.08, 1.14, 1.18, 1.15, 1.08, 0.95, 0.78, 0.58]
    base_cw_temp = 30.0

    cop_table = []
    for cw_t in cw_temps:
        row = []
        temp_factor = 1.0 - 0.03 * (cw_t - base_cw_temp)
        for plr_f in plr_factors:
            cop = rated_cop * plr_f * temp_factor
            row.append(round(max(cop, 2.0), 2))
        cop_table.append(row)

    return {
        "cw_temps": cw_temps,
        "load_ratios": load_ratios,
        "cop_table": cop_table,
    }
