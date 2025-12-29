# 节能率范围计算实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 基于Excel模板的上限和下限两个sheet，为每个调研表计算节能率的评估范围（最小值-最大值）

**架构:**
- 扩展 CellMapping 支持上限和下限两个sheet的配置
- 修改 ExcelCalculator 支持双sheet计算（上限+下限）
- 更新 UI 展示节能率范围而非单一值
- 保持向后兼容，现有单一值计算仍可用

**技术栈:**
- Python openpyxl, formulas（双sheet计算）
- CellMapping 扩展（多sheet配置）
- Streamlit（范围展示）

---

## 背景分析

### 当前实现问题

**现状:**
- `CellMapping.SHEET_NAME` 硬编码为 `"【2】按冷站电量数据 "`（下限sheet）
- `ExcelCalculator` 只计算一个sheet，返回单一节能率值
- UI 展示单一节能率，用户无法了解评估范围

**Excel模板结构:**
- Sheet 1: `【1】按冷站电量数据-上限 ` - 估算节能率上限
- Sheet 2: `【2】按冷站电量数据-下限` - 估算节能率下限
- Sheet 3: `全国主要城市气象情况` - 气象数据（不变）

**关键发现:**
- 上限和下限sheet的**行列结构完全相同**（数据输入位置、结果提取位置一致）
- 只是公式中的**系数不同**（如优化幅度、安全系数等）
- 因此可以复用同一套 CellMapping，只需切换 sheet 名称

### 目标效果

**输入:** 调研表数据（filled_data.json）

**输出:** 节能率范围
```json
{
  "energy_saving_rate_min": 0.12,  // 下限（保守估计）
  "energy_saving_rate_max": 0.18,  // 上限（理想情况）
  "energy_saving_rate_range": "12.0% - 18.0%",
  "calculation_method": "dual_sheet",
  ...
}
```

**UI展示:**
- 原来：节能率 15.0%
- 现在：节能率范围 12.0% - 18.0%（下限-上限）

---

## 任务1: 扩展 CellMapping 支持多sheet配置

**文件:**
- 修改: `config/cell_mapping.py:1-83`
- 测试: `tests/unit/test_cell_mapping.py`

### 步骤1: 编写测试 - 测试上限sheet映射

创建 `tests/unit/test_cell_mapping_multi_sheet.py`:

```python
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
```

### 步骤2: 运行测试确认失败

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_cell_mapping_multi_sheet.py -v
```

**预期**: FAIL - AttributeError: 'CellMapping' object has no attribute 'get_sheet_name'

### 步骤3: 实现 CellMapping 多sheet支持

修改 `config/cell_mapping.py`:

```python
"""Excel 单元格映射配置

映射 JSON 数据字段到 Excel 模板单元格位置
基于模板: 00_sample/模板测算表/节能评估表-按冷站电量数据-标准版.xlsx
"""
from typing import Dict, List


class CellMapping:
    """Excel 单元格映射器 - 支持上限和下限两个sheet"""

    # Sheet 名称映射
    SHEET_NAMES = {
        "upper": "【1】按冷站电量数据-上限 ",  # 节能率上限
        "lower": "【2】按冷站电量数据-下限",   # 节能率下限
    }

    # 默认使用下限sheet（向后兼容）
    SHEET_NAME = SHEET_NAMES["lower"]

    # 列号映射: 月份(0-11) -> Excel列(D-O)
    MONTH_COLS = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O']

    # 月度数据字段 -> 行号映射
    # 注意：上限和下限sheet的行号完全相同
    MONTHLY_ROWS = {
        "total_energy": 27,
        "chiller_supply_temp": 9,
        "cooling_pump_freq": 13,
        "cooling_water_temp_diff": 14,
        "freezing_pump_freq": 18,
        "freezing_water_temp_diff": 19,
        "cooling_tower_outlet_temp": 23,
    }

    # 基础信息字段 -> 单元格映射
    BASIC_INFO_CELLS = {
        "project_region": "H4",
    }

    # 结果提取位置
    # 注意：上限和下限sheet的结果位置完全相同
    RESULT_CELLS = {
        "chiller_saving_total": "P11",
        "cooling_pump_saving_total": "P16",
        "freezing_pump_saving_total": "P21",
        "tower_saving_total": "P25",
        "total_saving": "P28",
        "saving_rate": "O30",
    }

    def get_sheet_name(self, sheet_type: str) -> str:
        """获取sheet名称

        Args:
            sheet_type: sheet类型 ("upper"/"lower")

        Returns:
            Excel sheet名称

        Raises:
            ValueError: 无效的sheet类型
        """
        if sheet_type not in self.SHEET_NAMES:
            raise ValueError(
                f"无效的sheet类型: {sheet_type}。"
                f"支持的类型: {list(self.SHEET_NAMES.keys())}"
            )
        return self.SHEET_NAMES[sheet_type]

    def get_cell(self, data_type: str, month_index: int, field: str) -> str:
        """获取单元格位置

        Args:
            data_type: 数据类型 ("monthly_data")
            month_index: 月份索引 (0-11)
            field: 字段名

        Returns:
            Excel单元格位置,如 "D27"
        """
        if data_type != "monthly_data":
            raise ValueError(f"Unsupported data_type: {data_type}")

        if month_index < 0 or month_index > 11:
            raise ValueError(f"Invalid month_index: {month_index}")

        if field not in self.MONTHLY_ROWS:
            raise ValueError(f"Unknown field: {field}")

        col = self.MONTH_COLS[month_index]
        row = self.MONTHLY_ROWS[field]
        return f"{col}{row}"

    def get_basic_info_cell(self, field: str) -> str:
        """获取基础信息单元格位置"""
        if field not in self.BASIC_INFO_CELLS:
            raise ValueError(f"Unknown basic info field: {field}")
        return self.BASIC_INFO_CELLS[field]

    def get_result_cell(self, field: str) -> str:
        """获取结果单元格位置"""
        if field not in self.RESULT_CELLS:
            raise ValueError(f"Unknown result field: {field}")
        return self.RESULT_CELLS[field]

    def get_monthly_fields(self) -> List[str]:
        """获取所有月度数据字段列表"""
        return list(self.MONTHLY_ROWS.keys())
```

### 步骤4: 运行测试确认通过

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_cell_mapping_multi_sheet.py -v
```

**预期**: PASS - 5个测试全部通过

### 步骤5: 验证现有测试不受影响

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_cell_mapping.py -v
```

**预期**: PASS - 现有测试保持通过（向后兼容）

### 步骤6: 提交 CellMapping 多sheet支持

```bash
git add config/cell_mapping.py tests/unit/test_cell_mapping_multi_sheet.py
git commit -m "feat: add multi-sheet support to CellMapping

- 新增 SHEET_NAMES 字典映射 upper/lower
- 新增 get_sheet_name() 方法
- 保持向后兼容，默认使用下限sheet
- 添加5个单元测试

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务2: 扩展 ExcelCalculator 支持双sheet计算

**文件:**
- 修改: `core/excel_calculator.py:85-155`
- 测试: `tests/unit/test_excel_calculator_range.py`

### 步骤1: 编写测试 - 测试双sheet计算

创建 `tests/unit/test_excel_calculator_range.py`:

```python
"""测试 ExcelCalculator 双sheet范围计算"""
import json
import pytest
from pathlib import Path
from core.excel_calculator import ExcelCalculator


@pytest.fixture
def sample_filled_data(tmp_path):
    """样例填充数据"""
    data = {
        "station_type": "standard",
        "project_region": "华南",
        "monthly_data": [
            {
                "month": i,
                "total_energy": 100 + i * 10,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": 45.0,
                "cooling_water_temp_diff": 5.0,
                "freezing_pump_freq": 45.0,
                "freezing_water_temp_diff": 5.0,
                "cooling_tower_outlet_temp": 30.0,
            }
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    data_path = tmp_path / "filled.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

    return str(data_path)


def test_calculate_with_range(sample_filled_data, tmp_path):
    """测试计算节能率范围（上限+下限）"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result.json"
    result_path = calculator.calculate(
        sample_filled_data,
        str(output_path)
    )

    assert Path(result_path).exists()

    with open(result_path) as f:
        result = json.load(f)

    # 验证包含范围字段
    assert "energy_saving_rate_min" in result
    assert "energy_saving_rate_max" in result
    assert "energy_saving_rate_range" in result

    # 验证范围合理性
    min_rate = result["energy_saving_rate_min"]
    max_rate = result["energy_saving_rate_max"]

    assert 0 < min_rate < max_rate < 1.0
    assert result["energy_saving_rate_range"] == f"{min_rate*100:.1f}% - {max_rate*100:.1f}%"


def test_calculate_preserves_original_fields(sample_filled_data, tmp_path):
    """测试计算保留原有字段（向后兼容）"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result.json"
    result_path = calculator.calculate(
        sample_filled_data,
        str(output_path)
    )

    with open(result_path) as f:
        result = json.load(f)

    # 验证原有字段仍存在
    assert "energy_saving_rate" in result  # 原字段（下限值）
    assert "chiller_saving" in result
    assert "pump_saving" in result
    assert "tower_saving" in result
    assert "total_saving" in result


def test_backward_compatibility_single_value(sample_filled_data, tmp_path):
    """测试向后兼容 - energy_saving_rate 应等于下限值"""
    calculator = ExcelCalculator()

    output_path = tmp_path / "result.json"
    result_path = calculator.calculate(
        sample_filled_data,
        str(output_path)
    )

    with open(result_path) as f:
        result = json.load(f)

    # energy_saving_rate（旧字段）应该等于 energy_saving_rate_min（下限）
    assert result["energy_saving_rate"] == result["energy_saving_rate_min"]
```

### 步骤2: 运行测试确认失败

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_excel_calculator_range.py -v
```

**预期**: FAIL - KeyError: 'energy_saving_rate_min'

### 步骤3: 实现双sheet计算逻辑

修改 `core/excel_calculator.py` 的 `_calculate_with_formulas` 方法：

```python
def _calculate_with_formulas(
    self,
    data: Dict[str, Any],
    excel_path: Path
) -> Dict[str, Any]:
    """使用 formulas 库执行计算

    计算上限和下限两个sheet，返回节能率范围

    Args:
        data: 填充后的数据字典
        excel_path: Excel 文件路径

    Returns:
        计算结果字典（包含范围）
    """
    try:
        import formulas
        import openpyxl
    except ImportError as e:
        raise RuntimeError(f"Required library not installed: {e}")

    # 计算下限（保守估计）
    result_lower = self._calculate_single_sheet(data, excel_path, "lower")

    # 计算上限（理想情况）
    result_upper = self._calculate_single_sheet(data, excel_path, "upper")

    # 合并结果，构建范围
    result = {
        # 节能率范围
        "energy_saving_rate_min": result_lower["saving_rate"],
        "energy_saving_rate_max": result_upper["saving_rate"],
        "energy_saving_rate_range": (
            f"{result_lower['saving_rate']*100:.1f}% - "
            f"{result_upper['saving_rate']*100:.1f}%"
        ),

        # 向后兼容：保留原有单一值字段（使用下限）
        "energy_saving_rate": result_lower["saving_rate"],

        # 分项节能量范围
        "chiller_saving_min": result_lower["chiller_saving"],
        "chiller_saving_max": result_upper["chiller_saving"],
        "chiller_saving": result_lower["chiller_saving"],  # 向后兼容

        "pump_saving_min": result_lower["pump_saving"],
        "pump_saving_max": result_upper["pump_saving"],
        "pump_saving": result_lower["pump_saving"],  # 向后兼容

        "tower_saving_min": result_lower["tower_saving"],
        "tower_saving_max": result_upper["tower_saving"],
        "tower_saving": result_lower["tower_saving"],  # 向后兼容

        "total_saving_min": result_lower["total_saving"],
        "total_saving_max": result_upper["total_saving"],
        "total_saving": result_lower["total_saving"],  # 向后兼容

        # 元数据
        "completeness": data["_metadata"]["final_completeness"],
        "filled_count": data["_metadata"]["fill_count"],
        "calculation_timestamp": datetime.now().isoformat(),
        "calculation_method": "dual_sheet",  # 标记使用双sheet计算
    }

    return result


def _calculate_single_sheet(
    self,
    data: Dict[str, Any],
    excel_path: Path,
    sheet_type: str
) -> Dict[str, Any]:
    """计算单个sheet（上限或下限）

    Args:
        data: 填充后的数据字典
        excel_path: Excel 文件路径
        sheet_type: sheet类型 ("upper"/"lower")

    Returns:
        单个sheet的计算结果
    """
    import formulas
    import openpyxl

    # 获取sheet名称
    sheet_name = self.mapper.get_sheet_name(sheet_type)

    # 阶段1: 使用 openpyxl 将数据写入 Excel 文件
    wb = openpyxl.load_workbook(excel_path)
    sheet = wb[sheet_name]

    # 1. 回填项目地区
    region_cell = self.mapper.get_basic_info_cell("project_region")
    sheet[region_cell] = data["project_region"]

    # 2. 回填月度数据
    for month_data in data["monthly_data"]:
        month_idx = month_data["month"] - 1

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
    book_name = list(xl_model.books.keys())[0]
    result_data = xl_model.calculate()

    # 阶段3: 提取计算结果
    def get_result_value(result_field: str) -> float:
        """提取结果单元格的值"""
        cell = self.mapper.get_result_cell(result_field)
        cell_id = f"'[{book_name.lower()}]{sheet_name}'!{cell}"

        if cell_id in result_data:
            value = result_data[cell_id]
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
        "saving_rate": get_result_value("saving_rate"),
    }

    return result
```

### 步骤4: 运行测试确认通过

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_excel_calculator_range.py -v
```

**预期**: PASS - 3个测试全部通过

### 步骤5: 验证现有测试兼容性

```bash
PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_excel_calculator.py tests/integration/test_multi_template_calculation.py -v
```

**预期**: 现有测试保持通过或可接受的修改

### 步骤6: 提交双sheet计算功能

```bash
git add core/excel_calculator.py tests/unit/test_excel_calculator_range.py
git commit -m "feat: add dual-sheet range calculation to ExcelCalculator

- 新增 _calculate_single_sheet() 方法计算单个sheet
- 修改 _calculate_with_formulas() 计算上限和下限
- 返回节能率范围字段（min/max/range）
- 保持向后兼容，原有字段使用下限值
- 添加3个单元测试

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务3: 更新 UI 展示节能率范围

**文件:**
- 修改: `app.py:render_result_stage()`

### 步骤1: 修改结果展示阶段

在 `app.py` 的 `render_result_stage()` 函数中，修改节能率展示：

**定位代码:**
找到显示节能率的部分（通常在结果页面的核心指标展示区域）

**原代码（大约）:**
```python
st.metric(
    "节能率",
    f"{result['energy_saving_rate'] * 100:.1f}%"
)
```

**修改为:**
```python
# 检查是否为范围计算结果
if "energy_saving_rate_range" in result:
    # 新版：展示范围
    st.metric(
        "节能率范围",
        result["energy_saving_rate_range"],
        help="基于上限和下限两种估算方法"
    )

    # 详细展示
    col1, col2 = st.columns(2)
    with col1:
        st.metric(
            "下限（保守估计）",
            f"{result['energy_saving_rate_min'] * 100:.1f}%"
        )
    with col2:
        st.metric(
            "上限（理想情况）",
            f"{result['energy_saving_rate_max'] * 100:.1f}%"
        )
else:
    # 旧版：单一值（向后兼容）
    st.metric(
        "节能率",
        f"{result['energy_saving_rate'] * 100:.1f}%"
    )
```

### 步骤2: 更新分项节能量展示

在分项节能量展示部分，同样支持范围：

```python
# 冷机节能量
if "chiller_saving_min" in result:
    st.metric(
        "冷机节能量范围",
        f"{result['chiller_saving_min']:.1f} - {result['chiller_saving_max']:.1f} 万kWh"
    )
else:
    st.metric("冷机节能量", f"{result['chiller_saving']:.1f} 万kWh")

# 水泵节能量
if "pump_saving_min" in result:
    st.metric(
        "水泵节能量范围",
        f"{result['pump_saving_min']:.1f} - {result['pump_saving_max']:.1f} 万kWh"
    )
else:
    st.metric("水泵节能量", f"{result['pump_saving']:.1f} 万kWh")

# 冷却塔节能量
if "tower_saving_min" in result:
    st.metric(
        "冷却塔节能量范围",
        f"{result['tower_saving_min']:.1f} - {result['tower_saving_max']:.1f} 万kWh"
    )
else:
    st.metric("冷却塔节能量", f"{result['tower_saving']:.1f} 万kWh")

# 总节能量
if "total_saving_min" in result:
    st.metric(
        "总节能量范围",
        f"{result['total_saving_min']:.1f} - {result['total_saving_max']:.1f} 万kWh"
    )
else:
    st.metric("总节能量", f"{result['total_saving']:.1f} 万kWh")
```

### 步骤3: 添加计算方法说明

在结果页面添加说明：

```python
# 在结果展示区域末尾添加
if result.get("calculation_method") == "dual_sheet":
    st.info(
        "📊 **节能率范围说明**\n\n"
        "- **下限（保守估计）**: 基于常规优化参数，考虑实际约束\n"
        "- **上限（理想情况）**: 基于最优运行条件，理想化假设\n"
        "- **实际节能效果**: 通常在此范围内，具体取决于项目实施情况"
    )
```

### 步骤4: 手动测试 UI

```bash
streamlit run app.py
```

**测试步骤:**
1. 上传调研表
2. 完成提取、填充、计算流程
3. 验证结果页面显示节能率范围
4. 验证分项节能量显示范围
5. 验证向后兼容（如果有旧数据）

### 步骤5: 提交 UI 更新

```bash
git add app.py
git commit -m "feat: display energy saving rate range in UI

- 展示节能率范围（下限-上限）
- 分项节能量同样展示范围
- 添加范围计算说明
- 保持向后兼容，支持旧版单一值

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务4: 更新文档

**文件:**
- 修改: `CLAUDE.md`
- 修改: `00_sample/模板测算表/readme.md`

### 步骤1: 更新 CLAUDE.md 核心架构说明

在 `CLAUDE.md` 的"核心架构"部分添加：

```markdown
### Excel计算模板

模板文件：`00_sample/模板测算表/节能评估表-按冷站电量数据-标准版.xlsx`（和二次泵版）

**Sheet结构（3个）**：
1. **【1】按冷站电量数据-上限** - 估算节能率上限（理想情况）
2. **【2】按冷站电量数据-下限** - 估算节能率下限（保守估计）
3. **全国主要城市气象情况** - 气象数据（辅助计算）

**双Sheet计算机制**：
- 系统会同时计算上限和下限两个sheet
- 上限：基于最优运行条件，理想化假设
- 下限：基于常规优化参数，考虑实际约束
- 输出节能率范围：下限% - 上限%

**Sheet1和Sheet2的差异**：
- 行列结构完全相同（数据输入位置、结果提取位置一致）
- 仅公式中的系数不同（优化幅度、安全系数等）
- 因此使用同一套 CellMapping 映射

**数据输入** (Sheet1和Sheet2):
- 月度数据写入列：D-O（1-12月）
- 关键行号：见 `config/cell_mapping.py` 的 `MONTHLY_ROWS`

**结果提取** (Sheet1和Sheet2):
- 基础信息：项目地区(H4)
- 结果提取：总节能率(O30)、分项节能量(P11/P16/P21/P25/P28)

**核心物理系数**：
- 冷机供水温度优化：4%/℃（上限和下限可能不同）
- 水泵变频优化：能耗 ∝ 频率^2.5
- 冷却塔优化：1.5%/℃（上限和下限可能不同）
```

### 步骤2: 更新 readme.md

修改 `00_sample/模板测算表/readme.md`:

```markdown
# 节能评估表模板说明

## 文件清单

### 1. 节能评估表-按冷站电量数据-标准版.xlsx
- **适用范围**: 标准空调站房
- **特征**: 仅有一次冷冻泵，无二次泵分离
- **Sheet结构**: 3个sheet（上限/下限/气象数据）
- **不适用**: 包含热水泵、水蓄冷、二次泵、中低温机组的空调站房

### 2. 节能评估表-按冷站电量数据-二次泵版.xlsx
- **适用范围**: 冷冻系统包含二次泵的空调站房
- **特征**: 冷冻泵分为一次泵和二次泵
- **Sheet结构**: 3个sheet（上限/下限/气象数据）
- **不适用**: 包含热水泵、水蓄冷、中低温机组的空调站房

## Sheet结构说明

每个模板包含3个sheet：

1. **【1】按冷站电量数据-上限**
   - 用途：估算节能率上限（理想情况）
   - 特点：基于最优运行条件，理想化假设
   - 适用：了解项目最大节能潜力

2. **【2】按冷站电量数据-下限**
   - 用途：估算节能率下限（保守估计）
   - 特点：基于常规优化参数，考虑实际约束
   - 适用：风险控制，保守承诺

3. **全国主要城市气象情况**
   - 用途：提供各地区湿球温度等气象数据
   - 特点：辅助上限和下限的计算

## 自动识别和计算机制

系统会根据调研表内容**自动识别站房类型**并选择对应模板：

- 检测到"一次泵"/"二次泵"关键词 → 使用二次泵版
- 未检测到分离泵特征 → 使用标准版
- 检测到热水泵/水蓄冷/中低温机组 → 自动拦截，不支持

**节能率范围计算**：
- 系统自动计算上限和下限两个sheet
- 输出节能率范围：下限% - 上限%
- 实际节能效果通常在此范围内

## 不支持的特殊类型

以下类型的空调站房**不在自动评估范围内**：

- ❌ 包含热水泵的站房
- ❌ 包含水蓄冷/冰蓄冷系统的站房
- ❌ 包含中低温机组的站房

这些特殊类型需要专门的节能评估方法，系统会在数据提取阶段自动识别并拦截。

## 技术实现

- 站房类型识别：`.claude/skills/extract-and-check-data/`
- 模板配置管理：`config/template_config.py`
- 单元格映射（双sheet）：`config/cell_mapping.py`
- 计算引擎（双sheet）：`core/excel_calculator.py`
```

### 步骤3: 提交文档更新

```bash
git add CLAUDE.md 00_sample/模板测算表/readme.md
git commit -m "docs: update documentation for dual-sheet range calculation

- 更新Excel模板结构说明（上限/下限/气象）
- 说明双sheet计算机制
- 补充节能率范围的含义
- 更新readme.md模板说明

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 任务5: 端到端测试

**文件:**
- 创建: `tests/e2e/test_energy_saving_range_workflow.py`

### 步骤1: 编写端到端测试

创建 `tests/e2e/test_energy_saving_range_workflow.py`:

```python
"""端到端测试：节能率范围计算工作流"""
import json
import pytest
from pathlib import Path
from core.excel_calculator import ExcelCalculator
from core.data_filler import DataFiller


def test_full_range_calculation_workflow(tmp_path):
    """测试完整的范围计算工作流"""

    # 准备测试数据
    filled_data = {
        "station_type": "standard",
        "project_region": "华南",
        "monthly_data": [
            {
                "month": i,
                "total_energy": 100 + i * 10,
                "chiller_supply_temp": 7.0 + i * 0.1,
                "cooling_pump_freq": 45.0,
                "cooling_water_temp_diff": 5.0,
                "freezing_pump_freq": 45.0,
                "freezing_water_temp_diff": 5.0,
                "cooling_tower_outlet_temp": 30.0 - i * 0.5,
            }
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 3}
    }

    filled_path = tmp_path / "filled_data.json"
    with open(filled_path, 'w', encoding='utf-8') as f:
        json.dump(filled_data, f)

    # 执行计算
    calculator = ExcelCalculator()
    result_path = tmp_path / "result.json"

    calculator.calculate(str(filled_path), str(result_path))

    # 验证结果
    with open(result_path) as f:
        result = json.load(f)

    # 1. 验证范围字段存在
    assert "energy_saving_rate_min" in result
    assert "energy_saving_rate_max" in result
    assert "energy_saving_rate_range" in result

    # 2. 验证范围合理性
    min_rate = result["energy_saving_rate_min"]
    max_rate = result["energy_saving_rate_max"]

    assert 0 < min_rate < max_rate < 1.0, "节能率范围应在0-100%之间且min<max"

    # 3. 验证范围字符串格式
    expected_range = f"{min_rate*100:.1f}% - {max_rate*100:.1f}%"
    assert result["energy_saving_rate_range"] == expected_range

    # 4. 验证分项节能量范围
    assert result["chiller_saving_min"] < result["chiller_saving_max"]
    assert result["pump_saving_min"] < result["pump_saving_max"]
    assert result["tower_saving_min"] < result["tower_saving_max"]
    assert result["total_saving_min"] < result["total_saving_max"]

    # 5. 验证向后兼容字段
    assert result["energy_saving_rate"] == min_rate  # 旧字段=下限
    assert result["chiller_saving"] == result["chiller_saving_min"]

    # 6. 验证元数据
    assert result["calculation_method"] == "dual_sheet"
    assert result["completeness"] == 1.0


def test_range_with_secondary_pump_template(tmp_path):
    """测试二次泵模板的范围计算"""

    filled_data = {
        "station_type": "secondary_pump",
        "project_region": "华北",
        "monthly_data": [
            {
                "month": i,
                "total_energy": 120 + i * 15,
                "chiller_supply_temp": 7.5,
                "cooling_pump_freq": 45.0,
                "cooling_water_temp_diff": 5.0,
                "freezing_pump_freq": 45.0,
                "freezing_water_temp_diff": 5.0,
                "cooling_tower_outlet_temp": 28.0,
            }
            for i in range(1, 13)
        ],
        "_metadata": {"final_completeness": 1.0, "fill_count": 0}
    }

    filled_path = tmp_path / "filled_secondary.json"
    with open(filled_path, 'w', encoding='utf-8') as f:
        json.dump(filled_data, f)

    calculator = ExcelCalculator()
    result_path = tmp_path / "result_secondary.json"

    calculator.calculate(str(filled_path), str(result_path))

    with open(result_path) as f:
        result = json.load(f)

    # 验证二次泵版同样支持范围计算
    assert "energy_saving_rate_range" in result
    assert result["calculation_method"] == "dual_sheet"
```

### 步骤2: 运行端到端测试

```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/e2e/test_energy_saving_range_workflow.py -v -s
```

**预期**: PASS - 2个测试全部通过

### 步骤3: 清理临时文件

```bash
rm -rf tmp/*
```

### 步骤4: 提交端到端测试

```bash
git add tests/e2e/test_energy_saving_range_workflow.py
git commit -m "test: add end-to-end tests for range calculation workflow

- 测试完整的范围计算工作流
- 测试二次泵模板的范围计算
- 验证范围合理性和向后兼容性

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## 验收标准

### 功能验收

- [ ] CellMapping 支持 get_sheet_name("upper"/"lower")
- [ ] ExcelCalculator 能计算上限和下限两个sheet
- [ ] 返回结果包含 energy_saving_rate_min/max/range
- [ ] UI 展示节能率范围而非单一值
- [ ] 向后兼容，原有单一值字段仍可用
- [ ] 文档已更新，说明双sheet计算机制

### 测试验收

- [ ] test_cell_mapping_multi_sheet.py 单元测试通过（5个）
- [ ] test_excel_calculator_range.py 单元测试通过（3个）
- [ ] test_energy_saving_range_workflow.py 端到端测试通过（2个）
- [ ] 现有测试保持通过（向后兼容验证）

### 代码质量

- [ ] 代码遵循 DRY 原则（复用 CellMapping）
- [ ] 向后兼容（energy_saving_rate = min值）
- [ ] 错误处理完善
- [ ] 提交信息符合规范

---

## 重要注意事项

1. **向后兼容性**：
   - 保留原有的 `energy_saving_rate` 字段，值为下限（保守估计）
   - 旧版数据不包含范围字段时，UI 仍显示单一值
   - 确保现有测试和功能不受影响

2. **Sheet名称准确性**：
   - 上限：`"【1】按冷站电量数据-上限 "`（注意末尾空格）
   - 下限：`"【2】按冷站电量数据-下限"`（无末尾空格）
   - 必须与Excel模板的实际sheet名称完全一致

3. **范围合理性验证**：
   - 上限值必须大于下限值
   - 两者都应在 0-100% 之间
   - 添加断言确保数据合理性

4. **性能考虑**：
   - 双sheet计算会增加计算时间（约2倍）
   - 可以考虑并行计算上限和下限（可选优化）
   - 当前串行计算已足够快（formulas 库高效）

5. **UI用户体验**：
   - 明确说明上限和下限的含义
   - 避免用户混淆"范围"和"误差"
   - 提供清晰的帮助文本

---

## 后续优化方向

1. **可视化增强**：
   - 使用柱状图展示范围（error bar）
   - 分项节能量使用堆叠柱状图

2. **置信度评估**：
   - 基于数据完整性调整范围宽度
   - 数据越完整，范围越窄（更准确）

3. **并行计算**：
   - 使用 multiprocessing 并行计算上限和下限
   - 减少双sheet计算时间

4. **自定义范围**：
   - 允许用户选择只计算上限或下限
   - 提供"快速模式"（仅下限）和"完整模式"（上限+下限）
