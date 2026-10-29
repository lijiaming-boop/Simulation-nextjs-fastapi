"""报告生成"""


def generate_report_markdown(summary: dict, config_desc: str = "") -> str:
    bl_cop = summary["baseline_cop"]
    opt_cop = summary["optimized_cop"]
    saving = summary["saving_kwh"]
    saving_pct = summary["saving_pct"]

    report = f"""# 冷站优化控制策略仿真报告

## 核心结果

| 指标 | 基线 | 优化后 | 变化 |
|------|------|--------|------|
| 年加权系统COP | {bl_cop:.2f} | {opt_cop:.2f} | +{(opt_cop-bl_cop)/bl_cop*100:.1f}% |
| 年总耗电量(万kWh) | {summary['baseline_power_kwh']/1e4:.0f} | {summary['optimized_power_kwh']/1e4:.0f} | -{saving_pct:.1f}% |
| 年节电量(万kWh) | — | — | {saving/1e4:.0f} |
| 年节省电费(万元) | — | — | {summary['saving_cost_yuan']/1e4:.1f} |

## 分项能耗对比

| 设备 | 基线(万kWh) | 优化后(万kWh) | 节省(万kWh) | 节省率 |
|------|------------|-------------|------------|--------|
| 冷水机组 | {summary['baseline_chiller_kwh']/1e4:.0f} | {summary['optimized_chiller_kwh']/1e4:.0f} | {(summary['baseline_chiller_kwh']-summary['optimized_chiller_kwh'])/1e4:.0f} | {(summary['baseline_chiller_kwh']-summary['optimized_chiller_kwh'])/summary['baseline_chiller_kwh']*100:.1f}% |
| 冷冻泵 | {summary['baseline_chw_pump_kwh']/1e4:.0f} | {summary['optimized_chw_pump_kwh']/1e4:.0f} | {(summary['baseline_chw_pump_kwh']-summary['optimized_chw_pump_kwh'])/1e4:.0f} | {(summary['baseline_chw_pump_kwh']-summary['optimized_chw_pump_kwh'])/max(1,summary['baseline_chw_pump_kwh'])*100:.1f}% |
| 冷却泵 | {summary['baseline_cw_pump_kwh']/1e4:.0f} | {summary['optimized_cw_pump_kwh']/1e4:.0f} | {(summary['baseline_cw_pump_kwh']-summary['optimized_cw_pump_kwh'])/1e4:.0f} | {(summary['baseline_cw_pump_kwh']-summary['optimized_cw_pump_kwh'])/max(1,summary['baseline_cw_pump_kwh'])*100:.1f}% |
| 冷却塔 | {summary['baseline_tower_kwh']/1e4:.0f} | {summary['optimized_tower_kwh']/1e4:.0f} | {(summary['baseline_tower_kwh']-summary['optimized_tower_kwh'])/1e4:.0f} | {(summary['baseline_tower_kwh']-summary['optimized_tower_kwh'])/max(1,summary['baseline_tower_kwh'])*100:.1f}% |

## 季节性能

| 季节 | 基线COP | 优化COP |
|------|---------|---------|
| 夏季(6-9月) | {summary['summer_base_cop']:.2f} | {summary['summer_opt_cop']:.2f} |
| 冬季(12-2月) | {summary['winter_base_cop']:.2f} | {summary['winter_opt_cop']:.2f} |

## 优化策略说明

1. **冷冻泵温差控制**: 目标供回水温差5°C，根据实际冷量动态调节泵频率
2. **冷却塔优化变频**: 根据环温和逼近度智能调节风机频率
3. **冷却泵**: 工频泵保持不变，变频泵按温差控制

---
*仿真方法: 全年8760小时逐时计算，基于主机COP性能曲线*
"""
    return report
