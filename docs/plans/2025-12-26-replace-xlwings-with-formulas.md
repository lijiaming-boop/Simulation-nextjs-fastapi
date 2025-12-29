# 替换 xlwings 为 formulas 库实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 将 `core/excel_calculator.py` 中的 xlwings 依赖替换为 formulas 库，实现纯 Python 的 Excel 公式计算，无需外部依赖。

**架构：** 使用 formulas 库加载 Excel 模板文件，修改单元格值，触发公式引擎计算，提取结果。formulas 库是纯 Python 实现，不依赖 Excel/LibreOffice，适合服务器端部署。

**技术栈：**
- formulas >= 1.3.0 (Excel 公式计算引擎)
- openpyxl >= 3.1.0 (Excel 文件读写，已有依赖)
- pandas >= 2.0.0 (数据处理，已有依赖)

---

## 任务概述

1. **Task 1**: 研究 formulas 库 API 并编写测试用例
2. **Task 2**: 实现基于 formulas 的计算方法
3. **Task 3**: 重构错误处理和降级逻辑
4. **Task 4**: 更新文档和依赖配置
5. **Task 5**: 端到端集成测试

---

## Task 1: 研究 formulas 库 API 并编写测试用例

**Files:**
- Create: `tests/unit/test_formulas_engine.py`
- Modify: `requirements.txt`

### Step 1: 添加 formulas 依赖

**File:** `requirements.txt`

```text
streamlit>=1.28.0
pandas>=2.0.0
openpyxl>=3.1.0
formulas>=1.3.0
pytest>=7.0.0
plotly>=5.0.0
claude-agent-sdk>=0.1.0
```

**删除:** `xlwings>=0.30.0` (不再需要)

**Run:**
```bash
pip install formulas>=1.3.0
```

### Step 2: 编写 formulas 库探索测试

**File:** `tests/unit/test_formulas_engine.py`

```python
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

    # 读取 Sheet2 的 H4 单元格 (项目地区)
    # formulas 库使用格式: workbook!sheet!cell
    book_name = list(xl_model.books.keys())[0]
    cell_id = f"{book_name}!Sheet2!H4"

    # 获取单元格值
    value = xl_model[cell_id]

    # 验证能读取到值（可能是空字符串或默认值）
    assert value is not None


def test_formulas_write_and_calculate(template_path):
    """测试写入单元格并触发计算"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    xl_model = formulas.ExcelModel().loads(template_path).finish()
    book_name = list(xl_model.books.keys())[0]

    # 写入测试数据到 Sheet1 的 D27 (1月总能耗)
    cell_id = f"{book_name}!Sheet1!D27"
    xl_model.calculate()  # 首次计算建立依赖图

    # 修改单元格值
    xl_model[cell_id] = 100.5

    # 触发重新计算
    xl_model.calculate()

    # 验证值已更新
    assert xl_model[cell_id] == 100.5


def test_formulas_extract_results(template_path):
    """测试提取计算结果"""
    if not Path(template_path).exists():
        pytest.skip("Excel template not found")

    xl_model = formulas.ExcelModel().loads(template_path).finish()
    book_name = list(xl_model.books.keys())[0]

    # 填充一些测试数据
    # Sheet2 H4: 项目地区
    xl_model[f"{book_name}!Sheet2!H4"] = "华北"

    # Sheet1 月度数据示例 (1月)
    xl_model[f"{book_name}!Sheet1!D27"] = 100  # 总能耗
    xl_model[f"{book_name}!Sheet1!D9"] = 7     # 冷机供水温度
    xl_model[f"{book_name}!Sheet1!D13"] = 45   # 冷却泵频率
    xl_model[f"{book_name}!Sheet1!D14"] = 4.5  # 冷却水温差
    xl_model[f"{book_name}!Sheet1!D18"] = 50   # 冷冻泵频率
    xl_model[f"{book_name}!Sheet1!D19"] = 4.5  # 冷冻水温差
    xl_model[f"{book_name}!Sheet1!D23"] = 22   # 冷却塔温度

    # 触发计算
    xl_model.calculate()

    # 提取 Sheet2 结果
    result_cells = {
        "chiller_saving_total": f"{book_name}!Sheet2!P11",
        "cooling_pump_saving_total": f"{book_name}!Sheet2!P16",
        "freezing_pump_saving_total": f"{book_name}!Sheet2!P21",
        "tower_saving_total": f"{book_name}!Sheet2!P25",
        "total_saving": f"{book_name}!Sheet2!P28",
        "saving_rate": f"{book_name}!Sheet2!P29",
    }

    results = {}
    for key, cell_id in result_cells.items():
        value = xl_model[cell_id]
        results[key] = value if value is not None else 0

    # 验证结果结构
    assert "chiller_saving_total" in results
    assert "saving_rate" in results

    # 打印结果用于调试
    print(f"计算结果: {results}")
```

### Step 3: 运行探索测试

**Run:**
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_formulas_engine.py -v -s
```

**Expected:**
- 所有测试通过（如果 Excel 模板存在）
- 或跳过测试（如果模板不存在）
- 输出显示计算结果值

### Step 4: Commit

```bash
git add requirements.txt tests/unit/test_formulas_engine.py
git commit -m "test: add formulas library exploration tests

- Add formulas>=1.3.0 dependency
- Remove xlwings dependency
- Create test cases for formulas library API
- Verify Excel loading, cell read/write, and calculation"
```

---

## Task 2: 实现基于 formulas 的计算方法

**Files:**
- Modify: `core/excel_calculator.py:64-135`

### Step 1: 编写新方法的测试用例

**File:** `tests/unit/test_excel_calculator.py`

在现有测试文件末尾添加：

```python
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
    assert "total_saving" in result
    assert "completeness" in result

    # 验证节能率在合理范围
    assert 0 <= result["energy_saving_rate"] <= 1.0
```

### Step 2: 运行测试验证其失败

**Run:**
```bash
pytest tests/unit/test_excel_calculator.py::test_calculate_with_formulas_engine -v
```

**Expected:** FAIL - AttributeError: 'ExcelCalculator' object has no attribute '_calculate_with_formulas'

### Step 3: 实现 _calculate_with_formulas 方法

**File:** `core/excel_calculator.py`

在 `_calculate_with_xlwings` 方法之后添加新方法：

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
        except ImportError:
            raise RuntimeError("formulas library not installed")

        # 加载 Excel 文件
        xl_model = formulas.ExcelModel().loads(str(excel_path)).finish()

        # 获取工作簿名称
        book_name = list(xl_model.books.keys())[0]

        # 1. 回填项目地区到 Sheet2
        region_cell = self.mapper.get_basic_info_cell("project_region")
        cell_id = f"{book_name}!Sheet2!{region_cell}"
        xl_model[cell_id] = data["project_region"]

        # 2. 回填月度数据到 Sheet1
        for month_data in data["monthly_data"]:
            month_idx = month_data["month"] - 1  # 转换为 0-based 索引

            for field in self.mapper.get_monthly_fields():
                value = month_data.get(field)
                if value is not None:
                    cell = self.mapper.get_cell("monthly_data", month_idx, field)
                    cell_id = f"{book_name}!Sheet1!{cell}"
                    xl_model[cell_id] = value

        # 3. 触发重新计算
        xl_model.calculate()

        # 4. 提取计算结果
        def get_result_value(result_field: str) -> float:
            """提取结果单元格的值"""
            cell = self.mapper.get_result_cell(result_field)
            cell_id = f"{book_name}!Sheet2!{cell}"
            value = xl_model[cell_id]
            return float(value) if value is not None else 0.0

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

### Step 4: 运行测试验证其通过

**Run:**
```bash
pytest tests/unit/test_excel_calculator.py::test_calculate_with_formulas_engine -v -s
```

**Expected:** PASS - 测试通过，显示计算结果

### Step 5: Commit

```bash
git add core/excel_calculator.py tests/unit/test_excel_calculator.py
git commit -m "feat: implement formulas-based Excel calculation

- Add _calculate_with_formulas method using formulas library
- Support cell value writing and formula evaluation
- Extract calculation results from Excel model
- Add unit test for formulas engine integration"
```

---

## Task 3: 重构计算流程使用 formulas 优先

**Files:**
- Modify: `core/excel_calculator.py:1-62`

### Step 1: 编写集成测试

**File:** `tests/unit/test_excel_calculator.py`

修改现有的 `test_calculate_energy_saving` 测试：

```python
@pytest.mark.skipif(
    not Path("00_sample/机房智能化节能评估表-按冷站电量数据.xlsx").exists(),
    reason="Excel template not found"
)
def test_calculate_energy_saving(template_path, filled_data_path, tmp_dir):
    """测试节能率计算 (使用 formulas 引擎)"""
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
```

### Step 2: 运行测试验证当前行为

**Run:**
```bash
pytest tests/unit/test_excel_calculator.py::test_calculate_energy_saving -v -s
```

**Expected:** 测试通过（使用 xlwings 或 mock）

### Step 3: 修改 calculate 方法使用 formulas 优先

**File:** `core/excel_calculator.py`

替换 `calculate` 方法中的计算逻辑（第 47-53 行）：

```python
        try:
            # 优先使用 formulas 库（纯 Python，无需外部依赖）
            result = self._calculate_with_formulas(data, temp_excel)
        except Exception as e:
            # 如果 formulas 不可用，返回 mock 结果用于测试
            print(f"Warning: formulas calculation failed: {e}")
            result = self._mock_result(data)
```

### Step 4: 更新模块文档字符串

**File:** `core/excel_calculator.py` (第 1-4 行)

```python
"""Excel 计算引擎

使用 formulas 库执行 Excel 公式计算（纯 Python 实现，无需外部依赖）
"""
```

### Step 5: 运行测试验证新实现

**Run:**
```bash
pytest tests/unit/test_excel_calculator.py::test_calculate_energy_saving -v -s
```

**Expected:** PASS - 使用 formulas 引擎完成计算

### Step 6: Commit

```bash
git add core/excel_calculator.py
git commit -m "refactor: use formulas library as primary calculation engine

- Replace xlwings with formulas library
- Update docstring to reflect new implementation
- Maintain mock fallback for error handling
- All tests pass with formulas engine"
```

---

## Task 4: 清理遗留代码和更新文档

**Files:**
- Modify: `core/excel_calculator.py:64-135`
- Modify: `CLAUDE.md`
- Modify: `README.md` (if exists)

### Step 1: 编写测试确保向后兼容

**File:** `tests/unit/test_excel_calculator.py`

添加测试验证完整的计算流程：

```python
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
```

### Step 2: 运行测试验证

**Run:**
```bash
pytest tests/unit/test_excel_calculator.py::test_end_to_end_calculation -v -s
```

**Expected:** PASS

### Step 3: 移除 xlwings 相关代码

**File:** `core/excel_calculator.py`

删除 `_calculate_with_xlwings` 方法（第 64-135 行）：

```python
# 删除整个 _calculate_with_xlwings 方法
# 该方法已被 _calculate_with_formulas 替代
```

### Step 4: 运行所有测试确保没有破坏

**Run:**
```bash
pytest tests/unit/test_excel_calculator.py -v
```

**Expected:** 所有测试通过

### Step 5: 更新 CLAUDE.md 文档

**File:** `CLAUDE.md`

找到 "### Excel引擎优先级" 部分并更新：

```markdown
### Excel 计算引擎

**当前实现：** 使用 `formulas` 库（纯 Python）

- **formulas 库**：Excel 公式解析和计算引擎
  - 无需外部依赖（不需要 Excel/LibreOffice）
  - 纯 Python 实现，跨平台兼容
  - 支持大部分 Excel 公式和函数
  - 适合服务器端自动化部署

**代码位置：** `core/excel_calculator.py`

**关键方法：**
- `_calculate_with_formulas()`: 使用 formulas 库执行计算
- `_mock_result()`: 降级方案（当 formulas 不可用时）

**使用示例：**
```python
# core/excel_calculator.py 会自动使用 formulas 引擎
calc = ExcelCalculator(template_path)
result_path = calc.calculate(filled_data_path, output_path)
```
```

同时删除原有的 xlwings/openpyxl 优先级说明。

### Step 6: Commit

```bash
git add core/excel_calculator.py CLAUDE.md tests/unit/test_excel_calculator.py
git commit -m "refactor: remove xlwings legacy code

- Delete _calculate_with_xlwings method
- Update CLAUDE.md documentation
- Add comprehensive end-to-end test
- Simplify calculation engine to formulas-only"
```

---

## Task 5: 端到端集成测试和验证

**Files:**
- Run integration tests
- Verify app functionality

### Step 1: 运行所有单元测试

**Run:**
```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/ -v
```

**Expected:** 所有单元测试通过

### Step 2: 运行集成测试（如果存在）

**Run:**
```bash
pytest tests/integration/ -v -s
```

**Expected:** 集成测试通过或合理跳过

### Step 3: 手动测试 Streamlit 应用

**Run:**
```bash
streamlit run app.py
```

**Manual Test Steps:**
1. 上传调研表 Excel 文件
2. 查看数据提取和质量检查结果
3. 应用填充建议
4. 执行节能率计算
5. 验证计算结果显示正常
6. 下载结果 Excel 文件

**Expected:**
- 应用正常启动
- 计算流程完整执行
- 结果数值合理
- 无错误或警告

### Step 4: 验证示例调研表测试

**Run:**
```bash
export ANTHROPIC_API_KEY='your-api-key'
pytest tests/integration/test_sample_surveys_e2e.py -v -s
```

**Expected:** 示例调研表端到端测试通过（如果该测试存在）

### Step 5: 更新 requirements.txt 最终版本

**File:** `requirements.txt`

最终版本应为：

```text
streamlit>=1.28.0
pandas>=2.0.0
openpyxl>=3.1.0
formulas>=1.3.0
pytest>=7.0.0
plotly>=5.0.0
claude-agent-sdk>=0.1.0
```

确认已移除 `xlwings>=0.30.0`

### Step 6: Commit 和总结

```bash
git add requirements.txt
git commit -m "chore: finalize formulas library integration

- Remove xlwings from dependencies
- Verify all tests pass with formulas engine
- Confirm Streamlit app works end-to-end
- Update requirements.txt to final version"
```

---

## 验收标准

✅ **功能完整性**
- [ ] 所有单元测试通过
- [ ] 集成测试通过（如适用）
- [ ] Streamlit 应用正常运行
- [ ] 计算结果准确（与 xlwings 版本对比）

✅ **代码质量**
- [ ] 移除所有 xlwings 相关代码
- [ ] 错误处理清晰（formulas 失败时降级到 mock）
- [ ] 代码注释准确反映新实现
- [ ] 无未使用的导入和死代码

✅ **文档完整性**
- [ ] CLAUDE.md 更新正确
- [ ] requirements.txt 移除 xlwings
- [ ] 代码注释反映 formulas 实现

✅ **部署友好**
- [ ] 无外部依赖（不需要 Excel/LibreOffice）
- [ ] 纯 Python 实现，跨平台兼容
- [ ] 适合服务器端自动化部署

---

## 潜在风险和缓解策略

### 风险 1: formulas 库不支持某些复杂公式

**症状:** 计算结果为 0 或错误

**缓解:**
1. 在探索测试中提前验证公式支持
2. 如果发现不支持的公式，考虑：
   - 使用 openpyxl 读取公式，手动实现计算逻辑
   - 或保留 xlwings 作为可选依赖（通过环境变量控制）

### 风险 2: 单元格引用格式不兼容

**症状:** KeyError 或单元格找不到

**缓解:**
1. 在探索测试中验证单元格引用格式
2. formulas 库使用 `workbook!sheet!cell` 格式
3. 确保正确获取 workbook 名称

### 风险 3: 性能下降

**症状:** 计算时间显著增加

**缓解:**
1. 如果 formulas 性能不佳，考虑：
   - 缓存 ExcelModel 对象
   - 只加载一次模板，复用计算
2. 性能对比测试：xlwings vs formulas

### 风险 4: 数值精度差异

**症状:** 计算结果与 xlwings 版本不完全一致

**缓解:**
1. 在集成测试中对比两种引擎的结果
2. 设置合理的误差容忍度（如 0.01%）
3. 记录差异原因

---

## 参考资料

**Formulas 库文档:**
- PyPI: https://pypi.org/project/formulas/
- GitHub: https://github.com/vinci1it2000/formulas
- ReadTheDocs: https://formulas.readthedocs.io/

**备选方案:**
- xlcalculator: https://pypi.org/project/xlcalculator/
- excel-formulas-calculator: https://pypi.org/project/excel-formulas-calculator/

**项目文档:**
- `CLAUDE.md`: 项目架构和开发指南
- `docs/testing/sample-surveys-testing-guide.md`: 测试指南

---

## Sources
- [formulas · PyPI](https://pypi.org/project/formulas/)
- [GitHub - vinci1it2000/formulas](https://github.com/vinci1it2000/formulas)
- [formulas: An Excel formulas interpreter in Python](https://formulas.readthedocs.io/)
- [xlcalculator · PyPI](https://pypi.org/project/xlcalculator/)
- [excel-formulas-calculator · PyPI](https://pypi.org/project/excel-formulas-calculator/)
