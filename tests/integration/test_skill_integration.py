"""Skill 集成测试（需要有效的 ANTHROPIC_API_KEY）"""
import pytest
import os
import json
from pathlib import Path
from core.skill_caller import SkillCaller, SkillError


@pytest.mark.skipif(
    not os.getenv('ANTHROPIC_API_KEY'),
    reason="需要 ANTHROPIC_API_KEY 环境变量"
)
@pytest.mark.integration
class TestSkillIntegration:
    """Skills 集成测试（真实 API 调用）"""

    @pytest.fixture
    def skill_caller(self):
        """创建 SkillCaller 实例"""
        project_root = Path(__file__).parent.parent.parent
        return SkillCaller(timeout=300, project_root=project_root)

    @pytest.fixture
    def tmp_output_dir(self, tmp_path):
        """创建临时输出目录"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        return output_dir

    def test_extract_survey_data_skill_real_call(
        self, skill_caller, tmp_output_dir
    ):
        """测试真实调用 extract-survey-data skill"""
        # 使用样例文件
        survey_file = "00_sample/02-中央空调节能调研表（首页含问题指引）-工业板块.xlsx"
        output_file = tmp_output_dir / "extracted_data.json"

        # 检查样例文件是否存在
        if not Path(survey_file).exists():
            pytest.skip(f"样例文件不存在: {survey_file}")

        # 调用 skill
        result = skill_caller.call_skill(
            "extract-survey-data",
            str(survey_file),
            str(output_file)
        )

        # 验证输出文件生成
        assert output_file.exists(), "输出文件应该被创建"

        # 验证 JSON 格式
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 验证必要字段
        assert "project_region" in data
        assert "monthly_data" in data
        assert isinstance(data["monthly_data"], list)

    def test_skill_not_found_error(self, skill_caller):
        """测试调用不存在的 skill"""
        with pytest.raises(SkillError) as exc_info:
            skill_caller.call_skill("non-existent-skill", "arg1")

        assert "Skill not found" in str(exc_info.value)
