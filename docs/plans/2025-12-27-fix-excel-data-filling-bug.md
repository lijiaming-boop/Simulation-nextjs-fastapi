# Excel 数据回填 Bug 修复实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 ExcelCalculator 数据回填失败的严重 bug，确保 filled_data.json 的数据正确写入 Excel 并用于节能率计算

**Architecture:**
当前实现使用 `xl_model.calculate(inputs={...})`，但 formulas 库忽略 inputs 参数，导致计算使用模板默认值而非用户数据。修复方案采用两阶段方法：(1) 使用 openpyxl 将数据写入 Excel 文件 (2) 使用 formulas 库加载已写入数据的文件并计算。

**Tech Stack:**
- openpyxl: Excel 文件读写
- formulas: Excel 公式计算引擎
- pytest: 单元测试和集成测试

**Bug 严重性:** 🔴 高危 - 当前所有计算结果基于错误数据

**参考文档:** `tmp/test_report.md`

---

## Task 1: 创建数据回填准确性验证测试

**目的:** TDD - 先写失败测试，验证数据确实被正确回填到 Excel

**Files:**
- Create: `tests/unit/test_excel_data_filling.py`

**Step 1: 编写数据回填验证测试**

```python
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
```

**Step 2: 运行测试验证当前实现失败**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/unit/test_excel_data_filling.py::test_data_filling_accuracy -v
```

**预期结果:** FAIL - "项目地区回填错误: 期望'华南', 实际'华北'"

**Step 3: 提交测试文件**

```bash
git add tests/unit/test_excel_data_filling.py
git commit -m "test: add failing test for Excel data filling accuracy

验证数据回填到 Excel 的准确性，当前实现会失败因为 formulas
库的 calculate(inputs={}) 不生效。

Related: tmp/test_report.md"
```

---

## Task 2: 修复 ExcelCalculator._calculate_with_formulas() 方法

**目的:** 使用 openpyxl 先写入数据，再用 formulas 计算

**Files:**
- Modify: `core/excel_calculator.py:64-149`

**Step 1: 重写 _calculate_with_formulas 方法**

在 `core/excel_calculator.py` 中，替换 `_calculate_with_formulas` 方法：

```python
def _calculate_with_formulas(
    self,
    data: Dict[str, Any],
    excel_path: Path
) -> Dict[str, Any]:
    """使用 formulas 库执行计算

    Args:
        data: 填充后的数据字典
        excel_path: Excel 文件路径

    Returns:
        计算结果字典
    """
    try:
        import formulas
        import openpyxl
    except ImportError as e:
        raise RuntimeError(f"Required library not installed: {e}")

    # 阶段1: 使用 openpyxl 将数据写入 Excel 文件
    wb = openpyxl.load_workbook(excel_path)
    sheet = wb[self.mapper.SHEET_NAME]

    # 1. 回填项目地区到 Sheet2
    region_cell = self.mapper.get_basic_info_cell("project_region")
    sheet[region_cell] = data["project_region"]

    # 2. 回填月度数据到 Sheet1
    for month_data in data["monthly_data"]:
        month_idx = month_data["month"] - 1  # 转换为 0-based 索引

        for field in self.mapper.get_monthly_fields():
            value = month_data.get(field)
            if value is not None:
                cell = self.mapper.get_cell("monthly_data", month_idx, field)
                sheet[cell] = value

    # 3. 保存写入的数据
    wb.save(excel_path)
    wb.close()

    # 阶段2: 使用 formulas 库加载并计算
    xl_model = formulas.ExcelModel().loads(str(excel_path)).finish()

    # 获取工作簿名称（用于结果提取）
    book_name = list(xl_model.books.keys())[0]

    # 触发计算（不需要传入 inputs，数据已在文件中）
    result_data = xl_model.calculate()

    # 阶段3: 提取计算结果
    def get_result_value(result_field: str) -> float:
        """提取结果单元格的值"""
        cell = self.mapper.get_result_cell(result_field)
        # 读取结果时使用小写工作簿名称
        cell_id = f"'[{book_name.lower()}]{self.mapper.SHEET_NAME}'!{cell}"

        if cell_id in result_data:
            value = result_data[cell_id]
            # Ranges 对象的值存储在 .value 属性的嵌套列表中
            if hasattr(value, 'value'):
                value = value.value[0][0]
            return float(value) if value is not None else 0.0
        else:
            return 0.0

    result = {
        "chiller_saving": get_result_value("chiller_saving_total"),
        "pump_saving": (
            get_result_value("cooling_pump_saving_total") +
            get_result_value("freezing_pump_saving_total")
        ),
        "tower_saving": get_result_value("tower_saving_total"),
        "total_saving": get_result_value("total_saving"),
        "energy_saving_rate": get_result_value("saving_rate"),
    }

    # 计算节能率范围 (±20%)
    rate = result["energy_saving_rate"]
    result["energy_saving_rate_min"] = rate * 0.8
    result["energy_saving_rate_max"] = rate * 1.2

    # 添加元数据
    result["completeness"] = data["_metadata"]["final_completeness"]
    result["filled_count"] = data["_metadata"]["fill_count"]
    result["calculation_timestamp"] = datetime.now().isoformat()

    return result
```

**Step 2: 更新导入语句**

确保文件顶部已导入 openpyxl（如果未导入）：

在 `core/excel_calculator.py` 的导入部分，确认包含：

```python
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from config.cell_mapping import CellMapping
# openpyxl 在 _calculate_with_formulas 中按需导入
```

**Step 3: 运行数据回填准确性测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/unit/test_excel_data_filling.py::test_data_filling_accuracy -v -s
```

**预期结果:** PASS - 数据正确回填到 Excel

**Step 4: 运行计算结果验证测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/unit/test_excel_data_filling.py::test_calculation_uses_filled_data -v -s
```

**预期结果:** PASS - 计算使用正确数据

**Step 5: 提交修复**

```bash
git add core/excel_calculator.py
git commit -m "fix: correct Excel data filling in _calculate_with_formulas

修复严重 bug：使用 openpyxl 先写入数据到 Excel，再用 formulas
计算。之前的 calculate(inputs={}) 方法不生效，导致计算使用
模板默认值而非用户数据。

修复方法：
1. 使用 openpyxl 写入数据到 Excel 文件
2. 保存文件
3. 使用 formulas 加载已写入数据的文件并计算

验证：tests/unit/test_excel_data_filling.py

Fixes: 数据回填失败导致所有计算结果错误
Related: tmp/test_report.md"
```

---

## Task 3: 验证现有测试套件通过

**目的:** 确保修复不破坏现有功能

**Files:**
- Test: `tests/unit/test_excel_calculator.py`

**Step 1: 运行所有 Excel 计算器测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/unit/test_excel_calculator.py -v
```

**预期结果:** 所有测试 PASS

**Step 2: 运行端到端测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/unit/test_excel_calculator.py::test_end_to_end_calculation -v -s
```

**预期结果:** PASS，输出正确的计算结果

**Step 3: 如果有测试失败，分析并修复**

如果 `test_calculate_with_formulas_engine` 失败：
- 检查是否因为数据回填导致计算结果变化
- 更新测试的预期值范围
- 确保测试使用的 fixture 数据与新实现兼容

**Step 4: 所有测试通过后提交**

```bash
# 如果需要更新测试
git add tests/unit/test_excel_calculator.py
git commit -m "test: update assertions for correct data filling behavior"
```

---

## Task 4: 使用真实数据进行集成测试

**目的:** 验证修复在实际场景下工作正常

**Files:**
- Test: 手动测试脚本（已存在于 `tmp/test_calculation.py`）

**Step 1: 使用 tmp/filled_data.json 运行测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH python tmp/test_calculation.py
```

**预期结果:**
- 项目地区: 华南（不是华北）
- 1月能耗: 186.21（不是 20.79）
- 节能率: 合理范围内

**Step 2: 验证 Excel 数据回填**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH python tmp/verify_excel_data.py
```

**预期结果:**
- ✅ 项目地区 (H4): JSON='华南' | Excel='华南'
- ✅ 1月能耗 (D27): JSON=186.21 | Excel=186.21
- ✅ 验证通过！所有数据回填准确无误

**Step 3: 对比修复前后的结果**

创建对比报告：

```bash
cat > tmp/fix_verification.md << 'EOF'
# 修复验证报告

## 修复前（使用模板默认值）
- 项目地区: 华北
- 1月能耗: 20.79 万kWh
- 节能率: 基于错误数据

## 修复后（使用用户数据）
- 项目地区: 华南 ✅
- 1月能耗: 186.21 万kWh ✅
- 节能率: 基于正确数据 ✅

## 结论
✅ Bug 已修复，数据回填准确，计算结果可信
EOF

cat tmp/fix_verification.md
```

**Step 4: 记录验证结果**

无需提交，继续下一任务

---

## Task 5: 更新文档和清理临时文件

**目的:** 更新项目文档，清理测试临时文件

**Files:**
- Modify: `CLAUDE.md`
- Delete: `tmp/*.py` (测试脚本)
- Keep: `tmp/test_report.md` (历史记录)

**Step 1: 更新 CLAUDE.md 中的实现说明**

在 `CLAUDE.md` 的"### Excel计算模板"部分后添加说明：

```markdown
### 数据回填机制

**实现方法**（`core/excel_calculator.py::_calculate_with_formulas`）:

1. **阶段1 - 数据写入**：使用 openpyxl 将 filled_data.json 的数据写入 Excel 文件
   - 项目地区 → Sheet2 H4
   - 月度数据（12个月 × 7个字段）→ Sheet1 D-O 列对应行

2. **阶段2 - 公式计算**：使用 formulas 库加载已写入数据的文件并计算
   - `xl_model = formulas.ExcelModel().loads(excel_path).finish()`
   - `result_data = xl_model.calculate()`

3. **阶段3 - 结果提取**：从 result_data 提取计算结果

**重要**: 早期实现尝试使用 `calculate(inputs={...})`，但 formulas 库会忽略 inputs 参数。
当前实现通过先写入文件再计算解决了这个问题。

**验证**: `tests/unit/test_excel_data_filling.py` 确保数据回填准确性
```

**Step 2: 清理临时测试脚本**

```bash
rm tmp/test_calculation.py
rm tmp/verify_excel_data.py
rm tmp/verify_formulas_calculation.py
rm tmp/test_formulas_methods.py
rm tmp/fix_verification.md
```

**Step 3: 保留测试报告作为历史记录**

```bash
# 保留 tmp/test_report.md 和 tmp/test_method2.xlsx 供参考
ls -lh tmp/
```

**Step 4: 提交文档更新**

```bash
git add CLAUDE.md
git commit -m "docs: document Excel data filling mechanism

更新文档说明数据回填的实现机制，记录早期 calculate(inputs={})
方法的问题及修复方案。

Related: tmp/test_report.md
Related: docs/plans/2025-12-27-fix-excel-data-filling-bug.md"
```

---

## Task 6: 运行完整测试套件

**目的:** 确保整个项目测试通过

**Files:**
- Test: 所有测试

**Step 1: 运行单元测试**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/unit/ -v
```

**预期结果:** 所有单元测试 PASS

**Step 2: 运行集成测试（如果存在）**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/integration/ -v
```

**预期结果:** 所有集成测试 PASS

**Step 3: 检查测试覆盖率**

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH pytest tests/unit/test_excel_calculator.py tests/unit/test_excel_data_filling.py --cov=core.excel_calculator --cov-report=term-missing
```

**预期结果:** `_calculate_with_formulas` 方法覆盖率 > 80%

**Step 4: 记录测试结果**

```bash
echo "✅ 所有测试通过，Bug 修复完成" > tmp/test_summary.txt
```

---

## 验收标准

修复完成后，以下条件必须全部满足：

1. ✅ `tests/unit/test_excel_data_filling.py::test_data_filling_accuracy` PASS
2. ✅ `tests/unit/test_excel_data_filling.py::test_calculation_uses_filled_data` PASS
3. ✅ `tests/unit/test_excel_calculator.py` 所有测试 PASS
4. ✅ 使用 `tmp/filled_data.json` 测试时，项目地区为"华南"，1月能耗为 186.21
5. ✅ 节能率计算结果在合理范围（5%-35%）
6. ✅ 不使用 mock 数据（result 中无 "mock" 字段或为 False）
7. ✅ 文档已更新说明数据回填机制

---

## 回归测试检查清单

在标记 bug 修复完成前，手动验证：

- [ ] Streamlit 应用启动正常
- [ ] 上传调研表 Excel 正常
- [ ] 数据提取和质量检查正常
- [ ] 填充建议生成正常
- [ ] **节能率计算使用正确的用户数据**
- [ ] 结果展示和下载正常

---

## 技术债务和后续改进

1. **性能优化**: 当前每次计算都写入 Excel 文件，可考虑缓存机制
2. **错误处理**: 增强 openpyxl 写入失败时的错误提示
3. **测试数据**: 扩充 `tests/fixtures/` 中的测试用例覆盖更多场景
4. **代码注释**: 在关键步骤添加中文注释说明为什么必须先写文件

---

## 参考资料

- Bug 发现报告: `tmp/test_report.md`
- formulas 库文档: https://formulas.readthedocs.io/
- openpyxl 文档: https://openpyxl.readthedocs.io/
- 相关技能: @superpowers:test-driven-development, @superpowers:systematic-debugging
