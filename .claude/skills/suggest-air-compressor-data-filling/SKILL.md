---
name: "suggest-air-compressor-data-filling"
description: "为空压机调研表数据提供智能填充建议，基于行业标准和附表查询。当空压机数据提取后需要填充缺失字段时调用。"
---

# 空压机数据填充建议

## 功能描述

基于需求文档的附表和行业标准，为空压机调研表中的缺失字段提供智能填充建议。

## 填充规则

### 1. 基于附表的自动填充

#### 附表1：压力波动与安全裕量
- 根据industryType自动填充safetyMargin和pressureFluctuation
- 电池: 压力波动0.15bar, 安全裕量0.10bar
- 整车及电子: 压力波动0.20bar, 安全裕量0.20bar  
- 钢铁有色: 压力波动0.30bar, 安全裕量0.20bar
- 其他: 压力波动0.20bar, 安全裕量0.20bar

#### 附表2：压缩机功率因子
- 根据brand和manufactureYear自动填充compressorPowerFactor
- 三星/国产/复盛/英格索兰卡梅隆 >10年: 0.32
- 寿力/韩华 任意: 0.34
- 阿特拉斯/英格索兰 5-10年: 0.35
- 阿特拉斯/英格索兰 <5年: 0.36
- 其他或无法确定: 0.35

#### 附表3：各省份工业用电价格
- 根据projectLocation自动填充electricityPrice
- 支持31个省份的参考电价

### 2. 计算字段自动生成

- age: 当前年份 - manufactureYear
- specificPower: (ratedPower × 1.1) / ratedFlow
- averageAnnualOperatingHours: dailyRunningHours × annualRunningDays (默认8500)

### 3. 默认值填充

- annualRunningDays: 330天 (如果缺失)
- dailyRunningHours: 20小时 (如果缺失)
- runningStatus: "运行" (如果缺失且是主要设备)

## 使用方法

```bash
python .claude/skills/suggest-air-compressor-data-filling/scripts/suggest_air_compressor_data_filling.py <提取数据JSON路径> <质量报告JSON路径> <输出建议JSON路径>
```

## 输入格式

- 提取数据JSON: extract_air_compressor_data_llm的输出
- 质量报告JSON: 同上的quality_report部分

## 输出格式

```json
{
  "can_proceed": true,
  "fillable_suggestions": [
    {
      "field": "electricityPrice",
      "original_value": null,
      "suggested_value": 0.62,
      "method": "省份查表",
      "confidence": "high",
      "reasoning": "根据河北省工业用电参考价格"
    }
  ],
  "unfillable_fields": [],
  "summary": "生成了5个填充建议，可以继续计算"
}
```

## 质量保证

- 基于官方标准和行业经验
- 详细的推理说明
- 置信度评估
- 关键字段验证