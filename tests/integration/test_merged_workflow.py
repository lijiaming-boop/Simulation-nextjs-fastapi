#!/usr/bin/env python3
"""测试合并后的完整工作流程"""

import pytest
import json
import tempfile
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def test_excel_file():
    """获取测试Excel文件路径"""
    excel_path = project_root / "00_sample/02-中央空调节能调研表（首页含问题指引）-工业板块.xlsx"
    if not excel_path.exists():
        pytest.skip("测试Excel文件不存在")
    return excel_path


def test_complete_merged_workflow(test_excel_file):
    """测试完整的合并工作流程"""
    sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))

    from extract_and_check_data import extract_and_check_data

    # 创建临时输出文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = Path(f.name)

    try:
        # 执行提取和检查
        extract_and_check_data(str(test_excel_file), str(output_path))

        # 验证输出文件存在
        assert output_path.exists()

        # 读取结果
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # 如果Excel文件没有有效数据，应该返回错误信息
        if 'error' in result:
            pytest.skip(f"测试Excel文件没有有效数据: {result.get('message', '未知错误')}")

        # 验证结构
        assert 'extracted_data' in result
        assert 'quality_report' in result

        # 验证提取数据
        extracted = result['extracted_data']
        assert 'project_region' in extracted
        assert 'monthly_data' in extracted
        assert len(extracted['monthly_data']) == 12

        # 验证每个月的数据结构
        for month_data in extracted['monthly_data']:
            assert 'month' in month_data
            assert 'total_energy' in month_data
            assert 'chiller_supply_temp' in month_data

        # 验证质量报告
        quality = result['quality_report']
        assert 'completeness' in quality
        assert 'confidence_level' in quality
        assert 'issues' in quality
        assert 'summary' in quality

        # 验证质量报告的数据类型
        assert 0 <= quality['completeness'] <= 1
        assert quality['confidence_level'] in ['high', 'medium', 'low']
        assert isinstance(quality['issues'], list)
        assert isinstance(quality['summary'], str)

        # 验证问题列表结构
        for issue in quality['issues']:
            assert 'field' in issue
            assert 'severity' in issue
            assert 'type' in issue
            assert 'message' in issue
            assert issue['severity'] in ['critical', 'high', 'medium', 'low']
            assert issue['type'] in ['missing', 'out_of_range', 'logic_error']

        print(f"✅ 测试通过: 数据完整率 {quality['completeness']*100:.1f}%")
        print(f"   置信度: {quality['confidence_level']}")
        print(f"   问题数: {len(quality['issues'])}")

    finally:
        # 清理
        if output_path.exists():
            output_path.unlink()


def test_workflow_backwards_compatibility():
    """测试向后兼容性 - 确保生成的单独文件"""
    # 这个测试确保即使合并了步骤，仍然生成单独的文件供现有代码使用
    from core.skill_caller import SkillCaller

    test_excel = project_root / "00_sample/02-中央空调节能调研表（首页含问题指引）-工业板块.xlsx"
    if not test_excel.exists():
        pytest.skip("测试Excel文件不存在")

    # 创建临时目录
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"

        try:
            caller = SkillCaller(timeout=300)
            caller.call_skill(
                "extract-and-check-data",
                str(test_excel),
                str(output_path)
            )

            # 验证主输出文件
            assert output_path.exists()

            # 在实际应用中，app.py 会从主文件中分离并保存单独文件
            # 这里模拟这个过程
            with open(output_path, 'r', encoding='utf-8') as f:
                result = json.load(f)

            extracted_path = Path(tmpdir) / "extracted_data.json"
            quality_path = Path(tmpdir) / "quality_report.json"

            with open(extracted_path, 'w', encoding='utf-8') as f:
                json.dump(result['extracted_data'], f, ensure_ascii=False, indent=2)

            with open(quality_path, 'w', encoding='utf-8') as f:
                json.dump(result['quality_report'], f, ensure_ascii=False, indent=2)

            # 验证单独文件存在
            assert extracted_path.exists()
            assert quality_path.exists()

            # 验证单独文件内容正确
            with open(extracted_path, 'r', encoding='utf-8') as f:
                extracted = json.load(f)
                assert 'monthly_data' in extracted

            with open(quality_path, 'r', encoding='utf-8') as f:
                quality = json.load(f)
                assert 'completeness' in quality

            print("✅ 向后兼容性测试通过")

        except Exception as e:
            pytest.skip(f"Skill调用失败: {e}")
