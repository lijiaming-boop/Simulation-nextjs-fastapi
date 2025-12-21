"""测试 Excel 计算引擎"""
import json
import pytest
from pathlib import Path
from core.excel_calculator import ExcelCalculator


@pytest.fixture
def template_path():
    """Excel 模板路径"""
    return "00_sample/机房智能化节能评估表-按冷站电量数据.xlsx"


@pytest.fixture
def filled_data_path():
    """填充后的测试数据"""
    return Path(__file__).parent.parent / "fixtures" / "filled_data.json"


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def test_calculator_initialization(template_path):
    """测试计算器初始化"""
    calc = ExcelCalculator(template_path)
    assert calc.template_path == template_path


@pytest.mark.skipif(
    not Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx").exists(),
    reason="Excel template not found"
)
def test_calculate_energy_saving(template_path, filled_data_path, tmp_dir):
    """测试节能率计算 (需要 Excel 模板和 xlwings 环境)"""
    calc = ExcelCalculator(template_path)

    result_path = tmp_dir / "result.json"

    # 执行计算
    output = calc.calculate(
        str(filled_data_path),
        str(result_path)
    )

    # 验证输出文件
    assert Path(output).exists()

    # 验证结果结构
    with open(output) as f:
        result = json.load(f)

    assert "energy_saving_rate" in result
    assert "energy_saving_rate_min" in result
    assert "energy_saving_rate_max" in result
    assert "chiller_saving" in result
    assert "total_saving" in result

    # 验证节能率在合理范围 (5%-35%)
    assert 0.05 <= result["energy_saving_rate"] <= 0.35
