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


@pytest.mark.integration
class TestCompleteSurvey:
    """测试【齐全】数据场景"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """测试前后的设置和清理"""
        TestHelper.setup_tmp_dir()
        yield
        # 保留临时文件以便检查，不清理

    def test_extract_and_check_complete_survey(self):
        """测试提取和检查齐全的调研表数据"""
        # 获取调研表路径
        survey_path = get_survey_path("complete")

        # 调用 extract-and-check-data skill
        caller = SkillCaller(timeout=300)
        result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )

        # 验证调用成功
        assert result["success"], f"Skill调用失败: {result.get('error')}"

        # 验证输出文件存在
        extract_check_file = TMP_DIR / "extract_check_result.json"
        assert extract_check_file.exists(), "未生成 extract_check_result.json"

        # 加载结果
        result_data = TestHelper.load_json(extract_check_file)

        # 验证结果结构
        assert "extracted_data" in result_data, "缺少提取的数据"
        assert "quality_report" in result_data, "缺少质量报告"

        # 验证提取的数据
        extracted = result_data["extracted_data"]
        TestHelper.validate_extracted_data(extracted)

        # 验证质量报告
        quality = result_data["quality_report"]
        TestHelper.validate_quality_report(quality)

        # 验证置信度应为"高"
        expected_conf = SAMPLE_SURVEYS["complete"]["expected_confidence"]
        assert quality["confidence_level"] == expected_conf, \
            f"置信度应为 {expected_conf}，实际为 {quality['confidence_level']}"

        # 验证完整率应≥80%
        completeness = quality["completeness_rate"]
        assert completeness >= 80.0, \
            f"完整率应≥80%，实际为 {completeness}%"

        print(f"✓ 【齐全】数据提取完成，完整率: {completeness}%，置信度: {quality['confidence_level']}")
