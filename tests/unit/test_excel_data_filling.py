"""测试 Excel 数据回填的准确性"""
import json
import pytest
import openpyxl
from pathlib import Path
from core.excel_calculator import ExcelCalculator
from config.cell_mapping import CellMapping


@pytest.fixture
def template_path():
    """Excel 模板路径"""
    return "00_sample/机房智能化节能评估表-按冷站电量数据.xlsx"


@pytest.fixture
def test_data():
    """测试数据"""
    return {
        "project_region": "华南",
        "monthly_data": [
            {
                "month": 1,
                "total_energy": 186.21,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": 37.5,
                "cooling_water_temp_diff": 3.5,
                "freezing_pump_freq": 37.5,
                "freezing_water_temp_diff": 3.0,
                "cooling_tower_outlet_temp": 20.5,
                "_filled_fields": []
            },
            {
                "month": 6,
                "total_energy": 287.10,
                "chiller_supply_temp": 6.5,
                "cooling_pump_freq": 45,
                "cooling_water_temp_diff": 3.5,
                "freezing_pump_freq": 45,
                "freezing_water_temp_diff": 4.0,
                "cooling_tower_outlet_temp": 29.0,
                "_filled_fields": []
            },
            {
                "month": 12,
                "total_energy": 0.40,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": 37.5,
                "cooling_water_temp_diff": 3.5,
                "freezing_pump_freq": 37.5,
                "freezing_water_temp_diff": 3.0,
                "cooling_tower_outlet_temp": 23.5,
                "_filled_fields": []
            }
        ],
        "_metadata": {
            "fill_timestamp": "2025-12-27T08:45:40",
            "fill_count": 0,
            "original_completeness": 1.0,
            "final_completeness": 1.0
        }
    }


@pytest.mark.skipif(
    not Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx").exists(),
    reason="Excel template not found"
)
def test_data_filling_accuracy(template_path, test_data, tmp_path):
    """测试数据回填到 Excel 的准确性"""
    # 保存测试数据
    filled_data_path = tmp_path / "test_filled_data.json"
    with open(filled_data_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)

    # 执行计算
    calc = ExcelCalculator(template_path)
    result_path = tmp_path / "result.json"
    calc.calculate(str(filled_data_path), str(result_path))

    # 验证数据回填准确性
    temp_excel = tmp_path / "calculation_result.xlsx"
    assert temp_excel.exists(), "临时 Excel 文件不存在"

    # 使用 openpyxl 读取 Excel 验证
    wb = openpyxl.load_workbook(temp_excel, data_only=False)
    sheet = wb["【2】按冷站电量数据 "]
    mapper = CellMapping()

    # 验证项目地区
    region_cell = mapper.get_basic_info_cell("project_region")
    excel_region = sheet[region_cell].value
    assert excel_region == "华南", f"项目地区回填错误: 期望'华南', 实际'{excel_region}'"

    # 验证 1 月能耗
    cell_1m = mapper.get_cell("monthly_data", 0, "total_energy")
    excel_energy_1m = sheet[cell_1m].value
    assert abs(float(excel_energy_1m) - 186.21) < 0.01, \
        f"1月能耗回填错误: 期望 186.21, 实际 {excel_energy_1m}"

    # 验证 6 月能耗
    cell_6m = mapper.get_cell("monthly_data", 5, "total_energy")
    excel_energy_6m = sheet[cell_6m].value
    assert abs(float(excel_energy_6m) - 287.10) < 0.01, \
        f"6月能耗回填错误: 期望 287.10, 实际 {excel_energy_6m}"

    # 验证 12 月能耗
    cell_12m = mapper.get_cell("monthly_data", 11, "total_energy")
    excel_energy_12m = sheet[cell_12m].value
    assert abs(float(excel_energy_12m) - 0.40) < 0.01, \
        f"12月能耗回填错误: 期望 0.40, 实际 {excel_energy_12m}"

    # 验证其他月度字段（1月样本）
    month_fields_1m = {
        "chiller_supply_temp": 7.0,
        "cooling_pump_freq": 37.5,
        "cooling_water_temp_diff": 3.5,
        "freezing_pump_freq": 37.5,
        "freezing_water_temp_diff": 3.0,
        "cooling_tower_outlet_temp": 20.5,
    }

    for field, expected_value in month_fields_1m.items():
        cell = mapper.get_cell("monthly_data", 0, field)
        excel_value = sheet[cell].value
        assert abs(float(excel_value) - expected_value) < 0.01, \
            f"1月 {field} 回填错误: 期望 {expected_value}, 实际 {excel_value}"

    wb.close()
    print("\n✅ 数据回填准确性验证通过")


@pytest.mark.skipif(
    not Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx").exists(),
    reason="Excel template not found"
)
def test_calculation_uses_filled_data(template_path, test_data, tmp_path):
    """测试计算结果使用的是回填数据而非模板默认值"""
    # 保存测试数据
    filled_data_path = tmp_path / "test_filled_data.json"
    with open(filled_data_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)

    # 执行计算
    calc = ExcelCalculator(template_path)
    result_path = tmp_path / "result.json"
    calc.calculate(str(filled_data_path), str(result_path))

    # 读取计算结果
    with open(result_path, 'r', encoding='utf-8') as f:
        result = json.load(f)

    # 验证节能率在合理范围
    assert "energy_saving_rate" in result
    assert 0.05 <= result["energy_saving_rate"] <= 0.35, \
        f"节能率超出合理范围: {result['energy_saving_rate']}"

    # 验证不是 mock 数据
    assert "mock" not in result, "计算使用了 mock 数据"

    print(f"\n✅ 计算结果验证通过，节能率: {result['energy_saving_rate']:.2%}")
