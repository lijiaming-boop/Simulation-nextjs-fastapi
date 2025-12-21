---
name: check-data-quality
description: 检查提取数据的完整性和合理性
---

# Check Data Quality Skill

## 任务

检查从调研表提取的数据的完整性和合理性,输出质量报告。

## 输入参数

1. `extracted_json_path`: 提取的数据 JSON 文件路径
2. `output_json_path`: 输出质量报告 JSON 路径

## 检查项

### 1. 必填字段缺失检查

**Critical 级别**:
- `project_region` 缺失 → "项目地区缺失,无法匹配气象数据"

**High 级别**:
- 某月的 `total_energy` 缺失 → "X月冷站总能耗缺失"
- 某月的 `chiller_supply_temp` 缺失 → "X月冷机供水温度缺失"

**Medium 级别**:
- 其他参数字段缺失 (如冷却泵频率、温差、冷却塔温度等)

### 2. 数值范围检查

使用行业经验值判断数据是否异常:

- `chiller_supply_temp`: 应在 5-15°C 范围,否则标记为 `out_of_range`
- `cooling_pump_freq`, `freezing_pump_freq`: 应在 20-50Hz,否则标记
- `cooling_water_temp_diff`, `freezing_water_temp_diff`: 应在 2-8℃,否则标记
- `cooling_tower_outlet_temp`: 应在 15-40°C,否则标记

### 3. 逻辑一致性检查

- 温差 < 0 → "供回水温差不能为负值" (severity: high)
- 频率 > 50Hz → "频率超过工频上限" (severity: high)
- 同一字段在不同月份波动 > 200% → "数据异常波动,请核实" (severity: medium)
- 总能耗为 0 或负数 → "能耗数据异常" (severity: critical)

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
    },
    {
      "field": "monthly_data[5].cooling_pump_freq",
      "severity": "medium",
      "type": "out_of_range",
      "message": "6月冷却泵频率(55Hz)超出合理范围(20-50Hz)"
    }
  ],
  "summary": "数据完整率75%,建议补充缺失月份数据。发现1个严重问题,2个高优先级问题。"
}
```

## 字段说明

- `completeness`: 数据完整率 (0.0-1.0)
- `confidence_level`: 置信度等级 ("high" | "medium" | "low")
- `issues`: 问题列表,每个问题包含:
  - `field`: 字段路径 (如 "project_region" 或 "monthly_data[3].chiller_supply_temp")
  - `severity`: 严重程度 ("critical" | "high" | "medium" | "low")
  - `type`: 问题类型 ("missing" | "out_of_range" | "logic_error")
  - `message`: 问题描述
- `summary`: 总结说明,用自然语言描述数据质量状况

## 执行流程

1. 读取提取的数据 JSON (`extracted_json_path`)
2. 检查基础信息 (project_region)
3. 遍历所有月度数据,检查每个字段:
   - 是否缺失
   - 数值是否在合理范围
   - 是否存在逻辑错误
4. 计算完整率和置信度
5. 生成总结说明 (用中文,简洁清晰)
6. 输出质量报告 JSON 到 `output_json_path`

## 重要提示

- 按照 severity 对 issues 排序 (critical > high > medium > low)
- summary 要包含关键信息:完整率、问题数量、建议
- 如果数据完全没有问题,issues 应为空数组 `[]`
- 完整率计算时只统计 7 个运行参数字段,不包括 month 字段
