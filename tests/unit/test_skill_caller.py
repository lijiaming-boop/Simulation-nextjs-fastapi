"""测试 Skill 调用封装"""
import pytest
from pathlib import Path
from core.skill_caller import SkillCaller, SkillError


def test_skill_caller_initialization():
    """测试 SkillCaller 初始化"""
    caller = SkillCaller(timeout=300)
    assert caller.timeout == 300


def test_call_skill_with_invalid_name():
    """测试调用不存在的 Skill"""
    caller = SkillCaller()

    with pytest.raises(SkillError) as exc_info:
        caller.call_skill("non-existent-skill", "arg1")

    assert "Skill not found" in str(exc_info.value) or "执行出错" in str(exc_info.value)


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
