"""输入解析 - 从各种格式提取设备参数和COP曲线"""
import re
from typing import Dict, List

from .simulator import ChillerGroup, PumpGroup, TowerGroup, PlantConfig


def parse_cop_curve_from_text(text: str) -> Dict[float, float]:
    """从文本描述解析COP曲线，支持多种格式"""
    curve = {}
    lines = text.strip().split("\n")
    for line in lines:
        numbers = re.findall(r"[\d.]+", line)
        if len(numbers) >= 2:
            load = float(numbers[0])
            cop = float(numbers[-1])
            if load > 1:
                load = load / 100.0
            if 0 < load <= 1.0 and 0 < cop < 20:
                curve[load] = cop
    return curve if curve else {0.7: 5.5, 1.0: 5.0}


def parse_cop_curve_from_table(load_ratios: List[float], cop_values: List[float]) -> Dict[float, float]:
    """从表格数据解析COP曲线"""
    curve = {}
    for lr, cop in zip(load_ratios, cop_values):
        if lr > 1:
            lr = lr / 100.0
        curve[lr] = cop
    return curve


def parse_cop_curve_from_image_result(ai_response: str) -> Dict[float, float]:
    """从AI图片识别结果解析COP曲线"""
    curve = {}
    lines = ai_response.strip().split("\n")
    for line in lines:
        numbers = re.findall(r"[\d.]+", line)
        if len(numbers) >= 2:
            for i in range(len(numbers) - 1):
                load = float(numbers[i])
                cop = float(numbers[i + 1])
                if load > 1:
                    load = load / 100.0
                if 0 < load <= 1.0 and 1 < cop < 15:
                    curve[load] = cop
                    break
    return curve


def build_plant_config_from_extracted_data(ac_data: dict, user_inputs: dict) -> PlantConfig:
    """从已有节能率提取数据 + 用户输入构建PlantConfig"""
    config = PlantConfig()

    # 从用户输入获取主机信息
    chiller_groups = user_inputs.get("chiller_groups", [])
    for cg in chiller_groups:
        config.chillers.append(ChillerGroup(
            name=cg.get("name", "主机"),
            qty=cg.get("qty", 1),
            capacity_kw=cg.get("capacity_kw", 5000),
            rated_power_kw=cg.get("rated_power_kw", 800),
            rated_cop=cg.get("rated_cop", 6.0),
            variable_freq=cg.get("variable_freq", False),
            cop_curve=cg.get("cop_curve"),
        ))

    # 水泵
    for pg in user_inputs.get("chw_pumps", []):
        config.chw_pumps.append(PumpGroup(
            name=pg.get("name", "冷冻泵"),
            qty=pg.get("qty", 1),
            power_kw=pg.get("power_kw", 100),
            flow_m3h=pg.get("flow_m3h", 500),
            variable_freq=pg.get("variable_freq", True),
        ))
    for pg in user_inputs.get("cw_pumps", []):
        config.cw_pumps.append(PumpGroup(
            name=pg.get("name", "冷却泵"),
            qty=pg.get("qty", 1),
            power_kw=pg.get("power_kw", 100),
            flow_m3h=pg.get("flow_m3h", 800),
            variable_freq=pg.get("variable_freq", False),
        ))

    # 冷却塔
    for tg in user_inputs.get("towers", []):
        config.towers.append(TowerGroup(
            name=tg.get("name", "冷却塔"),
            qty=tg.get("qty", 1),
            fan_power_kw=tg.get("fan_power_kw", 22),
            fans_per_tower=tg.get("fans_per_tower", 2),
            variable_freq=tg.get("variable_freq", True),
        ))

    # 月度运行参数 - 优先从ac_extracted_data获取
    monthly_data = ac_data.get("monthly_data", {}) if ac_data else {}

    if monthly_data:
        for m in range(12):
            m_key = str(m + 1)
            m_data = monthly_data.get(m_key, {})
            if "freezing_pump_freq" in m_data and m_data["freezing_pump_freq"]:
                config.monthly_chw_pump_hz[m] = float(m_data["freezing_pump_freq"])
            if "cooling_pump_freq" in m_data and m_data["cooling_pump_freq"]:
                config.monthly_cw_pump_hz[m] = float(m_data["cooling_pump_freq"])
            if "cooling_tower_freq" in m_data and m_data.get("cooling_tower_freq"):
                config.monthly_tower_hz[m] = float(m_data["cooling_tower_freq"])
            if "freezing_water_temp_diff" in m_data and m_data["freezing_water_temp_diff"]:
                config.monthly_chw_dt[m] = float(m_data["freezing_water_temp_diff"])
            if "cooling_water_temp_diff" in m_data and m_data["cooling_water_temp_diff"]:
                config.monthly_cw_dt[m] = float(m_data["cooling_water_temp_diff"])
            if "chiller_supply_temp" in m_data and m_data["chiller_supply_temp"]:
                config.monthly_chw_supply_temp[m] = float(m_data["chiller_supply_temp"])

    # 用户覆盖
    if "monthly_chiller_count" in user_inputs:
        config.monthly_chiller_count = user_inputs["monthly_chiller_count"]
    if "monthly_load_factors" in user_inputs and len(user_inputs["monthly_load_factors"]) == 12:
        config.monthly_load_factor = user_inputs["monthly_load_factors"]
    if "base_load_ratio" in user_inputs:
        config.base_load_ratio = user_inputs["base_load_ratio"]
    # 工作日/休息日双曲线 + 日历（来自 AI 推荐模块）
    if "workday_hourly_curve" in user_inputs and len(user_inputs["workday_hourly_curve"]) == 24:
        config.workday_hourly_curve = user_inputs["workday_hourly_curve"]
    if "offday_hourly_curve" in user_inputs and len(user_inputs["offday_hourly_curve"]) == 24:
        config.offday_hourly_curve = user_inputs["offday_hourly_curve"]
    if "day_type" in user_inputs and len(user_inputs["day_type"]) == 365:
        config.day_type = user_inputs["day_type"]

    return config
