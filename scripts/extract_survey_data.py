#!/usr/bin/env python3
"""
从中央空调节能调研表中提取月度运行数据
"""

import pandas as pd
import json
import re
import sys
from pathlib import Path


def parse_value(value):
    """解析文本值为数值"""
    if pd.isna(value):
        return None

    # 转换为字符串
    value_str = str(value).strip()

    # 处理空字符串
    if not value_str or value_str.lower() in ['nan', 'none', '无', '/']:
        return None

    # 尝试直接转换为数值
    try:
        return float(value_str)
    except ValueError:
        pass

    # 处理范围格式 (如 "35-50HZ/45HZ", "3-5℃/4℃")
    range_match = re.search(r'(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)', value_str)
    if range_match:
        start = float(range_match.group(1))
        end = float(range_match.group(2))
        return (start + end) / 2

    # 处理 "工频50HZ" 格式
    freq_match = re.search(r'(\d+\.?\d*)\s*(?:Hz|HZ|hz)', value_str)
    if freq_match:
        return float(freq_match.group(1))

    # 处理 "4℃" 格式
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
    # 尝试从项目地址中推断地区
    for idx, row in df.iterrows():
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val)
            # 查找地区关键词
            regions = {
                '华南': ['广东', '广西', '海南', '福建', '深圳', '广州', '厦门'],
                '华东': ['上海', '江苏', '浙江', '安徽', '江西', '南京', '杭州'],
                '华中': ['湖北', '湖南', '河南', '武汉', '长沙'],
                '西南': ['四川', '重庆', '贵州', '云南', '西藏', '成都', '重庆'],
                '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆', '西安', '兰州'],
                '华北': ['北京', '天津', '河北', '山西', '内蒙古'],
                '东北': ['辽宁', '吉林', '黑龙江', '沈阳', '大连', '长春', '哈尔滨']
            }

            for region, keywords in regions.items():
                if any(keyword in val_str for keyword in keywords):
                    return region

    return None


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


def extract_survey_data(survey_excel_path, output_json_path):
    """从调研表中提取数据"""

    # 读取Excel文件
    xls = pd.ExcelFile(survey_excel_path)

    # 提取项目地区
    project_region = None
    if '项目总体情况' in xls.sheet_names:
        df_overview = pd.read_excel(xls, sheet_name='项目总体情况', header=None)
        project_region = extract_region(df_overview)

    # 读取冷站数据
    if '冷站' not in xls.sheet_names:
        result = {
            "error": True,
            "message": "找不到'冷站'工作表,请确认上传了正确的文件"
        }
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return

    df = pd.read_excel(xls, sheet_name='冷站', header=None)

    # 查找关键行的位置
    row_mappings = {
        'chiller_supply_temp': ['冷机供水温度'],  # 行37
        'cooling_pump_freq': ['冷却泵运行频率'],  # 行38
        'cooling_water_temp_diff': ['冷却侧供回水温差'],  # 行39
        'freezing_pump_freq': ['冷冻泵运行频率'],  # 行40
        'freezing_water_temp_diff': ['冷冻侧供回水温差'],  # 行41
        'cooling_tower_outlet_temp': ['冷却塔出水温度'],  # 行43
        'total_energy': ['整个冷站', '万kWh']  # 行46
    }

    # 查找月份行
    month_row_idx = find_row_by_keyword(df, ['月份', '备注'])
    if month_row_idx is None:
        result = {
            "error": True,
            "message": "未能识别调研表中的月度数据行,请确认上传了正确的文件"
        }
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return

    # 查找各数据行
    data_rows = {}
    for key, keywords in row_mappings.items():
        row_idx = find_row_by_keyword(df, keywords, start_row=month_row_idx, end_row=month_row_idx + 20)
        if row_idx is not None:
            data_rows[key] = row_idx

    # 如果找不到total_energy,尝试查找行46
    if 'total_energy' not in data_rows:
        # 尝试直接读取行46 (索引45)
        if len(df) > 46:
            data_rows['total_energy'] = 46

    # 提取月度数据
    monthly_data = []
    valid_energy_count = 0

    # 月份列通常在 D-O 列 (索引 3-14)
    month_col_start = 3  # D列

    for month in range(1, 13):
        month_col_idx = month_col_start + (month - 1)

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

        # 提取total_energy
        if 'total_energy' in data_rows:
            row_idx = data_rows['total_energy']
            if row_idx < len(df):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)
                if parsed is not None:
                    month_record['total_energy'] = parsed
                    valid_energy_count += 1

        # 提取冷机供水温度
        if 'chiller_supply_temp' in data_rows:
            row_idx = data_rows['chiller_supply_temp']
            if row_idx < len(df):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)
                month_record['chiller_supply_temp'] = parsed

        # 提取冷却泵运行频率
        if 'cooling_pump_freq' in data_rows:
            row_idx = data_rows['cooling_pump_freq']
            if row_idx < len(df):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)
                month_record['cooling_pump_freq'] = parsed

        # 提取冷却侧供回水温差
        if 'cooling_water_temp_diff' in data_rows:
            row_idx = data_rows['cooling_water_temp_diff']
            if row_idx < len(df):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)
                month_record['cooling_water_temp_diff'] = parsed

        # 提取冷冻泵运行频率
        if 'freezing_pump_freq' in data_rows:
            row_idx = data_rows['freezing_pump_freq']
            if row_idx < len(df):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)
                month_record['freezing_pump_freq'] = parsed

        # 提取冷冻侧供回水温差
        if 'freezing_water_temp_diff' in data_rows:
            row_idx = data_rows['freezing_water_temp_diff']
            if row_idx < len(df):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)
                month_record['freezing_water_temp_diff'] = parsed

        # 提取冷却塔出水温度
        if 'cooling_tower_outlet_temp' in data_rows:
            row_idx = data_rows['cooling_tower_outlet_temp']
            if row_idx < len(df):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)
                month_record['cooling_tower_outlet_temp'] = parsed

        monthly_data.append(month_record)

    # 验证数据质量
    if valid_energy_count < 3:
        result = {
            "error": True,
            "message": f"有效能耗数据月份不足3个月(仅找到{valid_energy_count}个月),请确认上传了正确的文件"
        }
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return

    # 构建输出
    result = {
        "project_region": project_region,
        "monthly_data": monthly_data
    }

    # 输出JSON文件
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"数据提取成功: {output_json_path}")
    print(f"项目地区: {project_region}")
    print(f"有效能耗数据月份: {valid_energy_count}/12")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("用法: python extract_survey_data.py <调研表Excel路径> <输出JSON路径>")
        sys.exit(1)

    survey_excel_path = sys.argv[1]
    output_json_path = sys.argv[2]

    extract_survey_data(survey_excel_path, output_json_path)
