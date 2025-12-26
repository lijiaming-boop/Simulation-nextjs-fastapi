"""示例调研表测试夹具配置"""
import os
from pathlib import Path

# 示例调研表目录
SAMPLE_DIR = Path(__file__).parent.parent.parent / "00_sample" / "示例调研表"

# 6份示例调研表配置
SAMPLE_SURVEYS = {
    "complete": {
        "file": "【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx",
        "expected_rate": 15.2,
        "expected_confidence": "high",  # ≥80%
        "description": "数据填写齐全"
    },
    "summer_only": {
        "file": "【仅有夏季】6.5%和光同程-机房智能化调研表2023年5月版.xlsx",
        "expected_rate": 6.5,
        "expected_confidence": "medium",  # 50-80%
        "description": "只填了夏季数据"
    },
    "no_winter": {
        "file": "【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx",
        "expected_rate": 10.4,
        "expected_confidence": "medium",
        "description": "没有填冬季数据"
    },
    "no_summer": {
        "file": "【缺夏季】12.1%上海和元-机房智能化调研表模板（深度调研）.xlsx",
        "expected_rate": 12.1,
        "expected_confidence": "medium",
        "description": "没有填夏季能耗数据"
    },
    "irregular": {
        "file": "【参差不齐】11.9%中央空调节能调研表（首页含问题指引）.xlsx",
        "expected_rate": 11.9,
        "expected_confidence": "medium",
        "description": "按月份间隔着填写"
    },
    "insufficient": {
        "file": "【数据缺失过多 无法计算节能率】02-中央空调节能调研表（首页含问题指引）-工业板块.xlsx",
        "expected_rate": None,  # 无法计算
        "expected_confidence": "low",  # <50%
        "description": "数据缺失过多，无法计算节能率"
    }
}


def get_survey_path(survey_key: str) -> Path:
    """获取示例调研表的完整路径"""
    config = SAMPLE_SURVEYS.get(survey_key)
    if not config:
        raise ValueError(f"Unknown survey key: {survey_key}")

    path = SAMPLE_DIR / config["file"]
    if not path.exists():
        raise FileNotFoundError(f"Survey file not found: {path}")

    return path


def get_all_survey_paths():
    """获取所有示例调研表路径"""
    return {key: get_survey_path(key) for key in SAMPLE_SURVEYS.keys()}
