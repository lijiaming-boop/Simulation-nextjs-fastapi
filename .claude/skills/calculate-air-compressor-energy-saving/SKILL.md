---
name: "calculate-air-compressor-energy-saving"
description: "计算空压机系统节能率和节能量，基于需求文档的标准计算公式。当空压机数据填充完成后需要进行节能计算时调用。"
---

# 空压机节能率计算

## 功能描述

基于需求文档的标准计算公式，计算空压机系统的节能率和节能量。

## 计算逻辑

### 1. 系统参数计算

#### 系统压缩机功率因子
- 取所有运行和备用空压机的压缩机功率因子求算术平均值
- systemCompressorPowerFactor = Σ(compressorPowerFactor) / 设备数量

#### 系统比功率  
- 取所有运行空压机的比功率求算术平均值
- systemSpecificPower = Σ(specificPower) / 运行设备数量

#### 系统压缩空气流量
- 取所有运行空压机的额定流量求和
- systemCompressedAirFlow = Σ(ratedFlow)

### 2. 节能计算

#### 当前系统能耗
- 基于现有压力和系统参数计算当前能耗

#### 优化后系统能耗  
- 基于智控后压力和优化参数计算节能后能耗

#### 节能率计算
- energySavingRate = (当前能耗 - 优化后能耗) / 当前能耗

#### 节能量计算
- energySaving = 当前能耗 - 优化后能耗

### 3. 范围估算

- 保守估计: 节能率 × 0.8
- 理想情况: 节能率 × 1.2

## 使用方法

```bash
python .claude/skills/calculate-air-compressor-energy-saving/scripts/calculate_air_compressor_energy_saving.py <填充数据JSON路径> <输出结果JSON路径>
```

## 输入格式

填充后的完整数据JSON，包含：
- 项目基本信息
- 系统运行参数  
- 设备清单（含计算字段）
- 填充建议应用后的数据

## 输出格式

```json
{
  "current_total_energy": 45000000,
  "optimized_total_energy": 36000000,
  "energy_saving": 9000000,
  "energy_saving_rate": 0.20,
  "energy_saving_rate_range": "16.0% - 24.0%",
  "energy_saving_rate_min": 0.16,
  "energy_saving_rate_max": 0.24,
  "total_saving_min": 7200000,
  "total_saving_max": 10800000,
  "system_parameters": {
    "systemCompressorPowerFactor": 0.35,
    "systemSpecificPower": 7.2,
    "systemCompressedAirFlow": 480.0
  },
  "calculation_details": {
    "current_pressure": 5.45,
    "optimized_pressure": 5.0,
    "pressure_reduction": 0.45
  }
}
```

## 计算特点

- 基于物理公式的精确计算
- 考虑压力优化的节能效果
- 提供保守和理想两种估算
- 详细的计算过程记录