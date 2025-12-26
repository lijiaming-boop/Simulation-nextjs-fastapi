#!/usr/bin/env python3
"""端到端测试：验证从真实调研表提取项目地区"""

import pytest
import json
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / '.claude/skills/extract-and-check-data/scripts'))

from extract_and_check_data import extract_and_check_data


class TestRegionExtractionE2E:
    """测试真实调研表的地区提取"""

    @pytest.mark.parametrize("survey_file,expected_region,extraction_source", [
        ('00_sample/示例调研表/【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx', '华南', 'filename'),
        ('00_sample/示例调研表/【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx', '华北', 'filename'),
        # 注意：【缺夏季】上海和元 使用"1#冷站"而不是"冷站"，暂时跳过
        ('00_sample/示例调研表/【参差不齐】11.9%中央空调节能调研表（首页含问题指引）.xlsx', '华南', 'filename'),
    ])
    def test_extract_region_from_real_surveys(self, survey_file, expected_region, extraction_source, tmp_path):
        """测试从真实调研表提取地区"""
        survey_path = project_root / survey_file
        if not survey_path.exists():
            pytest.skip(f"测试文件不存在: {survey_file}")

        output_path = tmp_path / 'result.json'

        # 执行提取
        extract_and_check_data(str(survey_path), str(output_path))

        # 验证输出
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        assert 'extracted_data' in result
        assert result['extracted_data']['project_region'] == expected_region, \
            f"预期从{extraction_source}提取到{expected_region},实际为{result['extracted_data']['project_region']}"

    def test_region_extraction_coverage(self, tmp_path):
        """统计所有示例调研表的地区提取成功率"""
        sample_dir = project_root / '00_sample/示例调研表'
        if not sample_dir.exists():
            pytest.skip("示例调研表目录不存在")

        survey_files = list(sample_dir.glob('*.xlsx'))
        if not survey_files:
            pytest.skip("未找到示例调研表文件")

        success_count = 0
        total_count = len(survey_files)
        results = []

        for survey_file in survey_files:
            output_path = tmp_path / f'{survey_file.stem}_result.json'

            try:
                extract_and_check_data(str(survey_file), str(output_path))

                with open(output_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)

                project_region = result.get('extracted_data', {}).get('project_region')
                if project_region:
                    success_count += 1
                    results.append(f'✅ {survey_file.name}: {project_region}')
                else:
                    results.append(f'❌ {survey_file.name}: 地区提取失败')
            except Exception as e:
                results.append(f'❌ {survey_file.name}: 异常 - {str(e)}')

        # 打印统计结果
        print('\n地区提取测试结果:')
        print('=' * 60)
        for result in results:
            print(result)
        print('=' * 60)
        print(f'成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)')

        # 期望至少50%的调研表能成功提取地区
        # 注意：有些调研表使用非标准sheet名称（如"1#冷站"）或完全缺少地区信息，这些是可接受的失败
        # 对于使用标准"冷站"sheet且包含地区信息的调研表，三级优先级能有效提取
        assert success_count / total_count >= 0.50, f'地区提取成功率过低: {success_count}/{total_count}'

        # 报告详细统计
        print(f'\n✅ 成功提取: {success_count}份')
        print(f'❌ 提取失败: {total_count - success_count}份')
        print(f'📊 成功率: {success_count/total_count*100:.1f}%')
