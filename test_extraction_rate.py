#!/usr/bin/env python3
"""
测试空压调研表文件的信息提取率
"""

import os
import json
import sys
from pathlib import Path
import subprocess
import tempfile
import shutil

def test_file_extraction(file_path, output_dir):
    """测试单个文件的信息提取率"""
    print(f"\n{'='*60}")
    print(f"测试文件: {file_path.name}")
    print(f"文件大小: {file_path.stat().st_size / 1024:.1f} KB")
    print(f"{'='*60}")
    
    # 创建临时输出文件
    output_file = output_dir / f"result_{file_path.stem}.json"
    
    try:
        # 调用数据提取脚本 - 使用新的LLM版本
        script_path = Path(".trae/skills/extract-air-compressor-data-llm/scripts/extract_air_compressor_data_llm.py")
        
        cmd = [
            sys.executable,
            str(script_path),
            str(file_path),
            str(output_file),
            file_path.name  # 原始文件名
        ]
        
        print(f"执行命令: {' '.join(cmd)}")
        
        # 执行提取
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2分钟超时
        )
        
        if result.returncode == 0:
            print("✅ 提取成功")
            
            # 读取结果
            if output_file.exists():
                with open(output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 分析提取结果
                return analyze_extraction_result(file_path.name, data)
            else:
                print("❌ 输出文件不存在")
                return None
        else:
            print(f"❌ 提取失败 (返回码: {result.returncode})")
            print(f"错误输出: {result.stderr}")
            return {
                "file_name": file_path.name,
                "status": "failed",
                "error": result.stderr,
                "completeness": 0.0
            }
            
    except subprocess.TimeoutExpired:
        print("❌ 提取超时")
        return {
            "file_name": file_path.name,
            "status": "timeout",
            "error": "执行超时",
            "completeness": 0.0
        }
    except Exception as e:
        print(f"❌ 执行异常: {str(e)}")
        return {
            "file_name": file_path.name,
            "status": "error",
            "error": str(e),
            "completeness": 0.0
        }

def analyze_extraction_result(file_name, data):
    """分析提取结果的完整性"""
    print(f"\n📊 分析提取结果...")
    
    if data.get("error"):
        print(f"❌ 提取错误: {data.get('message', '未知错误')}")
        return {
            "file_name": file_name,
            "status": "failed",
            "error": data.get("message", "未知错误"),
            "completeness": 0.0
        }
    
    extracted_data = data.get("extracted_data", {})
    quality_report = data.get("quality_report", {})
    
    # 计算完整性
    completeness = quality_report.get("completeness", 0.0)
    confidence = quality_report.get("confidence_level", "unknown")
    issues = quality_report.get("issues", [])
    
    print(f"📈 数据完整度: {completeness * 100:.1f}%")
    print(f"🎯 置信水平: {confidence}")
    print(f"⚠️  问题数量: {len(issues)}")
    
    # 分析关键字段
    key_fields = [
        "companyName", "projectName", "projectLocation", "industryType",
        "totalAnnualEnergyConsumption", "electricityPrice", 
        "alarmPressureLowerLimit", "averagePressure",
        "dailyRunningHours", "annualRunningDays"
    ]
    
    filled_fields = 0
    missing_fields = []
    
    for field in key_fields:
        value = extracted_data.get(field)
        if value is not None and value != "" and value != "未知" and value != "未填写":
            filled_fields += 1
            print(f"✅ {field}: {value}")
        else:
            missing_fields.append(field)
            print(f"❌ {field}: 缺失")
    
    field_completeness = filled_fields / len(key_fields)
    
    # 设备信息
    equipment_list = extracted_data.get("equipmentList", [])
    print(f"🔧 设备数量: {len(equipment_list)}")
    
    if equipment_list:
        for i, eq in enumerate(equipment_list[:3]):  # 只显示前3个
            print(f"   设备{i+1}: {eq.get('brand', '未知')} {eq.get('model', '未知')} - {eq.get('ratedPower', '未知')}kW")
    
    # 问题分析
    if issues:
        print(f"\n⚠️  发现的问题:")
        for issue in issues[:5]:  # 只显示前5个问题
            severity = issue.get("severity", "low")
            field = issue.get("field", "未知字段")
            description = issue.get("description", "")
            print(f"   [{severity.upper()}] {field}: {description}")
    
    return {
        "file_name": file_name,
        "status": "success",
        "completeness": completeness,
        "field_completeness": field_completeness,
        "confidence": confidence,
        "issues_count": len(issues),
        "equipment_count": len(equipment_list),
        "missing_fields": missing_fields,
        "key_data": {
            "company": extracted_data.get("companyName", ""),
            "project": extracted_data.get("projectName", ""),
            "location": extracted_data.get("projectLocation", ""),
            "industry": extracted_data.get("industryType", ""),
            "energy": extracted_data.get("totalAnnualEnergyConsumption", ""),
            "price": extracted_data.get("electricityPrice", "")
        }
    }

def main():
    """主函数"""
    print("🚀 开始测试空压调研表文件的信息提取率")
    
    # 调研表文件目录
    survey_dir = Path("00_sample/示例调研表/空压调研表")
    
    if not survey_dir.exists():
        print(f"❌ 调研表目录不存在: {survey_dir}")
        return
    
    # 创建临时输出目录
    output_dir = Path("tmp/extraction_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取所有调研表文件
    file_patterns = ["*.xlsx", "*.xls", "*.docx", "*.doc"]
    test_files = []
    
    for pattern in file_patterns:
        test_files.extend(survey_dir.glob(pattern))
    
    # 过滤掉临时文件
    test_files = [f for f in test_files if not f.name.startswith("~$")]
    
    print(f"📁 找到 {len(test_files)} 个调研表文件")
    
    if not test_files:
        print("❌ 未找到任何调研表文件")
        return
    
    # 测试结果
    results = []
    
    # 逐个测试文件
    for i, file_path in enumerate(test_files, 1):
        print(f"\n🔄 进度: {i}/{len(test_files)}")
        result = test_file_extraction(file_path, output_dir)
        if result:
            results.append(result)
    
    # 生成汇总报告
    print(f"\n{'='*80}")
    print("📋 测试汇总报告")
    print(f"{'='*80}")
    
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] != "success"]
    
    print(f"✅ 成功提取: {len(successful)} 个文件")
    print(f"❌ 提取失败: {len(failed)} 个文件")
    
    if successful:
        avg_completeness = sum(r["completeness"] for r in successful) / len(successful)
        avg_field_completeness = sum(r["field_completeness"] for r in successful) / len(successful)
        
        print(f"📊 平均数据完整度: {avg_completeness * 100:.1f}%")
        print(f"📊 平均字段完整度: {avg_field_completeness * 100:.1f}%")
        
        # 按完整度排序
        successful.sort(key=lambda x: x["completeness"], reverse=True)
        
        print(f"\n🏆 提取效果最好的文件:")
        for r in successful[:3]:
            print(f"   {r['file_name']}: {r['completeness']*100:.1f}% (设备:{r['equipment_count']}个)")
        
        print(f"\n⚠️  提取效果较差的文件:")
        for r in successful[-3:]:
            print(f"   {r['file_name']}: {r['completeness']*100:.1f}% (问题:{r['issues_count']}个)")
            if r['missing_fields']:
                print(f"      缺失字段: {', '.join(r['missing_fields'][:5])}")
    
    if failed:
        print(f"\n❌ 失败文件详情:")
        for r in failed:
            print(f"   {r['file_name']}: {r['status']} - {r.get('error', '未知错误')[:100]}")
    
    # 保存详细结果
    report_file = output_dir / "extraction_test_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "summary": {
                "total_files": len(test_files),
                "successful": len(successful),
                "failed": len(failed),
                "avg_completeness": avg_completeness if successful else 0,
                "avg_field_completeness": avg_field_completeness if successful else 0
            },
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    
    # 清理临时文件
    try:
        for result_file in output_dir.glob("result_*.json"):
            result_file.unlink()
    except:
        pass

if __name__ == "__main__":
    main()