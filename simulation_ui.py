"""冷站仿真 Streamlit UI - 输入页面和结果页面"""
import io
import json
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

from simulation.simulator import PlantSimulator, PlantConfig, ChillerGroup, PumpGroup, TowerGroup, HOURLY_LOAD_FACTOR
from simulation.chart_generator import generate_monthly_cop_chart, generate_energy_structure_chart, generate_cop_heatmap
from simulation.report_generator import generate_report_markdown
from simulation.weather import get_regions, get_monthly_dry_bulb
from simulation.input_parser import parse_cop_curve_from_text, parse_cop_curve_from_table, build_plant_config_from_extracted_data
from simulation.ai_service import ai_generate_simulation_report
from simulation.ai智能识别设备铭牌 import extract_plant_topology, extract_cop_curve, extract_multi_chiller_topology
from simulation.ai智能推荐月度参数模块.recommend import ai_stage1_from_text, ai_stage2_recommend
from simulation.ai智能推荐月度参数模块.presets import PRESET_SCHEDULES, SCHEDULE_LABELS
from simulation.ai智能推荐月度参数模块.calendar_parser import parse_calendar_smart, DEFAULT_DAY_TYPE
from simulation.ai智能推荐月度参数模块 import preset_manager


def _apply_single_chiller_result(group_index: int, chiller_data: dict):
    """将单组主机 AI 识别结果填入对应表单字段。

    不修改整个 ai_extracted_topology，只通过直接操作 st.session_state
    来覆盖当前组的 widget 值。之所以不走 ai_extracted_topology 是因为
    顶层 AI 的结果可能包含多组主机，而组内 AI 只负责当前这一组。
    """
    # 递增版本号以强制所有 widget 重新渲染
    st.session_state.sim_widget_version += 1
    wv = st.session_state.sim_widget_version
    _write_chiller_to_session_state(group_index, chiller_data, wv)


def _write_chiller_to_session_state(group_index: int, chiller_data: dict, wv: int):
    """将单组主机参数写入 session_state（不递增版本号）。

    用于批量填入场景，调用方负责统一管理版本号。
    """
    i = group_index
    st.session_state[f"chi_name_{i}_v{wv}"] = chiller_data.get(
        "name", f"主机组{i+1}"
    )
    st.session_state[f"chi_qty_{i}_v{wv}"] = int(chiller_data.get("qty") or 1)
    st.session_state[f"chi_cap_{i}_v{wv}"] = float(
        chiller_data.get("capacity_kw") or 5000
    )
    st.session_state[f"chi_pow_{i}_v{wv}"] = float(
        chiller_data.get("rated_power_kw") or 800
    )
    st.session_state[f"chi_cop_{i}_v{wv}"] = float(
        chiller_data.get("rated_cop") or 6.0
    )
    st.session_state[f"chi_vf_{i}_v{wv}"] = bool(
        chiller_data.get("variable_freq", False)
    )


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

    # === 0. AI智能识别设备 ===
    with st.expander("🤖 AI智能识别多设备拓扑", expanded=False):
        st.caption("上传设备清单图片、铭牌照片或粘贴文本，AI自动提取所有参数")
        ai_input_tab1, ai_input_tab2 = st.tabs(["上传图片", "粘贴文本"])

        with ai_input_tab1:
            ai_images = st.file_uploader(
                "上传设备清单/铭牌照片（支持多张）",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key="ai_topo_img"
            )
            if ai_images:
                for img in ai_images:
                    st.image(img, width=300)

        with ai_input_tab2:
            ai_text = st.text_area(
                "粘贴设备信息（调研表内容、设备清单等）",
                placeholder="例如：\n3台变频离心机，单台5274kW，COP 6.12\n4台冷冻泵132kW变频\n4台冷却泵132kW工频\n6台冷却塔22kW变频",
                height=150,
                key="ai_topo_text"
            )

        if st.button(" AI识别并填入参数", use_container_width=True, type="primary", key="ai_extract_btn"):
            with st.spinner(" AI正在识别设备参数，请稍候..."):
                has_images = ai_images and len(ai_images) > 0
                has_text = bool(ai_text)

                if has_images:
                    # ── 多图批量识别：一次性识别所有铭牌照片 ──
                    image_bytes_list = [img.getvalue() for img in ai_images]
                    media_types = []
                    for img in ai_images:
                        fname = img.name.lower()
                        media_types.append(
                            "image/png" if fname.endswith(".png") else "image/jpeg"
                        )

                    result = extract_multi_chiller_topology(
                        images=image_bytes_list,
                        media_types=media_types,
                    )

                    if result and result.get("total_count", 0) > 0:
                        # 提取成功识别和部分识别的 chillers
                        chillers = result.get("chillers", [])
                        valid_chillers = [
                            ch for ch in chillers
                            if ch.get("status") in ("success", "partial")
                        ]

                        if valid_chillers:
                            # 构建 topology 结果（仅包含成功/部分识别的组）
                            topology = {
                                "chillers": [ch["data"] for ch in valid_chillers
                                             if ch.get("data") is not None],
                            }
                            st.session_state.ai_extracted_topology = topology
                            # 先递增版本号，统一使用一个 wv 给所有组
                            st.session_state.sim_widget_version += 1
                            wv = st.session_state.sim_widget_version

                            # 逐组填入参数（直接写 session_state，使用统一的 wv）
                            filled_index = 0
                            for ch in chillers:
                                if ch.get("status") == "success":
                                    if ch.get("data"):
                                        _write_chiller_to_session_state(filled_index, ch["data"], wv)
                                    filled_index += 1
                                elif ch.get("status") == "partial":
                                    if ch.get("data"):
                                        _write_chiller_to_session_state(filled_index, ch["data"], wv)
                                    if ch.get("warning"):
                                        st.session_state._pending_warnings.append(ch["warning"])
                                    filled_index += 1
                                elif ch.get("status") == "failed":
                                    st.session_state._pending_warnings.append(ch["warning"])

                            n_success = result.get("success_count", 0)
                            n_partial = result.get("partial_count", 0)
                            n_failed = result.get("failed_count", 0)

                            # 构建成功消息
                            msg_parts = []
                            if n_success > 0:
                                msg_parts.append(f"{n_success} 组成功识别")
                            if n_partial > 0:
                                msg_parts.append(f"{n_partial} 组部分识别（请核查）")
                            if n_failed > 0:
                                msg_parts.append(f"{n_failed} 张图片识别失败")

                            st.session_state._pending_success = (
                                f"识别完成！共 {n_success + n_partial} 组主机已填入表单"
                                f"（{', '.join(msg_parts)}），请核对各主机组参数"
                            )
                        else:
                            # 全部失败
                            for ch in chillers:
                                if ch.get("warning"):
                                    st.session_state._pending_warnings.append(ch["warning"])
                            st.session_state._pending_error = (
                                "所有图片均识别失败，请检查图片质量或尝试粘贴文本方式"
                            )
                    else:
                        st.session_state._pending_error = "识别失败，请检查图片质量或尝试粘贴文本方式"

                elif has_text:
                    # ── 纯文本方式（保持原有逻辑）──
                    result = extract_plant_topology(
                        content=ai_text,
                        content_type="text",
                    )

                    if result:
                        st.session_state.ai_extracted_topology = result
                        st.session_state.sim_widget_version += 1
                        n_ch = len(result.get("chillers", []))
                        n_chw = len(result.get("chw_pumps", []))
                        n_cw = len(result.get("cw_pumps", []))
                        n_tw = len(result.get("towers", []))
                        st.session_state._pending_success = (
                            f"识别成功！检测到 {n_ch} 组主机、{n_chw} 组冷冻泵、"
                            f"{n_cw} 组冷却泵、{n_tw} 组冷却塔，参数已自动填入下方表单，请核对"
                        )
                    else:
                        st.session_state._pending_error = "识别失败，请检查文本内容或尝试上传图片方式"

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

    # 从AI识别结果预填（如果有）
    ai_topo = st.session_state.get("ai_extracted_topology", {})
    wv = st.session_state.sim_widget_version  # widget 版本号，AI 识别后递增以强制刷新

    # === 1. 地区选择 ===
    st.markdown("### 1. 冷站所在地区")
    regions = get_regions()
    ai_region = ai_topo.get("region", "华东")
    default_region_idx = regions.index(ai_region) if ai_region in regions else (regions.index("华东") if "华东" in regions else 0)
    region = st.selectbox("选择地区", regions, index=default_region_idx)

    # === 2. 主机信息 ===
    st.markdown("### 2. 主机COP性能曲线")

    cop_input_method = st.radio(
        "COP曲线输入方式",
        ["上传图片(AI识别)", "手动填写表格", "文本描述"],
        horizontal=True,
    )

    chiller_groups = []
    ai_chillers = ai_topo.get("chillers", [])
    n_groups = st.number_input("主机组数 (不同型号为一组)", min_value=1, max_value=6,
                               value=max(1, len(ai_chillers)) if ai_chillers else 1)

    for i in range(n_groups):
        ai_ch = ai_chillers[i] if i < len(ai_chillers) else {}
        with st.expander(f"主机组 {i+1}", expanded=(i == 0)):
            # ── 组内 AI 识图：只看当前主机的铭牌 ──
            ai_tab1, ai_tab2 = st.tabs(["上传铭牌", "粘贴文本"])
            with ai_tab1:
                chiller_img = st.file_uploader(
                    f"上传主机组{i+1}的铭牌照片",
                    type=["jpg", "jpeg", "png"],
                    key=f"chi_ai_img_{i}_v{wv}"
                )
                if chiller_img:
                    st.image(chiller_img, width=280)
            with ai_tab2:
                chiller_text = st.text_area(
                    f"粘贴主机组{i+1}参数",
                    placeholder="例如：约克YK离心机，制冷量3868kW，输入功率632kW，COP6.12，变频",
                    height=80,
                    key=f"chi_ai_text_{i}_v{wv}"
                )

            if st.button(
                f" AI识别并填入本组", 
                use_container_width=True,
                type="primary",
                key=f"chi_ai_btn_{i}_v{wv}"
            ):
                with st.spinner(" 正在识别本组设备参数..."):
                    chi_img_data = chiller_img.getvalue() if chiller_img else None
                    chi_media = (
                        "image/png"
                        if chiller_img and chiller_img.name.lower().endswith(".png")
                        else "image/jpeg"
                    ) if chiller_img else "image/jpeg"
                    chi_text = chiller_text if chiller_text else ""
                    if chiller_img and not chi_text:
                        chi_text = f"请识别这张主机组{i+1}的铭牌照片中的设备参数"

                    # 只提取 chillers[0]，其余字段（辅机/地区）忽略
                    raw = extract_plant_topology(
                        content=chi_text,
                        content_type="image" if chi_img_data else "text",
                        image_data=chi_img_data,
                        media_type=chi_media,
                    )

                    if raw and raw.get("chillers"):
                        # 只取第一组主机的参数填入当前组
                        matched = raw["chillers"][0]
                        _apply_single_chiller_result(i, matched)
                        # 如果 AI 碰巧也识别了辅机，顺便预填辅机
                        if not ai_topo.get("chw_pumps") and raw.get("chw_pumps"):
                            st.session_state.ai_extracted_topology = {
                                **st.session_state.get("ai_extracted_topology", {}),
                                "chw_pumps": raw["chw_pumps"],
                                "cw_pumps": raw.get("cw_pumps"),
                                "towers": raw.get("towers"),
                                "region": raw.get("region"),
                            }
                        st.success(f" 主机组{i+1}参数已填入，请核对")
                        st.rerun()
                    else:
                        st.error(" 识别失败，请检查图片或手动填写")

            col1, col2, col3 = st.columns(3)
            with col1:
                name = st.text_input(f"名称", value=ai_ch.get("name", f"主机组{i+1}"), key=f"chi_name_{i}_v{wv}")
                qty = st.number_input("台数", min_value=1, max_value=10,
                                      value=ai_ch.get("qty", 1), key=f"chi_qty_{i}_v{wv}")
            with col2:
                capacity = st.number_input("单台制冷量(kW)", min_value=100.0,
                                           value=float(ai_ch.get("capacity_kw", 5000)), key=f"chi_cap_{i}_v{wv}")
                power = st.number_input("单台额定功率(kW)", min_value=10.0,
                                        value=float(ai_ch.get("rated_power_kw", 800)), key=f"chi_pow_{i}_v{wv}")
            with col3:
                rated_cop = st.number_input("额定COP", min_value=1.0, max_value=15.0,
                                            value=float(ai_ch.get("rated_cop", 6.0)), key=f"chi_cop_{i}_v{wv}")
                vf = st.checkbox("变频", value=ai_ch.get("variable_freq", False), key=f"chi_vf_{i}_v{wv}")

            # COP曲线
            cop_curve = None
            if cop_input_method == "上传图片(AI识别)":
                uploaded_img = st.file_uploader(
                    "上传COP性能曲线图片", type=["jpg", "jpeg", "png"],
                    key=f"cop_img_{i}_v{wv}"
                )
                if uploaded_img:
                    st.image(uploaded_img, width=500)
                    if st.button("AI识别曲线", key=f"parse_img_{i}_v{wv}"):
                        with st.spinner("正在识别..."):
                            cop_curve = _ai_parse_cop_image(uploaded_img)
                            if cop_curve:
                                st.success(f"识别到 {len(cop_curve)} 个数据点")
                                st.json(cop_curve)
                            else:
                                st.warning("识别失败，请手动填写")

            elif cop_input_method == "手动填写表格":
                st.caption("填写负载率(%)和对应COP值")
                default_data = {"负载率(%)": [100, 90, 80, 70, 60, 50, 40, 30],
                                "COP": [6.0, 6.2, 6.3, 6.3, 6.0, 5.6, 4.8, 3.6]}
                df_input = pd.DataFrame(default_data)
                edited_df = st.data_editor(df_input, num_rows="dynamic", key=f"cop_table_{i}_v{wv}")
                if not edited_df.empty:
                    cop_curve = parse_cop_curve_from_table(
                        edited_df["负载率(%)"].tolist(),
                        edited_df["COP"].tolist()
                    )

            else:  # 文本描述
                text = st.text_area(
                    "输入COP数据 (每行: 负载率 COP)",
                    value="100% 6.0\n80% 6.3\n60% 6.0\n40% 4.8",
                    key=f"cop_text_{i}_v{wv}"
                )
                if text.strip():
                    cop_curve = parse_cop_curve_from_text(text)

            chiller_groups.append({
                "name": name, "qty": qty, "capacity_kw": capacity,
                "rated_power_kw": power, "rated_cop": rated_cop,
                "variable_freq": vf, "cop_curve": cop_curve,
            })

    # === 3. 辅机参数 ===
    st.markdown("### 3. 辅机参数")

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

    ai_chw = ai_topo.get("chw_pumps", [{}])[0] if ai_topo.get("chw_pumps") else {}
    ai_cw = ai_topo.get("cw_pumps", [{}])[0] if ai_topo.get("cw_pumps") else {}
    ai_tw = ai_topo.get("towers", [{}])[0] if ai_topo.get("towers") else {}

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**冷冻泵**")
        chw_qty = st.number_input("台数", 1, 20, ai_chw.get("qty", 4), key=f"chw_qty_v{wv}")
        chw_power = st.number_input("单台功率(kW)", 1.0, 500.0, float(ai_chw.get("power_kw", 132)), key=f"chw_pow_v{wv}")
        chw_flow = st.number_input("单台流量(m³/h)", 10.0, 5000.0, float(ai_chw.get("flow_m3h", 920)), key=f"chw_flow_v{wv}")
        chw_vf = st.checkbox("变频", value=ai_chw.get("variable_freq", True), key=f"chw_vf_v{wv}")

    with col_b:
        st.markdown("**冷却泵**")
        cw_qty = st.number_input("台数", 1, 20, ai_cw.get("qty", 4), key=f"cw_qty_v{wv}")
        cw_power = st.number_input("单台功率(kW)", 1.0, 500.0, float(ai_cw.get("power_kw", 132)), key=f"cw_pow_v{wv}")
        cw_flow = st.number_input("单台流量(m³/h)", 10.0, 5000.0, float(ai_cw.get("flow_m3h", 1300)), key=f"cw_flow_v{wv}")
        cw_vf = st.checkbox("变频", value=ai_cw.get("variable_freq", False), key=f"cw_vf_v{wv}")

    st.markdown("**冷却塔**")
    tower_qty = st.number_input("台数", 1, 20, ai_tw.get("qty", 4), key=f"tower_qty_v{wv}")
    tower_fan_kw = st.number_input("单台风机功率(kW)", 1.0, 100.0, float(ai_tw.get("fan_power_kw", 22)), key=f"tower_fan_v{wv}")
    tower_fans = st.number_input("每台风机数", 1, 4, ai_tw.get("fans_per_tower", 2), key=f"tower_fans_v{wv}")
    tower_vf = st.checkbox("变频", value=ai_tw.get("variable_freq", True), key=f"tower_vf_v{wv}")

    # === 4. 运行参数 ===
    st.markdown("### 4. 月度运行参数")

    # 尝试从已有数据自动填入
    ac_data = st.session_state.get("ac_extracted_data")
    ai_monthly = ai_topo.get("monthly_chiller_count")
    default_chiller_count = ai_monthly if ai_monthly and len(ai_monthly) == 12 else [1]*12
    default_load = ai_topo.get("base_load_ratio", 0.70)

    if ac_data and "monthly_data" in ac_data:
        st.info("已从调研表数据自动填入月度参数，可修改")
    elif ai_monthly:
        st.info("已从AI识别结果填入月度参数，可修改")

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
            st.session_state.aim_user_region = "未知"
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
                            st.session_state.aim_user_region = analysis.get("region", "未知")
                            st.session_state.aim_total_chiller_count = analysis.get("total_chiller_count", 3)
                            label = analysis.get("schedule_label", "单班制办公")
                            if label not in preset_manager.get_preset_names():
                                label = "单班制办公"
                            _aim_apply_preset(label)
                            st.session_state.aim_stage1_done = True
                            st.session_state.aim_stage2_done = False
                            st.success(f"✅ 分析完成：{analysis.get('project_type', '?')} | "
                                       f"地区 {analysis.get('region', '?')} | "
                                       f"推荐 {analysis.get('schedule_label', '?')}")
                            st.rerun()
                        else:
                            st.error("AI 解析失败")

        st.divider()

        # ═══════════════════════════════════════════════
        #  二、项目地区
        # ═══════════════════════════════════════════════
        st.markdown("**二、项目地区**")
        REGIONS = ["华南", "华东", "华中", "华北", "西南", "西北", "东北", "未知"]
        ar = aim_analysis.get("region", "未知")
        cur_r = st.session_state.get("aim_user_region") or ar
        if cur_r not in REGIONS:
            cur_r = "未知"
        ur = st.selectbox("选择项目所在地区", REGIONS, index=REGIONS.index(cur_r), key="aim_region_sim",
                          help="阶段二将以你选择的地区为准推荐月度参数。")
        st.session_state.aim_user_region = ur

        st.divider()

        # ═══════════════════════════════════════════════
        #  三、运行班制设置
        # ═══════════════════════════════════════════════
        st.markdown("**三、运行班制设置**")
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
        #  四、工作日历设置
        # ═══════════════════════════════════════════════
        st.markdown("**四、工作日历设置**")
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
        #  五、生成推荐参数
        # ═══════════════════════════════════════════════
        st.markdown("**五、生成推荐参数**")
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


def _ai_parse_cop_image(uploaded_file) -> dict:
    """调用AI解析COP曲线图片（委托给 ai_vision 模块）"""
    try:
        fname = uploaded_file.name.lower()
        media_type = "image/png" if fname.endswith(".png") else "image/jpeg"
        return extract_cop_curve(uploaded_file.getvalue(), media_type=media_type)
    except Exception as e:
        st.error(f"AI识别失败: {e}")
        return None


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
