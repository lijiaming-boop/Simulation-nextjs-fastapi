"""测试 Skill 调用封装"""
import pytest
import asyncio
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from core.skill_caller import SkillCaller, SkillError


def test_skill_caller_initialization():
    """测试 SkillCaller 初始化"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller(timeout=300)
        assert caller.timeout == 300


def test_call_skill_with_invalid_name():
    """测试调用不存在的 Skill"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller()

        with pytest.raises(SkillError) as exc_info:
            caller.call_skill("non-existent-skill", "arg1")

        assert "Skill not found" in str(exc_info.value)


@pytest.mark.skipif(
    not Path(".claude/skills/extract-survey-data.md").exists(),
    reason="Skills not yet implemented"
)
def test_call_extract_survey_data_skill(tmp_path):
    """测试调用数据提取 Skill (需要 Skill 文件存在)"""
    caller = SkillCaller()

    # 这个测试在 Skills 实现后才能通过
    survey_path = "00_sample/02-中央空调节能调研表.xlsx"
    output_path = tmp_path / "extracted_data.json"

    result = caller.call_skill(
        "extract-survey-data",
        survey_path,
        str(output_path)
    )

    assert Path(output_path).exists()


@pytest.mark.asyncio
async def test_skill_caller_async_initialization():
    """测试异步 SkillCaller 初始化"""
    with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
        caller = SkillCaller(timeout=300)
        assert caller.timeout == 300
        assert caller.api_key == 'test-key'
        assert caller.project_root is not None


@pytest.mark.asyncio
async def test_skill_caller_missing_api_key():
    """测试缺失 API key 时抛出错误"""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(SkillError) as exc_info:
            SkillCaller()
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)
