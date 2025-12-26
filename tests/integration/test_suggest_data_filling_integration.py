"""
集成测试：suggest-data-filling skill 的项目地区自动提取功能

测试场景:
1. 端到端测试：使用真实的 extracted_data.json
2. 兜底场景：项目地区缺失时的行为
"""

import json
import pytest
from pathlib import Path
import sys

# 添加脚本路径到Python路径
scripts_path = Path(__file__).parent.parent.parent / ".claude/skills/suggest-data-filling/scripts"
sys.path.insert(0, str(scripts_path))

from generate_suggestions import generate_suggestions


def test_e2e_with_real_extracted_data():
    """端到端测试：使用真实的extracted_data.json"""
    base_dir = Path(__file__).parent.parent.parent
    extracted_data_path = base_dir / "tmp" / "extracted_data.json"

    # 跳过测试如果文件不存在
    if not extracted_data_path.exists():
        pytest.skip("tmp/extracted_data.json not found")

    with open(extracted_data_path, 'r', encoding='utf-8') as f:
        extracted_data = json.load(f)

    quality_report = {"confidence_level": "medium"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    # 验证项目地区被自动提取
    assert suggestions["project_region"]["suggested_value"] is not None
    assert suggestions["project_region"]["method"] == "auto_extracted"
    assert suggestions["project_region"]["confidence"] == "high"
    assert suggestions["project_region"]["suggested_value"] in [
        "华南", "华东", "华中", "西南", "西北", "华北", "东北"
    ]

    # 验证月度建议存在
    assert len(suggestions["monthly_suggestions"]) == 12


def test_fallback_when_region_missing():
    """测试项目地区缺失时的兜底行为"""
    extracted_data = {
        "monthly_data": [
            {"month": i, "total_energy": 1000 * i}
            for i in range(1, 13)
        ]
    }

    quality_report = {"confidence_level": "high"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    # 应该要求手动输入
    assert suggestions["project_region"]["suggested_value"] is None
    assert suggestions["project_region"]["method"] == "manual_input"
    assert suggestions["project_region"]["confidence"] == "none"
    assert "用户输入" in suggestions["project_region"]["reason"]
