#!/usr/bin/env python3
"""
空压机数据填充建议生成器
基于需求文档的附表和行业标准提供智能填充建议
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import datetime

# 附表1：压力波动与安全裕量查询表
PRESSURE_SAFETY_TABLE = {
    "电池": {"pressure_fluctuation": 0.15, "safety_margin": 0.10},
    "整车及电子": {"pressure_fluctuation": 0.20, "safety_margin": 0.20},
    "钢铁有色": {"pressure_fluctuation": 0.30, "safety_margin": 0.20},
    "钢铁": {"pressure_fluctuation": 0.30, "safety_margin": 0.20},  # 钢铁简写
    "有色": {"pressure_fluctuation": 0.30, "safety_margin": 0.20},  # 有色简写
    "其他": {"pressure_fluctuation": 0.20, "safety_margin": 0.20}  # 默认值
}

# 附表2：压缩机功率因子查询表
COMPRESSOR_POWER_FACTOR_TABLE = {
    "三星": {"age_threshold": 10, "old_factor": 0.32, "new_factor": 0.32},
    "国产": {"age_threshold": 10, "old_factor": 0.32, "new_factor": 0.32},
    "复盛": {"age_threshold": 10, "old_factor": 0.32, "new_factor": 0.32},
    "英格索兰卡梅隆": {"age_threshold": 10, "old_factor": 0.32, "new_factor": 0.32},
    "寿力": {"age_threshold": None, "old_factor": 0.34, "new_factor": 0.34},
    "韩华": {"age_threshold": None, "old_factor": 0.34, "new_factor": 0.34},
    "阿特拉斯": {"age_threshold": 5, "old_factor": 0.35, "new_factor": 0.36},
    "英格索兰": {"age_threshold": 5, "old_factor": 0.35, "new_factor": 0.36},
    "默认": {"age_threshold": None, "old_factor": 0.35, "new_factor": 0.35}
}

# 附表3：各省份工业用电电价参考表
ELECTRICITY_PRICE_TABLE = {
    "北京": 0.64, "天津": 0.69, "河北": 0.62, "山西": 0.55, "内蒙古": 0.43,
    "辽宁": 0.61, "吉林": 0.59, "黑龙江": 0.61, "上海": 0.75, "江苏": 0.70,
    "浙江": 0.73, "安徽": 0.65, "福建": 0.63, "江西": 0.62, "山东": 0.74,
    "河南": 0.61, "湖北": 0.64, "湖南": 0.65, "广东": 0.69, "广西": 0.55,
    "海南": 0.63, "重庆": 0.65, "四川": 0.58, "贵州": 0.52, "云南": 0.45,
    "西藏": 0.50, "陕西": 0.55, "甘肃": 0.48, "青海": 0.42, "宁夏": 0.45,
    "新疆": 0.40
}

# 常量定义
DEFAULT_ANNUAL_RUNNING_DAYS = 330
DEFAULT_DAILY_RUNNING_HOURS = 20
DEFAULT_ANNUAL_OPERATING_HOURS = 8500
RATED_POWER_FACTOR = 1.1  # 铭牌功率系数
MAIN_PIPELINE_DIRECT_CONSUMPTION_RATIO = 70  # 主管网直接耗量比例


class AirCompressorDataFiller:
    """空压机数据填充建议生成器"""
    
    def __init__(self):
        """初始化填充器"""
        self.current_year = datetime.datetime.now().year
        self.suggestions = []
        self.unfillable_fields = []
    
    def generate_suggestions(self, extracted_data: Dict[str, Any], quality_report: Dict[str, Any]) -> Dict[str, Any]:
        """生成填充建议"""
        
        print(f"🔍 [数据填充] 开始分析缺失字段...")
        
        # 重置建议列表
        self.suggestions = []
        self.unfillable_fields = []
        
        # 1. 填充项目级字段
        self._suggest_project_level_fields(extracted_data)
        
        # 2. 填充设备级字段
        self._suggest_equipment_level_fields(extracted_data)
        
        # 3. 生成计算字段
        self._suggest_calculated_fields(extracted_data)
        
        # 4. 检查关键字段是否可以继续
        can_proceed = self._check_can_proceed(extracted_data)
        
        # 生成总结
        summary = self._generate_summary()
        
        result = {
            "can_proceed": can_proceed,
            "fillable_suggestions": self.suggestions,
            "unfillable_fields": self.unfillable_fields,
            "summary": summary
        }
        
        print(f"✅ [数据填充] 生成了 {len(self.suggestions)} 个填充建议")
        print(f"⚠️  [数据填充] 发现 {len(self.unfillable_fields)} 个无法填充的字段")
        
        return result
    
    def _suggest_project_level_fields(self, data: Dict[str, Any]):
        """建议项目级字段填充"""
        
        # 获取项目级数据（支持两种数据结构）
        project_level = data.get("rawData", {}).get("projectLevel", data)
        
        # 填充电价
        if not project_level.get("electricityPrice"):
            location = project_level.get("projectLocation", "")
            suggested_price = self._get_electricity_price_by_location(location)
            if suggested_price:
                self.suggestions.append({
                    "field": "electricityPrice",
                    "original_value": project_level.get("electricityPrice"),
                    "suggested_value": suggested_price,
                    "method": "省份查表",
                    "confidence": "high" if location else "medium",
                    "reasoning": f"根据{self._extract_province(location) or '默认'}省份工业用电参考价格"
                })
        
        # NOTE: 根据用户要求，dailyRunningHours 和 annualRunningDays 不自动填充
        # 如果这两个字段为空，计算阶段会使用默认年运行时间8500小时
        # 这样符合需求文档要求，避免"瞎提取"
    
    def _suggest_equipment_level_fields(self, data: Dict[str, Any]):
        """建议设备级字段填充"""
        
        # 获取设备列表（支持两种数据结构）
        equipment_list = data.get("rawData", {}).get("equipmentLevel", data.get("equipmentList", []))
        
        for i, equipment in enumerate(equipment_list):
            # 填充运行状态
            if not equipment.get("runningStatus"):
                # 根据设备编号或位置推断状态
                equipment_number = equipment.get("equipmentNumber", "")
                if "1" in equipment_number or "主" in equipment_number:
                    suggested_status = "运行"
                    reasoning = "根据设备编号推断为主要设备，通常处于运行状态"
                else:
                    suggested_status = "备用"
                    reasoning = "根据设备编号推断为备用设备"
                
                self.suggestions.append({
                    "field": f"equipmentList[{i}].runningStatus",
                    "original_value": equipment.get("runningStatus"),
                    "suggested_value": suggested_status,
                    "method": "设备编号推断",
                    "confidence": "medium",
                    "reasoning": reasoning
                })
            
            # 填充出厂年份
            if not equipment.get("manufactureYear"):
                # 根据设备品牌和型号推断大概年份
                brand = equipment.get("brand", "")
                model = equipment.get("model", "")
                
                # 简单的年份推断逻辑
                if "新" in model or "2020" in model:
                    suggested_year = 2020
                elif "老" in model or "旧" in model:
                    suggested_year = 2010
                else:
                    suggested_year = 2015  # 默认中等年份
                
                self.suggestions.append({
                    "field": f"equipmentList[{i}].manufactureYear",
                    "original_value": equipment.get("manufactureYear"),
                    "suggested_value": suggested_year,
                    "method": "型号推断",
                    "confidence": "low",
                    "reasoning": f"根据设备型号{model}推断的大概出厂年份，建议核实"
                })
    
    def _suggest_calculated_fields(self, data: Dict[str, Any]):
        """建议计算字段"""
        
        # 获取项目级数据和设备列表（支持两种数据结构）
        project_level = data.get("rawData", {}).get("projectLevel", data)
        equipment_list = data.get("rawData", {}).get("equipmentLevel", data.get("equipmentList", []))
        
        for i, equipment in enumerate(equipment_list):
            # 计算机龄
            manufacture_year = equipment.get("manufactureYear")
            if manufacture_year:
                age = self.current_year - int(manufacture_year)
                self.suggestions.append({
                    "field": f"equipmentList[{i}].age",
                    "original_value": None,
                    "suggested_value": age,
                    "method": "公式计算",
                    "confidence": "high",
                    "reasoning": f"机龄 = {self.current_year} - {int(manufacture_year)} = {age}年"
                })
            
            # 计算比功率
            rated_power = equipment.get("ratedPower")
            rated_flow = equipment.get("ratedFlow")
            if rated_power and rated_flow:
                specific_power = (rated_power * RATED_POWER_FACTOR) / rated_flow
                self.suggestions.append({
                    "field": f"equipmentList[{i}].specificPower",
                    "original_value": None,
                    "suggested_value": round(specific_power, 2),
                    "method": "公式计算",
                    "confidence": "high",
                    "reasoning": f"比功率 = ({rated_power} × {RATED_POWER_FACTOR}) / {rated_flow} = {specific_power:.2f} kW/(m³/min)"
                })
            
            # 计算压缩机功率因子
            brand = equipment.get("brand", "")
            age = self.current_year - int(equipment.get("manufactureYear", self.current_year))
            power_factor = self._get_compressor_power_factor(brand, age)
            
            self.suggestions.append({
                "field": f"equipmentList[{i}].compressorPowerFactor",
                "original_value": None,
                "suggested_value": power_factor,
                "method": "品牌机龄查表",
                "confidence": "high" if brand else "medium",
                "reasoning": f"根据品牌{brand}和机龄{age}年查表得出功率因子"
            })
        
        # 计算系统级参数
        industry_type = project_level.get("industryType", "其他")
        pressure_params = PRESSURE_SAFETY_TABLE.get(industry_type, PRESSURE_SAFETY_TABLE["其他"])
        
        # 安全保护裕量
        self.suggestions.append({
            "field": "safetyMargin",
            "original_value": None,
            "suggested_value": pressure_params["safety_margin"],
            "method": "行业查表",
            "confidence": "high",
            "reasoning": f"根据{industry_type}行业标准安全保护裕量"
        })
        
        # 压力波动
        self.suggestions.append({
            "field": "pressureFluctuation",
            "original_value": None,
            "suggested_value": pressure_params["pressure_fluctuation"],
            "method": "行业查表",
            "confidence": "high",
            "reasoning": f"根据{industry_type}行业典型压力波动范围"
        })
        
        # 计算智控后平均压力
        alarm_pressure = project_level.get("alarmPressureLowerLimit")
        if alarm_pressure:
            post_control_pressure = alarm_pressure + pressure_params["safety_margin"] + pressure_params["pressure_fluctuation"]
            self.suggestions.append({
                "field": "postControlAveragePressure",
                "original_value": None,
                "suggested_value": round(post_control_pressure, 2),
                "method": "公式计算",
                "confidence": "high",
                "reasoning": f"智控后平均压力 = {alarm_pressure} + {pressure_params['safety_margin']} + {pressure_params['pressure_fluctuation']} = {post_control_pressure:.2f} bar"
            })
        
        # 计算平均年运行时间
        daily_hours = project_level.get("dailyRunningHours") or DEFAULT_DAILY_RUNNING_HOURS
        annual_days = project_level.get("annualRunningDays") or DEFAULT_ANNUAL_RUNNING_DAYS
        
        if daily_hours and annual_days:
            annual_hours = daily_hours * annual_days
            if annual_hours <= 0 or annual_hours > 8760:
                annual_hours = DEFAULT_ANNUAL_OPERATING_HOURS
                reasoning = f"计算结果{daily_hours * annual_days}小时超出合理范围，使用默认值{DEFAULT_ANNUAL_OPERATING_HOURS}小时"
            else:
                reasoning = f"平均年运行时间 = {daily_hours} × {annual_days} = {annual_hours} 小时"
        else:
            annual_hours = DEFAULT_ANNUAL_OPERATING_HOURS
            reasoning = f"缺少运行时间数据，使用行业默认值{DEFAULT_ANNUAL_OPERATING_HOURS}小时"
        
        self.suggestions.append({
            "field": "averageAnnualOperatingHours",
            "original_value": None,
            "suggested_value": annual_hours,
            "method": "公式计算",
            "confidence": "high",
            "reasoning": reasoning
        })
        
        # 主管网直接耗量比例（固定常量）
        self.suggestions.append({
            "field": "mainPipelineDirectConsumptionRatio",
            "original_value": None,
            "suggested_value": MAIN_PIPELINE_DIRECT_CONSUMPTION_RATIO,
            "method": "固定常量",
            "confidence": "high",
            "reasoning": f"根据行业标准，主管网直接耗量比例固定为{MAIN_PIPELINE_DIRECT_CONSUMPTION_RATIO}%"
        })
    
    def _get_electricity_price_by_location(self, location: str) -> Optional[float]:
        """根据地址获取电价"""
        if not location:
            return None
        
        # 提取省份
        province = self._extract_province(location)
        if province and province in ELECTRICITY_PRICE_TABLE:
            return ELECTRICITY_PRICE_TABLE[province]
        
        return None
    
    def _extract_province(self, location: str) -> Optional[str]:
        """从地址中提取省份"""
        if not location:
            return None
        
        # 常见省份匹配
        for province in ELECTRICITY_PRICE_TABLE.keys():
            if province in location:
                return province
        
        # 特殊处理
        if "内蒙" in location:
            return "内蒙古"
        
        return None
    
    def _get_compressor_power_factor(self, brand: str, age: int) -> float:
        """根据品牌和机龄获取压缩机功率因子"""
        
        # 品牌匹配
        for brand_key, params in COMPRESSOR_POWER_FACTOR_TABLE.items():
            if brand_key in brand or brand in brand_key:
                if params["age_threshold"] is None:
                    return params["old_factor"]  # 寿力、韩华不分年龄
                elif age >= params["age_threshold"]:
                    return params["old_factor"]
                else:
                    return params["new_factor"]
        
        # 默认值
        return COMPRESSOR_POWER_FACTOR_TABLE["默认"]["old_factor"]
    
    def _check_can_proceed(self, data: Dict[str, Any]) -> bool:
        """检查是否可以继续计算"""
        
        # 获取项目级数据和设备列表（支持两种数据结构）
        project_level = data.get("rawData", {}).get("projectLevel", data)
        equipment_list = data.get("rawData", {}).get("equipmentLevel", data.get("equipmentList", []))
        
        # 检查关键字段
        critical_fields = [
            "totalAnnualEnergyConsumption",
            "alarmPressureLowerLimit", 
            "averagePressure"
        ]
        
        for field in critical_fields:
            if not project_level.get(field):
                self.unfillable_fields.append({
                    "field": field,
                    "reason": "关键计算参数，必须从调研表中获取",
                    "severity": "critical"
                })
        if not equipment_list:
            self.unfillable_fields.append({
                "field": "equipmentList",
                "reason": "需要至少一台空压机设备信息",
                "severity": "critical"
            })
        else:
            # 检查是否有运行中的设备
            running_equipment = [eq for eq in equipment_list if eq.get("runningStatus") in ["运行", "备用"]]
            if not running_equipment:
                self.unfillable_fields.append({
                    "field": "equipmentList.runningStatus",
                    "reason": "需要至少一台运行或备用状态的空压机",
                    "severity": "critical"
                })
        
        return len(self.unfillable_fields) == 0
    
    def _generate_summary(self) -> str:
        """生成填充建议总结"""
        
        if self.unfillable_fields:
            return f"发现{len(self.unfillable_fields)}个关键字段缺失，无法继续计算。请补充调研表数据。"
        
        if not self.suggestions:
            return "数据完整，无需填充建议。"
        
        return f"生成了{len(self.suggestions)}个填充建议，可以继续计算。"


def main():
    """主函数"""
    if len(sys.argv) < 4:
        print("用法: python suggest_air_compressor_data_filling.py <提取数据JSON路径> <质量报告JSON路径> <输出建议JSON路径>")
        sys.exit(1)
    
    extracted_data_path = sys.argv[1]
    quality_report_path = sys.argv[2]
    output_path = sys.argv[3]
    
    print(f"🚀 [空压数据填充] 开始生成填充建议")
    print(f"📁 [空压数据填充] 提取数据: {extracted_data_path}")
    print(f"📁 [空压数据填充] 质量报告: {quality_report_path}")
    print(f"📁 [空压数据填充] 输出路径: {output_path}")
    
    try:
        # 读取提取的数据
        with open(extracted_data_path, 'r', encoding='utf-8') as f:
            extracted_data = json.load(f)
        
        # 读取质量报告
        with open(quality_report_path, 'r', encoding='utf-8') as f:
            quality_report = json.load(f)
        
        # 生成填充建议
        filler = AirCompressorDataFiller()
        suggestions = filler.generate_suggestions(extracted_data, quality_report)
        
        # 保存结果
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(suggestions, f, ensure_ascii=False, indent=2)
        
        print(f"✅ [空压数据填充] 填充建议生成完成")
        print(f"📄 结果已保存到: {output_path}")
        
    except Exception as e:
        print(f"❌ [空压数据填充] 处理失败: {str(e)}")
        
        # 保存错误结果
        error_result = {
            "can_proceed": False,
            "fillable_suggestions": [],
            "unfillable_fields": [
                {
                    "field": "system",
                    "reason": f"数据填充建议生成失败: {str(e)}",
                    "severity": "critical"
                }
            ],
            "summary": f"填充建议生成失败: {str(e)}"
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)


if __name__ == "__main__":
    main()