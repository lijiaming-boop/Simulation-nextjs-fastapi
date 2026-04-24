---
name: "extract-air-compressor-data-llm"
description: "使用LLM智能提取空压机调研表数据并进行质量检查。从文本内容中提取结构化数据。当需要从空压机调研表文本中提取结构化数据时调用。"
---

# 空压机数据提取与质量检查 (LLM版)

## 功能描述

使用大语言模型智能分析空压机调研表的文本内容，提取关键信息并转换为结构化数据，同时进行数据质量检查。

## 工作流程

1. **文本预处理**: 接收script提取的文本内容
2. **智能识别**: 使用LLM识别和提取关键字段
3. **数据清理**: 清理和标准化提取的数据
4. **质量检查**: 评估数据完整性和准确性
5. **结果输出**: 生成JSON格式的结构化数据

## LLM提取指令

请从以下文本内容中提取空压机调研表的关键信息，并按照指定的JSON格式输出。

### 输入
- 调研表的文本内容（由script从Excel、Word、PPT等文件中提取）
- 原始文件名（用于上下文参考）

### 输出要求
请严格按照以下JSON格式输出，确保所有字段都包含在内：

```json
{
  "companyName": "企业名称",
  "companyShortName": "企业简称", 
  "projectName": "项目名称",
  "projectLocation": "项目所在地",
  "industryType": "行业类型",
  "totalAnnualEnergyConsumption": 数值,
  "electricityPrice": 数值,
  "alarmPressureLowerLimit": 数值,
  "averagePressure": 数值,
  "dailyRunningHours": 数值,
  "annualRunningDays": 数值,
  "equipmentList": [
    {
      "equipmentNumber": "设备编号",
      "brand": "品牌",
      "model": "型号", 
      "equipmentType": "设备类型",
      "manufactureYear": 数值,
      "runningStatus": "运行状态",
      "ratedPower": 数值,
      "ratedFlow": 数值,
      "station": "所属站房"
    }
  ]
}
```

## 提取指令

### 项目基本信息
- **companyName**: 企业全称，从文档标题、表头或企业信息部分提取
- **companyShortName**: 企业简称，如果没有明确简称则使用全称
- **projectName**: 项目名称，通常包含"空压"、"节能"等关键词
- **projectLocation**: 项目地址，包含省市区详细地址
- **industryType**: 行业类型，如钢铁、化工、电子、汽车等

### 系统运行参数
- **totalAnnualEnergyConsumption**: 年度总用电量，单位万kWh，只提取数值
- **electricityPrice**: 电价，单位元/kWh，只提取数值
- **alarmPressureLowerLimit**: 报警压力下限，单位bar，只提取数值
- **averagePressure**: 平均压力，单位bar，只提取数值
- **dailyRunningHours**: 每天运行小时数，只提取数值
- **annualRunningDays**: 年运行天数，只提取数值

### 设备清单
**equipmentList**: 数组，每个设备包含：
- **equipmentNumber**: 设备编号或名称
- **brand**: 设备品牌
- **model**: 设备型号
- **equipmentType**: 设备类型（螺杆式、离心式、活塞式等）
- **manufactureYear**: 出厂年份，只提取数值
- **runningStatus**: 运行状态（运行、备用、故障、停用）
- **ratedPower**: 铭牌功率，单位kW，只提取数值
- **ratedFlow**: 铭牌流量，单位m³/min，只提取数值
- **station**: 所属站房（如"1#空压站"、"空压一站"等）

## 提取规则

1. **数值提取**: 只提取纯数字，去除单位和其他文字
2. **缺失处理**: 如果字段在文档中找不到，设置为null
3. **文本清理**: 去除多余空格、换行符和特殊字符
4. **类型转换**: 确保数值字段为数字类型，文本字段为字符串类型
5. **设备分组**: 如果有多个站房，按站房分组设备信息

## 质量检查

提取完成后，请评估数据质量：
- **完整性**: 关键字段的填充率
- **准确性**: 数据格式和数值合理性
- **一致性**: 相关字段之间的逻辑关系

请在JSON结果中添加质量报告：
```json
{
  "data": { /* 上述提取的数据 */ },
  "quality_report": {
    "completeness": 0.85,
    "confidence": "high",
    "issues": [
      {
        "field": "字段名",
        "severity": "low|medium|high|critical", 
        "description": "问题描述"
      }
    ]
  }
}
```

## 使用说明

1. **调用方式**: 通过Claude Agent SDK调用此skill
2. **输入参数**: 文本内容和原始文件名
3. **输出格式**: 包含提取数据和质量报告的JSON
4. **处理流程**: 文本分析 → 数据提取 → 质量检查 → 结果输出