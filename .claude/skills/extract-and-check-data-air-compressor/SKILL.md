# extract-and-check-data-air-compressor

## 技能描述
从空压机节能调研表中提取原始数据并进行质量检查。

## 输入参数
1. `survey_excel_path` (string): 调研表Excel文件路径
2. `output_json_path` (string): 输出JSON文件路径
3. `original_filename` (string, optional): 原始文件名(用于地区和行业推断)

## 输出结果
```json
{
  "extracted_data": {
    "system_info": {
      "companyName": "企业名称",
      "companyShortName": "企业简称",
      "projectName": "项目名称",
      "projectLocation": "项目所在地（省市）",
      "industryType": "行业类型",
      "totalAnnualEnergyConsumption": 空压系统年度总用量 (kWh),
      "electricityPrice": 平均电价 (元/kWh),
      "alarmPressureLowerLimit": 现有系统报警压力（下限） (bar),
      "averagePressure": 近14天系统平均压力 (bar),
      "dailyRunningHours": 每天开机时间 (小时/天),
      "annualRunningDays": 年运行天数 (天/年)
    },
    "equipment_list": [
      {
        "stationId": "站房编码/名称",
        "equipmentId": "设备编码/名称",
        "equipmentType": "设备类型",
        "brand": "品牌",
        "model": "型号",
        "manufactureYear": 出厂年份,
        "age": 机龄 (年),
        "runningStatus": "运行状态",
        "ratedPower": 铭牌功率 (kW),
        "ratedFlow": 铭牌流量 (m³/min),
        "compressorPowerFactor": 压缩机功率因子 (kW/(m³/min)/bar),
        "specificPower": 比功率 (kW/(m³/min))
      }
    ]
  },
  "quality_report": {
    "completeness": 数据完整率,
    "confidence": 置信度 (%),
    "confidence_level": "高/中/低",
    "issues": [
      {
        "field": "字段名",
        "severity": "critical/high/medium/low",
        "type": "missing/out_of_range/logic_error/duplicate",
        "message": "问题描述"
      }
    ],
    "summary": "质量检查总结",
    "need_rejection": 是否需要打回,
    "rejection_reasons": ["打回原因列表"]
  }
}
```

## 功能说明
1. **数据提取**:
   - 从调研表中提取项目级原始数据（企业信息、用电信息、压力信息等）
   - 从调研表中提取设备级原始数据（空压机清单）
   - 自动计算派生字段（机龄、比功率、压缩机功率因子等）
   - 自动填充缺失的行业类型和电价（基于默认值或地理位置推断）

2. **质量检查**:
   - 检查致命错误（必须打回的情况）
     - 现有系统报警压力缺失或无效
     - 近14天系统平均压力缺失
     - 空压系统年度总用量缺失或无效
     - 所有设备的运行状态均不是"运行"或"备用"
     - 站房编码重复或为空
     - 设备编码重复或为空
   - 检查严重错误（严重影响测算结果）
     - 运行设备的铭牌功率缺失或无效
     - 运行设备的铭牌流量缺失或无效
     - 设备类型缺失
   - 计算数据完整率
   - 计算置信度（基于数据缺失和推算情况）

3. **置信度计算**:
   - 从100%开始扣减
   - 压力曲线数据不足14天: -5%
   - 行业缺失: -15%
   - 每台功率因子使用默认值: -5%/台（最多-30%）
   - 电价缺失: -10%
   - 每天开机时间缺失: -5%
   - 年运行天数缺失: -5%
   - 年运行时间计算异常: -10%
   - 完整率低于60%: -10%
   - 完整率60-80%: -5%

## 示例调用
```python
from core.skill_caller import SkillCaller

caller = SkillCaller()
result = caller.call_skill(
    "extract-and-check-data-air-compressor",
    "input_survey.xlsx",
    "output_result.json",
    "客户_空压系统调研表.xlsx"
)
```

## 错误处理
如果提取或检查过程中发生错误，返回格式如下：
```json
{
  "error": true,
  "message": "错误描述",
  "traceback": "错误堆栈信息"
}
```