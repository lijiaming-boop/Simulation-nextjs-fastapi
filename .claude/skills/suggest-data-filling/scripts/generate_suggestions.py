#!/usr/bin/env python3
"""
数据填充建议生成器

基于季节模式和插值法生成冷站运行数据填充建议
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any


# 季节分组
SEASON_GROUPS = {
    "winter": [12, 1, 2],      # 冬季:12,1,2月
    "spring": [3, 4, 5],       # 春季:3,4,5月
    "summer": [6, 7, 8],       # 夏季:6,7,8月
    "autumn": [9, 10, 11]      # 秋季:9,10,11月
}

# 各季节代表月(用于填充)
SEASON_REPRESENTATIVE_MONTHS = {
    "winter": 1,    # 用1月数据填充冬季
    "spring": 5,    # 用5月数据填充春季(或用1月和7月插值)
    "summer": 7,    # 用7月数据填充夏季
    "autumn": 10    # 用10月数据填充秋季
}

# 各参数的典型范围
TYPICAL_RANGES = {
    "chiller_supply_temp": (5.0, 12.0),       # 冷机供水温度:5-12℃
    "cooling_pump_freq": (30.0, 50.0),        # 冷却泵频率:30-50Hz
    "freezing_pump_freq": (30.0, 50.0),       # 冷冻泵频率:30-50Hz
    "cooling_water_temp_diff": (3.0, 6.0),    # 冷却水温差:3-6℃
    "freezing_water_temp_diff": (3.0, 6.0),   # 冷冻水温差:3-6℃
    "cooling_tower_outlet_temp": (24.0, 32.0) # 冷却塔出水温度:24-32℃
}

# 能耗的季节系数(相对于7月的比例)
ENERGY_SEASONAL_FACTORS = {
    1: 0.4,   # 1月:冬季最低
    2: 0.5,   # 2月:冬季
    3: 0.7,   # 3月:春季开始
    4: 0.8,   # 4月:春季
    5: 0.9,   # 5月:春末夏初
    6: 1.0,   # 6月:夏季开始
    7: 1.0,   # 7月:夏季高峰(基准)
    8: 1.0,   # 8月:夏季高峰
    9: 0.9,   # 9月:秋季开始
    10: 0.8,  # 10月:秋季
    11: 0.6,  # 11月:秋末冬初
    12: 0.5   # 12月:冬季
}


def load_json(filepath: str) -> Dict:
    """加载JSON文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data: Dict, filepath: str) -> None:
    """保存JSON文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_season(month: int) -> str:
    """获取月份所属季节"""
    for season, months in SEASON_GROUPS.items():
        if month in months:
            return season
    raise ValueError(f"Invalid month: {month}")


def find_available_values_for_field(
    monthly_data: List[Dict],
    field: str,
    target_month: int
) -> Optional[List[float]]:
    """
    为指定字段和月份查找可用的数值用于插值

    返回: [(month, value), ...] 或 None
    """
    available = []

    # 首先找同季节的数据
    target_season = get_season(target_month)
    season_months = SEASON_GROUPS[target_season]

    for data in monthly_data:
        month = data["month"]
        value = data.get(field)

        if value is not None and isinstance(value, (int, float)):
            available.append((month, value))

    if not available:
        return None

    # 按月份排序
    available.sort(key=lambda x: x[0])
    return available


def interpolate_value(
    available_data: List[tuple],
    target_month: int
) -> float:
    """
    基于可用数据进行线性插值

    available_data: [(month, value), ...]
    target_month: 目标月份
    """
    if not available_data:
        raise ValueError("No available data for interpolation")

    # 如果只有一个数据点,直接返回
    if len(available_data) == 1:
        return available_data[0][1]

    # 找到目标月份前后的最近数据点
    before = None
    after = None

    for month, value in available_data:
        if month < target_month:
            before = (month, value)
        elif month > target_month:
            after = (month, value)
            break

    # 如果只有前序数据,用最近的
    if before and not after:
        return before[1]

    # 如果只有后续数据,用最近的
    if after and not before:
        return after[1]

    # 线性插值
    if before and after:
        month1, val1 = before
        month2, val2 = after

        ratio = (target_month - month1) / (month2 - month1)
        return val1 + (val2 - val1) * ratio

    # 不应该到这里
    return available_data[-1][1]


def get_typical_value(field: str) -> float:
    """获取字段的典型值(范围的中值)"""
    if field in TYPICAL_RANGES:
        min_val, max_val = TYPICAL_RANGES[field]
        return (min_val + max_val) / 2
    return 0.0


def estimate_energy_from_params(monthly_data: List[Dict]) -> Dict[int, float]:
    """
    根据运行参数估算能耗

    简化的能耗模型:
    - 基准能耗(根据季节)
    - 泵频率影响: 能耗 ∝ 频率^2.5
    - 温度影响: 供水温度每升高1℃,能耗约降低4%
    """
    energy_estimates = {}

    for data in monthly_data:
        month = data["month"]

        # 基准能耗(假设7月为100000 kWh)
        base_energy = 100000 * ENERGY_SEASONAL_FACTORS.get(month, 0.7)

        # 如果有泵频率数据,调整
        pump_freq = data.get("cooling_pump_freq") or data.get("freezing_pump_freq")
        if pump_freq:
            # 假设基准频率为45Hz
            freq_factor = (pump_freq / 45.0) ** 2.5
            base_energy *= freq_factor

        # 如果有供水温度,调整
        supply_temp = data.get("chiller_supply_temp")
        if supply_temp:
            # 假设基准温度为7℃,每升高1℃节能4%
            temp_factor = 1.0 - (supply_temp - 7.0) * 0.04
            base_energy *= temp_factor

        energy_estimates[month] = round(base_energy, 2)

    return energy_estimates


def generate_suggestions(
    extracted_data: Dict,
    quality_report: Dict
) -> Dict:
    """
    生成填充建议

    策略:
    1. 对于项目地区:
       - 优先从extracted_data中读取project_region字段
       - 如果没有,则需要用户手动输入

    2. 对于能耗数据:
       - 如果有运行参数,基于参数估算
       - 如果没有,使用季节系数推算

    3. 对于运行参数(温度、频率、温差):
       - 优先使用同季节代表月的数据
       - 如果没有,使用线性插值
       - 如果完全没有,使用典型值
    """
    # 提取项目地区
    project_region = extracted_data.get("project_region")

    if project_region:
        region_suggestion = {
            "suggested_value": project_region,
            "method": "auto_extracted",
            "confidence": "high",
            "reason": "从调研表中自动提取的项目地区"
        }
    else:
        region_suggestion = {
            "suggested_value": None,
            "method": "manual_input",
            "confidence": "none",
            "reason": "需要用户输入项目所在地区"
        }

    suggestions = {
        "project_region": region_suggestion,
        "monthly_suggestions": []
    }

    monthly_data = extracted_data.get("monthly_data", [])

    # 确保有12个月的数据，补齐缺失的月份
    while len(monthly_data) < 12:
        monthly_data.append({"month": len(monthly_data) + 1})

    # 先估算能耗(如果有的话)
    energy_estimates = estimate_energy_from_params(monthly_data)

    # 为每个月生成建议
    for month_idx in range(12):
        month = month_idx + 1
        month_data = monthly_data[month_idx]

        month_suggestion = {
            "month": month,
            "fields": {}
        }

        # 处理能耗字段
        if month_data.get("total_energy") is None:
            suggested_energy = energy_estimates.get(month)

            if suggested_energy:
                month_suggestion["fields"]["total_energy"] = {
                    "suggested_value": suggested_energy,
                    "method": "param_based_estimation" if month_data.get("cooling_pump_freq") else "seasonal_pattern",
                    "confidence": "medium" if month_data.get("cooling_pump_freq") else "low",
                    "reason": f"基于{'运行参数' if month_data.get('cooling_pump_freq') else '季节模式'}估算"
                }
            else:
                # 使用季节系数(需要基准值)
                month_suggestion["fields"]["total_energy"] = {
                    "suggested_value": None,
                    "method": "requires_base_value",
                    "confidence": "none",
                    "reason": "需要至少一个月份的能耗数据作为基准"
                }

        # 处理运行参数字段
        param_fields = [
            "chiller_supply_temp",
            "cooling_pump_freq",
            "freezing_pump_freq",
            "cooling_water_temp_diff",
            "freezing_water_temp_diff",
            "cooling_tower_outlet_temp"
        ]

        for field in param_fields:
            if month_data.get(field) is None:
                # 查找可用数据
                available = find_available_values_for_field(monthly_data, field, month)

                if available:
                    # 使用插值
                    suggested_value = interpolate_value(available, month)

                    month_suggestion["fields"][field] = {
                        "suggested_value": round(suggested_value, 2),
                        "method": "interpolation",
                        "confidence": "high" if len(available) >= 2 else "medium",
                        "reason": f"基于可用数据线性插值(数据点: {len(available)}个)"
                    }
                else:
                    # 使用典型值
                    typical_value = get_typical_value(field)

                    month_suggestion["fields"][field] = {
                        "suggested_value": round(typical_value, 2),
                        "method": "typical_value",
                        "confidence": "low",
                        "reason": f"使用{field}的典型范围中值(无可用历史数据)"
                    }

        suggestions["monthly_suggestions"].append(month_suggestion)

    return suggestions


def main():
    """主函数"""
    # 文件路径
    base_dir = Path("/home/zack/lingzhi_apps/conditioner_saving")
    extracted_data_path = base_dir / "tmp" / "extracted_data.json"
    quality_report_path = base_dir / "tmp" / "quality_report.json"
    output_path = base_dir / "tmp" / "filling_suggestions.json"

    # 加载数据
    print("正在加载提取的数据...")
    extracted_data = load_json(extracted_data_path)
    print("正在加载质量报告...")
    quality_report = load_json(quality_report_path)

    # 生成建议
    print("正在生成填充建议...")
    suggestions = generate_suggestions(extracted_data, quality_report)

    # 保存结果
    save_json(suggestions, output_path)
    print(f" 填充建议已保存到: {output_path}")

    # 输出统计信息
    total_fields = 0
    high_confidence = 0
    medium_confidence = 0
    low_confidence = 0

    for month_sugg in suggestions["monthly_suggestions"]:
        for field_sugg in month_sugg["fields"].values():
            total_fields += 1
            conf = field_sugg.get("confidence", "none")
            if conf == "high":
                high_confidence += 1
            elif conf == "medium":
                medium_confidence += 1
            elif conf == "low":
                low_confidence += 1

    print(f"\n建议统计:")
    print(f"  总字段数: {total_fields}")
    print(f"  高置信度: {high_confidence}")
    print(f"  中置信度: {medium_confidence}")
    print(f"  低置信度: {low_confidence}")


if __name__ == "__main__":
    main()
