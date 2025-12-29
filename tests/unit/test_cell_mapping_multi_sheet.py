"""测试 CellMapping 多sheet支持"""
import pytest
from config.cell_mapping import CellMapping


def test_get_sheet_name_upper():
    """测试获取上限sheet名称"""
    mapper = CellMapping()
    sheet_name = mapper.get_sheet_name("upper")
    assert sheet_name == "【1】按冷站电量数据-上限 "


def test_get_sheet_name_lower():
    """测试获取下限sheet名称"""
    mapper = CellMapping()
    sheet_name = mapper.get_sheet_name("lower")
    assert sheet_name == "【2】按冷站电量数据-下限"


def test_get_sheet_name_invalid():
    """测试无效sheet类型抛出异常"""
    mapper = CellMapping()
    with pytest.raises(ValueError, match="无效的sheet类型"):
        mapper.get_sheet_name("invalid")


def test_default_sheet_is_lower():
    """测试默认sheet是下限（向后兼容）"""
    mapper = CellMapping()
    assert mapper.SHEET_NAME == "【2】按冷站电量数据-下限"


def test_get_cell_works_for_both_sheets():
    """测试单元格映射对两个sheet都有效"""
    mapper = CellMapping()

    # 上限和下限使用相同的行列映射
    cell = mapper.get_cell("monthly_data", 0, "total_energy")
    assert cell == "D27"  # 1月总能耗位置
