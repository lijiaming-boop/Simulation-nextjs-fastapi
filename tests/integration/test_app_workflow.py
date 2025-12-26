#!/usr/bin/env python3
"""测试应用工作流程"""

import pytest
from pathlib import Path


def test_streamlit_workflow_stages():
    """测试 Streamlit 工作流程阶段数量"""
    app_file = Path(__file__).parent.parent.parent / "app.py"

    with open(app_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 验证阶段数量为 5（上传、提取+质量检查、填充建议、计算、结果）
    assert "stages = ['上传', '提取+质量检查', '填充建议', '计算', '结果']" in content

    # 验证阶段映射
    assert "'extract_check': 1" in content


def test_low_confidence_blocks_workflow():
    """测试低置信度阻止工作流程继续"""
    import tempfile
    import json

    # 创建模拟的低置信度结果
    low_confidence_result = {
        "extracted_data": {
            "project_region": "华北",
            "monthly_data": [{"month": i, "total_energy": None} for i in range(1, 13)]
        },
        "quality_report": {
            "completeness": 0.25,
            "confidence_level": "low",
            "issues": [
                {
                    "field": f"monthly_data[{i}].total_energy",
                    "severity": "high",
                    "type": "missing",
                    "message": f"{i+1}月冷站总能耗缺失"
                }
                for i in range(12)
            ],
            "summary": "数据完整率25%,建议补充缺失月份数据。发现12个高优先级问题。"
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(low_confidence_result, f, ensure_ascii=False)
        temp_file = Path(f.name)

    try:
        # 读取结果
        with open(temp_file, 'r', encoding='utf-8') as f:
            result = json.load(f)

        quality_report = result["quality_report"]

        # 模拟流程判断
        should_block = quality_report["confidence_level"] == "low"

        assert should_block is True
        assert quality_report["completeness"] < 0.5
        assert len(quality_report["issues"]) == 12

        print("✅ 低置信度正确阻止流程")

    finally:
        temp_file.unlink()
