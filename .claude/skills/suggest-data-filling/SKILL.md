---
name: suggest-data-filling
description: 基于季节模式和插值法为中央空调冷站运行数据生成智能填充建议。当调研表数据不完整,需要推荐缺失数据的合理填充值时使用此技能。
---

# Suggest Data Filling Skill

## 任务

分析数据质量报告,为缺失数据提供智能填充建议。

## 输入参数

1. `extracted_json_path`: 提取的原始数据 JSON (来自 extract-and-check-data skill)
2. `quality_report_path`: 数据质量报告 JSON (来自 extract-and-check-data skill)
3. `output_json_path`: 输出填充建议 JSON

## 依赖说明

本 skill 依赖 `extract-and-check-data` skill 提前提取 `project_region`：
- `extracted_data.json` 中必须包含 `project_region` 字段
- 如果缺失，会被标记为 `unfillable_fields` 并中断流程

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
- `project_region`: 必须由 extract-and-check-data skill 提取，无法推断
- `total_energy`: 如果 12 个月中 < 6 个月有数据,标记为不可填充 (数据太少,推断不可靠)

## 输出格式

### 输出字段详解

#### can_proceed (boolean)
- `true`: 所有缺失字段都可以通过算法填充，可以继续计算
- `false`: 存在关键字段无法填充，必须用户补充数据后重新上传

#### unfillable_fields (array)
不可填充字段列表，仅当 `can_proceed = false` 时有值：
- `field`: 字段路径 (如 "project_region", "total_energy")
- `reason`: 不可填充的原因说明

#### fillable_suggestions (array)
可填充字段的建议列表：
- `field`: 字段路径 (格式: "monthly_data[索引].字段名")
- `original_value`: 原始值 (通常为 null)
- `suggested_value`: 建议填充值 (数值类型)
- `method`: 填充方法 ("linear_interpolation" | "season_default" | "adjacent_average" | "industry_default")
- `confidence`: 置信度 ("high" | "medium" | "low")
- `reasoning`: 推理说明 (中文,解释为什么这样填充)

### 场景 1: 有不可填充字段 (中断流程)

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

### 场景 2: 可以继续 (所有缺失都能填充)

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

## 使用方法

### 直接调用脚本

```bash
# 确保输入文件存在
ls tmp/extracted_data.json tmp/quality_report.json

# 运行填充建议生成器
python .claude/skills/suggest-data-filling/scripts/suggest_data_filling.py \
  tmp/extracted_data.json \
  tmp/quality_report.json \
  tmp/filling_suggestions.json

# 查看输出
cat tmp/filling_suggestions.json
```

### 在 Python 代码中调用

```python
from core.skill_caller import SkillCaller

caller = SkillCaller(timeout=300)
result = caller.call_skill(
    "suggest-data-filling",
    "tmp/extracted_data.json",
    "tmp/quality_report.json",
    "tmp/filling_suggestions.json"
)
```

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

## 推理原则

1. **优先使用相邻数据**: 能插值就插值,精度最高
2. **其次使用同季节数据**: 季节特征相似,温度、频率相近
3. **再次使用相邻均值**: 跨度大时用平均值
4. **最后使用默认值**: 仅作为兜底方案,置信度低
5. **关键字段缺失拒绝**: `project_region` 缺失或 `total_energy` 数据太少时应拒绝

## 技术细节

### 季节分组
```python
SEASON_GROUPS = {
    "winter": [12, 1, 2],    # 冬季
    "spring": [3, 4, 5],     # 春季
    "summer": [6, 7, 8],     # 夏季
    "autumn": [9, 10, 11]    # 秋季
}
```

### 典型值范围
- 基于《中央空调系统节能评估规范》
- 参考《公共建筑节能设计标准》

## 注意事项

1. **置信度判断**: 建议仅供参考,高置信度建议优先采用
2. **物理合理性**: 所有建议值均符合物理约束(如温度不能为负)
3. **数据质量**: 如果原始数据质量低,填充建议置信度也会降低
4. **人工审核**: 关键字段(如能耗)建议人工审核后再使用

## 重要提示

- **LLM 推理能力是核心**: 要理解季节规律、温度变化趋势、设备运行特征
- **置信度要诚实**: 不确定的推断要标记为 low,不要过度自信
- **reasoning 要清晰**: 用户需要理解为什么这样填充,增强可信度
- **优先保证关键参数**: total_energy 和 chiller_supply_temp 是核心,必须有足够数据支撑
- **避免过度填充**: 如果某个月所有参数都缺失,且无法合理推断,建议在 reasoning 中说明风险

## 后续处理

填充建议生成后,可以:
1. 使用 `DataFiller` 应用建议到原始数据
2. 使用 `ExcelCalculator` 计算节能率
3. 对比不同填充策略对结果的影响

## 资源

### scripts/
- `suggest_data_filling.py`: 核心填充建议生成器

该脚本包含:
- 数据加载和保存函数
- 季节分组和插值算法
- 不可填充字段检测
- 填充建议生成逻辑
