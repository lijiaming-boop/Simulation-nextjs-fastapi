#!/usr/bin/env python3
"""
从中央空调节能调研表中提取月度运行数据并进行质量检查
合并了 extract-survey-data 和 check-data-quality 的功能
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import pandas as pd
except ImportError:
    print("错误: 需要安装 pandas 库")
    print("请运行: pip install pandas")
    sys.exit(1)


# ============= 数据提取部分 (来自 extract_survey_data.py) =============

def parse_value(value):
    """解析文本值为数值"""
    if pd.isna(value):
        return None

    value_str = str(value).strip()

    if not value_str or value_str.lower() in ['nan', 'none', '无', '/']:
        return None

    try:
        return float(value_str)
    except ValueError:
        pass

    # 处理范围格式
    range_match = re.search(r'(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)', value_str)
    if range_match:
        start = float(range_match.group(1))
        end = float(range_match.group(2))
        return (start + end) / 2

    # 处理频率格式
    freq_match = re.search(r'(\d+\.?\d*)\s*(?:Hz|HZ|hz)', value_str)
    if freq_match:
        return float(freq_match.group(1))

    # 处理温度格式
    temp_match = re.search(r'(\d+\.?\d*)\s*(?:℃|°C|C)', value_str)
    if temp_match:
        return float(temp_match.group(1))

    # 提取第一个数字
    number_match = re.search(r'(\d+\.?\d*)', value_str)
    if number_match:
        return float(number_match.group(1))

    return None


def extract_region(df):
    """从项目总体情况表中提取地区信息"""
    for idx, row in df.iterrows():
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val)
            regions = {
                '华南': ['广东', '广西', '海南', '福建', '深圳', '广州', '厦门'],
                '华东': ['上海', '江苏', '浙江', '安徽', '江西', '南京', '杭州'],
                '华中': ['湖北', '湖南', '河南', '武汉', '长沙'],
                '西南': ['四川', '重庆', '贵州', '云南', '西藏', '成都'],
                '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆', '西安', '兰州'],
                '华北': ['北京', '天津', '河北', '山西', '内蒙古'],
                '东北': ['辽宁', '吉林', '黑龙江', '沈阳', '大连', '长春', '哈尔滨']
            }

            for region, keywords in regions.items():
                if any(keyword in val_str for keyword in keywords):
                    return region

    return None


def extract_station_name(df):
    """从冷站工作表中提取站房名称

    Args:
        df: 冷站工作表的 DataFrame

    Returns:
        站房名称字符串，如果未找到则返回 None
    """
    # 在前10行查找"站房名称"字段
    for idx in range(min(10, len(df))):
        row = df.iloc[idx]
        for col_idx, val in enumerate(row):
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if '站房名称' in val_str:
                # 站房名称的值通常在右侧第2列（跳过1列）
                if col_idx + 2 < len(row):
                    station_name = df.iloc[idx, col_idx + 2]
                    if pd.notna(station_name):
                        return str(station_name).strip()
                return None
    return None


def infer_region_from_text(text):
    """从文本（站房名称或文件名）推断项目地区

    Args:
        text: 文本字符串（站房名称、文件名等）

    Returns:
        地区字符串（华南/华东/华中/西南/西北/华北/东北），如果无法推断则返回 None
    """
    if not text or pd.isna(text):
        return None

    text_str = str(text)

    # 地区关键词映射（扩展了城市列表以提高识别率）
    regions = {
        '华南': ['广东', '广西', '海南', '福建', '深圳', '广州', '厦门', '珠海', '东莞', '佛山', '惠州', '中山', '江门', '湛江', '汕头'],
        '华东': ['上海', '江苏', '浙江', '安徽', '江西', '南京', '杭州', '苏州', '无锡', '宁波', '合肥', '南昌', '温州', '常州', '徐州'],
        '华中': ['湖北', '湖南', '河南', '武汉', '长沙', '郑州', '洛阳', '株洲', '岳阳'],
        '西南': ['四川', '重庆', '贵州', '云南', '西藏', '成都', '贵阳', '昆明', '拉萨'],
        '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆', '西安', '兰州', '银川', '乌鲁木齐', '西宁'],
        '华北': ['北京', '天津', '河北', '山西', '内蒙古', '石家庄', '太原', '呼和浩特', '唐山', '保定', '廊坊'],
        '东北': ['辽宁', '吉林', '黑龙江', '沈阳', '大连', '长春', '哈尔滨', '鞍山', '抚顺']
    }

    # 查找匹配的地区
    for region, keywords in regions.items():
        if any(keyword in text_str for keyword in keywords):
            return region

    return None


def extract_region_from_filename(filepath):
    """从文件名提取项目地区

    Args:
        filepath: 文件路径字符串

    Returns:
        地区字符串（华南/华东/华中/西南/西北/华北/东北），如果无法推断则返回 None
    """
    if not filepath:
        return None

    # 从完整路径中提取文件名（包括目录名，因为目录名可能也包含地区信息）
    return infer_region_from_text(filepath)


def find_row_by_keyword(df, keywords, start_row=0, end_row=None):
    """根据关键词查找行号"""
    if end_row is None:
        end_row = len(df)

    for idx in range(start_row, min(end_row, len(df))):
        row = df.iloc[idx]
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if any(keyword in val_str for keyword in keywords):
                return idx
    return None


def detect_month_column_start(df, row_idx):
    """检测指定行的月份列起始位置

    通过在该行查找 '1月' 关键字来确定月份数据的起始列。
    这样可以处理不同部分的列结构差异：
    - 设备运行规律：月份从D列开始（有备注列C）
    - 用电情况统计：月份从C列开始（无备注列）

    Args:
        df: DataFrame
        row_idx: 月份标题行的行号

    Returns:
        月份数据起始列索引（0-based），如果未找到则返回 None
    """
    if row_idx is None or row_idx >= len(df):
        return None

    # 在该行查找 '1月' 关键字
    row = df.iloc[row_idx]
    for col_idx in range(len(row)):
        cell_value = row.iloc[col_idx]
        if pd.notna(cell_value) and '1月' in str(cell_value):
            return col_idx

    return None


def extract_data_from_excel(survey_excel_path: str) -> Dict[str, Any]:
    """从 Excel 文件提取数据"""
    xls = pd.ExcelFile(survey_excel_path)

    # 读取冷站数据
    if '冷站' not in xls.sheet_names:
        return {
            "error": True,
            "message": "找不到'冷站'工作表,请确认上传了正确的文件"
        }

    df = pd.read_excel(xls, sheet_name='冷站', header=None)

    # 提取项目地区（三级优先级）
    project_region = None

    # 优先级1: 从站房名称推断地区
    station_name = extract_station_name(df)
    if station_name:
        project_region = infer_region_from_text(station_name)

    # 优先级2: 如果优先级1失败，从文件名推断地区
    if not project_region:
        project_region = extract_region_from_filename(survey_excel_path)

    # 优先级3: 如果优先级1和2都失败，从项目总体情况表提取
    if not project_region and '项目总体情况' in xls.sheet_names:
        df_overview = pd.read_excel(xls, sheet_name='项目总体情况', header=None)
        project_region = extract_region(df_overview)

    # 查找关键行
    row_mappings = {
        'chiller_supply_temp': ['冷机供水温度'],
        'cooling_pump_freq': ['冷却泵运行频率'],
        'cooling_water_temp_diff': ['冷却侧供回水温差'],
        'freezing_pump_freq': ['冷冻泵运行频率'],
        'freezing_water_temp_diff': ['冷冻侧供回水温差'],
        'cooling_tower_outlet_temp': ['冷却塔出水温度'],
        'total_energy': ['整个冷站', '万kWh']
    }

    # 从第30行开始查找设备运行规律部分的月份行
    equipment_month_row_idx = find_row_by_keyword(df, ['月份', '备注'], start_row=30, end_row=45)
    if equipment_month_row_idx is None:
        return {
            "error": True,
            "message": "未能识别调研表中的设备运行规律月度数据行,请确认上传了正确的文件"
        }

    # 检测设备运行规律部分的月份列起始位置
    equipment_col_start = detect_month_column_start(df, equipment_month_row_idx)
    if equipment_col_start is None:
        equipment_col_start = 3  # 默认 D 列

    # 查找用电情况统计部分的月份行（通常在设备运行规律之后）
    energy_month_row_idx = find_row_by_keyword(df, ['月份'], start_row=equipment_month_row_idx + 5, end_row=equipment_month_row_idx + 20)

    # 检测用电情况部分的月份列起始位置
    energy_col_start = None
    if energy_month_row_idx is not None:
        energy_col_start = detect_month_column_start(df, energy_month_row_idx)
    if energy_col_start is None:
        energy_col_start = 2  # 默认 C 列（用电情况通常从C列开始）

    # 查找各数据行
    data_rows = {}
    for key, keywords in row_mappings.items():
        # 设备运行规律字段：从设备运行规律部分开始查找
        if key != 'total_energy':
            row_idx = find_row_by_keyword(df, keywords, start_row=equipment_month_row_idx, end_row=equipment_month_row_idx + 15)
            if row_idx is not None:
                data_rows[key] = row_idx
        # 用电情况字段：从用电情况统计部分开始查找
        else:
            if energy_month_row_idx is not None:
                row_idx = find_row_by_keyword(df, keywords, start_row=energy_month_row_idx, end_row=energy_month_row_idx + 5)
                if row_idx is not None:
                    # 检查找到的行数据是否合理（万kWh应该<100）
                    # 如果第一个月份列的值>100，说明这是kWh单位的行，需要跳到下一行
                    if energy_col_start is not None and energy_col_start < len(df.columns):
                        first_month_val = df.iloc[row_idx, energy_col_start]
                        if pd.notna(first_month_val) and first_month_val > 100:
                            # 当前行是kWh，检查下一行
                            if row_idx + 1 < len(df):
                                next_row_val = df.iloc[row_idx + 1, energy_col_start]
                                if pd.notna(next_row_val) and next_row_val < 100:
                                    row_idx = row_idx + 1
                    data_rows[key] = row_idx
            # 兜底：使用硬编码行号
            if 'total_energy' not in data_rows and len(df) > 43:
                data_rows['total_energy'] = 43  # 修正：用电量通常在第44行（索引43）

    # 提取月度数据
    monthly_data = []
    valid_energy_count = 0

    for month in range(1, 13):
        month_record = {
            "month": month,
            "total_energy": None,
            "chiller_supply_temp": None,
            "cooling_pump_freq": None,
            "cooling_water_temp_diff": None,
            "freezing_pump_freq": None,
            "freezing_water_temp_diff": None,
            "cooling_tower_outlet_temp": None
        }

        for field in ['total_energy', 'chiller_supply_temp', 'cooling_pump_freq',
                     'cooling_water_temp_diff', 'freezing_pump_freq',
                     'freezing_water_temp_diff', 'cooling_tower_outlet_temp']:
            if field in data_rows:
                row_idx = data_rows[field]
                if row_idx < len(df):
                    # 根据字段类型使用不同的列起始位置
                    if field == 'total_energy':
                        # 用电情况：使用 energy_col_start
                        month_col_idx = energy_col_start + (month - 1)
                    else:
                        # 设备运行规律：使用 equipment_col_start
                        month_col_idx = equipment_col_start + (month - 1)

                    # 确保列索引在有效范围内
                    if month_col_idx < len(df.columns):
                        value = df.iloc[row_idx, month_col_idx]
                        parsed = parse_value(value)
                        month_record[field] = parsed
                        if field == 'total_energy' and parsed is not None:
                            valid_energy_count += 1

        monthly_data.append(month_record)

    # 注意：不再强制要求至少3个月数据，让质量检查报告来反馈数据完整性问题
    # 这样即使是空白模板也能返回提取结果和详细的质量报告

    return {
        "project_region": project_region,
        "monthly_data": monthly_data
    }


# ============= 数据质量检查部分 (来自 check_data_quality.py) =============

class DataQualityChecker:
    """数据质量检查器"""

    RANGES = {
        'chiller_supply_temp': (5, 15, '°C'),
        'cooling_pump_freq': (20, 50, 'Hz'),
        'freezing_pump_freq': (20, 50, 'Hz'),
        'cooling_water_temp_diff': (2, 8, '℃'),
        'freezing_water_temp_diff': (2, 8, '℃'),
        'cooling_tower_outlet_temp': (15, 40, '°C'),
    }

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
        """检查项目地区"""
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
            self._check_total_energy(month, month_data)
            self._check_chiller_supply_temp(month, month_data)

            for field in self.MONTHLY_FIELDS[2:]:
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
            self.issues.append({
                'field': f'monthly_data[{month-1}].{field}',
                'severity': 'medium',
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

            if 'temp_diff' in field and value < 0:
                self.issues.append({
                    'field': f'monthly_data[{month-1}].{field}',
                    'severity': 'high',
                    'type': 'logic_error',
                    'message': f'{month}月供回水温差不能为负值(当前值:{value})'
                })

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
        """按严重程度排序"""
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        self.issues.sort(key=lambda x: severity_order.get(x['severity'], 99))

    def generate_summary(self, completeness: float) -> str:
        """生成总结"""
        percentage = int(completeness * 100)

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
        """执行检查"""
        self.check_project_region()
        self.check_monthly_data()

        completeness = self.calculate_completeness()
        confidence_level = self.get_confidence_level(completeness)

        self.sort_issues()
        summary = self.generate_summary(completeness)

        return {
            'completeness': round(completeness, 2),
            'confidence_level': confidence_level,
            'issues': self.issues,
            'summary': summary
        }


# ============= 主函数 =============

def extract_and_check_data(survey_excel_path: str, output_json_path: str):
    """提取数据并进行质量检查"""

    # 步骤 1: 提取数据
    extracted_data = extract_data_from_excel(survey_excel_path)

    # 如果提取失败，直接返回错误
    if extracted_data.get("error"):
        output_path = Path(output_json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)
        return

    # 步骤 2: 执行质量检查
    checker = DataQualityChecker(extracted_data)
    quality_report = checker.run()

    # 步骤 3: 合并结果
    result = {
        "extracted_data": extracted_data,
        "quality_report": quality_report
    }

    # 步骤 4: 输出结果
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 数据提取和质量检查完成: {output_json_path}")
    print(f"项目地区: {extracted_data.get('project_region')}")
    print(f"\n{quality_report['summary']}")


def main():
    """命令行入口"""
    if len(sys.argv) != 3:
        print('用法: python extract_and_check_data.py <调研表Excel路径> <输出JSON路径>')
        sys.exit(1)

    survey_excel_path = sys.argv[1]
    output_json_path = sys.argv[2]

    try:
        extract_and_check_data(survey_excel_path, output_json_path)
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
