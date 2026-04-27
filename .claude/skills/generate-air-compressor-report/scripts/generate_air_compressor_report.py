#!/usr/bin/env python3
"""
空压机报告生成器
生成空压系统数智化升级方案报告和报价单
"""

import json
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


def generate_word_report(extracted_data: Dict[str, Any], result: Dict[str, Any], output_dir: Path) -> Optional[Path]:
    """生成Word格式的方案报告"""
    try:
        from docx import Document
        
        # 读取模板
        template_path = Path('00_sample/模板测算表/空压系统数智化升级方案模板.docx')
        if not template_path.exists():
            print(f"❌ Word模板文件不存在: {template_path}")
            return None
        
        # 复制模板
        output_path = output_dir / f"空压系统数智化升级方案_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        shutil.copy(template_path, output_path)
        
        # 打开文档
        doc = Document(str(output_path))
        
        # 替换文档中的占位符
        for paragraph in doc.paragraphs:
            for run in paragraph.runs:
                text = run.text
                if not text:
                    continue
                
                # 项目信息
                if '{companyName}' in text:
                    company_name = extracted_data.get('rawData', {}).get('projectLevel', {}).get('companyName', '')
                    text = text.replace('{companyName}', company_name)
                if '{projectLocation}' in text:
                    project_location = extracted_data.get('rawData', {}).get('projectLevel', {}).get('projectLocation', '')
                    text = text.replace('{projectLocation}', project_location)
                if '{industryType}' in text:
                    industry_type = extracted_data.get('rawData', {}).get('projectLevel', {}).get('industryType', '')
                    text = text.replace('{industryType}', industry_type)
                
                # 节能数据
                if '{energySavingRate}' in text:
                    energy_saving_rate = result.get('energy_saving_rate_range', '0% - 0%')
                    text = text.replace('{energySavingRate}', energy_saving_rate)
                if '{currentEnergy}' in text:
                    current_energy = result.get('current_total_energy', 0) / 10000
                    text = text.replace('{currentEnergy}', f"{current_energy:.1f}万kWh")
                if '{optimizedEnergy}' in text:
                    optimized_energy = result.get('optimized_total_energy', 0) / 10000
                    text = text.replace('{optimizedEnergy}', f"{optimized_energy:.1f}万kWh")
                if '{annualSaving}' in text:
                    annual_saving = result.get('annual_energy_saving', 0) / 10000
                    text = text.replace('{annualSaving}', f"{annual_saving:.1f}万kWh")
                
                # 系统参数
                system_params = result.get('system_parameters', {})
                if '{systemCompressorPowerFactor}' in text:
                    power_factor = system_params.get('systemCompressorPowerFactor', 0)
                    text = text.replace('{systemCompressorPowerFactor}', f"{power_factor:.3f}")
                if '{systemSpecificPower}' in text:
                    specific_power = system_params.get('systemSpecificPower', 0)
                    text = text.replace('{systemSpecificPower}', f"{specific_power:.2f}kW/(m³/min)")
                if '{systemCompressedAirFlow}' in text:
                    air_flow = system_params.get('systemCompressedAirFlow', 0)
                    text = text.replace('{systemCompressedAirFlow}', f"{air_flow:.1f}m³/min")
                
                run.text = text
        
        # 替换表格中的占位符
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            text = run.text
                            if not text:
                                continue
                            
                            # 项目信息
                            if '{companyName}' in text:
                                company_name = extracted_data.get('rawData', {}).get('projectLevel', {}).get('companyName', '')
                                text = text.replace('{companyName}', company_name)
                            if '{projectLocation}' in text:
                                project_location = extracted_data.get('rawData', {}).get('projectLevel', {}).get('projectLocation', '')
                                text = text.replace('{projectLocation}', project_location)
                            if '{industryType}' in text:
                                industry_type = extracted_data.get('rawData', {}).get('projectLevel', {}).get('industryType', '')
                                text = text.replace('{industryType}', industry_type)
                            
                            # 节能数据
                            if '{energySavingRate}' in text:
                                energy_saving_rate = result.get('energy_saving_rate_range', '0% - 0%')
                                text = text.replace('{energySavingRate}', energy_saving_rate)
                            if '{currentEnergy}' in text:
                                current_energy = result.get('current_total_energy', 0) / 10000
                                text = text.replace('{currentEnergy}', f"{current_energy:.1f}万kWh")
                            if '{optimizedEnergy}' in text:
                                optimized_energy = result.get('optimized_total_energy', 0) / 10000
                                text = text.replace('{optimizedEnergy}', f"{optimized_energy:.1f}万kWh")
                            if '{annualSaving}' in text:
                                annual_saving = result.get('annual_energy_saving', 0) / 10000
                                text = text.replace('{annualSaving}', f"{annual_saving:.1f}万kWh")
                            
                            # 系统参数
                            system_params = result.get('system_parameters', {})
                            if '{systemCompressorPowerFactor}' in text:
                                power_factor = system_params.get('systemCompressorPowerFactor', 0)
                                text = text.replace('{systemCompressorPowerFactor}', f"{power_factor:.3f}")
                            if '{systemSpecificPower}' in text:
                                specific_power = system_params.get('systemSpecificPower', 0)
                                text = text.replace('{systemSpecificPower}', f"{specific_power:.2f}kW/(m³/min)")
                            if '{systemCompressedAirFlow}' in text:
                                air_flow = system_params.get('systemCompressedAirFlow', 0)
                                text = text.replace('{systemCompressedAirFlow}', f"{air_flow:.1f}m³/min")
                            
                            run.text = text
        
        # 保存文档
        doc.save(str(output_path))
        print(f"✅ Word报告已生成: {output_path}")
        return output_path
        
    except ImportError:
        print("❌ 需要安装 python-docx 库: pip install python-docx")
        return None
    except Exception as e:
        print(f"❌ 生成Word报告失败: {str(e)}")
        return None


def generate_excel_quote(extracted_data: Dict[str, Any], result: Dict[str, Any], output_dir: Path) -> Optional[Path]:
    """生成Excel格式的报价单"""
    try:
        import openpyxl
        from openpyxl import load_workbook
        
        # 读取模板
        template_path = Path('00_sample/模板测算表/2026年空压云智控报价模板.xlsx')
        if not template_path.exists():
            print(f"❌ Excel模板文件不存在: {template_path}")
            return None
        
        # 加载工作簿
        wb = load_workbook(str(template_path))
        
        # 获取第一个工作表
        ws = wb.active
        
        # 替换单元格中的占位符
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    text = cell.value
                    
                    # 项目信息
                    if '{companyName}' in text:
                        company_name = extracted_data.get('rawData', {}).get('projectLevel', {}).get('companyName', '')
                        cell.value = text.replace('{companyName}', company_name)
                    if '{projectLocation}' in text:
                        project_location = extracted_data.get('rawData', {}).get('projectLevel', {}).get('projectLocation', '')
                        cell.value = text.replace('{projectLocation}', project_location)
                    if '{industryType}' in text:
                        industry_type = extracted_data.get('rawData', {}).get('projectLevel', {}).get('industryType', '')
                        cell.value = text.replace('{industryType}', industry_type)
                    
                    # 节能数据
                    if '{energySavingRate}' in text:
                        energy_saving_rate = result.get('energy_saving_rate_range', '0% - 0%')
                        cell.value = text.replace('{energySavingRate}', energy_saving_rate)
                    if '{currentEnergy}' in text:
                        current_energy = result.get('current_total_energy', 0) / 10000
                        cell.value = text.replace('{currentEnergy}', f"{current_energy:.1f}万kWh")
                    if '{optimizedEnergy}' in text:
                        optimized_energy = result.get('optimized_total_energy', 0) / 10000
                        cell.value = text.replace('{optimizedEnergy}', f"{optimized_energy:.1f}万kWh")
                    if '{annualSaving}' in text:
                        annual_saving = result.get('annual_energy_saving', 0) / 10000
                        cell.value = text.replace('{annualSaving}', f"{annual_saving:.1f}万kWh")
                    
                    # 系统参数
                    system_params = result.get('system_parameters', {})
                    if '{systemCompressorPowerFactor}' in text:
                        power_factor = system_params.get('systemCompressorPowerFactor', 0)
                        cell.value = text.replace('{systemCompressorPowerFactor}', f"{power_factor:.3f}")
                    if '{systemSpecificPower}' in text:
                        specific_power = system_params.get('systemSpecificPower', 0)
                        cell.value = text.replace('{systemSpecificPower}', f"{specific_power:.2f}kW/(m³/min)")
                    if '{systemCompressedAirFlow}' in text:
                        air_flow = system_params.get('systemCompressedAirFlow', 0)
                        cell.value = text.replace('{systemCompressedAirFlow}', f"{air_flow:.1f}m³/min")
                    
                    # 设备信息
                    equipment_list = extracted_data.get('rawData', {}).get('equipmentLevel', [])
                    if '{equipmentCount}' in text:
                        cell.value = text.replace('{equipmentCount}', str(len(equipment_list)))
                    
                    # 电价信息
                    electricity_price = extracted_data.get('rawData', {}).get('projectLevel', {}).get('electricityPrice', 0)
                    if '{electricityPrice}' in text:
                        cell.value = text.replace('{electricityPrice}', f"{electricity_price:.3f}元/kWh")
                    
                    # 压力信息
                    alarm_pressure = extracted_data.get('rawData', {}).get('projectLevel', {}).get('alarmPressureLowerLimit', 0)
                    if '{alarmPressure}' in text:
                        cell.value = text.replace('{alarmPressure}', f"{alarm_pressure:.1f}bar")
                    
                    average_pressure = extracted_data.get('rawData', {}).get('projectLevel', {}).get('averagePressure', 0)
                    if '{averagePressure}' in text:
                        cell.value = text.replace('{averagePressure}', f"{average_pressure:.1f}bar")
        
        # 保存文件
        output_path = output_dir / f"2026年空压云智控报价单_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        wb.save(str(output_path))
        print(f"✅ Excel报价单已生成: {output_path}")
        return output_path
        
    except ImportError:
        print("❌ 需要安装 openpyxl 库: pip install openpyxl")
        return None
    except Exception as e:
        print(f"❌ 生成Excel报价单失败: {str(e)}")
        return None


def main():
    """主函数"""
    if len(sys.argv) < 4:
        print("用法: python generate_air_compressor_report.py <提取数据JSON路径> <计算结果JSON路径> <输出目录>")
        sys.exit(1)
    
    extracted_data_path = sys.argv[1]
    calculation_result_path = sys.argv[2]
    output_dir = Path(sys.argv[3])
    
    print(f"🚀 [报告生成] 开始生成空压机报告...")
    print(f"📁 [报告生成] 提取数据: {extracted_data_path}")
    print(f"📁 [报告生成] 计算结果: {calculation_result_path}")
    print(f"📁 [报告生成] 输出目录: {output_dir}")
    
    try:
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取数据
        with open(extracted_data_path, 'r', encoding='utf-8') as f:
            extracted_data = json.load(f)
        
        with open(calculation_result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        print(f"✅ [报告生成] 数据读取成功")
        
        # 生成Word报告
        word_report_path = generate_word_report(extracted_data, result, output_dir)
        
        # 生成Excel报价单
        excel_quote_path = generate_excel_quote(extracted_data, result, output_dir)
        
        # 输出结果
        if word_report_path:
            print(f"📄 Word报告: {word_report_path}")
        if excel_quote_path:
            print(f"📊 Excel报价单: {excel_quote_path}")
        
        if word_report_path or excel_quote_path:
            print(f"✅ [报告生成] 报告生成完成")
        else:
            print(f"❌ [报告生成] 报告生成失败")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ [报告生成] 处理失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()