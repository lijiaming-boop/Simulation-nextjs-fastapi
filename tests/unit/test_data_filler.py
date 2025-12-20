"""测试数据填充器"""
import json
import pytest
from pathlib import Path
from core.data_filler import DataFiller


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def test_fill_data_basic(fixtures_dir, tmp_dir):
    """测试基本数据填充功能"""
    filler = DataFiller()

    extracted_path = fixtures_dir / "extracted_data.json"
    suggestions_path = fixtures_dir / "filling_suggestions.json"
    output_path = tmp_dir / "filled_data.json"

    # 执行填充
    result_path = filler.fill_data(
        str(extracted_path),
        str(suggestions_path),
        str(output_path)
    )

    # 验证输出文件存在
    assert Path(result_path).exists()

    # 验证填充结果
    with open(result_path) as f:
        filled_data = json.load(f)

    # 检查2月数据已填充
    month_2 = filled_data["monthly_data"][1]
    assert month_2["chiller_supply_temp"] == 7.5
    assert month_2["cooling_tower_outlet_temp"] == 21
    assert "chiller_supply_temp" in month_2["_filled_fields"]
    assert "cooling_tower_outlet_temp" in month_2["_filled_fields"]

    # 检查元数据
    assert "_metadata" in filled_data
    assert filled_data["_metadata"]["fill_count"] == 2
    assert filled_data["_metadata"]["original_completeness"] < 1.0
    assert filled_data["_metadata"]["final_completeness"] == 1.0


def test_fill_does_not_overwrite_existing(fixtures_dir, tmp_dir):
    """测试填充不覆盖已有数据"""
    filler = DataFiller()

    extracted_path = fixtures_dir / "extracted_data.json"
    suggestions_path = fixtures_dir / "filling_suggestions.json"
    output_path = tmp_dir / "filled_data.json"

    result_path = filler.fill_data(
        str(extracted_path),
        str(suggestions_path),
        str(output_path)
    )

    with open(result_path) as f:
        filled_data = json.load(f)

    # 1月数据本来就完整,不应该被标记为填充
    month_1 = filled_data["monthly_data"][0]
    assert month_1["_filled_fields"] == []
    assert month_1["chiller_supply_temp"] == 7.0  # 保持原值
