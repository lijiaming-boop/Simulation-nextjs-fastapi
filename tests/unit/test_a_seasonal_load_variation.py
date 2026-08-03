"""测试负荷模型季节差异改进"""
# todo

import pytest
import numpy as np
from simulation.simulator import (
    PlantSimulator,
    PlantConfig,
    infer_monthly_load_factors
)


class TestSeasonalLoadVariation:
    """测试负荷模型季节差异"""

    def test_default_monthly_factors_exist(self):
        """测试默认月度负载率系数存在且合理"""
        config = PlantConfig()

        assert hasattr(config, 'monthly_load_factor')
        assert len(config.monthly_load_factor) == 12
        assert max(config.monthly_load_factor) == 1.0
        assert min(config.monthly_load_factor) >= 0.3
        assert min(config.monthly_load_factor) <= 0.5

    def test_plr_varies_by_month(self):
        """测试负载率随月份变化"""
        config = PlantConfig(base_load_ratio=0.7)
        simulator = PlantSimulator(config, monthly_ambient=[25] * 12)

        # 夏季中午负载率应较高（7月，13点）
        plr_summer_noon = simulator._calc_plr(12, 7)

        # 冬季凌晨负载率应较低（1月，3点）
        plr_winter_night = simulator._calc_plr(2, 1)

        # 验证夏季 > 冬季
        assert plr_summer_noon > plr_winter_night, \
            f"夏季PLR({plr_summer_noon:.3f})应高于冬季({plr_winter_night:.3f})"

        # 验证范围合理
        assert 0.2 <= plr_summer_noon <= 0.95
        assert 0.2 <= plr_winter_night <= 0.95

        print(f"夏季中午PLR: {plr_summer_noon:.3f}")
        print(f"冬季凌晨PLR: {plr_winter_night:.3f}")
        print(f"差异: {(plr_summer_noon - plr_winter_night) * 100:.1f}%")

    def test_plr_same_hour_different_months(self):
        """测试同一小时不同月份的PLR差异"""
        config = PlantConfig(base_load_ratio=0.7)
        simulator = PlantSimulator(config, monthly_ambient=[25] * 12)

        # 固定中午12点，比较不同月份
        hour = 12
        plr_values = []

        for month in range(1, 13):
            plr = simulator._calc_plr(hour, month)
            plr_values.append(plr)

        # 验证有明显的季节性波动
        max_plr = max(plr_values)
        min_plr = min(plr_values)
        variation = max_plr - min_plr

        assert variation > 0.3, \
            f"月度PLR差异应大于0.3，实际为{variation:.3f}"

        # 验证夏季（6-8月）PLR较高
        summer_plr = np.mean(plr_values[5:8])  # 6,7,8月
        winter_plr = np.mean(plr_values[11:] + plr_values[:2])  # 12,1,2月

        assert summer_plr > winter_plr, \
            f"夏季平均PLR({summer_plr:.3f})应高于冬季({winter_plr:.3f})"

        print(f"最大PLR: {max_plr:.3f} (月份{plr_values.index(max_plr) + 1})")
        print(f"最小PLR: {min_plr:.3f} (月份{plr_values.index(min_plr) + 1})")
        print(f"季节差异: {variation:.3f}")

    def test_plr_clip_bounds(self):
        """测试PLR边界限制"""
        config = PlantConfig(base_load_ratio=0.7)
        simulator = PlantSimulator(config, monthly_ambient=[25] * 12)

        # 极端情况测试
        for month in range(1, 13):
            for hour in range(24):
                plr = simulator._calc_plr(hour, month)
                assert 0.20 <= plr <= 0.95, \
                    f"PLR超出范围: month={month}, hour={hour}, plr={plr}"

    def test_backward_compatibility(self):
        """测试向后兼容性（旧代码仍能运行）"""
        # 不传 monthly_load_factor，使用默认值
        config = PlantConfig()
        simulator = PlantSimulator(config, monthly_ambient=[25] * 12)

        # 应该能正常执行
        plr = simulator._calc_plr(12, 7)
        assert 0.2 <= plr <= 0.95


class TestInferMonthlyLoadFactors:
    """测试从调研表反推负载系数"""

    def test_infer_from_valid_data(self):
        """从有效数据反推"""
        ac_data = {
            "monthly_data": {
                str(m): {"total_energy": 100 + m * 10}
                for m in range(12)
            }
        }

        factors = infer_monthly_load_factors(ac_data)

        assert len(factors) == 12
        assert max(factors) == 1.0  # 最大值应归一化为1.0
        assert min(factors) > 0  # 最小值应大于0

        # 验证单调递增（因为测试数据是递增的）
        for i in range(len(factors) - 1):
            assert factors[i] <= factors[i + 1], \
                f"系数应递增: {factors}"

        print(f"反推系数: {factors}")

    def test_infer_with_missing_data(self):
        """处理缺失数据"""
        ac_data = {
            "monthly_data": {
                "0": {"total_energy": 100},  # 1月
                "6": {"total_energy": 200},  # 7月
                # 其他月份缺失
            }
        }

        factors = infer_monthly_load_factors(ac_data)

        assert len(factors) == 12
        # 有数据的月份应正确计算
        assert factors[0] == 0.5  # 100/200
        assert factors[6] == 1.0  # 200/200
        # 缺失数据应有默认值
        assert factors[1] == 0.5  # 默认值

    def test_infer_from_empty_data(self):
        """空数据返回默认值"""
        ac_data = {}

        factors = infer_monthly_load_factors(ac_data)

        assert len(factors) == 12
        # 应返回默认系数
        expected = [0.40, 0.40, 0.50, 0.60, 0.75, 0.90,
                    1.00, 1.00, 0.85, 0.65, 0.50, 0.40]
        assert factors == expected

    def test_infer_with_zero_energy(self):
        """处理零能耗数据"""
        ac_data = {
            "monthly_data": {
                "0": {"total_energy": 0},  # 零能耗
                "6": {"total_energy": 100},
            }
        }

        factors = infer_monthly_load_factors(ac_data)

        # 零能耗应被忽略或使用默认值
        assert len(factors) == 12


class TestSimulationWithSeasonalLoad:
    """测试带季节差异的完整仿真"""

    def test_baseline_simulation_produces_realistic_cop(self):
        """基线仿真产生合理的COP趋势"""
        config = PlantConfig(
            base_load_ratio=0.7,
            monthly_chiller_count=[1, 1, 1, 2, 2, 2, 2, 2, 2, 1, 1, 1]
        )

        # 添加简单的主机配置
        from simulation.simulator import ChillerGroup
        config.chillers = [
            ChillerGroup(
                name="测试主机",
                qty=2,
                capacity_kw=5000,
                rated_power_kw=800,
                rated_cop=6.0,
                variable_freq=True
            )
        ]

        # 使用华东地区气象数据
        monthly_ambient = [5, 6, 11, 17, 22, 26, 30, 30, 26, 20, 14, 7]

        simulator = PlantSimulator(config, monthly_ambient)
        df_base = simulator.simulate_baseline()

        # 验证月度COP趋势
        monthly_cop = df_base.groupby("month")["system_cop"].mean()

        # 夏季COP应高于冬季（因为负荷高，主机效率高）
        summer_cop = monthly_cop.loc[[6, 7, 8]].mean()
        winter_cop = monthly_cop.loc[[12, 1, 2]].mean()

        assert summer_cop > winter_cop, \
            f"夏季COP({summer_cop:.2f})应高于冬季({winter_cop:.2f})"

        print(f"夏季平均COP: {summer_cop:.2f}")
        print(f"冬季平均COP: {winter_cop:.2f}")
        print(f"季节差异: {summer_cop - winter_cop:.2f}")

    def test_optimized_simulation_respects_seasonal_pattern(self):
        """优化仿真保持季节性模式"""
        config = PlantConfig(base_load_ratio=0.7)

        from simulation.simulator import ChillerGroup, PumpGroup, TowerGroup
        config.chillers = [
            ChillerGroup(
                name="测试主机",
                qty=2,
                capacity_kw=5000,
                rated_power_kw=800,
                rated_cop=6.0,
                variable_freq=True
            )
        ]
        config.chw_pumps = [
            PumpGroup(name="冷冻泵", qty=2, power_kw=100, flow_m3h=500, variable_freq=True)
        ]
        config.cw_pumps = [
            PumpGroup(name="冷却泵", qty=2, power_kw=100, flow_m3h=800, variable_freq=False)
        ]
        config.towers = [
            TowerGroup(name="冷却塔", qty=2, fan_power_kw=22, fans_per_tower=2, variable_freq=True)
        ]

        monthly_ambient = [5, 6, 11, 17, 22, 26, 30, 30, 26, 20, 14, 7]

        simulator = PlantSimulator(config, monthly_ambient)
        df_opt = simulator.simulate_optimized(chw_target_dt=5.0)

        # 验证月度能耗趋势
        monthly_energy = df_opt.groupby("month")["total_power_kw"].sum()

        # 夏季能耗应高于冬季
        summer_energy = monthly_energy.loc[[6, 7, 8]].mean()
        winter_energy = monthly_energy.loc[[12, 1, 2]].mean()

        assert summer_energy > winter_energy, \
            f"夏季能耗({summer_energy:.0f})应高于冬季({winter_energy:.0f})"

        print(f"夏季月均能耗: {summer_energy:.0f} kWh")
        print(f"冬季月均能耗: {winter_energy:.0f} kWh")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
