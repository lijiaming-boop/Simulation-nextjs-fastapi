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

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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


# ============= 数据提取部分 (来自 extract_survey_data.py) =============

def get_season(month: int) -> str:
    """根据月份判断季节

    Args:
        month: 月份 (1-12)

    Returns:
        季节字符串: 'winter', 'spring', 'summer', 'autumn'

    Raises:
        ValueError: 如果月份不在 1-12 范围内
    """
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month: {month}. Must be between 1 and 12.")

    if month in [12, 1, 2]:
        return 'winter'
    elif month in [3, 4, 5]:
        return 'spring'
    elif month in [6, 7, 8]:
        return 'summer'
    else:  # 9, 10, 11
        return 'autumn'


def parse_range_value_seasonal(value_str: str, month: int, field_name: str) -> float:
    """根据季节和字段类型智能解析范围值

    Args:
        value_str: 范围值字符串 (如 "30-50", "7-10℃")
        month: 月份 (1-12)
        field_name: 字段名称

    Returns:
        解析后的数值

    策略:
        - 水泵频率/温差: 冬季取下限, 夏季取上限, 春秋取平均
        - 供水温度: 冬季取上限, 夏季取下限, 春秋取平均 (相反)
    """
    # 特殊处理温差字段，确保在3-5度范围内
    if field_name in ['cooling_water_temp_diff', 'freezing_water_temp_diff']:
        # 提取范围值（支持多种分隔符：- / , | ~）
        range_match = re.search(r'(\d+\.?\d*)\s*[-~/,|]\s*(\d+\.?\d*)', value_str)
        if range_match:
            start = float(range_match.group(1))
            end = float(range_match.group(2))
            
            # 确保 start 是最小值，end 是最大值
            min_val = min(start, end)
            max_val = max(start, end)
            
            # 将范围限制在3-5度之间
            min_val = max(3.0, min_val)
            max_val = min(5.0, max_val)
            
            # 如果超出范围，则统一使用边界值
            if min_val > 5.0:
                min_val = 5.0
            if max_val < 3.0:
                max_val = 3.0
            
            # 判断季节
            season = get_season(month)
            
            if season == 'winter':
                return min_val  # 冬季取下限
            elif season == 'summer':
                return max_val  # 夏季取上限
            else:  # spring or autumn
                return (min_val + max_val) / 2
        else:
            # 如果不是范围值，直接解析并限制在3-5度范围内
            parsed_value = parse_value(value_str)
            if parsed_value is not None:
                return max(3.0, min(5.0, parsed_value))
            else:
                return None
    else:
        # 非温差字段，按原逻辑处理
        # 提取范围值（支持多种分隔符：- / , | ~）
        range_match = re.search(r'(\d+\.?\d*)\s*[-~/,|]\s*(\d+\.?\d*)', value_str)
        if not range_match:
            return None

        start = float(range_match.group(1))
        end = float(range_match.group(2))

        # 确保 start 是最小值，end 是最大值
        min_val = min(start, end)
        max_val = max(start, end)

        # 判断季节
        season = get_season(month)

        # 供水温度字段白名单：使用精确匹配而非子串匹配
        SUPPLY_TEMP_FIELDS = {'chiller_supply_temp', 'supply_temp'}
        is_supply_temp = field_name in SUPPLY_TEMP_FIELDS

        if season == 'winter':
            return max_val if is_supply_temp else min_val
        elif season == 'summer':
            return min_val if is_supply_temp else max_val
        else:  # spring or autumn
            return (min_val + max_val) / 2


def parse_value(value, month=None, field_name=None):
    """解析文本值为数值，支持季节性范围值处理

    Args:
        value: 单元格值
        month: 月份 (1-12)，用于季节性范围值解析
        field_name: 字段名称，用于判断是否需要相反逻辑

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

    # 处理工频/定频标记：包含 fixed/工频/定频 关键词时，返回明确频率或默认50Hz
    # 如 "Fixed"、"Fixed speed"、"Fixed: 50Hz"、"工频"、"定频"
    if re.search(r'(?i)\bfixed\b|工频|定频', value_str):
        # 优先提取明确的频率数字（如 "Fixed: 50Hz"）
        freq_in_text = re.search(r'(\d+\.?\d*)\s*(?:Hz|HZ|hz)', value_str)
        if freq_in_text:
            return float(freq_in_text.group(1))
        return 50.0  # 工频默认50Hz

    # 处理变频标签无数值：仅填了 "VFD"、"变频" 但没数字，视为数据缺失
    vfd_only = re.search(r'(?i)\bVFD\b|变频', value_str)
    if vfd_only and not re.search(r'\d', value_str):
        return None

    # 处理范围格式 - 如果提供了月份和字段名，使用季节性解析
    # 支持多种分隔符：- / , | ~
    range_match = re.search(r'(\d+\.?\d*)\s*[-~/,|]\s*(\d+\.?\d*)', value_str)
    if range_match:
        if month is not None and field_name is not None:
            # 使用季节性解析
            return parse_range_value_seasonal(value_str, month, field_name)
        else:
            # 向后兼容：默认取平均值
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
    """从项目总体情况表中提取地区信息
    
    Returns:
        地区字符串（华南/华东/华中/西南/西北/华北/东北/东南亚），如果无法推断则返回 None
    """
    # 收集所有匹配的地区候选
    all_region_candidates = []
    
    for idx, row in df.iterrows():
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val)
            val_lower = val_str.lower()
            regions = {
                '华南': ['广东', '广西', '海南', '福建', '深圳', '广州', '厦门'],
                '华东': ['上海', '江苏', '浙江', '安徽', '江西', '南京', '杭州'],
                '华中': ['湖北', '湖南', '河南', '武汉', '长沙'],
                '西南': ['四川', '重庆', '贵州', '云南', '西藏', '成都'],
                '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆', '西安', '兰州'],
                '华北': ['北京', '天津', '河北', '山西', '内蒙古'],
                '东北': ['辽宁', '吉林', '黑龙江', '沈阳', '大连', '长春', '哈尔滨'],
                '东南亚': ['马来西亚', '泰国', '越南', '新加坡', '菲律宾']
            }

            # 英文关键词映射（全小写匹配）
            regions_en = {
                '华南': ['guangdong', 'guangzhou', 'shenzhen', 'dongguan', 'foshan', 'xiamen', 'fujian'],
                '华东': ['shanghai', 'jiangsu', 'zhejiang', 'nanjing', 'hangzhou', 'suzhou'],
                '华中': ['hubei', 'wuhan', 'hunan', 'changsha', 'henan', 'zhengzhou'],
                '西南': ['sichuan', 'chengdu', 'chongqing', 'yunnan', 'kunming', 'guizhou'],
                '西北': ['shaanxi', 'xian', 'gansu', 'lanzhou', 'xinjiang'],
                '华北': ['beijing', 'tianjin', 'hebei', 'shijiazhuang'],
                '东北': ['liaoning', 'shenyang', 'dalian', 'jilin', 'changchun', 'harbin', 'heilongjiang']
            }
            
            # 优先检查东南亚具体城市（中文，直接返回城市名，与 infer_region_from_text 保持一致）
            sea_cn_cities = ["吉隆坡", "曼谷", "罗勇", "大城府", "槟城",
                             "胡志明市", "河内", "北宁省", "马尼拉",
                             "新加坡", "雅加达", "金边", "仰光"]
            for city in sea_cn_cities:
                if city in val_str:
                    return city

            # 英文东南亚城市/国家名优先检查（返回对应中文城市名）
            sea_en_mappings = [
                ('ho chi minh', '胡志明市'),
                ('hanoi', '河内'),
                ('vietnam', '胡志明市'),
                ('bangkok', '曼谷'),
                ('rayong', '罗勇'),
                ('ayutthaya', '大城府'),
                ('thailand', '曼谷'),
                ('kuala lumpur', '吉隆坡'),
                ('penang', '槟城'),
                ('malaysia', '吉隆坡'),
                ('manila', '马尼拉'),
                ('philippines', '马尼拉'),
                ('singapore', '新加坡'),
                ('indonesia', '雅加达'),
                ('jakarta', '雅加达'),
                ('cambodia', '金边'),
                ('phnom penh', '金边'),
                ('myanmar', '仰光'),
                ('yangon', '仰光'),
            ]
            for en_kw, cn_city in sea_en_mappings:
                if en_kw in val_lower:
                    return cn_city

            # 其他国家的英文地区关键词（返回区域名）
            for region_en, keywords_en in regions_en.items():
                if region_en == '东南亚':
                    continue  # 东南亚已在上面处理
                for kw in keywords_en:
                    if kw in val_lower:
                        all_region_candidates.append((len(kw), region_en, kw))

            # 按关键词长度排序，优先匹配更长的关键词
            region_candidates = []
            for region, keywords in regions.items():
                for keyword in keywords:
                    if keyword in val_str:
                        region_candidates.append((len(keyword), region, keyword))
            
            # 收集所有匹配的候选
            all_region_candidates.extend(region_candidates)
    
    # 按关键词长度降序排序，优先匹配更长的关键词
    if all_region_candidates:
        all_region_candidates.sort(key=lambda x: -x[0])
        return all_region_candidates[0][1]
    
    return None


def extract_station_name(df):
    """从冷站工作表中提取站房名称

    Args:
        df: 冷站工作表的 DataFrame

    Returns:
        站房名称字符串，如果未找到则返回 None
    """
    # 在前10行查找"站房名称"或"Name of Plant"字段（中英文兼容）
    for idx in range(min(10, len(df))):
        row = df.iloc[idx]
        for col_idx, val in enumerate(row):
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if '站房名称' in val_str or 'Name of Plant' in val_str:
                # 站房名称的值通常在右侧第2列（跳过1列）
                if col_idx + 2 < len(row):
                    station_name = df.iloc[idx, col_idx + 2]
                    if pd.notna(station_name):
                        return str(station_name).strip()
                # 英文版可能在右侧第1列
                if col_idx + 1 < len(row):
                    station_name = df.iloc[idx, col_idx + 1]
                    if pd.notna(station_name):
                        return str(station_name).strip()
                return None
    return None


def infer_region_from_text(text):
    """从文本（站房名称或文件名）推断项目地区

    Args:
        text: 文本字符串（站房名称、文件名等）

    Returns:
        国内地区字符串（华南/华东/华中/西南/西北/华北/东北），东南亚返回具体城市名称（吉隆坡/曼谷/罗勇/大城府/槟城/胡志明市/北宁省/马尼拉），如果无法推断则返回 None
    """
    if not text or pd.isna(text):
        return None

    text_str = str(text)
    text_lower = text_str.lower()

    # 地区关键词映射（扩展了城市列表以提高识别率）
    regions = {
        '华南': ['广东', '广西', '海南', '福建', '深圳', '广州', '厦门', '珠海', '东莞', '佛山', '惠州', '中山', '江门', '湛江', '汕头'],
        '华东': ['上海', '江苏', '浙江', '安徽', '江西', '南京', '杭州', '苏州', '无锡', '宁波', '合肥', '南昌', '温州', '常州', '徐州'],
        '华中': ['湖北', '湖南', '河南', '武汉', '长沙', '郑州', '洛阳', '株洲', '岳阳', '宜昌'],
        '西南': ['四川', '重庆', '贵州', '云南', '西藏', '成都', '贵阳', '昆明', '拉萨'],
        '西北': ['陕西', '甘肃', '青海', '宁夏', '新疆', '西安', '兰州', '银川', '乌鲁木齐', '西宁'],
        '华北': ['北京', '天津', '河北', '山西', '内蒙古', '石家庄', '太原', '呼和浩特', '唐山', '保定', '廊坊'],
        '东北': ['辽宁', '吉林', '黑龙江', '沈阳', '大连', '长春', '哈尔滨', '鞍山', '抚顺']
    }

    # 优先检查东南亚城市（中文，直接返回城市名称）
    if "吉隆坡" in text_str:
        return "吉隆坡"
    if "曼谷" in text_str:
        return "曼谷"
    if "罗勇" in text_str:
        return "罗勇"
    if "大城府" in text_str:
        return "大城府"
    if "槟城" in text_str:
        return "槟城"
    if "胡志明市" in text_str:
        return "胡志明市"
    if "北宁省" in text_str:
        return "北宁省"
    if "马尼拉" in text_str:
        return "马尼拉"

    # 英文东南亚城市/国家名（大小写不敏感，返回对应中文城市名）
    sea_en_mappings = [
        ('ho chi minh', '胡志明市'),
        ('hanoi', '河内'),
        ('vietnam', '胡志明市'),
        ('bangkok', '曼谷'),
        ('rayong', '罗勇'),
        ('ayutthaya', '大城府'),
        ('thailand', '曼谷'),
        ('kuala lumpur', '吉隆坡'),
        ('penang', '槟城'),
        ('malaysia', '吉隆坡'),
        ('manila', '马尼拉'),
        ('philippines', '马尼拉'),
        ('singapore', '新加坡'),
        ('indonesia', '雅加达'),
        ('jakarta', '雅加达'),
        ('cambodia', '金边'),
        ('phnom penh', '金边'),
        ('myanmar', '仰光'),
        ('yangon', '仰光'),
    ]
    for en_kw, cn_city in sea_en_mappings:
        if en_kw in text_lower:
            return cn_city
    
    # 按关键词长度排序，优先匹配更长的关键词
    region_candidates = []
    for region, keywords in regions.items():
        for keyword in keywords:
            if keyword in text_str:
                region_candidates.append((len(keyword), region, keyword))
    
    # 按关键词长度降序排序，优先匹配更长的关键词
    if region_candidates:
        region_candidates.sort(key=lambda x: -x[0])
        return region_candidates[0][1]
    
    return None


def extract_region_from_filename(filepath):
    """从文件名提取项目地区

    Args:
        filepath: 文件路径字符串

    Returns:
        地区字符串（华南/华东/华中/西南/西北/华北/东北/东南亚），如果无法推断则返回 None
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


_MONTH_HEADER_RE = regex_module.compile(r'^\s*(\d{1,2})\s*月\s*$')


def is_month_header_row(df, row_idx: int, col_start: int) -> bool:
    """判断某行是否是"月份表头"行（如 1月/2月/.../12月）

    用于防止把表头行误当成数据行——历史上月份表头曾被解析成
    total_energy=1,2,3...（把"N月"里的数字读成了能耗），属于静默错数。
    注意：必须带"月"字才算表头，纯数字行（如供水温度 7,7,7...）是数据。
    """
    if row_idx is None or row_idx >= len(df):
        return False
    hit = 0
    for offset in range(12):
        col = col_start + offset
        if col >= df.shape[1]:
            break
        val = df.iloc[row_idx, col]
        if pd.isna(val):
            continue
        m = _MONTH_HEADER_RE.match(str(val).strip())
        if m and 1 <= int(m.group(1)) <= 12:
            hit += 1
    return hit >= 3


def extract_energy_from_meter_sheet(xls: pd.ExcelFile, exclude_sheet: Optional[str] = None) -> Optional[Dict[int, float]]:
    """从电表逐柜记录表中解析冷站月度用电量（深度调研模板变体）

    适配的表结构特征（如上海和元调研表的 Sheet1）：
    - 表头一行中含多个 "N月" 标签，"N月"列下的数值为该月当月用电量（kWh）
    - 设备柜行（名称含 冷却塔/冷却水泵/冷冻水泵/冷水机组/泵 等）逐柜记录
    - 表尾可能有 合计/占比 汇总块，需排除

    Returns:
        {月份: 万kWh}；未识别到电表结构时返回 None
    """
    device_keywords = ['冷却塔', '冷却水泵', '冷冻水泵', '冷水机组', '冷冻机组', '冷却泵', '冷冻泵']
    exclude_keywords = ['合计', '占比', '%', '汇总']

    for sheet in xls.sheet_names:
        if sheet == exclude_sheet:
            continue
        try:
            df = pd.read_excel(xls, sheet_name=sheet, header=None)
        except Exception:
            continue

        # 定位表头行：包含 >=4 个 "N月" 标签
        for r in range(min(len(df), 10)):
            month_cols: Dict[int, int] = {}
            for c in range(df.shape[1]):
                val = df.iloc[r, c]
                if pd.isna(val):
                    continue
                m = _MONTH_HEADER_RE.match(str(val).strip())
                if m and 1 <= int(m.group(1)) <= 12:
                    month_cols[int(m.group(1))] = c
            if len(month_cols) < 4:
                continue

            # 汇总设备柜行。注意：表中" N月"列下的值有的是当月增量（要累加），
            # 有的是累计读数（不能累加，否则能耗虚高数倍）。判别方法：
            # 当月增量必然小于两侧相邻的累计读数（抄表值单调递增）。
            sums = {m: 0.0 for m in month_cols}
            device_rows = 0
            for rr in range(r + 1, len(df)):
                label = ' '.join(
                    str(df.iloc[rr, c]) for c in range(0, min(6, df.shape[1])) if pd.notna(df.iloc[rr, c])
                )
                if not label or not any(k in label for k in device_keywords):
                    continue
                if any(k in label for k in exclude_keywords):
                    continue
                added = 0
                for m, c in sorted(month_cols.items()):
                    if c >= df.shape[1]:
                        continue
                    v = df.iloc[rr, c]
                    if pd.isna(v):
                        continue
                    try:
                        num = float(v)
                    except (TypeError, ValueError):
                        continue
                    if num <= 0:
                        continue
                    prev_v = df.iloc[rr, c - 1] if c - 1 >= 0 else None
                    next_v = df.iloc[rr, c + 1] if c + 1 < df.shape[1] else None

                    def _num(x):
                        try:
                            return float(x)
                        except (TypeError, ValueError):
                            return None

                    p, n = _num(prev_v), _num(next_v)
                    # 与两侧累计读数比较；两侧都不可用时视为增量
                    is_delta = True
                    if p is not None and n is not None:
                        is_delta = num < min(p, n)
                    elif p is not None:
                        is_delta = num < p
                    elif n is not None:
                        is_delta = num < n
                    if is_delta:
                        sums[m] += num
                        added += 1
                if added:
                    device_rows += 1

            if device_rows < 3:
                continue

            # 单位判断：电表原始值为 kWh（逐柜累计的月度电量），转为万kWh
            annual_total = sum(sums.values())
            scale = 1e-4 if annual_total > 1000 else 1.0
            result = {m: round(s * scale, 2) for m, s in sums.items() if s > 0}
            if len(result) >= 4:
                return result
    return None


def detect_month_column_start(df, row_idx):
    """检测指定行的月份列起始位置

    通过在该行查找 '1月' / 'Jan' 关键字来确定月份数据的起始列。
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

    # 在该行查找 '1月' 或 'Jan' 关键字（中英文兼容）
    row = df.iloc[row_idx]
    for col_idx in range(len(row)):
        cell_value = row.iloc[col_idx]
        if pd.notna(cell_value):
            cell_str = str(cell_value).strip()
            if '1月' in cell_str or cell_str.lower() == 'jan':
                return col_idx

    return None



def find_cold_station_sheet(xls: pd.ExcelFile) -> Optional[str]:
    """查找包含冷站数据的工作表

    支持多种命名模式（中英文）：
    - 中文: '冷站', '1#冷站', '2#冷站' 等
    - 英文: 'Chiller Plant' 等
    - 任何包含'冷站'或'Chiller'关键字的工作表

    优先级：
    1. 如果只有一个匹配工作表，直接使用
    2. 如果有多个，优先使用包含"设备运行规律"/"Equipment Operation Patterns"
       或"用电情况统计"/"Electricity Consumption Statistics"的sheet
    3. 如果没有包含运行数据的sheet，优先使用'冷站详情'
    4. 如果没有1#冷站，使用第一个匹配sheet

    Args:
        xls: Excel文件对象

    Returns:
        工作表名称，如果未找到则返回 None
    """
    # 查找所有包含"冷站"或"Chiller"关键字的工作表（中英文兼容）
    cold_station_sheets = [
        sheet for sheet in xls.sheet_names
        if '冷站' in sheet or 'chiller' in sheet.lower()
    ]

    if not cold_station_sheets:
        return None

    # 如果只有一个匹配，直接返回
    if len(cold_station_sheets) == 1:
        return cold_station_sheets[0]

    # 如果有多个，智能查找包含月度运行数据的sheet
    for sheet_name in cold_station_sheets:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            # 查找是否包含运行数据关键词（中英文）
            for idx in range(min(50, len(df))):
                row = df.iloc[idx]
                for val in row:
                    if pd.notna(val) and isinstance(val, str):
                        val_lower = val.lower()
                        if any(k in val for k in ['设备运行规律', '用电情况统计']):
                            return sheet_name
                        if any(k in val_lower for k in ['equipment operation patterns',
                                                        'electricity consumption statistics']):
                            return sheet_name
        except Exception:
            continue

    # 如果没有找到包含运行数据的sheet，优先使用'冷站详情'
    if '冷站详情' in cold_station_sheets:
        return '冷站详情'

    # 如果有多个冷站，优先使用"1#冷站"
    if '1#冷站' in cold_station_sheets:
        return '1#冷站'

    # 否则使用第一个匹配sheet
    return cold_station_sheets[0]


def detect_station_type(workbook) -> dict:
    """
    基于调研表内容推断站房类型

    Args:
        workbook: openpyxl.Workbook 对象

    Returns:
        {
            "station_type": "standard" | "secondary_pump" | "unsupported",
            "confidence": "high" | "medium" | "low",
            "reason": "识别原因描述"
        }
    """
    try:
        # 获取所有sheet的文本内容
        all_sheets_text = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                all_sheets_text.extend([str(cell) for cell in row if cell])

        # 合并所有文本用于匹配
        full_text = " ".join(all_sheets_text).lower()

        # 检测不支持的特殊类型（优先级最高）
        unsupported_keywords = {
            "热水泵": ["热水泵", "热水循环泵"],
            "水蓄冷": ["蓄冷", "蓄冰", "冰蓄冷", "水蓄冷"],
            "中低温机组": ["中温机组", "低温机组", "中低温"]
        }

        for feature, keywords in unsupported_keywords.items():
            for keyword in keywords:
                if keyword in full_text:
                    return {
                        "station_type": "unsupported",
                        "confidence": "high",
                        "reason": f"检测到{feature}特征: '{keyword}'，该类型站房不在自动评估范围内"
                    }

        # 检测二次泵特征
        secondary_pump_keywords = [
            "一次冷冻泵", "二次冷冻泵",
            "一次泵", "二次泵",
            "冷冻一次泵", "冷冻二次泵"
        ]

        has_secondary_pump_keyword = any(kw in full_text for kw in secondary_pump_keywords)

        if has_secondary_pump_keyword:
            # 有关键词，还需要检查二次泵数据行是否有实际数据
            # 遍历每个sheet的数据，检查二次泵数据行
            has_secondary_pump_data = False

            for sheet in workbook.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    row_text = " ".join([str(cell).lower() for cell in row if cell])
                    # 检查是否包含二次泵数据关键词且有实际数据（如品牌、功率等）
                    if any(kw in row_text for kw in ["二次泵", "冷冻二次泵"]):
                        # 检查该行是否有实际数据（不仅仅是表头）
                        # 排除仅包含表头关键词的行
                        non_null_cells = [cell for cell in row if cell is not None and str(cell).strip()]
                        if len(non_null_cells) >= 3:  # 至少有3个非空单元格才认为有实际数据
                            has_secondary_pump_data = True
                            break
                if has_secondary_pump_data:
                    break

            if has_secondary_pump_data:
                return {
                    "station_type": "secondary_pump",
                    "confidence": "high",
                    "reason": "检测到一次泵/二次泵分离特征且有实际数据"
                }
            else:
                return {
                    "station_type": "standard",
                    "confidence": "high",
                    "reason": "二次泵字段为空，识别为一次泵系统"
                }

        # 默认为标准站房
        return {
            "station_type": "standard",
            "confidence": "medium",
            "reason": "未检测到二次泵或特殊类型特征，默认为标准站房"
        }

    except Exception as e:
        # 检测失败，默认标准版（低置信度）
        return {
            "station_type": "standard",
            "confidence": "low",
            "reason": f"站房类型检测失败: {str(e)}，默认使用标准版"
        }


def extract_electricity_price(df) -> Optional[float]:
    """从冷站sheet中提取电单价

    扫描所有单元格，用正则匹配电单价相关文本。

    Args:
        df: 冷站sheet的DataFrame

    Returns:
        电单价(元/kWh)，未找到则返回None
    """
    patterns = [
        r'电单价[：:]\s*(\d+\.?\d*)',
        r'电价[：:]\s*(\d+\.?\d*)',
        r'(\d+\.?\d*)\s*元[/每](?:度|kWh|kwh)',
        r'综合.*?[：:]\s*(\d+\.?\d*)\s*元',
    ]

    for row_idx in range(len(df)):
        for col_idx in range(len(df.columns)):
            val = df.iloc[row_idx, col_idx]
            if not isinstance(val, str):
                continue
            if '电' not in val:
                continue
            for pattern in patterns:
                match = re.search(pattern, val)
                if match:
                    price = float(match.group(1))
                    if 0.1 <= price <= 3.0:
                        return price
    return None


def extract_data_from_excel(survey_excel_path: str, original_filename: Optional[str] = None) -> Dict[str, Any]:
    """从 Excel 文件提取数据

    Args:
        survey_excel_path: Excel 文件路径
        original_filename: 原始文件名(优先用于地区推断)
    """
    xls = pd.ExcelFile(survey_excel_path)

    # 查找冷站工作表
    cold_station_sheet = find_cold_station_sheet(xls)
    if not cold_station_sheet:
        return {
            "error": True,
            "message": "找不到包含冷站数据的工作表,请确认上传了正确的文件"
        }

    df = pd.read_excel(xls, sheet_name=cold_station_sheet, header=None)

    # 提取项目地区（三级优先级）
    project_region = None

    # 优先级1: 从文件名推断地区（优先使用原始文件名）
    # 文件名通常更准确地反映项目的实际位置
    filename_to_infer = original_filename if original_filename else survey_excel_path
    project_region = extract_region_from_filename(filename_to_infer)

    # 优先级2: 从站房名称推断地区
    if not project_region:
        station_name = extract_station_name(df)
        if station_name:
            project_region = infer_region_from_text(station_name)

    # 优先级3: 从项目总体情况表提取（中英文兼容）
    if not project_region:
        overview_sheet = None
        for sheet in xls.sheet_names:
            if '项目总体情况' in sheet or 'overall project information' in sheet.lower():
                overview_sheet = sheet
                break
        if overview_sheet:
            df_overview = pd.read_excel(xls, sheet_name=overview_sheet, header=None)
            project_region = extract_region(df_overview)

    # 查找关键行（中英文关键词兼容）
    # 注意：部分模板变体（如深度调研版）只写"供水温度"而非"冷机供水温度"，
    # 精确关键词匹配失败后用短关键词兜底
    row_mappings = {
        'chiller_supply_temp': ['冷机供水温度', 'Chiller Supply Temp', '供水温度'],
        'cooling_pump_freq': ['冷却泵运行频率', 'Cooling Pump Freq', '冷却泵频率'],
        'cooling_water_temp_diff': ['冷却侧供回水温差', 'Cooling Side ΔT', '冷却水温差'],
        'freezing_pump_freq': ['冷冻泵运行频率', 'Chilled Pump Freq', '冷冻泵频率'],
        'freezing_water_temp_diff': ['冷冻侧供回水温差', 'Chilled Side ΔT', '冷冻水温差'],
        'cooling_tower_outlet_temp': ['冷却塔出水温度', 'Cooling Tower Outlet Temp'],
        'total_energy': ['整个冷站', '万kWh', 'Entire Chiller Plant', '总能耗']
    }

    # 动态查找"设备运行规律"/"Equipment Operation Patterns"标题行
    equipment_section_row = find_row_by_keyword(
        df,
        ['设备运行规律', '冷机运行规律', 'Equipment Operation Patterns'],
        start_row=0, end_row=100
    )
    if equipment_section_row is None:
        return {
            "error": True,
            "message": "未能识别调研表中的'设备运行规律'部分,请确认上传了正确的文件"
        }

    # 从设备运行规律标题行向下查找月份行（中英文兼容）
    equipment_month_row_idx = find_row_by_keyword(
        df,
        ['月份', '备注', 'Month', 'Remarks'],
        start_row=equipment_section_row, end_row=equipment_section_row + 10
    )
    if equipment_month_row_idx is None:
        return {
            "error": True,
            "message": "未能识别调研表中的设备运行规律月度数据行,请确认上传了正确的文件"
        }

    # 检测设备运行规律部分的月份列起始位置
    equipment_col_start = detect_month_column_start(df, equipment_month_row_idx)
    if equipment_col_start is None:
        equipment_col_start = 3  # 默认 D 列

    # 动态查找"用电情况统计"/"Electricity Consumption Statistics"标题行
    energy_section_row = find_row_by_keyword(
        df,
        ['用电情况统计', 'Electricity Consumption Statistics'],
        start_row=equipment_month_row_idx, end_row=len(df)
    )

    # 从用电情况统计标题行向下查找月份行
    energy_month_row_idx = None
    if energy_section_row is not None:
        energy_month_row_idx = find_row_by_keyword(
            df,
            ['月份', 'Month'],
            start_row=energy_section_row, end_row=energy_section_row + 10
        )

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
            if row_idx is not None and not is_month_header_row(df, row_idx, equipment_col_start):
                data_rows[key] = row_idx
        # 用电情况字段：从用电情况统计部分开始查找
        else:
            if energy_month_row_idx is not None:
                row_idx = find_row_by_keyword(df, keywords, start_row=energy_month_row_idx, end_row=energy_month_row_idx + 5)
                if row_idx is not None and not is_month_header_row(df, row_idx, energy_col_start):
                    # 检查找到的行数据是否合理（万kWh应该<100）
                    # 如果第一个月份列的值>100，说明这是kWh单位的行，需要跳到下一行
                    if energy_col_start is not None and energy_col_start < len(df.columns):
                        first_month_val = df.iloc[row_idx, energy_col_start]
                        if pd.notna(first_month_val) and first_month_val > 100:
                            # 当前行是kWh，检查下一行
                            if row_idx + 1 < len(df):
                                next_row_val = df.iloc[row_idx + 1, energy_col_start]
                                if pd.notna(next_month_val := next_row_val) and next_month_val < 100:
                                    row_idx = row_idx + 1
                    data_rows[key] = row_idx
            # 不再使用硬编码行号兜底：关键词匹配失败时盲读固定行，
            # 曾把"月份"表头行解析成能耗 1,2,3...（静默错数）。
            # 找不到就留空，由电表解析器或质量检查兜底。

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
                        # 传递月份和字段名以支持季节性范围值解析
                        parsed = parse_value(value, month=month, field_name=field)
                        
                        # 温差边界处理：冷冻水和冷却水温差正常范围3-5°
                        if field in ['cooling_water_temp_diff', 'freezing_water_temp_diff'] and parsed is not None:
                            if parsed < 3:
                                parsed = 3.0  # 低于3度按3度处理
                            elif parsed > 5:
                                parsed = 5.0  # 超过5度按5度处理
                        
                        month_record[field] = parsed
                        if field == 'total_energy' and parsed is not None:
                            valid_energy_count += 1

        monthly_data.append(month_record)

    # 深度调研模板变体兜底：冷站 sheet 的"用电情况统计"为空、关键词匹配不到时，
    # 尝试从工作簿中的电表逐柜记录表（如 Sheet1）按"N月"列汇总月度用电量
    energy_source = 'survey_sheet'
    if valid_energy_count == 0:
        meter_energy = extract_energy_from_meter_sheet(xls, exclude_sheet=cold_station_sheet)
        if meter_energy:
            for month_record in monthly_data:
                m = month_record['month']
                if month_record['total_energy'] is None and m in meter_energy:
                    month_record['total_energy'] = meter_energy[m]
                    valid_energy_count += 1
            energy_source = 'meter_sheet'

    # 标记模板实际可提供的字段（用于完整率计算：分母按可用字段计，
    # 而不是把模板本身没有的字段算作"数据缺失"）
    available_fields = [
        field for field in ['total_energy', 'chiller_supply_temp', 'cooling_pump_freq',
                            'cooling_water_temp_diff', 'freezing_pump_freq',
                            'freezing_water_temp_diff', 'cooling_tower_outlet_temp']
        if any(rec.get(field) is not None for rec in monthly_data)
    ]

    # 注意：不再强制要求至少3个月数据，让质量检查报告来反馈数据完整性问题
    # 这样即使是空白模板也能返回提取结果和详细的质量报告

    # 提取电单价
    electricity_price = extract_electricity_price(df)

    # 新增：提取站房类型（使用 openpyxl.Workbook）
    try:
        wb_openpyxl = openpyxl.load_workbook(survey_excel_path, read_only=True, data_only=True)
        station_type_info = detect_station_type(wb_openpyxl)
        wb_openpyxl.close()
    except Exception as e:
        # 如果加载失败（如测试中的 mock 文件），使用默认值
        station_type_info = {
            "station_type": "standard",
            "confidence": "low",
            "reason": f"无法加载工作簿进行站房类型检测: {str(e)}"
        }

    return {
        "project_region": project_region,
        "electricity_price": electricity_price,
        "station_type": station_type_info["station_type"],
        "station_type_confidence": station_type_info["confidence"],
        "station_type_reason": station_type_info["reason"],
        "energy_source": energy_source,
        "available_fields": available_fields,
        "monthly_data": monthly_data
    }


# ============= 数据质量检查部分 (来自 check_data_quality.py) =============

class DataQualityChecker:
    """数据质量检查器"""

    RANGES = {
        'chiller_supply_temp': (5, 15, '°C'),
        'cooling_pump_freq': (20, 50, 'Hz'),
        'freezing_pump_freq': (20, 50, 'Hz'),
        'cooling_water_temp_diff': (3, 5, '℃'),      # 修改：正常范围3-5℃
        'freezing_water_temp_diff': (3, 5, '℃'),    # 修改：正常范围3-5℃
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
        available_fields = set(self._available_fields())

        for idx, month_data in enumerate(monthly_data):
            month = month_data.get('month', idx + 1)
            self._check_total_energy(month, month_data)
            self._check_chiller_supply_temp(month, month_data)

            for field in self.MONTHLY_FIELDS[2:]:
                self._check_field(month, month_data, field)

            # 模板本身没有的字段缺失不算数据质量问题，降级为提示
            for field in self.MONTHLY_FIELDS:
                if field not in available_fields and month_data.get(field) is None:
                    self.issues.append({
                        'field': f'monthly_data[{month-1}].{field}',
                        'severity': 'low',
                        'type': 'not_in_template',
                        'message': f'{month}月{self._get_field_name(field)}为调研表模板未包含字段，'
                                   f'将由行业默认值填充并标注置信度'
                    })

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

    def _available_fields(self) -> List[str]:
        """模板实际可提供的月度字段

        完整率只应衡量"模板有的字段填了几成"。部分模板变体（如深度调研版）
        本身没有泵频率/温差等行，把它们算进分母会把完整率压到 0.2 左右，
        误触发低置信度中断。未标记 available_fields 的旧数据按全部 7 字段计。
        """
        available = self.data.get('available_fields')
        if available:
            return [f for f in self.MONTHLY_FIELDS if f in available]
        return list(self.MONTHLY_FIELDS)

    def calculate_completeness(self) -> float:
        """计算数据完整率"""
        monthly_data = self.data.get('monthly_data', [])
        if not monthly_data:
            return 0.0

        fields = self._available_fields()
        total_points = len(monthly_data) * len(fields)
        non_null_points = 0

        for month_data in monthly_data:
            for field in fields:
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

def extract_and_check_data(survey_excel_path: str, output_json_path: str, original_filename: Optional[str] = None):
    """提取数据并进行质量检查

    Args:
        survey_excel_path: 调研表路径
        output_json_path: 输出路径
        original_filename: 原始文件名(用于地区推断)
    """
    try:
        # 步骤 1: 提取数据,传递原始文件名
        extracted_data = extract_data_from_excel(survey_excel_path, original_filename)

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

        print(f" 数据提取和质量检查完成: {output_json_path}")
        print(f"项目地区: {extracted_data.get('project_region')}")
        print(f"站房类型: {extracted_data.get('station_type')} (置信度: {extracted_data.get('station_type_confidence')})")
        print(f"识别依据: {extracted_data.get('station_type_reason')}")
        print(f"\n{quality_report['summary']}")
    except Exception as e:
        import traceback
        error_result = {
            "error": True,
            "message": f"执行过程中发生错误: {str(e)}",
            "traceback": traceback.format_exc()
        }
        output_path = Path(output_json_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        print(f" 执行出错: {str(e)}")
        print(traceback.format_exc())


def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print('用法: python extract_and_check_data.py <调研表Excel路径> <输出JSON路径> [原始文件名]')
        sys.exit(1)

    survey_excel_path = sys.argv[1]
    output_json_path = sys.argv[2]
    original_filename = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        extract_and_check_data(survey_excel_path, output_json_path, original_filename)
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()