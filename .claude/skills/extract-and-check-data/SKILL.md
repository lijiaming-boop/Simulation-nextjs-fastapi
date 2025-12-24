---
name: extract-and-check-data
description: 从中央空调节能调研表 Excel 文件中提取月度运行数据,同时进行数据质量检查,输出结构化 JSON 数据和质量报告。当用户需要处理中央空调调研表、提取能耗数据并验证数据质量时使用此技能。
---

# Extract and Check Data Skill

## 任务

从上传的中央空调节能调研表中提取关键数据,同时进行质量检查,输出包含提取数据和质量报告的 JSON 文件。

## 输入参数

1. `survey_excel_path`: 调研表 Excel 文件路径
2. `output_json_path`: 输出 JSON 文件路径

## 提取字段

**基础信息:**
- `project_region`: 项目地区 (华南/华东/华中/西南/西北/华北)

**月度运行数据** (1-12月):
- `month`: 月份 (1-12)
- `total_energy`: 冷站月度总能耗 (万kWh)
- `chiller_supply_temp`: 冷机供水温度 (°C)
- `cooling_pump_freq`: 冷却泵运行频率 (Hz)
- `cooling_water_temp_diff`: 冷却侧供回水温差 (℃)
- `freezing_pump_freq`: 冷冻泵运行频率 (Hz)
- `freezing_water_temp_diff`: 冷冻侧供回水温差 (℃)
- `cooling_tower_outlet_temp`: 冷却塔出水温度 (℃)

## 数据处理要点

1. **智能识别**: 不要硬编码 Sheet 名称，利用 LLM 理解能力识别包含月度数据的工作表
2. **文本解析**:
   - 频率字段可能是 "工频50HZ"、"45Hz"、"50" 等格式，提取数值部分
   - 温差字段可能是 "3-5℃"、"4℃"、"4.5" 等格式，提取中间值或单一值
   - 例如: "工频50HZ" → 50, "3-5℃/4℃" → 4.5 (取区间中值或明确值)
3. **缺失值处理**: 空白单元格或无法解析的值标记为 `null`
4. **数据验证**: 如果 12 个月中有 < 3 个月有 total_energy 数据，返回错误

## 质量检查项

### 1. 必填字段缺失检查
- Critical: `project_region` 缺失
- High: `total_energy`, `chiller_supply_temp` 缺失
- Medium: 其他运行参数缺失

### 2. 数值范围检查
- `chiller_supply_temp`: 5-15°C
- `cooling_pump_freq`: 20-50 Hz
- `freezing_pump_freq`: 20-50 Hz
- `cooling_water_temp_diff`: 2-8℃
- `freezing_water_temp_diff`: 2-8℃
- `cooling_tower_outlet_temp`: 15-40°C

### 3. 逻辑一致性检查
- 温差 < 0
- 频率 > 50Hz
- 总能耗 ≤ 0

### 4. 数据完整率计算
- 完整率 ≥ 80% → `high` 置信度
- 完整率 50%-80% → `medium` 置信度
- 完整率 < 50% → `low` 置信度

## 输出格式

成功提取和检查时输出:

```json
{
  "extracted_data": {
    "project_region": "华北",
    "monthly_data": [
      {
        "month": 1,
        "total_energy": 20.7948,
        "chiller_supply_temp": 7.0,
        "cooling_pump_freq": 45,
        "cooling_water_temp_diff": 4.5,
        "freezing_pump_freq": 50,
        "freezing_water_temp_diff": 4.5,
        "cooling_tower_outlet_temp": 22
      }
    ]
  },
  "quality_report": {
    "completeness": 0.75,
    "confidence_level": "medium",
    "issues": [
      {
        "field": "monthly_data[3].chiller_supply_temp",
        "severity": "high",
        "type": "missing",
        "message": "4月冷机供水温度缺失"
      }
    ],
    "summary": "数据完整率75%,建议补充缺失月份数据。发现1个高优先级问题。"
  }
}
```

**注意**: `monthly_data` 数组必须包含全部12个月的记录，缺失的月份所有字段设为 null。

## 错误处理

如果遇到以下情况,返回错误 JSON:

```json
{
  "error": true,
  "message": "未能识别调研表中的月度运行数据,请确认上传了正确的文件"
}
```

错误情况包括:
- Excel 文件无法读取
- 找不到包含月度数据的工作表
- 有效能耗数据月份 < 3个月

## 执行流程

### 使用提供的脚本

推荐使用 `scripts/extract_and_check_data.py` 脚本:

```bash
python .claude/skills/extract-and-check-data/scripts/extract_and_check_data.py <survey_excel_path> <output_json_path>
```

脚本会自动完成:
1. 读取 Excel 文件
2. 智能识别包含月度数据的工作表
3. 提取 1-12 月的数据并解析文本值
4. 执行数据质量检查
5. 输出包含提取数据和质量报告的 JSON 文件
