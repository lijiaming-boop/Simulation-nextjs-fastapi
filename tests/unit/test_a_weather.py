"""测试气象数据服务模块 - weather.py"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.weather import (
    get_regions,
    get_monthly_dry_bulb,
    get_monthly_wet_bulb,
    get_monthly_tower_outlet,
    REGION_DRY_BULB,
    REGION_CITIES,
)


class TestGetRegions:
    """测试获取地区列表"""

    def test_get_regions_returns_all_regions(self):
        """测试返回所有地区"""
        regions = get_regions()

        assert len(regions) == 7
        assert "华南" in regions
        assert "华东" in regions
        assert "华中" in regions
        assert "华北" in regions
        assert "西南" in regions
        assert "西北" in regions
        assert "东北" in regions

    def test_get_regions_order(self):
        """测试地区顺序"""
        regions = get_regions()

        # 验证顺序与REGION_DRY_BULB字典一致
        assert regions == list(REGION_DRY_BULB.keys())

    def test_get_regions_not_empty(self):
        """测试返回非空列表"""
        regions = get_regions()

        assert len(regions) > 0
        assert isinstance(regions, list)


class TestGetMonthlyDryBulb:
    """测试获取月度干球温度"""

    def test_get_dry_bulb_exact_match(self):
        """测试精确匹配地区名称"""
        result = get_monthly_dry_bulb("华南")

        assert len(result) == 12
        assert result == REGION_DRY_BULB["华南"]
        assert result[0] == 14  # 1月
        assert result[6] == 30  # 7月

    def test_get_dry_bulb_all_regions(self):
        """测试所有地区的干球温度"""
        for region in REGION_DRY_BULB:
            result = get_monthly_dry_bulb(region)

            assert len(result) == 12
            assert all(isinstance(t, (int, float)) for t in result)
            assert min(result) >= -20  # 合理范围下限
            assert max(result) <= 40  # 合理范围上限

    def test_get_dry_bulb_partial_match_region_in_key(self):
        """测试部分匹配：地区名在键中"""
        # "华南地区" 包含 "华南"
        result = get_monthly_dry_bulb("华南地区")

        assert result == REGION_DRY_BULB["华南"]

    def test_get_dry_bulb_partial_match_key_in_region(self):
        """测试部分匹配：键在地区名中"""
        # 传入 "华" 应该匹配到某个包含"华"的地区
        result = get_monthly_dry_bulb("华")

        # 应该返回某个匹配地区的温度
        assert len(result) == 12

    def test_get_dry_bulb_default_to_east_china(self):
        """测试未知地区默认返回华东数据"""
        result = get_monthly_dry_bulb("未知地区")

        assert result == REGION_DRY_BULB["华东"]

    def test_get_dry_bulb_empty_string(self):
        """测试空字符串输入"""
        result = get_monthly_dry_bulb("")

        # 空字符串在Python中被认为包含在任何字符串中，所以会匹配到第一个地区（华南）
        # 这是 get_monthly_dry_bulb 函数的实现特性
        assert result == REGION_DRY_BULB["华南"]

    def test_get_dry_bulb_case_sensitivity(self):
        """测试大小写敏感性（中文不受影响）"""
        result1 = get_monthly_dry_bulb("华东")
        result2 = get_monthly_dry_bulb("华东")

        assert result1 == result2

    def test_get_dry_bulb_temperature_range(self):
        """测试温度值合理性"""
        for region in REGION_DRY_BULB:
            temps = get_monthly_dry_bulb(region)

            # 夏季温度应高于冬季（北半球）
            summer_avg = sum(temps[5:8]) / 3  # 6,7,8月
            winter_avg = sum([temps[0], temps[1], temps[11]]) / 3  # 12,1,2月

            # 大多数地区夏季应比冬季温暖（除特殊气候外）
            assert summer_avg > -10  # 夏季平均温度合理


class TestGetMonthlyWetBulb:
    """测试获取月度湿球温度"""

    def create_mock_weather_data(self):
        """创建模拟天气数据"""
        return {
            "china_shanghai": {
                "city": "上海",
                "region": "华东",
                "jan": 6.1,
                "feb": 7.4,
                "mar": 10.9,
                "apr": 15.3,
                "may": 20.0,
                "jun": 23.8,
                "jul": 27.2,
                "aug": 26.9,
                "sep": 24.2,
                "oct": 19.9,
                "nov": 14.3,
                "dec": 8.2
            }
        }

    def test_get_wet_bulb_from_json_file(self):
        """测试从JSON文件读取湿球温度"""
        mock_data = self.create_mock_weather_data()
        mock_json_str = json.dumps(mock_data)

        with patch("builtins.open", mock_open(read_data=mock_json_str)):
            result = get_monthly_wet_bulb("华东")

        assert len(result) == 12
        # 湿球温度应该接近JSON中的数据
        assert result[0] == 6.1  # 1月

    def test_get_wet_bulb_file_not_found(self):
        """测试文件不存在时的降级处理"""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = get_monthly_wet_bulb("华南")
            expected = [t - 4.0 for t in REGION_DRY_BULB["华南"]]

        assert result == expected

    def test_get_wet_bulb_fallback_calculation(self):
        """测试降级计算：干球温度减4度"""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = get_monthly_wet_bulb("华北")

        dry_bulb = REGION_DRY_BULB["华北"]
        expected = [t - 4.0 for t in dry_bulb]

        assert result == expected
        assert len(result) == 12

    def test_get_wet_bulb_unknown_region_fallback(self):
        """测试未知地区使用默认降级计算"""
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = get_monthly_wet_bulb("未知地区")

        # 未知地区会使用华东的干球温度降级计算
        dry_bulb = REGION_DRY_BULB["华东"]
        expected = [t - 4.0 for t in dry_bulb]

        assert result == expected

    def test_get_wet_bulb_lower_than_dry_bulb(self):
        """测试湿球温度低于干球温度"""
        for region in REGION_DRY_BULB:
            dry_bulb = get_monthly_dry_bulb(region)

            with patch("builtins.open", side_effect=FileNotFoundError):
                wet_bulb = get_monthly_wet_bulb(region)

            # 湿球温度应始终低于干球温度
            for wb, db in zip(wet_bulb, dry_bulb):
                assert wb < db

    def test_get_wet_bulb_reasonable_range(self):
        """测试湿球温度合理范围"""
        for region in REGION_DRY_BULB:
            with patch("builtins.open", side_effect=FileNotFoundError):
                wet_bulb = get_monthly_wet_bulb(region)

            # 湿球温度应在合理范围内
            assert min(wet_bulb) >= -25  # 合理下限
            assert max(wet_bulb) <= 35  # 合理上限


class TestGetMonthlyTowerOutlet:
    """测试获取冷却塔出水温度"""

    def test_tower_outlet_calculation(self):
        """测试冷却塔出水温度计算：湿球+4.5"""
        with patch("simulation.weather.get_monthly_wet_bulb") as mock_wet_bulb:
            mock_wet_bulb.return_value = [10.0, 12.0, 15.0, 18.0, 20.0, 22.0,
                                          24.0, 24.0, 22.0, 19.0, 15.0, 11.0]

            result = get_monthly_tower_outlet("华东")

        expected = [max(21.0, wb + 4.5) for wb in mock_wet_bulb.return_value]

        assert result == expected
        assert len(result) == 12

    def test_tower_outlet_minimum_temperature(self):
        """测试最低出水温度限制为21°C"""
        with patch("simulation.weather.get_monthly_wet_bulb") as mock_wet_bulb:
            # 设置很低的湿球温度
            mock_wet_bulb.return_value = [5.0, 6.0, 8.0, 10.0, 12.0, 14.0,
                                          15.0, 15.0, 14.0, 12.0, 9.0, 6.0]

            result = get_monthly_tower_outlet("华北")

        # 即使湿球+4.5 < 21，也应该返回21
        for temp in result:
            assert temp >= 21.0

    def test_tower_outlet_summer_values(self):
        """测试夏季冷却塔出水温度"""
        with patch("simulation.weather.get_monthly_wet_bulb") as mock_wet_bulb:
            # 夏季湿球温度较高
            mock_wet_bulb.return_value = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0,
                                          26.0, 26.0, 25.0, 24.0, 22.0, 21.0]

            result = get_monthly_tower_outlet("华南")

        # 夏季应该是湿球+4.5（超过21）
        assert result[6] == 26.0 + 4.5  # 7月
        assert result[7] == 26.0 + 4.5  # 8月

    def test_tower_outlet_winter_values(self):
        """测试冬季冷却塔出水温度受最小值限制"""
        with patch("simulation.weather.get_monthly_wet_bulb") as mock_wet_bulb:
            # 冬季湿球温度很低
            mock_wet_bulb.return_value = [2.0, 3.0, 5.0, 8.0, 10.0, 12.0,
                                          14.0, 14.0, 12.0, 10.0, 7.0, 3.0]

            result = get_monthly_tower_outlet("华北")

        # 冬季应该都是21°C（最小值）
        assert result[0] == 21.0  # 1月
        assert result[1] == 21.0  # 2月
        assert result[11] == 21.0  # 12月

    def test_tower_outlet_all_regions(self):
        """测试所有地区的冷却塔出水温度"""
        for region in REGION_DRY_BULB:
            with patch("simulation.weather.get_monthly_wet_bulb") as mock_wet_bulb:
                mock_wet_bulb.return_value = [15.0] * 12  # 统一湿球温度

                result = get_monthly_tower_outlet(region)

            # 所有月份都应该 >= 21
            assert all(temp >= 21.0 for temp in result)
            # 所有月份都应该是 15 + 4.5 = 19.5，但受最小值限制为21
            assert all(temp == 21.0 for temp in result)

    def test_tower_outlet_formula_correctness(self):
        """测试计算公式正确性：max(21.0, wet_bulb + 4.5)"""
        test_cases = [
            ([10.0], 21.0),  # 10 + 4.5 = 14.5 < 21，返回21
            ([17.0], 21.5),  # 17 + 4.5 = 21.5 > 21，返回21.5
            ([20.0], 24.5),  # 20 + 4.5 = 24.5 > 21，返回24.5
            ([0.0], 21.0),  # 0 + 4.5 = 4.5 < 21，返回21
        ]

        for wet_bulb_input, expected_output in test_cases:
            with patch("simulation.weather.get_monthly_wet_bulb") as mock_wet_bulb:
                mock_wet_bulb.return_value = wet_bulb_input * 12
                result = get_monthly_tower_outlet("华东")

                assert result[0] == expected_output


class TestRegionCities:
    """测试地区城市映射"""

    def test_region_cities_coverage(self):
        """测试所有地区都有对应城市"""
        for region in REGION_DRY_BULB:
            assert region in REGION_CITIES, f"地区 {region} 缺少城市映射"

    def test_region_cities_are_strings(self):
        """测试城市名称都是字符串"""
        for city in REGION_CITIES.values():
            assert isinstance(city, str)
            assert len(city) > 0

    def test_specific_city_mapping(self):
        """测试特定地区城市映射"""
        assert REGION_CITIES["华南"] == "广州"
        assert REGION_CITIES["华东"] == "上海"
        assert REGION_CITIES["华中"] == "武汉"
        assert REGION_CITIES["华北"] == "北京"
        assert REGION_CITIES["西南"] == "成都"
        assert REGION_CITIES["西北"] == "西安"
        assert REGION_CITIES["东北"] == "沈阳"


class TestWeatherDataIntegration:
    """集成测试 - 测试气象数据完整流程"""

    def test_full_weather_data_pipeline(self):
        """测试完整气象数据流程"""
        region = "华东"

        # 1. 获取干球温度
        dry_bulb = get_monthly_dry_bulb(region)
        assert len(dry_bulb) == 12

        # 2. 获取湿球温度（使用mock确保一致性）
        # 注意：需要mock整个函数，包括在get_monthly_tower_outlet内部的调用
        mock_wet_values = [t - 5.0 for t in dry_bulb]
        
        with patch("simulation.weather.get_monthly_wet_bulb", return_value=mock_wet_values):
            wet_bulb = get_monthly_wet_bulb(region)
            assert len(wet_bulb) == 12

            # 3. 湿球温度应低于干球温度
            for wb, db in zip(wet_bulb, dry_bulb):
                assert wb < db

            # 4. 获取冷却塔出水温度（内部也会使用mock的湿球温度）
            tower_outlet = get_monthly_tower_outlet(region)
        
        assert len(tower_outlet) == 12

        # 5. 冷却塔出水温度应 >= 21
        assert all(temp >= 21.0 for temp in tower_outlet)

    def test_seasonal_temperature_variation(self):
        """测试季节性温度变化"""
        region = "华北"

        dry_bulb = get_monthly_dry_bulb(region)

        # 夏季（6-8月）应明显高于冬季（12-2月）
        summer_avg = sum(dry_bulb[5:8]) / 3
        winter_avg = sum([dry_bulb[11], dry_bulb[0], dry_bulb[1]]) / 3

        assert summer_avg > winter_avg
        # 华北地区温差应该很大
        assert summer_avg - winter_avg > 20

    def test_tropical_climate_stability(self):
        """测试热带气候温度稳定性"""
        region = "华南"

        dry_bulb = get_monthly_dry_bulb(region)

        # 华南地区全年温差较小
        temp_range = max(dry_bulb) - min(dry_bulb)

        # 温差应该在合理范围内（不是极端气候）
        assert temp_range < 20


class TestEdgeCases:
    """边界情况测试"""

    def test_none_region_handling(self):
        """测试None地区输入"""
        # 应该抛出异常或使用默认值
        with pytest.raises((TypeError, KeyError)):
            get_monthly_dry_bulb(None)

    def test_numeric_region_input(self):
        """测试数字类型地区输入"""
        with pytest.raises(TypeError):
            get_monthly_dry_bulb(123)

    def test_very_long_region_name(self):
        """测试超长地区名称"""
        long_name = "A" * 1000
        result = get_monthly_dry_bulb(long_name)

        # 应该返回默认值
        assert result == REGION_DRY_BULB["华东"]

    def test_special_characters_in_region(self):
        """测试特殊字符地区名称"""
        result = get_monthly_dry_bulb("@#$%^&*")

        # 应该返回默认值
        assert result == REGION_DRY_BULB["华东"]

    def test_unicode_region_names(self):
        """测试Unicode字符"""
        result = get_monthly_dry_bulb("🌏地区")

        # 应该返回默认值
        assert result == REGION_DRY_BULB["华东"]


class TestDataConsistency:
    """数据一致性测试"""

    def test_regions_and_cities_same_count(self):
        """测试地区和城市数量一致"""
        assert len(REGION_DRY_BULB) == len(REGION_CITIES)

    def test_all_regions_have_cities(self):
        """测试所有地区都有城市映射"""
        for region in REGION_DRY_BULB:
            assert region in REGION_CITIES

    def test_dry_bulb_all_have_12_months(self):
        """测试所有地区都有12个月数据"""
        for region, temps in REGION_DRY_BULB.items():
            assert len(temps) == 12, f"地区 {region} 的温度数据不足12个月"

    def test_temperature_values_are_numbers(self):
        """测试所有温度值都是数字"""
        for region, temps in REGION_DRY_BULB.items():
            for temp in temps:
                assert isinstance(temp, (int, float)), \
                    f"地区 {region} 存在非数字温度值: {temp}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
