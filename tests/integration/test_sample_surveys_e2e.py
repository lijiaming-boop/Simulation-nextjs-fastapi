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

    def test_full_workflow_complete_survey(self):
        """测试【齐全】数据的完整工作流：提取→填充→计算"""
        survey_path = get_survey_path("complete")

        # === 阶段1: 提取和质量检查 ===
        caller = SkillCaller(timeout=300)
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"], "提取失败"

        # 加载提取结果
        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        extracted_data = extract_check["extracted_data"]
        quality_report = extract_check["quality_report"]

        # === 阶段2: 生成填充建议 ===
        # 保存单独的文件供 suggest-data-filling 使用
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)

        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        # 调用 suggest-data-filling skill
        suggest_result = caller.call_skill(
            "suggest-data-filling",
            str(TMP_DIR / "quality_report.json"),
            str(TMP_DIR / "filling_suggestions.json")
        )
        assert suggest_result["success"], "生成填充建议失败"

        # 加载填充建议
        filling_suggestions = TestHelper.load_json(TMP_DIR / "filling_suggestions.json")
        TestHelper.validate_filling_suggestions(filling_suggestions)

        # === 阶段3: 应用填充建议 ===
        filler = DataFiller()
        filled_data_path = filler.fill_data(
            str(TMP_DIR / "extracted_data.json"),
            str(TMP_DIR / "filling_suggestions.json"),
            str(TMP_DIR / "filled_data.json")
        )

        # 加载填充后的数据供验证使用
        filled_data = TestHelper.load_json(Path(filled_data_path))

        # === 阶段4: 计算节能率 ===
        template_path = Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calculator = ExcelCalculator(str(template_path))
        calc_result_path = calculator.calculate(
            str(TMP_DIR / "filled_data.json"),
            str(TMP_DIR / "calc_result.json")
        )

        # 加载计算结果供验证使用
        calc_result = TestHelper.load_json(Path(calc_result_path))

        # 验证计算结果
        assert "energy_saving_rate" in calc_result, "缺少节能率"
        assert "total_saving" in calc_result, "缺少总节能量"

        # 验证节能率在预期范围内（±0.5%）
        expected_rate = SAMPLE_SURVEYS["complete"]["expected_rate"]
        actual_rate = calc_result["energy_saving_rate"] * 100  # 转换为百分比
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差过大: 期望 {expected_rate}%, 实际 {actual_rate:.2f}%, 容差 ±{tolerance}%"

        print(f"✓ 【齐全】数据完整流程测试通过")
        print(f"  - 完整率: {quality_report['completeness_rate']}%")
        print(f"  - 置信度: {quality_report['confidence_level']}")
        print(f"  - 节能率: {actual_rate:.2f}% (期望 {expected_rate}%)")
        print(f"  - 总节能量: {calc_result['total_saving']:.2f} kWh")
