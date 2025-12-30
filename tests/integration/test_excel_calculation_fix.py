"""端到端测试: 验证Excel计算修复后能正常工作"""
import pytest
import json
from pathlib import Path
from core.excel_calculator import ExcelCalculator
from core.data_filler import DataFiller


class TestExcelCalculationFix:
    """验证Excel计算bug修复后的端到端功能"""

    @pytest.fixture
    def test_filled_data(self, tmp_path):
        """创建测试用的填充数据"""
        filled_data = {
            "project_region": "华南",
            "station_type": "standard",
            "monthly_data": [
                {
                    "month": i + 1,
                    "total_energy": 100 + i * 20,
                    "chiller_supply_temp": 7.0,
                    "cooling_pump_freq": 40.0,
                    "cooling_water_temp_diff": 3.0,
                    "freezing_pump_freq": 40.0,
                    "freezing_water_temp_diff": 3.0,
                    "cooling_tower_outlet_temp": 25.0,
                    "_filled_fields": []
                }
                for i in range(12)
            ],
            "_metadata": {
                "fill_timestamp": "2025-12-29T00:00:00",
                "fill_count": 0,
                "original_completeness": 1.0,
                "final_completeness": 1.0
            }
        }

        filled_data_path = tmp_path / "filled_data.json"
        with open(filled_data_path, 'w', encoding='utf-8') as f:
            json.dump(filled_data, f, ensure_ascii=False, indent=2)

        return filled_data_path

    def test_calculation_succeeds_without_mock(self, test_filled_data, tmp_path):
        """测试计算成功且不使用mock结果"""
        # Given: Excel计算器
        calculator = ExcelCalculator()
        output_path = tmp_path / "result.json"

        # When: 执行计算
        result_path = calculator.calculate(
            str(test_filled_data),
            str(output_path)
        )

        # Then: 计算成功，结果文件存在
        assert Path(result_path).exists()

        with open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # Then: 结果不是mock（关键验证！）
        assert result.get("mock") is not True, (
            "计算结果使用了mock默认值，说明formulas计算失败！"
        )

    def test_dual_sheet_calculation_produces_range(self, test_filled_data, tmp_path):
        """测试双sheet计算产生节能率范围"""
        # Given: Excel计算器
        calculator = ExcelCalculator()
        output_path = tmp_path / "result.json"

        # When: 执行计算
        result_path = calculator.calculate(
            str(test_filled_data),
            str(output_path)
        )

        with open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # Then: 结果包含范围字段
        assert "energy_saving_rate_min" in result, "缺少节能率下限"
        assert "energy_saving_rate_max" in result, "缺少节能率上限"
        assert "energy_saving_rate_range" in result, "缺少节能率范围"

        # Then: 上限应该大于等于下限
        min_rate = result["energy_saving_rate_min"]
        max_rate = result["energy_saving_rate_max"]
        assert max_rate >= min_rate, (
            f"上限({max_rate})应该大于等于下限({min_rate})"
        )

        # Then: 范围格式正确
        range_str = result["energy_saving_rate_range"]
        assert "%" in range_str, "范围字符串应包含百分号"
        assert "-" in range_str, "范围字符串应包含连字符"

    def test_calculation_method_is_dual_sheet(self, test_filled_data, tmp_path):
        """测试计算方法标记为dual_sheet"""
        # Given: Excel计算器
        calculator = ExcelCalculator()
        output_path = tmp_path / "result.json"

        # When: 执行计算
        result_path = calculator.calculate(
            str(test_filled_data),
            str(output_path)
        )

        with open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # Then: 计算方法应标记为dual_sheet
        assert result.get("calculation_method") == "dual_sheet", (
            "应该使用双sheet计算方法"
        )
