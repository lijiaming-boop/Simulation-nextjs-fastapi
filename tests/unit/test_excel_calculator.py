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


def test_calculate_with_formulas_engine(template_path, filled_data_path, tmp_dir):
    """测试使用 formulas 库进行计算"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    calc = ExcelCalculator(template_path)

    # 读取填充数据
    with open(filled_data_path) as f:
        data = json.load(f)

    # 创建临时 Excel 文件
    temp_excel = tmp_dir / "test_calc.xlsx"
    import shutil
    shutil.copy(template_path, temp_excel)

    # 调用新的计算方法
    result = calc._calculate_with_formulas(data, temp_excel)

    # 验证结果结构
    assert "energy_saving_rate" in result
    assert "chiller_saving" in result
    assert "pump_saving" in result
    assert "tower_saving" in result
    assert "total_saving" in result
    assert "completeness" in result
    assert "filled_count" in result

    # 验证节能率在合理范围
    assert 0 <= result["energy_saving_rate"] <= 1.0

    # 打印结果用于调试
    print(f"\n计算结果: {result}")


@pytest.mark.skipif(
    not Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx").exists(),
    reason="Excel template not found"
)
def test_calculate_uses_formulas_engine(template_path, filled_data_path, tmp_dir):
    """测试 calculate 方法使用 formulas 引擎"""
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

    # 验证不是 mock 数据
    assert "mock" not in result or result["mock"] is False

    # 验证节能率在合理范围 (5%-35%)
    assert 0.05 <= result["energy_saving_rate"] <= 0.35

    print(f"\n使用 formulas 引擎的计算结果: {result}")


def test_end_to_end_calculation(template_path, tmp_dir):
    """端到端测试：完整计算流程"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    # 准备测试数据
    test_data = {
        "project_region": "华南",
        "monthly_data": [
            {
                "month": i + 1,
                "total_energy": 80 + i * 5,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": 45,
                "cooling_water_temp_diff": 4.5,
                "freezing_pump_freq": 50,
                "freezing_water_temp_diff": 4.5,
                "cooling_tower_outlet_temp": 20 + i,
                "_filled_fields": []
            }
            for i in range(12)
        ],
        "_metadata": {
            "fill_timestamp": "2025-12-26T10:00:00",
            "fill_count": 0,
            "original_completeness": 1.0,
            "final_completeness": 1.0
        }
    }

    # 保存测试数据
    filled_data_path = tmp_dir / "filled_data.json"
    with open(filled_data_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)

    # 执行计算
    calc = ExcelCalculator(template_path)
    result_path = tmp_dir / "result.json"

    output = calc.calculate(str(filled_data_path), str(result_path))

    # 验证结果
    assert Path(output).exists()

    with open(output) as f:
        result = json.load(f)

    # 验证所有必需字段
    required_fields = [
        "energy_saving_rate",
        "energy_saving_rate_min",
        "energy_saving_rate_max",
        "chiller_saving",
        "pump_saving",
        "tower_saving",
        "total_saving",
        "completeness",
        "filled_count",
        "calculation_timestamp"
    ]

    for field in required_fields:
        assert field in result, f"Missing field: {field}"

    # 验证计算逻辑
    assert result["completeness"] == 1.0
    assert result["filled_count"] == 0
    assert 0 <= result["energy_saving_rate"] <= 1.0

    print(f"\n端到端计算结果: {result}")
