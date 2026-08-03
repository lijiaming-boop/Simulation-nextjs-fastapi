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
3. `original_filename` (可选): 原始上传文件名,用于地区推断优先级2

## 提取字段

**基础信息:**
- `project_region`: 项目地区 (华南/华东/华中/西南/西北/华北/吉隆坡/曼谷/罗勇/大城府/槟城/胡志明市/北宁省/马尼拉)
  - **提取方法1（最优先）**: 从"冷站"sheet的"站房名称"字段推断（如"深圳工业园区F栋" → 华南）
  - **提取方法2（次优先）**: 从调研表文件名推断（如"惠州光弘-调研表.xlsx" → 华南）
  - **提取方法3（兜底）**: 从"项目总体情况"sheet扫描所有单元格，匹配省市关键词

- `electricity_price`: 电费单价 (元/kWh)，可选
  - **提取方法**: 扫描"冷站"sheet所有单元格，正则匹配"电单价"/"电价"等关键词后的数值
  - **示例匹配**: "综合电单价：0.6967元/度" → 0.6967
  - **范围校验**: 0.1 ~ 3.0 元/kWh
  - **缺失处理**: 如未提取到，后续由suggest-data-filling根据项目地区查表填充

- `station_type`: 站房类型 (standard/secondary_pump/unsupported)
  - **识别方法**: 基于调研表内容AI智能推断
  - **standard（标准版）**:
    - 仅有一次冷冻泵，无二次泵
    - 不包含热水泵、水蓄冷、中低温机组
    - 典型调研表特征: "冷冻泵"字段只有一行数据，无"一次泵"/"二次泵"分开描述
  - **secondary_pump（二次泵版）**:
    - 冷冻系统包含一次泵和二次泵
    - 典型调研表特征: 冷冻泵分为"一次泵"和"二次泵"两个部分
    - 表格中可能有"一次冷冻泵"/"二次冷冻泵"标签
  - **unsupported（不支持）**:
    - 包含热水泵: 调研表中有"热水泵"相关字段
    - 包含水蓄冷: 调研表中有"蓄冷"/"蓄冰"相关字段
    - 包含中低温机组: 调研表中有"中温"/"低温"机组描述

- `station_type_confidence`: 站房类型识别置信度 (high/medium/low)
  - high: 明确特征，如明确标注"一次泵"/"二次泵"
  - medium: 特征不明显，需推断
  - low: 无法判断，默认为 standard

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
   - **频率字段**: 可能是 "工频50HZ"、"45Hz"、"50" 等格式，提取数值部分
   - **温度/温差字段**: 可能是 "3-5℃"、"4℃"、"4.5"、"7-10度" 等格式
   - **范围值分隔符**: 支持多种分隔符 `-` `~` `/` `,` `|`（如 "7-10"、"7~10"、"7/10"、"7,10"、"7|10"）
   - **范围值智能解析**: 根据月份和字段类型智能选择数值
     - **水泵频率** (`cooling_pump_freq`, `freezing_pump_freq`):
       - 冬季 (12, 1, 2月): 取下限值（设备低负荷运行）
       - 夏季 (6, 7, 8月): 取上限值（设备高负荷运行）
       - 春秋 (3-5, 9-11月): 取平均值（设备中等负荷）
     - **温差字段** (`cooling_water_temp_diff`, `freezing_water_temp_diff`):
       - 冬季: 取下限值（温差较小）
       - 夏季: 取上限值（温差较大）
       - 春秋: 取平均值
     - **供水温度** (`chiller_supply_temp`):
       - 冬季: 取上限值（冬季供水温度较高）
       - 夏季: 取下限值（夏季供水温度较低）
       - 春秋: 取平均值
   - **示例**:
     - "30-50Hz" + 1月（冬季）+ cooling_pump_freq → 30
     - "30/50Hz" + 7月（夏季）+ cooling_pump_freq → 50（斜杠分隔符）
     - "7-10℃" + 1月（冬季）+ chiller_supply_temp → 10
     - "7,10℃" + 7月（夏季）+ chiller_supply_temp → 7（逗号分隔符）
     - "3|5℃" + 4月（春季）+ cooling_water_temp_diff → 4.0（竖线分隔符）
     - "6.5/6℃" + 1月（冬季）+ chiller_supply_temp → 6.5（小数+斜杠）

4. **缺失值处理**: 空白单元格或无法解析的值标记为 `null`

5. **数据验证**: 如果 12 个月中有 < 3 个月有 total_energy 数据，返回错误

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
    "station_type": "standard",
    "station_type_confidence": "medium",
    "station_type_reason": "未检测到二次泵或特殊类型特征，默认为标准站房",
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
# 基本调用（不包含原始文件名）
python .Codex/skills/extract-and-check-data/scripts/extract_and_check_data.py <survey_excel_path> <output_json_path>

# 完整调用（推荐，包含原始文件名用于地区推断）
python .Codex/skills/extract-and-check-data/scripts/extract_and_check_data.py <survey_excel_path> <output_json_path> <original_filename>
```

**重要**: 强烈建议传递第三个参数 `original_filename`（用户上传时的原始文件名），以提高项目地区识别成功率。
示例: `python ... tmp/upload_survey.xlsx tmp/result.json "惠州光弘-调研表.xlsx"`

脚本会自动完成:
1. 读取 Excel 文件
2. 智能识别包含月度数据的工作表
3. 提取 1-12 月的数据并解析文本值
4. 使用三级优先级提取项目地区（站房名称 → 原始文件名 → 项目总体情况sheet）
5. 执行数据质量检查
6. 输出包含提取数据和质量报告的 JSON 文件
