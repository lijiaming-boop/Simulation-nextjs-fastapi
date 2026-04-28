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


def generate_equipment_table(equipment_list: list) -> str:
    """生成空压机运行情况表格"""
    table_rows = []
    
    # 按站房分组
    stations = {}
    for equipment in equipment_list:
        station_id = equipment.get('stationId', '未知')
        if station_id not in stations:
            stations[station_id] = []
        stations[station_id].append(equipment)
    
    # 生成表格行
    for station_id, equipments in stations.items():
        for i, equipment in enumerate(equipments, 1):
            # 计算加载率（模拟数据）
            load_rate = 70 + (i % 20)  # 模拟70-90%的加载率
            
            row = [
                station_id,
                f"{station_id}-{i}号机",
                equipment.get('brand', '未知'),
                equipment.get('equipmentType', '未知'),
                equipment.get('model', '未知'),
                str(equipment.get('ratedPower', 0)),
                str(equipment.get('ratedFlow', 0)),
                "7.1",  # 模拟加载压力
                "8.1",  # 模拟卸载压力
                str(10000 + i * 1000),  # 模拟运行总时间
                str(int((10000 + i * 1000) * load_rate / 100)),  # 模拟加载时间
                f"{load_rate}%"
            ]
            table_rows.append('| ' + ' | '.join(row) + ' |')
    
    return '\n'.join(table_rows)


def generate_md_report(extracted_data: Dict[str, Any], result: Dict[str, Any], output_dir: Path) -> Optional[Path]:
    """生成MD格式的方案报告"""
    try:
        # 读取模板
        template_path = Path('00_sample/模板测算表/空压系统数智化升级方案模板.md')
        if not template_path.exists():
            print(f"❌ MD模板文件不存在: {template_path}")
            return None
        
        # 读取模板内容
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # 生成设备表格
        equipment_list = extracted_data.get('rawData', {}).get('equipmentLevel', [])
        equipment_table = generate_equipment_table(equipment_list)
        
        # 计算站房数量
        station_ids = set()
        for equipment in equipment_list:
            if 'stationId' in equipment:
                station_ids.add(equipment['stationId'])
        station_count = len(station_ids)
        
        # 计算设备数量
        total_count = len(equipment_list)
        centrifugal_count = sum(1 for eq in equipment_list if eq.get('equipmentType') == '离心')
        screw_count = sum(1 for eq in equipment_list if eq.get('equipmentType') == '螺杆')
        
        # 计算能耗数据
        annual_energy = extracted_data.get('rawData', {}).get('projectLevel', {}).get('totalAnnualEnergyConsumption', 0) / 10000
        electricity_price = extracted_data.get('rawData', {}).get('projectLevel', {}).get('electricityPrice', 0)
        annual_cost = annual_energy * electricity_price
        
        # 计算节能数据
        annual_saving = result.get('annual_energy_saving', 0) / 10000
        energy_saving_rate = result.get('energy_saving_rate', 0) * 100
        annual_saving_cost = annual_saving * electricity_price
        
        # 系统参数
        system_params = result.get('system_parameters', {})
        current_energy = result.get('current_total_energy', 0) / 10000
        optimized_energy = result.get('optimized_total_energy', 0) / 10000
        
        # 替换占位符
        content = template_content
        content = content.replace('【企业名称】', extracted_data.get('rawData', {}).get('projectLevel', {}).get('companyName', ''))
        content = content.replace('【站房数量】', str(station_count))
        content = content.replace('【空压机总台数】', str(total_count))
        content = content.replace('【离心机台数】', str(centrifugal_count))
        content = content.replace('【螺杆机台数】', str(screw_count))
        content = content.replace('【变频机台数】', '0')
        content = content.replace('【年耗电量(万kWh)】', f"{annual_energy:.1f}")
        content = content.replace('【电价(元/kWh)】', f"{electricity_price:.3f}")
        content = content.replace('【年电费(万元)】', f"{annual_cost:.1f}")
        content = content.replace('【数据时间段】', '2026年')
        content = content.replace('【螺杆机组压力范围(bar)】', '7.0-7.5')
        content = content.replace('【离心机压力设定(bar)】', '7.0')
        content = content.replace('【系统平均压力(bar)】', f"{extracted_data.get('rawData', {}).get('projectLevel', {}).get('averagePressure', 0):.1f}")
        content = content.replace('【螺杆机平均加载率(%)】', '75')
        content = content.replace('【节电量(万kWh)】', f"{annual_saving:.1f}")
        content = content.replace('【节能率(%)】', f"{energy_saving_rate:.1f}")
        content = content.replace('【年节能费用(万元)】', f"{annual_saving_cost:.1f}")
        content = content.replace('{{equipment_table}}', equipment_table)
        content = content.replace('{{current_energy}}', f"{current_energy:.1f}")
        content = content.replace('{{optimized_energy}}', f"{optimized_energy:.1f}")
        content = content.replace('{{annual_saving}}', f"{annual_saving:.1f}")
        content = content.replace('{{energy_saving_rate}}', f"{energy_saving_rate:.1f}")
        content = content.replace('{{annual_saving_cost}}', f"{annual_saving_cost:.1f}")
        content = content.replace('{{system_compressor_power_factor}}', f"{system_params.get('systemCompressorPowerFactor', 0):.3f}")
        content = content.replace('{{system_specific_power}}', f"{system_params.get('systemSpecificPower', 0):.2f}")
        content = content.replace('{{system_compressed_air_flow}}', f"{system_params.get('systemCompressedAirFlow', 0):.1f}")
        content = content.replace('{{running_equipment_count}}', str(system_params.get('runningEquipmentCount', 0)))
        content = content.replace('{{backup_equipment_count}}', str(system_params.get('backupEquipmentCount', 0)))
        content = content.replace('{{total_equipment_count}}', str(system_params.get('totalEquipmentCount', 0)))
        
        # 保存MD文件
        md_output_path = output_dir / f"空压系统数智化升级方案_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(md_output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ MD报告已生成: {md_output_path}")
        return md_output_path
        
    except Exception as e:
        print(f"❌ 生成MD报告失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def convert_md_to_pdf(md_path: Path, output_dir: Path) -> Optional[Path]:
    """将MD文件转换为PDF"""
    try:
        import markdown
        from weasyprint import HTML
        
        # 读取MD文件
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # 转换为HTML
        html_content = markdown.markdown(md_content, extensions=['tables'])
        
        # 添加CSS样式
        css = '''
        body {
            font-family: SimSun, serif;
            line-height: 1.6;
            margin: 20px;
        }
        h1, h2, h3, h4 {
            color: #333;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
        }
        '''
        
        # 生成PDF
        pdf_output_path = output_dir / f"{md_path.stem}.pdf"
        HTML(string=html_content).write_pdf(str(pdf_output_path), stylesheets=[css])
        
        print(f"✅ PDF报告已生成: {pdf_output_path}")
        return pdf_output_path
        
    except ImportError:
        print("❌ 需要安装依赖库: pip install markdown weasyprint")
        return None
    except Exception as e:
        print(f"❌ 转换PDF失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def generate_word_report(extracted_data: Dict[str, Any], result: Dict[str, Any], output_dir: Path) -> Optional[Path]:
    """生成Word格式的方案报告"""
    # 先生成MD报告
    md_path = generate_md_report(extracted_data, result, output_dir)
    if not md_path:
        return None
    
    # 转换为PDF
    pdf_path = convert_md_to_pdf(md_path, output_dir)
    if not pdf_path:
        # 如果PDF转换失败，返回MD文件
        return md_path
    
    return pdf_path


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
        
        # 生成报告（MD + PDF）
        report_path = generate_word_report(extracted_data, result, output_dir)
        
        # 生成Excel报价单
        excel_quote_path = generate_excel_quote(extracted_data, result, output_dir)
        
        # 输出结果
        if report_path:
            print(f"📄 报告: {report_path}")
        if excel_quote_path:
            print(f"📊 Excel报价单: {excel_quote_path}")
        
        if report_path or excel_quote_path:
            print(f"✅ [报告生成] 报告生成完成")
        else:
            print(f"❌ [报告生成] 报告生成失败")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ [报告生成] 处理失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()