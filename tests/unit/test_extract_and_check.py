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

    # 测试斜杠分隔符
    # 水泵频率 - 冬季取下限
    assert parse_range_value_seasonal("30/50", 1, 'cooling_pump_freq') == 30.0
    assert parse_range_value_seasonal("6.5/6", 7, 'chiller_supply_temp') == 6.0

    # 测试逗号分隔符
    # 供水温度 - 冬季取上限
    assert parse_range_value_seasonal("7,10", 1, 'chiller_supply_temp') == 10.0
    # 水泵频率 - 夏季取上限
    assert parse_range_value_seasonal("30,50", 7, 'cooling_pump_freq') == 50.0

    # 测试竖线分隔符
    # 温差 - 春季取平均
    assert parse_range_value_seasonal("3|5", 4, 'cooling_water_temp_diff') == 4.0
    # 供水温度 - 夏季取下限
    assert parse_range_value_seasonal("7|10", 7, 'chiller_supply_temp') == 7.0


def test_parse_value_with_season_and_field():
    """测试增强的 parse_value() 函数（支持季节和字段类型）"""
    from extract_and_check_data import parse_value

    # 测试水泵频率范围值 - 冬季
    result = parse_value("30-50Hz", month=1, field_name='cooling_pump_freq')
    assert result == 30.0

    # 测试水泵频率范围值 - 夏季
    result = parse_value("30-50Hz", month=7, field_name='cooling_pump_freq')
    assert result == 50.0

    # 测试供水温度范围值 - 冬季（相反逻辑）
    result = parse_value("7-10℃", month=1, field_name='chiller_supply_temp')
    assert result == 10.0

    # 测试供水温度范围值 - 夏季（相反逻辑）
    result = parse_value("7-10℃", month=7, field_name='chiller_supply_temp')
    assert result == 7.0

    # 测试温差范围值 - 春季（平均值）
    result = parse_value("3-5℃", month=4, field_name='cooling_water_temp_diff')
    assert result == 4.0

    # 测试非范围值（单一数值）- 应该不受季节影响
    result = parse_value("45Hz", month=1, field_name='cooling_pump_freq')
    assert result == 45.0

    result = parse_value("7.5℃", month=7, field_name='chiller_supply_temp')
    assert result == 7.5

    # 测试向后兼容 - 没有月份参数时默认取平均值
    result = parse_value("30-50")
    assert result == 40.0

    # 测试斜杠分隔符
    result = parse_value("6.5/6℃", month=1, field_name='chiller_supply_temp')
    assert result == 6.5  # 冬季取上限
    result = parse_value("30/50Hz", month=7, field_name='cooling_pump_freq')
    assert result == 50.0  # 夏季取上限

    # 测试逗号分隔符
    result = parse_value("7,10℃", month=7, field_name='chiller_supply_temp')
    assert result == 7.0  # 夏季取下限
    result = parse_value("3,5℃", month=4, field_name='cooling_water_temp_diff')
    assert result == 4.0  # 春季取平均

    # 测试竖线分隔符
    result = parse_value("30|50Hz", month=1, field_name='cooling_pump_freq')
    assert result == 30.0  # 冬季取下限
    result = parse_value("7|10℃", month=1, field_name='chiller_supply_temp')
    assert result == 10.0  # 冬季取上限


def test_parse_value_edge_cases():
    """测试 parse_value() 边界情况"""
    from extract_and_check_data import parse_value

    # 缺失值
    assert parse_value(None) is None
    assert parse_value("") is None
    assert parse_value("nan") is None
    assert parse_value("/") is None

    # 工频格式
    result = parse_value("工频50HZ", month=1, field_name='cooling_pump_freq')
    assert result == 50.0


def test_extract_with_seasonal_range_values():
    """测试完整提取流程中的季节性范围值解析（集成测试）"""
    from extract_and_check_data import extract_data_from_excel
    from unittest.mock import patch, MagicMock
    import pandas as pd

    # 创建模拟的 DataFrame，包含范围值数据
    # 模拟调研表的结构
    mock_df_rows = []

    # 前30行为项目信息（跳过）
    for i in range(30):
        mock_df_rows.append([''] * 20)

    # 第31行：设备运行规律的月份行（带"备注"列）
    mock_df_rows.append(['', '', '月份', '备注', '1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'])

    # 第32行：冷却泵运行频率
    mock_df_rows.append(['', '', '冷却泵运行频率', ''] + ['30-50Hz'] * 12)

    # 第33行：冷机供水温度
    mock_df_rows.append(['', '', '冷机供水温度', ''] + ['7-10℃'] * 12)

    # 第34行：冷却侧供回水温差
    mock_df_rows.append(['', '', '冷却侧供回水温差', ''] + ['3-5℃'] * 12)

    # 再填充一些行
    for i in range(10):
        mock_df_rows.append([''] * 20)

    # 第45行：用电情况统计的月份行（无"备注"列）
    mock_df_rows.append(['', '', '月份', '1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'])

    # 第46行：整个冷站用电（万kWh）
    mock_df_rows.append(['', '', '整个冷站', 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0])
    mock_df_rows.append(['', '', '万kWh', 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0])

    mock_df = pd.DataFrame(mock_df_rows)

    # Mock Excel 读取
    with patch('pandas.ExcelFile') as mock_excel:
        mock_xls = MagicMock()
        mock_xls.sheet_names = ['冷站']
        mock_excel.return_value = mock_xls

        with patch('pandas.read_excel', return_value=mock_df):
            # 调用底层提取函数
            result = extract_data_from_excel('dummy.xlsx')

            # 验证返回结果不是错误
            assert 'error' not in result or not result.get('error')

            monthly_data = result['monthly_data']
            assert len(monthly_data) == 12

            # 验证1月（冬季）- 水泵频率取下限，供水温度取上限，温差取下限
            jan_data = monthly_data[0]  # month=1
            assert jan_data['cooling_pump_freq'] == 30.0  # 下限
            assert jan_data['chiller_supply_temp'] == 10.0  # 上限（相反）
            assert jan_data['cooling_water_temp_diff'] == 3.0  # 下限

            # 验证7月（夏季）- 水泵频率取上限，供水温度取下限，温差取上限
            jul_data = monthly_data[6]  # month=7
            assert jul_data['cooling_pump_freq'] == 50.0  # 上限
            assert jul_data['chiller_supply_temp'] == 7.0  # 下限（相反）
            assert jul_data['cooling_water_temp_diff'] == 5.0  # 上限

            # 验证4月（春季）- 所有范围值取平均
            apr_data = monthly_data[3]  # month=4
            assert apr_data['cooling_pump_freq'] == 40.0  # 平均
            assert apr_data['chiller_supply_temp'] == 8.5  # 平均
            assert apr_data['cooling_water_temp_diff'] == 4.0  # 平均

            # 验证10月（秋季）- 所有范围值取平均
            oct_data = monthly_data[9]  # month=10
            assert oct_data['cooling_pump_freq'] == 40.0  # 平均
            assert oct_data['chiller_supply_temp'] == 8.5  # 平均
            assert oct_data['cooling_water_temp_diff'] == 4.0  # 平均
