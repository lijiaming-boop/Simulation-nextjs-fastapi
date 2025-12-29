#!/usr/bin/env python3
"""
季节性范围值解析的端到端测试
使用真实的调研表文件验证季节性解析功能
"""

import pytest
import json
import tempfile
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))


@pytest.mark.skipif(
    not (project_root / "00_sample/示例调研表").exists(),
    reason="示例调研表目录不存在"
)
def test_seasonal_parsing_with_real_excel():
    """使用真实调研表测试季节性范围值解析"""
    from extract_and_check_data import extract_and_check_data

    # 查找包含范围值的示例调研表
    sample_dir = project_root / "00_sample/示例调研表"
    excel_files = list(sample_dir.glob("*.xlsx"))

    if not excel_files:
        pytest.skip("未找到示例调研表文件")

    # 使用第一个调研表进行测试
    excel_path = excel_files[0]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = Path(f.name)

    try:
        # 执行提取
        extract_and_check_data(str(excel_path), str(output_path))

        # 读取结果
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # 验证结果结构
        assert 'extracted_data' in result
        assert 'quality_report' in result

        monthly_data = result['extracted_data']['monthly_data']
        assert len(monthly_data) == 12

        # 验证季节性解析是否生效（通过检查冬夏季数据差异）
        # 注意：只有当调研表中包含范围值时，这个差异才会显现
        # 这里只做结构验证，具体数值验证在单元测试中完成

        for month_record in monthly_data:
            assert 'month' in month_record
            assert 1 <= month_record['month'] <= 12

        print(f"✅ 季节性解析端到端测试通过: {excel_path.name}")

    finally:
        if output_path.exists():
            output_path.unlink()


def test_seasonal_parsing_consistency():
    """验证季节性解析的一致性（不同月份的相同范围值应该解析为不同数值）"""
    from extract_and_check_data import parse_range_value_seasonal

    # 水泵频率范围值在不同季节应该有不同结果
    winter_result = parse_range_value_seasonal("30-50", 1, 'cooling_pump_freq')
    summer_result = parse_range_value_seasonal("30-50", 7, 'cooling_pump_freq')
    spring_result = parse_range_value_seasonal("30-50", 4, 'cooling_pump_freq')

    # 冬夏春三季结果应该不同
    assert winter_result != summer_result
    assert winter_result != spring_result
    assert summer_result != spring_result

    # 验证数值符合预期
    assert winter_result == 30.0  # 下限
    assert summer_result == 50.0  # 上限
    assert spring_result == 40.0  # 平均
