"""工作日历程序化解析器

支持：
- 灵活循环模式识别（上七修二、6+1、单休、双休…）
- 2024 年法定节假日自动识别
- "考虑所有节假日除了XX" / "XX节上班" 等复合规则

优先程序化解析（确定性），复杂情况回退 AI。
"""

import re
from typing import List, Optional, Tuple, Dict, Set

# ═══════════════════════════════════════════════════════════════
#  2024 年中国法定节假日
# ═══════════════════════════════════════════════════════════════
# day 0 = 2024-01-01 (周一)，2024 是闰年 (2月29天)

CHINESE_HOLIDAYS_2024: Dict[str, List[int]] = {
    "元旦": [0],                       # 1月1日
    "春节": list(range(28, 35)),       # 1月29日~2月4日，共7天
    "清明": [94],                      # 4月4日
    "劳动节": [121],                   # 5月1日
    "端午": [161],                     # 6月10日
    "中秋": [260],                     # 9月17日
    "国庆": list(range(273, 280)),     # 10月1日~7日，共7天
}

HOLIDAY_ALIASES: Dict[str, List[str]] = {
    "元旦": ["元旦", "新年", "1月1"],
    "春节": ["春节", "过年", "除夕", "新春"],
    "清明": ["清明", "清明节"],
    "劳动节": ["劳动节", "五一", "五一节", "5月1"],
    "端午": ["端午", "端午节"],
    "中秋": ["中秋", "中秋节"],
    "国庆": ["国庆", "国庆节", "十一", "10月1"],
}

# 中文数字 → 阿拉伯数字
_CN_NUM_MAP: Dict[str, int] = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '零': 0,
}

# 默认工作日历：5+2（周一~周五工作，周六~周日休息）
DEFAULT_DAY_TYPE: List[int] = [0 if (d % 7 < 5) else 1 for d in range(365)]


def _to_int(s: str) -> int:
    """中文/阿拉伯数字 → 整数。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in _CN_NUM_MAP:
        return _CN_NUM_MAP[s]
    if len(s) == 2 and s[0] == '十':
        return 10 + _CN_NUM_MAP.get(s[1], 0)
    return int(s)


def parse_cycle_pattern(user_text: str) -> Optional[Tuple[int, int]]:
    """从用户文字中程序化解析工作/休息循环模式。

    返回 (work_days, rest_days) 或 None。

    支持：「上X修Y」「上X休Y」「X+Y」「单休」「双休」「每周工作X天」等。
    """
    _N = r'([一二三四五六七八九十\d]+)'
    text = user_text.strip()

    # 1) "上X修Y" / "上X休Y" / "上X天休息Y天"
    m = re.search(r'上\s*' + _N + r'\s*(?:天\s*)?(?:休息|[修休])\s*' + _N + r'\s*天?', text)
    if m:
        return _to_int(m.group(1)), _to_int(m.group(2))

    # 2) "做X休Y" / "做X休息Y"
    m = re.search(r'做\s*' + _N + r'\s*(?:休息|[休修])\s*' + _N, text)
    if m:
        return _to_int(m.group(1)), _to_int(m.group(2))

    # 3) "X+Y"（仅阿拉伯数字）
    m = re.search(r'(?<!\d)(\d+)\s*\+\s*(\d+)(?!\d)', text)
    if m:
        return int(m.group(1)), int(m.group(2))

    # 4) "工作X天休息Y天" / "干X天休Y天"
    m = re.search(r'(?:工作|干|做)\s*' + _N + r'\s*天\s*(?:休息|[修休])\s*' + _N + r'\s*天', text)
    if m:
        return _to_int(m.group(1)), _to_int(m.group(2))

    # 5) "单休" → 6+1
    if re.search(r'(?<!不)单休', text):
        return 6, 1

    # 6) "双休" → 5+2
    if re.search(r'(?<!不)双休', text):
        return 5, 2

    # 7) "大小周" → 无法简单循环，返回 None 交给 AI
    if '大小周' in text:
        return None

    # 8) "X天工作制" → X + (7-X)
    m = re.search(_N + r'\s*天\s*工作制', text)
    if m:
        work = _to_int(m.group(1))
        if 1 <= work <= 6:
            return work, 7 - work

    # 9) "每周工作X天" / "一周工作X天" / "每周上X天"
    m = re.search(r'(?:每周|一周|每星期)\s*(?:工作|干|做|上)\s*' + _N + r'\s*天', text)
    if m:
        work = _to_int(m.group(1))
        if 1 <= work <= 6:
            return work, 7 - work

    # 10) "X天工作Y天休息"
    m = re.search(_N + r'\s*天\s*工作\s*' + _N + r'\s*天\s*休息', text)
    if m:
        return _to_int(m.group(1)), _to_int(m.group(2))

    # 11) "每周休X天"
    m = re.search(r'(?:每周|一周|每星期)\s*休\s*(\d+)\s*天', text)
    if m:
        rest = int(m.group(1))
        if 1 <= rest <= 2:
            return 7 - rest, rest

    return None


def generate_cycle_day_type(work_days: int, rest_days: int, total_days: int = 365) -> List[int]:
    """根据工作/休息循环生成 day_type 数组。0=工作日, 1=休息日。"""
    cycle_len = work_days + rest_days
    result = []
    for i in range(total_days):
        pos = i % cycle_len
        result.append(0 if pos < work_days else 1)
    return result


def parse_holiday_intent(user_text: str) -> Dict:
    """从用户文字中解析节假日意图。

    返回 dict:
        all_holidays: bool    — 是否涵盖所有法定节假日
        excluded: Set[str]    — 要排除的节日名
        work_on: Set[str]     — 要设为上班(0)的节日名
        rest_on: Set[str]     — 要单独设为放假(1)的节日名
    """
    text = user_text.strip()
    result: Dict = {
        "all_holidays": False,
        "excluded": set(),
        "work_on": set(),
        "rest_on": set(),
    }

    # 检测"所有/全部 节假日/法定假日"
    all_keywords = [
        '所有节假日', '全部法定假日', '全部假日', '法定节假日',
        '所有法定假日', '所有法定节假日', '考虑节假日', '考虑所有节假日',
        '所有假期', '全部假期', '法定假期', '法定假日', '国家法定假日',
        '法定节日', '所有法定节日', '全部法定节日',
    ]
    result["all_holidays"] = any(kw in text for kw in all_keywords)

    # 精确模式匹配排除
    for canonical_name, aliases in HOLIDAY_ALIASES.items():
        for alias in aliases:
            for pat in [f'除了{alias}', f'除{alias}外', f'{alias}除外',
                         f'不算{alias}', f'去掉{alias}', f'不含{alias}',
                         f'不包括{alias}']:
                if pat in text:
                    result["excluded"].add(canonical_name)
                    break

    # 上下文扫描：处理"除了A和B"并列
    for exc_kw in ['除了', '除']:
        idx = 0
        while True:
            idx = text.find(exc_kw, idx)
            if idx < 0:
                break
            after_start = idx + len(exc_kw)
            after = text[after_start:]
            end_idx = len(after)
            for sep in ['，', ',', '。', '.', '；', ';', '！', '!', '？', '?',
                         '我', '请', '但', '不', '需', '按']:
                pos = after.find(sep)
                if 0 <= pos < end_idx:
                    end_idx = pos
            context = after[:end_idx]
            for canonical_name, aliases in HOLIDAY_ALIASES.items():
                for alias in aliases:
                    if alias in context:
                        result["excluded"].add(canonical_name)
                        break
            idx = after_start

    # 要上班的节日
    for canonical_name, aliases in HOLIDAY_ALIASES.items():
        for alias in aliases:
            for pat in [f'{alias}上班', f'{alias}工作', f'{alias}不休息',
                         f'{alias}不放假', f'{alias}正常上班', f'{alias}照常上班',
                         f'{alias}正常工作日']:
                if pat in text:
                    result["work_on"].add(canonical_name)
                    break

    # 单独放假的节日（非 all_holidays 时）
    if not result["all_holidays"]:
        for canonical_name, aliases in HOLIDAY_ALIASES.items():
            for alias in aliases:
                if alias in text:
                    if canonical_name not in result["excluded"] and canonical_name not in result["work_on"]:
                        for pat2 in [f'{alias}放假', f'{alias}休息', f'{alias}节']:
                            if pat2 in text or text.strip().startswith(alias):
                                result["rest_on"].add(canonical_name)
                                break
                    break

    return result


def apply_holiday_overrides(day_type: List[int], holiday_intent: Dict) -> List[int]:
    """将节假日覆盖应用到 day_type 数组，返回新数组。"""
    result = list(day_type)

    if holiday_intent["all_holidays"]:
        for canonical_name, days in CHINESE_HOLIDAYS_2024.items():
            if canonical_name in holiday_intent["excluded"]:
                continue
            if canonical_name in holiday_intent["work_on"]:
                for d in days:
                    if 0 <= d < len(result):
                        result[d] = 0
            else:
                for d in days:
                    if 0 <= d < len(result):
                        result[d] = 1
    else:
        for canonical_name, days in CHINESE_HOLIDAYS_2024.items():
            if canonical_name in holiday_intent["rest_on"]:
                for d in days:
                    if 0 <= d < len(result):
                        result[d] = 1
            if canonical_name in holiday_intent["work_on"]:
                for d in days:
                    if 0 <= d < len(result):
                        result[d] = 0

    return result


def parse_calendar_smart(user_text: str) -> Optional[Dict]:
    """智能解析工作日历规则：优先程序化，失败回退 AI。

    返回 dict:
        day_type: List[int]     — 365 天数组
        method: str             — 'programmatic' | 'ai' | …
        pattern: str | None     — 循环模式如 "7+2"
        holidays: List[str]     — 已应用的节假日
        excluded_holidays: List[str]
        work_on_holidays: List[str]
    """
    text = user_text.strip()
    if not text:
        return None

    # 第一步：程序化解析循环
    cycle = parse_cycle_pattern(text)
    if cycle:
        work_days, rest_days = cycle
        day_type = generate_cycle_day_type(work_days, rest_days)
        pattern = f"{work_days}+{rest_days}"
        method = "programmatic"
    else:
        day_type = generate_cycle_day_type(5, 2)
        pattern = "5+2（默认）"
        method = "programmatic (默认5+2 + 节假日覆盖)"

    # 第二步：程序化解析节假日
    holiday_intent = parse_holiday_intent(text)

    holidays_applied: List[str] = []
    if holiday_intent["all_holidays"]:
        holidays_applied = sorted([
            name for name in CHINESE_HOLIDAYS_2024
            if name not in holiday_intent["excluded"]
            and name not in holiday_intent["work_on"]
        ])
    elif holiday_intent["rest_on"]:
        holidays_applied = sorted(holiday_intent["rest_on"])

    has_holiday_intent = (
        holiday_intent["all_holidays"]
        or holiday_intent["rest_on"]
        or holiday_intent["work_on"]
        or holiday_intent["excluded"]
    )

    if has_holiday_intent:
        day_type = apply_holiday_overrides(day_type, holiday_intent)

    return {
        "day_type": day_type,
        "method": method,
        "pattern": pattern,
        "holidays": holidays_applied,
        "excluded_holidays": sorted(holiday_intent["excluded"]),
        "work_on_holidays": sorted(holiday_intent["work_on"]),
    }
