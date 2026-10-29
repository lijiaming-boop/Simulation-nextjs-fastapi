#!/usr/bin/env python3
"""
数据质量检查脚本
检查从调研表提取的数据的完整性和合理性,输出质量报告
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')


class DataQualityChecker:
    """数据质量检查器"""

    # 数值范围定义
    RANGES = {
        'chiller_supply_temp': (5, 15, '°C'),
        'cooling_pump_freq': (20, 50, 'Hz'),
        'freezing_pump_freq': (20, 50, 'Hz'),
        'cooling_water_temp_diff': (2, 8, '℃'),
        'freezing_water_temp_diff': (2, 8, '℃'),
        'cooling_tower_outlet_temp': (15, 40, '°C'),
    }

    # 字段列表(用于计算完整率)
    MONTHLY_FIELDS = [
        'total_energy',
        'chiller_supply_temp',
        'cooling_pump_freq',
        'freezing_pump_freq',
        'cooling_water_temp_diff',
        'freezing_water_temp_diff',
        'cooling_tower_outlet_temp'
    ]

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.issues: List[Dict[str, str]] = []

    def check_project_region(self) -> None:
        """检查项目地区是否缺失"""
        if not self.data.get('project_region'):
            self.issues.append({
                'field': 'project_region',
                'severity': 'critical',
                'type': 'missing',
                'message': '项目地区缺失,无法匹配气象数据'
            })

    def check_monthly_data(self) -> None:
        """检查月度数据"""
        monthly_data = self.data.get('monthly_data', [])

        for idx, month_data in enumerate(monthly_data):
            month = month_data.get('month', idx + 1)

            # 检查 total_energy
            self._check_total_energy(month, month_data)

            # 检查 chiller_supply_temp
            self._check_chiller_supply_temp(month, month_data)

            # 检查其他字段
            for field in self.MONTHLY_FIELDS[2:]:  # 跳过已检查的前两个
                self._check_field(month, month_data, field)

    def _check_total_energy(self, month: int, data: Dict) -> None:
        """检查总能耗"""
        value = data.get('total_energy')

        if value is None:
            self.issues.append({
                'field': f'monthly_data[{month-1}].total_energy',
                'severity': 'high',
                'type': 'missing',
                'message': f'{month}月冷站总能耗缺失'
            })
        elif value <= 0:
            self.issues.append({
                'field': f'monthly_data[{month-1}].total_energy',
                'severity': 'critical',
                'type': 'logic_error',
                'message': f'{month}月能耗数据异常(值为{value})'
            })

    def _check_chiller_supply_temp(self, month: int, data: Dict) -> None:
        """检查冷机供水温度"""
        value = data.get('chiller_supply_temp')

        if value is None:
            self.issues.append({
                'field': f'monthly_data[{month-1}].chiller_supply_temp',
                'severity': 'high',
                'type': 'missing',
                'message': f'{month}月冷机供水温度缺失'
            })
        elif not (5 <= value <= 15):
            self.issues.append({
                'field': f'monthly_data[{month-1}].chiller_supply_temp',
                'severity': 'medium',
                'type': 'out_of_range',
                'message': f'{month}月冷机供水温度({value}°C)超出合理范围(5-15°C)'
            })

    def _check_field(self, month: int, data: Dict, field: str) -> None:
        """通用字段检查"""
        value = data.get(field)

        if value is None:
            severity = 'high' if 'temp_diff' in field else 'medium'
            self.issues.append({
                'field': f'monthly_data[{month-1}].{field}',
                'severity': severity,
                'type': 'missing',
                'message': f'{month}月{self._get_field_name(field)}缺失'
            })
        elif field in self.RANGES:
            min_val, max_val, unit = self.RANGES[field]
            if not (min_val <= value <= max_val):
                self.issues.append({
                    'field': f'monthly_data[{month-1}].{field}',
                    'severity': 'medium',
                    'type': 'out_of_range',
                    'message': f'{month}月{self._get_field_name(field)}({value}{unit})超出合理范围({min_val}-{max_val}{unit})'
                })

            # 检查温差是否为负
            if 'temp_diff' in field and value < 0:
                self.issues.append({
                    'field': f'monthly_data[{month-1}].{field}',
                    'severity': 'high',
                    'type': 'logic_error',
                    'message': f'{month}月供回水温差不能为负值(当前值:{value})'
                })

            # 检查频率是否超过工频
            if 'freq' in field and value > 50:
                self.issues.append({
                    'field': f'monthly_data[{month-1}].{field}',
                    'severity': 'high',
                    'type': 'logic_error',
                    'message': f'{month}月频率超过工频上限(当前值:{value}Hz)'
                })

    def _get_field_name(self, field: str) -> str:
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

    def calculate_completeness(self) -> float:
        """计算数据完整率"""
        monthly_data = self.data.get('monthly_data', [])
        if not monthly_data:
            return 0.0

        total_points = len(monthly_data) * len(self.MONTHLY_FIELDS)
        non_null_points = 0

        for month_data in monthly_data:
            for field in self.MONTHLY_FIELDS:
                if month_data.get(field) is not None:
                    non_null_points += 1

        return non_null_points / total_points if total_points > 0 else 0.0

    def get_confidence_level(self, completeness: float) -> str:
        """根据完整率判断置信度"""
        if completeness >= 0.8:
            return 'high'
        elif completeness >= 0.5:
            return 'medium'
        else:
            return 'low'

    def sort_issues(self) -> None:
        """按严重程度排序问题"""
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        self.issues.sort(key=lambda x: severity_order.get(x['severity'], 99))

    def generate_summary(self, completeness: float) -> str:
        """生成总结说明"""
        percentage = int(completeness * 100)

        # 统计各级别问题数量
        critical_count = sum(1 for i in self.issues if i['severity'] == 'critical')
        high_count = sum(1 for i in self.issues if i['severity'] == 'high')
        medium_count = sum(1 for i in self.issues if i['severity'] == 'medium')

        if not self.issues:
            return f'数据完整率{percentage}%,未发现数据质量问题。'

        problem_desc = []
        if critical_count > 0:
            problem_desc.append(f'{critical_count}个严重问题')
        if high_count > 0:
            problem_desc.append(f'{high_count}个高优先级问题')
        if medium_count > 0:
            problem_desc.append(f'{medium_count}个中等问题')

        problem_str = '、'.join(problem_desc)

        if completeness < 0.8:
            return f'数据完整率{percentage}%,建议补充缺失月份数据。发现{problem_str}。'
        else:
            return f'数据完整率{percentage}%。发现{problem_str}。'

    def run(self) -> Dict[str, Any]:
        """执行检查并返回报告"""
        # 执行所有检查
        self.check_project_region()
        self.check_monthly_data()

        # 计算完整率
        completeness = self.calculate_completeness()
        confidence_level = self.get_confidence_level(completeness)

        # 排序问题
        self.sort_issues()

        # 生成总结
        summary = self.generate_summary(completeness)

        return {
            'completeness': round(completeness, 2),
            'confidence_level': confidence_level,
            'issues': self.issues,
            'summary': summary
        }


def main():
    """主函数"""
    if len(sys.argv) != 3:
        print('用法: python check_data_quality.py <extracted_json_path> <output_json_path>')
        sys.exit(1)

    extracted_json_path = Path(sys.argv[1])
    output_json_path = Path(sys.argv[2])

    # 检查输入文件是否存在
    if not extracted_json_path.exists():
        print(f'错误: 输入文件不存在: {extracted_json_path}')
        sys.exit(1)

    # 读取输入数据
    try:
        with open(extracted_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f'错误: JSON 解析失败: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'错误: 读取文件失败: {e}')
        sys.exit(1)

    # 执行检查
    checker = DataQualityChecker(data)
    report = checker.run()

    # 输出报告
    try:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f' 质量报告已生成: {output_json_path}')
        print(f'\n{report["summary"]}')
    except Exception as e:
        print(f'错误: 写入输出文件失败: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
