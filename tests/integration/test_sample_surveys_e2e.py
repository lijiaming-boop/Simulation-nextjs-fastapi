"""示例调研表端到端测试"""
import pytest
import json
import shutil
from pathlib import Path
from core.skill_caller import SkillCaller
from core.data_filler import DataFiller
from core.excel_calculator import ExcelCalculator
from tests.fixtures.sample_surveys import SAMPLE_SURVEYS, get_survey_path

# 临时文件目录
TMP_DIR = Path(__file__).parent.parent.parent / "tmp"


class TestHelper:
    """测试辅助类"""

    @staticmethod
    def setup_tmp_dir():
        """创建临时目录"""
        TMP_DIR.mkdir(exist_ok=True)

    @staticmethod
    def cleanup_tmp_dir():
        """清理临时目录"""
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR)
            TMP_DIR.mkdir(exist_ok=True)

    @staticmethod
    def load_json(file_path: Path):
        """加载JSON文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def validate_extracted_data(data: dict):
        """验证提取的数据结构"""
        assert "basic_info" in data, "缺少基础信息"
        assert "monthly_data" in data, "缺少月度数据"
        assert isinstance(data["monthly_data"], list), "月度数据应为列表"
        assert len(data["monthly_data"]) == 12, "应有12个月数据"

    @staticmethod
    def validate_quality_report(report: dict):
        """验证质量报告结构"""
        assert "completeness_rate" in report, "缺少完整率"
        assert "confidence_level" in report, "缺少置信度"
        assert "issues" in report, "缺少问题列表"
        assert "summary" in report, "缺少总结"

        # 验证置信度级别
        assert report["confidence_level"] in ["high", "medium", "low"], \
            f"无效的置信度级别: {report['confidence_level']}"

    @staticmethod
    def validate_filling_suggestions(suggestions: dict):
        """验证填充建议结构"""
        assert "suggestions" in suggestions, "缺少填充建议"
        assert isinstance(suggestions["suggestions"], list), "填充建议应为列表"

    @staticmethod
    def calculate_rate_tolerance(expected_rate: float) -> float:
        """计算节能率容差（允许±0.5%的误差）"""
        return 0.5
