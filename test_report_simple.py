#!/usr/bin/env python3
"""
简化的报告生成测试脚本
"""

import subprocess
from pathlib import Path

def main():
    """主函数"""
    project_root = Path(__file__).parent
    
    print("=" * 60)
    print("空压机报告生成功能测试")
    print("=" * 60)
    
    # 测试数据路径
    test_session_dir = project_root / "tmp" / "session_20260427_195432_630"
    extracted_data_path = test_session_dir / "extracted_data.json"
    calculation_result_path = test_session_dir / "calculation_result.json"
    output_dir = test_session_dir / "generated_reports"
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 运行skill脚本
    skill_script = project_root / ".claude" / "skills" / "generate-air-compressor-report" / "scripts" / "generate_air_compressor_report.py"
    
    cmd = [
        "python", str(skill_script),
        str(extracted_data_path),
        str(calculation_result_path),
        str(output_dir)
    ]
    
    print(f"运行命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
        
        print("\n输出:")
        print(result.stdout)
        
        if result.stderr:
            print("\n错误:")
            print(result.stderr)
        
        # 检查生成的文件
        word_files = list(output_dir.glob("空压系统数智化升级方案_*.docx"))
        excel_files = list(output_dir.glob("2026年空压云智控报价单_*.xlsx"))
        
        print("\n生成文件:")
        for file in word_files:
            print(f"✅ Word报告: {file}")
        for file in excel_files:
            print(f"✅ Excel报价单: {file}")
            
    except Exception as e:
        print(f"错误: {str(e)}")


if __name__ == "__main__":
    main()