---
name: "extract-air-compressor-data-llm"
description: "使用LLM智能提取空压机调研表数据并进行质量检查。支持Excel、Word、PPT等多种格式。当需要从空压机调研表中提取结构化数据时调用。"
---

# 空压机数据提取与质量检查 (LLM版)

## 功能描述

使用大语言模型智能提取空压机调研表中的关键信息，支持多种文件格式，并进行数据质量检查。

## 支持格式

- Excel文件 (.xlsx, .xls)
- Word文档 (.docx, .doc)
- PowerPoint演示文稿 (.pptx, .ppt)

## 提取字段

### 项目基本信息
- 企业名称 (companyName)
- 企业简称 (companyShortName)
- 项目名称 (projectName)
- 项目所在地 (projectLocation)
- 行业类型 (industryType)

### 系统参数
- 空压系统年度总用量 (totalAnnualEnergyConsumption) - 万kWh
- 平均电价 (electricityPrice) - 元/kWh
- 现有系统报警压力下限 (alarmPressureLowerLimit) - bar
- 近14天系统平均压力 (averagePressure) - bar
- 每天开机时间 (dailyRunningHours) - 小时
- 年运行天数 (annualRunningDays) - 天

### 设备清单
每个设备包含：
- 设备编号 (equipmentNumber)
- 品牌 (brand)
- 型号 (model)
- 设备类型 (equipmentType) - 螺杆式/离心式
- 铭牌功率 (ratedPower) - kW
- 铭牌流量 (ratedFlow) - m³/min
- 所属站房 (station)

## 使用方法

```bash
python .claude/skills/extract-air-compressor-data-llm/scripts/extract_air_compressor_data_llm.py <输入文件路径> <输出JSON路径> [原始文件名]
```

## 输出格式

```json
{
  "error": false,
  "extracted_data": {
    "companyName": "企业名称",
    "projectName": "项目名称",
    "totalAnnualEnergyConsumption": 4554,
    "equipmentList": [
      {
        "equipmentNumber": "AC-001",
        "brand": "阿特拉斯",
        "model": "GA75",
        "equipmentType": "螺杆式",
        "ratedPower": 75,
        "ratedFlow": 12.5
      }
    ]
  },
  "quality_report": {
    "completeness": 0.85,
    "confidence_level": "high",
    "issues": [],
    "summary": "数据完整度85%，质量良好"
  }
}
```

## 质量检查

- 数据完整性检查
- 数值范围验证
- 逻辑一致性验证
- 置信度评估

## 错误处理

- 文件格式不支持
- 文件损坏或无法读取
- 数据提取失败
- LLM调用异常