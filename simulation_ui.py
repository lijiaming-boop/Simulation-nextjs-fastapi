"""冷站仿真 Streamlit UI - 输入页面和结果页面"""
import io
import json
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

from simulation.simulator import PlantSimulator, PlantConfig, ChillerGroup, PumpGroup, TowerGroup
from simulation.chart_generator import generate_monthly_cop_chart, generate_energy_structure_chart, generate_cop_heatmap
from simulation.report_generator import generate_report_markdown
from simulation.weather import get_regions, get_monthly_dry_bulb
from simulation.input_parser import parse_cop_curve_from_text, parse_cop_curve_from_table, build_plant_config_from_extracted_data
from simulation.ai_service import ai_extract_plant_topology, ai_generate_simulation_report


def render_simulation_input_stage():
    """仿真输入页面"""
    st.subheader("🔬 冷站性能仿真 — 参数输入")
    st.caption("基于主机COP性能曲线，仿真全年8760小时运行，输出优化控制策略")

    # 初始化仿真状态
    if "sim_chiller_groups" not in st.session_state:
        st.session_state.sim_chiller_groups = [{}]

    # === 0. AI智能识别设备 ===
    with st.expander("🤖 AI智能识别设备拓扑（可选）", expanded=False):
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

        if st.button("🧠 AI识别并填入参数", use_container_width=True, key="ai_extract_btn"):
            with st.spinner("AI正在分析设备信息..."):
                content = ai_text if ai_text else ""
                image_data = None
                media_type = "image/jpeg"

                if ai_images:
                    image_data = ai_images[0].getvalue()
                    fname = ai_images[0].name.lower()
                    media_type = "image/png" if fname.endswith(".png") else "image/jpeg"
                    content += f"\n[已上传{len(ai_images)}张设备图片]"

                result = ai_extract_plant_topology(
                    content=content,
                    content_type="image" if image_data else "text",
                    image_data=image_data,
                    media_type=media_type,
                )

                if result:
                    st.session_state.ai_extracted_topology = result
                    st.success("识别成功，参数已填入下方表单")
                    st.json(result)
                else:
                    st.error("识别失败，请手动填写或检查输入内容")

    # 从AI识别结果预填（如果有）
    ai_topo = st.session_state.get("ai_extracted_topology", {})

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
            col1, col2, col3 = st.columns(3)
            with col1:
                name = st.text_input(f"名称", value=ai_ch.get("name", f"主机组{i+1}"), key=f"chi_name_{i}")
                qty = st.number_input("台数", min_value=1, max_value=10,
                                      value=ai_ch.get("qty", 1), key=f"chi_qty_{i}")
            with col2:
                capacity = st.number_input("单台制冷量(kW)", min_value=100.0,
                                           value=float(ai_ch.get("capacity_kw", 5000)), key=f"chi_cap_{i}")
                power = st.number_input("单台额定功率(kW)", min_value=10.0,
                                        value=float(ai_ch.get("rated_power_kw", 800)), key=f"chi_pow_{i}")
            with col3:
                rated_cop = st.number_input("额定COP", min_value=1.0, max_value=15.0,
                                            value=float(ai_ch.get("rated_cop", 6.0)), key=f"chi_cop_{i}")
                vf = st.checkbox("变频", value=ai_ch.get("variable_freq", False), key=f"chi_vf_{i}")

            # COP曲线
            cop_curve = None
            if cop_input_method == "上传图片(AI识别)":
                uploaded_img = st.file_uploader(
                    "上传COP性能曲线图片", type=["jpg", "jpeg", "png"],
                    key=f"cop_img_{i}"
                )
                if uploaded_img:
                    st.image(uploaded_img, width=500)
                    if st.button("AI识别曲线", key=f"parse_img_{i}"):
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
                edited_df = st.data_editor(df_input, num_rows="dynamic", key=f"cop_table_{i}")
                if not edited_df.empty:
                    cop_curve = parse_cop_curve_from_table(
                        edited_df["负载率(%)"].tolist(),
                        edited_df["COP"].tolist()
                    )

            else:  # 文本描述
                text = st.text_area(
                    "输入COP数据 (每行: 负载率 COP)",
                    value="100% 6.0\n80% 6.3\n60% 6.0\n40% 4.8",
                    key=f"cop_text_{i}"
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

    ai_chw = ai_topo.get("chw_pumps", [{}])[0] if ai_topo.get("chw_pumps") else {}
    ai_cw = ai_topo.get("cw_pumps", [{}])[0] if ai_topo.get("cw_pumps") else {}
    ai_tw = ai_topo.get("towers", [{}])[0] if ai_topo.get("towers") else {}

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**冷冻泵**")
        chw_qty = st.number_input("台数", 1, 20, ai_chw.get("qty", 4), key="chw_qty")
        chw_power = st.number_input("单台功率(kW)", 1.0, 500.0, float(ai_chw.get("power_kw", 132)), key="chw_pow")
        chw_flow = st.number_input("单台流量(m³/h)", 10.0, 5000.0, float(ai_chw.get("flow_m3h", 920)), key="chw_flow")
        chw_vf = st.checkbox("变频", value=ai_chw.get("variable_freq", True), key="chw_vf")

    with col_b:
        st.markdown("**冷却泵**")
        cw_qty = st.number_input("台数", 1, 20, ai_cw.get("qty", 4), key="cw_qty")
        cw_power = st.number_input("单台功率(kW)", 1.0, 500.0, float(ai_cw.get("power_kw", 132)), key="cw_pow")
        cw_flow = st.number_input("单台流量(m³/h)", 10.0, 5000.0, float(ai_cw.get("flow_m3h", 1300)), key="cw_flow")
        cw_vf = st.checkbox("变频", value=ai_cw.get("variable_freq", False), key="cw_vf")

    st.markdown("**冷却塔**")
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        tower_qty = st.number_input("台数", 1, 20, ai_tw.get("qty", 4), key="tower_qty")
    with col_t2:
        tower_fan_kw = st.number_input("单台风机功率(kW)", 1.0, 100.0, float(ai_tw.get("fan_power_kw", 22)), key="tower_fan")
        tower_fans = st.number_input("每台风机数", 1, 4, ai_tw.get("fans_per_tower", 2), key="tower_fans")
    with col_t3:
        tower_vf = st.checkbox("变频", value=ai_tw.get("variable_freq", True), key="tower_vf")

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

    load_ratio = st.slider("平均负载率", 0.3, 1.0, default_load, 0.05)

    st.caption("每月开机台数")
    monthly_counts = []
    cols = st.columns(12)
    for i, col in enumerate(cols):
        with col:
            v = col.number_input(f"{i+1}月", 1, 10, default_chiller_count[i], key=f"mc_{i}")
            monthly_counts.append(v)

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
            "base_load_ratio": load_ratio,
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
    """调用AI解析COP曲线图片"""
    try:
        import base64
        from simulation.ai_service import _get_client, _get_model

        image_data = uploaded_file.getvalue()
        b64 = base64.b64encode(image_data).decode()
        media_type = "image/jpeg" if uploaded_file.name.lower().endswith((".jpg", ".jpeg")) else "image/png"

        client = _get_client()
        response = client.messages.create(
            model=_get_model(),
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "请从这张COP性能曲线图/表格中提取数据。输出格式为每行一个数据点：负载率百分比 COP值。例如：\n100 6.0\n90 6.2\n80 6.3\n只输出数据，不要其他文字。"}
                ]
            }]
        )

        text = response.content[0].text
        from simulation.input_parser import parse_cop_curve_from_text
        return parse_cop_curve_from_text(text)
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
