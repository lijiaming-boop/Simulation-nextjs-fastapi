#!/usr/bin/env python3
"""
空压机节能率计算器
基于需求文档的标准计算公式进行节能率和节能量计算
"""

import json
import sys
import math
from pathlib import Path
from typing import Dict, List, Any, Optional

# 常量定义
ATMOSPHERIC_PRESSURE = 1.0  # bar，大气压力
MAIN_PIPELINE_DIRECT_CONSUMPTION_RATIO = 70  # %，主管网直接耗量比例


class AirCompressorEnergyCalculator:
    """空压机节能率计算器"""
    
    def __init__(self):
        """初始化计算器"""
        self.calculation_details = {}
        self.intermediate_data = {}  # 新增：保存中间数据
    
    def calculate_energy_saving(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """计算空压机系统节能率"""
        
        print(f"🔢 [节能计算] 开始计算空压机系统节能率...")
        
        # 初始化中间数据
        self.intermediate_data = {
            "calculation_steps": [],
            "input_data": {},
            "calculated_parameters": {},
            "energy_calculation": {},
            "final_results": {}
        }
        
        # 保存原始输入数据
        self.intermediate_data["input_data"]["raw_data"] = raw_data
        
        # 第一步：计算第二部分输入字段定义
        calculation_inputs = self._calculate_input_fields(raw_data)
        self.intermediate_data["calculated_parameters"]["calculation_inputs"] = calculation_inputs
        self._add_calculation_step("第一步", "计算第二部分输入字段定义", calculation_inputs)
        
        # 第二步：提取项目和设备数据
        project_data = self._extract_project_data(raw_data, calculation_inputs)
        equipment_level = raw_data.get("rawData", {}).get("equipmentLevel", [])
        equipment_data = self._calculate_equipment_derived_fields(equipment_level)
        self.intermediate_data["calculated_parameters"]["project_data"] = project_data
        self.intermediate_data["calculated_parameters"]["equipment_data"] = equipment_data
        self._add_calculation_step("第二步", "提取项目和设备数据", {
            "project_data": project_data,
            "equipment_count": len(equipment_data)
        })
        
        # 第三步：计算系统参数
        system_params = self._calculate_system_parameters(equipment_data)
        self.intermediate_data["calculated_parameters"]["system_params"] = system_params
        self._add_calculation_step("第三步", "计算系统参数", system_params)
        
        # 第四步：计算当前系统能耗
        current_energy = self._calculate_current_energy_consumption(project_data, system_params)
        self.intermediate_data["energy_calculation"]["current_energy"] = {
            "value": current_energy,
            "details": self.calculation_details.copy()
        }
        self._add_calculation_step("第四步", "计算当前系统能耗", {
            "current_total_energy": current_energy,
            "unit": "kWh/年"
        })
        
        # 第五步：计算优化后系统能耗
        optimized_energy = self._calculate_optimized_energy_consumption(project_data, system_params)
        self.intermediate_data["energy_calculation"]["optimized_energy"] = {
            "value": optimized_energy,
            "details": self.calculation_details.copy()
        }
        self._add_calculation_step("第五步", "计算优化后系统能耗", {
            "optimized_total_energy": optimized_energy,
            "unit": "kWh/年"
        })
        
        # 第六步：计算节能率和节能量
        energy_saving = current_energy - optimized_energy
        energy_saving_rate = energy_saving / current_energy if current_energy > 0 else 0
        
        # 计算范围估算
        energy_saving_rate_min = energy_saving_rate * 0.8
        energy_saving_rate_max = energy_saving_rate * 1.2
        total_saving_min = energy_saving * 0.8
        total_saving_max = energy_saving * 1.2
        
        # 保存最终结果
        final_results = {
            "current_total_energy": current_energy,
            "optimized_total_energy": optimized_energy,
            "energy_saving": energy_saving,
            "energy_saving_rate": energy_saving_rate,
            "energy_saving_rate_range": f"{energy_saving_rate_min * 100:.1f}% - {energy_saving_rate_max * 100:.1f}%",
            "energy_saving_rate_min": energy_saving_rate_min,
            "energy_saving_rate_max": energy_saving_rate_max,
            "total_saving_min": total_saving_min,
            "total_saving_max": total_saving_max
        }
        self.intermediate_data["final_results"] = final_results
        self._add_calculation_step("第六步", "计算节能率和节能量", final_results)
        
        # 构建结果
        result = {
            "current_total_energy": current_energy,
            "optimized_total_energy": optimized_energy,
            "energy_saving": energy_saving,
            "energy_saving_rate": energy_saving_rate,
            "energy_saving_rate_range": f"{energy_saving_rate_min * 100:.1f}% - {energy_saving_rate_max * 100:.1f}%",
            "energy_saving_rate_min": energy_saving_rate_min,
            "energy_saving_rate_max": energy_saving_rate_max,
            "total_saving_min": total_saving_min,
            "total_saving_max": total_saving_max,
            "system_parameters": system_params,
            "calculation_details": self.calculation_details,
            "completeness": raw_data.get("completeness", 1.0),
            "filled_count": len(raw_data.get("fillable_suggestions", [])),
            "calculation_method": "air_compressor_standard",
            "equipment_analysis": self._analyze_equipment(equipment_data)
        }
        
        print(f"✅ [节能计算] 计算完成")
        print(f"📊 当前系统能耗: {current_energy / 10000:.1f} 万kWh/年")
        print(f"📊 优化后能耗: {optimized_energy / 10000:.1f} 万kWh/年")
        print(f"📊 节能量: {energy_saving / 10000:.1f} 万kWh/年")
        print(f"📊 节能率: {energy_saving_rate * 100:.1f}%")
        
        return result
    
    def _add_calculation_step(self, step_name: str, step_description: str, step_data: Any):
        """添加计算步骤到中间数据"""
        self.intermediate_data["calculation_steps"].append({
            "step": step_name,
            "description": step_description,
            "data": step_data
        })
    
    def _calculate_input_fields(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """计算第二部分：输入字段定义（计算逻辑的直接输入）"""
        
        print(f"🧮 [输入字段计算] 计算第二部分输入字段定义...")
        
        # 提取原始数据
        project_level = raw_data.get("rawData", {}).get("projectLevel", {})
        equipment_level = raw_data.get("rawData", {}).get("equipmentLevel", [])
        
        # 基础字段（直接来源于原始数据）
        alarm_pressure = project_level.get("alarmPressureLowerLimit")
        average_pressure = project_level.get("averagePressure")
        total_annual_energy = project_level.get("totalAnnualEnergyConsumption")
        electricity_price = project_level.get("electricityPrice")
        daily_hours = project_level.get("dailyRunningHours")
        annual_days = project_level.get("annualRunningDays")
        industry_type = project_level.get("industryType", "其他")
        
        # 查表字段（根据行业类型查表）
        safety_margin, pressure_fluctuation = self._lookup_industry_parameters(industry_type)
        
        # 计算派生的设备字段
        processed_equipment = self._calculate_equipment_derived_fields(equipment_level)
        
        # 计算字段
        post_control_pressure = None
        if alarm_pressure is not None:
            post_control_pressure = alarm_pressure + safety_margin + pressure_fluctuation
        
        # 计算系统级参数
        system_compressor_power_factor = self._calculate_system_compressor_power_factor(processed_equipment)
        system_specific_power = self._calculate_system_specific_power(processed_equipment)
        system_compressed_air_flow = self._calculate_system_compressed_air_flow(processed_equipment)
        
        # 计算平均年运行时间
        average_annual_hours = self._calculate_average_annual_hours(daily_hours, annual_days)
        
        calculation_inputs = {
            "alarmPressureLowerLimit": alarm_pressure,
            "averagePressure": average_pressure,
            "safetyMargin": safety_margin,
            "pressureFluctuation": pressure_fluctuation,
            "postControlAveragePressure": post_control_pressure,
            "systemCompressorPowerFactor": system_compressor_power_factor,
            "systemSpecificPower": system_specific_power,
            "systemCompressedAirFlow": system_compressed_air_flow,
            "totalAnnualEnergyConsumption": total_annual_energy,
            "averageAnnualOperatingHours": average_annual_hours,
            "electricityPrice": electricity_price,
            "mainPipelineDirectConsumptionRatio": MAIN_PIPELINE_DIRECT_CONSUMPTION_RATIO
        }
        
        print(f"📊 智控后平均压力: {post_control_pressure} bar")
        print(f"📊 系统压缩机功率因子: {system_compressor_power_factor}")
        print(f"📊 系统比功率: {system_specific_power} kW/(m³/min)")
        print(f"📊 系统压缩空气流量: {system_compressed_air_flow} m³/min")
        
        return calculation_inputs
    
    def _lookup_industry_parameters(self, industry_type: str) -> tuple:
        """根据行业类型查询压力波动和安全裕量"""
        
        industry_params = {
            "电池": (0.10, 0.15),  # (安全保护裕量, 压力波动)
            "整车及电子": (0.20, 0.20),
            "钢铁有色": (0.20, 0.30),
            "其他": (0.20, 0.20)  # 默认值
        }
        
        return industry_params.get(industry_type, industry_params["其他"])
    
    def _calculate_equipment_derived_fields(self, equipment_level: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """计算设备级派生字段"""
        
        processed_equipment = []
        current_year = 2026  # 当前年份
        
        for equipment in equipment_level:
            processed_eq = equipment.copy()
            
            # 计算机龄
            manufacture_year = equipment.get("manufactureYear")
            if manufacture_year:
                processed_eq["age"] = current_year - manufacture_year
            else:
                processed_eq["age"] = 10  # 默认机龄
            
            # 计算压缩机功率因子
            brand = equipment.get("brand", "")
            age = processed_eq["age"]
            processed_eq["compressorPowerFactor"] = self._lookup_compressor_power_factor(brand, age)
            
            # 计算比功率
            rated_power = equipment.get("ratedPower", 0)
            rated_flow = equipment.get("ratedFlow", 1)  # 避免除零
            if rated_flow > 0:
                processed_eq["specificPower"] = (rated_power * 1.1) / rated_flow
            else:
                processed_eq["specificPower"] = 7.0  # 默认比功率
            
            processed_equipment.append(processed_eq)
        
        return processed_equipment
    
    def _lookup_compressor_power_factor(self, brand: str, age: int) -> float:
        """根据品牌和机龄查询压缩机功率因子"""
        
        brand_lower = brand.lower() if brand else ""
        
        # 根据附表2查询
        if any(b in brand_lower for b in ["三星", "国产", "复盛", "英格索兰卡梅隆"]) and age > 10:
            return 0.32
        elif any(b in brand_lower for b in ["寿力", "韩华"]):
            return 0.34
        elif any(b in brand_lower for b in ["阿特拉斯", "英格索兰"]):
            if age < 5:
                return 0.36
            elif 5 <= age <= 10:
                return 0.35
            else:
                return 0.35
        else:
            return 0.35  # 默认值
    
    def _calculate_system_compressor_power_factor(self, equipment_list: List[Dict[str, Any]]) -> float:
        """计算系统压缩机功率因子（运行设备的流量加权平均值）"""
        
        running_equipment = [
            eq for eq in equipment_list 
            if eq.get("runningStatus") == "运行"
        ]
        
        if not running_equipment:
            return 0.35  # 默认值
        
        # 流量加权平均
        total_weighted_factor = 0.0
        total_flow = 0.0
        
        for eq in running_equipment:
            flow = eq.get("ratedFlow", 0)
            factor = eq.get("compressorPowerFactor", 0.35)
            total_weighted_factor += flow * factor
            total_flow += flow
        
        if total_flow == 0:
            return 0.35
        
        return round(total_weighted_factor / total_flow, 3)
    
    def _calculate_system_specific_power(self, equipment_list: List[Dict[str, Any]]) -> float:
        """计算系统比功率（运行设备的流量加权平均值）"""
        
        running_equipment = [
            eq for eq in equipment_list 
            if eq.get("runningStatus") == "运行"
        ]
        
        if not running_equipment:
            return 7.0  # 默认值
        
        # 流量加权平均
        total_weighted_power = 0.0
        total_flow = 0.0
        
        for eq in running_equipment:
            flow = eq.get("ratedFlow", 0)
            spec_power = eq.get("specificPower", 7.0)
            total_weighted_power += flow * spec_power
            total_flow += flow
        
        if total_flow == 0:
            return 7.0
        
        return round(total_weighted_power / total_flow, 2)
        
    def _calculate_system_compressed_air_flow(self, equipment_list: List[Dict[str, Any]]) -> float:
        """计算系统压缩空气流量（仅运行设备的流量求和）"""
        
        running_equipment = [
            eq for eq in equipment_list 
            if eq.get("runningStatus") == "运行"
        ]
        
        total_flow = sum(eq.get("ratedFlow", 0) for eq in running_equipment)
        return round(total_flow, 1)
    
    def _calculate_average_annual_hours(self, daily_hours: Optional[float], annual_days: Optional[int]) -> float:
        """计算平均年运行时间"""
        
        if daily_hours and annual_days:
            calculated_hours = daily_hours * annual_days
            if 0 < calculated_hours <= 8760:
                return calculated_hours
        
        return 8500  # 默认值
    
    def _extract_project_data(self, raw_data: Dict[str, Any], calculation_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """提取项目级数据"""
        
        # 从计算输入字段中获取数据
        return {
            "totalAnnualEnergyConsumption": calculation_inputs.get("totalAnnualEnergyConsumption", 0),
            "electricityPrice": calculation_inputs.get("electricityPrice", 0.6),
            "alarmPressureLowerLimit": calculation_inputs.get("alarmPressureLowerLimit", 5.0),
            "averagePressure": calculation_inputs.get("averagePressure", 6.0),
            "averageAnnualOperatingHours": calculation_inputs.get("averageAnnualOperatingHours", 8500),
            "safetyMargin": calculation_inputs.get("safetyMargin", 0.2),
            "pressureFluctuation": calculation_inputs.get("pressureFluctuation", 0.2),
            "postControlAveragePressure": calculation_inputs.get("postControlAveragePressure", 5.4),
            "mainPipelineDirectConsumptionRatio": calculation_inputs.get("mainPipelineDirectConsumptionRatio", 70)
        }
    
    def _calculate_system_parameters(self, equipment_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算系统级参数"""
        
        print(f"🔧 [系统参数] 计算系统级参数...")
        
        # 筛选运行和备用设备
        running_equipment = [eq for eq in equipment_data if eq["runningStatus"] in ["运行", "备用"]]
        active_equipment = [eq for eq in equipment_data if eq["runningStatus"] == "运行"]
        
        if not running_equipment:
            raise ValueError("没有找到运行或备用状态的空压机设备")
        
        if not active_equipment:
            raise ValueError("没有找到运行状态的空压机设备")
        
        # 使用流量加权平均计算系统参数
        system_compressor_power_factor = self._calculate_system_compressor_power_factor(equipment_data)
        system_specific_power = self._calculate_system_specific_power(equipment_data)
        
        # 计算系统压缩空气流量（仅运行设备的流量求和）
        system_compressed_air_flow = sum(eq["ratedFlow"] for eq in active_equipment)
        
        system_params = {
            "systemCompressorPowerFactor": round(system_compressor_power_factor, 3),
            "systemSpecificPower": round(system_specific_power, 2),
            "systemCompressedAirFlow": round(system_compressed_air_flow, 1),
            "runningEquipmentCount": len(active_equipment),
            "backupEquipmentCount": len([eq for eq in running_equipment if eq["runningStatus"] == "备用"]),
            "totalEquipmentCount": len(equipment_data)
        }
        
        print(f"📊 系统压缩机功率因子: {system_params['systemCompressorPowerFactor']}")
        print(f"📊 系统比功率: {system_params['systemSpecificPower']} kW/(m³/min)")
        print(f"📊 系统压缩空气流量: {system_params['systemCompressedAirFlow']} m³/min")
        
        return system_params
    
    def _calculate_current_energy_consumption(self, project_data: Dict[str, Any], system_params: Dict[str, Any]) -> float:
        """计算当前系统能耗"""
        
        print(f"⚡ [当前能耗] 计算当前系统能耗...")
        
        # 基础参数
        current_pressure = project_data["averagePressure"]  # bar
        annual_energy = project_data["totalAnnualEnergyConsumption"]  # kWh
        
        # 记录计算详情
        self.calculation_details["current_pressure"] = current_pressure
        self.calculation_details["annual_energy_from_survey"] = annual_energy
        
        print(f"📊 调研表年度总能耗: {annual_energy / 10000:.1f} 万kWh")
        print(f"📊 当前系统平均压力: {current_pressure} bar")
        
        # 直接使用调研表中的年度总能耗作为当前系统能耗
        # 这是最准确的基准值
        current_total_energy = annual_energy
        
        self.calculation_details["current_calculation_method"] = "直接使用调研表年度总能耗"
        
        return current_total_energy
    
    def _calculate_optimized_energy_consumption(self, project_data: Dict[str, Any], system_params: Dict[str, Any]) -> float:
        """计算优化后系统能耗（按照需求文档公式）"""
        
        print(f"⚡ [优化能耗] 计算优化后系统能耗...")
        
        # 基础参数
        current_pressure = project_data["averagePressure"]  # bar
        optimized_pressure = project_data["postControlAveragePressure"]  # bar
        annual_energy = project_data["totalAnnualEnergyConsumption"]  # kWh
        annual_hours = project_data["averageAnnualOperatingHours"]  # 小时/年
        direct_consumption_ratio = project_data["mainPipelineDirectConsumptionRatio"] / 100  # 转换为小数
        
        # 系统参数
        system_power_factor = system_params["systemCompressorPowerFactor"]  # kW/(m³/min)/bar
        system_specific_power = system_params["systemSpecificPower"]  # kW/(m³/min)
        system_flow = system_params["systemCompressedAirFlow"]  # m³/min
        
        # 检查压力合理性：如果当前压力低于优化后压力，说明当前系统已经很高效
        if current_pressure <= optimized_pressure:
            print(f"⚠️  当前压力({current_pressure} bar)已经接近或低于优化目标({optimized_pressure} bar)")
            # 在这种情况下，节能主要来自控制优化，而非压力降低
            control_optimization_factor = 0.9  # 10%的控制优化节能
            optimized_total_energy = annual_energy * control_optimization_factor
            
            self.calculation_details["optimization_type"] = "控制优化为主"
            self.calculation_details["control_optimization_factor"] = control_optimization_factor
        else:
            # ===== 按照需求文档公式计算 =====
            
            # 6.1.2 压力降低值
            deltaPressure = current_pressure - optimized_pressure  # bar
            
            # 6.1.3 空气消耗降低百分比
            airReductionPercent = 100 * (1 - (optimized_pressure + ATMOSPHERIC_PRESSURE) / (current_pressure + ATMOSPHERIC_PRESSURE))
            
            # 6.1.4 空气流量降低值
            deltaFlowRate = system_flow * (airReductionPercent / 100) * direct_consumption_ratio  # m³/min
            
            # 6.3.1 压力降低节能量 (MWh)
            E_pressure = deltaPressure * system_power_factor * system_flow * annual_hours / 1000
            
            # 6.3.2 空气消耗降低节能量 (MWh)
            E_air = deltaFlowRate * system_specific_power * annual_hours / 1000
            
            # 6.3.3 总节能量 (MWh)
            E_total_MWh = E_pressure + E_air
            
            # 总节能量 (kWh)
            total_saving_kWh = E_total_MWh * 1000
            
            # 优化后能耗
            optimized_total_energy = annual_energy - total_saving_kWh
            
            # 记录计算详情
            self.calculation_details["optimization_type"] = "压力优化为主"
            self.calculation_details["deltaPressure"] = deltaPressure
            self.calculation_details["airReductionPercent"] = airReductionPercent
            self.calculation_details["deltaFlowRate"] = deltaFlowRate
            self.calculation_details["E_pressure_MWh"] = E_pressure
            self.calculation_details["E_air_MWh"] = E_air
            self.calculation_details["E_total_MWh"] = E_total_MWh
        
        # 记录通用计算详情
        self.calculation_details.update({
            "optimized_pressure": optimized_pressure,
            "pressure_reduction": current_pressure - optimized_pressure,
            "optimized_calculation_method": "按照需求文档公式计算"
        })
        
        print(f"📊 优化后系统平均压力: {optimized_pressure} bar")
        print(f"📊 压力变化: {current_pressure - optimized_pressure:.2f} bar")
        
        # 根据优化类型显示不同信息
        if "control_optimization_factor" in self.calculation_details:
            print(f"📊 控制优化系数: {self.calculation_details['control_optimization_factor']:.3f}")
        else:
            print(f"📊 压力降低值(deltaPressure): {self.calculation_details.get('deltaPressure', 0):.2f} bar")
            print(f"📊 空气消耗降低百分比: {self.calculation_details.get('airReductionPercent', 0):.2f}%")
            print(f"📊 空气流量降低值(deltaFlowRate): {self.calculation_details.get('deltaFlowRate', 0):.2f} m³/min")
            print(f"📊 压力降低节能量(E_pressure): {self.calculation_details.get('E_pressure_MWh', 0):.2f} MWh")
            print(f"📊 空气消耗降低节能量(E_air): {self.calculation_details.get('E_air_MWh', 0):.2f} MWh")
            print(f"📊 总节能量(E_total): {self.calculation_details.get('E_total_MWh', 0):.2f} MWh")
        
        return optimized_total_energy
    
    def _analyze_equipment(self, equipment_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析设备状况"""
        
        analysis = {
            "total_air_compressors": len(equipment_data),
            "total_power": 0.0,
            "average_efficiency": 0.0,
            "equipment_types": {},
            "brand_distribution": {},
            "age_distribution": {}
        }
        
        if not equipment_data:
            return analysis
        
        # 统计运行设备
        running_equipment = [eq for eq in equipment_data if eq["runningStatus"] == "运行"]
        
        if running_equipment:
            # 总功率
            total_power = sum(eq["ratedPower"] for eq in running_equipment)
            analysis["total_power"] = total_power
            
            # 平均效率（基于比功率估算）
            avg_specific_power = sum(eq["specificPower"] for eq in running_equipment) / len(running_equipment)
            # 效率估算：比功率越低效率越高，参考值7.0对应80%效率
            estimated_efficiency = max(0.6, min(0.9, 0.8 * (7.0 / avg_specific_power)))
            analysis["average_efficiency"] = estimated_efficiency
        
        # 设备类型分布
        for eq in equipment_data:
            eq_type = eq["equipmentType"]
            analysis["equipment_types"][eq_type] = analysis["equipment_types"].get(eq_type, 0) + 1
        
        # 品牌分布
        for eq in equipment_data:
            brand = eq["brand"] or "未知品牌"
            analysis["brand_distribution"][brand] = analysis["brand_distribution"].get(brand, 0) + 1
        
        # 机龄分布
        for eq in equipment_data:
            age = eq["age"]
            if age < 5:
                age_group = "5年以下"
            elif age < 10:
                age_group = "5-10年"
            else:
                age_group = "10年以上"
            
            analysis["age_distribution"][age_group] = analysis["age_distribution"].get(age_group, 0) + 1
        
        return analysis
    
    def _calculate_energy_saving_details(self, project_data: Dict[str, Any], system_params: Dict[str, Any]) -> Dict[str, Any]:
        """计算详细的节能分析"""
        
        current_pressure = project_data["averagePressure"]
        optimized_pressure = project_data["postControlAveragePressure"]
        annual_hours = project_data["averageAnnualOperatingHours"]
        system_flow = system_params["systemCompressedAirFlow"]
        
        # 计算压力节能潜力
        pressure_reduction = current_pressure - optimized_pressure
        pressure_saving_potential = pressure_reduction / current_pressure
        
        # 计算流量相关节能
        # 基于主管网直接耗量比例
        direct_consumption_ratio = project_data["mainPipelineDirectConsumptionRatio"] / 100
        
        details = {
            "pressure_analysis": {
                "current_pressure": current_pressure,
                "optimized_pressure": optimized_pressure,
                "pressure_reduction": pressure_reduction,
                "pressure_saving_potential": pressure_saving_potential
            },
            "flow_analysis": {
                "system_flow": system_flow,
                "direct_consumption_ratio": direct_consumption_ratio,
                "annual_operating_hours": annual_hours
            },
            "energy_breakdown": {
                "compression_energy_saving": "基于压力优化的节能",
                "control_optimization_saving": "智能控制优化节能",
                "system_efficiency_improvement": "系统效率提升节能"
            }
        }
        
        return details


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print("用法: python calculate_air_compressor_energy_saving.py <原始数据JSON路径> <输出结果JSON路径>")
        sys.exit(1)
    
    raw_data_path = sys.argv[1]
    output_path = sys.argv[2]
    
    # 生成中间数据文件路径
    output_path_obj = Path(output_path)
    intermediate_data_path = output_path_obj.parent / f"{output_path_obj.stem}_intermediate.json"
    
    print(f"🚀 [空压节能计算] 开始计算节能率")
    print(f"📁 [空压节能计算] 原始数据: {raw_data_path}")
    print(f"📁 [空压节能计算] 输出路径: {output_path}")
    print(f"📁 [空压节能计算] 中间数据路径: {intermediate_data_path}")
    
    try:
        # 读取原始数据
        with open(raw_data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # 执行节能计算
        calculator = AirCompressorEnergyCalculator()
        result = calculator.calculate_energy_saving(raw_data)
        
        # 保存最终结果
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 保存中间数据
        intermediate_data = {
            "calculation_metadata": {
                "input_file": raw_data_path,
                "output_file": output_path,
                "calculation_method": "air_compressor_standard",
                "timestamp": __import__('datetime').datetime.now().isoformat()
            },
            "intermediate_data": calculator.intermediate_data
        }
        
        with open(intermediate_data_path, 'w', encoding='utf-8') as f:
            json.dump(intermediate_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ [空压节能计算] 计算完成")
        print(f"📄 结果已保存到: {output_path}")
        print(f"📊 中间数据已保存到: {intermediate_data_path}")
        
    except Exception as e:
        print(f"❌ [空压节能计算] 计算失败: {str(e)}")
        
        # 保存错误结果
        error_result = {
            "error": True,
            "message": f"节能计算失败: {str(e)}",
            "current_total_energy": 0,
            "optimized_total_energy": 0,
            "energy_saving": 0,
            "energy_saving_rate": 0,
            "energy_saving_rate_range": "0% - 0%",
            "calculation_method": "failed"
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)


if __name__ == "__main__":
    main()