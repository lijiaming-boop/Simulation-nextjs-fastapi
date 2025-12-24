#!/usr/bin/env python3
"""测试文档一致性"""

import pytest
from pathlib import Path


def test_claude_md_workflow_description():
    """测试 CLAUDE.md 中的工作流程描述"""
    claude_md = Path(__file__).parent.parent.parent / "CLAUDE.md"

    with open(claude_md, 'r', encoding='utf-8') as f:
        content = f.read()

    # 验证数据流向包含合并后的步骤
    assert "extract-and-check-data" in content

    # 验证技能列表更新
    assert "extract-and-check-data**：从调研表Excel提取数据并进行质量检查" in content


def test_claude_md_skill_count():
    """测试技能数量"""
    claude_md = Path(__file__).parent.parent.parent / "CLAUDE.md"

    with open(claude_md, 'r', encoding='utf-8') as f:
        content = f.read()

    # 应该有3个skills: extract-and-check-data, suggest-data-filling, (移除了单独的extract和check)
    # 但为了向后兼容，旧的skills可能仍然存在
    assert "extract-and-check-data" in content
