---
name: "generate-air-compressor-report"
description: "生成空压系统数智化升级方案报告和报价单。当空压机节能计算完成后需要生成方案报告和报价单时调用。"
---

# 空压机报告生成技能

## 功能描述

基于空压机节能计算结果，生成专业的方案报告和报价单，包括：
- Word格式的空压系统数智化升级方案报告
- Excel格式的空压云智控报价单

## 输入参数

1. `extracted_data_path`: 提取的数据JSON文件路径
2. `calculation_result_path`: 节能计算结果JSON文件路径
3. `output_dir`: 输出目录路径

## 输出文件

### 1. 空压系统数智化升级方案报告
- 文件名格式：`空压系统数智化升级方案_YYYYMMDD_HHMMSS.docx`
- 基于模板：`00_sample/模板测算表/空压系统数智化升级方案模板.docx`

### 2. 空压云智控报价单
- 文件名格式：`2026年空压云智控报价单_YYYYMMDD_HHMMSS.xlsx`
- 基于模板：`00_sample/模板测算表/2026年空压云智控报价模板.xlsx`

## 替换占位符

### Word报告模板占位符
- 项目信息：`{companyName}`, `{projectLocation}`, `{industryType}`
- 节能数据：`{energySavingRate}`, `{currentEnergy}`, `{optimizedEnergy}`, `{annualSaving}`
- 系统参数：`{systemCompressorPowerFactor}`, `{systemSpecificPower}`, `{systemCompressedAirFlow}`

### Excel报价单模板占位符
- 项目信息：`{companyName}`, `{projectLocation}`, `{industryType}`
- 节能数据：`{energySavingRate}`, `{currentEnergy}`, `{optimizedEnergy}`, `{annualSaving}`
- 系统参数：`{systemCompressorPowerFactor}`, `{systemSpecificPower}`, `{systemCompressedAirFlow}`
- 设备信息：`{equipmentCount}`
- 电价信息：`{electricityPrice}`
- 压力信息：`{alarmPressure}`, `{averagePressure}`

## 使用示例

```bash
python .claude/skills/generate-air-compressor-report/scripts/generate_air_compressor_report.py \
    /path/to/extracted_data.json \
    /path/to/calculation_result.json \
    /path/to/output/directory
```

## 依赖库

- `python-docx`: Word文档处理
- `openpyxl`: Excel文件处理

安装依赖：
```bash
pip install python-docx openpyxl
```

## 错误处理

- 如果模板文件不存在，会提示错误信息
- 如果数据不完整，会使用默认值填充
- 如果依赖库未安装，会提示安装命令

## 注意事项

1. 确保模板文件存在于正确路径
2. 确保输入的数据文件格式正确
3. 确保输出目录有写入权限
4. 生成的报告文件会包含时间戳，避免重名覆盖