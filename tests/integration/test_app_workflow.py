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
