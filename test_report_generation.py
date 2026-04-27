def test_skill_call():
    """测试skill调用功能"""
    
    print("\n🔧 [Skill测试] 开始测试skill调用...")
    
    try:
        from core.skill_caller import SkillCaller
        
        # 测试数据路径
        test_session_dir = project_root / "tmp" / "session_20260427_195432_630"
        extracted_data_path = test_session_dir / "extracted_data.json"
        calculation_result_path = test_session_dir / "calculation_result.json"
        output_dir = test_session_dir / "skill_generated_reports"
        
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 [Skill测试] 输出目录: {output_dir}")
        
        # 调用skill
        skill_caller = SkillCaller()
        print("🚀 [Skill测试] 开始调用generate-air-compressor-report skill...")
        
        skill_result = skill_caller.call_skill(
            "generate-air-compressor-report",
            str(extracted_data_path),
            str(calculation_result_path),
            str(output_dir)
        )
        
        print(f"✅ [Skill测试] Skill调用完成")
        print(f"📄 [Skill测试] Skill返回结果: {skill_result}")
        
        # 检查生成的文件
        word_files = list(output_dir.glob("空压系统数智化升级方案_*.docx"))
        excel_files = list(output_dir.glob("2026年空压云智控报价单_*.xlsx"))
        
        if word_files:
            print(f"✅ [Skill测试] Word报告生成成功: {word_files[0]}")
        else:
            print("❌ [Skill测试] Word报告生成失败")
            
        if excel_files:
            print(f"✅ [Skill测试] Excel报价单生成成功: {excel_files[0]}")
        else:
            print("❌ [Skill测试] Excel报价单生成失败")
            
    except Exception as e:
        print(f"❌ [Skill测试] Skill调用失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("空压机报告生成功能测试")
    print("=" * 60)
    
    # 测试直接调用
    test_report_generation()
    
    # 测试skill调用
    test_skill_call()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)#!/usr/bin/env python3
"""
测试报告生成功能
使用测试数据验证报告生成skill是否正常工作
"""

import json
import sys
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入报告生成模块
from .claude.skills.generate_air_compressor_report.scripts.generate_air_compressor_report import (
    generate_word_report, generate_excel_quote
)

def test_report_generation():
    """测试报告生成功能"""
    
    # 测试数据路径
    test_session_dir = project_root / "tmp" / "session_20260427_195432_630"
    extracted_data_path = test_session_dir / "extracted_data.json"
    calculation_result_path = test_session_dir / "calculation_result.json"
    output_dir = test_session_dir / "generated_reports"
    
    print(f"🔍 [测试] 开始测试报告生成功能...")
    print(f"📁 [测试] 测试数据目录: {test_session_dir}")
    print(f"📁 [测试] 提取数据文件: {extracted_data_path}")
    print(f"📁 [测试] 计算结果文件: {calculation_result_path}")
    print(f"📁 [测试] 输出目录: {output_dir}")
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 读取测试数据
        with open(extracted_data_path, 'r', encoding='utf-8') as f:
            extracted_data = json.load(f)
        
        with open(calculation_result_path, 'r', encoding='utf-8') as f:
            calculation_result = json.load(f)
        
        print(f"✅ [测试] 数据读取成功")
        print(f"📊 [测试] 企业名称: {extracted_data.get('rawData', {}).get('projectLevel', {}).get('companyName', '')}")
        print(f"📊 [测试] 节能率: {calculation_result.get('energy_saving_rate_range', '')}")
        print(f"📊 [测试] 设备数量: {len(extracted_data.get('rawData', {}).get('equipmentLevel', []))}")
        
        # 测试Word报告生成
        print("\n📄 [测试] 开始测试Word报告生成...")
        word_report_path = generate_word_report(extracted_data, calculation_result, output_dir)
        
        if word_report_path:
            print(f"✅ [测试] Word报告生成成功: {word_report_path}")
            print(f"📏 [测试] 文件大小: {word_report_path.stat().st_size} bytes")
        else:
            print("❌ [测试] Word报告生成失败")
        
        # 测试Excel报价单生成
        print("\n📊 [测试] 开始测试Excel报价单生成...")
        excel_quote_path = generate_excel_quote(extracted_data, calculation_result, output_dir)
        
        if excel_quote_path:
            print(f"✅ [测试] Excel报价单生成成功: {excel_quote_path}")
            print(f"📏 [测试] 文件大小: {excel_quote_path.stat().st_size} bytes")
        else:
            print("❌ [测试] Excel报价单生成失败")
        
        # 检查依赖库
        print("\n🔧 [测试] 检查依赖库...")
        try:
            import python_docx
            print("✅ [测试] python-docx 已安装")
        except ImportError:
            print("❌ [测试] python-docx 未安装")
            print("💡 [测试] 安装命令: pip install python-docx")
        
        try:
            import openpyxl
            print("✅ [测试] openpyxl 已安装")
        except ImportError:
            print("❌ [测试] openpyxl 未安装")
            print("💡 [测试] 安装命令: pip install openpyxl")
        
        # 总结测试结果
        print("\n📋 [测试] 测试结果总结:")
        if word_report_path and excel_quote_path:
            print("✅ [测试] 报告生成功能完全正常！")
            print(f"📄 Word报告: {word_report_path}")
            print(f"📊 Excel报价单: {excel_quote_path}")
        elif word_report_path:
            print("⚠️ [测试] Word报告生成正常，但Excel报价单生成失败")
        elif excel_quote_path:
            print("⚠️ [测试] Excel报价单生成正常，但Word报告生成失败")
        else:
            print("❌ [测试] 报告生成功能完全失败")
            
    except Exception as e:
        print(f"❌ [测试] 测试过程中出现错误: {str(e)}")
        import traceback
        traceback.print_exc()


def test_skill_call():
    """测试skill调用功能"""
    
    print("\n🔧 [Skill测试] 开始测试skill调用...")
    
    try:
        from core.skill_caller import SkillCaller
        
        # 测试数据路径
        test_session_dir = project_root / "tmp" / "session_20260427_195432_630"
        extracted_data_path = test_session_dir / "extracted_data.json"
        calculation_result_path = test_session_dir / "calculation_result.json"
        output_dir = test_session_dir / "skill_generated_reports"
        
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 [Skill测试] 输出目录: {output_dir}")
        
        # 调用skill
        skill_caller = SkillCaller()
        print("🚀 [Skill测试] 开始调用generate-air-compressor-report skill...")
        
        skill_result = skill_caller.call_skill(
            "generate-air-compressor-report",
            str(extracted_data_path),
            str(calculation_result_path),
            str(output_dir)
        )
        
        print(f"✅ [Skill测试] Skill调用完成")
        print(f"📄 [Skill测试] Skill返回结果: {skill_result}")
        
        # 检查生成的文件
        word_files = list(output_dir.glob("空压系统数智化升级方案_*.docx"))
        excel_files = list(output_dir.glob("2026年空压云智控报价单_*.xlsx"))
        
        if word_files:
            print(f"✅ [Skill测试] Word报告生成成功: {word_files[0]}")
        else:
            print("❌ [Skill测试] Word报告生成失败")
            
        if excel_files:
            print(f"✅ [Skill测试] Excel报价单生成成功: {excel_files[0]}")
        else:
            print("❌ [Skill测试] Excel报价单生成失败")
            
    except Exception as e:
        print(f"❌ [Skill测试] Skill调用失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("空压机报告生成功能测试")
    print("=" * 60)
    
    # 测试直接调用
    test_report_generation()
    
    # 测试skill调用
    test_skill_call()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)