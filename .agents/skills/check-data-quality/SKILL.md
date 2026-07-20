---
name: check-data-quality
description: 检查提取数据的完整性和合理性。当需要验证从调研表提取的冷站运行数据质量时使用,包括检查必填字段缺失、数值范围合理性、逻辑一致性,并输出包含完整率、置信度和问题列表的质量报告。适用于数据验证、质量评估等场景。
---

# Check Data Quality

## 概述

检查从调研表提取的冷站运行数据的完整性和合理性,生成结构化的质量报告。

## 快速开始

使用 `scripts/check_data_quality.py` 脚本执行数据质量检查:

```bash
python scripts/check_data_quality.py <extracted_json_path> <output_json_path>
```

**参数**:
- `extracted_json_path`: 提取的数据 JSON 文件路径
- `output_json_path`: 输出质量报告 JSON 路径

**示例**:
```bash
python scripts/check_data_quality.py ./data/extracted.json ./output/quality_report.json
```

## 检查项

### 1. 必填字段缺失检查

**Critical 级别**:
- `project_region` 缺失 → "项目地区缺失,无法匹配气象数据"

**High 级别**:
- 某月的 `total_energy` 缺失 → "X月冷站总能耗缺失"
- 某月的 `chiller_supply_temp` 缺失 → "X月冷机供水温度缺失"

**Medium 级别**:
- 其他运行参数字段缺失(冷却泵频率、温差、冷却塔温度等)

### 2. 数值范围检查

使用行业经验值判断数据是否异常:

| 字段 | 合理范围 | 单位 |
|------|---------|------|
| `chiller_supply_temp` | 5-15 | °C |
| `cooling_pump_freq` | 20-50 | Hz |
| `freezing_pump_freq` | 20-50 | Hz |
| `cooling_water_temp_diff` | 2-8 | ℃ |
| `freezing_water_temp_diff` | 2-8 | ℃ |
| `cooling_tower_outlet_temp` | 15-40 | °C |

超出范围的值将被标记为 `out_of_range` 类型问题。

### 3. 逻辑一致性检查

- 温差 < 0 → "供回水温差不能为负值" (severity: high)
- 频率 > 50Hz → "频率超过工频上限" (severity: high)
- 总能耗 ≤ 0 → "能耗数据异常" (severity: critical)

### 4. 数据完整率计算

```
完整率 = 非null数据点数 / 总数据点数
总数据点数 = 12个月 × 7个字段 = 84
```

**置信度判断**:
- 完整率 ≥ 80% → `high`
- 完整率 50%-80% → `medium`
- 完整率 < 50% → `low`

## 输出格式

质量报告 JSON 包含以下字段:

```json
{
  "completeness": 0.75,
  "confidence_level": "medium",
  "issues": [
    {
      "field": "project_region",
      "severity": "critical",
      "type": "missing",
      "message": "项目地区缺失,无法匹配气象数据"
    },
    {
      "field": "monthly_data[3].chiller_supply_temp",
      "severity": "high",
      "type": "missing",
      "message": "4月冷机供水温度缺失"
    }
  ],
  "summary": "数据完整率75%,建议补充缺失月份数据。发现1个严重问题,1个高优先级问题。"
}
```

**字段说明**:
- `completeness`: 数据完整率 (0.0-1.0)
- `confidence_level`: 置信度等级 ("high" | "medium" | "low")
- `issues`: 问题列表,按严重程度排序 (critical > high > medium > low)
  - `field`: 字段路径
  - `severity`: 严重程度 ("critical" | "high" | "medium" | "low")
  - `type`: 问题类型 ("missing" | "out_of_range" | "logic_error")
  - `message`: 问题描述
- `summary`: 中文总结,包含完整率、问题数量和建议

## 运行参数字段

脚本检查以下 7 个月度运行参数字段:

1. `total_energy` - 冷站总能耗
2. `chiller_supply_temp` - 冷机供水温度
3. `cooling_pump_freq` - 冷却泵频率
4. `freezing_pump_freq` - 冷冻泵频率
5. `cooling_water_temp_diff` - 冷却水温差
6. `freezing_water_temp_diff` - 冷冻水温差
7. `cooling_tower_outlet_temp` - 冷却塔出水温度

## 使用说明

1. 确保输入 JSON 文件包含 `project_region` 和 `monthly_data` 字段
2. `monthly_data` 应为包含 12 个月数据的数组
3. 脚本会自动创建输出目录(如不存在)
4. 运行成功后会在控制台显示总结信息
