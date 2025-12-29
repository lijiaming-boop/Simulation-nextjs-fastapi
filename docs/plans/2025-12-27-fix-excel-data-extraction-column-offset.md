# 修复 Excel 数据提取月份列错位问题 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复调研表数据提取中"用电情况"和"设备运行规律"月份列错位导致数据提取错误的bug

**Architecture:**
- 根源问题：调研表中"设备运行规律"部分比"用电情况统计"部分多一列"备注"列（C列），导致月份列向右偏移一列
- 当前代码使用硬编码 `month_col_start = 3`（D列）处理所有字段，导致用电情况（从C列开始）的数据被错位读取
- 解决方案：为每个数据行单独判断月份列起始位置，根据该行的实际列结构动态确定起始列

**Tech Stack:** Python, pandas, openpyxl, pytest

---

## Task 1: 排查和验证问题

**Files:**
- Read: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:240`
- Create: `scripts/verify_column_offset_bug.py`

**Step 1: 创建问题验证脚本**

创建脚本以清晰展示问题：

```python
#!/usr/bin/env python3
"""验证月份列错位问题"""

import openpyxl
import pandas as pd

def verify_column_offset():
    """验证调研表中月份列的错位问题"""
    file_path = '00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx'

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb['冷站']

    print("=== 设备运行规律（第32行 - 月份标题）===")
    print("月份列起始位置：")
    for col_idx in range(1, 15):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        value = ws[f'{col_letter}32'].value
        if value and '月' in str(value):
            print(f"  {col_letter}32 (索引{col_idx-1}): {value}")

    print("\n第34行（冷机供水温度）数据列：")
    for col_idx in range(3, 15):  # C列开始
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        value = ws[f'{col_letter}34'].value
        print(f"  {col_letter}34: {value}")

    print("\n=== 用电情况统计（第42行 - 月份标题）===")
    print("月份列起始位置：")
    for col_idx in range(1, 15):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        value = ws[f'{col_letter}42'].value
        if value and '月' in str(value):
            print(f"  {col_letter}42 (索引{col_idx-1}): {value}")

    print("\n第44行（冷站用电量）数据列：")
    for col_idx in range(2, 15):  # B列开始
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        value = ws[f'{col_letter}44'].value
        print(f"  {col_letter}44: {value}")

    print("\n=== 问题总结 ===")
    print("❌ 设备运行规律：1月数据在 D 列（索引3）")
    print("❌ 用电情况统计：1月数据在 C 列（索引2）")
    print("❌ 当前代码使用 month_col_start=3（D列）会导致用电数据错位：")
    print("   - 漏读1月数据（C列）")
    print("   - 2月数据（D列）被错当成1月")
    print("   - 后续月份全部向左错位一个月")

if __name__ == '__main__':
    verify_column_offset()
```

**Step 2: 运行验证脚本**

Run: `python scripts/verify_column_offset_bug.py`
Expected: 清晰展示两个部分的月份列起始位置不同（D列 vs C列）

**Step 3: 提交验证脚本**

```bash
git add scripts/verify_column_offset_bug.py
git commit -m "test: add script to verify column offset bug

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: 编写失败测试（TDD Red Phase）

**Files:**
- Create: `tests/unit/test_extract_column_offset.py`

**Step 1: 编写测试用例验证提取的1月数据正确性**

```python
"""测试数据提取中月份列对齐问题"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pathlib import Path
import pytest


def test_extract_january_data_alignment():
    """测试1月数据提取的正确性 - 验证用电情况和设备运行规律的月份对齐

    根本问题：
    - 设备运行规律：1月从D列开始（有备注列C）
    - 用电情况统计：1月从C列开始（无备注列）

    预期：
    - 1月冷站用电量应该是 26.16 万kWh（C44单元格）
    - 1月冷机供水温度应该是 8°C（D34单元格）
    """
    from pathlib import Path
    import sys

    # 导入提取函数
    skill_script_path = Path(__file__).parent.parent.parent / '.claude/skills/extract-and-check-data/scripts'
    sys.path.insert(0, str(skill_script_path))

    from extract_and_check_data import extract_data_from_excel

    # 使用齐全的示例调研表
    survey_path = '00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx'

    result = extract_data_from_excel(survey_path)

    # 验证没有错误
    assert 'error' not in result or not result['error'], f"提取失败: {result.get('message')}"

    monthly_data = result['monthly_data']
    assert len(monthly_data) == 12, "应该提取12个月的数据"

    # 验证1月数据
    jan_data = monthly_data[0]
    assert jan_data['month'] == 1

    # ✅ 核心验证：1月冷站用电量应该是 26.16（C44单元格）
    # 当前 bug 会读取到 19.94（2月的数据，D44单元格）
    assert jan_data['total_energy'] == pytest.approx(26.16, abs=0.01), \
        f"1月冷站用电量错误: 期望 26.16, 实际 {jan_data['total_energy']}"

    # ✅ 验证1月冷机供水温度应该是 8°C（D34单元格）
    assert jan_data['chiller_supply_temp'] == pytest.approx(8.0, abs=0.1), \
        f"1月冷机供水温度错误: 期望 8.0, 实际 {jan_data['chiller_supply_temp']}"

    # 验证2月数据（作为对照）
    feb_data = monthly_data[1]
    assert feb_data['month'] == 2

    # ✅ 2月冷站用电量应该是 19.94（D44单元格）
    assert feb_data['total_energy'] == pytest.approx(19.94, abs=0.01), \
        f"2月冷站用电量错误: 期望 19.94, 实际 {feb_data['total_energy']}"


def test_extract_december_data_presence():
    """测试12月数据提取 - 验证不会漏掉最后一个月

    由于错位问题：
    - 设备运行规律只有11个月（D-N列，1-11月，缺12月）
    - 用电情况统计有完整12个月（C-N列，1-12月）

    预期：
    - 12月应该有用电量数据 28.64 万kWh（N44单元格）
    - 12月的设备运行规律数据可能缺失（因为表格只到11月）
    """
    from pathlib import Path
    import sys

    skill_script_path = Path(__file__).parent.parent.parent / '.claude/skills/extract-and-check-data/scripts'
    sys.path.insert(0, str(skill_script_path))

    from extract_and_check_data import extract_data_from_excel

    survey_path = '00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx'

    result = extract_data_from_excel(survey_path)
    monthly_data = result['monthly_data']

    # 验证12月数据
    dec_data = monthly_data[11]
    assert dec_data['month'] == 12

    # ✅ 12月应该有用电量数据 28.64 万kWh（N44单元格）
    assert dec_data['total_energy'] == pytest.approx(28.64, abs=0.01), \
        f"12月冷站用电量错误: 期望 28.64, 实际 {dec_data['total_energy']}"
```

**Step 2: 运行测试确认失败**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_extract_column_offset.py -v`
Expected: FAIL - 1月用电量为 19.94（错误），期望 26.16

**Step 3: 提交失败测试**

```bash
git add tests/unit/test_extract_column_offset.py
git commit -m "test: add failing test for column offset bug

验证月份列错位导致的数据提取错误

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: 修复数据提取逻辑（TDD Green Phase）

**Files:**
- Modify: `.claude/skills/extract-and-check-data/scripts/extract_and_check_data.py:209-268`

**Step 1: 添加动态检测月份列起始位置的函数**

在 `find_row_by_keyword` 函数后添加（第176行后）：

```python
def detect_month_column_start(df, row_idx):
    """检测指定行的月份列起始位置

    通过在该行查找 '1月' 关键字来确定月份数据的起始列。
    这样可以处理不同部分的列结构差异：
    - 设备运行规律：月份从D列开始（有备注列C）
    - 用电情况统计：月份从C列开始（无备注列）

    Args:
        df: DataFrame
        row_idx: 月份标题行的行号

    Returns:
        月份数据起始列索引（0-based），如果未找到则返回 None
    """
    if row_idx is None or row_idx >= len(df):
        return None

    # 在该行查找 '1月' 关键字
    row = df.iloc[row_idx]
    for col_idx in range(len(row)):
        cell_value = row.iloc[col_idx]
        if pd.notna(cell_value) and '1月' in str(cell_value):
            return col_idx

    return None
```

**Step 2: 修改提取逻辑以分别处理不同部分的列起始位置**

修改 `extract_data_from_excel` 函数中的数据提取部分（第209-268行）：

```python
    # 查找关键行
    row_mappings = {
        'chiller_supply_temp': ['冷机供水温度'],
        'cooling_pump_freq': ['冷却泵运行频率'],
        'cooling_water_temp_diff': ['冷却侧供回水温差'],
        'freezing_pump_freq': ['冷冻泵运行频率'],
        'freezing_water_temp_diff': ['冷冻侧供回水温差'],
        'cooling_tower_outlet_temp': ['冷却塔出水温度'],
        'total_energy': ['整个冷站', '万kWh']
    }

    # 从第30行开始查找设备运行规律部分的月份行
    equipment_month_row_idx = find_row_by_keyword(df, ['月份', '备注'], start_row=30, end_row=45)
    if equipment_month_row_idx is None:
        return {
            "error": True,
            "message": "未能识别调研表中的设备运行规律月度数据行,请确认上传了正确的文件"
        }

    # 检测设备运行规律部分的月份列起始位置
    equipment_col_start = detect_month_column_start(df, equipment_month_row_idx)
    if equipment_col_start is None:
        equipment_col_start = 3  # 默认 D 列

    # 查找用电情况统计部分的月份行（通常在设备运行规律之后）
    energy_month_row_idx = find_row_by_keyword(df, ['月份'], start_row=equipment_month_row_idx + 5, end_row=equipment_month_row_idx + 20)

    # 检测用电情况部分的月份列起始位置
    energy_col_start = None
    if energy_month_row_idx is not None:
        energy_col_start = detect_month_column_start(df, energy_month_row_idx)
    if energy_col_start is None:
        energy_col_start = 2  # 默认 C 列（用电情况通常从C列开始）

    # 查找各数据行
    data_rows = {}
    for key, keywords in row_mappings.items():
        # 设备运行规律字段：从设备运行规律部分开始查找
        if key != 'total_energy':
            row_idx = find_row_by_keyword(df, keywords, start_row=equipment_month_row_idx, end_row=equipment_month_row_idx + 15)
            if row_idx is not None:
                data_rows[key] = row_idx
        # 用电情况字段：从用电情况统计部分开始查找
        else:
            if energy_month_row_idx is not None:
                row_idx = find_row_by_keyword(df, keywords, start_row=energy_month_row_idx, end_row=energy_month_row_idx + 5)
                if row_idx is not None:
                    data_rows[key] = row_idx
            # 兜底：使用硬编码行号
            if 'total_energy' not in data_rows and len(df) > 43:
                data_rows['total_energy'] = 43  # 修正：用电量通常在第44行（索引43）

    # 提取月度数据
    monthly_data = []
    valid_energy_count = 0

    for month in range(1, 13):
        month_record = {
            "month": month,
            "total_energy": None,
            "chiller_supply_temp": None,
            "cooling_pump_freq": None,
            "cooling_water_temp_diff": None,
            "freezing_pump_freq": None,
            "freezing_water_temp_diff": None,
            "cooling_tower_outlet_temp": None
        }

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
                        parsed = parse_value(value)
                        month_record[field] = parsed
                        if field == 'total_energy' and parsed is not None:
                            valid_energy_count += 1

        monthly_data.append(month_record)

    # 注意：不再强制要求至少3个月数据，让质量检查报告来反馈数据完整性问题
    # 这样即使是空白模板也能返回提取结果和详细的质量报告

    return {
        "project_region": project_region,
        "monthly_data": monthly_data
    }
```

**Step 3: 运行测试确认通过**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_extract_column_offset.py -v`
Expected: PASS - 所有测试通过

**Step 4: 提交修复**

```bash
git add .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py
git commit -m "fix: correct column offset for energy vs equipment data

动态检测月份列起始位置,解决用电情况(C列起始)和设备运行规律(D列起始)的列错位问题

修复:
- 添加 detect_month_column_start() 函数动态检测月份列位置
- 分别处理设备运行规律部分(equipment_col_start)和用电情况部分(energy_col_start)
- 修正硬编码行号从46改为43（用电量数据行）

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: 运行集成测试验证完整流程

**Files:**
- Test: `tests/integration/test_sample_surveys_e2e.py`

**Step 1: 运行所有示例调研表的端到端测试**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving ANTHROPIC_API_KEY=test-key pytest tests/integration/test_sample_surveys_e2e.py -v -s`
Expected: 所有测试通过（或跳过需要真实API的测试）

**Step 2: 手动测试单个调研表提取**

Run:
```bash
python .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py \
  "00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx" \
  "tmp/test_extract_result.json"
```
Expected:
- 成功提取12个月数据
- 1月用电量为 26.16 万kWh
- 12月用电量为 28.64 万kWh

**Step 3: 检查输出JSON文件验证数据正确性**

Run: `cat tmp/test_extract_result.json | python -m json.tool | grep -A 10 '"month": 1'`
Expected: 1月数据中 total_energy 为 26.16

**Step 4: 清理临时文件**

Run: `rm -f tmp/test_extract_result.json`

---

## Task 5: 更新 Skill 文档

**Files:**
- Modify: `.claude/skills/extract-and-check-data/SKILL.md:35-49`

**Step 1: 在 SKILL.md 中添加列错位问题的说明**

在"数据处理要点"部分（第35-49行）添加新的条目：

```markdown
## 数据处理要点

1. **智能识别**:
   - 不要硬编码 Sheet 名称，利用 LLM 理解能力识别包含月度数据的工作表
   - **项目地区三级优先级提取**：
     1. **优先级1**: 从"冷站"sheet的"站房名称"字段推断（如"深圳工业园区F栋" → 华南）
     2. **优先级2**: 从调研表文件名推断（如"惠州光弘-调研表.xlsx" → 华南）
     3. **优先级3**: 从"项目总体情况"sheet扫描所有单元格匹配省市关键词
   - 支持识别全国主要城市：北上广深、省会城市、计划单列市等

2. **月份列对齐处理**:
   - **关键问题**: 调研表中"设备运行规律"和"用电情况统计"两部分的月份列起始位置不同
   - **设备运行规律**: 有"备注"列（C列），月份从D列开始（D=1月, E=2月, ..., N=11月）
   - **用电情况统计**: 无备注列，月份从C列开始（C=1月, D=2月, ..., N=12月）
   - **解决方案**: 通过查找"1月"关键字动态检测每个部分的月份列起始位置，避免硬编码列号
   - **重要性**: 列错位会导致1月数据缺失、所有月份数据向左错位一个月

3. **文本解析**:
   - 频率字段可能是 "工频50HZ"、"45Hz"、"50" 等格式，提取数值部分
   - 温差字段可能是 "3-5℃"、"4℃"、"4.5" 等格式，提取中间值或单一值
   - 例如: "工频50HZ" → 50, "3-5℃/4℃" → 4.5 (取区间中值或明确值)

4. **缺失值处理**: 空白单元格或无法解析的值标记为 `null`

5. **数据验证**: 如果 12 个月中有 < 3 个月有 total_energy 数据，返回错误
```

**Step 2: 提交文档更新**

```bash
git add .claude/skills/extract-and-check-data/SKILL.md
git commit -m "docs: document column offset handling in extraction

添加月份列对齐处理的说明,解释设备运行规律和用电情况统计的列结构差异

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: 更新项目文档

**Files:**
- Modify: `CLAUDE.md`

**Step 1: 在 CLAUDE.md 中添加已知问题和解决方案部分**

在文件末尾"相关文档"部分之前添加：

```markdown
## 已修复的关键问题

### 月份列错位问题（已修复）

**问题描述：**
调研表的"用电情况统计"和"设备运行规律"两个部分的列结构不同：
- **设备运行规律**：有"备注"列（C列），月份从D列开始（D=1月, E=2月, ..., N=11月）
- **用电情况统计**：无备注列，月份从C列开始（C=1月, D=2月, ..., N=12月）

早期实现使用硬编码 `month_col_start = 3`（D列）处理所有字段，导致：
- ❌ 用电情况的1月数据（C列）被漏读
- ❌ 2月数据（D列）被错当成1月
- ❌ 后续所有月份向左错位一个月
- ❌ 12月数据可能超出范围

**解决方案：**
- 添加 `detect_month_column_start()` 函数，通过查找"1月"关键字动态检测每个部分的月份列起始位置
- 分别处理设备运行规律（equipment_col_start）和用电情况（energy_col_start）
- 根据字段类型使用正确的列偏移量

**验证：**
- 测试文件：`tests/unit/test_extract_column_offset.py`
- 验证脚本：`scripts/verify_column_offset_bug.py`

**相关 Commit:**
- `fix: correct column offset for energy vs equipment data`
```

**Step 2: 提交项目文档更新**

```bash
git add CLAUDE.md
git commit -m "docs: document column offset bug and fix

记录月份列错位问题的根源、影响和解决方案

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: 最终验证和清理

**Files:**
- Test: All test files
- Clean: `tmp/` directory

**Step 1: 运行完整测试套件**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/ -v`
Expected: 所有测试通过

**Step 2: 清理临时文件**

Run: `rm -rf tmp/*`

**Step 3: 验证 git 状态**

Run: `git status`
Expected: Working tree clean（所有更改已提交）

**Step 4: 查看提交历史**

Run: `git log --oneline -10`
Expected: 看到本次修复的所有相关提交

---

## 验收标准

✅ **功能验证:**
- [ ] `test_extract_january_data_alignment` 测试通过（1月用电量 = 26.16）
- [ ] `test_extract_december_data_presence` 测试通过（12月用电量 = 28.64）
- [ ] 所有6个示例调研表的集成测试通过

✅ **代码质量:**
- [ ] 使用动态检测替代硬编码列号
- [ ] 添加详细注释解释列错位问题
- [ ] 代码符合项目现有风格

✅ **文档完整:**
- [ ] SKILL.md 更新说明列对齐处理逻辑
- [ ] CLAUDE.md 记录问题和解决方案
- [ ] 测试文件包含清晰的问题说明注释

✅ **测试覆盖:**
- [ ] 单元测试覆盖1月和12月边界情况
- [ ] 验证脚本可清晰展示问题
- [ ] 集成测试验证完整流程

---

## 技术债务和后续优化

**当前实现的局限性:**
1. 假设调研表格式相对固定（有"1月"关键字的列标题）
2. 使用硬编码的兜底行号（43行）作为最后手段

**未来可能的改进:**
1. 使用更健壮的表格结构识别（例如识别连续的月份列）
2. 添加对多种调研表格式的自适应支持
3. 提供数据提取的可视化验证工具

**优先级:** 低（当前实现已满足实际需求）

---

## Execution Handoff

计划已保存到 `docs/plans/2025-12-27-fix-excel-data-extraction-column-offset.md`。

**两种执行方式：**

**1. Subagent-Driven（本会话）** - 我在本会话中为每个任务派发新的 subagent，任务间代码审查，快速迭代

**2. Parallel Session（独立会话）** - 在新会话中使用 executing-plans，批量执行并在检查点审查

**您选择哪种方式？**
