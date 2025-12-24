#!/usr/bin/env python3
"""测试合并的提取和质量检查功能"""

import pytest
import json
import tempfile
from pathlib import Path
import sys
from unittest.mock import patch

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / ".claude/skills/extract-and-check-data/scripts"))


def test_extract_and_check_data_with_mock():
    """测试提取和质量检查的集成功能（使用模拟数据）"""
    from extract_and_check_data import DataQualityChecker, extract_and_check_data

    # 模拟提取的数据
    mock_extracted_data = {
        "project_region": "华南",
        "monthly_data": [
            {
                "month": i,
                "total_energy": 20.0 + i,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": 45.0,
                "cooling_water_temp_diff": 4.5,
                "freezing_pump_freq": 50.0,
                "freezing_water_temp_diff": 4.5,
                "cooling_tower_outlet_temp": 25.0
            }
            for i in range(1, 13)
        ]
    }

    # 创建临时输出文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        output_path = Path(f.name)

    try:
        # Mock extract_data_from_excel 函数
        with patch('extract_and_check_data.extract_data_from_excel', return_value=mock_extracted_data):
            # 执行提取和检查
            extract_and_check_data('dummy.xlsx', str(output_path))

        # 读取结果
        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # 验证结果结构
        assert 'extracted_data' in result
        assert 'quality_report' in result

        # 验证提取数据
        extracted = result['extracted_data']
        assert 'project_region' in extracted
        assert extracted['project_region'] == '华南'
        assert 'monthly_data' in extracted
        assert len(extracted['monthly_data']) == 12

        # 验证质量报告
        quality = result['quality_report']
        assert 'completeness' in quality
        assert 'confidence_level' in quality
        assert 'issues' in quality
        assert 'summary' in quality

        # 验证数据类型
        assert isinstance(quality['completeness'], (int, float))
        assert quality['confidence_level'] in ['high', 'medium', 'low']
        assert isinstance(quality['issues'], list)

        # 验证完整率应该是100%（所有字段都有值）
        assert quality['completeness'] == 1.0
        assert quality['confidence_level'] == 'high'

    finally:
        # 清理临时文件
        if output_path.exists():
            output_path.unlink()


def test_data_quality_checker():
    """测试数据质量检查器单独功能"""
    from extract_and_check_data import DataQualityChecker

    # 测试数据有缺失
    test_data = {
        "project_region": "华北",
        "monthly_data": [
            {
                "month": 1,
                "total_energy": 20.0,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": None,  # 缺失
                "cooling_water_temp_diff": 4.5,
                "freezing_pump_freq": 50.0,
                "freezing_water_temp_diff": 4.5,
                "cooling_tower_outlet_temp": 25.0
            },
            {
                "month": 2,
                "total_energy": None,  # 缺失
                "chiller_supply_temp": None,  # 缺失
                "cooling_pump_freq": 45.0,
                "cooling_water_temp_diff": 4.5,
                "freezing_pump_freq": 50.0,
                "freezing_water_temp_diff": 4.5,
                "cooling_tower_outlet_temp": 25.0
            }
        ] + [
            {
                "month": i,
                "total_energy": 20.0,
                "chiller_supply_temp": 7.0,
                "cooling_pump_freq": 45.0,
                "cooling_water_temp_diff": 4.5,
                "freezing_pump_freq": 50.0,
                "freezing_water_temp_diff": 4.5,
                "cooling_tower_outlet_temp": 25.0
            }
            for i in range(3, 13)
        ]
    }

    checker = DataQualityChecker(test_data)
    report = checker.run()

    # 验证报告结构
    assert 'completeness' in report
    assert 'confidence_level' in report
    assert 'issues' in report
    assert 'summary' in report

    # 应该有问题被检测出来
    assert len(report['issues']) > 0

    # 验证问题包含缺失字段
    issue_fields = [issue['field'] for issue in report['issues']]
    assert 'monthly_data[0].cooling_pump_freq' in issue_fields
    assert 'monthly_data[1].total_energy' in issue_fields
    assert 'monthly_data[1].chiller_supply_temp' in issue_fields
