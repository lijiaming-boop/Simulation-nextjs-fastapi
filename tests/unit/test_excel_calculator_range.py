"""测试 ExcelCalculator 双sheet范围计算"""
import json
import pytest
from pathlib import Path
from core.excel_calculator import ExcelCalculator


@pytest.fixture
def sample_filled_data(tmp_path):
    """样例填充数据"""
    data = {
        "station_type": "standard",
        "project_region": "华南",
        "monthly_data": [
            {
                "month": i,
                "total_energy": 100 + i * 10,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": 45.0,
                "cooling_water_temp_diff": 5.0,
                "freezing_pump_freq": 45.0,
                "freezing_water_temp_diff": 5.0,
                "cooling_tower_outlet_temp": 30.0,
            }
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    data_path = tmp_path / "filled.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    return str(data_path)


def test_calculate_with_range(sample_filled_data, tmp_path):
    """测试计算节能率范围（上限+下限）"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result.json"
    result_path = calculator.calculate(
        sample_filled_data,
        str(output_path)
    )

    assert Path(result_path).exists()

    with open(result_path) as f:
        result = json.load(f)

    # 验证包含范围字段
    assert "energy_saving_rate_min" in result
    assert "energy_saving_rate_max" in result
    assert "energy_saving_rate_range" in result

    # 验证范围合理性
    min_rate = result["energy_saving_rate_min"]
    max_rate = result["energy_saving_rate_max"]

    assert 0 < min_rate < max_rate < 1.0
    assert result["energy_saving_rate_range"] == f"{min_rate*100:.1f}% - {max_rate*100:.1f}%"


def test_calculate_preserves_original_fields(sample_filled_data, tmp_path):
    """测试计算保留原有字段（向后兼容）"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result.json"
    result_path = calculator.calculate(
        sample_filled_data,
        str(output_path)
    )

    with open(result_path) as f:
        result = json.load(f)

    # 验证原有字段仍存在
    assert "energy_saving_rate" in result  # 原字段（下限值）
    assert "chiller_saving" in result
    assert "pump_saving" in result
    assert "tower_saving" in result
    assert "total_saving" in result


def test_backward_compatibility_single_value(sample_filled_data, tmp_path):
    """测试向后兼容 - energy_saving_rate 应等于下限值"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result.json"
    result_path = calculator.calculate(
        sample_filled_data,
        str(output_path)
    )

    with open(result_path) as f:
        result = json.load(f)

    # energy_saving_rate（旧字段）应该等于 energy_saving_rate_min（下限）
    assert result["energy_saving_rate"] == result["energy_saving_rate_min"]
