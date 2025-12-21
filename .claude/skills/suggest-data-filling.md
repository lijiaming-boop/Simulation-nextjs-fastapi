---
name: suggest-data-filling
description: 为缺失数据提供智能填充建议
---

# Suggest Data Filling Skill

## 任务

分析数据质量报告,为缺失数据提供智能填充建议。

## 输入参数

1. `extracted_json_path`: 提取的原始数据 JSON
2. `quality_report_path`: 数据质量报告 JSON
3. `output_json_path`: 输出填充建议 JSON

## 填充策略

### 策略 1: 线性插值 (优先使用)

**适用条件**: 缺失月份前后都有数据

**示例**:
- 已知: 1月=7.0°C, 3月=8.0°C
- 推断: 2月=7.5°C
- 方法: `linear_interpolation`
- 置信度: `high`

**计算方法**:
```
value_missing = value_before + (value_after - value_before) × (month_distance / total_distance)
```

### 策略 2: 季节代表值

**适用条件**: 同季节有数据,缺失月份可用代表值

**季节划分**:
- 夏季: 6-8月 (代表月: 7月)
- 春季: 4-5月 (代表月: 5月)
- 秋季: 9-10月 (代表月: 10月)
- 冬季: 11-3月 (代表月: 1月)

**示例**:
- 已知: 7月冷却塔出水温度=32°C
- 推断: 6月、8月也用 32°C (夏季温度相近)
- 方法: `season_default`
- 置信度: `medium`

### 策略 3: 相邻月份均值

**适用条件**: 缺失月份前后都有数据,但跨度较大 (>2个月)

**示例**:
- 已知: 1月=45Hz, 6月=50Hz
- 推断: 3月=(45+50)/2=47.5Hz
- 方法: `adjacent_average`
- 置信度: `medium`

### 策略 4: 行业默认值 (最后手段)

**适用条件**: 完全无数据,使用行业经验值

**默认值表**:
- `chiller_supply_temp`:
  - 冬季(11-3月): 7°C
  - 春秋(4-5, 9-10月): 8°C
  - 夏季(6-8月): 9°C
- `cooling_tower_outlet_temp`:
  - 冬季: 20°C
  - 春秋: 26°C
  - 夏季: 32°C
- `cooling_pump_freq`: 45Hz
- `freezing_pump_freq`: 50Hz
- `cooling_water_temp_diff`: 4.5℃
- `freezing_water_temp_diff`: 4.5℃
- 方法: `industry_default`
- 置信度: `low`

### 不可填充字段

以下字段缺失时标记为 `unfillable`:
- `project_region`: 必须用户提供,无法推断
- `total_energy`: 如果 12 个月中 < 6 个月有数据,标记为不可填充 (数据太少,推断不可靠)

## 输出格式

**场景 1: 有不可填充字段 (中断流程)**

```json
{
  "can_proceed": false,
  "unfillable_fields": [
    {
      "field": "project_region",
      "reason": "项目地区是必填项,无法通过算法推断,必须用户补充"
    },
    {
      "field": "total_energy",
      "reason": "仅有2个月的能耗数据,不足以推断全年,建议至少提供6个月数据"
    }
  ],
  "fillable_suggestions": []
}
```

**场景 2: 可以继续 (所有缺失都能填充)**

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
      "reasoning": "基于1月(7.0°C)和3月(8.0°C)的线性插值"
    },
    {
      "field": "monthly_data[3].cooling_tower_outlet_temp",
      "original_value": null,
      "suggested_value": 28,
      "method": "season_default",
      "confidence": "medium",
      "reasoning": "使用春季代表值(5月数据: 28°C)"
    },
    {
      "field": "monthly_data[11].freezing_pump_freq",
      "original_value": null,
      "suggested_value": 50,
      "method": "industry_default",
      "confidence": "low",
      "reasoning": "该参数全年数据缺失,使用行业默认值50Hz"
    }
  ]
}
```

## 字段说明

- `can_proceed`: 是否可以继续计算 (boolean)
- `unfillable_fields`: 不可填充字段列表
  - `field`: 字段路径
  - `reason`: 不可填充的原因说明
- `fillable_suggestions`: 可填充建议列表
  - `field`: 字段路径 (格式: "monthly_data[索引].字段名")
  - `original_value`: 原始值 (通常为 null)
  - `suggested_value`: 建议填充值 (数值类型)
  - `method`: 填充方法 ("linear_interpolation" | "season_default" | "adjacent_average" | "industry_default")
  - `confidence`: 置信度 ("high" | "medium" | "low")
  - `reasoning`: 推理说明 (中文,解释为什么这样填充)

## 推理原则

1. **优先使用相邻数据**: 能插值就插值,精度最高
2. **其次使用同季节数据**: 季节特征相似,温度、频率相近
3. **再次使用相邻均值**: 跨度大时用平均值
4. **最后使用默认值**: 仅作为兜底方案,置信度低
5. **关键字段缺失拒绝**: `project_region` 缺失或 `total_energy` 数据太少时应拒绝

## 执行流程

1. 读取原始数据 (`extracted_json_path`) 和质量报告 (`quality_report_path`)
2. 识别所有缺失字段 (从 quality_report 的 issues 中提取 type="missing" 的项)
3. 判断是否有不可填充字段:
   - project_region 缺失 → unfillable
   - total_energy 有效月份 < 6 → unfillable
4. 为每个可填充字段选择最佳策略:
   - 检查前后月份数据 → 尝试线性插值
   - 检查同季节数据 → 尝试季节代表值
   - 检查相邻月份 → 尝试均值
   - 否则使用行业默认值
5. 生成填充建议和推理说明
6. 输出填充建议 JSON 到 `output_json_path`

## 重要提示

- **LLM 推理能力是核心**: 要理解季节规律、温度变化趋势、设备运行特征
- **置信度要诚实**: 不确定的推断要标记为 low,不要过度自信
- **reasoning 要清晰**: 用户需要理解为什么这样填充,增强可信度
- **优先保证关键参数**: total_energy 和 chiller_supply_temp 是核心,必须有足够数据支撑
- **避免过度填充**: 如果某个月所有参数都缺失,且无法合理推断,建议在 reasoning 中说明风险
