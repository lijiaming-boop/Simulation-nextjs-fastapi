"""端到端测试：多模板工作流"""
import json
import pytest
from pathlib import Path
from core.skill_caller import SkillCaller
from core.data_filler import DataFiller
from core.excel_calculator import ExcelCalculator


@pytest.mark.skipif(
    not Path("00_sample/02-中央空调节能调研表.xlsx").exists(),
    reason="需要样例调研表文件"
)
def test_standard_station_full_workflow(tmp_path):
    """测试标准站房完整工作流"""

    # 阶段1: 提取和质量检查
    caller = SkillCaller(timeout=300)
    survey_path = "00_sample/02-中央空调节能调研表.xlsx"
    extract_output = tmp_path / "extracted.json"

    result = caller.call_skill(
        "extract-and-check-data",
        survey_path,
        str(extract_output),
        "测试调研表.xlsx"
    )

    assert result["success"]
    assert extract_output.exists()

    with open(extract_output) as f:
        extracted = json.load(f)

    # 验证站房类型
    assert "station_type" in extracted["extracted_data"]
    station_type = extracted["extracted_data"]["station_type"]
    assert station_type in ["standard", "secondary_pump"]  # 不应是 unsupported

    # 阶段2: 填充建议
    quality_path = tmp_path / "quality.json"
    with open(quality_path, 'w', encoding='utf-8') as f:
        json.dump(extracted["quality_report"], f)

    data_path = tmp_path / "data.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(extracted["extracted_data"], f)

    filling_output = tmp_path / "filling.json"
    caller.call_skill(
        "suggest-data-filling",
        str(quality_path),
        str(data_path),
        str(filling_output)
    )

    # 阶段3: 数据填充
    filler = DataFiller()
    filled_output = tmp_path / "filled.json"
    filler.fill(
        str(data_path),
        str(filling_output),
        str(filled_output)
    )

    # 验证 filled_data 包含 station_type
    with open(filled_output) as f:
        filled = json.load(f)
    assert "station_type" in filled
    assert filled["station_type"] == station_type

    # 阶段4: 计算节能率（自动选择模板）
    calculator = ExcelCalculator()  # 不指定模板
    result_output = tmp_path / "result.json"

    calculator.calculate(
        str(filled_output),
        str(result_output)
    )

    # 验证结果
    with open(result_output) as f:
        result = json.load(f)

    assert "energy_saving_rate" in result
    assert result["energy_saving_rate"] > 0


def test_unsupported_station_blocked(tmp_path):
    """测试不支持类型被正确拦截"""

    # 创建包含 "热水泵" 的模拟数据
    unsupported_data = {
        "station_type": "unsupported",
        "station_type_reason": "检测到热水泵特征",
        "project_region": "华南",
        "monthly_data": [],
        "_metadata": {"final_completeness": 0.5, "fill_count": 0}
    }

    data_path = tmp_path / "unsupported.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(unsupported_data, f)

    # 尝试计算应抛出异常
    calculator = ExcelCalculator()
    result_path = tmp_path / "result.json"

    with pytest.raises(ValueError, match="不支持的站房类型"):
        calculator.calculate(str(data_path), str(result_path))
