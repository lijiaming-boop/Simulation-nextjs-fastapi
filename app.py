"""空调节能率智能测算工具 - Streamlit 主应用"""
import streamlit as st
import json
import time
import pandas as pd
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from streamlit_scroll_to_top import scroll_to_here
from core.skill_caller import SkillCaller, SkillError
from core.data_filler import DataFiller
from core.excel_calculator import ExcelCalculator


# ==================== 流式 UI 辅助函数 ====================

def create_streaming_container(title: str = "🤖 查看 AI 分析过程"):
    """创建流式日志容器

    Args:
        title: expander 标题

    Returns:
        (expander, container): expander 对象和用于流式更新的 container
    """
    expander = st.expander(title, expanded=True)  # 默认展开
    with expander:
        container = st.empty()  # 用于流式更新的容器
    return expander, container


def update_streaming_container(container, texts: list):
    """更新流式容器显示

    Args:
        container: st.empty() 容器
        texts: 文本列表
    """
    # 拼接所有文本，使用 Markdown 渲染
    combined_text = "\n\n".join(texts)  # 段落间用两个换行分隔
    container.markdown(combined_text)


def init_session_state():
    """初始化 session state"""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'
        st.session_state.uploaded_file = None
        st.session_state.original_filename = None
        st.session_state.extracted_data = None
        st.session_state.quality_report = None
        st.session_state.filling_suggestions = None
        st.session_state.result = None
        st.session_state.uploader_key = 0
        st.session_state.scroll_to_top = False

        from core.session_manager import SessionManager
        st.session_state.session_manager = SessionManager()
        st.session_state.session_dir = st.session_state.session_manager.create_session_directory()


def reset_flow():
    """重置流程"""
    st.session_state.stage = 'upload'
    st.session_state.uploaded_file = None
    st.session_state.original_filename = None  # 新增
    st.session_state.extracted_data = None
    st.session_state.quality_report = None
    st.session_state.filling_suggestions = None
    st.session_state.result = None
    # 重要：增加 uploader_key 强制清空 file_uploader 缓存
    st.session_state.uploader_key = st.session_state.get('uploader_key', 0) + 1

    # 新增：创建新的会话目录
    st.session_state.session_dir = st.session_state.session_manager.create_session_directory()


def main():
    """主函数"""
    # 页面配置
    st.set_page_config(
        page_title="空调节能率智能测算工具",
        page_icon="❄️",
        layout="wide"
    )

    # ==================== 应用主逻辑 ====================

    # 初始化
    init_session_state()

    # 标题和退出按钮
    col_title, col_logout = st.columns([6, 1])
    with col_title:
        st.title("❄️ 空调节能率智能测算工具")
    with col_logout:
        st.link_button("🚪 退出", "/logout", use_container_width=True)
    
    st.markdown("---")

    # 滚动到顶部逻辑（在标题之后立即执行）
    if st.session_state.get('scroll_to_top', False):
        scroll_to_here(0, key='scroll_to_top_marker')
        st.session_state.scroll_to_top = False  # 重置标志

    # 流程进度指示器
    stages = ['上传调研表', '数据提取 + 质量检查', '数据填充', '节能测算', '结果展示']
    stage_map = {
        'upload': 0, 'extract_check': 1,
        'filling': 2, 'calculate': 3, 'result': 4
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
    elif stage == 'extract_check':
        render_extract_check_stage()
    elif stage == 'filling':
        render_filling_stage()
    elif stage == 'calculate':
        render_calculate_stage()
    elif stage == 'result':
        render_result_stage()


def render_upload_stage():
    """阶段 1: 上传调研表"""
    st.header("📁 步骤 1: 上传调研表")

    st.info("请上传标准的中央空调节能调研表 (Excel 格式)")

    uploaded_file = st.file_uploader(
        "选择文件",
        type=['xlsx', 'xls'],
        help="请使用标准调研表模板",
        key=f"file_uploader_{st.session_state.uploader_key}"  # 动态 key，reset 时强制刷新
    )

    if uploaded_file:
        st.session_state.uploaded_file = uploaded_file
        st.session_state.original_filename = uploaded_file.name  # 新增：保存原始文件名

        # 修改：保存到会话目录（不再使用硬编码的 tmp 目录）
        session_dir = st.session_state.session_dir
        upload_path = session_dir / "upload_survey.xlsx"

        with open(upload_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"✅ 文件已上传：{uploaded_file.name}")
        st.info(f"文件大小：{uploaded_file.size / 1024:.2f} KB")
        st.info(f"📂 会话目录：{session_dir.name}")  # 新增：显示会话目录名

        if st.button("🚀 开始分析", type="primary", use_container_width=True):
            st.session_state.stage = 'extract_check'
            st.session_state.scroll_to_top = True  # 新增：触发滚动
            st.rerun()


def render_extract_check_stage():
    """阶段 2: 数据提取和质量检查 (自动流转)"""
    st.header("🔍 步骤 2: 数据提取和质量检查")

    # 检查是否已经有缓存的结果（避免重复执行 skill）
    if (st.session_state.get('extracted_data') is not None and
        st.session_state.get('quality_report') is not None):
        # 使用缓存的结果
        extracted_data = st.session_state.extracted_data
        quality_report = st.session_state.quality_report
        st.info("ℹ️ 使用缓存的分析结果")
    else:
        # 创建流式日志容器
        _, log_container = create_streaming_container("🤖 查看灵知 AI 分析过程")

        # 需要执行 skill 获取新结果
        with st.spinner("正在提取调研表数据并进行质量检查，请稍候..."):
            try:
                # 流式日志累积器
                streaming_logs = []

                def on_text_received(timestamp: str, text: str):
                    """接收到 AI 文本时的回调"""
                    # 添加时间戳和品牌前缀
                    log_entry = f"**[{timestamp}]** 灵知 AI：{text}"
                    streaming_logs.append(log_entry)
                    update_streaming_container(log_container, streaming_logs)

                caller = SkillCaller(timeout=300)

                # 修改：使用会话目录
                session_dir = st.session_state.session_dir
                upload_path = session_dir / "upload_survey.xlsx"
                output_path = session_dir / "extract_check_result.json"

                # 获取原始文件名
                original_filename = st.session_state.get('original_filename', 'unknown.xlsx')

                # 调用合并的 Skill: 提取和质量检查，传递原始文件名和回调
                skill_result = caller.call_skill(
                    "extract-and-check-data",
                    str(upload_path),
                    str(output_path),
                    original_filename,  # 新增：传递原始文件名
                    callback=on_text_received  # 新增：传递流式回调
                )

                # 读取结果
                with open(output_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)

                # 检查是否有错误
                if result.get("error"):
                    st.error(f"❌ 数据处理失败：{result.get('message', '未知错误')}")
                    if st.button("🔄 重新上传", use_container_width=True):
                        reset_flow()
                        st.rerun()
                    return

                # 分离提取数据和质量报告
                extracted_data = result.get("extracted_data", {})
                quality_report = result.get("quality_report", {})

                # 保存到 session
                st.session_state.extracted_data = extracted_data
                st.session_state.quality_report = quality_report

                # 同时保存单独的文件（供后续步骤使用）
                # 修改：保存到会话目录
                with open(session_dir / "extracted_data.json", 'w', encoding='utf-8') as f:
                    json.dump(extracted_data, f, ensure_ascii=False, indent=2)
                with open(session_dir / "quality_report.json", 'w', encoding='utf-8') as f:
                    json.dump(quality_report, f, ensure_ascii=False, indent=2)

            except SkillError as e:
                st.error(f"❌ 数据处理失败：{str(e)}")
                if st.button("🔄 重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()
                return
            except Exception as e:
                st.error(f"❌ 发生未知错误：{str(e)}")
                if st.button("🔄 重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()
                return

    # =================================================================
    # 下面的代码对缓存和新获取的结果都生效
    # =================================================================

    # 展示提取结果
    st.success("✅ 数据提取完成")

    # 新增：展示站房类型（3 列布局）
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("项目地区", extracted_data.get("project_region", "未识别"))
    with col2:
        station_type = extracted_data.get("station_type", "unknown")
        station_type_names = {
            "standard": "标准站房",
            "secondary_pump": "二次泵站房",
            "unsupported": "⚠️ 不支持类型"
        }
        st.metric("站房类型", station_type_names.get(station_type, station_type))
    with col3:
        st.metric("月度数据记录", len(extracted_data.get("monthly_data", [])))

    # 新增：展示站房类型识别详情
    station_type_confidence = extracted_data.get("station_type_confidence", "unknown")
    station_type_reason = extracted_data.get("station_type_reason", "")

    if station_type_confidence != "high":
        st.info(
            f"ℹ️ **站房类型识别置信度**: {station_type_confidence}\n\n"
            f"**识别依据**: {station_type_reason}"
        )

    # 新增：检查是否为不支持类型（在质量检查之前）
    if station_type == "unsupported":
        st.markdown("---")
        st.error("⛔ **该类型站房不支持自动节能评估**")

        st.warning(
            "⚠️ 检测到您的站房包含以下特殊配置之一：\n\n"
            "- 热水泵\n"
            "- 水蓄冷/冰蓄冷\n"
            "- 中低温机组\n\n"
            "**这些特殊类型的站房节能计算逻辑较为复杂，暂不在本工具的自动评估范围内。**\n\n"
            f"**识别依据**: {station_type_reason}"
        )

        # 提供重新上传按钮
        if st.button("🔄 返回重新上传", type="primary", use_container_width=True):
            reset_flow()
            st.rerun()

        # 终止函数执行
        return

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

        severity_groups = {"critical": [], "high": [], "medium": [], "low": []}
        for issue in issues:
            severity = issue.get("severity", "low")
            severity_groups.get(severity, []).append(issue)

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
        st.success("✨ 未发现任何问题，数据质量优秀!")

    # 总结
    st.info(f"**总结**: {quality_report.get('summary', '数据检查完成')}")

    # 检查置信度级别
    confidence = quality_report.get("confidence_level", "unknown")

    if confidence == "low":
        # 低置信度，中断流程
        st.markdown("---")
        st.error("⛔ **数据质量不达标，无法继续计算**")

        st.warning(
            "⚠️ 当前数据完整率过低 (< 50%),无法保证计算结果的可靠性。\n\n"
            "**建议操作:**\n"
            "1. 在原始调研表中补充缺失的关键数据\n"
            "2. 确保至少填写 6 个月以上的运行数据\n"
            "3. 重点补充月度总能耗和冷机供水温度\n"
            "4. 补充完成后重新上传调研表"
        )

        # 展示必须修复的问题
        critical_and_high = [
            i for i in issues
            if i.get("severity") in ["critical", "high"]
        ]

        if critical_and_high:
            st.subheader("🔴 必须修复的问题")
            st.info(f"共 {len(critical_and_high)} 个严重/高优先级问题需要解决")

            for idx, issue in enumerate(critical_and_high[:20], 1):  # 最多显示 20 个
                st.error(
                    f"**{idx}. {issue.get('field')}**\n\n"
                    f"{issue.get('message')}"
                )

            if len(critical_and_high) > 20:
                st.warning(f"... 还有 {len(critical_and_high) - 20} 个问题未显示")

        # 提供重新上传按钮
        if st.button("🔄 返回重新上传", type="primary", use_container_width=True):
            reset_flow()
            st.rerun()

        # 终止函数执行，不进入下一阶段
        return

    # 中等/高置信度，展示提示但允许继续
    if confidence == "medium":
        st.warning(
            "⚠️ 数据完整率适中 (50%-80%),部分数据需要智能填充，请谨慎使用计算结果"
        )
    elif confidence == "high":
        st.success("✅ 数据质量良好，可以继续计算")

    with st.expander("查看提取的原始数据"):
        st.json(extracted_data)

    # 提供确认按钮进入下一阶段 (仅当置信度不是 low 时)
    st.markdown("---")
    if st.button("✅ 确认，进行下一步", type="primary", use_container_width=True):
        st.session_state.stage = 'filling'
        st.session_state.scroll_to_top = True  # 新增：触发滚动
        st.rerun()



def render_filling_stage():
    """阶段 3: 填充建议 (需要用户确认)"""
    st.header("🔧 步骤 3: 数据填充建议")

    # 检查是否已经生成填充建议
    if st.session_state.filling_suggestions is None:
        # 创建流式日志容器
        _, log_container = create_streaming_container("🤖 查看灵知 AI 推理过程")

        with st.spinner("正在生成智能填充建议..."):
            try:
                # 流式日志累积器
                streaming_logs = []

                def on_text_received(timestamp: str, text: str):
                    """接收到 AI 文本时的回调"""
                    # 添加时间戳和品牌前缀
                    log_entry = f"**[{timestamp}]** 灵知 AI：{text}"
                    streaming_logs.append(log_entry)
                    update_streaming_container(log_container, streaming_logs)

                caller = SkillCaller(timeout=300)

                # 修改：使用会话目录
                session_dir = st.session_state.session_dir
                extracted_path = session_dir / "extracted_data.json"
                quality_path = session_dir / "quality_report.json"
                output_path = session_dir / "filling_suggestions.json"

                # 调用 Skill 3: 填充建议，传递回调
                skill_result = caller.call_skill(
                    "suggest-data-filling",
                    str(extracted_path),
                    str(quality_path),
                    str(output_path),
                    callback=on_text_received  # 新增：传递流式回调
                )

                # 读取结果
                with open(output_path, 'r', encoding='utf-8') as f:
                    filling_suggestions = json.load(f)

                # 保存到 session
                st.session_state.filling_suggestions = filling_suggestions

            except SkillError as e:
                st.error(f"❌ 生成填充建议失败：{str(e)}")
                if st.button("🔄 返回重试", use_container_width=True):
                    st.session_state.stage = 'extract_check'
                    st.rerun()
                return
            except Exception as e:
                st.error(f"❌ 发生未知错误：{str(e)}")
                if st.button("🔄 返回重试", use_container_width=True):
                    st.session_state.stage = 'extract_check'
                    st.rerun()
                return

    # 展示填充建议
    suggestions = st.session_state.filling_suggestions

    # 检查是否可以继续
    can_proceed = suggestions.get("can_proceed", False)

    if not can_proceed:
        # 有不可填充字段，中断流程
        st.error("❌ 发现关键数据缺失，无法继续计算")

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
        # 可以继续，展示填充建议
        fillable = suggestions.get("fillable_suggestions", [])

        if fillable:
            st.success(f"✅ 生成了 {len(fillable)} 个智能填充建议")

            st.subheader("📝 填充建议详情")

            # 转换为 DataFrame 展示
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
                "如果您同意这些建议，点击下方按钮继续计算。"
            )
        else:
            st.success("✨ 数据完整，无需填充!")

        # 用户确认按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 确认填充，开始计算", type="primary", use_container_width=True):
                st.session_state.stage = 'calculate'
                st.session_state.scroll_to_top = True  # 新增：触发滚动
                st.rerun()

        with col2:
            if st.button("❌ 取消，重新上传", use_container_width=True):
                reset_flow()
                st.rerun()


def render_calculate_stage():
    """阶段 4: 执行计算 (自动执行)"""
    st.header("⚙️ 步骤 4: 执行计算")

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # 修改：使用会话目录
        session_dir = st.session_state.session_dir

        # 步骤 0: 执行数据填充（每次都重新生成，避免使用旧数据）
        status_text.text("正在填充数据...")
        progress_bar.progress(10)

        filler = DataFiller()
        filled_path = filler.fill_data(
            str(session_dir / "extracted_data.json"),
            str(session_dir / "filling_suggestions.json"),
            str(session_dir / "filled_data.json")
        )
        progress_bar.progress(20)

        # 读取数据检查站房类型
        with open(filled_path, 'r', encoding='utf-8') as f:
            filled_data = json.load(f)

        station_type = filled_data.get("station_type", "standard")

        # 再次检查是否为不支持类型（防御性编程）
        if station_type == "unsupported":
            st.error("❌ 该站房类型不支持自动计算")
            if st.button("🔄 返回重新上传", use_container_width=True):
                reset_flow()
                st.rerun()
            return

        # 步骤 1: 数据填充完成确认
        st.success("✅ 数据填充完成")
        progress_bar.progress(40)

        # 步骤 2: Excel 计算
        status_text.text("正在调用 AI 计算引擎...")
        progress_bar.progress(60)

        calculator = ExcelCalculator()  # 不传 template_path，自动根据 station_type 选择

        result_path = calculator.calculate(
            filled_path,
            str(session_dir / "result_data.json")
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

    except ValueError as e:
        # 捕获 unsupported 类型异常
        if "不支持的站房类型" in str(e):
            st.error(f"❌ {str(e)}")
            if st.button("🔄 返回重新上传", use_container_width=True):
                reset_flow()
                st.rerun()
        else:
            st.error(f"❌ 计算失败：{str(e)}")
            if st.button("🔄 返回重试", use_container_width=True):
                st.session_state.stage = 'filling'
                st.rerun()
    except Exception as e:
        st.error(f"❌ 计算失败：{str(e)}")
        if st.button("🔄 返回重试", use_container_width=True):
            st.session_state.stage = 'filling'
            st.rerun()


def render_result_stage():
    """阶段 5: 结果展示"""

    # 打印提示
    st.info("📋 **呼叫 SR 前，请点击右上角打印本页**")

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

    # 检查是否为范围计算结果
    if "energy_saving_rate_range" in result:
        # 新版：展示范围
        st.metric(
            "节能率范围",
            result["energy_saving_rate_range"],
            help="基于上限和下限两种估算方法"
        )

        # 详细展示：5 个核心指标
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric(
                "下限（保守估计）",
                f"{result['energy_saving_rate_min'] * 100:.1f}%"
            )

        with col2:
            st.metric(
                "上限（理想情况）",
                f"{result['energy_saving_rate_max'] * 100:.1f}%"
            )

        with col3:
            # P0 修复：添加总节能量范围
            total_min = result.get('total_saving_min', 0)
            total_max = result.get('total_saving_max', 0)
            st.metric(
                "总节能量范围",
                f"{total_min:.1f} - {total_max:.1f} 万 kWh",
                help="预估的年度总节能量范围"
            )

        with col4:
            completeness = result.get("completeness", 0)
            st.metric("数据完整度", f"{completeness * 100:.1f}%")

        with col5:
            filled_count = result.get("filled_count", 0)
            st.metric("填充字段数", filled_count)
    else:
        # 旧版：单一值（向后兼容）
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            rate = result.get("energy_saving_rate", 0)
            rate_min = result.get("energy_saving_rate_min", 0)
            rate_max = result.get("energy_saving_rate_max", 0)

            # P1 修复：恢复 delta 显示（如果 min/max 存在）
            if rate_min > 0 and rate_max > 0:
                st.metric(
                    "预估节能率",
                    f"{rate * 100:.2f}%",
                    delta=f"{rate_min * 100:.1f}% ~ {rate_max * 100:.1f}%"
                )
            else:
                st.metric(
                    "预估节能率",
                    f"{rate * 100:.2f}%"
                )

        with col2:
            total_saving = result.get("total_saving", 0)
            st.metric("总节能量", f"{total_saving:.2f} 万 kWh")

        with col3:
            completeness = result.get("completeness", 0)
            st.metric("数据完整度", f"{completeness * 100:.1f}%")

        with col4:
            filled_count = result.get("filled_count", 0)
            st.metric("填充字段数", filled_count)

    st.markdown("---")

    # 分项节能明细
    st.subheader("📊 分项节能明细")

    # 检查是否为范围计算结果
    if "chiller_saving_min" in result:
        # 新版：展示范围
        savings_data = {
            "设备类型": ["冷机", "水泵", "冷却塔", "合计"],
            "节能量范围 (万 kWh)": [
                f"{result.get('chiller_saving_min', 0):.1f} - {result.get('chiller_saving_max', 0):.1f}",
                f"{result.get('pump_saving_min', 0):.1f} - {result.get('pump_saving_max', 0):.1f}",
                f"{result.get('tower_saving_min', 0):.1f} - {result.get('tower_saving_max', 0):.1f}",
                f"{result.get('total_saving_min', 0):.1f} - {result.get('total_saving_max', 0):.1f}"
            ],
            "下限 (万 kWh)": [
                result.get("chiller_saving_min", 0),
                result.get("pump_saving_min", 0),
                result.get("tower_saving_min", 0),
                result.get("total_saving_min", 0)
            ],
            "上限 (万 kWh)": [
                result.get("chiller_saving_max", 0),
                result.get("pump_saving_max", 0),
                result.get("tower_saving_max", 0),
                result.get("total_saving_max", 0)
            ]
        }

        df_savings = pd.DataFrame(savings_data)
        st.dataframe(df_savings, use_container_width=True, hide_index=True)

        # 柱状图 - 展示范围
        devices = ["冷机", "水泵", "冷却塔"]
        min_values = [
            result.get("chiller_saving_min", 0),
            result.get("pump_saving_min", 0),
            result.get("tower_saving_min", 0)
        ]
        max_values = [
            result.get("chiller_saving_max", 0),
            result.get("pump_saving_max", 0),
            result.get("tower_saving_max", 0)
        ]

        fig = go.Figure()

        # 添加下限柱
        fig.add_trace(go.Bar(
            name='下限（保守估计）',
            x=devices,
            y=min_values,
            text=[f"{v:.1f}" for v in min_values],
            textposition='outside'
        ))

        # 添加上限柱
        fig.add_trace(go.Bar(
            name='上限（理想情况）',
            x=devices,
            y=max_values,
            text=[f"{v:.1f}" for v in max_values],
            textposition='outside'
        ))

        fig.update_layout(
            title="分项节能量范围分布",
            xaxis_title="设备类型",
            yaxis_title="节能量 (万 kWh)",
            barmode='group'
        )

        st.plotly_chart(fig, use_container_width=True)

    else:
        # 旧版：单一值（向后兼容）
        savings_data = {
            "设备类型": ["冷机", "水泵", "冷却塔", "合计"],
            "节能量 (万 kWh)": [
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
            df_savings["占比"] = df_savings["节能量 (万 kWh)"].apply(
                lambda x: f"{x / total * 100:.1f}%" if x != total else "100%"
            )

        st.dataframe(df_savings, use_container_width=True, hide_index=True)

        # 柱状图
        fig = px.bar(
            df_savings[df_savings["设备类型"] != "合计"],
            x="设备类型",
            y="节能量 (万 kWh)",
            title="分项节能量分布",
            text="节能量 (万 kWh)"
        )
        fig.update_traces(texttemplate='%{text:.2f}', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # 置信度说明
    if result.get("mock"):
        st.warning("⚠️ 注意：此结果为模拟数据 (formulas 库不可用)")

    completeness = result.get("completeness", 0)
    if completeness >= 0.9:
        confidence_msg = "🟢 高置信度 - 数据完整，结果可靠"
    elif completeness >= 0.7:
        confidence_msg = "🟡 中等置信度 - 部分数据通过智能填充，建议谨慎使用"
    else:
        confidence_msg = "🔴 低置信度 - 较多数据缺失，结果仅供参考"

    st.info(confidence_msg)

    # 添加范围计算说明
    if result.get("calculation_method") == "dual_sheet":
        st.info(
            "📊 **节能率范围说明**\n\n"
            "- **下限（保守估计）**: 基于常规优化参数，考虑实际约束\n"
            "- **上限（理想情况）**: 基于最优运行条件，理想化假设\n"
            "- **实际节能效果**: 通常在此范围内，具体取决于项目实施情况"
        )

    st.markdown("---")

    # 下载区域
    st.subheader("📥 下载完整计算表格")
    st.info("完整的 Excel 计算表格包含详细的计算过程和中间数据，需要管理员权限下载")

    password = st.text_input("请输入管理员密码", type="password", key="download_password")

    if password:
        admin_password = st.secrets.get("admin_password", "admin123")
        if password == admin_password:
            st.success("✅ 密码验证通过")

            # 修改：从会话目录读取计算结果 Excel
            session_dir = st.session_state.session_dir
            excel_path = session_dir / "calculation_result.xlsx"

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
                st.warning("⚠️ Excel 文件未找到")
        else:
            st.error("❌ 密码错误，请联系管理员")

    st.markdown("---")

    # 元数据
    with st.expander("🔍 查看计算元数据", expanded=True):
        st.json(result)

    st.markdown("---")

    # 重新开始
    if st.button("🔄 开始新的测算", type="primary", use_container_width=True):
        reset_flow()
        st.rerun()


if __name__ == "__main__":
    main()
