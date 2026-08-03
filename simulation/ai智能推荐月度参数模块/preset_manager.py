"""用户预设持久化管理

将预设曲线存储在 JSON 文件中，支持 CRUD：
- 内置 7 个班制首次自动写入
- 用户可新增/编辑/删除预设
- 刷新/重启后自动加载
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .presets import PRESET_SCHEDULES, SCHEDULE_LABELS

_PRESET_FILE = Path(__file__).parent / "user_presets.json"

# ── 内置班制（启动时写入 JSON）──────────────────────────────

def _builtin_data() -> Dict:
    """将 PRESET_SCHEDULES 转为持久化格式。"""
    return {
        name: {
            "label": data["label"],
            "desc": data["desc"],
            "workday_curve": data["workday_curve"],
            "offday_curve": data["offday_curve"],
            "is_builtin": True,
        }
        for name, data in PRESET_SCHEDULES.items()
    }


# ── 核心操作 ─────────────────────────────────────────────────

def _read() -> Dict:
    """读取 JSON 文件，若不存在则用内置数据初始化。"""
    if not _PRESET_FILE.exists():
        data = {"presets": _builtin_data()}
        _write(data)
        return data
    try:
        with open(_PRESET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        data = {"presets": _builtin_data()}
        _write(data)
        return data


def _write(data: Dict):
    """写入 JSON 文件。"""
    _PRESET_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_PRESET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_presets() -> Dict:
    """返回所有预设 {name: {label, desc, workday_curve, offday_curve, is_builtin}}。"""
    return _read().get("presets", {})


def get_preset_names() -> List[str]:
    """返回所有预设名称列表。"""
    return list(get_all_presets().keys())


def get_preset(name: str) -> Optional[Dict]:
    """获取单个预设。"""
    return get_all_presets().get(name)


def save_preset(name: str, workday_curve: List[float], offday_curve: List[float],
                desc: str = "", label: str = "") -> bool:
    """保存/覆盖一个预设。若同名内置预设被覆盖，标记为非内置。

    Returns:
        True 若为新建，False 若为覆盖。
    """
    data = _read()
    is_new = name not in data.get("presets", {})
    data.setdefault("presets", {})[name] = {
        "label": label or name,
        "desc": desc or _auto_desc(workday_curve, offday_curve),
        "workday_curve": workday_curve,
        "offday_curve": offday_curve,
        "is_builtin": False,  # 用户编辑过后就不再是内置
    }
    _write(data)
    return is_new


def delete_preset(name: str) -> bool:
    """删除预设。内置预设也可删除。

    Returns:
        True 若成功删除，False 若不存在。
    """
    data = _read()
    if name not in data.get("presets", {}):
        return False
    del data["presets"][name]
    _write(data)
    return True


def ensure_defaults():
    """确保 JSON 中至少有一个预设（防止全部删光）。"""
    data = _read()
    if not data.get("presets"):
        data["presets"] = {
            "单班制办公": {
                "label": "单班制办公",
                "desc": "工作日 8:00-18:00 运行，夜间值班 30%，周末基本关闭 15%",
                "workday_curve": PRESET_SCHEDULES["单班制办公"]["workday_curve"],
                "offday_curve": PRESET_SCHEDULES["单班制办公"]["offday_curve"],
                "is_builtin": True,
            }
        }
        _write(data)


def _auto_desc(wd: List[float], od: List[float]) -> str:
    """根据曲线自动生成一句话描述。"""
    wd_avg = sum(wd) / len(wd)
    od_avg = sum(od) / len(od)
    wd_peak = max(wd)
    peak_hours = [i for i, v in enumerate(wd) if v >= wd_peak * 0.9]
    if peak_hours:
        start, end = min(peak_hours), max(peak_hours) + 1
        hours_str = f"{start}:00-{end}:00"
    else:
        hours_str = "全天"
    return (
        f"工作日 {hours_str} 运行，日均系数 {wd_avg:.0%}，"
        f"休息日日均系数 {od_avg:.0%}"
    )
