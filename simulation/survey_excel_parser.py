"""调研表 Excel 解析器

从中央空调节能调研表 Excel 中结构化提取：
- 主机（冷机）参数：台数、制冷量、功率、COP、变频、机型、品牌、型号等
- 冷却泵 / 冷冻泵参数：台数、流量、功率、扬程、变频、品牌
- 冷却塔参数：台数、风机数、单台风机功率、流量、变频、品牌
- 月度运行数据：月度冷机台数、供水温度、泵频率、温差、冷却塔出水温度
- 站房基础信息：站房名称

输出格式对齐 simulation/input_parser.build_plant_config_from_extracted_data() 的输入：

    {
        "chillers": [...],                # 主机列表
        "chw_pumps": [...],               # 冷冻泵列表
        "cw_pumps": [...],                # 冷却泵列表
        "towers": [...],                  # 冷却塔列表
        "monthly_data": {"1": {...}, ...},# 1-12月运行数据
        "monthly_chiller_count": [...],   # 12个月冷机台数
        "station_name": "...",
    }

调研表布局（动态定位，行号不固定）：
    B 列含 "冷机" / "冷却泵" / "冷冻泵" / "冷却塔" → 设备表头行
    表头下一行起为数据行，直到空行或下一个表头
    B 列含 "冷机运行台数" / "冷却泵运行频率" 等 → 月度数据行
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet


# ── 单位/关键词识别 ──────────────────────────────────────────

_VARIABLE_FREQ_KEYWORDS = ("变频", "VFD", "vfd", "inverter", "INV")
_FIXED_FREQ_KEYWORDS = ("工频", "定频", "fixed", "D fixed")
_CHILLER_TYPE_KEYWORDS = (
    ("离心", "离心式"),
    ("螺杆", "螺杆式"),
    ("磁悬浮", "磁悬浮"),
    ("往复", "往复式"),
    ("涡旋", "涡旋式"),
)
_REGION_KEYWORDS = {
    "华南": ["广东", "广西", "海南", "福建", "深圳", "广州", "厦门", "珠海",
             "东莞", "佛山", "惠州", "中山", "江门", "湛江", "汕头"],
    "华东": ["上海", "江苏", "浙江", "安徽", "江西", "南京", "杭州", "苏州",
             "无锡", "宁波", "合肥", "南昌", "温州", "常州", "徐州"],
    "华中": ["湖北", "湖南", "河南", "武汉", "长沙", "郑州", "洛阳", "株洲", "岳阳"],
    "西南": ["四川", "重庆", "贵州", "云南", "西藏", "成都", "贵阳", "昆明", "拉萨"],
    "西北": ["陕西", "甘肃", "青海", "宁夏", "新疆", "西安", "兰州", "银川",
             "乌鲁木齐", "西宁"],
    "华北": ["北京", "天津", "河北", "山西", "内蒙古", "石家庄", "太原",
             "呼和浩特", "唐山", "保定", "廊坊"],
    "东北": ["辽宁", "吉林", "黑龙江", "沈阳", "大连", "长春", "哈尔滨",
             "鞍山", "抚顺"],
}


def _infer_region(text: str) -> Optional[str]:
    """从文本中识别地区关键词，返回大区名（华南/华东/...）。"""
    if not text:
        return None
    for region, kws in _REGION_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return region
    return None


_RANGE_PATTERN = re.compile(r"(\d+\.?\d*)\s*[-~～]\s*(\d+\.?\d*)")


def _try_parse_range(s: str) -> Optional[Tuple[float, float]]:
    """从字符串中识别范围值，返回 (a, b) 或 None。

    识别策略（避免日期"2019-09-01"被误识别为范围）：
    1. 优先用紧邻型正则 "X-Y" / "X~Y" 匹配（中间仅允许空白）
    2. 若失败，回退到"找所有数字 + 原文含分隔符"启发式：
       - 原文必须含 - / ~ / ～ 之一
       - 取前两个数字
       - 两数差值 < 100（排除日期 2019-09 的差值 2010）
    """
    m = _RANGE_PATTERN.search(s)
    if m:
        try:
            a, b = float(m.group(1)), float(m.group(2))
            if a > 0 and b > 0:
                return (a, b)
        except (TypeError, ValueError):
            pass
    if any(sep in s for sep in ("-", "~", "～")):
        nums = re.findall(r"\d+\.?\d*", s)
        if len(nums) >= 2:
            try:
                a, b = float(nums[0]), float(nums[1])
                if a > 0 and b > 0 and abs(a - b) < 100:
                    return (a, b)
            except (TypeError, ValueError):
                pass
    return None


def _extract_number(value: Any) -> Optional[float]:
    """从可能含单位/范围的单元格值中提取数字。

    - "660m³/h" → 660.0
    - "75KW" → 75.0
    - "30-50Hz" → 40.0 (取中值)
    - "2-4.5" → 3.25 (取中值，避免负号误识别)
    - "2-5" → 3.5 (取中值)
    - "28℃-32℃" → 30.0 (范围中值，跨非数字字符)
    - "50Hz 30-50Hz" → 40.0 (匹配到 30-50 范围)
    - "2019-09-01" → 2019.0 (日期不视为范围)
    - "一用二备" → None
    - 数字 → 直接返回
    - None/空 → None
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            f = float(value)
            return f if f == f else None  # NaN 检测
        except (TypeError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    rng = _try_parse_range(s)
    if rng:
        a, b = rng
        return (a + b) / 2.0
    nums = re.findall(r"\d+\.?\d*", s)
    if not nums:
        return None
    try:
        return float(nums[0])
    except (TypeError, ValueError):
        return None


def _extract_temp_diff(value: Any) -> Optional[float]:
    """提取温差值。

    调研表里"供回水温差"栏有时被误填为温度范围（如"28-32℃"或"9-13.2℃"），
    需要智能判断：
    - 任一数 > 10：认为是温度范围，取差值（如 28-32 → 4, 9-13.2 → 4.2）
    - 两数都 ≤ 10：认为是温差范围，取中值（如 2-4.5 → 3.25）
    - 单值 ≤ 10：直接返回（如 5 → 5）
    - 单值 > 10：返回 None（温差不可能 > 10℃）
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if f != f:
            return None
        return f if 0 < f <= 10 else None
    s = str(value).strip()
    if not s:
        return None
    rng = _try_parse_range(s)
    if rng:
        a, b = rng
        if a > 10 or b > 10:
            return abs(b - a)
        return (a + b) / 2.0
    nums = re.findall(r"\d+\.?\d*", s)
    if not nums:
        return None
    try:
        v = float(nums[0])
        return v if 0 < v <= 10 else None
    except (TypeError, ValueError):
        return None


def _detect_variable_freq(text: str) -> Optional[bool]:
    """从文本识别变频/工频。返回 True=变频, False=工频, None=未知。"""
    if not text:
        return None
    s = str(text)
    has_vf = any(kw in s for kw in _VARIABLE_FREQ_KEYWORDS)
    has_fixed = any(kw in s for kw in _FIXED_FREQ_KEYWORDS)
    if has_vf and not has_fixed:
        return True
    if has_fixed and not has_vf:
        return False
    if has_vf and has_fixed:
        # "变频泵是哪号机？" 这类描述里同时有，倾向变频
        return True
    return None


def _detect_chiller_type(text: str) -> str:
    """从文本识别主机机型。返回 "" 表示未知。"""
    if not text:
        return ""
    s = str(text)
    for kw, label in _CHILLER_TYPE_KEYWORDS:
        if kw in s:
            return label
    return ""


# ── Sheet 定位 ─────────────────────────────────────────────

def _find_cold_station_sheet(wb) -> Optional[str]:
    """定位冷站 sheet。优先级：1#冷站 > 冷站 > 冷站详情 > Chiller Plant。"""
    names = wb.sheetnames
    # 优先匹配 1#冷站
    for n in names:
        if "1#" in n and "冷站" in n:
            return n
    # 通用冷站
    for n in names:
        if n.strip() == "冷站" or n.startswith("冷站"):
            return n
    # 冷站详情
    for n in names:
        if "冷站详情" in n:
            return n
    # 英文
    for n in names:
        if "chiller plant" in n.lower() or "chillerplant" in n.lower():
            return n
    return None


# ── 表头/数据行定位 ────────────────────────────────────────

_DEVICE_HEADERS = {
    "chiller": ["冷机"],
    "cw_pump": ["冷却泵"],
    "chw_pump": ["冷冻泵"],
    "tower": ["冷却塔"],
}

# 设备表头 B 列文本必须**完全**等于这些关键词之一，避免误匹配（如"冷却塔出水温度"不应被识别为冷却塔表头）
# 因此使用"以...开头"匹配 + 排除月度数据行关键词
_MONTHLY_ROW_KEYWORDS = (
    "冷机运行台数", "冷机供水温度", "冷却泵运行频率", "冷却侧供回水温差",
    "冷冻泵运行频率", "冷冻侧供回水温差", "冷却塔运行频率", "冷却塔出水温度",
    "冷站/", "冷站/万", "冷站",
)


def _is_device_header(b_value: str) -> Optional[str]:
    """判断 B 列单元格是否为设备表头，返回设备类型 key 或 None。"""
    if not b_value:
        return None
    s = str(b_value).strip()
    if not s:
        return None
    # 排除月度数据行
    for kw in _MONTHLY_ROW_KEYWORDS:
        if s == kw or s.startswith(kw):
            return None
    # 必须精确等于设备名（避免"冷却塔运行频率"误匹配"冷却塔"）
    for dev_key, kws in _DEVICE_HEADERS.items():
        for kw in kws:
            if s == kw:
                return dev_key
    return None


def _find_device_header_rows(ws: Worksheet) -> Dict[str, int]:
    """扫描 B 列，找到各设备类型的表头行号。返回 {device_key: row_number}。"""
    found: Dict[str, int] = {}
    for r in range(1, min(ws.max_row + 1, 80)):
        b_val = ws.cell(row=r, column=2).value
        dev = _is_device_header(b_val)
        if dev and dev not in found:
            found[dev] = r
    return found


# ── 设备数据行解析 ────────────────────────────────────────

def _read_str(ws: Worksheet, row: int, col: int) -> str:
    v = ws.cell(row=row, column=col).value
    if v is None:
        return ""
    return str(v).strip()


def _read_num(ws: Worksheet, row: int, col: int) -> Optional[float]:
    return _extract_number(ws.cell(row=row, column=col).value)


def _read_int(ws: Worksheet, row: int, col: int, default: Optional[int] = None) -> Optional[int]:
    f = _read_num(ws, row, col)
    if f is None:
        return default
    try:
        return int(round(f))
    except (TypeError, ValueError):
        return default


def _is_empty_row(ws: Worksheet, row: int, max_col: int = 12) -> bool:
    """判断是否为空行（前 max_col 列全为空）。"""
    for c in range(1, max_col + 1):
        v = ws.cell(row=row, column=c).value
        if v is not None and str(v).strip():
            return False
    return True


def _is_section_boundary(ws: Worksheet, row: int) -> bool:
    """判断某行是否是新区块边界（如下一个设备表头、章节标题、电动阀门等）。"""
    b_val = _read_str(ws, row, 2)
    if not b_val:
        return False
    # 下一个设备表头
    if _is_device_header(b_val):
        return True
    # 章节标题
    if b_val in ("电动阀门", "三、冷站运行情况", "四、设备运行规律",
                 "五、用电情况统计", "六、照片、图纸、运行数据清单"):
        return True
    if b_val.startswith("三、") or b_val.startswith("四、") or b_val.startswith("五、"):
        return True
    return False


def _parse_chiller_row(ws: Worksheet, row: int) -> Optional[Dict[str, Any]]:
    """解析一行冷机数据。返回 None 表示该行无有效数据。"""
    # 列映射：C=类型, D=品牌, E=型号, G=台数, H=制冷量, I=功率, J=COP, K=年份, L=备注
    type_str = _read_str(ws, row, 3)
    brand = _read_str(ws, row, 4)
    model = _read_str(ws, row, 5)
    qty = _read_int(ws, row, 7, default=None)
    capacity = _read_num(ws, row, 8)
    power = _read_num(ws, row, 9)
    cop = _read_num(ws, row, 10)
    remark = _read_str(ws, row, 12)

    # 整行无有效数据则跳过
    if not any([type_str, brand, model, qty, capacity, power, cop]):
        return None
    if qty is None and capacity is None and power is None:
        return None

    # 变频判断：C 列类型描述 + 备注 + K 列（部分表 K 列写"变频/工频"）
    type_or_remark = f"{type_str} {remark}"
    vf = _detect_variable_freq(type_or_remark)

    # COP 缺失时从制冷量/功率推算
    if (cop is None or cop <= 0) and capacity and power and power > 0:
        cop = round(capacity / power, 3)

    # 机型识别
    chiller_type = _detect_chiller_type(type_str)

    # 名称：型号优先，否则用类型描述
    name = model or type_str or f"主机组"

    return {
        "name": name,
        "qty": qty if qty and qty > 0 else 1,
        "capacity_kw": float(capacity) if capacity else 0.0,
        "rated_power_kw": float(power) if power else 0.0,
        "rated_cop": float(cop) if cop else 0.0,
        "variable_freq": bool(vf) if vf is not None else False,
        "chiller_type": chiller_type,
        "brand": brand,
        "model": model,
        "remark": remark,
    }


def _parse_pump_row(ws: Worksheet, row: int, default_name: str) -> Optional[Dict[str, Any]]:
    """解析一行泵数据（冷却泵/冷冻泵共用）。

    列映射：C=类型, D=品牌, E=型号, G=台数, H=流量, I=功率, J=扬程, K=变频/工频, L=备注
    """
    type_str = _read_str(ws, row, 3)
    brand = _read_str(ws, row, 4)
    model = _read_str(ws, row, 5)
    qty = _read_int(ws, row, 7, default=None)
    flow = _read_num(ws, row, 8)
    power = _read_num(ws, row, 9)
    head = _read_num(ws, row, 10)
    vf_text = _read_str(ws, row, 11)
    remark = _read_str(ws, row, 12)

    if not any([type_str, brand, model, qty, flow, power, head]):
        return None
    if qty is None and flow is None and power is None:
        return None

    # 变频：K 列明确标注优先；否则从类型描述推断
    vf = _detect_variable_freq(vf_text)
    if vf is None:
        vf = _detect_variable_freq(f"{type_str} {remark}")

    name = model or type_str or default_name

    return {
        "name": name,
        "qty": qty if qty and qty > 0 else 1,
        "power_kw": float(power) if power else 0.0,
        "flow_m3h": float(flow) if flow else 0.0,
        "variable_freq": bool(vf) if vf is not None else False,
        "rated_head_m": head,
        "brand": brand,
        "model": model,
        "remark": remark,
    }


def _parse_tower_row(ws: Worksheet, row: int) -> Optional[Dict[str, Any]]:
    """解析一行冷却塔数据。

    列映射：C=序号/类型, D=品牌, E=型号, G=台数, H=流量, I=每台风机数, J=单台风机功率, K=变频/工频, L=备注
    """
    type_str = _read_str(ws, row, 3)
    brand = _read_str(ws, row, 4)
    model = _read_str(ws, row, 5)
    qty = _read_int(ws, row, 7, default=None)
    flow = _read_num(ws, row, 8)
    fans = _read_int(ws, row, 9, default=1)
    fan_power = _read_num(ws, row, 10)
    vf_text = _read_str(ws, row, 11)
    remark = _read_str(ws, row, 12)

    if not any([type_str, brand, model, qty, flow, fan_power]):
        return None
    if qty is None and flow is None and fan_power is None:
        return None

    vf = _detect_variable_freq(vf_text)
    if vf is None:
        vf = _detect_variable_freq(f"{type_str} {remark}")

    name = model or type_str or "冷却塔"

    return {
        "name": name,
        "qty": qty if qty and qty > 0 else 1,
        "fan_power_kw": float(fan_power) if fan_power else 0.0,
        "fans_per_tower": fans if fans and fans > 0 else 1,
        "variable_freq": bool(vf) if vf is not None else False,
        "water_flow_m3h": flow,
        "brand": brand,
        "model": model,
        "remark": remark,
    }


def _parse_device_section(ws: Worksheet, header_row: int, device_key: str) -> List[Dict[str, Any]]:
    """从设备表头行开始向下解析数据行，直到空行或下一个区块边界。"""
    items: List[Dict[str, Any]] = []
    # 表头下一行开始
    r = header_row + 1
    while r <= min(ws.max_row, header_row + 10):
        if _is_empty_row(ws, r):
            break
        if _is_section_boundary(ws, r):
            break
        item: Optional[Dict[str, Any]] = None
        if device_key == "chiller":
            item = _parse_chiller_row(ws, r)
        elif device_key in ("cw_pump", "chw_pump"):
            default_name = "冷却泵" if device_key == "cw_pump" else "冷冻泵"
            item = _parse_pump_row(ws, r, default_name)
        elif device_key == "tower":
            item = _parse_tower_row(ws, r)
        if item:
            items.append(item)
        r += 1
    return items


# ── 月度数据解析 ────────────────────────────────────────────

_MONTHLY_ROW_PARSERS = {
    "冷机运行台数": "chiller_count",
    "冷机供水温度": "chiller_supply_temp",
    "冷却泵运行频率": "cooling_pump_freq",
    "冷却侧供回水温差": "cooling_water_temp_diff",
    "冷冻泵运行频率": "freezing_pump_freq",
    "冷冻侧供回水温差": "freezing_water_temp_diff",
    "冷却塔运行频率": "cooling_tower_freq",
    "冷却塔出水温度": "cooling_tower_outlet_temp",
}


def _detect_month_column_start(ws: Worksheet, header_row: int) -> int:
    """检测月度数据区的列起始位置。

    调研表"设备运行规律"部分：C 列是"备注"，月份从 D 列（col=4）开始
    调研表"用电情况统计"部分：无"备注"列，月份从 C 列（col=3）开始
    通过查找表头行中"1月"关键字定位。
    """
    for c in range(2, 18):
        v = ws.cell(row=header_row, column=c).value
        if v and "1月" in str(v):
            return c
    # 默认 D 列（设备运行规律）
    return 4


def _parse_monthly_section(ws: Worksheet, section_header_row: int) -> Dict[str, Any]:
    """解析月度运行数据区块。

    Args:
        section_header_row: "四、设备运行规律" 章节标题行
    Returns:
        {
            "monthly_data": {"1": {...}, ..., "12": {...}},
            "monthly_chiller_count": [12 个月的开机台数],
        }
    """
    # 找月份表头行（紧接章节标题的下一行含"月份"）
    month_header_row = None
    for r in range(section_header_row + 1, section_header_row + 5):
        b_val = _read_str(ws, r, 2)
        if b_val == "月份" or "月份" in b_val:
            month_header_row = r
            break
    if month_header_row is None:
        return {"monthly_data": {}, "monthly_chiller_count": [1] * 12}

    col_start = _detect_month_column_start(ws, month_header_row)

    monthly_data: Dict[str, Any] = {}
    monthly_chiller_count: List[int] = [1] * 12

    # 从月份表头下一行开始解析
    r = month_header_row + 1
    while r <= min(ws.max_row, month_header_row + 15):
        b_val = _read_str(ws, r, 2)
        if not b_val:
            r += 1
            continue
        # 命中下一个章节标题则停止
        if b_val.startswith("五、") or b_val.startswith("六、") or b_val in ("五、用电情况统计", "六、照片、图纸、运行数据清单"):
            break

        # 匹配月度数据行类型
        row_key = None
        for keyword, field_key in _MONTHLY_ROW_PARSERS.items():
            if keyword in b_val:
                row_key = field_key
                break

        if row_key:
            for m_idx in range(12):
                col = col_start + m_idx
                cell_val = ws.cell(row=r, column=col).value
                m_str = str(m_idx + 1)
                if m_str not in monthly_data:
                    monthly_data[m_str] = {}

                if row_key == "chiller_count":
                    v = _read_int(ws, r, col, default=None)
                    if v is not None and v > 0:
                        monthly_chiller_count[m_idx] = v
                    monthly_data[m_str][row_key] = v
                elif row_key in ("freezing_water_temp_diff", "cooling_water_temp_diff"):
                    v = _extract_temp_diff(cell_val)
                    monthly_data[m_str][row_key] = v
                elif "温度" in row_key:
                    v = _extract_number(cell_val)
                    monthly_data[m_str][row_key] = v
                elif "频率" in row_key:
                    v = _extract_number(cell_val)
                    # 频率范围中值（如 30-50Hz → 40Hz）
                    monthly_data[m_str][row_key] = v
                else:
                    v = _extract_number(cell_val)
                    monthly_data[m_str][row_key] = v
        r += 1

    return {
        "monthly_data": monthly_data,
        "monthly_chiller_count": monthly_chiller_count,
    }


def _find_monthly_section_header(ws: Worksheet) -> Optional[int]:
    """定位"四、设备运行规律"章节标题行号。"""
    for r in range(1, min(ws.max_row + 1, 80)):
        b_val = _read_str(ws, r, 2)
        if b_val and ("设备运行规律" in b_val or b_val.startswith("四、")):
            return r
    return None


def _find_station_name(ws: Worksheet) -> str:
    """提取站房名称（用于地区推断）。"""
    # 站房名称通常在 B2 单元格
    for r in range(1, 6):
        b_val = _read_str(ws, r, 2)
        if b_val == "站房名称":
            # 同行 C 列或 D 列是名称值
            for c in (3, 4, 5):
                v = ws.cell(row=r, column=c).value
                if v and str(v).strip():
                    return str(v).strip()
    return ""


# ── 同种类设备合并 ─────────────────────────────────────────

def _chiller_merge_key(c: Dict[str, Any]) -> Tuple:
    """生成主机合并键：同品牌+同型号+同制冷量+同功率+同变频状态视为同一种类。

    注意：型号相同但变频/工频不同的主机不合并（运行特性差异大）。
    """
    return (
        (c.get("brand") or "").strip(),
        (c.get("model") or "").strip(),
        round(float(c.get("capacity_kw") or 0), 1),
        round(float(c.get("rated_power_kw") or 0), 1),
        bool(c.get("variable_freq")),
    )


def _merge_chiller_groups(chillers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并同一种类的冷机组。

    合并规则：
    - qty: 累加
    - name: 取最长的非空名称（型号优先，含类型描述的更优）
    - chiller_type: 取首个非空
    - rated_cop: 取首个 >0 的值；若仍有缺失则从制冷量/功率重算
    - remark: 合并所有非空备注（去重，分号分隔）
    - 其余字段（brand/model/capacity_kw/rated_power_kw/variable_freq）取首组
    """
    if not chillers:
        return []
    groups: Dict[Tuple, List[Dict[str, Any]]] = {}
    order: List[Tuple] = []
    for c in chillers:
        key = _chiller_merge_key(c)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    merged: List[Dict[str, Any]] = []
    for key in order:
        items = groups[key]
        if len(items) == 1:
            merged.append(items[0])
            continue
        base = dict(items[0])
        total_qty = sum(int(it.get("qty") or 1) for it in items)
        names = [str(it.get("name") or "") for it in items]
        best_name = max(names, key=len) if names else base.get("name")
        if best_name:
            base["name"] = best_name
        for it in items:
            if it.get("chiller_type"):
                base["chiller_type"] = it["chiller_type"]
                break
        cop_val = 0.0
        for it in items:
            v = float(it.get("rated_cop") or 0)
            if v > 0:
                cop_val = v
                break
        if cop_val <= 0:
            cap = float(base.get("capacity_kw") or 0)
            pow_ = float(base.get("rated_power_kw") or 0)
            if cap > 0 and pow_ > 0:
                cop_val = round(cap / pow_, 3)
        base["rated_cop"] = cop_val
        remarks = []
        for it in items:
            r = (it.get("remark") or "").strip()
            if r and r not in remarks:
                remarks.append(r)
        base["remark"] = "；".join(remarks) if remarks else ""
        base["qty"] = total_qty
        merged.append(base)
    return merged


def _pump_merge_key(p: Dict[str, Any]) -> Tuple:
    """生成泵合并键：同品牌+同型号+同流量+同功率+同扬程+同变频状态视为同一种类。"""
    return (
        (p.get("brand") or "").strip(),
        (p.get("model") or "").strip(),
        round(float(p.get("flow_m3h") or 0), 1),
        round(float(p.get("power_kw") or 0), 1),
        round(float(p.get("rated_head_m") or 0), 1),
        bool(p.get("variable_freq")),
    )


def _merge_pump_groups_by_key(pumps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并同一种类的泵组（冷却泵/冷冻泵通用）。"""
    if not pumps:
        return []
    groups: Dict[Tuple, List[Dict[str, Any]]] = {}
    order: List[Tuple] = []
    for p in pumps:
        key = _pump_merge_key(p)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(p)

    merged: List[Dict[str, Any]] = []
    for key in order:
        items = groups[key]
        if len(items) == 1:
            merged.append(items[0])
            continue
        base = dict(items[0])
        total_qty = sum(int(it.get("qty") or 1) for it in items)
        names = [str(it.get("name") or "") for it in items]
        best_name = max(names, key=len) if names else base.get("name")
        if best_name:
            base["name"] = best_name
        remarks = []
        for it in items:
            r = (it.get("remark") or "").strip()
            if r and r not in remarks:
                remarks.append(r)
        base["remark"] = "；".join(remarks) if remarks else ""
        base["qty"] = total_qty
        merged.append(base)
    return merged


def _tower_merge_key(t: Dict[str, Any]) -> Tuple:
    """生成冷却塔合并键：同品牌+同型号+同风机功率+同风机数+同变频+同流量视为同一种类。"""
    return (
        (t.get("brand") or "").strip(),
        (t.get("model") or "").strip(),
        round(float(t.get("fan_power_kw") or 0), 1),
        int(t.get("fans_per_tower") or 1),
        bool(t.get("variable_freq")),
        round(float(t.get("water_flow_m3h") or 0), 1),
    )


def _merge_tower_groups_by_key(towers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并同一种类的冷却塔组。"""
    if not towers:
        return []
    groups: Dict[Tuple, List[Dict[str, Any]]] = {}
    order: List[Tuple] = []
    for t in towers:
        key = _tower_merge_key(t)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(t)

    merged: List[Dict[str, Any]] = []
    for key in order:
        items = groups[key]
        if len(items) == 1:
            merged.append(items[0])
            continue
        base = dict(items[0])
        total_qty = sum(int(it.get("qty") or 1) for it in items)
        names = [str(it.get("name") or "") for it in items]
        best_name = max(names, key=len) if names else base.get("name")
        if best_name:
            base["name"] = best_name
        remarks = []
        for it in items:
            r = (it.get("remark") or "").strip()
            if r and r not in remarks:
                remarks.append(r)
        base["remark"] = "；".join(remarks) if remarks else ""
        base["qty"] = total_qty
        merged.append(base)
    return merged


# ── 主入口 ──────────────────────────────────────────────────

def parse_survey_excel(file_path: str, original_filename: Optional[str] = None) -> Dict[str, Any]:
    """从调研表 Excel 文件路径解析。

    Args:
        file_path: Excel 文件路径
        original_filename: 用户上传时的原始文件名（用于地区推断兜底）

    Returns:
        {
            "chillers": [...],
            "chw_pumps": [...],
            "cw_pumps": [...],
            "towers": [...],
            "monthly_data": {"1": {...}, ...},
            "monthly_chiller_count": [...],
            "station_name": "...",
            "region_hint": "华南/华东/...",  # 从站房名称/文件名推断
        }
    """
    wb = load_workbook(file_path, data_only=True)
    sheet_name = _find_cold_station_sheet(wb)
    if sheet_name is None:
        wb.close()
        return {
            "chillers": [], "chw_pumps": [], "cw_pumps": [], "towers": [],
            "monthly_data": {}, "monthly_chiller_count": [1] * 12,
            "station_name": "", "region_hint": None,
        }
    ws = wb[sheet_name]

    # 站房名称
    station_name = _find_station_name(ws)

    # 设备区块
    device_headers = _find_device_header_rows(ws)
    chillers = _parse_device_section(ws, device_headers["chiller"], "chiller") if "chiller" in device_headers else []
    cw_pumps = _parse_device_section(ws, device_headers["cw_pump"], "cw_pump") if "cw_pump" in device_headers else []
    chw_pumps = _parse_device_section(ws, device_headers["chw_pump"], "chw_pump") if "chw_pump" in device_headers else []
    towers = _parse_device_section(ws, device_headers["tower"], "tower") if "tower" in device_headers else []

    # 月度数据
    monthly_section_row = _find_monthly_section_header(ws)
    monthly_result = {"monthly_data": {}, "monthly_chiller_count": [1] * 12}
    if monthly_section_row:
        monthly_result = _parse_monthly_section(ws, monthly_section_row)

    wb.close()

    # 地区推断（三级优先级）
    region_hint = None
    # 优先级 1: 站房名称
    if station_name:
        region_hint = _infer_region(station_name)
    # 优先级 2: 原始文件名
    if not region_hint and original_filename:
        region_hint = _infer_region(original_filename)

    result = {
        "chillers": chillers,
        "chw_pumps": chw_pumps,
        "cw_pumps": cw_pumps,
        "towers": towers,
        "monthly_data": monthly_result["monthly_data"],
        "monthly_chiller_count": monthly_result["monthly_chiller_count"],
        "station_name": station_name,
        "region_hint": region_hint,
    }

    # 同种类设备合并（调研表常把同型号设备拆成多行）
    result["chillers"] = _merge_chiller_groups(result["chillers"])
    result["chw_pumps"] = _merge_pump_groups_by_key(result["chw_pumps"])
    result["cw_pumps"] = _merge_pump_groups_by_key(result["cw_pumps"])
    result["towers"] = _merge_tower_groups_by_key(result["towers"])

    return result


def parse_survey_excel_from_bytes(file_bytes: bytes, original_filename: Optional[str] = None) -> Dict[str, Any]:
    """从调研表 Excel 字节流解析（用于 Streamlit UploadedFile）。

    Args:
        file_bytes: Excel 文件字节流
        original_filename: 用户上传时的原始文件名（用于地区推断兜底）

    Returns:
        同 parse_survey_excel
    """
    import io
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheet_name = _find_cold_station_sheet(wb)
    if sheet_name is None:
        wb.close()
        return {
            "chillers": [], "chw_pumps": [], "cw_pumps": [], "towers": [],
            "monthly_data": {}, "monthly_chiller_count": [1] * 12,
            "station_name": "", "region_hint": None,
        }
    ws = wb[sheet_name]

    station_name = _find_station_name(ws)

    device_headers = _find_device_header_rows(ws)
    chillers = _parse_device_section(ws, device_headers["chiller"], "chiller") if "chiller" in device_headers else []
    cw_pumps = _parse_device_section(ws, device_headers["cw_pump"], "cw_pump") if "cw_pump" in device_headers else []
    chw_pumps = _parse_device_section(ws, device_headers["chw_pump"], "chw_pump") if "chw_pump" in device_headers else []
    towers = _parse_device_section(ws, device_headers["tower"], "tower") if "tower" in device_headers else []

    monthly_section_row = _find_monthly_section_header(ws)
    monthly_result = {"monthly_data": {}, "monthly_chiller_count": [1] * 12}
    if monthly_section_row:
        monthly_result = _parse_monthly_section(ws, monthly_section_row)

    wb.close()

    # 地区推断
    region_hint = None
    if station_name:
        region_hint = _infer_region(station_name)
    if not region_hint and original_filename:
        region_hint = _infer_region(original_filename)

    result = {
        "chillers": chillers,
        "chw_pumps": chw_pumps,
        "cw_pumps": cw_pumps,
        "towers": towers,
        "monthly_data": monthly_result["monthly_data"],
        "monthly_chiller_count": monthly_result["monthly_chiller_count"],
        "station_name": station_name,
        "region_hint": region_hint,
    }

    # 同种类设备合并
    result["chillers"] = _merge_chiller_groups(result["chillers"])
    result["chw_pumps"] = _merge_pump_groups_by_key(result["chw_pumps"])
    result["cw_pumps"] = _merge_pump_groups_by_key(result["cw_pumps"])
    result["towers"] = _merge_tower_groups_by_key(result["towers"])

    return result
