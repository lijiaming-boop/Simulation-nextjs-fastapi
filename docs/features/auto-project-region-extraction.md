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
