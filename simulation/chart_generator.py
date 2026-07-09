"""图表生成 - Plotly交互式图表"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def generate_monthly_cop_chart(df_base: pd.DataFrame, df_opt: pd.DataFrame) -> go.Figure:
    monthly_base = df_base.groupby("month").apply(
        lambda x: x["cooling_load_kw"].sum() / x["total_power_kw"].sum(),
        include_groups=False
    ).values
    monthly_opt = df_opt.groupby("month").apply(
        lambda x: x["cooling_load_kw"].sum() / x["total_power_kw"].sum(),
        include_groups=False
    ).values

    months = [f"{m}月" for m in range(1, 13)]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="基线(实际运行)", x=months, y=monthly_base,
                         marker_color="#5B9BD5", text=[f"{v:.2f}" for v in monthly_base],
                         textposition="outside"))
    fig.add_trace(go.Bar(name="优化(控制策略)", x=months, y=monthly_opt,
                         marker_color="#70AD47", text=[f"{v:.2f}" for v in monthly_opt],
                         textposition="outside"))

    fig.update_layout(
        title="月度系统COP对比",
        yaxis_title="系统COP", barmode="group",
        yaxis_range=[0, max(max(monthly_base), max(monthly_opt)) * 1.2],
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=450,
    )
    return fig


def generate_energy_structure_chart(summary: dict) -> go.Figure:
    labels = ["冷水机组", "冷冻泵", "冷却泵", "冷却塔"]
    base_values = [
        summary["baseline_chiller_kwh"],
        summary["baseline_chw_pump_kwh"],
        summary["baseline_cw_pump_kwh"],
        summary["baseline_tower_kwh"],
    ]
    opt_values = [
        summary["optimized_chiller_kwh"],
        summary["optimized_chw_pump_kwh"],
        summary["optimized_cw_pump_kwh"],
        summary["optimized_tower_kwh"],
    ]
    colors = ["#5B9BD5", "#FFC000", "#ED7D31", "#A5A5A5"]

    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "pie"}, {"type": "pie"}]],
                        subplot_titles=[
                            f"基线 (总耗电{sum(base_values)/1e4:.0f}万kWh)",
                            f"优化后 (总耗电{sum(opt_values)/1e4:.0f}万kWh)"
                        ])
    fig.add_trace(go.Pie(labels=labels, values=base_values, marker_colors=colors,
                         textinfo="label+percent"), row=1, col=1)
    fig.add_trace(go.Pie(labels=labels, values=opt_values, marker_colors=colors,
                         textinfo="label+percent"), row=1, col=2)
    fig.update_layout(title="冷站能耗结构对比", height=400)
    return fig


def generate_cop_heatmap(df_opt: pd.DataFrame) -> go.Figure:
    pivot = df_opt.pivot_table(values="system_cop", index="hour_of_day",
                               columns="month", aggfunc="mean")

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[f"{m}月" for m in range(1, 13)],
        y=[f"{h}:00" for h in range(24)],
        colorscale="RdYlGn",
        zmin=pivot.values.min() * 0.95,
        zmax=pivot.values.max() * 1.05,
        colorbar=dict(title="COP"),
    ))
    fig.update_layout(
        title="全年系统COP热力图 (优化策略)",
        xaxis_title="月份", yaxis_title="时刻",
        height=500,
    )
    return fig
