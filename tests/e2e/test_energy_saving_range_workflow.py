"""端到端测试：节能率范围计算工作流"""
import json
import pytest
from pathlib import Path
from core.excel_calculator import ExcelCalculator
from core.data_filler import DataFiller


def test_full_range_calculation_workflow(tmp_path):
    """测试完整的范围计算工作流"""

    # 准备测试数据 - 使用较高的泵频率以产生节能潜力
    filled_data = {
        "station_type": "standard",
        "project_region": "华南",
        "monthly_data": [
            {
                "month": i,
                "total_energy": 100 + i * 10,
                "chiller_supply_temp": 7.0 + i * 0.1,
                "cooling_pump_freq": 65.0,  # 使用较高频率
                "cooling_water_temp_diff": 5.0,
                "freezing_pump_freq": 65.0,  # 使用较高频率
                "freezing_water_temp_diff": 5.0,
                "cooling_tower_outlet_temp": 30.0 - i * 0.5,
            }
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 3}
    }

    filled_path = tmp_path / "filled_data.json"
    with open(filled_path, 'w', encoding='utf-8') as f:
        json.dump(filled_data, f)

    # 执行计算
    calculator = ExcelCalculator()
    result_path = tmp_path / "result.json"

    calculator.calculate(str(filled_path), str(result_path))

    # 验证结果
    with open(result_path) as f:
        result = json.load(f)

    # 1. 验证范围字段存在
    assert "energy_saving_rate_min" in result
    assert "energy_saving_rate_max" in result
    assert "energy_saving_rate_range" in result

    # 2. 验证范围合理性
    min_rate = result["energy_saving_rate_min"]
    max_rate = result["energy_saving_rate_max"]

    assert 0 < min_rate < max_rate < 1.0, "节能率范围应在0-100%之间且min<max"

    # 3. 验证范围字符串格式
    expected_range = f"{min_rate*100:.1f}% - {max_rate*100:.1f}%"
    assert result["energy_saving_rate_range"] == expected_range

    # 4. 验证分项节能量范围
    assert result["chiller_saving_min"] < result["chiller_saving_max"]
    assert result["pump_saving_min"] < result["pump_saving_max"]
    assert result["tower_saving_min"] < result["tower_saving_max"]
    assert result["total_saving_min"] < result["total_saving_max"]

    # 5. 验证向后兼容字段
    assert result["energy_saving_rate"] == min_rate  # 旧字段=下限
    assert result["chiller_saving"] == result["chiller_saving_min"]

    # 6. 验证元数据
    assert result["calculation_method"] == "dual_sheet"
    assert result["completeness"] == 1.0


def test_range_with_secondary_pump_template(tmp_path):
    """测试二次泵模板的范围计算"""

    filled_data = {
        "station_type": "secondary_pump",
        "project_region": "华北",
        "monthly_data": [
            {
                "month": i,
                "total_energy": 120 + i * 15,
                "chiller_supply_temp": 7.5,
                "cooling_pump_freq": 65.0,  # 使用较高频率
                "cooling_water_temp_diff": 5.0,
                "freezing_pump_freq": 65.0,  # 使用较高频率
                "freezing_water_temp_diff": 5.0,
                "cooling_tower_outlet_temp": 28.0,
            }
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    filled_path = tmp_path / "filled_secondary.json"
    with open(filled_path, 'w', encoding='utf-8') as f:
        json.dump(filled_data, f)

    calculator = ExcelCalculator()
    result_path = tmp_path / "result_secondary.json"

    calculator.calculate(str(filled_path), str(result_path))

    with open(result_path) as f:
        result = json.load(f)

    # 验证二次泵版同样支持范围计算
    assert "energy_saving_rate_range" in result
    assert result["calculation_method"] == "dual_sheet"
