"""测试多模板计算功能"""
import json
import pytest
from pathlib import Path
from core.excel_calculator import ExcelCalculator


@pytest.fixture
def sample_filled_data_standard(tmp_path):
    """标准版样例填充数据"""
    # 注意：填写全部 7 个月度字段（与真实管线一致）——只填能耗会令模板
    # 公式除零产生 #DIV/0!，计算引擎将显式报错而非返回无效数值
    data = {
        "station_type": "standard",
        "project_region": "华南",
        "monthly_data": [
            {"month": i, "total_energy": 100 + i * 10,
             "chiller_supply_temp": 7.0, "cooling_pump_freq": 45.0,
             "cooling_water_temp_diff": 4.5, "freezing_pump_freq": 48.0,
             "freezing_water_temp_diff": 4.0, "cooling_tower_outlet_temp": 32.0}
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    data_path = tmp_path / "filled_standard.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    return str(data_path)


@pytest.fixture
def sample_filled_data_secondary(tmp_path):
    """二次泵版样例填充数据"""
    data = {
        "station_type": "secondary_pump",
        "project_region": "华北",
        "monthly_data": [
            {"month": i, "total_energy": 120 + i * 15,
             "chiller_supply_temp": 7.5, "cooling_pump_freq": 44.0,
             "cooling_water_temp_diff": 4.5, "freezing_pump_freq": 47.0,
             "freezing_water_temp_diff": 4.2, "cooling_tower_outlet_temp": 31.0}
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    data_path = tmp_path / "filled_secondary.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    return str(data_path)


def test_calculate_standard_template(sample_filled_data_standard, tmp_path):
    """测试使用标准版模板计算"""
    calculator = ExcelCalculator()  # 不指定模板，自动选择

    output_path = tmp_path / "result_standard.json"
    result_path = calculator.calculate(
        sample_filled_data_standard,
        str(output_path)
    )

    assert Path(result_path).exists()

    with open(result_path) as f:
        result = json.load(f)

    assert "energy_saving_rate" in result
    assert result["completeness"] == 1.0


def test_calculate_secondary_pump_template(sample_filled_data_secondary, tmp_path):
    """测试使用二次泵版模板计算"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result_secondary.json"
    result_path = calculator.calculate(
        sample_filled_data_secondary,
        str(output_path)
    )

    assert Path(result_path).exists()

    with open(result_path) as f:
        result = json.load(f)

    assert "energy_saving_rate" in result
    assert result["completeness"] == 1.0


def test_unsupported_type_raises_error(tmp_path):
    """测试不支持类型抛出异常"""
    data = {
        "station_type": "unsupported",
        "project_region": "华南",
        "monthly_data": [],
        "_metadata": {"final_completeness": 0.5, "fill_count": 0}
    }

    data_path = tmp_path / "filled_unsupported.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    calculator = ExcelCalculator()
    output_path = tmp_path / "result.json"

    with pytest.raises(ValueError, match="不支持的站房类型"):
        calculator.calculate(str(data_path), str(output_path))
