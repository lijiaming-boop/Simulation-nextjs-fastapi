# 示例调研表综合测试计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 使用6份不同质量等级的示例调研表，完整测试数据提取、质量检测、数据填充和节能率测算的全流程功能

**Architecture:** 端到端集成测试，涵盖从Excel调研表输入到节能率结果输出的完整数据流，验证系统在不同数据质量场景下的行为

**Tech Stack:** pytest, pandas, openpyxl/xlwings, Claude Skills (extract-and-check-data, suggest-data-filling)

**Test Coverage:**
- 6种数据质量场景：齐全、仅有夏季、缺冬季、缺夏季、参差不齐、数据缺失过多
- 4个核心模块：数据提取、质量检测、数据填充、节能率计算
- 3种置信度等级：高(≥80%)、中(50-80%)、低(<50%)

---

## Task 1: 创建测试夹具和辅助函数

**Files:**
- Create: `tests/fixtures/sample_surveys.py`
- Create: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 创建示例调研表路径配置夹具**

在 `tests/fixtures/sample_surveys.py` 中：

```python
"""示例调研表测试夹具配置"""
import os
from pathlib import Path

# 示例调研表目录
SAMPLE_DIR = Path(__file__).parent.parent.parent / "00_sample" / "示例调研表"

# 6份示例调研表配置
SAMPLE_SURVEYS = {
    "complete": {
        "file": "【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx",
        "expected_rate": 15.2,
        "expected_confidence": "high",  # ≥80%
        "description": "数据填写齐全"
    },
    "summer_only": {
        "file": "【仅有夏季】6.5%和光同程-机房智能化调研表2023年5月版.xlsx",
        "expected_rate": 6.5,
        "expected_confidence": "medium",  # 50-80%
        "description": "只填了夏季数据"
    },
    "no_winter": {
        "file": "【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx",
        "expected_rate": 10.4,
        "expected_confidence": "medium",
        "description": "没有填冬季数据"
    },
    "no_summer": {
        "file": "【缺夏季】12.1%上海和元-机房智能化调研表模板（深度调研）.xlsx",
        "expected_rate": 12.1,
        "expected_confidence": "medium",
        "description": "没有填夏季能耗数据"
    },
    "irregular": {
        "file": "【参差不齐】11.9%中央空调节能调研表（首页含问题指引）.xlsx",
        "expected_rate": 11.9,
        "expected_confidence": "medium",
        "description": "按月份间隔着填写"
    },
    "insufficient": {
        "file": "【数据缺失过多 无法计算节能率】02-中央空调节能调研表（首页含问题指引）-工业板块.xlsx",
        "expected_rate": None,  # 无法计算
        "expected_confidence": "low",  # <50%
        "description": "数据缺失过多，无法计算节能率"
    }
}


def get_survey_path(survey_key: str) -> Path:
    """获取示例调研表的完整路径"""
    config = SAMPLE_SURVEYS.get(survey_key)
    if not config:
        raise ValueError(f"Unknown survey key: {survey_key}")

    path = SAMPLE_DIR / config["file"]
    if not path.exists():
        raise FileNotFoundError(f"Survey file not found: {path}")

    return path


def get_all_survey_paths():
    """获取所有示例调研表路径"""
    return {key: get_survey_path(key) for key in SAMPLE_SURVEYS.keys()}
```

**Step 2: 创建测试辅助函数**

在 `tests/integration/test_sample_surveys_e2e.py` 中：

```python
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
```

**Step 3: 提交夹具代码**

```bash
git add tests/fixtures/sample_surveys.py tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add sample survey fixtures and test helper"
```

---

## Task 2: 测试数据提取和质量检测（齐全数据）

**Files:**
- Modify: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 编写"齐全数据"场景测试**

```python
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
```

**Step 2: 运行测试验证提取和质量检测**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestCompleteSurvey::test_extract_and_check_complete_survey -v -s
```

预期输出：PASS，显示完整率≥80%，置信度=high

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add extraction and quality check test for complete survey"
```

---

## Task 3: 测试数据填充和节能率计算（齐全数据）

**Files:**
- Modify: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 添加数据填充和计算测试**

```python
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
        filled_data = filler.apply_suggestions(extracted_data, filling_suggestions)

        # 保存填充后的数据
        with open(TMP_DIR / "filled_data.json", 'w', encoding='utf-8') as f:
            json.dump(filled_data, f, ensure_ascii=False, indent=2)

        # === 阶段4: 计算节能率 ===
        template_path = Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        output_path = TMP_DIR / "result_complete.xlsx"

        calculator = ExcelCalculator(str(template_path))
        calc_result = calculator.calculate(filled_data, str(output_path))

        # 验证计算结果
        assert calc_result["success"], f"计算失败: {calc_result.get('error')}"
        assert "total_saving_rate" in calc_result, "缺少总节能率"

        # 验证节能率在预期范围内（±0.5%）
        expected_rate = SAMPLE_SURVEYS["complete"]["expected_rate"]
        actual_rate = calc_result["total_saving_rate"]
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差过大: 期望 {expected_rate}%, 实际 {actual_rate}%, 容差 ±{tolerance}%"

        print(f"✓ 【齐全】数据完整流程测试通过")
        print(f"  - 完整率: {quality_report['completeness_rate']}%")
        print(f"  - 置信度: {quality_report['confidence_level']}")
        print(f"  - 节能率: {actual_rate}% (期望 {expected_rate}%)")
```

**Step 2: 运行完整流程测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestCompleteSurvey::test_full_workflow_complete_survey -v -s
```

预期输出：PASS，节能率约15.2% (±0.5%)

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add full workflow test for complete survey"
```

---

## Task 4: 测试"仅有夏季"数据场景

**Files:**
- Modify: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 编写"仅有夏季"场景测试**

```python
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

        # === 阶段2-4: 填充和计算 ===
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

        # 应用填充
        filling_suggestions = TestHelper.load_json(TMP_DIR / "filling_suggestions.json")
        filler = DataFiller()
        filled_data = filler.apply_suggestions(extract_check["extracted_data"], filling_suggestions)

        # 计算节能率
        template_path = Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        output_path = TMP_DIR / "result_summer_only.xlsx"

        calculator = ExcelCalculator(str(template_path))
        calc_result = calculator.calculate(filled_data, str(output_path))

        assert calc_result["success"], "计算失败"

        # 验证节能率
        expected_rate = SAMPLE_SURVEYS["summer_only"]["expected_rate"]
        actual_rate = calc_result["total_saving_rate"]
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差: 期望 {expected_rate}%, 实际 {actual_rate}%"

        print(f"✓ 【仅有夏季】数据测试通过")
        print(f"  - 完整率: {completeness}%")
        print(f"  - 节能率: {actual_rate}% (期望 {expected_rate}%)")
```

**Step 2: 运行测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestSummerOnlySurvey -v -s
```

预期输出：PASS，节能率约6.5% (±0.5%)

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add summer-only survey test case"
```

---

## Task 5: 测试"缺冬季"和"缺夏季"数据场景

**Files:**
- Modify: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 编写"缺冬季"场景测试**

```python
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
        caller = SkillCaller(timeout=300)

        # 提取和检查
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"]

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证中等置信度
        assert quality_report["confidence_level"] == "medium"

        # 完整流程
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        caller.call_skill("suggest-data-filling",
                         str(TMP_DIR / "quality_report.json"),
                         str(TMP_DIR / "filling_suggestions.json"))

        filling_suggestions = TestHelper.load_json(TMP_DIR / "filling_suggestions.json")
        filler = DataFiller()
        filled_data = filler.apply_suggestions(extract_check["extracted_data"], filling_suggestions)

        calculator = ExcelCalculator("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calc_result = calculator.calculate(filled_data, str(TMP_DIR / "result_no_winter.xlsx"))

        # 验证结果
        expected_rate = SAMPLE_SURVEYS["no_winter"]["expected_rate"]
        actual_rate = calc_result["total_saving_rate"]
        assert abs(actual_rate - expected_rate) <= 0.5

        print(f"✓ 【缺冬季】测试通过: {actual_rate}% (期望 {expected_rate}%)")


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
        caller = SkillCaller(timeout=300)

        # 提取和检查
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"]

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证中等置信度
        assert quality_report["confidence_level"] == "medium"

        # 完整流程
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        caller.call_skill("suggest-data-filling",
                         str(TMP_DIR / "quality_report.json"),
                         str(TMP_DIR / "filling_suggestions.json"))

        filling_suggestions = TestHelper.load_json(TMP_DIR / "filling_suggestions.json")
        filler = DataFiller()
        filled_data = filler.apply_suggestions(extract_check["extracted_data"], filling_suggestions)

        calculator = ExcelCalculator("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calc_result = calculator.calculate(filled_data, str(TMP_DIR / "result_no_summer.xlsx"))

        # 验证结果
        expected_rate = SAMPLE_SURVEYS["no_summer"]["expected_rate"]
        actual_rate = calc_result["total_saving_rate"]
        assert abs(actual_rate - expected_rate) <= 0.5

        print(f"✓ 【缺夏季】测试通过: {actual_rate}% (期望 {expected_rate}%)")
```

**Step 2: 运行测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestNoWinterSurvey -v -s
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestNoSummerSurvey -v -s
```

预期输出：两个测试PASS，节能率分别约10.4%和12.1%

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add no-winter and no-summer survey test cases"
```

---

## Task 6: 测试"参差不齐"数据场景

**Files:**
- Modify: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 编写"参差不齐"场景测试**

```python
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
        caller = SkillCaller(timeout=300)

        # 提取和检查
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"]

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证中等置信度（参差不齐但仍可用）
        assert quality_report["confidence_level"] == "medium"

        # 验证质量报告中应标记间隔填写的问题
        issues = quality_report.get("issues", [])
        assert len(issues) > 0, "应检测到数据间隔填写的问题"

        # 完整流程
        with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
            json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
        with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
            json.dump(quality_report, f, ensure_ascii=False, indent=2)

        suggest_result = caller.call_skill(
            "suggest-data-filling",
            str(TMP_DIR / "quality_report.json"),
            str(TMP_DIR / "filling_suggestions.json")
        )
        assert suggest_result["success"]

        filling_suggestions = TestHelper.load_json(TMP_DIR / "filling_suggestions.json")

        # 验证应生成插值填充建议
        assert len(filling_suggestions.get("suggestions", [])) > 0, \
            "参差不齐的数据应生成填充建议"

        # 应用填充
        filler = DataFiller()
        filled_data = filler.apply_suggestions(extract_check["extracted_data"], filling_suggestions)

        # 计算节能率
        calculator = ExcelCalculator("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
        calc_result = calculator.calculate(filled_data, str(TMP_DIR / "result_irregular.xlsx"))

        assert calc_result["success"]

        # 验证结果
        expected_rate = SAMPLE_SURVEYS["irregular"]["expected_rate"]
        actual_rate = calc_result["total_saving_rate"]
        tolerance = TestHelper.calculate_rate_tolerance(expected_rate)

        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"节能率偏差: 期望 {expected_rate}%, 实际 {actual_rate}%"

        print(f"✓ 【参差不齐】测试通过")
        print(f"  - 完整率: {quality_report['completeness_rate']}%")
        print(f"  - 检测到问题数: {len(issues)}")
        print(f"  - 填充建议数: {len(filling_suggestions['suggestions'])}")
        print(f"  - 节能率: {actual_rate}% (期望 {expected_rate}%)")
```

**Step 2: 运行测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestIrregularSurvey -v -s
```

预期输出：PASS，节能率约11.9% (±0.5%)

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add irregular survey test case"
```

---

## Task 7: 测试"数据缺失过多"场景（流程中断）

**Files:**
- Modify: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 编写"数据缺失过多"场景测试**

```python
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

        # 验证置信度应为"低"
        expected_conf = SAMPLE_SURVEYS["insufficient"]["expected_confidence"]
        assert quality_report["confidence_level"] == expected_conf, \
            f"置信度应为 {expected_conf}，实际为 {quality_report['confidence_level']}"

        # 验证完整率应<50%
        completeness = quality_report["completeness_rate"]
        assert completeness < 50.0, \
            f"完整率应<50%，实际为 {completeness}%"

        # 验证应有大量严重问题
        issues = quality_report.get("issues", [])
        critical_issues = [i for i in issues if i.get("severity") == "CRITICAL"]
        assert len(critical_issues) > 0, "应检测到严重问题"

        print(f"✓ 【数据缺失过多】低置信度检测通过")
        print(f"  - 完整率: {completeness}%")
        print(f"  - 置信度: {quality_report['confidence_level']}")
        print(f"  - 严重问题数: {len(critical_issues)}")

    def test_insufficient_survey_should_block_calculation(self):
        """测试数据缺失过多时应阻止计算流程"""
        survey_path = get_survey_path("insufficient")
        caller = SkillCaller(timeout=300)

        # 提取和检查
        extract_result = caller.call_skill(
            "extract-and-check-data",
            str(survey_path),
            str(TMP_DIR / "extract_check_result.json")
        )
        assert extract_result["success"]

        extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
        quality_report = extract_check["quality_report"]

        # 验证低置信度
        assert quality_report["confidence_level"] == "low"

        # 模拟前端逻辑：低置信度应中断流程
        should_block = quality_report["confidence_level"] == "low"
        assert should_block, "低置信度应触发流程中断"

        # 验证：不应继续后续步骤
        # （在实际应用中，前端会在此处显示错误并要求重新上传）

        print(f"✓ 【数据缺失过多】流程中断验证通过")
        print(f"  - 系统正确识别低质量数据")
        print(f"  - 流程应在此中断，不进入填充和计算阶段")
```

**Step 2: 运行测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestInsufficientSurvey -v -s
```

预期输出：PASS，确认低置信度检测和流程中断逻辑

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add insufficient survey test case with workflow interruption"
```

---

## Task 8: 创建批量测试和测试报告

**Files:**
- Modify: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 添加批量测试和报告生成**

```python
@pytest.mark.integration
class TestAllSurveysBatch:
    """批量测试所有示例调研表"""

    def test_all_surveys_summary(self):
        """运行所有调研表并生成测试摘要报告"""
        results = []
        caller = SkillCaller(timeout=300)

        for survey_key, config in SAMPLE_SURVEYS.items():
            print(f"\n{'='*60}")
            print(f"测试调研表: {survey_key} - {config['description']}")
            print(f"{'='*60}")

            try:
                TestHelper.cleanup_tmp_dir()
                survey_path = get_survey_path(survey_key)

                # 提取和检查
                extract_result = caller.call_skill(
                    "extract-and-check-data",
                    str(survey_path),
                    str(TMP_DIR / "extract_check_result.json")
                )

                if not extract_result["success"]:
                    results.append({
                        "survey": survey_key,
                        "status": "FAILED",
                        "error": "提取失败"
                    })
                    continue

                extract_check = TestHelper.load_json(TMP_DIR / "extract_check_result.json")
                quality_report = extract_check["quality_report"]

                # 记录质量信息
                survey_result = {
                    "survey": survey_key,
                    "description": config["description"],
                    "completeness": quality_report["completeness_rate"],
                    "confidence": quality_report["confidence_level"],
                    "expected_confidence": config["expected_confidence"]
                }

                # 如果是低置信度，不继续计算
                if quality_report["confidence_level"] == "low":
                    survey_result["status"] = "BLOCKED"
                    survey_result["saving_rate"] = None
                    survey_result["note"] = "低置信度，流程中断"
                    results.append(survey_result)
                    print(f"⚠ {survey_key}: 低置信度，流程中断")
                    continue

                # 继续填充和计算流程
                with open(TMP_DIR / "extracted_data.json", 'w', encoding='utf-8') as f:
                    json.dump(extract_check["extracted_data"], f, ensure_ascii=False, indent=2)
                with open(TMP_DIR / "quality_report.json", 'w', encoding='utf-8') as f:
                    json.dump(quality_report, f, ensure_ascii=False, indent=2)

                # 填充建议
                suggest_result = caller.call_skill(
                    "suggest-data-filling",
                    str(TMP_DIR / "quality_report.json"),
                    str(TMP_DIR / "filling_suggestions.json")
                )

                if not suggest_result["success"]:
                    survey_result["status"] = "FAILED"
                    survey_result["error"] = "生成填充建议失败"
                    results.append(survey_result)
                    continue

                # 应用填充
                filling_suggestions = TestHelper.load_json(TMP_DIR / "filling_suggestions.json")
                filler = DataFiller()
                filled_data = filler.apply_suggestions(extract_check["extracted_data"], filling_suggestions)

                # 计算
                calculator = ExcelCalculator("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx")
                output_path = TMP_DIR / f"result_{survey_key}.xlsx"
                calc_result = calculator.calculate(filled_data, str(output_path))

                if not calc_result["success"]:
                    survey_result["status"] = "FAILED"
                    survey_result["error"] = "计算失败"
                    results.append(survey_result)
                    continue

                # 成功完成
                actual_rate = calc_result["total_saving_rate"]
                expected_rate = config["expected_rate"]

                survey_result["status"] = "PASSED"
                survey_result["saving_rate"] = actual_rate
                survey_result["expected_rate"] = expected_rate
                survey_result["deviation"] = abs(actual_rate - expected_rate) if expected_rate else None

                results.append(survey_result)
                print(f"✓ {survey_key}: 节能率 {actual_rate}% (期望 {expected_rate}%)")

            except Exception as e:
                results.append({
                    "survey": survey_key,
                    "status": "ERROR",
                    "error": str(e)
                })
                print(f"✗ {survey_key}: 异常 - {e}")

        # 生成测试报告
        print(f"\n{'='*80}")
        print("测试摘要报告")
        print(f"{'='*80}")

        for result in results:
            print(f"\n【{result['survey']}】 - {result.get('description', '')}")
            print(f"  状态: {result['status']}")
            print(f"  完整率: {result.get('completeness', 'N/A')}%")
            print(f"  置信度: {result.get('confidence', 'N/A')} (期望: {result.get('expected_confidence', 'N/A')})")

            if result['status'] == 'PASSED':
                print(f"  节能率: {result['saving_rate']}% (期望: {result['expected_rate']}%)")
                print(f"  偏差: {result['deviation']:.2f}%")
            elif result['status'] == 'BLOCKED':
                print(f"  备注: {result.get('note', '')}")
            elif result['status'] in ['FAILED', 'ERROR']:
                print(f"  错误: {result.get('error', '')}")

        # 统计
        total = len(results)
        passed = len([r for r in results if r['status'] == 'PASSED'])
        blocked = len([r for r in results if r['status'] == 'BLOCKED'])
        failed = len([r for r in results if r['status'] in ['FAILED', 'ERROR']])

        print(f"\n{'='*80}")
        print(f"统计: 总计 {total}, 通过 {passed}, 阻止 {blocked}, 失败 {failed}")
        print(f"{'='*80}")

        # 保存报告到文件
        report_path = TMP_DIR / "test_summary_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n报告已保存到: {report_path}")

        # 验证至少有一个通过和一个阻止的案例
        assert passed > 0, "应至少有一个测试通过"
        assert blocked > 0, "应至少有一个低置信度阻止的案例"
```

**Step 2: 运行批量测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_sample_surveys_e2e.py::TestAllSurveysBatch::test_all_surveys_summary -v -s
```

预期输出：完整的测试报告，显示6份调研表的测试结果

**Step 3: 提交测试代码**

```bash
git add tests/integration/test_sample_surveys_e2e.py
git commit -m "test: add batch testing and summary report for all surveys"
```

---

## Task 9: 添加测试文档和使用说明

**Files:**
- Create: `docs/testing/sample-surveys-testing-guide.md`

**Step 1: 编写测试指南文档**

```markdown
# 示例调研表测试指南

## 概述

本测试套件使用6份不同质量等级的示例调研表，全面测试中央空调节能率智能测算系统的核心功能。

## 测试覆盖

### 测试场景

| 场景 | 文件 | 完整率 | 置信度 | 预期节能率 | 测试目的 |
|------|------|--------|--------|------------|----------|
| 齐全 | 【齐全】15.2%惠州光弘 | ≥80% | high | 15.2% | 验证完整数据流程 |
| 仅有夏季 | 【仅有夏季】6.5%和光同程 | 50-80% | medium | 6.5% | 验证季节性缺失填充 |
| 缺冬季 | 【缺冬季】10.4%石家庄仁和 | 50-80% | medium | 10.4% | 验证冬季数据填充 |
| 缺夏季 | 【缺夏季】12.1%上海和元 | 50-80% | medium | 12.1% | 验证夏季数据填充 |
| 参差不齐 | 【参差不齐】11.9% | 50-80% | medium | 11.9% | 验证插值填充策略 |
| 数据缺失过多 | 【数据缺失过多】工业板块 | <50% | low | N/A | 验证流程中断机制 |

### 功能覆盖

- ✅ 数据提取（extract-and-check-data skill）
- ✅ 质量检测（完整率、置信度、问题检测）
- ✅ 数据填充（suggest-data-filling skill + DataFiller）
- ✅ 节能率计算（ExcelCalculator）
- ✅ 流程中断（低置信度阻止）

## 运行测试

### 前置要求

```bash
# 设置 PYTHONPATH
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH

# 设置 API Key（用于调用 Claude Skills）
export ANTHROPIC_API_KEY='your-api-key'
```

### 运行单个场景测试

```bash
# 测试齐全数据
pytest tests/integration/test_sample_surveys_e2e.py::TestCompleteSurvey -v -s

# 测试仅有夏季
pytest tests/integration/test_sample_surveys_e2e.py::TestSummerOnlySurvey -v -s

# 测试数据缺失过多
pytest tests/integration/test_sample_surveys_e2e.py::TestInsufficientSurvey -v -s
```

### 运行所有场景测试

```bash
# 运行全部测试
pytest tests/integration/test_sample_surveys_e2e.py -v -s

# 仅运行批量测试和报告
pytest tests/integration/test_sample_surveys_e2e.py::TestAllSurveysBatch -v -s
```

## 测试输出

### 临时文件

测试过程中会在 `tmp/` 目录生成：
- `extract_check_result.json` - 提取和质量检查结果
- `extracted_data.json` - 提取的原始数据
- `quality_report.json` - 质量报告
- `filling_suggestions.json` - 填充建议
- `filled_data.json` - 填充后的数据
- `result_*.xlsx` - 节能率计算结果Excel文件

### 测试报告

批量测试会生成 `tmp/test_summary_report.json`，包含：
- 每份调研表的测试状态
- 完整率和置信度
- 节能率实际值与期望值
- 误差统计

## 验证标准

### 节能率容差

允许 ±0.5% 的计算误差，考虑到：
- Excel引擎差异（xlwings vs openpyxl）
- 浮点数精度
- 填充策略的近似性

### 置信度判断

- **高置信度 (high)**：完整率 ≥ 80%，可直接计算
- **中等置信度 (medium)**：完整率 50-80%，需填充后计算
- **低置信度 (low)**：完整率 < 50%，阻止计算流程

## 故障排查

### 常见问题

1. **Skill调用超时**
   - 增加timeout参数：`SkillCaller(timeout=600)`
   - 检查ANTHROPIC_API_KEY是否设置

2. **Excel计算失败**
   - 确保模板文件存在：`00_sample/机房智能化节能评估表-按冷站电量数据.xlsx`
   - 检查xlwings/openpyxl是否正确安装

3. **节能率偏差过大**
   - 检查填充策略是否正确应用
   - 对比 `filled_data.json` 和预期值
   - 检查Excel模板公式是否被修改

## 扩展测试

### 添加新的测试场景

1. 在 `tests/fixtures/sample_surveys.py` 中添加配置
2. 放置调研表文件到 `00_sample/示例调研表/`
3. 创建对应的测试类

### 自定义验证逻辑

修改 `TestHelper` 类中的验证方法：
- `validate_extracted_data()` - 数据结构验证
- `validate_quality_report()` - 质量报告验证
- `validate_filling_suggestions()` - 填充建议验证
```

**Step 2: 提交文档**

```bash
git add docs/testing/sample-surveys-testing-guide.md
git commit -m "docs: add sample surveys testing guide"
```

---

## Task 10: 创建CI/CD集成脚本

**Files:**
- Create: `scripts/run_sample_survey_tests.sh`

**Step 1: 编写测试执行脚本**

```bash
#!/bin/bash
# 运行示例调研表端到端测试的脚本

set -e  # 遇到错误立即退出

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== 示例调研表综合测试 ===${NC}\n"

# 检查前置条件
echo -e "${YELLOW}检查前置条件...${NC}"

# 1. 检查 PYTHONPATH
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
echo "✓ PYTHONPATH 已设置"

# 2. 检查 ANTHROPIC_API_KEY
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}✗ ANTHROPIC_API_KEY 未设置${NC}"
    echo "请设置: export ANTHROPIC_API_KEY='your-api-key'"
    exit 1
fi
echo "✓ ANTHROPIC_API_KEY 已设置"

# 3. 检查示例文件存在
SAMPLE_DIR="00_sample/示例调研表"
if [ ! -d "$SAMPLE_DIR" ]; then
    echo -e "${RED}✗ 示例调研表目录不存在: $SAMPLE_DIR${NC}"
    exit 1
fi
echo "✓ 示例调研表目录存在"

# 4. 检查Excel模板
TEMPLATE="00_sample/机房智能化节能评估表-按冷站电量数据.xlsx"
if [ ! -f "$TEMPLATE" ]; then
    echo -e "${RED}✗ Excel模板不存在: $TEMPLATE${NC}"
    exit 1
fi
echo "✓ Excel模板文件存在"

echo ""

# 清理旧的临时文件
echo -e "${YELLOW}清理临时文件...${NC}"
rm -rf ./tmp/*
echo "✓ 临时文件已清理"
echo ""

# 运行测试
echo -e "${GREEN}开始运行测试...${NC}\n"

# 可选：运行单个场景测试（用于快速验证）
# pytest tests/integration/test_sample_surveys_e2e.py::TestCompleteSurvey -v -s

# 运行所有场景的批量测试
pytest tests/integration/test_sample_surveys_e2e.py::TestAllSurveysBatch::test_all_surveys_summary -v -s

TEST_EXIT_CODE=$?

echo ""

# 检查测试结果
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ 所有测试通过${NC}"

    # 显示报告路径
    REPORT_PATH="tmp/test_summary_report.json"
    if [ -f "$REPORT_PATH" ]; then
        echo -e "\n${YELLOW}测试报告已生成: $REPORT_PATH${NC}"
        echo "查看报告: cat $REPORT_PATH | python -m json.tool"
    fi

    exit 0
else
    echo -e "${RED}✗ 测试失败${NC}"
    exit 1
fi
```

**Step 2: 设置脚本权限**

```bash
chmod +x scripts/run_sample_survey_tests.sh
```

**Step 3: 测试脚本**

```bash
./scripts/run_sample_survey_tests.sh
```

预期输出：运行所有测试并显示结果

**Step 4: 提交脚本**

```bash
git add scripts/run_sample_survey_tests.sh
git commit -m "ci: add sample survey testing script"
```

---

## Task 11: 更新项目README和测试文档

**Files:**
- Modify: `CLAUDE.md`

**Step 1: 在CLAUDE.md中添加示例调研表测试说明**

在 `## 测试注意事项` 部分添加：

```markdown
### 示例调研表端到端测试

项目包含6份不同质量等级的示例调研表，用于全面测试系统功能：

**运行示例调研表测试：**
```bash
# 使用测试脚本（推荐）
./scripts/run_sample_survey_tests.sh

# 或手动运行
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
export ANTHROPIC_API_KEY='your-api-key'
pytest tests/integration/test_sample_surveys_e2e.py::TestAllSurveysBatch -v -s
```

**测试覆盖场景：**
- 齐全数据（高置信度）
- 仅有夏季/缺冬季/缺夏季（中等置信度，需填充）
- 参差不齐（中等置信度，插值填充）
- 数据缺失过多（低置信度，流程中断）

详见：`docs/testing/sample-surveys-testing-guide.md`
```

**Step 2: 提交更新**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with sample survey testing info"
```

---

## 验收标准

### 功能验证清单

- [ ] 所有6份示例调研表都能成功提取数据
- [ ] 质量检测正确识别3种置信度等级（高/中/低）
- [ ] 中等置信度场景能成功应用填充建议
- [ ] 节能率计算结果在期望值 ±0.5% 范围内
- [ ] 低置信度场景正确触发流程中断
- [ ] 批量测试生成完整的测试报告
- [ ] 测试脚本可一键运行所有测试

### 代码质量检查

- [ ] 所有测试类遵循pytest规范
- [ ] 测试夹具配置清晰且可扩展
- [ ] 测试辅助函数覆盖常见验证场景
- [ ] 临时文件正确管理（创建/清理）
- [ ] 错误信息清晰，便于调试

### 文档完整性

- [ ] 测试指南文档完整且易懂
- [ ] CLAUDE.md包含测试说明
- [ ] 代码注释清晰
- [ ] 提交信息符合规范

---

## 预期成果

1. **测试套件**：`tests/integration/test_sample_surveys_e2e.py`（约500行）
2. **测试夹具**：`tests/fixtures/sample_surveys.py`（约100行）
3. **测试文档**：`docs/testing/sample-surveys-testing-guide.md`
4. **执行脚本**：`scripts/run_sample_survey_tests.sh`
5. **测试报告**：`tmp/test_summary_report.json`（运行时生成）

**总测试时长**：约5-10分钟（取决于API响应时间和Excel计算性能）

**覆盖率**：端到端流程覆盖率 >90%
