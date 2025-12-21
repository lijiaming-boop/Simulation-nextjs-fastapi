---
name: extract-survey-data
description: 从中央空调调研表 Excel 中提取月度运行数据
---

# Extract Survey Data Skill

## 任务

从上传的中央空调节能调研表中提取关键数据,输出为结构化 JSON。

## 输入参数

1. `survey_excel_path`: 调研表 Excel 文件路径
2. `output_json_path`: 输出 JSON 文件路径

## 提取字段

**基础信息:**
- `project_region`: 项目地区 (华南/华东/华中/西南/西北/华北)
  - 如果找不到明确标注,尝试从地址、城市推断
  - 如果无法推断,设为 `null`

**月度运行数据** (1-12月,每月一条记录):
- `month`: 月份 (1-12)
- `total_energy`: 冷站月度总能耗 (万kWh) - 通常在调研表"冷站"工作表行47
- `chiller_supply_temp`: 冷机供水温度 (°C) - 行38
- `cooling_pump_freq`: 冷却泵运行频率 (Hz) - 行39
- `cooling_water_temp_diff`: 冷却侧供回水温差 (℃) - 行40
- `freezing_pump_freq`: 冷冻泵运行频率 (Hz) - 行41
- `freezing_water_temp_diff`: 冷冻侧供回水温差 (℃) - 行42
- `cooling_tower_outlet_temp`: 冷却塔出水温度 (℃) - 行44

## 数据处理要点

1. **智能识别**: 不要硬编码 Sheet 名称,利用 LLM 理解能力识别包含月度数据的工作表
2. **文本解析**:
   - 频率字段可能是 "工频50HZ"、"45Hz"、"50" 等格式,提取数值部分
   - 温差字段可能是 "3-5℃"、"4℃"、"4.5" 等格式,提取中间值或单一值
   - 例如: "工频50HZ" → 50, "3-5℃/4℃" → 4.5 (取区间中值或明确值)
3. **缺失值处理**: 空白单元格或无法解析的值标记为 `null`
4. **数据验证**:
   - 如果 12 个月中有 < 3 个月有 total_energy 数据,返回错误
   - 温度应在合理范围 (-20°C ~ 50°C)
   - 频率应在 0-50Hz 范围

## 输出格式

成功提取时输出:
```json
{
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
    },
    {
      "month": 2,
      "total_energy": null,
      "chiller_supply_temp": null,
      "cooling_pump_freq": null,
      "cooling_water_temp_diff": null,
      "freezing_pump_freq": null,
      "freezing_water_temp_diff": null,
      "cooling_tower_outlet_temp": null
    }
  ]
}
```

注意:月度数据数组必须包含全部12个月的记录,缺失的月份所有字段设为 null。

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

1. 读取 Excel 文件 (`survey_excel_path`)
2. 识别包含月度数据的工作表 (通常是"冷站"或类似名称)
3. 提取 1-12 月的数据 (行号可能有偏移,灵活识别列标题和数据位置)
4. 解析文本值为数值
5. 验证数据质量
6. 输出 JSON 到 `output_json_path`

## 重要提示

- 依赖 LLM 的理解能力和推理能力,不要硬编码单元格位置
- 对于文本描述的数值(如"工频50HZ"),要智能解析出数值
- 确保输出的 JSON 格式严格符合上述 Schema
- 所有数值类型字段输出为数字,不要用字符串包裹
