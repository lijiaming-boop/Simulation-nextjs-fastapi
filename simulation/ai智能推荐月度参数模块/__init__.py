"""AI 智能推荐月度参数模块

基于 AI + 程序化解析，从调研表文本（或手动输入）自动推荐：
  - monthly_chiller_count：每月开机台数
  - monthly_load_factors：月度负载系数
  - workday_curve / offday_curve：工作日/休息日逐时负载曲线
  - day_type：365 天工作日历

使用方式：
    # 独立运行（调试）：
    streamlit run simulation/ai智能推荐月度参数模块/ui.py

    # 嵌入仿真页面：
    from simulation.ai智能推荐月度参数模块 import render_ai_monthly_recommendation
    result = render_ai_monthly_recommendation()

模块结构：
    presets.py        — 7 种预置班制及逐时曲线
    calendar_parser.py — 工作日历程序化解析（循环 + 节假日）
    recommend.py      — AI 推荐引擎（阶段一 + 阶段二）
    ui.py             — Streamlit UI 组件
"""

from .presets import PRESET_SCHEDULES, SCHEDULE_LABELS
from .calendar_parser import (
    DEFAULT_DAY_TYPE,
    parse_cycle_pattern,
    generate_cycle_day_type,
    parse_holiday_intent,
    apply_holiday_overrides,
    parse_calendar_smart,
)
from .recommend import (
    ai_stage1_from_text,
    ai_stage2_recommend,
    ai_parse_calendar,
)
from .ui import (
    render_ai_monthly_recommendation,
    get_recommended_params,
)
from . import preset_manager

__all__ = [
    # presets
    "PRESET_SCHEDULES", "SCHEDULE_LABELS",
    # calendar
    "DEFAULT_DAY_TYPE", "parse_cycle_pattern", "generate_cycle_day_type",
    "parse_holiday_intent", "apply_holiday_overrides", "parse_calendar_smart",
    # recommend
    "ai_stage1_from_text", "ai_stage2_recommend", "ai_parse_calendar",
    # ui
    "render_ai_monthly_recommendation", "get_recommended_params",
]
