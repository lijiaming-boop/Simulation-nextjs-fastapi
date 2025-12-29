"""测试原始文件名保留和地区推断功能"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.skill_caller import SkillCaller


class TestOriginalFilenamePreservation:
    """测试原始文件名保留功能"""

    def test_skill_caller_accepts_variable_args(self):
        """测试 SkillCaller 支持可变参数"""
        # 模拟 API key 环境变量
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            caller = SkillCaller(timeout=30)

            # 验证 _build_prompt 方法接受可变参数
            # 测试传递3个参数时的提示词构建
            prompt = caller._build_prompt(
                "extract-and-check-data",
                "input.xlsx",
                "output.json",
                "惠州光弘-调研表.xlsx"
            )

            # 验证提示词包含所有参数
            assert "input.xlsx" in prompt
            assert "output.json" in prompt
            assert "惠州光弘-调研表.xlsx" in prompt
            assert "原始文件名" in prompt


class TestRegionInferenceFromFilename:
    """测试从文件名推断地区"""

    def test_region_inference_from_filename_priority_2(self):
        """测试优先级2: 从原始文件名推断地区"""
        # 导入提取函数 - 需要从正确的路径导入
        # 注意: 路径需要匹配实际的 skill 脚本位置
        sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))

        from extract_and_check_data import (
            extract_region_from_filename,
            infer_region_from_text
        )

        # 测试各种文件名格式
        test_cases = [
            ("惠州光弘-调研表.xlsx", "华南"),
            ("石家庄仁和药业中央空调节能调研表.xlsx", "华北"),
            ("深圳工业园-2024年调研.xlsx", "华南"),
            ("北京总部-节能调研表.xlsx", "华北"),
            ("/tmp/upload/武汉分公司-调研表.xlsx", "华中"),
        ]

        for filename, expected_region in test_cases:
            result = extract_region_from_filename(filename)
            assert result == expected_region, f"文件名 '{filename}' 应推断为 {expected_region}, 实际为 {result}"
