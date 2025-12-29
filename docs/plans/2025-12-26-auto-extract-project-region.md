# 自动提取项目地区实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 修改 suggest-data-filling skill，使其从 extracted_data.json 自动读取项目地区，而不是要求用户手动输入

**架构:** 修改 generate_suggestions.py 脚本，从 extracted_data 中读取 project_region 字段，并相应更新 SKILL.md 文档

**技术栈:** Python 3.8+, JSON

---

## Task 1: 修改项目地区提取逻辑

**Files:**
- Modify: `.claude/skills/suggest-data-filling/scripts/generate_suggestions.py:199-227`

**Step 1: 写失败测试**

创建测试文件验证项目地区提取功能：

```python
# tests/unit/test_suggest_data_filling.py
import json
import pytest
from pathlib import Path

def test_extract_project_region_from_input():
    """测试从extracted_data中提取项目地区"""
    extracted_data = {
        "project_region": "华南",
        "monthly_data": []
    }

    # 导入要测试的函数
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".claude/skills/suggest-data-filling/scripts"))
    from generate_suggestions import generate_suggestions

    quality_report = {"confidence_level": "medium"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    assert suggestions["project_region"]["suggested_value"] == "华南"
    assert suggestions["project_region"]["method"] == "auto_extracted"
    assert suggestions["project_region"]["confidence"] == "high"
```

**Step 2: 运行测试验证失败**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_suggest_data_filling.py::test_extract_project_region_from_input -v`

Expected: FAIL - 断言失败，当前返回 None 和 "manual_input"

**Step 3: 实现项目地区自动提取**

修改 `generate_suggestions` 函数中的项目地区处理逻辑：

```python
def generate_suggestions(
    extracted_data: Dict,
    quality_report: Dict
) -> Dict:
    """
    生成填充建议

    策略:
    1. 对于项目地区:
       - 优先从extracted_data中读取project_region字段
       - 如果没有,则需要用户手动输入

    2. 对于能耗数据:
       - 如果有运行参数,基于参数估算
       - 如果没有,使用季节系数推算

    3. 对于运行参数(温度、频率、温差):
       - 优先使用同季节代表月的数据
       - 如果没有,使用线性插值
       - 如果完全没有,使用典型值
    """
    # 提取项目地区
    project_region = extracted_data.get("project_region")

    if project_region:
        region_suggestion = {
            "suggested_value": project_region,
            "method": "auto_extracted",
            "confidence": "high",
            "reason": "从调研表中自动提取的项目地区"
        }
    else:
        region_suggestion = {
            "suggested_value": None,
            "method": "manual_input",
            "confidence": "none",
            "reason": "需要用户输入项目所在地区"
        }

    suggestions = {
        "project_region": region_suggestion,
        "monthly_suggestions": []
    }

    monthly_data = extracted_data.get("monthly_data", [])

    # ... 其余代码保持不变 ...
```

**Step 4: 运行测试验证通过**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_suggest_data_filling.py::test_extract_project_region_from_input -v`

Expected: PASS

**Step 5: 添加边界情况测试**

添加测试用例验证没有项目地区的情况：

```python
def test_missing_project_region_requires_manual_input():
    """测试缺失项目地区时要求手动输入"""
    extracted_data = {
        "monthly_data": []
        # 故意不包含 project_region
    }

    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".claude/skills/suggest-data-filling/scripts"))
    from generate_suggestions import generate_suggestions

    quality_report = {"confidence_level": "medium"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    assert suggestions["project_region"]["suggested_value"] is None
    assert suggestions["project_region"]["method"] == "manual_input"
    assert suggestions["project_region"]["confidence"] == "none"
```

**Step 6: 运行所有测试**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_suggest_data_filling.py -v`

Expected: 所有测试 PASS

**Step 7: 提交代码**

```bash
git add tests/unit/test_suggest_data_filling.py
git add .claude/skills/suggest-data-filling/scripts/generate_suggestions.py
git commit -m "feat: auto-extract project_region from input data

- Modify generate_suggestions to read project_region from extracted_data
- Add high-confidence auto_extracted method when region is available
- Fall back to manual_input when region is missing
- Add unit tests for both scenarios"
```

---

## Task 2: 更新 SKILL.md 文档

**Files:**
- Modify: `.claude/skills/suggest-data-filling/SKILL.md:50-53`

**Step 1: 更新项目地区策略说明**

修改文档中关于项目地区的策略描述：

```markdown
### 3. 项目地区

**策略:**
1. **自动提取**(高置信度): 从 `extracted_data.json` 的 `project_region` 字段自动读取
2. **手动输入**(无置信度): 如果提取数据中不包含项目地区，需要用户手动输入
```

**Step 2: 更新输出格式示例**

修改输出格式示例以反映自动提取的情况：

```markdown
### 输出格式

```json
{
  "project_region": {
    "suggested_value": "华南",
    "method": "auto_extracted",
    "confidence": "high",
    "reason": "从调研表中自动提取的项目地区"
  },
  "monthly_suggestions": [
    {
      "month": 2,
      "fields": {
        "total_energy": {
          "suggested_value": 50000.0,
          "method": "seasonal_pattern",
          "confidence": "low",
          "reason": "基于季节模式估算"
        }
      }
    }
  ]
}
```

**Step 3: 添加方法说明**

在"置信度说明"部分后添加"方法说明"：

```markdown
### 方法说明

- **auto_extracted**: 从提取的数据中自动获取（适用于项目地区）
- **manual_input**: 需要用户手动输入（当自动提取失败时）
- **interpolation**: 线性插值（基于相邻数据点）
- **seasonal_pattern**: 季节模式估算（基于季节系数）
- **param_based_estimation**: 基于运行参数的物理模型估算
- **typical_value**: 使用行业典型值
```

**Step 4: 更新使用场景说明**

在 Overview 部分添加项目地区自动提取的说明：

```markdown
**使用场景:**
- 调研表部分月份运行数据缺失
- 需要为缺失数据提供合理的估算值
- 希望基于已有数据和季节特征推断缺失值
- 自动从调研表提取项目地区信息（配合 extract-and-check-data skill）
```

**Step 5: 验证文档格式**

Run: `cat .claude/skills/suggest-data-filling/SKILL.md | head -60`

Expected: 显示更新后的文档内容，格式正确

**Step 6: 提交文档**

```bash
git add .claude/skills/suggest-data-filling/SKILL.md
git commit -m "docs: update SKILL.md for auto project_region extraction

- Update project region strategy to reflect auto-extraction
- Add method descriptions for auto_extracted vs manual_input
- Update output format examples with high-confidence region
- Clarify use cases for automatic region detection"
```

---

## Task 3: 集成测试验证

**Files:**
- Create: `tests/integration/test_suggest_data_filling_integration.py`

**Step 1: 写端到端集成测试**

创建集成测试验证完整流程：

```python
# tests/integration/test_suggest_data_filling_integration.py
import json
import pytest
from pathlib import Path
import sys

# 添加脚本路径到Python路径
scripts_path = Path(__file__).parent.parent.parent / ".claude/skills/suggest-data-filling/scripts"
sys.path.insert(0, str(scripts_path))

from generate_suggestions import generate_suggestions


def test_e2e_with_real_extracted_data():
    """端到端测试：使用真实的extracted_data.json"""
    base_dir = Path(__file__).parent.parent.parent
    extracted_data_path = base_dir / "tmp" / "extracted_data.json"

    # 跳过测试如果文件不存在
    if not extracted_data_path.exists():
        pytest.skip("tmp/extracted_data.json not found")

    with open(extracted_data_path, 'r', encoding='utf-8') as f:
        extracted_data = json.load(f)

    quality_report = {"confidence_level": "medium"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    # 验证项目地区被自动提取
    assert suggestions["project_region"]["suggested_value"] is not None
    assert suggestions["project_region"]["method"] == "auto_extracted"
    assert suggestions["project_region"]["confidence"] == "high"
    assert suggestions["project_region"]["suggested_value"] in [
        "华南", "华东", "华中", "西南", "西北", "华北", "东北"
    ]

    # 验证月度建议存在
    assert len(suggestions["monthly_suggestions"]) == 12
```

**Step 2: 运行集成测试**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_suggest_data_filling_integration.py -v -s`

Expected: PASS（如果 tmp/extracted_data.json 存在且包含 project_region）

**Step 3: 添加兜底场景测试**

测试当 extracted_data 不包含 project_region 时的行为：

```python
def test_fallback_when_region_missing():
    """测试项目地区缺失时的兜底行为"""
    extracted_data = {
        "monthly_data": [
            {"month": i, "total_energy": 1000 * i}
            for i in range(1, 13)
        ]
    }

    quality_report = {"confidence_level": "high"}

    suggestions = generate_suggestions(extracted_data, quality_report)

    # 应该要求手动输入
    assert suggestions["project_region"]["suggested_value"] is None
    assert suggestions["project_region"]["method"] == "manual_input"
    assert suggestions["project_region"]["confidence"] == "none"
    assert "用户输入" in suggestions["project_region"]["reason"]
```

**Step 4: 运行所有集成测试**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_suggest_data_filling_integration.py -v`

Expected: 所有测试 PASS

**Step 5: 提交集成测试**

```bash
git add tests/integration/test_suggest_data_filling_integration.py
git commit -m "test: add integration tests for project_region auto-extraction

- Add e2e test with real extracted_data.json
- Test fallback to manual_input when region missing
- Verify region values are valid Chinese regions"
```

---

## Task 4: 更新项目文档

**Files:**
- Modify: `CLAUDE.md` (项目地区识别规则部分)

**Step 1: 在 CLAUDE.md 中添加填充建议使用说明**

在"## Claude Skills（AI辅助层）"部分的 suggest-data-filling 描述中更新：

```markdown
2. **suggest-data-filling**：基于季节模式和插值法推荐填充值
   - 输入：质量报告 + 提取数据
   - 输出：`tmp/filling_suggestions.json`
   - 关键功能：
     - **自动读取项目地区**：从 extracted_data.json 的 project_region 字段获取（高置信度）
     - 能耗数据估算：季节代表月法（夏季用7月、春秋用5/10月、冬季用1月）
     - 运行参数插值：线性插值、季节复制、典型值兜底
   - 填充策略：季节代表月法、线性插值
```

**Step 2: 验证文档内容**

Run: `grep -A 10 "suggest-data-filling" CLAUDE.md`

Expected: 显示更新后的描述，包含自动读取项目地区的说明

**Step 3: 提交文档更新**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with auto project_region in filling skill

- Document automatic project_region extraction in suggest-data-filling
- Clarify that region is read from extracted_data.json
- Note high confidence level for auto-extracted regions"
```

---

## Task 5: 手动验证完整流程

**Files:**
- Test: 实际运行脚本验证

**Step 1: 确保测试数据存在**

Run: `ls -lh tmp/extracted_data.json tmp/quality_report.json`

Expected: 两个文件都存在

**Step 2: 备份现有输出**

Run: `cp tmp/filling_suggestions.json tmp/filling_suggestions.json.backup 2>/dev/null || true`

Expected: 成功（如果文件存在）或静默跳过

**Step 3: 运行填充建议生成器**

Run: `python .claude/skills/suggest-data-filling/scripts/generate_suggestions.py`

Expected:
```
正在加载提取的数据...
正在加载质量报告...
正在生成填充建议...
✓ 填充建议已保存到: /home/zack/lingzhi_apps/conditioner_saving/tmp/filling_suggestions.json

建议统计:
  总字段数: XX
  高置信度: XX
  中置信度: XX
  低置信度: XX
```

**Step 4: 检查项目地区字段**

Run: `cat tmp/filling_suggestions.json | python -m json.tool | head -10`

Expected: 显示 project_region 字段，suggested_value 为 "华南"，method 为 "auto_extracted"

**Step 5: 与备份对比**

Run: `diff tmp/filling_suggestions.json.backup tmp/filling_suggestions.json 2>/dev/null || echo "No backup or files differ"`

Expected: 项目地区部分显示变化（从 manual_input 变为 auto_extracted）

**Step 6: 清理临时文件**

Run: `rm -f tmp/filling_suggestions.json.backup`

Expected: 成功删除备份文件

---

## Task 6: 创建功能演示文档

**Files:**
- Create: `docs/features/auto-project-region-extraction.md`

**Step 1: 写演示文档**

创建功能说明文档：

```markdown
# 项目地区自动提取功能

## 概述

suggest-data-filling skill 现在能够自动从 extracted_data.json 中读取项目地区，无需用户手动输入。

## 功能特性

### 自动提取（高置信度）

当 extract-and-check-data skill 成功从调研表中识别项目地区时，suggest-data-filling 会自动使用该值：

```json
{
  "project_region": {
    "suggested_value": "华南",
    "method": "auto_extracted",
    "confidence": "high",
    "reason": "从调研表中自动提取的项目地区"
  }
}
```

### 兜底机制（需手动输入）

如果提取失败，系统会提示用户手动输入：

```json
{
  "project_region": {
    "suggested_value": null,
    "method": "manual_input",
    "confidence": "none",
    "reason": "需要用户输入项目所在地区"
  }
}
```

## 数据流

```
调研表 Excel
    ↓
extract-and-check-data skill
    ↓ 生成 extracted_data.json (含 project_region: "华南")
    ↓
suggest-data-filling skill
    ↓ 自动读取 project_region
    ↓
filling_suggestions.json (project_region.method = "auto_extracted")
```

## 支持的地区

- 华南、华东、华中
- 西南、西北
- 华北、东北

详见 CLAUDE.md 中的"项目地区识别规则"。

## 技术实现

### 代码位置
- 脚本：`.claude/skills/suggest-data-filling/scripts/generate_suggestions.py:199-227`
- 文档：`.claude/skills/suggest-data-filling/SKILL.md`

### 测试
- 单元测试：`tests/unit/test_suggest_data_filling.py`
- 集成测试：`tests/integration/test_suggest_data_filling_integration.py`

## 版本历史

- 2025-12-26: 实现自动提取功能（之前需要手动输入）
```

**Step 2: 提交演示文档**

```bash
git add docs/features/auto-project-region-extraction.md
git commit -m "docs: add feature documentation for auto project_region extraction

- Explain auto-extraction vs manual input fallback
- Document data flow from extract to filling suggestions
- List supported regions and testing coverage"
```

---

## Task 7: 运行完整测试套件

**Files:**
- Test: 所有相关测试

**Step 1: 运行单元测试**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_suggest_data_filling.py -v`

Expected: 所有测试 PASS

**Step 2: 运行集成测试**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/integration/test_suggest_data_filling_integration.py -v`

Expected: 所有测试 PASS

**Step 3: 运行完整测试套件**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/ -v -k "suggest_data_filling"`

Expected: 所有相关测试 PASS

**Step 4: 生成测试覆盖率报告（可选）**

Run: `PYTHONPATH=/home/zack/lingzhi_apps/conditioner_saving pytest tests/unit/test_suggest_data_filling.py --cov=.claude/skills/suggest-data-filling/scripts --cov-report=term-missing`

Expected: 显示代码覆盖率，generate_suggestions 函数应达到 80%+ 覆盖

**Step 5: 提交测试报告**

无需提交，仅验证通过即可。

---

## 验收标准

### 功能验收
- [ ] `extracted_data.json` 包含 `project_region` 时，自动提取并设置 confidence="high"
- [ ] `extracted_data.json` 不包含 `project_region` 时，回退到 manual_input
- [ ] 输出的 `filling_suggestions.json` 格式正确

### 代码质量
- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 代码符合 PEP 8 规范
- [ ] 函数有清晰的文档字符串

### 文档完整性
- [ ] SKILL.md 更新项目地区策略说明
- [ ] CLAUDE.md 更新 suggest-data-filling 描述
- [ ] 创建功能演示文档

### 向后兼容性
- [ ] 不影响其他填充建议功能（能耗、运行参数）
- [ ] 输出 JSON 格式保持一致（仅修改 project_region 字段的值和方法）

---

## 注意事项

1. **DRY 原则**: 不重复造轮子，直接读取 extracted_data 中已有的 project_region
2. **YAGNI 原则**: 不添加复杂的地区验证逻辑，信任 extract-and-check-data skill 的输出
3. **TDD 原则**: 先写测试，后改代码，确保功能正确
4. **频繁提交**: 每个任务完成后立即提交，保持 Git 历史清晰

## 依赖关系

- **前置条件**: extract-and-check-data skill 已在 extracted_data.json 中写入 project_region
- **后续影响**: DataFiller 和 ExcelCalculator 可以使用自动填充的项目地区

## 预估工作量

- Task 1-2: 核心功能实现（15分钟）
- Task 3-4: 测试和文档（15分钟）
- Task 5-7: 验证和完善（10分钟）
- **总计**: 约 40 分钟
