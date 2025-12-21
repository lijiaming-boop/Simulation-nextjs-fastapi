"""空调节能率智能测算工具 - Streamlit主应用"""
import streamlit as st
import json
import time
import pandas as pd
from pathlib import Path
from core.skill_caller import SkillCaller, SkillError
from core.data_filler import DataFiller
from core.excel_calculator import ExcelCalculator


def init_session_state():
    """初始化 session state"""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'
        st.session_state.uploaded_file = None
        st.session_state.extracted_data = None
        st.session_state.quality_report = None
        st.session_state.filling_suggestions = None
        st.session_state.result = None


def reset_flow():
    """重置流程"""
    st.session_state.stage = 'upload'
    st.session_state.uploaded_file = None
    st.session_state.extracted_data = None
    st.session_state.quality_report = None
    st.session_state.filling_suggestions = None
    st.session_state.result = None


def main():
    """主函数"""
    # 页面配置
    st.set_page_config(
        page_title="空调节能率智能测算工具",
        page_icon="❄️",
        layout="wide"
    )

    # 初始化
    init_session_state()

    # 标题
    st.title("❄️ 空调节能率智能测算工具")
    st.markdown("---")

    # 流程进度指示器
    stages = ['上传', '提取', '质量检查', '填充建议', '计算', '结果']
    stage_map = {
        'upload': 0, 'extract': 1, 'quality': 2,
        'filling': 3, 'calculate': 4, 'result': 5
    }
    current_stage = stage_map.get(st.session_state.stage, 0)

    cols = st.columns(len(stages))
    for i, (col, stage_name) in enumerate(zip(cols, stages)):
        with col:
            if i < current_stage:
                st.success(f"✅ {stage_name}")
            elif i == current_stage:
                st.info(f"▶️ {stage_name}")
            else:
                st.text(f"⏸️ {stage_name}")

    st.markdown("---")

    # 根据阶段渲染不同界面
    stage = st.session_state.stage

    if stage == 'upload':
        render_upload_stage()
    elif stage == 'extract':
        render_extract_stage()
    elif stage == 'quality':
        render_quality_stage()
    elif stage == 'filling':
        render_filling_stage()
    elif stage == 'calculate':
        render_calculate_stage()
    elif stage == 'result':
        render_result_stage()


def render_upload_stage():
    """阶段1: 上传调研表"""
    st.header("📁 步骤 1: 上传调研表")

    st.info("请上传标准的中央空调节能调研表 (Excel格式)")

    uploaded_file = st.file_uploader(
        "选择文件",
        type=['xlsx', 'xls'],
        help="请使用标准调研表模板"
    )

    if uploaded_file:
        st.session_state.uploaded_file = uploaded_file

        # 保存到临时目录
        tmp_dir = Path("tmp")
        tmp_dir.mkdir(exist_ok=True)

        upload_path = tmp_dir / "upload_survey.xlsx"
        with open(upload_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"✅ 文件已上传: {uploaded_file.name}")
        st.info(f"文件大小: {uploaded_file.size / 1024:.2f} KB")

        if st.button("🚀 开始分析", type="primary", use_container_width=True):
            st.session_state.stage = 'extract'
            st.rerun()


def render_extract_stage():
    """阶段2: 数据提取 (自动流转)"""
    st.header("🔍 步骤 2: 数据提取")

    with st.spinner("正在提取调研表数据,请稍候..."):
        try:
            caller = SkillCaller(timeout=300)

            upload_path = Path("tmp/upload_survey.xlsx")
            output_path = Path("tmp/extracted_data.json")

            # 调用 Skill 1: 数据提取
            caller.call_skill(
                "extract-survey-data",
                str(upload_path),
                str(output_path)
            )

            # 读取结果
            with open(output_path, 'r', encoding='utf-8') as f:
                extracted_data = json.load(f)

            # 检查是否有错误
            if extracted_data.get("error"):
                st.error(f"❌ 数据提取失败: {extracted_data.get('message', '未知错误')}")
                if st.button("🔄 重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()
                return

            # 保存到 session
            st.session_state.extracted_data = extracted_data

            # 展示提取结果摘要
            st.success("✅ 数据提取成功")

            col1, col2 = st.columns(2)
            with col1:
                st.metric("项目地区", extracted_data.get("project_region", "未识别"))
            with col2:
                st.metric("月度数据记录", len(extracted_data.get("monthly_data", [])))

            with st.expander("查看提取的原始数据"):
                st.json(extracted_data)

            # 自动进入下一阶段
            time.sleep(1.5)
            st.session_state.stage = 'quality'
            st.rerun()

        except SkillError as e:
            st.error(f"❌ 数据提取失败: {str(e)}")
            if st.button("🔄 重新上传", use_container_width=True):
                reset_flow()
                st.rerun()
        except Exception as e:
            st.error(f"❌ 发生未知错误: {str(e)}")
            if st.button("🔄 重新上传", use_container_width=True):
                reset_flow()
                st.rerun()


def render_quality_stage():
    """阶段3: 质量检查 (自动流转)"""
    st.header("📊 步骤 3: 数据质量检查")

    with st.spinner("正在检查数据质量..."):
        try:
            caller = SkillCaller(timeout=300)

            extracted_path = Path("tmp/extracted_data.json")
            output_path = Path("tmp/quality_report.json")

            # 调用 Skill 2: 质量检查
            caller.call_skill(
                "check-data-quality",
                str(extracted_path),
                str(output_path)
            )

            # 读取结果
            with open(output_path, 'r', encoding='utf-8') as f:
                quality_report = json.load(f)

            # 保存到 session
            st.session_state.quality_report = quality_report

            # 展示质量报告
            st.success("✅ 质量检查完成")

            # 核心指标卡
            col1, col2, col3 = st.columns(3)
            with col1:
                completeness = quality_report.get("completeness", 0)
                st.metric(
                    "数据完整率",
                    f"{completeness * 100:.1f}%",
                    delta=None if completeness >= 0.8 else "需要改进"
                )
            with col2:
                confidence = quality_report.get("confidence_level", "unknown")
                confidence_map = {"high": "高", "medium": "中", "low": "低"}
                st.metric("置信水平", confidence_map.get(confidence, confidence))
            with col3:
                issues = quality_report.get("issues", [])
                critical_issues = len([i for i in issues if i.get("severity") == "critical"])
                st.metric("严重问题数", critical_issues)

            # 问题列表
            if issues:
                st.subheader("📋 发现的问题")

                # 按严重程度分组
                severity_groups = {"critical": [], "high": [], "medium": [], "low": []}
                for issue in issues:
                    severity = issue.get("severity", "low")
                    severity_groups.get(severity, []).append(issue)

                # 展示各级别问题
                severity_labels = {
                    "critical": "🔴 严重问题",
                    "high": "🟠 高优先级",
                    "medium": "🟡 中优先级",
                    "low": "🔵 低优先级"
                }

                for severity in ["critical", "high", "medium", "low"]:
                    group = severity_groups[severity]
                    if group:
                        with st.expander(f"{severity_labels[severity]} ({len(group)}个)", expanded=(severity == "critical")):
                            for issue in group:
                                st.warning(f"**字段**: {issue.get('field')}\n\n{issue.get('message')}")
            else:
                st.success("✨ 未发现任何问题,数据质量优秀!")

            # 总结
            st.info(f"**总结**: {quality_report.get('summary', '数据检查完成')}")

            # 自动进入下一阶段
            time.sleep(1.5)
            st.session_state.stage = 'filling'
            st.rerun()

        except SkillError as e:
            st.error(f"❌ 质量检查失败: {str(e)}")
            if st.button("🔄 返回重试", use_container_width=True):
                st.session_state.stage = 'extract'
                st.rerun()
        except Exception as e:
            st.error(f"❌ 发生未知错误: {str(e)}")
            if st.button("🔄 返回重试", use_container_width=True):
                st.session_state.stage = 'extract'
                st.rerun()


def render_filling_stage():
    """阶段4: 填充建议 (需要用户确认)"""
    st.header("🔧 步骤 4: 数据填充建议")

    # 检查是否已经生成填充建议
    if st.session_state.filling_suggestions is None:
        with st.spinner("正在生成智能填充建议..."):
            try:
                caller = SkillCaller(timeout=300)

                extracted_path = Path("tmp/extracted_data.json")
                quality_path = Path("tmp/quality_report.json")
                output_path = Path("tmp/filling_suggestions.json")

                # 调用 Skill 3: 填充建议
                caller.call_skill(
                    "suggest-data-filling",
                    str(extracted_path),
                    str(quality_path),
                    str(output_path)
                )

                # 读取结果
                with open(output_path, 'r', encoding='utf-8') as f:
                    filling_suggestions = json.load(f)

                # 保存到 session
                st.session_state.filling_suggestions = filling_suggestions

            except SkillError as e:
                st.error(f"❌ 生成填充建议失败: {str(e)}")
                if st.button("🔄 返回重试", use_container_width=True):
                    st.session_state.stage = 'quality'
                    st.rerun()
                return
            except Exception as e:
                st.error(f"❌ 发生未知错误: {str(e)}")
                if st.button("🔄 返回重试", use_container_width=True):
                    st.session_state.stage = 'quality'
                    st.rerun()
                return

    # 展示填充建议
    suggestions = st.session_state.filling_suggestions

    # 检查是否可以继续
    can_proceed = suggestions.get("can_proceed", False)

    if not can_proceed:
        # 有不可填充字段,中断流程
        st.error("❌ 发现关键数据缺失,无法继续计算")

        unfillable = suggestions.get("unfillable_fields", [])
        st.subheader("以下关键字段必须补充:")

        for field_info in unfillable:
            st.warning(
                f"**字段**: {field_info.get('field')}\n\n"
                f"**原因**: {field_info.get('reason')}"
            )

        st.info("💡 请在调研表中补充完整数据后重新上传")

        if st.button("🔄 重新上传", type="primary", use_container_width=True):
            reset_flow()
            st.rerun()
    else:
        # 可以继续,展示填充建议
        fillable = suggestions.get("fillable_suggestions", [])

        if fillable:
            st.success(f"✅ 生成了 {len(fillable)} 个智能填充建议")

            st.subheader("📝 填充建议详情")

            # 转换为DataFrame展示
            suggestions_data = []
            for s in fillable:
                suggestions_data.append({
                    "字段": s.get("field"),
                    "原始值": s.get("original_value") or "缺失",
                    "建议值": s.get("suggested_value"),
                    "方法": s.get("method"),
                    "置信度": s.get("confidence"),
                    "推理说明": s.get("reasoning")
                })

            df = pd.DataFrame(suggestions_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.info(
                "ℹ️ 这些填充建议基于已有数据的模式推断得出。"
                "如果您同意这些建议,点击下方按钮继续计算。"
            )
        else:
            st.success("✨ 数据完整,无需填充!")

        # 用户确认按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 确认填充,开始计算", type="primary", use_container_width=True):
                st.session_state.stage = 'calculate'
                st.rerun()

        with col2:
            if st.button("❌ 取消,重新上传", use_container_width=True):
                reset_flow()
                st.rerun()


def render_calculate_stage():
    """阶段5: 执行计算 (自动执行)"""
    st.header("⚙️ 步骤 5: 执行计算")

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # 步骤1: 数据填充
        status_text.text("正在填充数据...")
        progress_bar.progress(20)

        filler = DataFiller()
        filled_path = filler.fill_data(
            "tmp/extracted_data.json",
            "tmp/filling_suggestions.json",
            "tmp/filled_data.json"
        )

        st.success("✅ 数据填充完成")
        progress_bar.progress(40)

        # 步骤2: Excel计算
        status_text.text("正在调用Excel计算引擎...")
        progress_bar.progress(60)

        template_path = "00_sample/机房智能化节能评估表-按冷站电量数据.xlsx"
        calculator = ExcelCalculator(template_path)

        result_path = calculator.calculate(
            filled_path,
            "tmp/result_data.json"
        )

        progress_bar.progress(80)

        # 读取结果
        with open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        st.session_state.result = result

        progress_bar.progress(100)
        st.success("✅ 计算完成")

        # 进入结果阶段
        time.sleep(1)
        st.session_state.stage = 'result'
        st.rerun()

    except Exception as e:
        st.error(f"❌ 计算失败: {str(e)}")
        if st.button("🔄 返回重试", use_container_width=True):
            st.session_state.stage = 'filling'
            st.rerun()


def render_result_stage():
    """阶段6: 结果展示"""
    st.header("📈 测算结果")

    result = st.session_state.result

    if not result:
        st.error("❌ 未找到计算结果")
        if st.button("🔄 重新开始", use_container_width=True):
            reset_flow()
            st.rerun()
        return

    # 核心指标卡
    st.subheader("🎯 核心指标")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        rate = result.get("energy_saving_rate", 0)
        rate_min = result.get("energy_saving_rate_min", 0)
        rate_max = result.get("energy_saving_rate_max", 0)
        st.metric(
            "预估节能率",
            f"{rate * 100:.2f}%",
            delta=f"{rate_min * 100:.1f}% ~ {rate_max * 100:.1f}%"
        )

    with col2:
        total_saving = result.get("total_saving", 0)
        st.metric("总节能量", f"{total_saving:.2f} 万kWh")

    with col3:
        completeness = result.get("completeness", 0)
        st.metric("数据完整度", f"{completeness * 100:.1f}%")

    with col4:
        filled_count = result.get("filled_count", 0)
        st.metric("填充字段数", filled_count)

    st.markdown("---")

    # 分项节能明细
    st.subheader("📊 分项节能明细")

    savings_data = {
        "设备类型": ["冷机", "水泵", "冷却塔", "合计"],
        "节能量 (万kWh)": [
            result.get("chiller_saving", 0),
            result.get("pump_saving", 0),
            result.get("tower_saving", 0),
            result.get("total_saving", 0)
        ]
    }

    df_savings = pd.DataFrame(savings_data)

    # 计算百分比
    total = result.get("total_saving", 0)
    if total > 0:
        df_savings["占比"] = df_savings["节能量 (万kWh)"].apply(
            lambda x: f"{x / total * 100:.1f}%" if x != total else "100%"
        )

    st.dataframe(df_savings, use_container_width=True, hide_index=True)

    # 柱状图
    import plotly.express as px
    fig = px.bar(
        df_savings[df_savings["设备类型"] != "合计"],
        x="设备类型",
        y="节能量 (万kWh)",
        title="分项节能量分布",
        text="节能量 (万kWh)"
    )
    fig.update_traces(texttemplate='%{text:.2f}', textposition='outside')
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # 置信度说明
    if result.get("mock"):
        st.warning("⚠️ 注意: 此结果为模拟数据 (xlwings环境未配置)")

    completeness = result.get("completeness", 0)
    if completeness >= 0.9:
        confidence_msg = "🟢 高置信度 - 数据完整,结果可靠"
    elif completeness >= 0.7:
        confidence_msg = "🟡 中等置信度 - 部分数据通过智能填充,建议谨慎使用"
    else:
        confidence_msg = "🔴 低置信度 - 较多数据缺失,结果仅供参考"

    st.info(confidence_msg)

    st.markdown("---")

    # 下载区域
    st.subheader("📥 下载完整计算表格")
    st.info("完整的Excel计算表格包含详细的计算过程和中间数据,需要管理员权限下载")

    password = st.text_input("请输入管理员密码", type="password", key="download_password")

    if password:
        admin_password = st.secrets.get("admin_password", "admin123")
        if password == admin_password:
            st.success("✅ 密码验证通过")

            # 读取计算结果Excel
            excel_path = Path("tmp/calculation_result.xlsx")
            if excel_path.exists():
                with open(excel_path, "rb") as f:
                    excel_data = f.read()

                st.download_button(
                    label="📥 下载 Excel 计算表",
                    data=excel_data,
                    file_name=f"节能率计算结果_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.warning("⚠️ Excel文件未找到")
        else:
            st.error("❌ 密码错误,请联系管理员")

    st.markdown("---")

    # 元数据
    with st.expander("🔍 查看计算元数据"):
        st.json(result)

    # 重新开始
    if st.button("🔄 开始新的测算", type="primary", use_container_width=True):
        reset_flow()
        st.rerun()


if __name__ == "__main__":
    main()
