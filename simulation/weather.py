"""气象数据服务 - 提供全年逐月干湿球温度"""
import json
from pathlib import Path
from typing import Dict, List, Optional

WEATHER_DATA_PATH = Path(__file__).parent.parent / "config" / "weather_data.json"

# 各地区月度干球温度 (°C) - 典型气象年数据
REGION_DRY_BULB = {
    "华南": [14, 15, 18, 23, 27, 29, 30, 30, 28, 24, 19, 15],
    "华东": [5, 6, 11, 17, 22, 26, 30, 30, 26, 20, 14, 7],
    "华中": [4, 6, 11, 17, 23, 27, 30, 29, 25, 19, 12, 6],
    "华北": [-3, 0, 7, 15, 22, 27, 28, 27, 22, 14, 6, -1],
    "西南": [7, 9, 14, 18, 22, 24, 26, 26, 22, 17, 12, 8],
    "西北": [-5, -1, 7, 14, 20, 25, 27, 26, 20, 13, 5, -3],
    "东北": [-15, -10, -1, 9, 17, 22, 25, 23, 16, 7, -3, -12],
}

REGION_CITIES = {
    "华南": "广州", "华东": "上海", "华中": "武汉",
    "华北": "北京", "西南": "成都", "西北": "西安", "东北": "沈阳",
}


def get_regions() -> List[str]:
    return list(REGION_DRY_BULB.keys())


def get_monthly_dry_bulb(region: str) -> List[float]:
    if region in REGION_DRY_BULB:
        return REGION_DRY_BULB[region]
    for key in REGION_DRY_BULB:
        if key in region or region in key:
            return REGION_DRY_BULB[key]
    return REGION_DRY_BULB["华东"]


def get_monthly_wet_bulb(region: str) -> List[float]:
    try:
        with open(WEATHER_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        month_keys = ["jan", "feb", "mar", "apr", "may", "jun",
                      "jul", "aug", "sep", "oct", "nov", "dec"]
        city = REGION_CITIES.get(region, "上海")
        for key, city_data in data.items():
            if city_data.get("city") == city or city_data.get("region") == region:
                return [city_data[m] for m in month_keys]
    except (FileNotFoundError, KeyError):
        pass
    dry_bulb = get_monthly_dry_bulb(region)
    return [t - 4.0 for t in dry_bulb]


def get_monthly_tower_outlet(region: str) -> List[float]:
    wet_bulb = get_monthly_wet_bulb(region)
    return [max(21.0, wb + 4.5) for wb in wet_bulb]
