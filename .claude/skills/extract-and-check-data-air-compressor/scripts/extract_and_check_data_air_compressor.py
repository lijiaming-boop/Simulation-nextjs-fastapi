#!/usr/bin/env python3
"""
从空压节能调研表中提取数据并进行质量检查
"""

import json
import re
import sys
import datetime
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加正则表达式导入用于精确匹配
import re as regex_module

try:
    import pandas as pd
except ImportError:
    print("错误: 需要安装 pandas 库")
    print("请运行: pip install pandas")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    print("错误: 需要安装 openpyxl 库")
    print("请运行: pip install openpyxl")
    sys.exit(1)

try:
    from docx import Document
except ImportError:
    print("警告: python-docx 未安装，Word文档读取功能将不可用")
    print("如需支持Word格式，请运行: pip install python-docx")
    Document = None


# 常量定义
ATMOSPHERIC_PRESSURE = 1  # bar，表压转绝对压
DIRECT_USE_RATIO = 70  # %，主管网直接耗量比例
RATED_POWER_FACTOR = 1.1  # 无量纲，铭牌功率系数
DEFAULT_ANNUAL_HOURS = 8500  # 小时/年，默认年运行时间
DEFAULT_DAILY_HOURS = 10  # 小时/天，默认每天开机时间
DEFAULT_ANNUAL_DAYS = 330  # 天/年，默认年运行天数

# 附表1：压力波动与安全裕量查询表
PRESSURE_SAFETY_MARGIN_TABLE = {
    "电池": {"pressure_fluctuation": 0.15, "safety_margin": 0.10},
    "整车及电子": {"pressure_fluctuation": 0.20, "safety_margin": 0.20},
    "钢铁有色": {"pressure_fluctuation": 0.30, "safety_margin": 0.20},
    "其他": {"pressure_fluctuation": 0.20, "safety_margin": 0.20}
}

# 附表2：压缩机功率因子查询表
COMPRESSOR_POWER_FACTOR_TABLE = {
    "三星": {"age": {"min": 10, "max": None, "value": 0.32}},
    "国产": {"age": {"min": 10, "max": None, "value": 0.32}},
    "复盛": {"age": {"min": 10, "max": None, "value": 0.32}},
    "英格索兰卡梅隆": {"age": {"min": 10, "max": None, "value": 0.32}},
    "寿力": {"age": {"min": None, "max": None, "value": 0.34}},
    "韩华": {"age": {"min": None, "max": None, "value": 0.34}},
    "阿特拉斯": {"age": {"min": 5, "max": 10, "value": 0.35}},
    "阿特拉斯": {"age": {"min": None, "max": 5, "value": 0.36}},
    "英格索兰": {"age": {"min": 5, "max": 10, "value": 0.35}},
    "英格索兰": {"age": {"min": None, "max": 5, "value": 0.36}}
}

DEFAULT_POWER_FACTOR = 0.35  # 默认功率因子

# 附表3：各省份工业用电电单价参考列表
ELECTRICITY_PRICE_TABLE = {
    "北京": 0.64,
    "天津": 0.69,
    "河北": 0.62,
    "山西": 0.55,
    "内蒙古": 0.43,
    "辽宁": 0.61,
    "吉林": 0.59,
    "黑龙江": 0.61,
    "上海": 0.75,
    "江苏": 0.70,
    "浙江": 0.73,
    "安徽": 0.65,
    "福建": 0.63,
    "江西": 0.62,
    "山东": 0.74,
    "河南": 0.61,
    "湖北": 0.64,
    "湖南": 0.65,
    "广东": 0.69,
    "广西": 0.55,
    "海南": 0.63,
    "重庆": 0.70,
    "四川": 0.52,
    "贵州": 0.57,
    "云南": 0.50,
    "西藏": 0.66,
    "陕西": 0.56,
    "甘肃": 0.44,
    "青海": 0.45,
    "宁夏": 0.43,
    "新疆": 0.45
}


def parse_value(value):
    """解析文本值为数值

    Args:
        value: 单元格值

    Returns:
        解析后的数值，或 None
    """
    if pd.isna(value):
        return None

    value_str = str(value).strip()

    if not value_str or value_str.lower() in ['nan', 'none', '无', '/']:
        return None

    try:
        return float(value_str)
    except ValueError:
        pass

    # 处理带单位的数值
    # 提取第一个数字
    number_match = re.search(r'(\d+\.?\d*)', value_str)
    if number_match:
        return float(number_match.group(1))

    return None


def read_word_document(docx_path: str) -> pd.DataFrame:
    """从Word文档中提取表格数据并转换为DataFrame
    
    Args:
        docx_path: Word文档路径
        
    Returns:
        包含Word文档表格数据的DataFrame
    """
    print(f"📖 [Word读取] 打开文档: {docx_path}")
    
    doc = Document(docx_path)
    
    # 收集所有表格
    all_tables = []
    print(f"📊 [Word读取] 发现 {len(doc.tables)} 个表格")
    
    for i, table in enumerate(doc.tables):
        print(f"📋 [Word读取] 处理表格 {i+1}/{len(doc.tables)}")
        # 将表格转换为DataFrame
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(cells)
        
        if rows:
            df_table = pd.DataFrame(rows[1:], columns=rows[0] if rows else None)
            all_tables.append(df_table)
            print(f"   表格 {i+1}: {df_table.shape[0]} 行 x {df_table.shape[1]} 列")
    
    if not all_tables:
        # 如果没有表格，尝试从段落中提取数据
        print(f"⚠️  [Word读取] 未发现表格，尝试从段落提取...")
        # 返回空的DataFrame
        return pd.DataFrame()
    
    # 合并所有表格（按行）
    # 优先使用第一个表格（通常是主数据表）
    if all_tables:
        main_df = all_tables[0]
        print(f"✅ [Word读取] 使用主表格: {main_df.shape[0]} 行 x {main_df.shape[1]} 列")
        return main_df
    
    return pd.DataFrame()


def extract_project_info(df):
    """从调研表中提取项目级原始数据

    Args:
        df: 调研表的 DataFrame

    Returns:
        项目级原始数据字典
    """
    project_info = {
        "companyName": None,
        "companyShortName": None,
        "projectName": None,
        "projectLocation": None,
        "industryType": None,
        "totalAnnualEnergyConsumption": None,
        "electricityPrice": None,
        "alarmPressureLowerLimit": None,
        "averagePressure": None,
        "dailyRunningHours": None,
        "annualRunningDays": None
    }

    # 遍历前20行查找项目信息
    for idx in range(min(20, len(df))):
        row = df.iloc[idx]
        for col_idx, val in enumerate(row):
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            
            # 企业名称和项目地点 - 从标签行的下一行提取
            if idx == 1 and col_idx == 0 and "企业名称" in val_str:
                # 企业名称标签行，下一行是企业名称
                if idx + 1 < len(df):
                    company_name_val = df.iloc[idx + 1, col_idx + 1]
                    if pd.notna(company_name_val):
                        company_name_str = str(company_name_val).strip()
                        if "企业名称" not in company_name_str:
                            project_info["companyName"] = company_name_str
            elif idx == 2 and col_idx == 0 and "项目地点" in val_str:
                # 项目地点标签行，下一行是项目地点
                if idx + 1 < len(df):
                    location_val = df.iloc[idx + 1, col_idx + 1]
                    if pd.notna(location_val):
                        location_str = str(location_val).strip()
                        if "项目地点" not in location_str:
                            project_info["projectLocation"] = location_str
            
            # 行业类型 - 尝试从企业名称或项目地点推断
            if not project_info["industryType"]:
                for industry in PRESSURE_SAFETY_MARGIN_TABLE.keys():
                    if industry in val_str:
                        project_info["industryType"] = industry
                        break
            
            # 空压系统年度总用量和平均电价 - 使用准确的列索引
            if idx == 6:  # 第7行（索引6）
                # 年能耗在第14列（索引13）
                if len(row) > 13:
                    project_info["totalAnnualEnergyConsumption"] = parse_value(row.iloc[13])
                
                # 平均电价在第15列（索引14）
                if len(row) > 14:
                    price_str = str(row.iloc[14]).strip()
                    if "元" in price_str:
                        project_info["electricityPrice"] = parse_value(price_str)
            
            # 从任何位置提取压力信息
            if "压力低于" in val_str and "bar" in val_str:
                # 提取报警压力下限
                pressure_match = re.search(r'压力低于\s*([0-9.]+)\s*bar', val_str)
                if pressure_match:
                    project_info["alarmPressureLowerLimit"] = parse_value(pressure_match.group(1))
            
            if "最低压力为" in val_str and "bar" in val_str:
                # 提取主管网最低压力
                pressure_match = re.search(r'最低压力为\s*([0-9.]+)\s*bar', val_str)
                if pressure_match:
                    project_info["averagePressure"] = parse_value(pressure_match.group(1))
            
            # 每天开机时间 - 假设24小时运行
            if not project_info["dailyRunningHours"]:
                project_info["dailyRunningHours"] = 24
            
            # 年运行天数 - 假设330天
            if not project_info["annualRunningDays"]:
                project_info["annualRunningDays"] = 330

    # 自动生成企业简称和项目名称
    if project_info["companyName"]:
        # 简单处理：删除常见后缀
        short_name = project_info["companyName"]
        for suffix in ["有限公司", "有限责任公司", "股份有限公司", "集团", "公司"]:
            if short_name.endswith(suffix):
                short_name = short_name[:-len(suffix)]
        project_info["companyShortName"] = short_name.strip()
        project_info["projectName"] = f"{short_name.strip()}空压系统节能项目"
    else:
        # 尝试从项目地点生成名称
        if project_info["projectLocation"]:
            project_info["companyName"] = project_info["projectLocation"]
            project_info["companyShortName"] = project_info["projectLocation"]
            project_info["projectName"] = f"{project_info["projectLocation"]}空压系统节能项目"
        else:
            # 从文件名或其他信息生成默认名称
            project_info["companyName"] = "未知企业"
            project_info["companyShortName"] = "未知企业"
            project_info["projectName"] = "空压系统节能项目"

    return project_info


def find_equipment_list_start(df):
    """查找设备清单的起始行

    Args:
        df: 调研表的 DataFrame

    Returns:
        设备清单起始行索引，或 None
    """
    # 查找螺杆机或离心机关键字
    keywords = ["螺杆机", "离心机"]
    
    for idx in range(len(df)):
        row = df.iloc[idx]
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if any(keyword in val_str for keyword in keywords):
                return idx
    
    return None


def extract_equipment_list(df):
    """从调研表中提取设备级原始数据

    Args:
        df: 调研表的 DataFrame

    Returns:
        设备级原始数据列表
    """
    equipment_list = []
    
    # 查找设备清单起始行
    start_row = find_equipment_list_start(df)
    if start_row is None:
        return equipment_list
    
    current_year = datetime.datetime.now().year
    current_equipment_type = None
    
    # 手动定义字段映射（根据示例调研表的结构）
    field_mapping = {
        "stationId": 1,      # 站房在第2列
        "equipmentId": 2,    # 序号/设备编码在第3列
        "brand": 3,          # 品牌在第4列
        "compressionType": 4,# 压缩形式在第5列
        "model": 5,          # 型号在第6列
        "ratedPower": 6,     # 额定功率在第7列
        "ratedVoltage": 7,   # 额定电压在第8列
        "ratedFlow": 8,      # 额定流量在第9列
        "ratedPressure": 10,  # 额定压力在第11列
        "loadingPressure": 11,# 加载压力在第12列
        "unloadingPressure": 12,# 卸载压力在第13列
        "manufactureYear": 13, # 出厂时间在第14列
        "runningStatus": 14,   # 运行状态在第15列
        "demandPressure": 15,   # 需求压力在第16列
        "totalRunningHours": 16, # 运行总时间在第17列
        "totalLoadingHours": 17, # 加载总时间在第18列
        "motherPipePressure": 20 # 母管压力在第21列
    }
    
    # 提取设备数据
    for idx in range(start_row, len(df)):
        row = df.iloc[idx]
        
        # 跳过空行
        if all(pd.isna(val) for val in row[:5]):
            continue
        
        # 检查是否是新的设备类型
        first_col_val = str(row.iloc[0]).strip()
        if "螺杆机" in first_col_val:
            current_equipment_type = "螺杆式"
            continue
        elif "离心机" in first_col_val:
            current_equipment_type = "离心式"
            continue
        elif "干燥机" in first_col_val:
            # 干燥机不属于空压机，跳过
            break
        
        # 提取设备信息
        equipment = {
            "stationId": None,
            "equipmentId": None,
            "equipmentType": current_equipment_type,
            "brand": None,
            "model": None,
            "manufactureYear": None,
            "age": None,
            "runningStatus": None,
            "ratedPower": None,
            "ratedFlow": None,
            "compressorPowerFactor": None,
            "specificPower": None
        }
        
        # 提取站房信息
        if field_mapping["stationId"] < len(row):
            station_val = row.iloc[field_mapping["stationId"]]
            if pd.notna(station_val):
                equipment["stationId"] = str(station_val).strip()
        
        # 提取设备编码
        if field_mapping["equipmentId"] < len(row):
            equip_id_val = row.iloc[field_mapping["equipmentId"]]
            if pd.notna(equip_id_val):
                equipment["equipmentId"] = str(equip_id_val).strip()
        
        # 提取品牌
        if field_mapping["brand"] < len(row):
            brand_val = row.iloc[field_mapping["brand"]]
            if pd.notna(brand_val):
                equipment["brand"] = str(brand_val).strip()
        
        # 提取型号
        if field_mapping["model"] < len(row):
            model_val = row.iloc[field_mapping["model"]]
            if pd.notna(model_val):
                equipment["model"] = str(model_val).strip()
        
        # 提取额定功率
        if field_mapping["ratedPower"] < len(row):
            power_val = row.iloc[field_mapping["ratedPower"]]
            equipment["ratedPower"] = parse_value(power_val)
        
        # 提取额定流量
        if field_mapping["ratedFlow"] < len(row):
            flow_val = row.iloc[field_mapping["ratedFlow"]]
            equipment["ratedFlow"] = parse_value(flow_val)
        
        # 提取出厂年份
        if field_mapping["manufactureYear"] < len(row):
            year_val = row.iloc[field_mapping["manufactureYear"]]
            if pd.notna(year_val):
                year_str = str(year_val).strip()
                # 处理"2016.7"或"2016"格式的年份
                year_match = re.search(r'(\d{4})', year_str)
                if year_match:
                    equipment["manufactureYear"] = int(year_match.group(1))
        
        # 提取运行状态 - 尝试多个可能的列
        status_columns = [14, 15, 16]  # 尝试第15、16、17列
        for col in status_columns:
            if col < len(row):
                status_val = row.iloc[col]
                if pd.notna(status_val):
                    status_str = str(status_val).strip()
                    # 只接受合理的状态值
                    if status_str in ["运行", "备用", "阶段运行", "故障", "停用"] or len(status_str) > 2:
                        equipment["runningStatus"] = status_str
                        break
        
        # 计算设备年龄
        if equipment['manufactureYear'] and isinstance(equipment['manufactureYear'], (int, float)):
            equipment['age'] = current_year - equipment['manufactureYear']
        
        # 计算比功率
        if equipment['ratedPower'] and equipment['ratedFlow'] and equipment['ratedFlow'] > 0:
            equipment['specificPower'] = (equipment['ratedPower'] * RATED_POWER_FACTOR) / equipment['ratedFlow']
        
        # 计算压缩机功率因子
        equipment['compressorPowerFactor'] = DEFAULT_POWER_FACTOR
        if equipment['brand']:
            for brand, factor_info in COMPRESSOR_POWER_FACTOR_TABLE.items():
                if brand in equipment['brand']:
                    age_info = factor_info['age']
                    if equipment['age'] is not None:
                        if (age_info['min'] is None or equipment['age'] >= age_info['min']) and \
                           (age_info['max'] is None or equipment['age'] < age_info['max']):
                            equipment['compressorPowerFactor'] = age_info['value']
                            break
                    else:
                        # 如果没有机龄信息，使用默认值
                        break
        
        # 只添加有基本信息的设备
        if equipment['stationId'] and equipment['equipmentId'] and equipment['equipmentType']:
            equipment_list.append(equipment)
    
    return equipment_list


def extract_data_from_excel(survey_excel_path: str, original_filename: Optional[str] = None) -> Dict[str, Any]:
    """从 Excel 文件提取空压机节能数据

    Args:
        survey_excel_path: Excel 文件路径
        original_filename: 原始文件名
    """
    try:
        print(f"📖 [数据提取] 读取Excel文件: {survey_excel_path}")
        print(f"📁 [数据提取] 原始文件名: {original_filename}")
        
        # 检查文件是否存在
        if not Path(survey_excel_path).exists():
            raise FileNotFoundError(f"文件不存在: {survey_excel_path}")
        
        # 获取文件信息
        file_size = Path(survey_excel_path).stat().st_size
        print(f"📏 [数据提取] 文件大小: {file_size} 字节")
        
        # 尝试不同的方式读取文件
        xls = None
        try:
            # 首先尝试作为Excel文件读取
            print(f"🔄 [数据提取] 尝试读取为Excel格式...")
            xls = pd.ExcelFile(survey_excel_path)
            print(f"✅ [数据提取] Excel格式读取成功")
        except Exception as e1:
            print(f"❌ [数据提取] Excel格式读取失败: {str(e1)}")
            
            # 如果失败，尝试指定引擎
            try:
                print(f"🔄 [数据提取] 尝试使用openpyxl引擎...")
                xls = pd.ExcelFile(survey_excel_path, engine='openpyxl')
                print(f"✅ [数据提取] openpyxl引擎读取成功")
            except Exception as e2:
                print(f"❌ [数据提取] openpyxl引擎读取失败: {str(e2)}")
                
                # 尝试xlrd引擎（用于.xls文件）
                try:
                    print(f"🔄 [数据提取] 尝试使用xlrd引擎...")
                    xls = pd.ExcelFile(survey_excel_path, engine='xlrd')
                    print(f"✅ [数据提取] xlrd引擎读取成功")
                except Exception as e3:
                    print(f"❌ [数据提取] xlrd引擎读取失败: {str(e3)}")
                    
                    # 所有Excel方法都失败了，检查是否是其他格式
                    print(f"⚠️  [数据提取] Excel读取失败，检查文件格式...")
                    
                    # 直接检查文件内容（更准确）
                    try:
                        with zipfile.ZipFile(survey_excel_path, 'r') as zf:
                            file_list = zf.namelist()
                            has_xl = any(f.startswith('xl/') for f in file_list)
                            has_word = any(f.startswith('word/') for f in file_list)
                            print(f"🔍 [数据提取] 文件内容检查: xl/={has_xl}, word/={has_word}")
                            
                            if has_word and not has_xl:
                                # 这是Word文件，尝试使用python-docx读取
                                if Document is None:
                                    error_msg = f"检测到文件是Word格式(.docx)，不是Excel格式\n"
                                    error_msg += f"当前环境未安装python-docx库，无法读取Word文档。\n"
                                    error_msg += f"请先安装库: pip install python-docx\n"
                                    error_msg += f"或者将Word文档中的表格数据复制到Excel文件中"
                                    raise Exception(error_msg)
                                
                                print(f"🔄 [数据提取] 尝试使用python-docx读取Word文档...")
                                try:
                                    df = read_word_document(survey_excel_path)
                                    print(f"✅ [数据提取] Word文档读取成功")
                                    print(f"📏 [数据提取] 文档尺寸: {df.shape[0]} 行 x {df.shape[1]} 列")
                                    
                                    # 提取项目信息
                                    print(f"🏢 [数据提取] 提取项目基本信息...")
                                    project_info = extract_project_info(df)
                                    print(f"✅ [数据提取] 项目信息提取完成: {project_info.get('companyName', '未知企业')}")
                                    
                                    # 提取设备列表
                                    print(f"🔧 [数据提取] 提取设备列表...")
                                    equipment_list = extract_equipment_list(df)
                                    print(f"📋 [数据提取] 从Word文档提取到 {len(equipment_list)} 台设备")
                                    
                                    # 填充缺失的行业类型
                                    if not project_info.get("industryType"):
                                        if original_filename:
                                            for industry in PRESSURE_SAFETY_MARGIN_TABLE.keys():
                                                if industry in original_filename:
                                                    project_info["industryType"] = industry
                                                    break
                                        if not project_info.get("industryType"):
                                            project_info["industryType"] = "其他"
                                    
                                    # 填充缺失的电价
                                    if not project_info.get("electricityPrice"):
                                        project_info["electricityPrice"] = 0.7
                                    
                                    # 返回结果
                                    return {
                                        "extracted_data": {
                                            "system_info": project_info,
                                            "equipment_list": equipment_list
                                        },
                                        "quality_report": {
                                            "completeness": calculate_completeness(project_info, equipment_list),
                                            "confidence": calculate_confidence(project_info, equipment_list),
                                            "confidence_level": get_confidence_level(project_info, equipment_list),
                                            "issues": check_quality_issues(project_info, equipment_list),
                                            "summary": generate_summary(project_info, equipment_list),
                                            "need_rejection": False,
                                            "rejection_reasons": []
                                        }
                                    }
                                except Exception as word_error:
                                    error_msg = f"Word文档读取失败: {str(word_error)}\n"
                                    error_msg += f"请确认Word文档中包含有效的表格数据"
                                    raise Exception(error_msg)
                            elif not has_xl and not has_word:
                                # 无法识别的格式
                                error_msg = f"无法识别文件格式\n"
                                error_msg += f"请确认文件是有效的Excel格式(.xlsx或.xls)"
                                raise Exception(error_msg)
                    except zipfile.BadZipFile:
                        # 不是zip格式（可能是老版本.xls或其他格式）
                        pass
                    
                    # 回退到扩展名检查
                    original_ext = Path(original_filename).suffix.lower() if original_filename else ""
                    if original_ext in ['.docx', '.doc', '.pptx', '.ppt']:
                        error_msg = f"检测到非Excel文件格式: {original_ext}\n"
                        error_msg += f"空压模块目前主要支持Excel格式的调研表。\n"
                        error_msg += f"如果您的调研表是Word或PowerPoint格式，请：\n"
                        error_msg += f"1. 将表格数据复制到Excel文件中\n"
                        error_msg += f"2. 或者联系技术支持添加对该格式的支持"
                        raise Exception(error_msg)
                    else:
                        error_msg = f"无法读取文件，尝试了多种Excel读取方法:\n"
                        error_msg += f"1. 默认方式: {str(e1)}\n"
                        error_msg += f"2. openpyxl引擎: {str(e2)}\n"
                        error_msg += f"3. xlrd引擎: {str(e3)}\n"
                        error_msg += f"请确认文件是有效的Excel格式(.xlsx或.xls)"
                        raise Exception(error_msg)
        
        print(f"📄 [数据提取] 发现工作表: {xls.sheet_names}")
        
        # 尝试从第一个工作表提取数据
        first_sheet = xls.sheet_names[0]
        print(f"📊 [数据提取] 开始处理工作表: {first_sheet}")
        df = pd.read_excel(xls, sheet_name=first_sheet, header=None)
        print(f"📏 [数据提取] 工作表尺寸: {df.shape[0]} 行 x {df.shape[1]} 列")
        
        # 提取项目信息
        print(f"🏢 [数据提取] 提取项目基本信息...")
        project_info = extract_project_info(df)
        print(f"✅ [数据提取] 项目信息提取完成: {project_info.get('companyName', '未知企业')}")
        
        # 提取设备列表
        print(f"🔧 [数据提取] 提取设备列表...")
        equipment_list = extract_equipment_list(df)
        print(f"📋 [数据提取] 从工作表 '{first_sheet}' 提取到 {len(equipment_list)} 台设备")
        
        # 如果第一个工作表没有设备列表，尝试其他工作表
        if not equipment_list:
            print(f"⚠️  [数据提取] 第一个工作表未找到设备，尝试其他工作表...")
            for sheet_name in xls.sheet_names[1:]:
                print(f"🔍 [数据提取] 检查工作表: {sheet_name}")
                df_sheet = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                equipment_list = extract_equipment_list(df_sheet)
                if equipment_list:
                    print(f"✅ [数据提取] 在工作表 '{sheet_name}' 找到 {len(equipment_list)} 台设备")
                    break
                else:
                    print(f"❌ [数据提取] 工作表 '{sheet_name}' 未找到设备数据")
        
        # 填充缺失的行业类型
        if not project_info.get("industryType"):
            # 尝试从文件名提取
            if original_filename:
                for industry in PRESSURE_SAFETY_MARGIN_TABLE.keys():
                    if industry in original_filename:
                        project_info["industryType"] = industry
                        break
            # 默认使用"其他"
            if not project_info.get("industryType"):
                project_info["industryType"] = "其他"
        
        # 填充缺失的电价
        if not project_info.get("electricityPrice") and project_info.get("projectLocation"):
            for province, price in ELECTRICITY_PRICE_TABLE.items():
                if province in project_info["projectLocation"]:
                    project_info["electricityPrice"] = price
                    break
        
        return {
            "system_info": project_info,
            "equipment_list": equipment_list
        }
        
    except Exception as e:
        print(f"❌ [数据提取] 发生异常: {str(e)}")
        import traceback
        print(f"🔍 [数据提取] 详细错误信息:")
        traceback.print_exc()
        return {
            "error": True,
            "message": f"数据提取失败: {str(e)}"
        }


class AirCompressorDataQualityChecker:
    """空压机数据质量检查器"""
    
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.issues: List[Dict[str, str]] = []
        self.rejection_reasons = []  # 打回原因
        
    def check_project_info(self):
        """检查项目级信息"""
        system_info = self.data.get("system_info", {})
        
        # 检查现有系统报警压力
        if not system_info.get("alarmPressureLowerLimit") or system_info.get("alarmPressureLowerLimit") <= 0:
            self.issues.append({
                'field': 'alarmPressureLowerLimit',
                'severity': 'critical',
                'type': 'missing',
                'message': '现有系统报警压力缺失或无效'
            })
            self.rejection_reasons.append("现有系统报警压力缺失或无效")
        
        # 检查近14天系统平均压力
        if not system_info.get("averagePressure"):
            self.issues.append({
                'field': 'averagePressure',
                'severity': 'critical',
                'type': 'missing',
                'message': '近14天系统平均压力缺失'
            })
            self.rejection_reasons.append("近14天系统平均压力缺失")
        
        # 检查空压系统年度总用量
        if not system_info.get("totalAnnualEnergyConsumption") or system_info.get("totalAnnualEnergyConsumption") <= 0:
            self.issues.append({
                'field': 'totalAnnualEnergyConsumption',
                'severity': 'critical',
                'type': 'missing',
                'message': '空压系统年度总用量缺失或无效'
            })
            self.rejection_reasons.append("空压系统年度总用量缺失或无效")
        
    def check_equipment_list(self):
        """检查设备级信息"""
        equipment_list = self.data.get("equipment_list", [])
        
        if not equipment_list:
            self.issues.append({
                'field': 'equipment_list',
                'severity': 'critical',
                'type': 'missing',
                'message': '设备清单缺失'
            })
            self.rejection_reasons.append("设备清单缺失")
            return
        
        # 检查是否有运行或备用设备
        has_valid_equipment = False
        valid_statuses = ["运行", "备用", "阶段运行"]  # 添加"阶段运行"作为有效状态
        for equipment in equipment_list:
            if equipment.get("runningStatus") in valid_statuses:
                has_valid_equipment = True
                break
        
        if not has_valid_equipment:
            self.issues.append({
                'field': 'equipment_list.runningStatus',
                'severity': 'critical',
                'type': 'logic_error',
                'message': f'所有设备的运行状态均不是{valid_statuses}中的任何一种'
            })
            self.rejection_reasons.append(f"所有设备的运行状态均不是{valid_statuses}中的任何一种")
        
        # 检查站房编码是否为空
        for equipment in equipment_list:
            station_id = equipment.get("stationId")
            if not station_id:
                self.issues.append({
                    'field': 'equipment_list.stationId',
                    'severity': 'critical',
                    'type': 'missing',
                    'message': f'设备 {equipment.get("equipmentId", "未知")} 的站房编码为空'
                })
                self.rejection_reasons.append(f'设备 {equipment.get("equipmentId", "未知")} 的站房编码为空')
        
        # 检查设备编码是否重复或为空
        station_equipment_map = {}
        for equipment in equipment_list:
            station_id = equipment.get("stationId")
            equipment_id = equipment.get("equipmentId")
            
            if not equipment_id:
                self.issues.append({
                    'field': 'equipment_list.equipmentId',
                    'severity': 'critical',
                    'type': 'missing',
                    'message': f'站房 {station_id} 下的设备编码为空'
                })
                self.rejection_reasons.append(f'站房 {station_id} 下的设备编码为空')
                continue
            
            if station_id not in station_equipment_map:
                station_equipment_map[station_id] = []
            
            if equipment_id in station_equipment_map[station_id]:
                self.issues.append({
                    'field': 'equipment_list.equipmentId',
                    'severity': 'critical',
                    'type': 'duplicate',
                    'message': f'站房 {station_id} 下的设备编码 {equipment_id} 重复'
                })
                self.rejection_reasons.append(f'站房 {station_id} 下的设备编码 {equipment_id} 重复')
            else:
                station_equipment_map[station_id].append(equipment_id)
        
        # 检查运行设备的铭牌功率和流量
        for equipment in equipment_list:
            if equipment.get("runningStatus") == "运行":
                if not equipment.get("ratedPower") or equipment.get("ratedPower") <= 0:
                    self.issues.append({
                        'field': 'equipment_list.ratedPower',
                        'severity': 'high',
                        'type': 'missing',
                        'message': f'设备 {equipment.get("equipmentId")} (运行状态) 的铭牌功率缺失或无效'
                    })
                
                if not equipment.get("ratedFlow") or equipment.get("ratedFlow") <= 0:
                    self.issues.append({
                        'field': 'equipment_list.ratedFlow',
                        'severity': 'high',
                        'type': 'missing',
                        'message': f'设备 {equipment.get("equipmentId")} (运行状态) 的铭牌流量缺失或无效'
                    })
            
            # 检查设备类型
            if not equipment.get("equipmentType"):
                self.issues.append({
                    'field': 'equipment_list.equipmentType',
                    'severity': 'high',
                    'type': 'missing',
                    'message': f'设备 {equipment.get("equipmentId")} 的设备类型缺失'
                })
    
    def calculate_completeness(self) -> float:
        """计算数据完整率"""
        system_info = self.data.get("system_info", {})
        equipment_list = self.data.get("equipment_list", [])
        
        total_fields = 0
        filled_fields = 0
        
        # 项目级字段完整率
        project_fields = [
            "companyName",
            "companyShortName",
            "projectName",
            "projectLocation",
            "industryType",
            "totalAnnualEnergyConsumption",
            "electricityPrice",
            "alarmPressureLowerLimit",
            "averagePressure",
            "dailyRunningHours",
            "annualRunningDays"
        ]
        
        total_fields += len(project_fields)
        for field in project_fields:
            if system_info.get(field) is not None:
                filled_fields += 1
        
        # 设备级字段完整率
        if equipment_list:
            equipment_fields = [
                "stationId",
                "equipmentId",
                "equipmentType",
                "brand",
                "model",
                "manufactureYear",
                "runningStatus",
                "ratedPower",
                "ratedFlow"
            ]
            
            total_fields += len(equipment_fields) * len(equipment_list)
            for equipment in equipment_list:
                for field in equipment_fields:
                    if equipment.get(field) is not None:
                        filled_fields += 1
        
        return filled_fields / total_fields if total_fields > 0 else 0.0
    
    def calculate_confidence(self, completeness: float) -> float:
        """计算置信度
        
        从100%开始扣减，最终置信度 = max(0, 100 - 总扣分)
        """
        confidence = 100.0
        system_info = self.data.get("system_info", {})
        equipment_list = self.data.get("equipment_list", [])
        
        # 压力曲线数据7~14天（不足14天） -5%
        # 假设如果有平均压力数据，但没有明确的14天数据，扣5%
        if system_info.get("averagePressure"):
            confidence -= 5.0
        
        # 行业缺失（压力波动用默认0.20） -15%
        if system_info.get("industryType") == "其他":
            confidence -= 15.0
        
        # 每台（运行+备用）功率因子使用默认0.35 -5%/台（最多-30%）
        default_power_factor_count = 0
        for equipment in equipment_list:
            if equipment.get("runningStatus") in ["运行", "备用"] and \
               equipment.get("compressorPowerFactor") == DEFAULT_POWER_FACTOR:
                default_power_factor_count += 1
        confidence -= min(default_power_factor_count * 5.0, 30.0)
        
        # 电价缺失（城市推算） -10%
        if not system_info.get("electricityPrice"):
            confidence -= 10.0
        
        # 每天开机时间缺失（默认10） -5%
        if not system_info.get("dailyRunningHours"):
            confidence -= 5.0
        
        # 年运行天数缺失（默认330） -5%
        if not system_info.get("annualRunningDays"):
            confidence -= 5.0
        
        # 年运行时间计算异常（用默认8500） -10%
        # 这里简化处理：如果有开机时间和运行天数，则不扣分
        if system_info.get("dailyRunningHours") and system_info.get("annualRunningDays"):
            pass
        else:
            confidence -= 10.0
        
        # 基于完整率的调整
        if completeness < 0.6:
            confidence -= 10.0
        elif completeness < 0.8:
            confidence -= 5.0
        
        return max(0.0, confidence)
    
    def get_confidence_level(self, confidence: float) -> str:
        """根据置信度值判断置信度级别
        
        Returns:
            "高"（≥80%）、"中"（60~79%）、"低"（<60%）
        """
        if confidence >= 80:
            return "高"
        elif confidence >= 60:
            return "中"
        else:
            return "低"
    
    def sort_issues(self) -> None:
        """按严重程度排序"""
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        self.issues.sort(key=lambda x: severity_order.get(x['severity'], 99))
    
    def generate_summary(self, completeness: float, confidence: float) -> str:
        """生成总结"""
        percentage = int(completeness * 100)
        confidence_percentage = int(confidence)
        
        critical_count = sum(1 for i in self.issues if i['severity'] == 'critical')
        high_count = sum(1 for i in self.issues if i['severity'] == 'high')
        medium_count = sum(1 for i in self.issues if i['severity'] == 'medium')
        
        if not self.issues:
            return f'数据完整率{percentage}%, 置信度{confidence_percentage}%, 未发现数据质量问题。'
        
        problem_desc = []
        if critical_count > 0:
            problem_desc.append(f'{critical_count}个严重问题')
        if high_count > 0:
            problem_desc.append(f'{high_count}个高优先级问题')
        if medium_count > 0:
            problem_desc.append(f'{medium_count}个中等问题')
        
        problem_str = '、'.join(problem_desc)
        
        return f'数据完整率{percentage}%, 置信度{confidence_percentage}%。发现{problem_str}。'
    
    def run(self) -> Dict[str, Any]:
        """执行检查"""
        # 检查项目信息
        self.check_project_info()
        
        # 检查设备列表
        self.check_equipment_list()
        
        # 计算完整率和置信度
        completeness = self.calculate_completeness()
        confidence = self.calculate_confidence(completeness)
        confidence_level = self.get_confidence_level(confidence)
        
        # 排序问题
        self.sort_issues()
        
        # 生成总结
        summary = self.generate_summary(completeness, confidence)
        
        # 判断是否需要打回
        need_rejection = len(self.rejection_reasons) > 0
        
        return {
            'completeness': round(completeness, 2),
            'confidence': round(confidence, 1),
            'confidence_level': confidence_level,
            'issues': self.issues,
            'summary': summary,
            'need_rejection': need_rejection,
            'rejection_reasons': self.rejection_reasons
        }


# ============= 主函数 =============

def extract_and_check_data_air_compressor(survey_excel_path: str, output_json_path: str, original_filename: Optional[str] = None):
    """提取空压机数据并进行质量检查

    Args:
        survey_excel_path: 调研表路径
        output_json_path: 输出路径
        original_filename: 原始文件名
    """
    try:
        print(f"🔧 [空压机数据提取] 开始处理文件: {survey_excel_path}")
        print(f"📁 [空压机数据提取] 原始文件名: {original_filename}")
        print(f"📤 [空压机数据提取] 输出路径: {output_json_path}")
        
        # 步骤 1: 提取数据
        print("📊 [步骤1] 开始从Excel文件提取数据...")
        extracted_data = extract_data_from_excel(survey_excel_path, original_filename)
        
        # 如果提取失败，直接返回错误
        if extracted_data.get("error"):
            print(f"❌ [步骤1] 数据提取失败: {extracted_data.get('message')}")
            output_path = Path(output_json_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)
            return
        
        print(f"✅ [步骤1] 数据提取成功")
        print(f"   - 提取到 {len(extracted_data.get('equipment_list', []))} 台设备")
        print(f"   - 企业名称: {extracted_data.get('system_info', {}).get('companyName', '未知')}")
        print(f"   - 行业类型: {extracted_data.get('system_info', {}).get('industryType', '未知')}")

        # 步骤 2: 执行质量检查
        print("🔍 [步骤2] 开始数据质量检查...")
        checker = AirCompressorDataQualityChecker(extracted_data)
        quality_report = checker.run()
        
        print(f"✅ [步骤2] 质量检查完成")
        print(f"   - 数据完整率: {quality_report.get('completeness', 0)*100:.1f}%")
        print(f"   - 置信度: {quality_report.get('confidence', 0):.1f}%")
        print(f"   - 置信度等级: {quality_report.get('confidence_level', '未知')}")
        print(f"   - 发现问题: {len(quality_report.get('issues', []))} 个")
        
        if quality_report.get('issues'):
            print("⚠️  [质量问题详情]:")
            for issue in quality_report.get('issues', []):
                severity_icon = "🔴" if issue.get('severity') == 'high' else "🟡" if issue.get('severity') == 'medium' else "🟢"
                print(f"   {severity_icon} {issue.get('message', '')}")

        # 步骤 3: 合并结果
        print("📋 [步骤3] 合并提取结果和质量报告...")
        result = {
            "extracted_data": extracted_data,
            "quality_report": quality_report
        }

        # 步骤 4: 输出结果
        print("💾 [步骤4] 保存结果到文件...")
        output_path = Path(output_json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✅ [完成] 空压机数据提取和质量检查完成: {output_json_path}")
        print(f"📊 [结果摘要]:")
        print(f"   - 企业名称: {extracted_data.get('system_info', {}).get('companyName', '未知')}")
        print(f"   - 项目名称: {extracted_data.get('system_info', {}).get('projectName', '未知')}")
        print(f"   - 设备数量: {len(extracted_data.get('equipment_list', []))} 台")
        print(f"   - 文件大小: {output_path.stat().st_size} 字节")
        print(f"\n📋 [质量报告]: {quality_report['summary']}")
        
        if quality_report['need_rejection']:
            print(f"\n❌ [需要打回] 发现致命问题:")
            for reason in quality_report['rejection_reasons']:
                print(f"   🔴 {reason}")
        else:
            print(f"\n✅ [可以继续] 数据质量符合要求，可进入下一步骤")
    except Exception as e:
        print(f"💥 [致命错误] 空压机数据处理失败: {str(e)}")
        import traceback
        print(f"🔍 [错误详情] 完整堆栈跟踪:")
        traceback.print_exc()
        
        error_result = {
            "error": True,
            "message": f"执行过程中发生错误: {str(e)}",
            "traceback": traceback.format_exc()
        }
        
        print(f"💾 [错误处理] 保存错误信息到: {output_json_path}")
        output_path = Path(output_json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        print(f"❌ [最终状态] 空压机数据处理失败，请检查上述错误信息")


def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print('用法: python extract_and_check_data_air_compressor.py <调研表Excel路径> <输出JSON路径> [原始文件名]')
        sys.exit(1)

    survey_excel_path = sys.argv[1]
    output_json_path = sys.argv[2]
    original_filename = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        extract_and_check_data_air_compressor(survey_excel_path, output_json_path, original_filename)
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()