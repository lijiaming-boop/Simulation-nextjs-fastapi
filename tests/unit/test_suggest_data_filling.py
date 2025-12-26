"""
测试数据填充建议生成器
"""

import json
import pytest
from pathlib import Path
import sys

# 添加脚本路径到Python路径
scripts_path = Path(__file__).parent.parent.parent / ".claude/skills/suggest-data-filling/scripts"
sys.path.insert(0, str(scripts_path))

from generate_suggestions import generate_suggestions


def test_extract_project_region_from_input():
    """测试从extracted_data中提取项目地区"""
    extracted_data = {
        "project_region": "华南",
        "monthly_data": [{"month": i} for i in range(1, 13)]
    }

    quality_report = {"confidence_level": "medium"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    assert suggestions["project_region"]["suggested_value"] == "华南"
    assert suggestions["project_region"]["method"] == "auto_extracted"
    assert suggestions["project_region"]["confidence"] == "high"


def test_missing_project_region_requires_manual_input():
    """测试缺失项目地区时要求手动输入"""
    extracted_data = {
        "monthly_data": [{"month": i} for i in range(1, 13)]
        # 故意不包含 project_region
    }

    quality_report = {"confidence_level": "medium"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    assert suggestions["project_region"]["suggested_value"] is None
    assert suggestions["project_region"]["method"] == "manual_input"
    assert suggestions["project_region"]["confidence"] == "none"
