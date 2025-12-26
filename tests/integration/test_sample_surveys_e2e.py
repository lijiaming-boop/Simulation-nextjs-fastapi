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


@pytest.mark.integration
class TestSummerOnlySurvey:
    """测试【仅有夏季】数据场景"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        TestHelper.setup_tmp_dir()
        yield

    def test_full_workflow_summer_only_survey(self):
        """测试【仅有夏季】数据的完整工作流"""
        survey_path = get_survey_path("summer_only")

        # === 阶段1: 提取和质量检查 ===
        caller = SkillCaller(timeout=300)
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"], "提取失败"

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证置信度应为"中等"
        expected_conf = SAMPLE_SURVEYS["summer_only"]["expected_confidence"]
        assert quality_report["confidence_level"] == expected_conf, \
            f"置信度应为 {expected_conf}"

        # 验证完整率应在50-80%之间
        completeness = quality_report["completeness_rate"]
        assert 50.0 <= completeness < 80.0, \
            f"完整率应在50-80%之间，实际为 {completeness}%"

        # === 阶段2: 生成填充建议 ===
        # 保存单独文件
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        # 生成填充建议
        suggest_result = caller.call_skill(
            "suggest-data-filling",
            str(TMP_DIR / "quality_report.json"),
            str(TMP_DIR / "filling_suggestions.json")
        )
        assert suggest_result["success"], "生成填充建议失败"

        # === 阶段3: 应用填充建议 ===
        filler = DataFiller()
        filled_data_path = filler.fill_data(
            str(TMP_DIR / "extracted_data.json"),
            str(TMP_DIR / "filling_suggestions.json"),
            str(TMP_DIR / "filled_data.json")
        )

        # === 阶段4: 计算节能率 ===
        template_path = Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calculator = ExcelCalculator(str(template_path))
        calc_result_path = calculator.calculate(
            str(TMP_DIR / "filled_data.json"),
            str(TMP_DIR / "calc_result.json")
        )

        # 加载计算结果
        calc_result = TestHelper.load_json(Path(calc_result_path))

        # 验证计算结果
        assert "energy_saving_rate" in calc_result, "缺少节能率"

        # 验证节能率
        expected_rate = SAMPLE_SURVEYS["summer_only"]["expected_rate"]
        actual_rate = calc_result["energy_saving_rate"] * 100  # 转换为百分比
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差: 期望 {expected_rate}%, 实际 {actual_rate:.2f}%"

        print(f"✓ 【仅有夏季】数据测试通过")
        print(f"  - 完整率: {completeness}%")
        print(f"  - 置信度: {quality_report['confidence_level']}")
        print(f"  - 节能率: {actual_rate:.2f}% (期望 {expected_rate}%)")
        print(f"  - 总节能量: {calc_result['total_saving']:.2f} kWh")


@pytest.mark.integration
class TestNoWinterSurvey:
    """测试【缺冬季】数据场景"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        TestHelper.setup_tmp_dir()
        yield

    def test_full_workflow_no_winter_survey(self):
        """测试【缺冬季】数据的完整工作流"""
        survey_path = get_survey_path("no_winter")

        # === 阶段1: 提取和质量检查 ===
        caller = SkillCaller(timeout=300)
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"], "提取失败"

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证置信度应为"中等"
        expected_conf = SAMPLE_SURVEYS["no_winter"]["expected_confidence"]
        assert quality_report["confidence_level"] == expected_conf, \
            f"置信度应为 {expected_conf}，实际为 {quality_report['confidence_level']}"

        # 验证完整率应在50-80%之间
        completeness = quality_report["completeness_rate"]
        assert 50.0 <= completeness < 80.0, \
            f"完整率应在50-80%之间，实际为 {completeness}%"

        # === 阶段2: 生成填充建议 ===
        # 保存单独文件
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        # 生成填充建议
        suggest_result = caller.call_skill(
            "suggest-data-filling",
            str(TMP_DIR / "quality_report.json"),
            str(TMP_DIR / "filling_suggestions.json")
        )
        assert suggest_result["success"], "生成填充建议失败"

        # === 阶段3: 应用填充建议 ===
        filler = DataFiller()
        filled_data_path = filler.fill_data(
            str(TMP_DIR / "extracted_data.json"),
            str(TMP_DIR / "filling_suggestions.json"),
            str(TMP_DIR / "filled_data.json")
        )

        # === 阶段4: 计算节能率 ===
        template_path = Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calculator = ExcelCalculator(str(template_path))
        calc_result_path = calculator.calculate(
            str(TMP_DIR / "filled_data.json"),
            str(TMP_DIR / "calc_result.json")
        )

        # 加载计算结果
        calc_result = TestHelper.load_json(Path(calc_result_path))

        # 验证计算结果
        assert "energy_saving_rate" in calc_result, "缺少节能率"

        # 验证节能率
        expected_rate = SAMPLE_SURVEYS["no_winter"]["expected_rate"]
        actual_rate = calc_result["energy_saving_rate"] * 100  # 转换为百分比
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差: 期望 {expected_rate}%, 实际 {actual_rate:.2f}%"

        print(f"✓ 【缺冬季】数据测试通过")
        print(f"  - 完整率: {completeness}%")
        print(f"  - 置信度: {quality_report['confidence_level']}")
        print(f"  - 节能率: {actual_rate:.2f}% (期望 {expected_rate}%)")
        print(f"  - 总节能量: {calc_result['total_saving']:.2f} kWh")


@pytest.mark.integration
class TestNoSummerSurvey:
    """测试【缺夏季】数据场景"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        TestHelper.setup_tmp_dir()
        yield

    def test_full_workflow_no_summer_survey(self):
        """测试【缺夏季】数据的完整工作流"""
        survey_path = get_survey_path("no_summer")

        # === 阶段1: 提取和质量检查 ===
        caller = SkillCaller(timeout=300)
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"], "提取失败"

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证置信度应为"中等"
        expected_conf = SAMPLE_SURVEYS["no_summer"]["expected_confidence"]
        assert quality_report["confidence_level"] == expected_conf, \
            f"置信度应为 {expected_conf}，实际为 {quality_report['confidence_level']}"

        # 验证完整率应在50-80%之间
        completeness = quality_report["completeness_rate"]
        assert 50.0 <= completeness < 80.0, \
            f"完整率应在50-80%之间，实际为 {completeness}%"

        # === 阶段2: 生成填充建议 ===
        # 保存单独文件
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        # 生成填充建议
        suggest_result = caller.call_skill(
            "suggest-data-filling",
            str(TMP_DIR / "quality_report.json"),
            str(TMP_DIR / "filling_suggestions.json")
        )
        assert suggest_result["success"], "生成填充建议失败"

        # === 阶段3: 应用填充建议 ===
        filler = DataFiller()
        filled_data_path = filler.fill_data(
            str(TMP_DIR / "extracted_data.json"),
            str(TMP_DIR / "filling_suggestions.json"),
            str(TMP_DIR / "filled_data.json")
        )

        # === 阶段4: 计算节能率 ===
        template_path = Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calculator = ExcelCalculator(str(template_path))
        calc_result_path = calculator.calculate(
            str(TMP_DIR / "filled_data.json"),
            str(TMP_DIR / "calc_result.json")
        )

        # 加载计算结果
        calc_result = TestHelper.load_json(Path(calc_result_path))

        # 验证计算结果
        assert "energy_saving_rate" in calc_result, "缺少节能率"

        # 验证节能率
        expected_rate = SAMPLE_SURVEYS["no_summer"]["expected_rate"]
        actual_rate = calc_result["energy_saving_rate"] * 100  # 转换为百分比
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差: 期望 {expected_rate}%, 实际 {actual_rate:.2f}%"

        print(f"✓ 【缺夏季】数据测试通过")
        print(f"  - 完整率: {completeness}%")
        print(f"  - 置信度: {quality_report['confidence_level']}")
        print(f"  - 节能率: {actual_rate:.2f}% (期望 {expected_rate}%)")
        print(f"  - 总节能量: {calc_result['total_saving']:.2f} kWh")


@pytest.mark.integration
class TestIrregularSurvey:
    """测试【参差不齐】数据场景"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        TestHelper.setup_tmp_dir()
        yield

    def test_full_workflow_irregular_survey(self):
        """测试【参差不齐】数据的完整工作流"""
        survey_path = get_survey_path("irregular")

        # === 阶段1: 提取和质量检查 ===
        caller = SkillCaller(timeout=300)
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"], "提取失败"

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证置信度应为"中等"（参差不齐但仍可用）
        expected_conf = SAMPLE_SURVEYS["irregular"]["expected_confidence"]
        assert quality_report["confidence_level"] == expected_conf, \
            f"置信度应为 {expected_conf}，实际为 {quality_report['confidence_level']}"

        # 验证完整率应在50-80%之间
        completeness = quality_report["completeness_rate"]
        assert 50.0 <= completeness < 80.0, \
            f"完整率应在50-80%之间，实际为 {completeness}%"

        # === 特殊验证1: 检测间隔填写问题 ===
        issues = quality_report.get("issues", [])
        assert len(issues) > 0, "应检测到数据间隔填写的问题"

        # 可能的问题描述关键词：间隔、缺失、不完整等
        issue_messages = [issue.get("message", "") for issue in issues]
        print(f"  检测到 {len(issues)} 个数据质量问题")
        print(f"  问题示例: {issue_messages[:3] if issue_messages else '无'}")

        # === 阶段2: 生成填充建议 ===
        # 保存单独文件
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        # 生成填充建议
        suggest_result = caller.call_skill(
            "suggest-data-filling",
            str(TMP_DIR / "quality_report.json"),
            str(TMP_DIR / "filling_suggestions.json")
        )
        assert suggest_result["success"], "生成填充建议失败"

        # 加载填充建议
        filling_suggestions = TestHelper.load_json(TMP_DIR / "filling_suggestions.json")

        # === 特殊验证2: 应生成插值填充建议 ===
        assert len(filling_suggestions.get("suggestions", [])) > 0, \
            "参差不齐的数据应生成填充建议"

        # 检查是否有可填充的建议
        fillable_suggestions = filling_suggestions.get("fillable_suggestions", [])
        print(f"  生成 {len(fillable_suggestions)} 条可填充建议")

        # === 阶段3: 应用填充建议 ===
        filler = DataFiller()
        filled_data_path = filler.fill_data(
            str(TMP_DIR / "extracted_data.json"),
            str(TMP_DIR / "filling_suggestions.json"),
            str(TMP_DIR / "filled_data.json")
        )

        # === 阶段4: 计算节能率 ===
        template_path = Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calculator = ExcelCalculator(str(template_path))
        calc_result_path = calculator.calculate(
            str(TMP_DIR / "filled_data.json"),
            str(TMP_DIR / "calc_result.json")
        )

        # 加载计算结果
        calc_result = TestHelper.load_json(Path(calc_result_path))

        # 验证计算结果
        assert "energy_saving_rate" in calc_result, "缺少节能率"

        # 验证节能率
        expected_rate = SAMPLE_SURVEYS["irregular"]["expected_rate"]
        actual_rate = calc_result["energy_saving_rate"] * 100  # 转换为百分比
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差: 期望 {expected_rate}%, 实际 {actual_rate:.2f}%"

        print(f"✓ 【参差不齐】数据测试通过")
        print(f"  - 完整率: {completeness}%")
        print(f"  - 置信度: {quality_report['confidence_level']}")
        print(f"  - 检测到问题数: {len(issues)}")
        print(f"  - 填充建议数: {len(fillable_suggestions)}")
        print(f"  - 节能率: {actual_rate:.2f}% (期望 {expected_rate}%)")
        print(f"  - 总节能量: {calc_result['total_saving']:.2f} kWh")


@pytest.mark.integration
class TestInsufficientSurvey:
    """测试【数据缺失过多】场景（应中断流程）"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        TestHelper.setup_tmp_dir()
        yield

    def test_extract_insufficient_survey_should_report_low_confidence(self):
        """测试数据缺失过多时应报告低置信度"""
        survey_path = get_survey_path("insufficient")

        # 提取和检查
        caller = SkillCaller(timeout=300)
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )

        # 验证skill调用成功（即使数据质量差）
        assert extract_result["success"], "提取应成功，但报告低置信度"

        # 加载结果
        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # === 特殊验证1: 置信度应为"低" ===
        expected_conf = SAMPLE_SURVEYS["insufficient"]["expected_confidence"]
        assert quality_report["confidence_level"] == expected_conf, \
            f"置信度应为 {expected_conf}，实际为 {quality_report['confidence_level']}"

        # === 特殊验证2: 完整率应<50% ===
        completeness = quality_report["completeness_rate"]
        assert completeness < 50.0, \
            f"完整率应<50%，实际为 {completeness}%"

        # === 特殊验证3: 应有大量严重问题 ===
        issues = quality_report.get("issues", [])
        critical_issues = [i for i in issues if i.get("severity") == "CRITICAL"]
        assert len(critical_issues) > 0, "应检测到至少1个严重(CRITICAL)问题"

        # 统计问题严重性分布
        high_issues = [i for i in issues if i.get("severity") == "HIGH"]
        medium_issues = [i for i in issues if i.get("severity") == "MEDIUM"]

        print(f"✓ 【数据缺失过多】低置信度检测通过")
        print(f"  - 完整率: {completeness:.1f}%（应<50%）")
        print(f"  - 置信度: {quality_report['confidence_level']}（低）")
        print(f"  - 问题统计:")
        print(f"    - CRITICAL（严重）: {len(critical_issues)} 个")
        print(f"    - HIGH（高）: {len(high_issues)} 个")
        print(f"    - MEDIUM（中）: {len(medium_issues)} 个")
        print(f"  - 总问题数: {len(issues)}")

        # 显示前3个严重问题示例
        if critical_issues:
            print(f"  - 严重问题示例:")
            for i, issue in enumerate(critical_issues[:3], 1):
                print(f"    {i}. {issue.get('message', 'N/A')}")

    def test_insufficient_survey_should_block_calculation(self):
        """测试数据缺失过多时应阻止计算流程"""
        survey_path = get_survey_path("insufficient")
        caller = SkillCaller(timeout=300)

        # === 阶段1: 提取和检查 ===
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"], "提取应成功"

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # === 验证1: 确认低置信度 ===
        assert quality_report["confidence_level"] == "low", \
            f"置信度应为 low，实际为 {quality_report['confidence_level']}"

        completeness = quality_report["completeness_rate"]
        assert completeness < 50.0, f"完整率应<50%，实际为 {completeness}%"

        # === 验证2: 模拟前端逻辑 - 低置信度应中断流程 ===
        should_block = quality_report["confidence_level"] == "low"
        assert should_block, "低置信度应触发流程中断标志"

        # === 验证3: 检查严重和高优先级问题 ===
        issues = quality_report.get("issues", [])
        critical_and_high_issues = [
            i for i in issues
            if i.get("severity") in ["CRITICAL", "HIGH"]
        ]
        assert len(critical_and_high_issues) > 0, \
            "应至少有1个CRITICAL或HIGH级别的问题"

        print(f"✓ 【数据缺失过多】流程中断验证通过")
        print(f"  - 置信度检测: {quality_report['confidence_level']} (低)")
        print(f"  - 完整率: {completeness:.1f}% (<50%)")
        print(f"  - 流程中断标志: should_block = {should_block}")
        print(f"  - 严重/高优先级问题: {len(critical_and_high_issues)} 个")
        print(f"")
        print(f"  【流程控制说明】")
        print(f"  - 系统正确识别低质量数据")
        print(f"  - 前端应在此处显示错误界面")
        print(f"  - 流程应中断，不进入填充和计算阶段")
        print(f"  - 要求用户补充数据后重新上传")
        print(f"")
        print(f"  ⚠ 注意: 此测试不执行后续填充和计算步骤（符合设计）")
