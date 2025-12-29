# suggest-data-filling Skill 代码和文档统一计划

**日期**: 2025-12-26
**问题**: SKILL.md 文档描述的输出格式与实际代码不一致，导致前端调用失败

## 问题分析

### 现状总结

| 组件 | 路径 | 格式 | 状态 |
|------|------|------|------|
| **实际代码** | `.claude/skills/suggest-data-filling/scripts/suggest_data_filling.py` | `can_proceed` 格式 | ✅ 正确 |
| **旧文档** | `.claude/skills/suggest-data-filling.md` | `can_proceed` 格式 | ✅ 正确 |
| **新文档** | `.claude/skills/suggest-data-filling/SKILL.md` | `project_region` 格式 | ❌ 错误 |
| **测试数据** | `tests/fixtures/filling_suggestions.json` | `can_proceed` 格式 | ✅ 正确 |
| **前端代码** | `app.py:351` | 期望 `can_proceed` 格式 | ✅ 正确 |

### 根本原因

2025-12-26 创建的 `.claude/skills/suggest-data-filling/SKILL.md` 使用了**错误的输出格式**：

**错误格式** (当前 SKILL.md):
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
      "fields": {...}
    }
  ]
}
```

**正确格式** (代码实际生成):
```json
{
  "can_proceed": true,
  "unfillable_fields": [],
  "fillable_suggestions": [
    {
      "field": "monthly_data[1].chiller_supply_temp",
      "original_value": null,
      "suggested_value": 7.5,
      "method": "linear_interpolation",
      "confidence": "high",
      "reasoning": "基于1月(7.0)和3月(8.0)的线性插值"
    }
  ]
}
```

### 影响范围

1. **前端中断**: `app.py` 中 `suggestions.get("can_proceed", False)` 因缺少该字段默认为 `False`，导致误报"关键数据缺失"
2. **文档误导**: 开发者阅读 SKILL.md 后会生成错误格式的输出
3. **集成错误**: 任何依赖该 skill 的外部系统会收到意外的数据结构

## 统一方案

### 选项 1: 更新 SKILL.md 为正确格式（推荐）✅

**理由**:
- 代码、测试、前端都已使用 `can_proceed` 格式
- 改动最小，只需更新一个文档文件
- 向后兼容，不破坏现有功能

**需要修改**:
- `.claude/skills/suggest-data-filling/SKILL.md`

### 选项 2: 修改代码匹配 SKILL.md（不推荐）❌

**理由**:
- 需要修改代码、测试、前端（改动巨大）
- 破坏现有测试和集成
- `can_proceed` 格式更清晰，符合流程控制需求

## 实施计划

### 第一阶段: 文档修复 (优先级: 🔥 高)

#### 任务 1.1: 备份当前错误文档
```bash
cp .claude/skills/suggest-data-filling/SKILL.md \
   .claude/skills/suggest-data-filling/SKILL.md.backup-2025-12-26
```

#### 任务 1.2: 更新 SKILL.md 输出格式部分

**需要修改的章节**:

1. **第 73-102 行**: 输出格式示例
   - 删除 `project_region` 和 `monthly_suggestions` 格式
   - 改为 `can_proceed` + `unfillable_fields` + `fillable_suggestions` 格式

2. **新增字段说明**:
   ```markdown
   ## 输出字段详解

   ### can_proceed (boolean)
   - `true`: 所有缺失字段都可以通过算法填充，可以继续计算
   - `false`: 存在关键字段无法填充，必须用户补充数据后重新上传

   ### unfillable_fields (array)
   不可填充字段列表，仅当 `can_proceed = false` 时有值：
   - `field`: 字段路径 (如 "project_region", "total_energy")
   - `reason`: 不可填充的原因说明

   ### fillable_suggestions (array)
   可填充字段的建议列表：
   - `field`: 字段路径 (格式: "monthly_data[索引].字段名")
   - `original_value`: 原始值 (通常为 null)
   - `suggested_value`: 建议填充值
   - `method`: 填充方法 (linear_interpolation / season_default / industry_default)
   - `confidence`: 置信度 (high / medium / low)
   - `reasoning`: 推理说明
   ```

3. **更新示例场景** (第 121-147 行):
   - 场景1 和场景2 的输出示例改为正确格式

#### 任务 1.3: 对齐方法名映射

**当前代码使用的方法名**:
- `linear_interpolation`
- `season_default`
- `adjacent_average`
- `industry_default`

**SKILL.md 第 112-119 行描述的方法名** (需要保持一致):
- `auto_extracted` (仅用于 project_region，已废弃)
- `manual_input` (仅用于 project_region，已废弃)
- ~~`interpolation`~~ → 应为 `linear_interpolation`
- ~~`seasonal_pattern`~~ → 应为 `season_default`
- ~~`param_based_estimation`~~ → 代码中未实现
- ~~`typical_value`~~ → 应为 `industry_default`

**修改方案**: 删除第 112-119 行的过时方法说明，引用 `.claude/skills/suggest-data-filling.md` 中的正确方法说明。

#### 任务 1.4: 删除 project_region 相关内容

**删除章节**:
- 第 51-55 行: "### 3. 项目地区" 整节
  - 原因: `project_region` 现在由 `extract-and-check-data` skill 负责提取，`suggest-data-filling` 不再处理

**保留说明**:
```markdown
## 依赖说明

本 skill 依赖 `extract-and-check-data` skill 提前提取 `project_region`：
- `extracted_data.json` 中必须包含 `project_region` 字段
- 如果缺失，会被标记为 `unfillable_fields` 并中断流程
```

### 第二阶段: 代码注释增强 (优先级: 中)

#### 任务 2.1: 在 suggest_data_filling.py 中添加输出格式文档字符串

在 `DataFillingSuggester.run()` 方法中添加：

```python
def run(self) -> Dict[str, Any]:
    """执行填充建议生成

    Returns:
        Dict[str, Any]: 填充建议结果
        {
            "can_proceed": bool,           # 是否可以继续计算
            "unfillable_fields": List[Dict],  # 不可填充字段列表
            "fillable_suggestions": List[Dict]  # 可填充建议列表
        }

    输出格式详见: .claude/skills/suggest-data-filling/SKILL.md
    """
```

### 第三阶段: 测试验证 (优先级: 🔥 高)

#### 任务 3.1: 运行现有测试套件

```bash
# 单元测试
pytest tests/unit/test_suggest_data_filling.py -v

# 集成测试
pytest tests/integration/test_suggest_data_filling_integration.py -v
```

#### 任务 3.2: 端到端验证

```bash
# 1. 使用示例数据生成填充建议
python .claude/skills/suggest-data-filling/scripts/suggest_data_filling.py \
  tmp/extracted_data.json \
  tmp/quality_report.json \
  tmp/filling_suggestions.json

# 2. 检查输出格式
cat tmp/filling_suggestions.json | jq 'keys'
# 期望输出: ["can_proceed", "unfillable_fields", "fillable_suggestions"]

# 3. 在 Streamlit 中测试完整流程
streamlit run app.py
```

### 第四阶段: 文档清理 (优先级: 低)

#### 任务 4.1: 决定旧文档的去留

**选项 A**: 删除旧文档
```bash
rm .claude/skills/suggest-data-filling.md
```

**选项 B**: 保留旧文档并添加废弃说明
```markdown
# ⚠️ DEPRECATED

本文档已废弃，请参考:
- 最新文档: `.claude/skills/suggest-data-filling/SKILL.md`
- 最后更新: 2025-12-26
```

**推荐**: 选项 A (删除)，避免文档冗余

#### 任务 4.2: 更新 CLAUDE.md 中的相关说明

在 `CLAUDE.md` 的 "Claude Skills（AI辅助层）" 章节中，确保对 `suggest-data-filling` 的描述正确：

```markdown
2. **suggest-data-filling**：基于季节模式和插值法推荐填充值
   - 输入：质量报告 + 提取数据
   - 输出：`tmp/filling_suggestions.json`
   - 关键功能：
     - **流程控制**: 通过 `can_proceed` 字段决定是否可继续计算
     - **不可填充检测**: 识别 project_region 缺失、能耗数据 < 6个月等情况
     - **智能填充**: 线性插值、季节代表值、行业默认值三级策略
   - 填充策略：线性插值（高置信度）、季节代表值（中）、行业默认值（低）
```

## 验收标准

### ✅ 文档一致性
- [ ] SKILL.md 中的输出格式示例与代码实际输出完全一致
- [ ] 所有方法名 (method 字段) 与代码中的常量一致
- [ ] 删除了过时的 `project_region` 处理说明

### ✅ 代码功能
- [ ] 所有现有测试通过 (pytest)
- [ ] 生成的 JSON 包含 `can_proceed` 字段
- [ ] `app.py` 能正确读取 `can_proceed` 并进行流程控制

### ✅ 端到端验证
- [ ] 使用示例调研表完整走通流程 (上传 → 提取 → 填充建议 → 计算 → 结果)
- [ ] 低置信度数据正确中断在"提取+质量检查"阶段
- [ ] 中等置信度数据正确进入"填充建议"阶段并显示建议

## 风险与注意事项

### 🔴 破坏性风险: 无
- 仅修改文档，不修改代码逻辑
- 所有现有测试和功能保持不变

### ⚠️ 注意事项
1. **备份文件**: 修改前务必备份 SKILL.md
2. **版本同步**: 如果有 Git 提交，确保提交信息清晰说明"修复文档格式不一致"
3. **下游影响**: 如果有外部系统依赖该 skill 的文档，需要通知更新

## 时间估算

| 阶段 | 任务数 | 预计时间 |
|------|--------|----------|
| 第一阶段: 文档修复 | 4 | 30 分钟 |
| 第二阶段: 代码注释 | 1 | 10 分钟 |
| 第三阶段: 测试验证 | 2 | 20 分钟 |
| 第四阶段: 文档清理 | 2 | 15 分钟 |
| **总计** | **9** | **75 分钟** |

## 后续改进建议

1. **建立文档-代码同步机制**:
   - 在 CI/CD 中添加文档格式校验
   - 使用 JSON Schema 验证输出格式

2. **自动化测试增强**:
   - 添加输出格式的 schema 验证测试
   - 确保文档中的示例 JSON 可以通过 schema 校验

3. **文档结构标准化**:
   - 为所有 skills 建立统一的文档模板
   - 包含: 输入参数、输出格式、示例、方法说明、错误处理

## 参考文档

- 代码实现: `.claude/skills/suggest-data-filling/scripts/suggest_data_filling.py`
- 正确文档: `.claude/skills/suggest-data-filling.md` (旧版，待清理)
- 错误文档: `.claude/skills/suggest-data-filling/SKILL.md` (待修复)
- 前端代码: `app.py` 第 351-370 行
- 测试数据: `tests/fixtures/filling_suggestions.json`
