"""Agent 工具注册表

把测算主线的确定性能力（提取/质检/填充/计算）包装成带 JSON Schema 的工具。
所有工具都是零 LLM 成本的确定性函数——LLM 只负责"决定调哪个"，不参与执行。

控制类工具（finish / request_user_input）由 orchestrator 拦截处理，
不走 handler，但同样注册在这里供决策模型看到统一的工具视图。
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.data_filler import DataFiller
from core.excel_calculator import ExcelCalculator
from config import WeatherService

# 项目根目录（agent/ 的上一级）
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"


class AgentToolError(RuntimeError):
    """工具执行失败（观察结果会带错误信息返回给决策模型）"""


@dataclass
class ToolContext:
    """一次 agent 运行的共享上下文：会话目录 + 中间产物状态"""
    session_dir: Path
    original_filename: str = ""
    # 运行时状态：各阶段产物（dict）与文件路径
    state: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value


@dataclass
class Tool:
    """一个可被 agent 调用的工具"""
    name: str
    description: str
    input_schema: Dict[str, Any]           # JSON Schema
    handler: Optional[Callable[[ToolContext, Dict[str, Any]], Dict[str, Any]]] = None
    control: bool = False                  # 控制类工具（finish/request_user_input），orchestrator 拦截

    def compact_view(self) -> Dict[str, Any]:
        """给决策模型的紧凑工具描述"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


class ToolRegistry:
    """工具注册表"""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def compact_views(self) -> List[Dict[str, Any]]:
        return [t.compact_view() for t in self._tools.values()]

    def execute(self, name: str, ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具 handler（仅确定性工具；控制类由 orchestrator 处理）"""
        tool = self._tools.get(name)
        if tool is None:
            raise AgentToolError(f"未知工具: {name}")
        if tool.handler is None:
            raise AgentToolError(f"工具 {name} 没有 handler（控制类工具应由 orchestrator 处理）")
        return tool.handler(ctx, args)


# ==================== 确定性工具 handler ====================

def _run_script(script_rel: Path, args: List[str]) -> str:
    """以子进程方式运行 skill 纯 Python 脚本（零 LLM 成本）"""
    script = SKILLS_DIR / script_rel
    if not script.exists():
        raise AgentToolError(f"脚本不存在: {script}")
    cmd = [sys.executable, str(script), *args]
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise AgentToolError(
            f"脚本 {script.name} 退出码 {proc.returncode}: {(stderr or stdout or '')[-500:]}"
        )
    return stdout


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_survey(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """调研表提取 + 质量检查（确定性规则引擎，合并原 extract+check 两个 skill）"""
    survey_path = Path(args["survey_path"])
    if not survey_path.exists():
        raise AgentToolError(f"调研表不存在: {survey_path}")

    out_path = ctx.session_dir / "extracted_data.json"
    original_filename = args.get("original_filename") or ctx.original_filename or survey_path.name

    _run_script(
        Path("extract-and-check-data") / "scripts" / "extract_and_check_data.py",
        [str(survey_path), str(out_path), original_filename],
    )
    if not out_path.exists():
        raise AgentToolError("提取脚本执行完成但未生成输出")

    content = _load_json(out_path)
    if content.get("error"):
        raise AgentToolError(f"提取失败: {content.get('message', '未知错误')}")

    extracted = content.get("extracted_data", content)
    quality = content.get("quality_report", {})
    ctx.set("extracted_data", extracted)
    ctx.set("quality_report", quality)

    # 提取脚本输出的是 {extracted_data, quality_report} 合并结构；
    # 拆分成两个原始文件，与下游 suggest/fill 工具及 services.py 的约定保持一致
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)
    with open(ctx.session_dir / "quality_report.json", "w", encoding="utf-8") as f:
        json.dump(quality, f, ensure_ascii=False, indent=2)

    issues = quality.get("issues", [])
    return {
        "project_region": extracted.get("project_region"),
        "station_type": extracted.get("station_type"),
        "station_type_confidence": extracted.get("station_type_confidence"),
        "completeness": quality.get("completeness"),
        "confidence_level": quality.get("confidence_level"),
        "issue_count": len(issues),
        "critical_issues": [
            i.get("message", str(i))[:120] for i in issues
            if isinstance(i, dict) and i.get("severity") in ("critical", "high")
        ][:5],
        "output_file": out_path.name,
    }


def suggest_filling(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """生成缺失数据填充建议（规则引擎：插值→季节代表值→行业默认值）"""
    extracted = ctx.get("extracted_data")
    quality = ctx.get("quality_report")
    if extracted is None or quality is None:
        raise AgentToolError("缺少提取数据，必须先执行 extract_survey")

    extracted_path = ctx.session_dir / "extracted_data.json"
    quality_path = ctx.session_dir / "quality_report.json"
    if not quality_path.exists():
        with open(quality_path, "w", encoding="utf-8") as f:
            json.dump(quality, f, ensure_ascii=False, indent=2)

    out_path = ctx.session_dir / "filling_suggestions.json"
    _run_script(
        Path("suggest-data-filling") / "scripts" / "suggest_data_filling.py",
        [str(extracted_path), str(quality_path), str(out_path)],
    )
    if not out_path.exists():
        raise AgentToolError("填充建议脚本执行完成但未生成输出")

    suggestions = _load_json(out_path)
    ctx.set("suggestions", suggestions)

    fillable = suggestions.get("fillable_suggestions", [])
    return {
        "can_proceed": suggestions.get("can_proceed"),
        "unfillable_count": len(suggestions.get("unfillable_fields", [])),
        "fillable_count": len(fillable),
        "unfillable_fields": [
            u.get("field", str(u))[:80] for u in suggestions.get("unfillable_fields", [])
        ][:8],
        "suggestion_methods": sorted({s.get("method", "") for s in fillable if s.get("method")}),
        "output_file": out_path.name,
    }


def apply_filling(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """应用填充建议，生成完整数据集（机械执行，受保护字段不可改写）"""
    suggestions = ctx.get("suggestions")
    if suggestions is None:
        raise AgentToolError("缺少填充建议，必须先执行 suggest_filling")

    extracted_path = ctx.session_dir / "extracted_data.json"
    suggestions_path = ctx.session_dir / "filling_suggestions.json"
    out_path = ctx.session_dir / "filled_data.json"

    filler = DataFiller()
    filler.fill_data(str(extracted_path), str(suggestions_path), str(out_path))

    filled = _load_json(out_path)
    ctx.set("filled_data", filled)
    meta = filled.get("_metadata", {})
    return {
        "fill_count": meta.get("fill_count"),
        "original_completeness": meta.get("original_completeness"),
        "final_completeness": meta.get("final_completeness"),
        "output_file": out_path.name,
    }


def calculate_saving_rate(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """运行 Excel 公式引擎计算节能率（formulas 库，双 sheet 上下限）"""
    filled_path = ctx.session_dir / "filled_data.json"
    if not filled_path.exists():
        raise AgentToolError("缺少填充后数据，必须先执行 apply_filling")

    result_path = ctx.session_dir / "result_data.json"
    calculator = ExcelCalculator(weather_service=WeatherService())
    calculator.calculate(str(filled_path), str(result_path))

    result = _load_json(result_path)
    filled = _load_json(filled_path)
    ctx.set("result", result)
    ctx.set("formatted_result", calculator.format_export_results(filled, result))

    return {
        "energy_saving_rate_range": result.get("energy_saving_rate_range"),
        "energy_saving_rate_min": result.get("energy_saving_rate_min"),
        "energy_saving_rate_max": result.get("energy_saving_rate_max"),
        "total_saving": result.get("total_saving"),
        "chiller_saving": result.get("chiller_saving"),
        "pump_saving": result.get("pump_saving"),
        "tower_saving": result.get("tower_saving"),
        "final_completeness": result.get("completeness"),
        "calculation_method": result.get("calculation_method"),
        "output_file": result_path.name,
    }


# ==================== 共享策略函数 ====================

def fill_ratio(suggestions: Dict[str, Any],
               available_fields: Optional[List[str]] = None) -> float:
    """填充建议占比 = 需估算的模板字段点 / 模板应有的字段点

    分母用模板可用字段（available_fields）：模板天生没有、只能靠行业默认值
    填充的点不属于数据质量风险，不计入分子。

    suggestions 支持两种输入：完整建议列表（fillable_suggestions）或
    紧凑字段名列表（fillable_fields，状态视图瘦身用）。
    """
    raw = suggestions.get("fillable_suggestions")
    if raw is not None:
        names = [str(s.get("field", "")).split(".")[-1] for s in raw]
    else:
        names = [str(n).split(".")[-1] for n in suggestions.get("fillable_fields", [])]
    if available_fields:
        available_set = set(available_fields)
        fillable_in_template = sum(1 for n in names if n in available_set)
        denominator = max(1, len(available_set) * 12)
    else:
        fillable_in_template = len(names)
        denominator = 12 * 7
    return fillable_in_template / denominator


# ==================== 空压机线工具（M2 统一编排） ====================

def extract_compressor_survey(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """空压调研表提取（LLM 型工具）：文本抽取 + agent 结构化，经 claude-agent-sdk"""
    survey_path = Path(args["survey_path"])
    if not survey_path.exists():
        raise AgentToolError(f"调研表不存在: {survey_path}")

    out_path = ctx.session_dir / "extracted_data.json"
    original_filename = args.get("original_filename") or ctx.original_filename or survey_path.name

    from core.skill_caller import SkillCaller
    caller = SkillCaller(timeout=300, project_root=PROJECT_ROOT)
    caller.call_skill(
        "extract-air-compressor-data-llm",
        str(survey_path), str(out_path), original_filename,
    )
    if not out_path.exists():
        raise AgentToolError("空压提取完成但未生成输出")

    content = _load_json(out_path)
    if content.get("error"):
        raise AgentToolError(f"提取失败: {content.get('message', '未知错误')}")

    # 兼容空压 LLM 输出 schema：rawData / quality_report / rejectionCheck
    extracted = content.get("rawData", content)
    quality = content.get("quality_report") or content.get("rejectionCheck") or {}
    ctx.set("extracted_data", extracted)
    ctx.set("quality_report", quality)
    with open(ctx.session_dir / "quality_report.json", "w", encoding="utf-8") as f:
        json.dump(quality, f, ensure_ascii=False, indent=2)

    rejected = bool(quality.get("rejected")) if isinstance(quality, dict) else False
    return {
        "project_name": (extracted.get("projectLevel") or {}).get("projectName", ""),
        "rejected": rejected,
        "rejection_reason": (quality or {}).get("reason", ""),
        "equipment_count": len(extracted.get("equipmentLevel") or []),
        "output_file": out_path.name,
    }


def suggest_compressor_filling(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """空压缺失参数填充建议（规则引擎：附表压力/功率因子/省份电价）"""
    extracted = ctx.get("extracted_data")
    quality = ctx.get("quality_report")
    if extracted is None or quality is None:
        raise AgentToolError("缺少提取数据，必须先执行 extract_survey")

    extracted_path = ctx.session_dir / "extracted_data.json"
    quality_path = ctx.session_dir / "quality_report.json"
    out_path = ctx.session_dir / "filling_suggestions.json"

    _run_script(
        Path("suggest-air-compressor-data-filling") / "scripts" / "suggest_air_compressor_data_filling.py",
        [str(extracted_path), str(quality_path), str(out_path)],
    )
    if not out_path.exists():
        raise AgentToolError("空压填充建议脚本执行完成但未生成输出")

    suggestions = _load_json(out_path)
    ctx.set("suggestions", suggestions)
    return {
        "can_proceed": suggestions.get("can_proceed"),
        "unfillable_count": len(suggestions.get("unfillable_fields", [])),
        "fillable_count": len(suggestions.get("fillable_suggestions", [])),
        "output_file": out_path.name,
    }


def apply_compressor_filling(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """把建议合并进计算输入，生成空压 filled_data（与 services.py 管线一致）"""
    suggestions = ctx.get("suggestions")
    extracted = ctx.get("extracted_data")
    if suggestions is None or extracted is None:
        raise AgentToolError("缺少提取数据或填充建议")

    project_level = extracted.get("projectLevel", {}) if isinstance(extracted, dict) else {}
    raw_equipment = extracted.get("equipmentLevel", []) if isinstance(extracted, dict) else []
    type_map = {"螺杆": "螺杆式", "离心": "离心式"}
    equipment_list = []
    for eq in (raw_equipment if isinstance(raw_equipment, list) else []):
        mapped = dict(eq)
        et = mapped.get("equipmentType", "")
        if et in type_map:
            mapped["equipmentType"] = type_map[et]
        equipment_list.append(mapped)

    daily = project_level.get("dailyRunningHours") or 10
    annual = project_level.get("annualRunningDays") or 330
    calculator_input = {
        "system_info": {
            "project_name": project_level.get("projectName", ""),
            "customer_name": project_level.get("companyName", ""),
            "contact_person": "",
            "contact_phone": "",
        },
        "equipment_list": equipment_list,
        "operation_data": {"annual_operating_hours": daily * annual},
        "completeness": 1.0,
        "filled_count": 0,
        "session_dir": str(ctx.session_dir),
        "original_filename": ctx.original_filename,
    }
    applied = 0
    for sug in suggestions.get("fillable_suggestions", []):
        field = sug.get("field", "")
        value = sug.get("suggested_value")
        if value is not None and field and not field.startswith("equipmentList["):
            calculator_input[field] = value
            applied += 1

    out_path = ctx.session_dir / "filled_data.json"
    _dump_json(out_path, calculator_input)
    ctx.set("filled_data", calculator_input)
    return {"fill_count": applied, "output_file": out_path.name}


def calculate_compressor_saving(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """空压节能计算（确定性公式：AirCompressorCalculator）"""
    filled_path = ctx.session_dir / "filled_data.json"
    if not filled_path.exists():
        raise AgentToolError("缺少填充后数据，必须先执行 apply_filling")

    result_path = ctx.session_dir / "result_data.json"
    from core.air_compressor_calculator import AirCompressorCalculator
    calculator = AirCompressorCalculator()
    calculator.calculate(str(filled_path), str(result_path))

    result = _load_json(result_path)
    filled = _load_json(filled_path)
    ctx.set("result", result)
    ctx.set("formatted_result", calculator.format_export_results(filled, result))
    return {
        "total_saving": result.get("total_saving"),
        "output_file": result_path.name,
    }


def _dump_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def build_registry_for_module(module_type: str = "air_conditioner") -> ToolRegistry:
    """按业务线构建工具注册表——同一 orchestrator/门禁语义，不同工具集"""
    registry = ToolRegistry()
    if module_type == "air_compressor":
        registry.register(Tool(
            name="extract_survey",
            description="从空压调研表（Excel/Word/PPT）提取结构化设备与运行数据"
                        "（LLM 型工具，经 agent 会话）。",
            input_schema={
                "type": "object",
                "properties": {
                    "survey_path": {"type": "string"},
                    "original_filename": {"type": "string"},
                },
                "required": ["survey_path"],
            },
            handler=extract_compressor_survey,
        ))
        registry.register(Tool(
            name="suggest_filling",
            description="空压缺失参数填充建议（规则引擎：附表压力/功率因子/省份电价）。",
            input_schema={"type": "object", "properties": {}},
            handler=suggest_compressor_filling,
        ))
        registry.register(Tool(
            name="apply_filling",
            description="把填充建议合并进计算输入，生成空压 filled_data。",
            input_schema={"type": "object", "properties": {}},
            handler=apply_compressor_filling,
        ))
        registry.register(Tool(
            name="calculate_saving_rate",
            description="运行空压节能计算（系统参数、保守/乐观区间）。",
            input_schema={"type": "object", "properties": {}},
            handler=calculate_compressor_saving,
        ))
    else:
        registry.register(Tool(
            name="extract_survey",
            description="从中央空调节能调研表 Excel 提取 12 个月运行数据并做质量检查。"
                        "返回项目地区、站房类型、数据完整率、置信度和问题列表。",
            input_schema={
                "type": "object",
                "properties": {
                    "survey_path": {"type": "string", "description": "调研表 Excel 文件路径"},
                    "original_filename": {"type": "string", "description": "用户上传时的原始文件名（用于地区推断）"},
                },
                "required": ["survey_path"],
            },
            handler=extract_survey,
        ))
        registry.register(Tool(
            name="suggest_filling",
            description="基于提取数据和质量报告，用规则引擎生成缺失数据的填充建议"
                        "（线性插值/季节代表值/行业默认值），返回 can_proceed 与建议列表。",
            input_schema={"type": "object", "properties": {}},
            handler=suggest_filling,
        ))
        registry.register(Tool(
            name="apply_filling",
            description="执行数据填充，把建议值写入缺失字段，生成完整数据集（受保护字段不可改写）。",
            input_schema={"type": "object", "properties": {}},
            handler=apply_filling,
        ))
        registry.register(Tool(
            name="calculate_saving_rate",
            description="用 Excel 物理公式引擎（双 sheet 上下限）计算节能率范围与分项节能量。",
            input_schema={"type": "object", "properties": {}},
            handler=calculate_saving_rate,
        ))
    # 控制类工具（两条业务线共用）
    registry.register(Tool(
        name="request_user_input",
        description="中断流程并向用户请求补充数据或确认。当数据质量不达标、"
                    "站房类型不支持、或填充建议风险过高时必须调用。",
        input_schema={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "为什么需要用户介入（一句话）"},
                "missing_items": {"type": "array", "items": {"type": "string"},
                                   "description": "需要用户补充/确认的具体条目"},
            },
            "required": ["reason"],
        },
        control=True,
    ))
    registry.register(Tool(
        name="request_approval",
        description="暂停流程等待人工审批（可恢复）。填充建议占比超阈值时，"
                    "在执行填充前调用；批准后流程从断点继续。",
        input_schema={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "为什么需要审批（一句话）"},
            },
            "required": ["reason"],
        },
        control=True,
    ))
    registry.register(Tool(
        name="finish",
        description="结束本次测算并向用户输出最终结论摘要。",
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "面向销售/解决方案用户的中文结论摘要"},
            },
            "required": ["summary"],
        },
        control=True,
    ))
    return registry


# 向后兼容：默认构建空调主线注册表
def build_default_registry() -> ToolRegistry:
    return build_registry_for_module("air_conditioner")
