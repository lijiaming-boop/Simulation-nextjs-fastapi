"""空压机节能率计算器"""
import json
import os
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows


class AirCompressorCalculator:
    """空压机节能率计算器类"""
    
    def __init__(self):
        """初始化计算器"""
        self.template_dir = Path("00_sample/模板测算表")
        self.scheme_template_path = self.template_dir / "空压系统数智化升级方案模板.docx"
        self.quotation_template_path = self.template_dir / "2026年空压云智控报价模板.xlsx"
    
    def calculate(self, filled_data_path: str, result_path: str) -> str:
        """执行空压机节能率计算
        
        Args:
            filled_data_path: 填充后的数据文件路径
            result_path: 结果输出文件路径
            
        Returns:
            result_path: 结果文件路径
        """
        # 读取填充后的数据
        with open(filled_data_path, 'r', encoding='utf-8') as f:
            filled_data = json.load(f)
        
        # 执行计算
        result = self._calculate_energy_saving(filled_data)
        
        # 保存结果
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 生成方案文档和报价单
        self._generate_scheme_document(filled_data, result)
        self._generate_quotation(filled_data, result)
        
        return result_path
    
    def _calculate_energy_saving(self, filled_data: dict) -> dict:
        """计算空压机节能率
        
        Args:
            filled_data: 填充后的数据
            
        Returns:
            计算结果
        """
        # 从填充数据中提取关键参数
        system_info = filled_data.get("system_info", {})
        equipment_list = filled_data.get("equipment_list", [])
        operation_data = filled_data.get("operation_data", {})
        
        # 计算当前系统总能耗
        current_total_energy = self._calculate_current_energy(equipment_list, operation_data)
        
        # 计算优化后系统总能耗
        optimized_total_energy = self._calculate_optimized_energy(equipment_list, operation_data)
        
        # 计算节能率
        energy_saving_rate = (current_total_energy - optimized_total_energy) / current_total_energy if current_total_energy > 0 else 0
        
        # 计算节能量
        energy_saving = current_total_energy - optimized_total_energy
        
        # 构建结果
        result = {
            "current_total_energy": current_total_energy,
            "optimized_total_energy": optimized_total_energy,
            "energy_saving": energy_saving,
            "energy_saving_rate": energy_saving_rate,
            "energy_saving_rate_range": f"{energy_saving_rate * 0.8 * 100:.1f}% - {energy_saving_rate * 1.2 * 100:.1f}%",
            "energy_saving_rate_min": energy_saving_rate * 0.8,
            "energy_saving_rate_max": energy_saving_rate * 1.2,
            "total_saving_min": energy_saving * 0.8,
            "total_saving_max": energy_saving * 1.2,
            "completeness": filled_data.get("completeness", 1.0),
            "filled_count": filled_data.get("filled_count", 0),
            "calculation_method": "air_compressor_standard",
            "system_info": system_info,
            "equipment_analysis": self._analyze_equipment(equipment_list)
        }
        
        return result
    
    def _calculate_current_energy(self, equipment_list: list, operation_data: dict) -> float:
        """计算当前系统总能耗
        
        Args:
            equipment_list: 设备列表
            operation_data: 运行数据
            
        Returns:
            当前总能耗 (kWh/年)
        """
        total_energy = 0.0
        annual_operating_hours = operation_data.get("annual_operating_hours", 8760)
        
        for equipment in equipment_list:
            # 修正：检查equipmentType字段，接受螺杆式和离心式作为空压机类型
            if equipment.get("equipmentType") in ["螺杆式", "离心式"]:
                power = equipment.get("ratedPower", 0)  # kW
                # 修正：使用默认负载率0.7
                load_rate = 0.7  # 负载率
                # 修正：使用默认效率0.8
                efficiency = 0.8  # 效率
                
                # 计算单台空压机年能耗
                equipment_energy = power * load_rate * annual_operating_hours / efficiency
                total_energy += equipment_energy
        
        return total_energy
    
    def _calculate_optimized_energy(self, equipment_list: list, operation_data: dict) -> float:
        """计算优化后系统总能耗
        
        Args:
            equipment_list: 设备列表
            operation_data: 运行数据
            
        Returns:
            优化后总能耗 (kWh/年)
        """
        total_energy = 0.0
        annual_operating_hours = operation_data.get("annual_operating_hours", 8760)
        
        for equipment in equipment_list:
            # 修正：检查equipmentType字段，接受螺杆式和离心式作为空压机类型
            if equipment.get("equipmentType") in ["螺杆式", "离心式"]:
                power = equipment.get("ratedPower", 0)  # kW
                # 修正：使用默认负载率0.7
                load_rate = 0.7  # 负载率
                
                # 优化后的效率（假设提高15%）
                optimized_efficiency = 0.8 * 1.15  # 假设效率从0.8提高到0.92
                
                # 计算优化后单台空压机年能耗
                equipment_energy = power * load_rate * annual_operating_hours / optimized_efficiency
                total_energy += equipment_energy
        
        return total_energy
    
    def _analyze_equipment(self, equipment_list: list) -> dict:
        """分析设备状况
        
        Args:
            equipment_list: 设备列表
            
        Returns:
            设备分析结果
        """
        analysis = {
            "total_air_compressors": 0,
            "total_power": 0.0,
            "average_efficiency": 0.0,
            "equipment_types": {}
        }
        
        # 修正：使用正确的字段名equipmentType，接受螺杆式和离心式作为空压机类型
        air_compressors = [eq for eq in equipment_list if eq.get("equipmentType") in ["螺杆式", "离心式"]]
        analysis["total_air_compressors"] = len(air_compressors)
        
        if air_compressors:
            # 修正：使用正确的字段名ratedPower
            total_power = sum(eq.get("ratedPower", 0) for eq in air_compressors)
            # 修正：使用默认效率0.8
            total_efficiency = 0.8 * len(air_compressors)  # 假设所有设备效率为0.8
            
            analysis["total_power"] = total_power
            analysis["average_efficiency"] = total_efficiency / len(air_compressors)
            
            # 统计设备类型
            for eq in air_compressors:
                comp_type = eq.get("equipmentType", "unknown")
                analysis["equipment_types"][comp_type] = analysis["equipment_types"].get(comp_type, 0) + 1
        
        return analysis
    
    def _generate_scheme_document(self, filled_data: dict, result: dict):
        """生成空压系统数智化升级方案文档
        
        Args:
            filled_data: 填充后的数据
            result: 计算结果
        """
        # 这里需要实现文档生成逻辑
        # 可以使用 python-docx 库来处理 Word 文档
        # 由于模板处理较为复杂，此处仅做示例
        print("正在生成空压系统数智化升级方案文档...")
        
    def _generate_quotation(self, filled_data: dict, result: dict):
        """生成报价单
        
        Args:
            filled_data: 填充后的数据
            result: 计算结果
        """
        # 读取报价模板
        if not self.quotation_template_path.exists():
            print(f"报价模板不存在: {self.quotation_template_path}")
            return
        
        # 这里需要实现报价单生成逻辑
        # 可以使用 openpyxl 或 pandas 来处理 Excel 文档
        print("正在生成报价单...")
        
        # 示例：读取模板并保存为新文件
        try:
            wb = load_workbook(self.quotation_template_path)
            ws = wb.active
            
            # 在模板中填写必要的信息
            # 这里需要根据实际模板的单元格映射来填写
            ws['B3'] = filled_data.get("system_info", {}).get("project_name", "未命名项目")
            ws['B4'] = filled_data.get("system_info", {}).get("customer_name", "未知客户")
            ws['B5'] = filled_data.get("system_info", {}).get("contact_person", "未知联系人")
            ws['B6'] = filled_data.get("system_info", {}).get("contact_phone", "未知电话")
            
            # 填写节能率信息
            ws['F10'] = f"{result['energy_saving_rate'] * 100:.1f}%"
            ws['F11'] = f"{result['energy_saving'] / 10000:.2f} 万 kWh"
            
            # 保存报价单
            session_dir = Path(filled_data.get("session_dir", "."))
            quotation_path = session_dir / f"空压系统报价单_{filled_data.get('original_filename', '').split('.')[0]}.xlsx"
            wb.save(quotation_path)
            print(f"报价单已生成: {quotation_path}")
            
        except Exception as e:
            print(f"生成报价单失败: {str(e)}")
    
    def format_export_results(self, filled_data: dict, result: dict) -> dict:
        """格式化导出结果
        
        Args:
            filled_data: 填充后的数据
            result: 计算结果
            
        Returns:
            格式化后的结果
        """
        # 格式化结果，使其适合导出
        formatted = {
            "project_info": filled_data.get("system_info", {}),
            "energy_saving_results": {
                "current_total_energy": f"{result['current_total_energy'] / 10000:.2f} 万 kWh/年",
                "optimized_total_energy": f"{result['optimized_total_energy'] / 10000:.2f} 万 kWh/年",
                "energy_saving": f"{result['energy_saving'] / 10000:.2f} 万 kWh/年",
                "energy_saving_rate": f"{result['energy_saving_rate'] * 100:.1f}%",
                "energy_saving_rate_range": result['energy_saving_rate_range']
            },
            "equipment_analysis": result['equipment_analysis'],
            "completeness": f"{result['completeness'] * 100:.1f}%"
        }
        
        return formatted
