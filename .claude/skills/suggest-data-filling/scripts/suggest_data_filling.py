#!/usr/bin/env python3
"""
数据填充建议脚本
分析数据质量报告,为缺失数据提供智能填充建议
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class DataFillingSuggester:
    """数据填充建议生成器"""

    # 季节划分 (月份 -> 季节代表月)
    SEASONS = {
        1: 1, 2: 1, 3: 1,      # 冬季 -> 1月
        4: 5, 5: 5,             # 春季 -> 5月
        6: 7, 7: 7, 8: 7,       # 夏季 -> 7月
        9: 10, 10: 10,          # 秋季 -> 10月
        11: 1, 12: 1            # 冬季 -> 1月
    }

    # 行业默认值
    INDUSTRY_DEFAULTS = {
        'chiller_supply_temp': {
            'winter': 7,    # 冬季(11-3月)
            'spring': 8,    # 春秋(4-5, 9-10月)
            'summer': 9     # 夏季(6-8月)
        },
        'cooling_tower_outlet_temp': {
            'winter': 20,
            'spring': 26,
            'summer': 32
        },
        'cooling_pump_freq': 45,
        'freezing_pump_freq': 50,
        'cooling_water_temp_diff': 4.0,    # 修改：3-5范围的中间值
        'freezing_water_temp_diff': 4.0   # 修改：3-5范围的中间值
    }

    def __init__(self, data: Dict[str, Any], quality_report: Dict[str, Any]):
        self.data = data
        self.quality_report = quality_report
        self.monthly_data = data.get('monthly_data', [])
        self.suggestions = []
        self.unfillable_fields = []

    def get_season(self, month: int) -> str:
        """获取月份对应的季节"""
        if month in [11, 12, 1, 2, 3]:
            return 'winter'
        elif month in [6, 7, 8]:
            return 'summer'
        else:
            return 'spring'

    def get_field_name(self, field: str) -> str:
        """获取字段中文名称"""
        field_names = {
            'total_energy': '冷站总能耗',
            'chiller_supply_temp': '冷机供水温度',
            'cooling_pump_freq': '冷却泵频率',
            'freezing_pump_freq': '冷冻泵频率',
            'cooling_water_temp_diff': '冷却水温差',
            'freezing_water_temp_diff': '冷冻水温差',
            'cooling_tower_outlet_temp': '冷却塔出水温度'
        }
        return field_names.get(field, field)

    def check_unfillable_fields(self) -> bool:
        """检查不可填充字段"""
        # 检查 project_region
        if not self.data.get('project_region'):
            self.unfillable_fields.append({
                'field': 'project_region',
                'reason': '项目地区是必填项,无法通过算法推断,必须用户补充'
            })

        # 检查 total_energy 数据量
        valid_energy_count = sum(
            1 for month_data in self.monthly_data
            if month_data.get('total_energy') is not None
        )
        if valid_energy_count < 6:
            self.unfillable_fields.append({
                'field': 'total_energy',
                'reason': f'仅有{valid_energy_count}个月的能耗数据,不足以推断全年,建议至少提供6个月数据'
            })

        # 检查 cooling_water_temp_diff 数据量
        valid_cooling_diff_count = sum(
            1 for month_data in self.monthly_data
            if month_data.get('cooling_water_temp_diff') is not None
        )
        if valid_cooling_diff_count < 6:
            self.unfillable_fields.append({
                'field': 'cooling_water_temp_diff',
                'reason': f'仅有{valid_cooling_diff_count}个月的冷却水温差数据,不足以推断全年,建议至少提供6个月数据'
            })

        # 检查 freezing_water_temp_diff 数据量
        valid_freezing_diff_count = sum(
            1 for month_data in self.monthly_data
            if month_data.get('freezing_water_temp_diff') is not None
        )
        if valid_freezing_diff_count < 6:
            self.unfillable_fields.append({
                'field': 'freezing_water_temp_diff',
                'reason': f'仅有{valid_freezing_diff_count}个月的冷冻水温差数据,不足以推断全年,建议至少提供6个月数据'
            })

        return len(self.unfillable_fields) > 0

    def get_missing_fields(self) -> List[Tuple[int, str]]:
        """从质量报告中提取缺失字段"""
        missing_fields = []
        for issue in self.quality_report.get('issues', []):
            if issue.get('type') == 'missing':
                field = issue.get('field', '')
                # 解析字段路径,如 "monthly_data[3].chiller_supply_temp"
                if 'monthly_data' in field and '.' in field:
                    parts = field.split('.')
                    month_part = parts[0]  # "monthly_data[3]"
                    field_name = parts[1]  # "chiller_supply_temp"

                    # 提取月份索引
                    month_idx = int(month_part.split('[')[1].split(']')[0])
                    missing_fields.append((month_idx, field_name))

        return missing_fields

    def try_linear_interpolation(self, month_idx: int, field: str) -> Optional[Dict[str, Any]]:
        """尝试线性插值"""
        month = month_idx + 1

        # 查找前后有数据的月份
        before_value = None
        before_month = None
        for i in range(month_idx - 1, -1, -1):
            val = self.monthly_data[i].get(field)
            if val is not None:
                before_value = val
                before_month = i + 1
                break

        after_value = None
        after_month = None
        for i in range(month_idx + 1, len(self.monthly_data)):
            val = self.monthly_data[i].get(field)
            if val is not None:
                after_value = val
                after_month = i + 1
                break

        # 如果前后都有数据,且距离不太远(≤2个月),使用线性插值
        if before_value is not None and after_value is not None:
            if after_month - before_month <= 3:
                # 计算插值
                total_distance = after_month - before_month
                month_distance = month - before_month
                suggested_value = before_value + (after_value - before_value) * (month_distance / total_distance)

                # 根据字段类型决定精度
                if 'temp' in field:
                    suggested_value = round(suggested_value, 1)
                elif 'freq' in field:
                    suggested_value = round(suggested_value)
                else:
                    suggested_value = round(suggested_value, 2)

                return {
                    'field': f'monthly_data[{month_idx}].{field}',
                    'original_value': None,
                    'suggested_value': suggested_value,
                    'method': 'linear_interpolation',
                    'confidence': 'high',
                    'reasoning': f'基于{before_month}月({before_value})和{after_month}月({after_value})的线性插值'
                }

        return None

    def try_season_default(self, month_idx: int, field: str) -> Optional[Dict[str, Any]]:
        """尝试使用季节代表值"""
        month = month_idx + 1
        season_rep_month = self.SEASONS[month]

        # 查找季节代表月的数据
        for i, month_data in enumerate(self.monthly_data):
            if month_data.get('month') == season_rep_month:
                value = month_data.get(field)
                if value is not None:
                    return {
                        'field': f'monthly_data[{month_idx}].{field}',
                        'original_value': None,
                        'suggested_value': value,
                        'method': 'season_default',
                        'confidence': 'medium',
                        'reasoning': f'使用同季节代表月{season_rep_month}月的数据({value})'
                    }

        return None

    def try_adjacent_average(self, month_idx: int, field: str) -> Optional[Dict[str, Any]]:
        """尝试使用相邻月份均值"""
        # 查找前后有数据的月份
        before_value = None
        before_month = None
        for i in range(month_idx - 1, -1, -1):
            val = self.monthly_data[i].get(field)
            if val is not None:
                before_value = val
                before_month = i + 1
                break

        after_value = None
        after_month = None
        for i in range(month_idx + 1, len(self.monthly_data)):
            val = self.monthly_data[i].get(field)
            if val is not None:
                after_value = val
                after_month = i + 1
                break

        # 如果前后都有数据,使用均值
        if before_value is not None and after_value is not None:
            avg_value = (before_value + after_value) / 2

            # 根据字段类型决定精度
            if 'temp' in field:
                avg_value = round(avg_value, 1)
            elif 'freq' in field:
                avg_value = round(avg_value)
            else:
                avg_value = round(avg_value, 2)

            return {
                'field': f'monthly_data[{month_idx}].{field}',
                'original_value': None,
                'suggested_value': avg_value,
                'method': 'adjacent_average',
                'confidence': 'medium',
                'reasoning': f'使用相邻月份{before_month}月({before_value})和{after_month}月({after_value})的均值'
            }

        return None

    def use_industry_default(self, month_idx: int, field: str) -> Dict[str, Any]:
        """使用行业默认值"""
        month = month_idx + 1
        season = self.get_season(month)

        # 获取默认值
        if field in ['chiller_supply_temp', 'cooling_tower_outlet_temp']:
            default_value = self.INDUSTRY_DEFAULTS[field][season]
        else:
            default_value = self.INDUSTRY_DEFAULTS.get(field, 0)

        season_name = {'winter': '冬季', 'spring': '春秋季', 'summer': '夏季'}[season]

        return {
            'field': f'monthly_data[{month_idx}].{field}',
            'original_value': None,
            'suggested_value': default_value,
            'method': 'industry_default',
            'confidence': 'low',
            'reasoning': f'该参数缺少足够数据支撑,使用{season_name}行业默认值({default_value})'
        }

    def suggest_filling(self, month_idx: int, field: str) -> Dict[str, Any]:
        """为单个缺失字段生成填充建议"""
        # 跳过不可填充的字段
        if field == 'total_energy':
            # total_energy 在 check_unfillable_fields 中已处理
            return None

        # 策略1: 线性插值
        suggestion = self.try_linear_interpolation(month_idx, field)
        if suggestion:
            return suggestion

        # 策略2: 季节代表值
        suggestion = self.try_season_default(month_idx, field)
        if suggestion:
            return suggestion

        # 策略3: 相邻月份均值
        suggestion = self.try_adjacent_average(month_idx, field)
        if suggestion:
            return suggestion

        # 策略4: 行业默认值
        return self.use_industry_default(month_idx, field)

    def run(self) -> Dict[str, Any]:
        """执行填充建议生成

        Returns:
            Dict[str, Any]: 填充建议结果，包含以下字段：
                - can_proceed (bool): 是否可以继续计算
                    - True: 所有缺失字段都可以通过算法填充
                    - False: 存在关键字段无法填充，需要用户补充数据
                - unfillable_fields (List[Dict]): 不可填充字段列表
                    - field (str): 字段路径
                    - reason (str): 不可填充的原因说明
                - fillable_suggestions (List[Dict]): 可填充建议列表
                    - field (str): 字段路径 (格式: "monthly_data[索引].字段名")
                    - original_value: 原始值 (通常为 null)
                    - suggested_value: 建议填充值
                    - method (str): 填充方法 (linear_interpolation/season_default/adjacent_average/industry_default)
                    - confidence (str): 置信度 (high/medium/low)
                    - reasoning (str): 推理说明

        输出格式详见: .claude/skills/suggest-data-filling/SKILL.md
        """
        # 检查不可填充字段
        has_unfillable = self.check_unfillable_fields()

        if has_unfillable:
            return {
                'can_proceed': False,
                'unfillable_fields': self.unfillable_fields,
                'fillable_suggestions': []
            }

        # 获取所有缺失字段
        missing_fields = self.get_missing_fields()

        # 为每个缺失字段生成建议
        for month_idx, field in missing_fields:
            suggestion = self.suggest_filling(month_idx, field)
            if suggestion:
                self.suggestions.append(suggestion)

        return {
            'can_proceed': True,
            'unfillable_fields': [],
            'fillable_suggestions': self.suggestions
        }


def main():
    """主函数"""
    if len(sys.argv) != 4:
        print('用法: python suggest_data_filling.py <extracted_json_path> <quality_report_path> <output_json_path>')
        sys.exit(1)

    extracted_json_path = Path(sys.argv[1])
    quality_report_path = Path(sys.argv[2])
    output_json_path = Path(sys.argv[3])

    # 检查输入文件是否存在
    if not extracted_json_path.exists():
        print(f'错误: 输入文件不存在: {extracted_json_path}')
        sys.exit(1)

    if not quality_report_path.exists():
        print(f'错误: 质量报告文件不存在: {quality_report_path}')
        sys.exit(1)

    # 读取输入数据
    try:
        with open(extracted_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open(quality_report_path, 'r', encoding='utf-8') as f:
            quality_report = json.load(f)
    except json.JSONDecodeError as e:
        print(f'错误: JSON 解析失败: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'错误: 读取文件失败: {e}')
        sys.exit(1)

    # 执行填充建议
    suggester = DataFillingSuggester(data, quality_report)
    result = suggester.run()

    # 输出结果
    try:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f'✅ 填充建议已生成: {output_json_path}')

        if result['can_proceed']:
            print(f'\n可以继续处理,共生成 {len(result["fillable_suggestions"])} 条填充建议')
        else:
            print(f'\n⚠️  发现 {len(result["unfillable_fields"])} 个不可填充字段,需要用户补充:')
            for field in result['unfillable_fields']:
                print(f'  - {field["field"]}: {field["reason"]}')
    except Exception as e:
        print(f'错误: 写入输出文件失败: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()