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
        
        # 计算节能数据（注意字段名称是energy_saving而不是annual_energy_saving）
        energy_saving_value = result.get('energy_saving', result.get('annual_energy_saving', 0))
        annual_saving = energy_saving_value / 10000
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
    
    # 将MD转换为Word
    word_path = convert_md_to_word(md_path, output_dir)
    if not word_path:
        # 如果Word转换失败，返回MD文件
        return md_path
    
    return word_path


def convert_md_to_word(md_path: Path, output_dir: Path) -> Optional[Path]:
    """将MD文件转换为Word"""
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        # 读取MD文件
        with open(md_path, 'r', encoding='utf-8') as f:
            md_lines = f.readlines()
        
        # 创建Word文档
        doc = Document()
        
        # 设置默认字体
        style = doc.styles['Normal']
        font = style.font
        font.name = 'SimSun'
        font.size = Pt(11)
        
        # 解析MD内容
        for line in md_lines:
            line = line.rstrip()
            
            # 标题
            if line.startswith('# '):
                heading = doc.add_heading(line[2:], level=1)
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif line.startswith('## '):
                doc.add_heading(line[3:], level=2)
            elif line.startswith('### '):
                doc.add_heading(line[4:], level=3)
            elif line.startswith('#### '):
                doc.add_heading(line[5:], level=4)
            
            # 列表
            elif line.startswith('- '):
                paragraph = doc.add_paragraph(line[2:], style='List Bullet')
            elif line.startswith('1. ') or line.startswith('（1）') or line.startswith('（2）') or line.startswith('（3）'):
                paragraph = doc.add_paragraph(line, style='List Number')
            
            # 表格
            elif line.startswith('|'):
                # 检查是否是表格行
                parts = line.split('|')
                if len(parts) > 2:
                    # 创建表格（第一行作为表头）
                    if not hasattr(doc, '_table_started'):
                        doc._table_started = True
                        doc._table = doc.add_table(rows=0, cols=len(parts)-2)
                        doc._table.style = 'Table Grid'
                    
                    # 添加行
                    row = doc._table.add_row()
                    for i, part in enumerate(parts[1:-1]):
                        row.cells[i].text = part.strip()
                continue
            
            # 普通段落
            elif line.strip():
                # 检查是否在表格中
                if hasattr(doc, '_table_started') and doc._table_started:
                    # 表格结束
                    doc._table_started = False
                doc.add_paragraph(line)
            
            # 空行
            else:
                doc.add_paragraph()
        
        # 保存Word文件
        word_output_path = output_dir / f"{md_path.stem}.docx"
        doc.save(str(word_output_path))
        
        print(f"✅ Word报告已生成: {word_output_path}")
        return word_output_path
        
    except ImportError:
        print("❌ 需要安装 python-docx 库: pip install python-docx")
        return None
    except Exception as e:
        print(f"❌ 转换Word失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


# 报价单功能已移除
# def generate_excel_quote(extracted_data: Dict[str, Any], result: Dict[str, Any], output_dir: Path) -> Optional[Path]:


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
        
        # 生成报告（MD + Word）
        report_path = generate_word_report(extracted_data, result, output_dir)
        
        # 输出结果
        if report_path:
            print(f"📄 报告: {report_path}")
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