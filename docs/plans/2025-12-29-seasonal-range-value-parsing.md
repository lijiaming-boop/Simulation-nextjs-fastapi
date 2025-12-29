# 季节性范围值解析实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为数据提取skill添加季节性范围值解析功能，根据月份智能选择范围值的上限/下限/平均值

**Architecture:** 增强 `parse_value()` 函数，添加季节判断逻辑和字段类型感知能力，使其能够根据月份和字段类型智能地从范围值中提取最合适的数值

**Tech Stack:** Python 3, pandas, regex, pytest

**背景:**
- 当前实现：所有范围值统一取平均值（如 "30-50Hz" → 40）
- 新需求：根据月份和字段类型智能选择
  - **水泵频率/温差**：冬季取下限，夏季取上限，春秋取平均
  - **供水温度**：冬季取上限，夏季取下限，春秋取平均（与上述相反）

**季节定义:**
- 冬季：12, 1, 2月
- 春季：3, 4, 5月
- 夏季：6, 7, 8月
- 秋季：9, 10, 11月

**影响范围:**
- 核心文件：`.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py`
- 文档文件：`.claude/skills/extract-and-check-data/SKILL.md`
- 测试文件：`tests/unit/test_extract_and_check.py`

---

## Task 1: 添加季节判断和范围值解析工具函数

**Files:**
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:23-60`

**Step 1: Write the failing test for seasonal utilities**

在 `tests/unit/test_extract_and_check.py` 末尾添加：

```python
def test_get_season():
    """测试季节判断函数"""
    from extract_and_check_data import get_season

    # 冬季
    assert get_season(12) == 'winter'
    assert get_season(1) == 'winter'
    assert get_season(2) == 'winter'

    # 春季
    assert get_season(3) == 'spring'
    assert get_season(4) == 'spring'
    assert get_season(5) == 'spring'

    # 夏季
    assert get_season(6) == 'summer'
    assert get_season(7) == 'summer'
    assert get_season(8) == 'summer'

    # 秋季
    assert get_season(9) == 'autumn'
    assert get_season(10) == 'autumn'
    assert get_season(11) == 'autumn'


def test_parse_range_value_seasonal():
    """测试季节性范围值解析"""
    from extract_and_check_data import parse_range_value_seasonal

    # 水泵频率 - 冬季取下限
    assert parse_range_value_seasonal("30-50", 1, 'cooling_pump_freq') == 30.0

    # 水泵频率 - 夏季取上限
    assert parse_range_value_seasonal("30-50", 7, 'cooling_pump_freq') == 50.0

    # 水泵频率 - 春季取平均
    assert parse_range_value_seasonal("30-50", 4, 'cooling_pump_freq') == 40.0

    # 供水温度 - 冬季取上限（相反）
    assert parse_range_value_seasonal("7-10", 1, 'chiller_supply_temp') == 10.0

    # 供水温度 - 夏季取下限（相反）
    assert parse_range_value_seasonal("7-10", 7, 'chiller_supply_temp') == 7.0

    # 供水温度 - 秋季取平均
    assert parse_range_value_seasonal("7-10", 10, 'chiller_supply_temp') == 8.5

    # 温差 - 冬季取下限
    assert parse_range_value_seasonal("3-5", 2, 'cooling_water_temp_diff') == 3.0

    # 温差 - 夏季取上限
    assert parse_range_value_seasonal("3-5", 8, 'freezing_water_temp_diff') == 5.0
```

**Step 2: Run test to verify it fails**

```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_extract_and_check.py::test_get_season -v
pytest tests/unit/test_extract_and_check.py::test_parse_range_value_seasonal -v
```

Expected: FAIL with "ImportError: cannot import name 'get_season'"

**Step 3: Implement seasonal utility functions**

在 `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py` 的 `parse_value()` 函数之前（第23行左右）添加：

```python
def get_season(month: int) -> str:
    """根据月份判断季节

    Args:
        month: 月份 (1-12)

    Returns:
        季节字符串: 'winter', 'spring', 'summer', 'autumn'
    """
    if month in [12, 1, 2]:
        return 'winter'
    elif month in [3, 4, 5]:
        return 'spring'
    elif month in [6, 7, 8]:
        return 'summer'
    else:  # 9, 10, 11
        return 'autumn'


def parse_range_value_seasonal(value_str: str, month: int, field_name: str) -> float:
    """根据季节和字段类型智能解析范围值

    Args:
        value_str: 范围值字符串 (如 "30-50", "7-10℃")
        month: 月份 (1-12)
        field_name: 字段名称

    Returns:
        解析后的数值

    策略:
        - 水泵频率/温差: 冬季取下限, 夏季取上限, 春秋取平均
        - 供水温度: 冬季取上限, 夏季取下限, 春秋取平均 (相反)
    """
    # 提取范围值
    range_match = re.search(r'(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)', value_str)
    if not range_match:
        return None

    start = float(range_match.group(1))
    end = float(range_match.group(2))

    # 判断季节
    season = get_season(month)

    # 供水温度字段使用相反逻辑
    is_supply_temp = 'supply_temp' in field_name

    if season == 'winter':
        return end if is_supply_temp else start
    elif season == 'summer':
        return start if is_supply_temp else end
    else:  # spring or autumn
        return (start + end) / 2
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_extract_and_check.py::test_get_season -v
pytest tests/unit/test_extract_and_check.py::test_parse_range_value_seasonal -v
```

Expected: PASS (all tests pass)

**Step 5: Commit**

```bash
git add tests/unit/test_extract_and_check.py
git add .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py
git commit -m "feat: add seasonal range value parsing utilities"
```

---

## Task 2: 重构 parse_value() 函数以支持字段感知和月份感知

**Files:**
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:23-60`

**Step 1: Write test for enhanced parse_value()**

在 `tests/unit/test_extract_and_check.py` 末尾添加：

```python
def test_parse_value_with_season_and_field():
    """测试增强的 parse_value() 函数（支持季节和字段类型）"""
    from extract_and_check_data import parse_value

    # 测试水泵频率范围值 - 冬季
    result = parse_value("30-50Hz", month=1, field_name='cooling_pump_freq')
    assert result == 30.0

    # 测试水泵频率范围值 - 夏季
    result = parse_value("30-50Hz", month=7, field_name='cooling_pump_freq')
    assert result == 50.0

    # 测试供水温度范围值 - 冬季（相反逻辑）
    result = parse_value("7-10℃", month=1, field_name='chiller_supply_temp')
    assert result == 10.0

    # 测试供水温度范围值 - 夏季（相反逻辑）
    result = parse_value("7-10℃", month=7, field_name='chiller_supply_temp')
    assert result == 7.0

    # 测试温差范围值 - 春季（平均值）
    result = parse_value("3-5℃", month=4, field_name='cooling_water_temp_diff')
    assert result == 4.0

    # 测试非范围值（单一数值）- 应该不受季节影响
    result = parse_value("45Hz", month=1, field_name='cooling_pump_freq')
    assert result == 45.0

    result = parse_value("7.5℃", month=7, field_name='chiller_supply_temp')
    assert result == 7.5

    # 测试向后兼容 - 没有月份参数时默认取平均值
    result = parse_value("30-50")
    assert result == 40.0


def test_parse_value_edge_cases():
    """测试 parse_value() 边界情况"""
    from extract_and_check_data import parse_value

    # 缺失值
    assert parse_value(None) is None
    assert parse_value("") is None
    assert parse_value("nan") is None
    assert parse_value("/") is None

    # 工频格式
    result = parse_value("工频50HZ", month=1, field_name='cooling_pump_freq')
    assert result == 50.0
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_extract_and_check.py::test_parse_value_with_season_and_field -v
pytest tests/unit/test_extract_and_check.py::test_parse_value_edge_cases -v
```

Expected: FAIL with "TypeError: parse_value() got an unexpected keyword argument 'month'"

**Step 3: Refactor parse_value() function**

修改 `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py` 中的 `parse_value()` 函数（约第23-60行）：

```python
def parse_value(value, month=None, field_name=None):
    """解析文本值为数值，支持季节性范围值处理

    Args:
        value: 单元格值
        month: 月份 (1-12)，用于季节性范围值解析
        field_name: 字段名称，用于判断是否需要相反逻辑

    Returns:
        解析后的数值，或 None
    """
    if pd.isna(value):
        return None

    value_str = str(value).strip()

    if not value_str or value_str.lower() in ['nan', 'none', '无', '/']:
        return None

    try:
        return float(value_str)
    except ValueError:
        pass

    # 处理范围格式 - 如果提供了月份和字段名，使用季节性解析
    range_match = re.search(r'(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)', value_str)
    if range_match:
        if month is not None and field_name is not None:
            # 使用季节性解析
            return parse_range_value_seasonal(value_str, month, field_name)
        else:
            # 向后兼容：默认取平均值
            start = float(range_match.group(1))
            end = float(range_match.group(2))
            return (start + end) / 2

    # 处理频率格式
    freq_match = re.search(r'(\d+\.?\d*)\s*(?:Hz|HZ|hz)', value_str)
    if freq_match:
        return float(freq_match.group(1))

    # 处理温度格式
    temp_match = re.search(r'(\d+\.?\d*)\s*(?:℃|°C|C)', value_str)
    if temp_match:
        return float(temp_match.group(1))

    # 提取第一个数字
    number_match = re.search(r'(\d+\.?\d*)', value_str)
    if number_match:
        return float(number_match.group(1))

    return None
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_extract_and_check.py::test_parse_value_with_season_and_field -v
pytest tests/unit/test_extract_and_check.py::test_parse_value_edge_cases -v
```

Expected: PASS (all tests pass)

**Step 5: Verify existing tests still pass (regression check)**

```bash
pytest tests/unit/test_extract_and_check.py -v
```

Expected: PASS (all tests including old ones still pass)

**Step 6: Commit**

```bash
git add tests/unit/test_extract_and_check.py
git add .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py
git commit -m "refactor: enhance parse_value with seasonal and field-aware logic"
```

---

## Task 3: 更新数据提取流程以传递月份和字段名参数

**Files:**
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:298-336`

**Step 1: Write integration test for seasonal extraction**

在 `tests/unit/test_extract_and_check.py` 末尾添加：

```python
def test_extract_with_seasonal_range_values():
    """测试完整提取流程中的季节性范围值解析（集成测试）"""
    from extract_and_check_data import extract_and_check_data
    from unittest.mock import patch, MagicMock
    import pandas as pd
    import tempfile

    # 创建模拟的 DataFrame，包含范围值数据
    # 假设：1月（冬季）的水泵频率写的是 "30-50Hz"
    mock_df = pd.DataFrame([
        ['月份'] + ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
        ['冷却泵运行频率'] + ['30-50Hz'] * 12,  # 所有月份都是范围值
        ['冷机供水温度'] + ['7-10℃'] * 12,     # 所有月份都是范围值
        ['冷却侧供回水温差'] + ['3-5℃'] * 12,   # 所有月份都是范围值
    ])

    # Mock Excel 读取
    with patch('pandas.ExcelFile') as mock_excel:
        mock_xls = MagicMock()
        mock_xls.sheet_names = ['冷站', '项目总体情况']
        mock_excel.return_value = mock_xls

        with patch('pandas.read_excel', return_value=mock_df):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                output_path = Path(f.name)

            try:
                extract_and_check_data('dummy.xlsx', str(output_path))

                # 读取结果
                with open(output_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)

                monthly_data = result['extracted_data']['monthly_data']

                # 验证1月（冬季）- 水泵频率取下限，供水温度取上限，温差取下限
                jan_data = monthly_data[0]  # month=1
                assert jan_data['cooling_pump_freq'] == 30.0  # 下限
                assert jan_data['chiller_supply_temp'] == 10.0  # 上限（相反）
                assert jan_data['cooling_water_temp_diff'] == 3.0  # 下限

                # 验证7月（夏季）- 水泵频率取上限，供水温度取下限，温差取上限
                jul_data = monthly_data[6]  # month=7
                assert jul_data['cooling_pump_freq'] == 50.0  # 上限
                assert jul_data['chiller_supply_temp'] == 7.0  # 下限（相反）
                assert jul_data['cooling_water_temp_diff'] == 5.0  # 上限

                # 验证4月（春季）- 所有范围值取平均
                apr_data = monthly_data[3]  # month=4
                assert apr_data['cooling_pump_freq'] == 40.0  # 平均
                assert apr_data['chiller_supply_temp'] == 8.5  # 平均
                assert apr_data['cooling_water_temp_diff'] == 4.0  # 平均

            finally:
                if output_path.exists():
                    output_path.unlink()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_extract_and_check.py::test_extract_with_seasonal_range_values -v
```

Expected: FAIL (因为当前的提取流程还没有传递 month 和 field_name 参数)

**Step 3: Update extraction loop to pass month and field_name**

修改 `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py` 中的月度数据提取循环（约第298-336行）：

找到这段代码：
```python
for field in ['total_energy', 'chiller_supply_temp', 'cooling_pump_freq',
             'cooling_water_temp_diff', 'freezing_pump_freq',
             'freezing_water_temp_diff', 'cooling_tower_outlet_temp']:
    if field in data_rows:
        row_idx = data_rows[field]
        if row_idx < len(df):
            # 根据字段类型使用不同的列起始位置
            if field == 'total_energy':
                # 用电情况：使用 energy_col_start
                month_col_idx = energy_col_start + (month - 1)
            else:
                # 设备运行规律：使用 equipment_col_start
                month_col_idx = equipment_col_start + (month - 1)

            # 确保列索引在有效范围内
            if month_col_idx < len(df.columns):
                value = df.iloc[row_idx, month_col_idx]
                parsed = parse_value(value)  # ← 这里需要修改
                month_record[field] = parsed
                if field == 'total_energy' and parsed is not None:
                    valid_energy_count += 1
```

替换为：
```python
for field in ['total_energy', 'chiller_supply_temp', 'cooling_pump_freq',
             'cooling_water_temp_diff', 'freezing_pump_freq',
             'freezing_water_temp_diff', 'cooling_tower_outlet_temp']:
    if field in data_rows:
        row_idx = data_rows[field]
        if row_idx < len(df):
            # 根据字段类型使用不同的列起始位置
            if field == 'total_energy':
                # 用电情况：使用 energy_col_start
                month_col_idx = energy_col_start + (month - 1)
            else:
                # 设备运行规律：使用 equipment_col_start
                month_col_idx = equipment_col_start + (month - 1)

            # 确保列索引在有效范围内
            if month_col_idx < len(df.columns):
                value = df.iloc[row_idx, month_col_idx]
                # 传递月份和字段名以支持季节性范围值解析
                parsed = parse_value(value, month=month, field_name=field)
                month_record[field] = parsed
                if field == 'total_energy' and parsed is not None:
                    valid_energy_count += 1
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_extract_and_check.py::test_extract_with_seasonal_range_values -v
```

Expected: PASS

**Step 5: Run all unit tests (regression check)**

```bash
pytest tests/unit/test_extract_and_check.py -v
```

Expected: PASS (all tests pass)

**Step 6: Commit**

```bash
git add tests/unit/test_extract_and_check.py
git add .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py
git commit -m "feat: integrate seasonal range parsing into extraction pipeline"
```

---

## Task 4: 更新 SKILL.md 文档

**Files:**
- Modify: `.claude/skills/extract-and-check-data/SKILL.md:35-58`

**Step 1: Update documentation to reflect seasonal parsing**

修改 `.claude/skills/extract-and-check-data/SKILL.md` 的"数据处理要点"部分（第35-58行）：

找到"3. **文本解析**:"部分，将其替换为：

```markdown
3. **文本解析**:
   - **频率字段**: 可能是 "工频50HZ"、"45Hz"、"50" 等格式，提取数值部分
   - **温度/温差字段**: 可能是 "3-5℃"、"4℃"、"4.5"、"7-10度" 等格式
   - **范围值智能解析**: 根据月份和字段类型智能选择数值
     - **水泵频率** (`cooling_pump_freq`, `freezing_pump_freq`):
       - 冬季 (12, 1, 2月): 取下限值（设备低负荷运行）
       - 夏季 (6, 7, 8月): 取上限值（设备高负荷运行）
       - 春秋 (3-5, 9-11月): 取平均值（设备中等负荷）
     - **温差字段** (`cooling_water_temp_diff`, `freezing_water_temp_diff`):
       - 冬季: 取下限值（温差较小）
       - 夏季: 取上限值（温差较大）
       - 春秋: 取平均值
     - **供水温度** (`chiller_supply_temp`):
       - 冬季: 取上限值（冬季供水温度较高）
       - 夏季: 取下限值（夏季供水温度较低）
       - 春秋: 取平均值
   - **示例**:
     - "30-50Hz" + 1月（冬季）+ cooling_pump_freq → 30
     - "30-50Hz" + 7月（夏季）+ cooling_pump_freq → 50
     - "7-10℃" + 1月（冬季）+ chiller_supply_temp → 10
     - "7-10℃" + 7月（夏季）+ chiller_supply_temp → 7
     - "3-5℃" + 4月（春季）+ cooling_water_temp_diff → 4.0
```

**Step 2: Verify documentation is clear and accurate**

人工检查文档：
- 确保季节定义清晰
- 确保逻辑说明准确
- 确保示例覆盖所有场景

**Step 3: Commit**

```bash
git add .claude/skills/extract-and-check-data/SKILL.md
git commit -m "docs: document seasonal range value parsing logic"
```

---

## Task 5: 添加实际调研表的端到端测试

**Files:**
- Create: `tests/integration/test_seasonal_range_parsing_e2e.py`

**Step 1: Write end-to-end test with real Excel file**

创建 `tests/integration/test_seasonal_range_parsing_e2e.py`：

```python
#!/usr/bin/env python3
"""
季节性范围值解析的端到端测试
使用真实的调研表文件验证季节性解析功能
"""

import pytest
import json
import tempfile
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))


@pytest.mark.skipif(
    not (project_root / "00_sample/示例调研表").exists(),
    reason="示例调研表目录不存在"
)
def test_seasonal_parsing_with_real_excel():
    """使用真实调研表测试季节性范围值解析"""
    from extract_and_check_data import extract_and_check_data

    # 查找包含范围值的示例调研表
    sample_dir = project_root / "00_sample/示例调研表"
    excel_files = list(sample_dir.glob("*.xlsx"))

    if not excel_files:
        pytest.skip("未找到示例调研表文件")

    # 使用第一个调研表进行测试
    excel_path = excel_files[0]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = Path(f.name)

    try:
        # 执行提取
        extract_and_check_data(str(excel_path), str(output_path))

        # 读取结果
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # 验证结果结构
        assert 'extracted_data' in result
        assert 'quality_report' in result

        monthly_data = result['extracted_data']['monthly_data']
        assert len(monthly_data) == 12

        # 验证季节性解析是否生效（通过检查冬夏季数据差异）
        # 注意：只有当调研表中包含范围值时，这个差异才会显现
        # 这里只做结构验证，具体数值验证在单元测试中完成

        for month_record in monthly_data:
            assert 'month' in month_record
            assert 1 <= month_record['month'] <= 12

        print(f"✅ 季节性解析端到端测试通过: {excel_path.name}")

    finally:
        if output_path.exists():
            output_path.unlink()


def test_seasonal_parsing_consistency():
    """验证季节性解析的一致性（不同月份的相同范围值应该解析为不同数值）"""
    from extract_and_check_data import parse_range_value_seasonal

    # 水泵频率范围值在不同季节应该有不同结果
    winter_result = parse_range_value_seasonal("30-50", 1, 'cooling_pump_freq')
    summer_result = parse_range_value_seasonal("30-50", 7, 'cooling_pump_freq')
    spring_result = parse_range_value_seasonal("30-50", 4, 'cooling_pump_freq')

    # 冬夏春三季结果应该不同
    assert winter_result != summer_result
    assert winter_result != spring_result
    assert summer_result != spring_result

    # 验证数值符合预期
    assert winter_result == 30.0  # 下限
    assert summer_result == 50.0  # 上限
    assert spring_result == 40.0  # 平均
```

**Step 2: Run E2E test**

```bash
pytest tests/integration/test_seasonal_range_parsing_e2e.py -v -s
```

Expected: PASS (如果有示例调研表) 或 SKIP (如果没有示例文件)

**Step 3: Commit**

```bash
git add tests/integration/test_seasonal_range_parsing_e2e.py
git commit -m "test: add e2e tests for seasonal range parsing"
```

---

## Task 6: 运行完整测试套件验证所有功能

**Files:**
- Test: `tests/unit/test_extract_and_check.py`
- Test: `tests/integration/test_seasonal_range_parsing_e2e.py`

**Step 1: Run all unit tests**

```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/unit/test_extract_and_check.py -v
```

Expected: PASS (all unit tests pass)

**Step 2: Run all integration tests**

```bash
pytest tests/integration/test_seasonal_range_parsing_e2e.py -v
```

Expected: PASS or SKIP

**Step 3: Run complete test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass (existing + new tests)

**Step 4: Verify with specific test cases**

手动验证几个关键场景：

```bash
# 测试季节判断
pytest tests/unit/test_extract_and_check.py::test_get_season -v

# 测试范围值解析
pytest tests/unit/test_extract_and_check.py::test_parse_range_value_seasonal -v

# 测试增强的 parse_value
pytest tests/unit/test_extract_and_check.py::test_parse_value_with_season_and_field -v

# 测试集成流程
pytest tests/unit/test_extract_and_check.py::test_extract_with_seasonal_range_values -v
```

Expected: All PASS

---

## Task 7: 更新 CLAUDE.md 项目文档

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Document the new feature**

在 `CLAUDE.md` 的"数据提取或质量检查逻辑"部分添加说明：

找到"### 场景1：调整数据提取或质量检查逻辑"部分（约第220行），在其后添加：

```markdown
**季节性范围值解析**：

系统支持根据月份和字段类型智能解析范围值（如 "30-50Hz"、"7-10℃"）：

**解析策略**：
- **水泵频率/温差字段**：冬季取下限，夏季取上限，春秋取平均
- **供水温度字段**：冬季取上限，夏季取下限，春秋取平均（相反逻辑）

**季节定义**：
- 冬季：12, 1, 2月
- 春季：3, 4, 5月
- 夏季：6, 7, 8月
- 秋季：9, 10, 11月

**实现位置**：
- 核心函数：`.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py::parse_range_value_seasonal()`
- 测试文件：`tests/unit/test_extract_and_check.py`

**示例**：
| 原始值 | 月份 | 字段类型 | 提取结果 | 原因 |
|--------|------|----------|---------|------|
| "30-50Hz" | 1月 | cooling_pump_freq | 30 | 冬季取下限 |
| "30-50Hz" | 7月 | cooling_pump_freq | 50 | 夏季取上限 |
| "7-10℃" | 1月 | chiller_supply_temp | 10 | 冬季取上限（相反） |
| "7-10℃" | 7月 | chiller_supply_temp | 7 | 夏季取下限（相反） |
| "3-5℃" | 4月 | cooling_water_temp_diff | 4.0 | 春季取平均 |
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add seasonal range parsing to project documentation"
```

---

## Task 8: 最终验证和清理

**Step 1: Run complete test suite one final time**

```bash
export PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving:$PYTHONPATH
pytest tests/ -v
```

Expected: All tests pass

**Step 2: Verify skill can be called successfully**

```bash
# 如果有示例调研表，测试完整流程
export ANTHROPIC_API_KEY='your-api-key'
python .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py \
    00_sample/示例调研表/某个调研表.xlsx \
    tmp/test_seasonal_output.json
```

Expected: 成功输出包含季节性解析数据的 JSON 文件

**Step 3: Review all commits**

```bash
git log --oneline -8
```

Expected: 看到所有8个相关提交

**Step 4: Clean up temporary files**

```bash
rm -f tmp/test_seasonal_output.json
```

---

## 验收标准

**功能验收**：
- ✅ 季节判断函数正确识别12个月份对应的季节
- ✅ 范围值解析正确处理水泵频率/温差/供水温度三类字段
- ✅ 提取流程成功集成季节性解析逻辑
- ✅ 向后兼容：没有月份参数时仍默认取平均值

**测试覆盖**：
- ✅ 单元测试覆盖所有工具函数（get_season, parse_range_value_seasonal）
- ✅ 单元测试覆盖增强的 parse_value() 函数
- ✅ 集成测试验证完整提取流程
- ✅ 端到端测试验证真实调研表场景
- ✅ 所有现有测试仍然通过（无回归）

**文档完整**：
- ✅ SKILL.md 详细说明季节性解析逻辑
- ✅ CLAUDE.md 提供开发者指南
- ✅ 代码注释清晰，函数 docstring 完整

**代码质量**：
- ✅ 遵循 DRY 原则（工具函数复用）
- ✅ 遵循 YAGNI 原则（只实现需要的功能）
- ✅ 遵循 TDD 流程（先写测试，后写代码）
- ✅ 每个功能点独立提交

---

## 潜在风险和缓解措施

**风险1：现有数据提取结果发生变化**
- 缓解：添加回归测试，确保非范围值的解析结果不变
- 缓解：向后兼容设计（没有月份参数时保持原有行为）

**风险2：季节定义不符合实际气候**
- 缓解：季节定义基于中国通用的四季划分
- 缓解：如需调整，只需修改 `get_season()` 函数

**风险3：某些字段不适合季节性解析**
- 缓解：只对频率、温差、供水温度三类字段应用季节逻辑
- 缓解：其他字段仍使用默认平均值

**风险4：用户期望与实际解析结果不符**
- 缓解：在 SKILL.md 中详细说明解析策略和示例
- 缓解：提供清晰的文档供用户理解逻辑

---

## 后续优化建议

1. **可配置化**：将季节定义和解析策略配置化，支持不同地区的季节划分
2. **日志记录**：添加调试日志，记录范围值的解析过程（原始值→季节→选择策略→结果）
3. **UI 提示**：在前端展示时标注哪些数据是通过季节性解析得到的
4. **更精细的策略**：考虑项目地区的气候特征（如华南vs东北的季节差异）

---

## 相关技能

本计划涉及以下 superpowers 技能：
- @superpowers:test-driven-development - 所有任务都遵循 TDD 流程
- @superpowers:systematic-debugging - 如果测试失败，使用系统性调试
- @superpowers:verification-before-completion - Task 6 和 Task 8 验证完成
