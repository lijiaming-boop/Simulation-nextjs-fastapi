"""测试图表生成模块 - chart_generator.py"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulation.chart_generator import (
    generate_monthly_cop_chart,
    generate_energy_structure_chart,
    generate_cop_heatmap,
)


def create_mock_simulation_data():
    """创建模拟的仿真数据用于测试"""
    # 创建8760小时的模拟数据
    hours = np.arange(8760)
    months = pd.date_range("2024-01-01", periods=8760, freq="h").month.values
    hour_of_day = hours % 24

    # 模拟环境温度（夏季高，冬季低）
    ambient_temp = 15 + 10 * np.sin(2 * np.pi * (months - 1) / 12) + \
                   3 * np.sin(2 * np.pi * hour_of_day / 24)

    # 模拟负载率（夏季高，冬季低；白天高，夜间低）
    load_ratio = 0.5 + 0.3 * np.sin(2 * np.pi * (months - 1) / 12) + \
                 0.2 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    load_ratio = np.clip(load_ratio, 0.2, 0.95)

    # 模拟制冷量（基于负载率）
    cooling_load = load_ratio * 10000  # 最大10000kW

    # 模拟功耗
    chiller_power = cooling_load / 5.0  # COP≈5
    chw_pump_power = 200 * load_ratio
    cw_pump_power = 250 * load_ratio
    tower_power = 150 * load_ratio

    total_power = chiller_power + chw_pump_power + cw_pump_power + tower_power
    system_cop = cooling_load / total_power

    # 创建DataFrame
    df = pd.DataFrame({
        "hour": hours,
        "month": months,
        "day_of_year": hours // 24,
        "hour_of_day": hour_of_day,
        "ambient_temp_c": ambient_temp,
        "total_chiller_count": np.ones(8760, dtype=int),
        "load_ratio": load_ratio,
        "cooling_load_kw": cooling_load,
        "chiller_power_kw": chiller_power,
        "chw_pump_power_kw": chw_pump_power,
        "cw_pump_power_kw": cw_pump_power,
        "tower_fan_power_kw": tower_power,
        "total_power_kw": total_power,
        "system_cop": system_cop,
    })

    return df


def create_mock_summary():
    """创建模拟的仿真汇总数据"""
    return {
        "baseline_cop": 5.23,
        "optimized_cop": 6.15,
        "annual_cooling_kwh": 50000000,
        "baseline_power_kwh": 9560000,
        "optimized_power_kwh": 8130000,
        "saving_kwh": 1430000,
        "saving_pct": 14.96,
        "saving_cost_yuan": 715000,
        "baseline_chiller_kwh": 6800000,
        "baseline_chw_pump_kwh": 1250000,
        "baseline_cw_pump_kwh": 1450000,
        "baseline_tower_kwh": 450000,
        "optimized_chiller_kwh": 5900000,
        "optimized_chw_pump_kwh": 850000,
        "optimized_cw_pump_kwh": 1450000,
        "optimized_tower_kwh": 280000,
        "summer_base_cop": 5.80,
        "summer_opt_cop": 6.45,
        "winter_base_cop": 4.03,
        "winter_opt_cop": 5.20,
    }


class TestGenerateMonthlyCopChart:
    """测试月度COP对比图表"""

    def test_generate_with_valid_data(self):
        """测试使用有效数据生成图表"""
        df_base = create_mock_simulation_data()
        df_opt = create_mock_simulation_data()

        # 优化后的COP稍高一些
        df_opt["system_cop"] = df_opt["system_cop"] * 1.15

        fig = generate_monthly_cop_chart(df_base, df_opt)

        # 验证返回的是Plotly Figure对象
        assert fig is not None
        assert hasattr(fig, 'data')
        assert len(fig.data) == 2  # 两个trace（基线和优化）

        # 验证trace类型
        assert fig.data[0].type == 'bar'
        assert fig.data[1].type == 'bar'

        # 验证X轴有12个月
        assert len(fig.data[0].x) == 12

        # 验证Y值都是正数
        assert all(v > 0 for v in fig.data[0].y)
        assert all(v > 0 for v in fig.data[1].y)

        print("\n 月度COP图表生成成功")
        print(f"   基线平均COP: {np.mean(fig.data[0].y):.2f}")
        print(f"   优化平均COP: {np.mean(fig.data[1].y):.2f}")

    def test_generate_with_empty_dataframe(self):
        """测试空DataFrame的处理"""
        df_empty = pd.DataFrame()
        df_valid = create_mock_simulation_data()

        # 应该抛出异常或返回None
        with pytest.raises((KeyError, ValueError, AttributeError)):
            generate_monthly_cop_chart(df_empty, df_valid)

    def test_chart_layout_properties(self):
        """测试图表布局属性"""
        df_base = create_mock_simulation_data()
        df_opt = create_mock_simulation_data()
        df_opt["system_cop"] = df_opt["system_cop"] * 1.15

        fig = generate_monthly_cop_chart(df_base, df_opt)

        # 验证标题
        assert fig.layout.title.text == "月度系统COP对比"

        # 验证Y轴标签
        assert fig.layout.yaxis.title.text == "系统COP"

        # 验证柱状图模式
        assert fig.layout.barmode == "group"

        # 验证高度
        assert fig.layout.height == 450

        print("\n 图表布局属性正确")


class TestGenerateEnergyStructureChart:
    """测试能耗结构饼图"""

    def test_generate_with_valid_summary(self):
        """测试使用有效汇总数据生成图表"""
        summary = create_mock_summary()

        fig = generate_energy_structure_chart(summary)

        # 验证返回的是Plotly Figure对象
        assert fig is not None
        assert hasattr(fig, 'data')

        # 验证有两个子图（两个饼图）
        assert len(fig.data) == 2

        # 验证trace类型
        assert fig.data[0].type == 'pie'
        assert fig.data[1].type == 'pie'

        # 验证每个饼图有4个类别
        assert len(fig.data[0].labels) == 4
        assert len(fig.data[1].labels) == 4

        # 验证标签正确
        expected_labels = ["冷水机组", "冷冻泵", "冷却泵", "冷却塔"]
        assert list(fig.data[0].labels) == expected_labels

        print("\n 能耗结构图表生成成功")
        print(f"   基线总耗电: {sum(fig.data[0].values) / 1e4:.0f}万kWh")
        print(f"   优化总耗电: {sum(fig.data[1].values) / 1e4:.0f}万kWh")

    def test_generate_with_missing_keys(self):
        """测试缺少必需字段的处理"""
        summary = {"baseline_chiller_kwh": 1000}  # 缺少其他字段

        with pytest.raises(KeyError):
            generate_energy_structure_chart(summary)

    def test_generate_with_zero_values(self):
        """测试零值处理"""
        summary = create_mock_summary()
        summary["baseline_tower_kwh"] = 0
        summary["optimized_tower_kwh"] = 0

        fig = generate_energy_structure_chart(summary)

        # 应该能正常生成，但饼图中该项占比为0
        assert fig is not None
        assert fig.data[0].values[3] == 0  # 冷却塔

        print("\n 零值处理正确")

    def test_subplot_titles_format(self):
        """测试子图标题格式"""
        summary = create_mock_summary()

        fig = generate_energy_structure_chart(summary)

        # 验证标题包含总耗电量
        assert "万kWh" in fig.layout.annotations[0].text
        assert "万kWh" in fig.layout.annotations[1].text

        print("\n 子图标题格式正确")


class TestGenerateCopHeatmap:
    """测试COP热力图"""

    def test_generate_with_valid_data(self):
        """测试使用有效数据生成热力图"""
        df_opt = create_mock_simulation_data()

        fig = generate_cop_heatmap(df_opt)

        # 验证返回的是Plotly Figure对象
        assert fig is not None
        assert hasattr(fig, 'data')

        # 验证是热力图
        assert fig.data[0].type == 'heatmap'

        # 验证X轴有12个月
        assert len(fig.data[0].x) == 12

        # 验证Y轴有24小时
        assert len(fig.data[0].y) == 24

        # 验证Z值矩阵维度
        assert fig.data[0].z.shape == (24, 12)

        print("\n COP热力图生成成功")
        print(f"   COP范围: {fig.data[0].z.min():.2f} - {fig.data[0].z.max():.2f}")

    def test_generate_with_missing_columns(self):
        """测试缺少必需列的处理"""
        df_incomplete = pd.DataFrame({
            "month": [1, 2, 3],
            "hour_of_day": [0, 1, 2],
            # 缺少 system_cop 列
        })

        with pytest.raises((KeyError, ValueError)):
            generate_cop_heatmap(df_incomplete)

    def test_heatmap_colorscale(self):
        """测试热力图颜色配置"""
        df_opt = create_mock_simulation_data()

        fig = generate_cop_heatmap(df_opt)

        # 验证使用了 RdYlGn 颜色方案
        colorscale = fig.data[0].colorscale
        
        # RdYlGn 的特征：红色开始，绿色结束
        assert colorscale[0][1] == 'rgb(165,0,38)'  # 起始为红色
        assert colorscale[-1][1] == 'rgb(0,104,55)'  # 结束为深绿色
        
        # 验证有11个颜色节点
        assert len(colorscale) == 11

        # 验证有颜色条
        assert fig.data[0].colorbar is not None
        assert fig.data[0].colorbar.title.text == "COP"

        print("\n 热力图颜色配置正确")

    def test_axis_labels(self):
        """测试坐标轴标签"""
        df_opt = create_mock_simulation_data()

        fig = generate_cop_heatmap(df_opt)

        # 验证标题
        assert fig.layout.title.text == "全年系统COP热力图 (优化策略)"

        # 验证X轴标签
        assert fig.layout.xaxis.title.text == "月份"

        # 验证Y轴标签
        assert fig.layout.yaxis.title.text == "时刻"

        # 验证高度
        assert fig.layout.height == 500

        print("\n 坐标轴标签正确")


class TestIntegration:
    """集成测试 - 测试所有图表一起生成"""

    def test_generate_all_charts(self):
        """测试生成所有图表"""
        df_base = create_mock_simulation_data()
        df_opt = create_mock_simulation_data()
        df_opt["system_cop"] = df_opt["system_cop"] * 1.15

        summary = create_mock_summary()

        # 生成所有图表
        fig_cop = generate_monthly_cop_chart(df_base, df_opt)
        fig_energy = generate_energy_structure_chart(summary)
        fig_heatmap = generate_cop_heatmap(df_opt)

        # 验证所有图表都成功生成
        assert fig_cop is not None
        assert fig_energy is not None
        assert fig_heatmap is not None

        print("\n 所有图表生成成功")
        print(f"   - 月度COP对比图: {len(fig_cop.data)} traces")
        print(f"   - 能耗结构图: {len(fig_energy.data)} traces")
        print(f"   - COP热力图: {fig_heatmap.data[0].z.shape}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
