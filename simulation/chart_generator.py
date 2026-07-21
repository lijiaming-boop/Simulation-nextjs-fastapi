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


def generate_cop_curve_chart(
    cop_curve: dict,
    rated_cop: float = None,
    group_label: str = "主机组",
) -> go.Figure:
    """渲染单组主机的 COP 性能曲线图。

    Args:
        cop_curve: {负载率(0-1): COP} 字典，例如 {0.3: 4.8, 0.5: 5.6, 0.7: 6.3, 1.0: 6.0}
        rated_cop: 额定 COP，用于绘制参考线（可选）
        group_label: 主机组标签，用于图标题
    """
    if not cop_curve:
        fig = go.Figure()
        fig.update_layout(
            title=f"{group_label} COP 性能曲线（无数据）",
            xaxis_title="负载率", yaxis_title="COP",
            height=350,
            annotations=[dict(
                text="请在下方表格中填写 COP 性能数据",
                showarrow=False, xref="paper", yref="paper",
                x=0.5, y=0.5, font=dict(size=14, color="gray"),
            )],
        )
        return fig

    # 按负载率排序
    sorted_items = sorted(cop_curve.items(), key=lambda x: x[0])
    loads = [item[0] for item in sorted_items]
    cops = [item[1] for item in sorted_items]
    load_pct = [round(l * 100, 1) for l in loads]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=load_pct, y=cops, mode="lines+markers",
        line=dict(width=2.5, color="#4A90D9"),
        marker=dict(size=10, color="#4A90D9", line=dict(width=2, color="white")),
        hovertemplate="负载率: %{x:.1f}%<br>COP: %{y:.2f}<extra></extra>",
        name="COP 曲线",
    ))

    # 额定 COP 参考线
    if rated_cop and rated_cop > 0:
        fig.add_hline(
            y=rated_cop, line_dash="dash", line_color="red", line_width=1.5,
            annotation_text=f"额定 COP = {rated_cop:.2f}",
            annotation_position="top left",
        )

    # 最高 COP 标注
    max_cop = max(cops)
    max_idx = cops.index(max_cop)
    fig.add_annotation(
        x=load_pct[max_idx], y=max_cop,
        text=f"峰值 {max_cop:.2f}",
        showarrow=True, arrowhead=2, arrowsize=1,
        arrowcolor="#666", ax=20, ay=-30,
        font=dict(size=11, color="#333"),
    )

    fig.update_layout(
        title=f"{group_label} COP 性能曲线",
        xaxis=dict(title="负载率 (%)", dtick=10, range=[0, 110], ticksuffix="%"),
        yaxis=dict(title="COP", range=[0, max(cops) * 1.15]),
        height=350,
        margin=dict(l=50, r=30, t=50, b=40),
        hovermode="x unified",
        showlegend=False,
    )
    return fig
