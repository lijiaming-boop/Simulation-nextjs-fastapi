"""测试站房类型识别功能"""
import pytest
import openpyxl
from openpyxl import Workbook
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加 scripts 目录到路径
scripts_path = project_root / ".claude/skills/extract-and-check-data/scripts"
sys.path.insert(0, str(scripts_path))

# 导入待测试函数
from extract_and_check_data import detect_station_type


def create_mock_workbook(cell_values: list) -> Workbook:
    """创建包含指定文本的模拟工作簿

    cell_values 支持两种格式：
    - 字符串列表：每个字符串放 A 列的一行（简单场景）
    - 嵌套列表：每个子列表是一行的多列数据（模拟真实调研表）
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "冷站"

    for i, value in enumerate(cell_values, start=1):
        if isinstance(value, list):
            for j, cell_val in enumerate(value, start=1):
                ws.cell(row=i, column=j, value=cell_val)
        else:
            ws.cell(row=i, column=1, value=value)

    return wb


def test_detect_standard_station():
    """测试识别标准站房（无特殊关键词）"""
    wb = create_mock_workbook([
        "站房名称", "深圳工业园区F栋",
        "冷冻泵", "运行频率", "45Hz"
    ])

    result = detect_station_type(wb)
    wb.close()

    assert result["station_type"] == "standard"
    assert result["confidence"] in ["medium", "low"]
    assert "标准" in result["reason"]


def test_detect_secondary_pump_station():
    """测试识别二次泵站房"""
    wb = create_mock_workbook([
        ["站房名称", "北京总部", ""],
        ["一次泵", "45Hz", "30kW"],
        ["二次泵", "40Hz", "22kW"]
    ])

    result = detect_station_type(wb)
    wb.close()

    assert result["station_type"] == "secondary_pump"
    assert result["confidence"] == "high"
    assert "一次泵" in result["reason"] or "二次泵" in result["reason"]


def test_detect_unsupported_hot_water():
    """测试识别不支持类型 - 热水泵"""
    wb = create_mock_workbook([
        "站房名称", "上海办公楼",
        "热水泵", "运行频率", "50Hz"
    ])

    result = detect_station_type(wb)
    wb.close()

    assert result["station_type"] == "unsupported"
    assert result["confidence"] == "high"
    assert "热水泵" in result["reason"]


def test_detect_unsupported_ice_storage():
    """测试识别不支持类型 - 水蓄冷"""
    wb = create_mock_workbook([
        "站房名称", "广州购物中心",
        "冰蓄冷系统", "容量", "1000吨"
    ])

    result = detect_station_type(wb)
    wb.close()

    assert result["station_type"] == "unsupported"
    assert result["confidence"] == "high"
    assert "蓄冷" in result["reason"] or "蓄冰" in result["reason"]


def test_detect_unsupported_mid_low_temp():
    """测试识别不支持类型 - 中低温机组"""
    wb = create_mock_workbook([
        "站房名称", "深圳工业园",
        "中温机组", "额定功率", "500kW"
    ])

    result = detect_station_type(wb)
    wb.close()

    assert result["station_type"] == "unsupported"
    assert result["confidence"] == "high"
    assert "中温" in result["reason"] or "低温" in result["reason"]


def test_empty_workbook():
    """测试空工作簿的处理"""
    wb = Workbook()

    result = detect_station_type(wb)
    wb.close()

    # 空工作簿没有任何特征，返回 standard + medium confidence
    assert result["station_type"] == "standard"
    assert result["confidence"] in ["medium", "low"]


def test_detect_secondary_pump_variant_keywords():
    """测试识别二次泵的多种关键词变体"""
    # 测试 "一次泵" 和 "二次泵"
    wb1 = create_mock_workbook([
        ["一次泵", "45Hz", "30kW"],
        ["二次泵", "40Hz", "22kW"]
    ])
    result1 = detect_station_type(wb1)
    wb1.close()
    assert result1["station_type"] == "secondary_pump"

    # 测试 "冷冻一次泵" 和 "冷冻二次泵"
    wb2 = create_mock_workbook([
        ["冷冻一次泵", "45Hz", "30kW"],
        ["冷冻二次泵", "40Hz", "22kW"]
    ])
    result2 = detect_station_type(wb2)
    wb2.close()
    assert result2["station_type"] == "secondary_pump"


def test_detect_unsupported_water_storage_variant():
    """测试识别水蓄冷的多种关键词变体"""
    # 测试 "蓄冷"
    wb1 = create_mock_workbook(["蓄冷系统"])
    result1 = detect_station_type(wb1)
    wb1.close()
    assert result1["station_type"] == "unsupported"

    # 测试 "水蓄冷"
    wb2 = create_mock_workbook(["水蓄冷技术"])
    result2 = detect_station_type(wb2)
    wb2.close()
    assert result2["station_type"] == "unsupported"

    # 测试 "蓄冰"
    wb3 = create_mock_workbook(["蓄冰空调"])
    result3 = detect_station_type(wb3)
    wb3.close()
    assert result3["station_type"] == "unsupported"


def test_case_insensitive_matching():
    """测试关键词匹配不区分大小写"""
    wb = create_mock_workbook([
        ["站房名称", "TEST", ""],
        ["一次泵", "PUMP", "45HZ"],
        ["二次泵", "PUMP", "40HZ"]
    ])

    result = detect_station_type(wb)
    wb.close()

    # 应该能识别出二次泵（即使有大写字母）
    assert result["station_type"] == "secondary_pump"


def test_priority_unsupported_over_secondary():
    """测试不支持类型优先级高于二次泵"""
    # 同时包含二次泵和热水泵关键词，应识别为不支持
    wb = create_mock_workbook([
        "一次冷冻泵", "二次冷冻泵",
        "热水泵", "运行中"
    ])

    result = detect_station_type(wb)
    wb.close()

    assert result["station_type"] == "unsupported"
    assert "热水泵" in result["reason"]
