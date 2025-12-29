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


def test_get_season():
    """测试季节判断函数"""
    from extract_and_check_data import get_season

    # 冬季
    assert get_season(12) == 'winter'
    assert get_season(1) == 'winter'
    assert get_season(2) == 'winter'

    # 春季
    assert get_season(3) == 'spring'
    assert get_season(4) == 'spring'
    assert get_season(5) == 'spring'

    # 夏季
    assert get_season(6) == 'summer'
    assert get_season(7) == 'summer'
    assert get_season(8) == 'summer'

    # 秋季
    assert get_season(9) == 'autumn'
    assert get_season(10) == 'autumn'
    assert get_season(11) == 'autumn'


def test_parse_range_value_seasonal():
    """测试季节性范围值解析"""
    from extract_and_check_data import parse_range_value_seasonal

    # 水泵频率 - 冬季取下限
    assert parse_range_value_seasonal("30-50", 1, 'cooling_pump_freq') == 30.0

    # 水泵频率 - 夏季取上限
    assert parse_range_value_seasonal("30-50", 7, 'cooling_pump_freq') == 50.0

    # 水泵频率 - 春季取平均
    assert parse_range_value_seasonal("30-50", 4, 'cooling_pump_freq') == 40.0

    # 供水温度 - 冬季取上限（相反）
    assert parse_range_value_seasonal("7-10", 1, 'chiller_supply_temp') == 10.0

    # 供水温度 - 夏季取下限（相反）
    assert parse_range_value_seasonal("7-10", 7, 'chiller_supply_temp') == 7.0

    # 供水温度 - 秋季取平均
    assert parse_range_value_seasonal("7-10", 10, 'chiller_supply_temp') == 8.5

    # 温差 - 冬季取下限
    assert parse_range_value_seasonal("3-5", 2, 'cooling_water_temp_diff') == 3.0

    # 温差 - 夏季取上限
    assert parse_range_value_seasonal("3-5", 8, 'freezing_water_temp_diff') == 5.0


def test_get_season_edge_cases():
    """测试 get_season 函数的边界情况"""
    from extract_and_check_data import get_season

    # 测试无效月份 - 小于1
    with pytest.raises(ValueError, match="Invalid month: 0. Must be between 1 and 12."):
        get_season(0)

    # 测试无效月份 - 大于12
    with pytest.raises(ValueError, match="Invalid month: 13. Must be between 1 and 12."):
        get_season(13)

    # 测试无效月份 - 负数
    with pytest.raises(ValueError, match="Invalid month: -1. Must be between 1 and 12."):
        get_season(-1)

    # 测试无效月份 - 超大值
    with pytest.raises(ValueError, match="Invalid month: 100. Must be between 1 and 12."):
        get_season(100)


def test_parse_range_value_seasonal_edge_cases():
    """测试 parse_range_value_seasonal 函数的边界情况"""
    from extract_and_check_data import parse_range_value_seasonal

    # 测试颠倒的范围值（50-30 应该被处理为 30-50）
    # 水泵频率 - 冬季应取最小值（30），即使范围是倒序的
    assert parse_range_value_seasonal("50-30", 1, 'cooling_pump_freq') == 30.0

    # 水泵频率 - 夏季应取最大值（50），即使范围是倒序的
    assert parse_range_value_seasonal("50-30", 7, 'cooling_pump_freq') == 50.0

    # 供水温度 - 冬季应取最大值（10），即使范围是倒序的
    assert parse_range_value_seasonal("10-7", 1, 'chiller_supply_temp') == 10.0

    # 供水温度 - 夏季应取最小值（7），即使范围是倒序的
    assert parse_range_value_seasonal("10-7", 7, 'chiller_supply_temp') == 7.0

    # 测试秋季月份
    # 水泵频率 - 秋季取平均
    assert parse_range_value_seasonal("30-50", 9, 'cooling_pump_freq') == 40.0
    assert parse_range_value_seasonal("30-50", 11, 'cooling_pump_freq') == 40.0

    # 供水温度 - 秋季取平均
    assert parse_range_value_seasonal("7-10", 9, 'chiller_supply_temp') == 8.5

    # 测试字段名精确匹配（不应匹配包含 'supply_temp' 子串的其他字段）
    # 假设有个字段叫 'some_supply_temp_other'，不应该被当作供水温度
    # 冬季应取最小值，而不是最大值
    assert parse_range_value_seasonal("30-50", 1, 'some_supply_temp_other') == 30.0
