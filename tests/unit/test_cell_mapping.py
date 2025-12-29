"""测试 Excel 单元格映射配置"""
import pytest
from config.cell_mapping import CellMapping


def test_get_monthly_data_cell():
    """测试获取月度数据单元格位置"""
    mapper = CellMapping()

    # 测试1月的冷站总能耗单元格
    cell = mapper.get_cell("monthly_data", 0, "total_energy")
    assert cell == "D27"

    # 测试12月的冷机供水温度单元格
    cell = mapper.get_cell("monthly_data", 11, "chiller_supply_temp")
    assert cell == "O9"


def test_get_result_cell():
    """测试获取结果提取单元格位置"""
    mapper = CellMapping()

    cell = mapper.get_result_cell("saving_rate")
    assert cell == "O30"  # 修正：实际位置是 O30 而非 P29

    cell = mapper.get_result_cell("total_saving")
    assert cell == "P28"


def test_get_all_monthly_fields():
    """测试获取所有月度数据字段"""
    mapper = CellMapping()
    fields = mapper.get_monthly_fields()

    assert "total_energy" in fields
    assert "chiller_supply_temp" in fields
    assert len(fields) == 7  # 7个月度数据字段
