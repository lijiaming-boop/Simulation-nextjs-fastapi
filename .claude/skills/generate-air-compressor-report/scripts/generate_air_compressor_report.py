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

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')


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
            print(f" MD模板文件不存在: {template_path}")
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
        
        print(f" MD报告已生成: {md_output_path}")
        return md_output_path
        
    except Exception as e:
        print(f" 生成MD报告失败: {str(e)}")
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
        
        print(f" PDF报告已生成: {pdf_output_path}")
        return pdf_output_path
        
    except ImportError:
        print(" 需要安装依赖库: pip install markdown weasyprint")
        return None
    except Exception as e:
        print(f" 转换PDF失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def generate_word_report(extracted_data: Dict[str, Any], result: Dict[str, Any], output_dir: Path) -> Optional[Path]:
    """生成报告（优先使用pandoc转换）"""
    # 先生成MD报告
    md_path = generate_md_report(extracted_data, result, output_dir)
    if not md_path:
        return None
    
    # 尝试使用pandoc转换
    output_paths = convert_md_with_pandoc(md_path, output_dir)
    
    if output_paths:
        # 返回生成的文件路径列表
        for path in output_paths:
            print(f" 报告已生成: {path}")
        return output_paths[0]  # 返回第一个生成的文件
    else:
        # 如果pandoc不可用，生成HTML格式
        html_path = generate_html_report(md_path, output_dir)
        if html_path:
            print(f" HTML报告已生成: {html_path}")
            return html_path
        
        # 最后返回MD文件
        return md_path


def convert_md_with_pandoc(md_path: Path, output_dir: Path) -> list:
    """使用pandoc转换MD文件（优化格式）"""
    import subprocess
    
    output_paths = []
    
    # 检查pandoc是否安装
    try:
        result = subprocess.run(['pandoc', '--version'], capture_output=True)
        if result.returncode != 0:
            print(" pandoc未安装，尝试生成HTML报告")
            return []
    except FileNotFoundError:
        print(" pandoc未安装，尝试生成HTML报告")
        return []
    
    try:
        # 转换为Word（添加更多格式化选项）
        word_path = output_dir / f"{md_path.stem}.docx"
        cmd = [
            'pandoc', str(md_path), 
            '-o', str(word_path), 
            '--toc',
            '--toc-depth=3',
            '--highlight-style=tango',
            '--reference-doc=00_sample/模板测算表/reference.docx'  # 使用自定义模板
        ]
        
        # 如果没有自定义模板，使用默认格式
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                output_paths.append(word_path)
                print(f" pandoc转换Word成功（使用自定义模板）")
            else:
                raise Exception(result.stderr)
        except:
            # 如果自定义模板不存在，使用默认格式
            cmd = [
                'pandoc', str(md_path), 
                '-o', str(word_path), 
                '--toc',
                '--toc-depth=3',
                '--highlight-style=tango',
                '-V', 'mainfont=Microsoft YaHei',
                '-V', 'sansfont=Microsoft YaHei',
                '-V', 'fontsize=12pt',
                '-V', 'linestretch=1.5',
                '-V', 'geometry:margin=2.5cm'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                output_paths.append(word_path)
                print(f" pandoc转换Word成功（使用默认格式）")
            else:
                print(f" pandoc转换Word失败: {result.stderr}")
        
        # 转换为PDF
        pdf_path = output_dir / f"{md_path.stem}.pdf"
        cmd = [
            'pandoc', str(md_path), 
            '-o', str(pdf_path), 
            '--toc',
            '--toc-depth=3',
            '-V', 'geometry:margin=2.5cm',
            '-V', 'fontsize=12pt',
            '-V', 'linestretch=1.5',
            '-V', 'mainfont=Microsoft YaHei'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            output_paths.append(pdf_path)
            print(f" pandoc转换PDF成功")
        else:
            print(f" pandoc转换PDF失败: {result.stderr}")
        
    except Exception as e:
        print(f" pandoc转换失败: {str(e)}")
    
    return output_paths


def generate_html_report(md_path: Path, output_dir: Path) -> Optional[Path]:
    """生成美观的HTML报告"""
    try:
        import markdown
        
        # 读取MD文件
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # 转换为HTML
        html_body = markdown.markdown(md_content, extensions=['tables', 'toc'])
        
        # 添加美观的CSS样式
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>空压系统数智化升级方案</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Microsoft YaHei', 'SimHei', sans-serif;
            line-height: 1.8;
            color: #333;
            background: #f5f5f5;
            padding: 40px 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 60px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        h1 {
            text-align: center;
            color: #2c3e50;
            font-size: 28px;
            border-bottom: 3px solid #3498db;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        h2 {
            color: #3498db;
            font-size: 22px;
            margin-top: 35px;
            margin-bottom: 20px;
            padding-left: 15px;
            border-left: 4px solid #3498db;
        }
        h3 {
            color: #2c3e50;
            font-size: 18px;
            margin-top: 25px;
            margin-bottom: 15px;
        }
        p {
            margin-bottom: 15px;
            text-indent: 2em;
        }
        ul, ol {
            margin-left: 30px;
            margin-bottom: 15px;
        }
        li {
            margin-bottom: 8px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px 15px;
            text-align: left;
        }
        th {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white;
            font-weight: bold;
        }
        tr:nth-child(even) {
            background-color: #f8f9fa;
        }
        tr:hover {
            background-color: #e8f4fc;
        }
        .summary-box {
            background: linear-gradient(135deg, #fff3cd 0%, #ffeeba 100%);
            border: 1px solid #ffeeba;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }
        .highlight {
            color: #e74c3c;
            font-weight: bold;
        }
        .footer {
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #777;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        {content}
        <div class="footer">
            报告生成时间: {timestamp}
        </div>
    </div>
</body>
</html>
        """.format(
            content=html_body,
            timestamp=datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')
        )
        
        # 保存HTML文件
        html_path = output_dir / f"{md_path.stem}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return html_path
        
    except ImportError:
        print(" 需要安装 markdown 库: pip install markdown")
        return None
    except Exception as e:
        print(f" 生成HTML报告失败: {str(e)}")
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
    
    print(f" [报告生成] 开始生成空压机报告...")
    print(f" [报告生成] 提取数据: {extracted_data_path}")
    print(f" [报告生成] 计算结果: {calculation_result_path}")
    print(f" [报告生成] 输出目录: {output_dir}")
    
    try:
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 读取数据
        with open(extracted_data_path, 'r', encoding='utf-8') as f:
            extracted_data = json.load(f)
        
        with open(calculation_result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        print(f" [报告生成] 数据读取成功")
        
        # 生成报告（MD + Word）
        report_path = generate_word_report(extracted_data, result, output_dir)
        
        # 输出结果
        if report_path:
            print(f" 报告: {report_path}")
            print(f" [报告生成] 报告生成完成")
        else:
            print(f" [报告生成] 报告生成失败")
            sys.exit(1)
            
    except Exception as e:
        print(f" [报告生成] 处理失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()