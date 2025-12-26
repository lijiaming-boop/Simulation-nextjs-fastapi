"""测试 formulas 库基础功能"""
import pytest
from pathlib import Path
import formulas


@pytest.fixture
def template_path():
    """Excel 模板路径"""
    return "00_sample/机房智能化节能评估表-按冷站电量数据.xlsx"


def test_formulas_load_excel(template_path):
    """测试 formulas 能否加载 Excel 文件"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    # 加载 Excel 文件
    xl_model = formulas.ExcelModel().loads(template_path).finish()

    # 验证模型加载成功
    assert xl_model is not None
    assert len(xl_model.books) > 0


def test_formulas_read_cell(template_path):
    """测试读取单元格值"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    xl_model = formulas.ExcelModel().loads(template_path).finish()

    # 获取工作簿名称
    book_name = list(xl_model.books.keys())[0]

    # 实际的 sheet 名称是 "【2】按冷站电量数据 "
    # formulas 库使用格式: '[workbook]sheet'!cell (注意小写)
    cell_id = f"'[{book_name.lower()}]【2】按冷站电量数据 '!H4"

    # 使用 calculate() 初始化，然后从结果中读取
    result = xl_model.calculate()

    # 验证能读取到值
    assert cell_id in result


def test_formulas_write_and_calculate(template_path):
    """测试写入单元格并触发计算"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    xl_model = formulas.ExcelModel().loads(template_path).finish()
    book_name = list(xl_model.books.keys())[0]

    # 使用 inputs 参数写入数据
    cell_id = f"'[{book_name}]【2】按冷站电量数据 '!D27"

    # 触发计算并传入输入值
    result = xl_model.calculate(inputs={cell_id: 100.5})

    # 验证值已更新（结果中应该包含这个cell）
    assert cell_id in result
    # 结果可能是 Ranges 对象或直接是值
    value = result[cell_id]
    if hasattr(value, 'value'):
        # Ranges 对象
        assert value.value[0][0] == 100.5
    else:
        # 直接的值
        assert value == 100.5


def test_formulas_extract_results(template_path):
    """测试提取计算结果"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    xl_model = formulas.ExcelModel().loads(template_path).finish()
    book_name = list(xl_model.books.keys())[0]

    # 准备输入数据字典
    inputs = {}

    # 项目地区
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!H4"] = "华北"

    # 1月数据
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!D27"] = 100  # 总能耗
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!D9"] = 7     # 冷机供水温度
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!D13"] = 45   # 冷却泵频率
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!D14"] = 4.5  # 冷却水温差
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!D18"] = 50   # 冷冻泵频率
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!D19"] = 4.5  # 冷冻水温差
    inputs[f"'[{book_name}]【2】按冷站电量数据 '!D23"] = 22   # 冷却塔温度

    # 触发计算
    result = xl_model.calculate(inputs=inputs)

    # 提取结果 (注意工作簿名称要用小写)
    result_cells = {
        "chiller_saving_total": f"'[{book_name.lower()}]【2】按冷站电量数据 '!P11",
        "cooling_pump_saving_total": f"'[{book_name.lower()}]【2】按冷站电量数据 '!P16",
        "freezing_pump_saving_total": f"'[{book_name.lower()}]【2】按冷站电量数据 '!P21",
        "tower_saving_total": f"'[{book_name.lower()}]【2】按冷站电量数据 '!P25",
        "total_saving": f"'[{book_name.lower()}]【2】按冷站电量数据 '!P28",
        "saving_rate": f"'[{book_name.lower()}]【2】按冷站电量数据 '!O30",  # 实际在O30
    }

    results = {}
    for key, cell_id in result_cells.items():
        if cell_id in result:
            # Ranges对象的值存储在.value属性的嵌套列表中
            value = result[cell_id].value[0][0]
            results[key] = float(value) if value is not None else 0.0
        else:
            results[key] = 0.0

    # 验证结果结构
    assert "chiller_saving_total" in results
    assert "saving_rate" in results

    # 打印结果用于调试
    print(f"\n计算结果: {results}")
