"""测试向后兼容性 - 确保 app.py 中的调用方式仍然有效"""
import pytest
import os
from pathlib import Path
from core.skill_caller import SkillCaller, SkillError


@pytest.mark.skipif(
    not os.getenv('ANTHROPIC_API_KEY'),
    reason="需要 ANTHROPIC_API_KEY 环境变量"
)
@pytest.mark.integration
class TestBackwardCompatibility:
    """测试新实现与现有代码的兼容性"""

    def test_app_py_usage_pattern(self):
        """测试 app.py 中的调用模式仍然有效"""
        # 这是 app.py 中的实际调用方式
        caller = SkillCaller(timeout=300)

        # 验证初始化成功
        assert caller is not None
        assert caller.timeout == 300

    def test_exception_type_compatibility(self):
        """测试异常类型保持一致"""
        caller = SkillCaller(timeout=300)

        # 应该抛出 SkillError（不是其他类型）
        with pytest.raises(SkillError):
            caller.call_skill("non-existent-skill", "arg1")

    def test_return_type_compatibility(self):
        """测试返回类型（应该是字符串或 None）"""
        # Mock 测试，不实际调用 API
        caller = SkillCaller(timeout=300)

        # _build_prompt 应该返回字符串
        prompt = caller._build_prompt(
            "extract-survey-data",
            "input.xlsx",
            "output.json"
        )
        assert isinstance(prompt, str)
