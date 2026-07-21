"""冷站仿真 Streamlit UI - 输入页面和结果页面"""
import io
import json
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

from simulation.simulator import PlantSimulator, PlantConfig, ChillerGroup, PumpGroup, TowerGroup, HOURLY_LOAD_FACTOR
from simulation.chart_generator import (
    generate_monthly_cop_chart,
    generate_energy_structure_chart,
    generate_cop_heatmap,
    generate_cop_curve_chart,
)
from simulation.report_generator import generate_report_markdown
from simulation.weather import get_monthly_dry_bulb
from simulation.input_parser import parse_cop_curve_from_text, parse_cop_curve_from_table, build_plant_config_from_extracted_data
from simulation.survey_excel_parser import parse_survey_excel_from_bytes
from simulation.ai_service import ai_generate_simulation_report
from simulation.ai智能推荐月度参数模块.recommend import (
    ai_stage1_from_text,
    ai_stage2_recommend,
    ai_parse_operation_rules,
    derive_monthly_chiller_count_from_combination,
)
from simulation.ai智能推荐月度参数模块.presets import PRESET_SCHEDULES, SCHEDULE_LABELS
from simulation.ai智能推荐月度参数模块.calendar_parser import parse_calendar_smart, DEFAULT_DAY_TYPE
from simulation.ai智能推荐月度参数模块 import preset_manager


def _f(value, default: float) -> float:
    """安全转 float：当 value 为 None 时返回 default，避免 float(None) 报错。

    适用于 st.number_input 中读取可能为 None 的预填值场景。
    """
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


# ── 调研表 Excel 上传辅助 ────────────────────────────────────

def _merge_pump_groups(pump_groups: list, default_name: str) -> dict:
    """把调研表解析出的多组泵合并为单组用于 UI 预填。

    合并规则：
    - 台数累加
    - 流量/功率/扬程取首组有效值
    - 变频：任一组变频则为变频
    - 品牌：取首个非空
    """
    if not pump_groups:
        return {}
    total_qty = sum(int(p.get("qty") or 0) for p in pump_groups) or 1
    first = pump_groups[0]
    any_vf = any(p.get("variable_freq") for p in pump_groups)
    brand = next((p.get("brand") for p in pump_groups if p.get("brand")), "")
    return {
        "name": first.get("name") or default_name,
        "qty": total_qty,
        "power_kw": float(first.get("power_kw") or 0.0),
        "flow_m3h": float(first.get("flow_m3h") or 0.0),
        "variable_freq": bool(any_vf),
        "rated_head_m": first.get("rated_head_m"),
        "brand": brand,
    }


def _merge_tower_groups(tower_groups: list) -> dict:
    """把调研表解析出的多组冷却塔合并为单组用于 UI 预填。"""
    if not tower_groups:
        return {}
    total_qty = sum(int(t.get("qty") or 0) for t in tower_groups) or 1
    first = tower_groups[0]
    any_vf = any(t.get("variable_freq") for t in tower_groups)
    brand = next((t.get("brand") for t in tower_groups if t.get("brand")), "")
    return {
        "name": first.get("name") or "冷却塔",
        "qty": total_qty,
        "fan_power_kw": float(first.get("fan_power_kw") or 0.0),
        "fans_per_tower": first.get("fans_per_tower") or 2,
        "variable_freq": bool(any_vf),
        "water_flow_m3h": first.get("water_flow_m3h"),
        "approach_temp": first.get("approach_temp"),
        "brand": brand,
    }


def _apply_survey_to_prefill(survey_data: dict):
    """将调研表解析结果写入 session_state 作为预填数据源。

    同时把 monthly_data 写入 ac_extracted_data 供 input_parser 使用，
    把 region 写入 aim_user_region 供 AI 推荐模块使用。
    """
    chillers = []
    for c in survey_data.get("chillers", []):
        chillers.append({
            "name": c.get("name") or "主机",
            "qty": c.get("qty") or 1,
            "capacity_kw": c.get("capacity_kw") or 5000,
            "rated_power_kw": c.get("rated_power_kw") or 800,
            "rated_cop": c.get("rated_cop") or 6.0,
            "variable_freq": c.get("variable_freq", False),
            "chiller_type": c.get("chiller_type") or "",
            "brand": c.get("brand") or "",
        })

    chw_pumps_merged = _merge_pump_groups(survey_data.get("chw_pumps", []), "冷冻泵")
    cw_pumps_merged = _merge_pump_groups(survey_data.get("cw_pumps", []), "冷却泵")
    towers_merged = _merge_tower_groups(survey_data.get("towers", []))

    # 地区：从调研表 region_hint 推断，未识别则默认华东
    region = survey_data.get("region_hint") or "华东"

    prefill = {
        "chillers": chillers,
        "chw_pumps": [chw_pumps_merged] if chw_pumps_merged else [],
        "cw_pumps": [cw_pumps_merged] if cw_pumps_merged else [],
        "towers": [towers_merged] if towers_merged else [],
        "monthly_chiller_count": survey_data.get("monthly_chiller_count") or [1] * 12,
        "region": region,
    }
    st.session_state.survey_extracted_data = prefill
    # 同步给 AI 推荐模块（不再暴露地区选择给用户）
    st.session_state.aim_user_region = region

    # 月度运行数据写入 ac_extracted_data（input_parser 会从这里读）
    monthly_data = survey_data.get("monthly_data") or {}
    if any(monthly_data.values()):
        st.session_state.ac_extracted_data = {
            "monthly_data": monthly_data,
            "station_name": survey_data.get("station_name", ""),
        }


# ── 设备运行规律解析（月度组合/负载率/需求冷量）──────────────

_OPERATION_RULES_EXAMPLE = """过渡季节工作日开2台约克3000RT中温变频，75%负载 （或多少需求冷量）
过渡季节休息日开1台约克1800RT低温变频，75%负载 （或多少需求冷量）
冬季不开机 （或多少需求冷量）
夏季工作日开3台3000RT中温变频，80%负载 （或多少需求冷量）
夏季休息日开1台3000RT中温变频和1台1800RT低温变频，70%负载 （或多少需求冷量）"""


def _init_opr_state():
    """初始化设备运行规律模块的 session_state。"""
    defaults = {
        "opr_text": "",            # 用户填写的文字描述
        "opr_table": None,         # AI 解析结果 {combination, load_factor, cooling_demand_kw, remark, summary}
        "opr_done": False,         # 是否已成功解析
        "opr_applied": False,      # 是否已应用到月度参数
        "opr_last_text": "",       # 上次解析的文字（用于判断是否变化）
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _render_cop_curve_realtime(cop_curve, rated_cop: float, group_index: int, wv: int):
    """实时渲染 COP 性能曲线图表。

    在用户输入 COP 数据后立即绘制图表，给出直观的可视化反馈，
    便于核对数据正确性。每次调用都基于当前数据生成新图。
    """
    label = f"主机组 {group_index + 1}"
    fig = generate_cop_curve_chart(cop_curve, rated_cop=rated_cop, group_label=label)
    # 用 cop_curve 数据指纹 + 时间戳作为 key，确保数据变化后图表强制重绘
    if cop_curve:
        fingerprint = sum(int(k * 100) + int(v * 100) for k, v in cop_curve.items())
    else:
        fingerprint = 0
    chart_key = f"_cop_curve_chart_{group_index}_v{wv}_{fingerprint}"
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def _render_operation_rules_section(chiller_groups: list, wv: int):
    """渲染"设备运行规律"区块。

    流程：
    1. 显示已识别主机清单（供用户参考）
    2. 文本输入框（带示例 placeholder）
    3. AI 解析按钮 → 调用 ai_parse_operation_rules
    4. 显示可编辑的 3×12 表格（冷机运行组合/负载率/需求冷量）
    5. "应用到月度参数"按钮 → 写入 mc_*/mlf_* widget 键
    """
    _init_opr_state()

    with st.expander("📋 设备运行规律（可选）", expanded=False):
        st.caption(
            "用自然语言描述每月/每季的冷机开机组合与负载率，AI 自动整理为 12 个月表格。"
            "调研表里通常不含\"组合/负载率\"字段，可在此补充。"
        )

        # 显示主机清单
        if chiller_groups:
            ch_lines = []
            for i, cg in enumerate(chiller_groups, 1):
                qty = cg.get("qty", 1)
                cap = cg.get("capacity_kw", 0)
                vf = "变频" if cg.get("variable_freq") else "工频"
                brand = cg.get("brand", "") or ""
                name = cg.get("name", "") or f"主机组{i}"
                ch_lines.append(f"  • 主机组{i}: {name} | {qty}台 | 单台{cap}kW | {vf} | {brand}")
            st.markdown("**已识别主机清单（供描述参考）：**")
            st.markdown("\n".join(ch_lines))

        st.markdown("**填写运行规律描述**")
        st.caption("示例（可参考，无需照抄）：")
        st.code(_OPERATION_RULES_EXAMPLE, language="text")

        user_text = st.text_area(
            "运行规律描述",
            value=st.session_state.opr_text,
            height=160,
            placeholder="在此填写运行规律，可分多行写不同季节/工作日/休息日的组合与负载率...",
            key=f"opr_text_input_v{wv}",
            label_visibility="collapsed",
        )
        # 同步到 session_state（text_area 用 key，但其它地方需要 opr_text）
        st.session_state.opr_text = user_text

        c1, c2, c3 = st.columns([1, 1, 2], gap="small")
        with c1:
            parse_clicked = st.button(
                "🤖 AI 解析运行规律",
                key=f"opr_parse_btn_v{wv}",
                use_container_width=True,
                type="primary",
                disabled=not user_text.strip(),
            )
        with c2:
            apply_clicked = st.button(
                "✅ 应用到月度参数",
                key=f"opr_apply_btn_v{wv}",
                use_container_width=True,
                disabled=not st.session_state.get("opr_table"),
            )
        with c3:
            if st.session_state.get("opr_done"):
                st.success("✅ 已解析，可继续修改文字后重新解析，或直接应用到月度参数")

        # AI 解析
        if parse_clicked and user_text.strip():
            with st.spinner("AI 正在解析运行规律..."):
                try:
                    result = ai_parse_operation_rules(user_text.strip(), chiller_groups)
                except Exception as e:
                    st.error(f"AI 调用失败: {e}")
                    result = None
                if result:
                    st.session_state.opr_table = result
                    st.session_state.opr_done = True
                    st.session_state.opr_last_text = user_text
                    st.session_state.opr_applied = False
                    st.rerun()
                else:
                    st.error("AI 解析失败，请检查描述或重试")

        # 应用到月度参数
        if apply_clicked and st.session_state.get("opr_table"):
            _apply_opr_to_monthly(chiller_groups, wv)
            st.session_state.opr_applied = True
            st.rerun()

        # 显示表格（可编辑）
        opr_table = st.session_state.get("opr_table")
        if opr_table:
            st.markdown("**解析结果（可编辑后重新应用）：**")
            if opr_table.get("summary"):
                st.caption(f"💡 {opr_table['summary']}")

            months = [f"{i}月" for i in range(1, 13)]
            df = pd.DataFrame({
                "冷机运行组合": opr_table.get("chiller_combination", [""] * 12),
                "负载率": opr_table.get("load_factor", [0.0] * 12),
                "需求冷量(kW)": opr_table.get("cooling_demand_kw", [0.0] * 12),
                "备注": opr_table.get("remark", [""] * 12),
            }, index=months)
            df.index.name = "月份"

            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="fixed",
                key=f"opr_table_editor_v{wv}",
                column_config={
                    "冷机运行组合": st.column_config.TextColumn(width="medium"),
                    "负载率": st.column_config.NumberColumn(
                        min_value=0.0, max_value=1.0, step=0.01, format="%.2f", width="small"
                    ),
                    "需求冷量(kW)": st.column_config.NumberColumn(
                        min_value=0.0, step=1.0, format="%.0f", width="small"
                    ),
                    "备注": st.column_config.TextColumn(width="small"),
                },
            )

            # 同步编辑结果到 session_state（用于"应用到月度参数"）
            st.session_state.opr_table["chiller_combination"] = edited["冷机运行组合"].tolist()
            st.session_state.opr_table["load_factor"] = [round(float(v), 2) for v in edited["负载率"].tolist()]
            st.session_state.opr_table["cooling_demand_kw"] = [round(float(v), 1) for v in edited["需求冷量(kW)"].tolist()]
            st.session_state.opr_table["remark"] = edited["备注"].tolist()


def _apply_opr_to_monthly(chiller_groups: list, wv: int):
    """把设备运行规律表格结果应用到月度参数 widget 键。"""
    opr = st.session_state.get("opr_table") or {}
    if not opr:
        return

    total_available = sum(int(g.get("qty", 1)) for g in chiller_groups) or 1

    # 1. 从组合描述反推每月开机台数
    combinations = opr.get("chiller_combination", [""] * 12)
    monthly_counts = derive_monthly_chiller_count_from_combination(
        combinations, total_available=total_available
    )
    # 不开机月份至少给 1 台（仿真引擎要求 >=1）
    monthly_counts = [max(1, c) for c in monthly_counts]

    # 2. 负载率直接取表格
    load_factors = opr.get("load_factor", [0.5] * 12)
    load_factors = [round(max(0.0, min(1.0, float(v or 0))), 2) for v in load_factors]

    # 3. 写入 widget 键（注意：如果某月份负载率为0但仿真要求≥0.3，下限放宽到0.0）
    mc_keys = [f"mc_{i}_v{wv}" for i in range(12)]
    mlf_keys = [f"mlf_{i}_v{wv}" for i in range(12)]
    for i in range(12):
        st.session_state[mc_keys[i]] = int(monthly_counts[i])
        st.session_state[mlf_keys[i]] = float(load_factors[i])

    # 同时同步到 aim 模块的状态（让 AI 推荐模块感知用户已手动填写）
    st.session_state.aim_monthly_chiller_count = monthly_counts
    st.session_state.aim_monthly_load_factors = load_factors
    st.session_state.aim_stage2_done = True
    st.session_state.aim_summary = opr.get("summary", "已根据设备运行规律解析填入月度参数")


# ── AI 推荐模块辅助 ─────────────────────────────────────────

def _init_aim_state():
    """初始化 AI 推荐模块的 session_state。"""
    defaults = {
        "aim_stage1_done": False,
        "aim_stage2_done": False,
        "aim_analysis": None,
        "aim_schedule_label": "单班制办公",
        "aim_workday_curve": list(HOURLY_LOAD_FACTOR),
        "aim_offday_curve": list(HOURLY_LOAD_FACTOR),
        "aim_user_region": None,
        "aim_total_chiller_count": 3,
        "aim_day_type": DEFAULT_DAY_TYPE,
        "aim_monthly_chiller_count": [1] * 12,
        "aim_monthly_load_factors": [0.5] * 12,
        "aim_summary": "",
        "_aim_fill_trigger": False,
        "_aim_last_file": "",
        "aim_curve_epoch": 0,
        "_aim_prev_label": "",
        "_aim_cal_done": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _aim_apply_preset(label: str):
    """将指定班制的预设曲线写入 session_state，递增 epoch 使滑块自动刷新。"""
    preset = preset_manager.get_preset(label)
    if preset is None:
        # 回退到第一个可用预设
        names = preset_manager.get_preset_names()
        label = names[0] if names else "单班制办公"
        preset = preset_manager.get_preset(label)
        if preset is None:
            # 极端情况：没有任何预设，用硬编码兜底
            preset = PRESET_SCHEDULES.get("单班制办公", {})
    st.session_state.aim_workday_curve = list(preset.get("workday_curve", [0.5]*24))
    st.session_state.aim_offday_curve = list(preset.get("offday_curve", [0.5]*24))
    st.session_state.aim_schedule_label = label
    st.session_state.aim_curve_epoch = st.session_state.get("aim_curve_epoch", 0) + 1


def _aim_curve_editor(label: str, state_key: str):
    """曲线编辑器（百分制）：直接读写 session_state[state_key]。

    图表以百分制展示（0-120%），编辑区使用滑块（拖动即可连续调节）。
    内部存储仍为 0.0-1.2 小数，与仿真模块兼容。
    """
    import plotly.graph_objects as go

    current = st.session_state.get(state_key, [0.5] * 24)

    # 图表：百分制显示
    pct_vals = [round(v * 100, 1) for v in current]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(24)), y=pct_vals, mode="lines+markers",
        line=dict(width=2.5, color="#4A90D9"),
        marker=dict(size=8, color="#4A90D9"),
        hovertemplate="%{x}:00 = %{y:.0f}%<extra></extra>",
    ))
    fig.update_layout(height=220, margin=dict(l=20, r=10, t=25, b=30),
                      xaxis=dict(dtick=2, range=[-0.5, 23.5]),
                      yaxis=dict(range=[-5, 125], ticksuffix="%"),
                      title=label, dragmode=False)
    # 用曲线数据的简单指纹做 key 后缀，确保每次数据变化后图表强制重绘
    _fingerprint = sum(int(v * 100) for v in current)
    st.plotly_chart(fig, use_container_width=True, key=f"_aim_plot_{state_key}_{_fingerprint}")

    with st.expander(f"编辑{label}逐时系数（百分制）", expanded=False):
        changed = False
        epoch = st.session_state.get("aim_curve_epoch", 0)
        for ri in range(6):
            cs = st.columns(4)
            for j in range(4):
                # 列映射：col0=0-5, col1=6-11, col2=12-17, col3=18-23
                i = j * 6 + ri
                if i >= 24:
                    break
                with cs[j]:
                    # 非 widget 键存真值（按钮可安全修改）
                    val_key = f"_aim_v_{state_key}_{i}"
                    if val_key not in st.session_state:
                        st.session_state[val_key] = int(round(current[i] * 100))

                    cur_val = st.session_state[val_key]

                    # [−] [====n%====] [+]  三列
                    bc1, bc2, bc3 = st.columns([0.14, 0.72, 0.14], gap="small")
                    with bc1:
                        if st.button("−", key=f"_aim_db_{state_key}_{i}_v{epoch}",
                                     use_container_width=True):
                            st.session_state[val_key] = max(0, cur_val - 1)
                            st.rerun()
                    with bc2:
                        # slider key 含当前值 → 值变了 key 就变 → 自动从 val_key 刷新
                        s_key = f"_aim_sl_{state_key}_{i}_v{epoch}_at{cur_val}"
                        new_pct = st.slider(
                            f"{i}:00", 0, 100, cur_val, 1,
                            format="%d%%", key=s_key,
                        )
                    with bc3:
                        if st.button("+", key=f"_aim_ib_{state_key}_{i}_v{epoch}",
                                     use_container_width=True):
                            st.session_state[val_key] = min(100, cur_val + 1)
                            st.rerun()

                    # 同步：滑块拖动后回写 val_key 和曲线
                    if new_pct != cur_val:
                        st.session_state[val_key] = new_pct
                    if new_pct != int(round(current[i] * 100)):
                        current[i] = new_pct / 100.0
                        changed = True
        if changed:
            st.session_state[state_key] = current
            st.rerun()


# ── 预设弹窗（模态对话框）───────────────────────────────────

@st.dialog("保存预设", width="small")
def _aim_save_dialog(default_name: str, default_desc: str):
    """保存弹窗：覆盖当前预设。"""
    name = st.text_input("预设名称", value=default_name, key="aim_dlg_save_name")
    desc = st.text_input("预设描述", value=default_desc, key="aim_dlg_save_desc")
    c1, c2 = st.columns(2, gap="small")
    with c1:
        if st.button("完成", use_container_width=True):
            n = name.strip()
            if not n:
                st.warning("请输入名称")
            else:
                wd = st.session_state.get("aim_workday_curve", [0.5] * 24)
                od = st.session_state.get("aim_offday_curve", [0.5] * 24)
                preset_manager.save_preset(n, wd, od, desc=desc.strip(), label=n)
                # 若改名了，删除旧预设
                if n != default_name and default_name in preset_manager.get_preset_names():
                    preset_manager.delete_preset(default_name)
                preset_manager.ensure_defaults()
                st.session_state._aim_popup_mode = None
                st.session_state._aim_prev_label = n
                _aim_apply_preset(n)
                st.rerun()
    with c2:
        if st.button("取消", use_container_width=True):
            st.session_state._aim_popup_mode = None
            st.rerun()


@st.dialog("新建预设", width="small")
def _aim_new_dialog():
    """新建弹窗：所有曲线初始为 0。"""
    st.caption("新建预设，所有曲线数值初始为 0")
    name = st.text_input("预设名称", key="aim_dlg_new_name")
    desc = st.text_input("预设描述", key="aim_dlg_new_desc")
    c1, c2 = st.columns(2, gap="small")
    with c1:
        if st.button("完成", use_container_width=True):
            n = name.strip()
            if not n:
                st.warning("请输入名称")
            else:
                preset_manager.save_preset(n, [0.0] * 24, [0.0] * 24,
                                            desc=desc.strip(), label=n)
                st.session_state._aim_popup_mode = None
                st.session_state._aim_prev_label = n
                _aim_apply_preset(n)
                st.rerun()
    with c2:
        if st.button("取消", use_container_width=True):
            st.session_state._aim_popup_mode = None
            st.rerun()


def render_simulation_input_stage():
    """仿真输入页面"""
    st.subheader("🔬 冷站性能仿真 — 参数输入")
    st.caption("基于主机COP性能曲线，仿真全年8760小时运行，输出优化控制策略")

    # 初始化仿真状态
    if "sim_chiller_groups" not in st.session_state:
        st.session_state.sim_chiller_groups = [{}]
    if "sim_widget_version" not in st.session_state:
        st.session_state.sim_widget_version = 0
    if "_pending_warnings" not in st.session_state:
        st.session_state._pending_warnings = []
    if "_pending_success" not in st.session_state:
        st.session_state._pending_success = None
    if "_pending_error" not in st.session_state:
        st.session_state._pending_error = None

    # === 0. 调研表 Excel 上传（主入口）===
    with st.expander("📋 上传调研表（自动识别设备参数）", expanded=False):
        st.caption(
            "上传调研表 Excel，自动识别主机/辅机/月度运行数据。"
            "识别结果会预填到下方表单，可手动修改。"
        )
        survey_file = st.file_uploader(
            "上传调研表 Excel",
            type=["xlsx", "xls"],
            key="sim_survey_upload",
            label_visibility="collapsed",
        )
        if survey_file:
            if st.button(
                "🔍 解析调研表并预填",
                type="primary",
                use_container_width=True,
                key="sim_survey_parse_btn",
            ):
                with st.spinner("正在解析调研表..."):
                    try:
                        survey_data = parse_survey_excel_from_bytes(
                            survey_file.getvalue(), original_filename=survey_file.name
                        )
                        _apply_survey_to_prefill(survey_data)
                        # 递增 widget 版本号，强制刷新下方所有输入框
                        st.session_state.sim_widget_version += 1
                        n_ch = len(survey_data.get("chillers", []))
                        n_chw = len(survey_data.get("chw_pumps", []))
                        n_cw = len(survey_data.get("cw_pumps", []))
                        n_tw = len(survey_data.get("towers", []))
                        region = survey_data.get("region_hint") or "未知"
                        station = survey_data.get("station_name") or ""
                        msg = (
                            f"识别完成：{n_ch} 组主机、{n_chw} 组冷冻泵、"
                            f"{n_cw} 组冷却泵、{n_tw} 组冷却塔；地区={region}"
                        )
                        if station:
                            msg += f"；站房={station}"
                        st.session_state._pending_success = msg
                    except Exception as e:
                        st.session_state._pending_error = f"解析失败: {e}"
                st.rerun()

    # ── 展示延迟消息（toast，10 秒后自动消失，可手动关闭）──
    if st.session_state.get("_pending_success"):
        st.toast(st.session_state._pending_success, icon="✅", duration="long")
        st.session_state._pending_success = None
    if st.session_state.get("_pending_warnings"):
        for w in st.session_state._pending_warnings:
            st.toast(w, icon="⚠️", duration="long")
        st.session_state._pending_warnings = []
    if st.session_state.get("_pending_error"):
        st.toast(st.session_state._pending_error, icon="❌", duration="long")
        st.session_state._pending_error = None

    # 从调研表识别结果预填（如果有）
    prefill_data = st.session_state.get("survey_extracted_data", {})
    wv = st.session_state.sim_widget_version  # widget 版本号，识别后递增以强制刷新

    # 项目地区：从调研表识别，未识别则默认华东
    region = prefill_data.get("region") or "华东"

    # === 1. 主机信息 ===
    st.markdown("### 1. 主机COP性能曲线")

    chiller_groups = []
    prefill_chillers = prefill_data.get("chillers", [])
    n_groups = st.number_input("主机组数 (不同型号为一组)", min_value=1, max_value=6,
                               value=max(1, len(prefill_chillers)) if prefill_chillers else 1)

    for i in range(n_groups):
        prefill_ch = prefill_chillers[i] if i < len(prefill_chillers) else {}
        with st.expander(f"主机组 {i+1}", expanded=(i == 0)):
            col1, col2, col3 = st.columns(3)
            with col1:
                name = st.text_input(
                    f"名称", value=prefill_ch.get("name", f"主机组{i+1}"),
                    key=f"chi_name_{i}_v{wv}"
                )
                qty = st.number_input(
                    "台数", min_value=1, max_value=10,
                    value=int(prefill_ch.get("qty", 1)), key=f"chi_qty_{i}_v{wv}"
                )
            with col2:
                capacity = st.number_input(
                    "单台制冷量(kW)", min_value=100.0,
                    value=_f(prefill_ch.get("capacity_kw"), 5000.0),
                    key=f"chi_cap_{i}_v{wv}"
                )
                power = st.number_input(
                    "单台额定功率(kW)", min_value=10.0,
                    value=_f(prefill_ch.get("rated_power_kw"), 800.0),
                    key=f"chi_pow_{i}_v{wv}"
                )
            with col3:
                rated_cop = st.number_input(
                    "额定COP", min_value=1.0, max_value=15.0,
                    value=_f(prefill_ch.get("rated_cop"), 6.0),
                    key=f"chi_cop_{i}_v{wv}"
                )
                vf = st.checkbox(
                    "变频", value=bool(prefill_ch.get("variable_freq", False)),
                    key=f"chi_vf_{i}_v{wv}"
                )

            # COP曲线 - 仅保留表格输入方式，实时绘制曲线
            st.caption("填写负载率(%)和对应COP值，下方实时绘制曲线")
            default_data = {"负载率(%)": [100, 90, 80, 70, 60, 50, 40, 30],
                            "COP": [6.0, 6.2, 6.3, 6.3, 6.0, 5.6, 4.8, 3.6]}
            df_input = pd.DataFrame(default_data)
            edited_df = st.data_editor(
                df_input, num_rows="dynamic", key=f"cop_table_{i}_v{wv}"
            )
            cop_curve = None
            if not edited_df.empty:
                cop_curve = parse_cop_curve_from_table(
                    edited_df["负载率(%)"].tolist(),
                    edited_df["COP"].tolist()
                )

            # 实时绘制 COP 性能曲线
            _render_cop_curve_realtime(cop_curve, rated_cop, i, wv)

            chiller_groups.append({
                "name": name, "qty": qty, "capacity_kw": capacity,
                "rated_power_kw": power, "rated_cop": rated_cop,
                "variable_freq": vf, "cop_curve": cop_curve,
            })

    # === 2. 辅机参数 ===
    st.markdown("### 2. 辅机参数")

    # 添加自定义CSS样式 - 限制输入框最大宽度
    st.markdown("""
    <style>
    /* 限制所有 number_input 和 text_input 的最大宽度 */
    .stNumberInput, .stTextInput {
        max-width: 750px !important;
    }

    /* 确保输入框内的input元素也遵守最大宽度 */
    .stNumberInput input, .stTextInput input {
        max-width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)

    prefill_chw = prefill_data.get("chw_pumps", [{}])[0] if prefill_data.get("chw_pumps") else {}
    prefill_cw = prefill_data.get("cw_pumps", [{}])[0] if prefill_data.get("cw_pumps") else {}
    prefill_tw = prefill_data.get("towers", [{}])[0] if prefill_data.get("towers") else {}

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**冷冻泵**")
        chw_qty = st.number_input("台数", 1, 20, int(prefill_chw.get("qty", 4)), key=f"chw_qty_v{wv}")
        chw_power = st.number_input("单台功率(kW)", 1.0, 500.0, _f(prefill_chw.get("power_kw"), 132.0), key=f"chw_pow_v{wv}")
        chw_flow = st.number_input("单台流量(m³/h)", 10.0, 5000.0, _f(prefill_chw.get("flow_m3h"), 920.0), key=f"chw_flow_v{wv}")
        chw_vf = st.checkbox("变频", value=bool(prefill_chw.get("variable_freq", True)), key=f"chw_vf_v{wv}")

    with col_b:
        st.markdown("**冷却泵**")
        cw_qty = st.number_input("台数", 1, 20, int(prefill_cw.get("qty", 4)), key=f"cw_qty_v{wv}")
        cw_power = st.number_input("单台功率(kW)", 1.0, 500.0, _f(prefill_cw.get("power_kw"), 132.0), key=f"cw_pow_v{wv}")
        cw_flow = st.number_input("单台流量(m³/h)", 10.0, 5000.0, _f(prefill_cw.get("flow_m3h"), 1300.0), key=f"cw_flow_v{wv}")
        cw_vf = st.checkbox("变频", value=bool(prefill_cw.get("variable_freq", False)), key=f"cw_vf_v{wv}")

    st.markdown("**冷却塔**")
    tower_qty = st.number_input("台数", 1, 20, int(prefill_tw.get("qty", 4)), key=f"tower_qty_v{wv}")
    tower_fan_kw = st.number_input("单台风机功率(kW)", 1.0, 100.0, _f(prefill_tw.get("fan_power_kw"), 22.0), key=f"tower_fan_v{wv}")
    tower_fans = st.number_input("每台风机数", 1, 4, int(prefill_tw.get("fans_per_tower", 2)), key=f"tower_fans_v{wv}")
    tower_vf = st.checkbox("变频", value=bool(prefill_tw.get("variable_freq", True)), key=f"tower_vf_v{wv}")

    # === 3. 运行参数 ===
    st.markdown("### 3. 月度运行参数")

    # 尝试从已有数据自动填入
    ac_data = st.session_state.get("ac_extracted_data")
    prefill_monthly = prefill_data.get("monthly_chiller_count")
    default_chiller_count = prefill_monthly if prefill_monthly and len(prefill_monthly) == 12 else [1]*12
    default_load = 0.70

    if ac_data and "monthly_data" in ac_data:
        st.info("已从调研表数据自动填入月度参数，可修改")

    # ── AI 智能推荐月度运行参数 ──
    _init_aim_state()

    # 从第2节取设备总数，强制同步到 AI 模块（以实际配置为准）
    total_available = sum(g["qty"] for g in chiller_groups)
    st.session_state.aim_total_chiller_count = total_available

    with st.expander("🤖 AI智能推荐月度运行参数", expanded=False):

        # 首次展开时自动初始化默认值（无需上传调研表）
        if not st.session_state.get("aim_stage1_done") and not st.session_state.get("aim_analysis"):
            default_analysis = {
                "project_type": "手动配置", "project_type_reason": "用户手动设置",
                "region": "未知", "schedule_label": "单班制办公",
                "schedule_reason": "手动选择", "total_chiller_count": 3,
                "can_identify": False, "summary": "用户手动配置项目参数。",
            }
            st.session_state.aim_analysis = default_analysis
            # 地区优先从调研表识别结果继承，未识别则用 "未知"
            if not st.session_state.get("aim_user_region"):
                st.session_state.aim_user_region = prefill_data.get("region") or "未知"
            st.session_state.aim_total_chiller_count = 3
            _aim_apply_preset("单班制办公")
            st.session_state.aim_stage1_done = True

        aim_analysis = st.session_state.get("aim_analysis", {})

        # ═══════════════════════════════════════════════
        #  一、上传调研表
        # ═══════════════════════════════════════════════
        st.markdown("**一、上传调研表**")
        st.caption("上传后 AI 自动分析并填入下方设置；不上传也可直接手动配置。")

        aim_uploaded = st.file_uploader("上传调研表（Excel）", type=["xlsx", "xls"],
                                        key="aim_upload_sim", label_visibility="collapsed")

        if aim_uploaded:
            if st.session_state.get("_aim_last_file") != aim_uploaded.name:
                st.session_state._aim_last_file = aim_uploaded.name

            if st.button("🔍 分析当前表格数据", key="aim_stage1_btn_sim", use_container_width=True):
                with st.spinner("AI 正在分析项目特征..."):
                    try:
                        import openpyxl, io as io_mod
                        wb = openpyxl.load_workbook(io_mod.BytesIO(aim_uploaded.getvalue()), data_only=True)
                        parts = []
                        for sn in wb.sheetnames:
                            ws = wb[sn]
                            for row in ws.iter_rows(min_row=1, max_row=ws.max_row,
                                                    max_col=min(ws.max_column, 20), values_only=True):
                                rt = " | ".join(str(c).strip() if c is not None else "" for c in row)
                                if rt.replace(" | ", "").strip():
                                    parts.append(rt)
                        wb.close()
                        survey_text = "\n".join(parts)
                    except Exception as e:
                        st.error(f"读取失败: {e}")
                        survey_text = None

                    if survey_text:
                        try:
                            result = ai_stage1_from_text(survey_text)
                        except Exception as e:
                            st.error(f"AI 调用失败: {e}")
                            result = None
                        if result:
                            analysis = result.get("analysis", {})
                            st.session_state.aim_analysis = analysis
                            # 地区不再暴露给用户选择，沿用调研表识别结果
                            if not st.session_state.get("aim_user_region") or st.session_state.aim_user_region == "未知":
                                st.session_state.aim_user_region = analysis.get("region", "未知") or prefill_data.get("region") or "未知"
                            st.session_state.aim_total_chiller_count = analysis.get("total_chiller_count", 3)
                            label = analysis.get("schedule_label", "单班制办公")
                            if label not in preset_manager.get_preset_names():
                                label = "单班制办公"
                            _aim_apply_preset(label)
                            st.session_state.aim_stage1_done = True
                            st.session_state.aim_stage2_done = False
                            st.success(f"✅ 分析完成：{analysis.get('project_type', '?')} | "
                                       f"地区 {st.session_state.aim_user_region} | "
                                       f"推荐 {analysis.get('schedule_label', '?')}")
                            st.rerun()
                        else:
                            st.error("AI 解析失败")

        st.divider()

        # 项目地区：从调研表识别继承，不再暴露选择给用户
        ur = st.session_state.get("aim_user_region") or prefill_data.get("region") or "未知"
        st.caption(f"📍 项目地区：**{ur}**（从调研表自动识别，如需修改请重新上传调研表）")

        st.divider()

        # ═══════════════════════════════════════════════
        #  二、运行班制设置
        # ═══════════════════════════════════════════════
        st.markdown("**二、运行班制设置**")
        preset_manager.ensure_defaults()

        all_presets = preset_manager.get_all_presets()
        preset_names = list(all_presets.keys())
        MAX_PRESETS = 20

        cl = st.session_state.get("aim_schedule_label", "单班制办公")
        if cl not in preset_names:
            cl = preset_names[0] if preset_names else "单班制办公"

        # 下拉框 + 新增 + 删除
        sc1, sc2, sc3 = st.columns([5, 1, 1], gap="small")
        with sc1:
            nl = st.selectbox("选择运行班制", preset_names, index=preset_names.index(cl),
                              key="aim_sched_sim", label_visibility="collapsed")
        with sc2:
            if st.button("新增", key="aim_add_preset", use_container_width=True):
                if len(preset_names) >= MAX_PRESETS:
                    st.warning(f"预设数量已达上限（{MAX_PRESETS}个），请先删除不需要的预设。")
                else:
                    st.session_state._aim_popup_mode = "new"
                    st.rerun()
        with sc3:
            if st.button("删除", key="aim_del_preset", use_container_width=True):
                if preset_manager.delete_preset(nl):
                    preset_manager.ensure_defaults()
                    names_after = preset_manager.get_preset_names()
                    new_sel = names_after[0] if names_after else "单班制办公"
                    _aim_apply_preset(new_sel)
                    st.session_state._aim_prev_label = new_sel
                    st.success(f"已删除「{nl}」")
                    st.rerun()

        # 班制切换
        if nl != st.session_state.get("_aim_prev_label", ""):
            _aim_apply_preset(nl)
            st.session_state._aim_prev_label = nl
            st.session_state.aim_stage2_done = False
            st.rerun()

        # 当前预设描述（只读）
        cur_preset = all_presets.get(nl, {})
        st.caption(cur_preset.get("desc", "(无描述)"))

        with st.expander("编辑逐时负载曲线", expanded=False):
            _aim_curve_editor("工作日", "aim_workday_curve")
            _aim_curve_editor("休息日", "aim_offday_curve")

        # 保存按钮 → 弹出命名弹窗
        if st.button("保存当前曲线和描述", key="aim_save_full", use_container_width=True):
            st.session_state._aim_popup_mode = "save"
            st.session_state._aim_popup_name = nl
            st.session_state._aim_popup_desc = cur_preset.get("desc", "")
            st.rerun()

        # ═══════════════════════════════════════════════
        #  弹窗渲染
        # ═══════════════════════════════════════════════
        popup_mode = st.session_state.get("_aim_popup_mode")
        if popup_mode == "save":
            _aim_save_dialog(
                st.session_state.get("_aim_popup_name", ""),
                st.session_state.get("_aim_popup_desc", ""),
            )
        elif popup_mode == "new":
            _aim_new_dialog()

        st.divider()

        # ═══════════════════════════════════════════════
        #  三、工作日历设置
        # ═══════════════════════════════════════════════
        st.markdown("**三、工作日历设置**")
        st.caption("设置工作/休息循环 + 节假日规则，决定每日选用工作日曲线还是休息日曲线。")
        cal_text = st.text_input(
            "运行日历规则",
            placeholder="默认五天两休，例：上六休一，考虑所有节假日（法定），端午上班",
            key="aim_cal_sim", label_visibility="collapsed",
        )
        if cal_text.strip() and cal_text != st.session_state.get("_aim_cal_done", ""):
            r = parse_calendar_smart(cal_text.strip())
            if r and r.get("day_type"):
                st.session_state.aim_day_type = r["day_type"]
                st.session_state._aim_cal_done = cal_text
                wd = r["day_type"].count(0)
                rd = r["day_type"].count(1)
                parts = []
                if r.get("pattern"): parts.append(f"循环：{r['pattern']}")
                if r.get("holidays"): parts.append(f"节假日：{'、'.join(r['holidays'])}")
                st.success(f"✅ 日历已生成：{wd} 工作日 + {rd} 休息日" +
                           ("  |  " + " · ".join(parts) if parts else ""))

        st.divider()

        # ═══════════════════════════════════════════════
        #  四、生成推荐参数
        # ═══════════════════════════════════════════════
        st.markdown("**四、生成推荐参数**")
        if st.button("📊 AI智能推荐月度运行参数并填入", type="primary", key="aim_stage2_btn_sim", use_container_width=True):
            tc = st.session_state.get("aim_total_chiller_count", 3)
            with st.spinner("AI 正在推荐月度参数..."):
                try:
                    r2 = ai_stage2_recommend(
                        aim_analysis, nl,
                        st.session_state.aim_workday_curve,
                        st.session_state.aim_offday_curve,
                        tc, user_region=ur,
                    )
                except Exception as e:
                    st.error(f"AI 调用失败: {e}")
                    r2 = None
                if r2:
                    st.session_state.aim_monthly_chiller_count = r2.get("monthly_chiller_count", [1]*12)
                    st.session_state.aim_monthly_load_factors = r2.get("monthly_load_factors", [0.5]*12)
                    st.session_state.aim_summary = r2.get("recommendation_summary", "")
                    st.session_state.aim_stage2_done = True
                    st.session_state._aim_fill_trigger = True
                    st.rerun()
                else:
                    st.error("AI 解析失败")

        if st.session_state.get("aim_stage2_done"):
            st.info(f"💡 {st.session_state.get('aim_summary', '')}")

    # ── 设备运行规律（可选）：用户用自然语言描述后 AI 整理为 12 个月表 ──
    _render_operation_rules_section(chiller_groups, wv)

    # 如果触发填入，直接写入 widget 的 session_state 键（Streamlit 用 key 缓存值，
    # 单纯改 value 参数不会生效，必须直接操作 session_state）
    mc_keys = [f"mc_{i}_v{wv}" for i in range(12)]
    mlf_keys = [f"mlf_{i}_v{wv}" for i in range(12)]
    if st.session_state.get("_aim_fill_trigger"):
        aim_mc = st.session_state.get("aim_monthly_chiller_count", [1]*12)
        aim_lf = st.session_state.get("aim_monthly_load_factors", [0.5]*12)
        for i in range(12):
            # 限制不超过设备总数
            st.session_state[mc_keys[i]] = min(aim_mc[i] if i < len(aim_mc) else 1, total_available)
            st.session_state[mlf_keys[i]] = float(aim_lf[i] if i < len(aim_lf) else 0.5)
        if st.session_state.get("aim_day_type"):
            st.session_state.aim_final_day_type = st.session_state.aim_day_type
        st.session_state._aim_fill_trigger = False

    load_ratio = st.slider("平均负载率", 0.3, 1.0, default_load, 0.05)

    st.caption(f"每月开机台数（共 {total_available} 台可用）")
    monthly_counts = []
    cols = st.columns(12)
    for i, col in enumerate(cols):
        with col:
            v = col.number_input(f"{i+1}月", min_value=1, max_value=max(1, total_available),
                                 value=1, key=mc_keys[i])
            monthly_counts.append(v)

    st.caption("月度负载系数")
    monthly_load_factors = []
    cols_lf = st.columns(12)
    for i, col in enumerate(cols_lf):
        with col:
            v = col.number_input(f"{i+1}月", min_value=0.0, max_value=1.0, value=0.5,
                                 step=0.01, format="%.2f", key=mlf_keys[i])
            monthly_load_factors.append(v)

    # === 5. 开始仿真 ===
    st.markdown("---")
    if st.button("开始仿真", type="primary", use_container_width=True):
        user_inputs = {
            "chiller_groups": chiller_groups,
            "chw_pumps": [{"name": "冷冻泵", "qty": chw_qty, "power_kw": chw_power,
                           "flow_m3h": chw_flow, "variable_freq": chw_vf}],
            "cw_pumps": [{"name": "冷却泵", "qty": cw_qty, "power_kw": cw_power,
                          "flow_m3h": cw_flow, "variable_freq": cw_vf}],
            "towers": [{"name": "冷却塔", "qty": tower_qty, "fan_power_kw": tower_fan_kw,
                        "fans_per_tower": tower_fans, "variable_freq": tower_vf}],
            "monthly_chiller_count": monthly_counts,
            "monthly_load_factors": monthly_load_factors,
            "base_load_ratio": load_ratio,
            # 来自 AI 推荐模块的曲线和日历（若未使用 AI 则回退硬编码默认值）
            "workday_hourly_curve": st.session_state.get("aim_workday_curve") or list(HOURLY_LOAD_FACTOR),
            "offday_hourly_curve": st.session_state.get("aim_offday_curve") or list(HOURLY_LOAD_FACTOR),
            "day_type": st.session_state.get("aim_day_type") or [0] * 365,
        }

        config = build_plant_config_from_extracted_data(ac_data, user_inputs)
        monthly_ambient = get_monthly_dry_bulb(region)

        with st.spinner("正在进行全年8760小时仿真..."):
            simulator = PlantSimulator(config, monthly_ambient)
            df_base = simulator.simulate_baseline()

            # 参考前面节能率计算结果来校准优化力度
            target_saving_pct = _get_target_saving_pct()
            df_opt, chw_target_dt = _calibrated_optimization(
                simulator, df_base, target_saving_pct)
            summary = simulator.generate_summary(df_base, df_opt)
            summary["chw_target_dt"] = chw_target_dt
            summary["reference_saving_pct"] = target_saving_pct

        st.session_state.sim_result = {
            "df_base": df_base,
            "df_opt": df_opt,
            "summary": summary,
            "region": region,
        }
        st.session_state.stage = "simulation_result"
        st.rerun()

    # 返回按钮
    if st.button("← 返回节能率结果", use_container_width=True):
        st.session_state.stage = "result"
        st.rerun()


def render_simulation_result_stage():
    """仿真结果页面"""
    st.subheader("🔬 冷站性能仿真结果")

    sim_result = st.session_state.get("sim_result")
    if not sim_result:
        st.warning("未找到仿真结果，请重新运行")
        if st.button("返回输入"):
            st.session_state.stage = "simulation_input"
            st.rerun()
        return

    df_base = sim_result["df_base"]
    df_opt = sim_result["df_opt"]
    summary = sim_result["summary"]

    # 核心指标
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("基线系统COP", f"{summary['baseline_cop']:.2f}")
    with col2:
        st.metric("优化系统COP", f"{summary['optimized_cop']:.2f}",
                  f"+{(summary['optimized_cop']-summary['baseline_cop'])/summary['baseline_cop']*100:.1f}%")
    with col3:
        st.metric("年节电量", f"{summary['saving_kwh']/1e4:.0f}万kWh")
    with col4:
        st.metric("年节省电费", f"{summary['saving_cost_yuan']/1e4:.1f}万元")

    st.markdown("---")

    # 图表
    tab1, tab2, tab3 = st.tabs(["月度COP对比", "能耗结构对比", "全年COP热力图"])

    with tab1:
        fig1 = generate_monthly_cop_chart(df_base, df_opt)
        st.plotly_chart(fig1, use_container_width=True)

    with tab2:
        fig2 = generate_energy_structure_chart(summary)
        st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        fig3 = generate_cop_heatmap(df_opt)
        st.plotly_chart(fig3, use_container_width=True)

    # 月度详表
    st.markdown("### 月度详细数据")
    monthly_table = _build_monthly_table(df_base, df_opt)
    st.dataframe(monthly_table, use_container_width=True)

    st.markdown("---")

    # AI报告生成
    st.markdown("### 🤖 AI优化分析报告")
    if "sim_ai_report" not in st.session_state:
        st.session_state.sim_ai_report = None

    if st.session_state.sim_ai_report:
        st.markdown(st.session_state.sim_ai_report)
        st.download_button(
            "📄 下载AI报告",
            data=st.session_state.sim_ai_report.encode("utf-8"),
            file_name="冷站AI优化分析报告.md",
            mime="text/markdown",
            use_container_width=True,
            key="dl_ai_report",
        )
    else:
        if st.button("🧠 生成AI专业分析报告", type="primary", use_container_width=True):
            with st.spinner("AI正在生成专业报告..."):
                ai_report = ai_generate_simulation_report(summary)
                if ai_report:
                    st.session_state.sim_ai_report = ai_report
                    st.rerun()
                else:
                    # 回退到模板报告
                    st.session_state.sim_ai_report = generate_report_markdown(summary)
                    st.warning("AI报告生成失败，已使用模板报告")
                    st.rerun()

    st.markdown("---")

    # 下载
    st.markdown("### 下载")
    col_d1, col_d2, col_d3 = st.columns(3)

    with col_d1:
        report_md = generate_report_markdown(summary)
        st.download_button(
            "📄 下载报告",
            data=report_md.encode("utf-8"),
            file_name="冷站仿真报告.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_d2:
        excel_buf = _export_excel(df_opt, summary)
        st.download_button(
            "📊 下载8760h仿真Excel",
            data=excel_buf,
            file_name="冷站8760h仿真结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_d3:
        json_data = json.dumps(summary, ensure_ascii=False, indent=2)
        st.download_button(
            "📋 下载汇总JSON",
            data=json_data.encode("utf-8"),
            file_name="仿真汇总.json",
            mime="application/json",
            use_container_width=True,
        )

    st.markdown("---")

    # 导航
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("← 修改参数重新仿真", use_container_width=True):
            st.session_state.stage = "simulation_input"
            st.rerun()
    with col_nav2:
        if st.button("🔄 开始新的测算", type="primary", use_container_width=True):
            from app import reset_flow
            reset_flow()
            st.rerun()


def _build_monthly_table(df_base, df_opt):
    months = range(1, 13)
    rows = []
    for m in months:
        base_m = df_base[df_base["month"] == m]
        opt_m = df_opt[df_opt["month"] == m]
        base_cop = base_m["cooling_load_kw"].sum() / base_m["total_power_kw"].sum() if base_m["total_power_kw"].sum() > 0 else 0
        opt_cop = opt_m["cooling_load_kw"].sum() / opt_m["total_power_kw"].sum() if opt_m["total_power_kw"].sum() > 0 else 0
        rows.append({
            "月份": f"{m}月",
            "基线COP": round(base_cop, 2),
            "优化COP": round(opt_cop, 2),
            "COP提升": f"+{(opt_cop-base_cop)/base_cop*100:.1f}%" if base_cop > 0 else "-",
            "基线耗电(万kWh)": round(base_m["total_power_kw"].sum() / 1e4, 1),
            "优化耗电(万kWh)": round(opt_m["total_power_kw"].sum() / 1e4, 1),
            "节电(万kWh)": round((base_m["total_power_kw"].sum() - opt_m["total_power_kw"].sum()) / 1e4, 1),
        })
    return pd.DataFrame(rows)


def _export_excel(df_opt: pd.DataFrame, summary: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_opt.to_excel(writer, sheet_name="8760h逐时数据", index=False)
        summary_df = pd.DataFrame([summary])
        summary_df.to_excel(writer, sheet_name="年度汇总", index=False)
    return buf.getvalue()


def _get_target_saving_pct() -> float:
    """从前面节能率计算结果获取目标节能率，仿真取略低值（实际工程保守估计）"""
    ac_result = st.session_state.get("ac_result")
    if not ac_result:
        return None

    # 支持范围和单值两种格式
    if "energy_saving_rate_range" in ac_result:
        rate_range = ac_result["energy_saving_rate_range"]
        low = rate_range.get("lower_bound", 0)
        high = rate_range.get("upper_bound", 0)
        # 取下限偏低值，仿真结果应低于节能率理论计算
        return low * 0.85
    elif "energy_saving_rate" in ac_result:
        return float(ac_result["energy_saving_rate"]) * 0.85
    return None


def _calibrated_optimization(simulator, df_base, target_saving_pct):
    """
    校准优化力度使仿真节能率与节能率计算结果一致。

    策略：通过调整温差控制目标来控制节能力度。
    温差目标越大 → 流量越小 → 泵功耗越低 → 节能越多。
    温差目标范围：3-7°C（工程合理区间）
    """
    if target_saving_pct is None:
        # 没有参考值，使用默认5°C目标温差
        df_opt = simulator.simulate_optimized(chw_target_dt=5.0)
        return df_opt, 5.0

    base_power = df_base["total_power_kw"].sum()
    target_saving_ratio = target_saving_pct / 100.0

    # 二分法搜索合适的温差目标使节能率接近目标
    dt_low, dt_high = 3.5, 7.0
    best_dt = 5.0
    best_df = None
    best_diff = float("inf")

    for _ in range(8):
        dt_mid = (dt_low + dt_high) / 2.0
        df_opt = simulator.simulate_optimized(chw_target_dt=dt_mid)
        opt_power = df_opt["total_power_kw"].sum()
        actual_saving = (base_power - opt_power) / base_power

        diff = abs(actual_saving - target_saving_ratio)
        if diff < best_diff:
            best_diff = diff
            best_dt = dt_mid
            best_df = df_opt

        if actual_saving < target_saving_ratio:
            dt_low = dt_mid
        else:
            dt_high = dt_mid

        # 足够接近就退出 (误差<1个百分点)
        if diff < 0.01:
            break

    # 如果校准后偏差仍大于3个百分点，限制在合理范围内输出
    if best_diff > 0.03:
        best_dt = max(4.0, min(6.0, best_dt))
        best_df = simulator.simulate_optimized(chw_target_dt=best_dt)

    return best_df, round(best_dt, 1)
