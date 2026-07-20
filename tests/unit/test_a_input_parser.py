"""测试输入解析模块 - input_parser.py"""
import pytest
import json
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.input_parser import (
    parse_cop_curve_from_text,
    parse_cop_curve_from_table,
    parse_cop_curve_from_image_result,
    build_plant_config_from_extracted_data,
)
from simulation.simulator import PlantConfig, ChillerGroup, PumpGroup, TowerGroup


class TestParseCopCurveFromText:
    """测试从文本解析COP曲线"""

    def test_parse_standard_format(self):
        """测试标准格式：负载率% COP值"""
        text = "100% 6.0\n80% 6.3\n60% 6.0\n40% 4.8"
        result = parse_cop_curve_from_text(text)

        assert len(result) == 4
        assert result[1.0] == 6.0
        assert result[0.8] == 6.3
        assert result[0.6] == 6.0
        assert result[0.4] == 4.8

    def test_parse_decimal_load_ratio(self):
        """测试小数形式的负载率"""
        text = "1.0 6.0\n0.8 6.3\n0.6 6.0\n0.4 4.8"
        result = parse_cop_curve_from_text(text)

        assert len(result) == 4
        assert result[1.0] == 6.0
        assert result[0.8] == 6.3

    def test_parse_with_extra_text(self):
        """测试包含额外文本的格式"""
        text = """
        在100%负载时，COP为6.0
        在80%负载时，COP为6.3
        在60%负载时，COP为6.0
        """
        result = parse_cop_curve_from_text(text)

        assert len(result) == 3
        assert result[1.0] == 6.0
        assert result[0.8] == 6.3
        assert result[0.6] == 6.0

    def test_parse_empty_text(self):
        """测试空文本返回默认值"""
        text = ""
        result = parse_cop_curve_from_text(text)

        # 应该返回默认值
        assert len(result) == 2
        assert 0.7 in result
        assert 1.0 in result

    def test_parse_invalid_numbers(self):
        """测试无效数字的处理"""
        text = "abc xyz\n100% 6.0"
        result = parse_cop_curve_from_text(text)

        # 应该只解析有效行
        assert len(result) >= 1
        assert result[1.0] == 6.0

    def test_parse_out_of_range_cop(self):
        """测试超出合理范围的COP值被过滤"""
        text = "100% 25.0\n80% 6.3\n60% 0.5"
        result = parse_cop_curve_from_text(text)

        # COP=25和0.5应该被过滤掉
        assert 1.0 not in result or result.get(1.0, 0) < 20
        assert 0.8 in result

    def test_parse_single_line_multiple_numbers(self):
        """测试单行多个数字的情况"""
        text = "负载率100% 对应COP 6.0 效率很高"
        result = parse_cop_curve_from_text(text)

        # 应该提取第一个和最后一个数字
        assert len(result) >= 1


class TestParseCopCurveFromTable:
    """测试从表格数据解析COP曲线"""

    def test_parse_percentage_load_ratios(self):
        """测试百分比形式的负载率"""
        load_ratios = [100, 90, 80, 70, 60]
        cop_values = [6.0, 6.2, 6.3, 6.3, 6.0]

        result = parse_cop_curve_from_table(load_ratios, cop_values)

        assert len(result) == 5
        assert result[1.0] == 6.0
        assert result[0.9] == 6.2
        assert result[0.8] == 6.3

    def test_parse_decimal_load_ratios(self):
        """测试小数形式的负载率"""
        load_ratios = [1.0, 0.8, 0.6, 0.4]
        cop_values = [6.0, 6.3, 6.0, 4.8]

        result = parse_cop_curve_from_table(load_ratios, cop_values)

        assert len(result) == 4
        assert result[1.0] == 6.0
        assert result[0.8] == 6.3

    def test_parse_mixed_formats(self):
        """测试混合格式（部分百分比，部分小数）"""
        load_ratios = [100, 0.8, 60, 0.4]
        cop_values = [6.0, 6.3, 6.0, 4.8]

        result = parse_cop_curve_from_table(load_ratios, cop_values)

        assert len(result) == 4
        assert result[1.0] == 6.0
        assert result[0.8] == 6.3
        assert result[0.6] == 6.0

    def test_parse_empty_lists(self):
        """测试空列表"""
        result = parse_cop_curve_from_table([], [])

        assert len(result) == 0

    def test_parse_unequal_lists(self):
        """测试不等长列表（以较短的为准）"""
        load_ratios = [100, 80, 60]
        cop_values = [6.0, 6.3]

        result = parse_cop_curve_from_table(load_ratios, cop_values)

        assert len(result) == 2


class TestParseCopCurveFromImageResult:
    """测试从AI图片识别结果解析COP曲线"""

    def test_parse_standard_ai_response(self):
        """测试标准AI响应格式"""
        ai_response = "100 6.0\n80 6.3\n60 6.0\n40 4.8"
        result = parse_cop_curve_from_image_result(ai_response)

        assert len(result) == 4
        assert result[1.0] == 6.0
        assert result[0.8] == 6.3

    def test_parse_with_headers(self):
        """测试带表头的AI响应"""
        ai_response = """负载率 COP
100 6.0
80 6.3
60 6.0"""
        result = parse_cop_curve_from_image_result(ai_response)

        assert len(result) >= 2

    def test_parse_json_like_format(self):
        """测试类JSON格式"""
        ai_response = '[{"load": 100, "cop": 6.0}, {"load": 80, "cop": 6.3}]'
        result = parse_cop_curve_from_image_result(ai_response)

        assert len(result) >= 1

    def test_parse_empty_response(self):
        """测试空响应"""
        ai_response = ""
        result = parse_cop_curve_from_image_result(ai_response)

        assert len(result) == 0

    def test_parse_invalid_cop_values(self):
        """测试无效COP值被过滤（1-15范围外）"""
        ai_response = "100 20.0\n80 6.3\n60 0.5"
        result = parse_cop_curve_from_image_result(ai_response)

        # 只有COP=6.3应该在范围内
        assert 0.8 in result
        assert result[0.8] == 6.3


class TestBuildPlantConfigFromExtractedData:
    """测试从提取数据构建PlantConfig"""

    def create_sample_ac_data(self):
        """创建示例空调提取数据"""
        return {
            "monthly_data": {
                "1": {
                    "freezing_pump_freq": 45.0,
                    "cooling_pump_freq": 48.0,
                    "cooling_tower_freq": 50.0,
                    "freezing_water_temp_diff": 5.0,
                    "cooling_water_temp_diff": 5.0,
                    "chiller_supply_temp": 7.0
                },
                "7": {
                    "freezing_pump_freq": 50.0,
                    "cooling_pump_freq": 50.0,
                    "cooling_tower_freq": 50.0,
                    "freezing_water_temp_diff": 5.0,
                    "cooling_water_temp_diff": 5.0,
                    "chiller_supply_temp": 7.0
                }
            }
        }

    def create_sample_user_inputs(self):
        """创建示例用户输入"""
        return {
            "chiller_groups": [
                {
                    "name": "离心机组1",
                    "qty": 3,
                    "capacity_kw": 5274,
                    "rated_power_kw": 862,
                    "rated_cop": 6.12,
                    "variable_freq": True,
                    "cop_curve": {1.0: 6.12, 0.8: 6.3, 0.6: 6.0}
                }
            ],
            "chw_pumps": [
                {
                    "name": "冷冻泵",
                    "qty": 4,
                    "power_kw": 132,
                    "flow_m3h": 920,
                    "variable_freq": True
                }
            ],
            "cw_pumps": [
                {
                    "name": "冷却泵",
                    "qty": 4,
                    "power_kw": 132,
                    "flow_m3h": 1300,
                    "variable_freq": False
                }
            ],
            "towers": [
                {
                    "name": "冷却塔",
                    "qty": 6,
                    "fan_power_kw": 22,
                    "fans_per_tower": 2,
                    "variable_freq": True
                }
            ]
        }

    def test_build_complete_config(self):
        """测试完整配置构建"""
        ac_data = self.create_sample_ac_data()
        user_inputs = self.create_sample_user_inputs()

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        # 验证主机配置
        assert len(config.chillers) == 1
        assert config.chillers[0].name == "离心机组1"
        assert config.chillers[0].qty == 3
        assert config.chillers[0].capacity_kw == 5274
        assert config.chillers[0].rated_cop == 6.12
        assert config.chillers[0].variable_freq is True

        # 验证冷冻泵配置
        assert len(config.chw_pumps) == 1
        assert config.chw_pumps[0].qty == 4
        assert config.chw_pumps[0].power_kw == 132
        assert config.chw_pumps[0].variable_freq is True

        # 验证冷却泵配置
        assert len(config.cw_pumps) == 1
        assert config.cw_pumps[0].qty == 4
        assert config.cw_pumps[0].variable_freq is False

        # 验证冷却塔配置
        assert len(config.towers) == 1
        assert config.towers[0].qty == 6
        assert config.towers[0].fan_power_kw == 22
        assert config.towers[0].fans_per_tower == 2

    def test_build_config_with_monthly_data(self):
        """测试包含月度运行参数的配置构建"""
        ac_data = self.create_sample_ac_data()
        user_inputs = self.create_sample_user_inputs()

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        # 验证1月参数
        assert config.monthly_chw_pump_hz[0] == 45.0
        assert config.monthly_cw_pump_hz[0] == 48.0
        assert config.monthly_tower_hz[0] == 50.0
        assert config.monthly_chw_dt[0] == 5.0
        assert config.monthly_cw_dt[0] == 5.0
        assert config.monthly_chw_supply_temp[0] == 7.0

        # 验证7月参数
        assert config.monthly_chw_pump_hz[6] == 50.0

    def test_build_config_without_ac_data(self):
        """测试没有空调提取数据时的配置构建"""
        ac_data = {}
        user_inputs = self.create_sample_user_inputs()

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        # 应该使用默认月度参数
        assert config.monthly_chw_pump_hz[0] == 50.0  # 默认值
        assert len(config.chillers) == 1

    def test_build_config_with_none_ac_data(self):
        """测试AC数据为None时的处理"""
        ac_data = None
        user_inputs = self.create_sample_user_inputs()

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        # 应该正常构建，使用默认值
        assert len(config.chillers) == 1
        assert config.monthly_chw_pump_hz[0] == 50.0

    def test_build_config_with_user_overrides(self):
        """测试用户覆盖参数"""
        ac_data = self.create_sample_ac_data()
        user_inputs = self.create_sample_user_inputs()
        user_inputs["monthly_chiller_count"] = [2, 2, 3, 3, 4, 4, 4, 4, 3, 3, 2, 2]
        user_inputs["base_load_ratio"] = 0.75

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        assert config.monthly_chiller_count == [2, 2, 3, 3, 4, 4, 4, 4, 3, 3, 2, 2]
        assert config.base_load_ratio == 0.75

    def test_build_config_multiple_chiller_groups(self):
        """测试多主机组配置"""
        ac_data = {}
        user_inputs = {
            "chiller_groups": [
                {
                    "name": "离心机组",
                    "qty": 2,
                    "capacity_kw": 5000,
                    "rated_power_kw": 800,
                    "rated_cop": 6.0,
                    "variable_freq": True
                },
                {
                    "name": "螺杆机组",
                    "qty": 1,
                    "capacity_kw": 2000,
                    "rated_power_kw": 400,
                    "rated_cop": 5.0,
                    "variable_freq": False
                }
            ],
            "chw_pumps": [],
            "cw_pumps": [],
            "towers": []
        }

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        assert len(config.chillers) == 2
        assert config.chillers[0].name == "离心机组"
        assert config.chillers[1].name == "螺杆机组"

    def test_build_config_missing_optional_fields(self):
        """测试缺少可选字段时使用默认值"""
        ac_data = {}
        user_inputs = {
            "chiller_groups": [
                {
                    "name": "主机",
                    "qty": 1
                    # 缺少其他字段
                }
            ],
            "chw_pumps": [],
            "cw_pumps": [],
            "towers": []
        }

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        # 应该使用默认值
        assert config.chillers[0].capacity_kw == 5000
        assert config.chillers[0].rated_power_kw == 800
        assert config.chillers[0].rated_cop == 6.0

    def test_build_config_empty_user_inputs(self):
        """测试空用户输入"""
        ac_data = {}
        user_inputs = {
            "chiller_groups": [],
            "chw_pumps": [],
            "cw_pumps": [],
            "towers": []
        }

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)

        # 应该创建空配置
        assert len(config.chillers) == 0
        assert len(config.chw_pumps) == 0
        assert len(config.cw_pumps) == 0
        assert len(config.towers) == 0


class TestIntegration:
    """集成测试 - 测试解析器组合使用"""

    def test_full_parsing_workflow(self):
        """测试完整解析工作流"""
        # 1. 从文本解析COP曲线
        cop_text = "100% 6.0\n80% 6.3\n60% 6.0"
        cop_curve = parse_cop_curve_from_text(cop_text)

        # 2. 构建用户输入
        user_inputs = {
            "chiller_groups": [
                {
                    "name": "测试主机",
                    "qty": 1,
                    "capacity_kw": 1000,
                    "rated_power_kw": 167,
                    "rated_cop": 6.0,
                    "variable_freq": True,
                    "cop_curve": cop_curve
                }
            ],
            "chw_pumps": [
                {"name": "冷冻泵", "qty": 1, "power_kw": 30, "flow_m3h": 200, "variable_freq": True}
            ],
            "cw_pumps": [
                {"name": "冷却泵", "qty": 1, "power_kw": 37, "flow_m3h": 280, "variable_freq": False}
            ],
            "towers": [
                {"name": "冷却塔", "qty": 1, "fan_power_kw": 15, "fans_per_tower": 1, "variable_freq": True}
            ]
        }

        # 3. 构建配置
        config = build_plant_config_from_extracted_data({}, user_inputs)

        # 4. 验证
        assert len(config.chillers) == 1
        assert config.chillers[0].cop_curve is not None
        assert config.chillers[0].cop_curve[1.0] == 6.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
