"""节能率智能测算工具 - Streamlit 主应用"""
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
from config import WeatherService


# ==================== 全局配置 ====================

def init_session_state():
    """初始化 session state"""
    if 'stage' not in st.session_state:
        st.session_state.stage = 'upload'
        st.session_state.ac_stage = 'upload'  # 空调模块独立stage
        st.session_state.compressor_stage = 'upload'  # 空压模块独立stage
        st.session_state.uploaded_file = None
        st.session_state.original_filename = None
        
        # 通用数据状态（保持向后兼容）
        st.session_state.extracted_data = None
        st.session_state.quality_report = None
        st.session_state.filling_suggestions = None
        st.session_state.result = None
        
        # 空调模块独立数据状态
        st.session_state.ac_extracted_data = None
        st.session_state.ac_quality_report = None
        st.session_state.ac_filling_suggestions = None
        st.session_state.ac_result = None
        
        # 空压模块独立数据状态
        st.session_state.compressor_extracted_data = None
        st.session_state.compressor_quality_report = None
        st.session_state.compressor_filling_suggestions = None
        st.session_state.compressor_result = None
        
        st.session_state.uploader_key = 0
        st.session_state.scroll_to_top = False

        from core.session_manager import SessionManager
        st.session_state.session_manager = SessionManager()
        st.session_state.session_dir = st.session_state.session_manager.create_session_directory()


def reset_flow():
    """重置流程"""
    st.session_state.stage = 'upload'
    st.session_state.ac_stage = 'upload'  # 空调模块独立stage
    st.session_state.compressor_stage = 'upload'  # 空压模块独立stage
    st.session_state.uploaded_file = None
    st.session_state.original_filename = None
    # 清理通用状态变量（避免模块间数据污染）
    st.session_state.extracted_data = None
    st.session_state.quality_report = None
    st.session_state.filling_suggestions = None
    st.session_state.result = None
    # 为每个模块创建独立的数据状态
    st.session_state.ac_extracted_data = None
    st.session_state.ac_quality_report = None
    st.session_state.ac_filling_suggestions = None
    st.session_state.ac_result = None
    st.session_state.compressor_extracted_data = None
    st.session_state.compressor_quality_report = None
    st.session_state.compressor_filling_suggestions = None
    st.session_state.compressor_result = None
    st.session_state.uploader_key = st.session_state.get('uploader_key', 0) + 1
    st.session_state.session_dir = st.session_state.session_manager.create_session_directory()


# ==================== UI 辅助函数 ====================

def create_streaming_container(title: str = "🤖 查看 AI 分析过程"):
    """创建流式日志容器"""
    expander = st.expander(title, expanded=True)
    with expander:
        container = st.empty()
    return expander, container


def update_streaming_container(container, texts: list):
    """更新流式容器显示"""
    combined_text = "\n\n".join(texts)
    container.markdown(combined_text)


def apply_filling_suggestions(data: dict, suggestions: dict) -> dict:
    """应用空压机数据填充建议到数据中"""
    import copy
    filled_data = copy.deepcopy(data)
    
    fillable_suggestions = suggestions.get('fillable_suggestions', [])
    
    for suggestion in fillable_suggestions:
        field = suggestion.get('field', '')
        suggested_value = suggestion.get('suggested_value')
        
        # 处理设备列表字段
        if field.startswith('equipmentList['):
            try:
                import re
                match = re.match(r'equipmentList\[(\d+)\]\.(.+)', field)
                if match:
                    index = int(match.group(1))
                    field_name = match.group(2)
                    
                    if 'equipmentLevel' not in filled_data:
                        filled_data['equipmentLevel'] = []
                    
                    while len(filled_data['equipmentLevel']) <= index:
                        filled_data['equipmentLevel'].append({})
                    
                    filled_data['equipmentLevel'][index][field_name] = suggested_value
            except (ValueError, IndexError) as e:
                print(f"应用设备字段填充建议失败: {field}, 错误: {e}")
        
        # 处理项目级字段
        elif 'projectLevel' not in filled_data:
            filled_data['projectLevel'] = {}
        
        if '.' in field and not field.startswith('equipmentList['):
            field_name = field.split('.')[-1]
            filled_data['projectLevel'][field_name] = suggested_value
        elif not field.startswith('equipmentList['):
            filled_data[field] = suggested_value
    
    return filled_data


def apply_filling_suggestions(data: dict, suggestions: dict) -> dict:
    """应用空压机数据填充建议到数据中"""
    import copy
    filled_data = copy.deepcopy(data)
    
    fillable_suggestions = suggestions.get('fillable_suggestions', [])
    
    for suggestion in fillable_suggestions:
        field = suggestion.get('field', '')
        suggested_value = suggestion.get('suggested_value')
        
        # 处理设备列表字段
        if field.startswith('equipmentList['):
            try:
                import re
                match = re.match(r'equipmentList\[(\d+)\]\.(.+)', field)
                if match:
                    index = int(match.group(1))
                    field_name = match.group(2)
                    
                    if 'equipmentLevel' not in filled_data:
                        filled_data['equipmentLevel'] = []
                    
                    while len(filled_data['equipmentLevel']) <= index:
                        filled_data['equipmentLevel'].append({})
                    
                    filled_data['equipmentLevel'][index][field_name] = suggested_value
            except (ValueError, IndexError) as e:
                print(f"应用设备字段填充建议失败: {field}, 错误: {e}")
        
        # 处理项目级字段
        elif 'projectLevel' not in filled_data:
            filled_data['projectLevel'] = {}
        
        if '.' in field and not field.startswith('equipmentList['):
            field_name = field.split('.')[-1]
            filled_data['projectLevel'][field_name] = suggested_value
        elif not field.startswith('equipmentList['):
            filled_data[field] = suggested_value
    
    return filled_data


def render_progress_indicator():
    """渲染进度指示器"""
    if st.session_state.module_type == 'air_conditioner':
        stages = ['上传调研表', '数据提取 + 质量检查', '数据填充', '节能测算', '结果展示']
        stage_map = {'upload': 0, 'extract_check': 1, 'filling': 2, 'calculate': 3, 'result': 4}
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
    else:
        # 空压机模块的进度指示器
        stages = [
            {'id': 'upload', 'name': '上传调研表', 'number': '1', 'desc': '上传调研表文件'},
            {'id': 'extract_check', 'name': '数据提取', 'number': '2', 'desc': '提取并验证关键数据'},
            {'id': 'calculate', 'name': '节能计算', 'number': '3', 'desc': '计算节能率和节能量'},
            {'id': 'result', 'name': '结果展示', 'number': '4', 'desc': '查看节能测算结果'}
        ]
        
        st.markdown("""
        <div style="background: #FFFFFF; border-radius: 12px; padding: 24px; margin: 24px auto; 
                    max-width: 1200px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); border: 1px solid #E2E8F0;">
        """, unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        cols = [col1, col2, col3, col4]
        
        for i, stage in enumerate(stages):
            with cols[i]:
                is_completed = st.session_state.stage in ['extract_check', 'calculate', 'result'] if i == 0 else \
                              st.session_state.stage in ['calculate', 'result'] if i == 1 else \
                              st.session_state.stage in ['result'] if i == 2 else \
                              st.session_state.stage == 'result' if i == 3 else False
                
                is_current = (st.session_state.stage == 'upload' and i == 0) or \
                            (st.session_state.stage == 'extract_check' and i == 1) or \
                            (st.session_state.stage == 'calculate' and i == 2) or \
                            (st.session_state.stage == 'result' and i == 3)
                
                if is_completed:
                    circle_color = "#10B981"
                    text_color = "#065F46"
                    icon = "✓"
                elif is_current:
                    circle_color = "#3B82F6"
                    text_color = "#1E40AF"
                    icon = stage['number']
                else:
                    circle_color = "#E5E7EB"
                    text_color = "#6B7280"
                    icon = stage['number']
                
                st.markdown(f"""
                <div style="text-align: center; margin-bottom: 16px;">
                    <div style="width: 48px; height: 48px; background: {circle_color}; border-radius: 50%; 
                               display: flex; align-items: center; justify-content: center; margin: 0 auto 12px auto;
                               color: white; font-weight: 600; font-size: 18px;">{icon}</div>
                    <div style="color: {text_color}; font-weight: 600; font-size: 14px; margin-bottom: 4px;">
                        {stage['name']}</div>
                    <div style="color: #6B7280; font-size: 12px; line-height: 1.4;">{stage['desc']}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)


# ==================== 模块选择 ====================

def render_module_selection():
    """模块选择页面"""
    st.title("⚡ 节能率智能测算工具")
    st.markdown("---")

    # 迁移公告
    st.warning("""
    🚀 **空调 / 空压机节能测算已迁移到新版前端**

    空调和空压机节能率计算功能已升级到 **Next.js + FastAPI** 架构，
    请前往新版工具使用：[http://localhost:3000](http://localhost:3000)

    新版优势：更快的响应速度、实时 AI 日志流、LLM 智能填充建议。
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📁 项目结构")
        st.info("""
        该工具包含三个主要模块：
        - **空调节能率计算**：已迁移 → [新版](http://localhost:3000)
        - **空压机节能率计算**：已迁移 → [新版](http://localhost:3000)
        - **冷站性能仿真**：保留在此（基于设备拓扑的全年8760h仿真）
        """)

    with col2:
        st.markdown("### 🛠️ 选择模块")

        # 空调/空压已下线，显示为禁用状态
        st.button("❄️ 空调节能率计算（已迁移）", use_container_width=True, disabled=True)
        st.caption("→ 请使用 [新版前端 http://localhost:3000](http://localhost:3000)")

        st.button("🔧 空压机节能率计算（已迁移）", use_container_width=True, disabled=True)
        st.caption("→ 请使用 [新版前端 http://localhost:3000](http://localhost:3000)")

        st.markdown("---")
        if st.button("🔬 冷站性能仿真", use_container_width=True):
            st.session_state.module_type = 'plant_simulation'
            st.session_state.stage = 'simulation_input'
            st.rerun()
        st.caption("无需调研表，输入设备拓扑即可进行全年仿真分析")


# ==================== 上传阶段 ====================

def render_upload_stage():
    """上传调研表阶段"""
    if st.session_state.module_type == 'air_conditioner':
        st.header("📁 步骤 1: 上传调研表")
        st.info("请上传标准的中央空调节能调研表 (Excel 格式)")
        file_description = "中央空调节能调研表"
        file_types = ['xlsx', 'xls']
    else:
        st.markdown("### 📁 步骤 1: 上传调研表")
        st.info("请上传空压机节能调研表，支持 Excel、PPT、Word 格式")
        file_description = "空压机节能调研表"
        file_types = ['xlsx', 'xls', 'docx', 'doc', 'pptx', 'ppt']

    uploaded_file = st.file_uploader(
        f"选择{file_description}",
        type=file_types,
        key=f"file_uploader_{st.session_state.uploader_key}"
    )

    if uploaded_file is not None:
        st.session_state.uploaded_file = uploaded_file
        st.session_state.original_filename = uploaded_file.name
        
        st.success(f"✅ 文件已上传：{uploaded_file.name}")
        st.info(f"文件大小：{uploaded_file.size / 1024:.2f} KB")

        if st.button("🚀 开始数据提取", type="primary", use_container_width=True):
            st.session_state.stage = 'extract_check'
            # 根据模块类型设置对应的独立stage
            if st.session_state.module_type == 'air_conditioner':
                st.session_state.ac_stage = 'extract_check'
            else:
                st.session_state.compressor_stage = 'extract_check'
            st.session_state.scroll_to_top = True
            st.rerun()


# ==================== 空调模块阶段 ====================

def render_air_conditioner_extract_check_stage():
    """空调模块：数据提取与质量检查阶段"""
    st.header("🔍 步骤 2: 数据提取 + 质量检查")
    
    if st.session_state.ac_extracted_data is None:
        expander, container = create_streaming_container("🤖 AI 正在分析调研表...")
        
        try:
            skill_caller = SkillCaller()
            file_path = st.session_state.session_dir / st.session_state.original_filename
            
            with open(file_path, 'wb') as f:
                f.write(st.session_state.uploaded_file.getbuffer())

            streaming_texts = []
            def log_callback(message: str, *args):
                streaming_texts.append(f"🔄 {message}")
                update_streaming_container(container, streaming_texts)
                time.sleep(0.1)

            streaming_texts.append("📋 开始提取调研表数据...")
            update_streaming_container(container, streaming_texts)

            # 构建输出JSON路径
            output_json_path = st.session_state.session_dir / "ac_extracted_data.json"
            original_filename = st.session_state.get('original_filename', 'unknown.xlsx')
            
            result = skill_caller.call_skill(
                'extract-and-check-data',
                str(file_path),
                str(output_json_path),
                original_filename,
                callback=log_callback
            )

            # 读取结果
            with open(output_json_path, 'r', encoding='utf-8') as f:
                result_data = json.load(f)

            # 检查是否有错误
            if result_data.get("error"):
                st.error(f"❌ 数据处理失败：{result_data.get('message', '未知错误')}")
                if st.button("🔄 重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()
                return

            # 分离提取数据和质量报告
            extracted_data = result_data.get("extracted_data", {})
            quality_report = result_data.get("quality_report", {})

            # 保存到 session
            st.session_state.ac_extracted_data = extracted_data
            st.session_state.ac_quality_report = quality_report

            # 同时保存单独的文件（供后续步骤使用）
            with open(st.session_state.session_dir / "ac_extracted_data.json", 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)
            with open(st.session_state.session_dir / "ac_quality_report.json", 'w', encoding='utf-8') as f:
                json.dump(quality_report, f, ensure_ascii=False, indent=2)

            streaming_texts.append("✅ 数据提取和质量检查完成！")
            update_streaming_container(container, streaming_texts)

            time.sleep(1)
            st.rerun()  # 只刷新页面，不自动跳转

        except Exception as e:
            st.error(f"❌ 数据提取失败: {str(e)}")
            if st.button("🔄 重新上传", use_container_width=True):
                reset_flow()
                st.rerun()
            return
    
    # =================================================================
    # 下面的代码对缓存和新获取的结果都生效
    # =================================================================

    extracted_data = st.session_state.ac_extracted_data
    quality_report = st.session_state.ac_quality_report
    issues = quality_report.get("issues", [])

    # 展示提取结果
    st.success("✅ 数据提取完成")

    # 展示站房类型（3 列布局）
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

    # 展示站房类型识别详情
    station_type_confidence = extracted_data.get("station_type_confidence", "unknown")
    station_type_reason = extracted_data.get("station_type_reason", "")

    if station_type_confidence != "high":
        st.info(
            f"ℹ️ **站房类型识别置信度**: {station_type_confidence}\n\n"
            f"**识别依据**: {station_type_reason}"
        )

    # 检查是否为不支持类型（在质量检查之前）
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
        # 同时支持completeness和confidence字段名
        completeness = quality_report.get("completeness", quality_report.get("confidence", 0))
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
        st.session_state.scroll_to_top = True
        st.rerun()


def render_air_conditioner_filling_stage():
    """空调模块：数据填充阶段"""
    st.header("📝 步骤 3: 数据填充")
    
    if st.session_state.ac_filling_suggestions is None:
        expander, container = create_streaming_container("🤖 AI 正在生成填充建议...")
        
        try:
            skill_caller = SkillCaller()
            
            streaming_texts = []
            def log_callback(message: str, *args):
                streaming_texts.append(f"🔄 {message}")
                update_streaming_container(container, streaming_texts)
                time.sleep(0.1)

            streaming_texts.append("🧠 分析数据缺失情况...")
            update_streaming_container(container, streaming_texts)

            extracted_data_path = st.session_state.session_dir / "ac_extracted_data.json"
            with open(extracted_data_path, 'w', encoding='utf-8') as f:
                json.dump(st.session_state.ac_extracted_data, f, ensure_ascii=False, indent=2)
            
            # 构建质量报告路径和输出建议路径
            quality_report_path = st.session_state.session_dir / "ac_quality_report.json"
            with open(quality_report_path, 'w', encoding='utf-8') as f:
                json.dump(st.session_state.ac_quality_report, f, ensure_ascii=False, indent=2)
            
            filling_suggestions_path = st.session_state.session_dir / "ac_filling_suggestions.json"

            result = skill_caller.call_skill(
                'suggest-data-filling',
                str(extracted_data_path),
                str(quality_report_path),
                str(filling_suggestions_path),
                callback=log_callback
            )

            # 从文件读取结果（这是关键！）
            with open(filling_suggestions_path, 'r', encoding='utf-8') as f:
                filling_suggestions = json.load(f)

            streaming_texts.append("✅ 填充建议生成完成！")
            update_streaming_container(container, streaming_texts)

            st.session_state.ac_filling_suggestions = filling_suggestions

            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"❌ 生成填充建议失败: {str(e)}")
            if st.button("🔄 重新生成", type="secondary"):
                st.session_state.ac_filling_suggestions = None
                st.rerun()
    else:
        # 展示填充建议
        suggestions = st.session_state.ac_filling_suggestions

        # 检查是否可以继续
        can_proceed = suggestions.get("can_proceed", suggestions.get("canProceed", False))

        # 处理字符串类型的true/false
        if isinstance(can_proceed, str):
            can_proceed = can_proceed.lower() == 'true'
        if not can_proceed:
            # 有不可填充字段，中断流程
            st.error("❌ 发现关键数据缺失，无法继续计算")

            unfillable = suggestions.get("unfillable_fields", suggestions.get("unfillableFields", []))
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
                    st.session_state.scroll_to_top = True
                    st.rerun()

            with col2:
                if st.button("❌ 取消，重新上传", use_container_width=True):
                    reset_flow()
                    st.rerun()


def render_air_conditioner_calculate_stage():
    """空调模块：节能测算阶段"""
    st.header("⚡ 步骤 4: 节能测算")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    if st.session_state.ac_result is None:
        try:
            # 步骤 0: 执行数据填充（每次都重新生成，避免使用旧数据）
            status_text.text("正在填充数据...")
            progress_bar.progress(10)

            filler = DataFiller()
            filled_path = filler.fill_data(
                str(st.session_state.session_dir / "ac_extracted_data.json"),
                str(st.session_state.session_dir / "ac_filling_suggestions.json"),
                str(st.session_state.session_dir / "ac_filled_data.json")
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

            # 使用气象数据服务（已在文件顶部导入）
            weather_service = WeatherService()
            calculator = ExcelCalculator(weather_service=weather_service)  # 不传 template_path，自动根据 station_type 选择

            result_path = calculator.calculate(
                filled_path,
                str(st.session_state.session_dir / "ac_result_data.json")
            )

            # 读取结果
            with open(result_path, 'r', encoding='utf-8') as f:
                result = json.load(f)

            # 保存格式化结果
            formatted_result = calculator.format_export_results(filled_data, result)
            with open(st.session_state.session_dir / "ac_formatted_result.json", 'w', encoding='utf-8') as f:
                json.dump(formatted_result, f, ensure_ascii=False, indent=2)

            progress_bar.progress(80)

            # 读取结果
            with open(result_path, 'r', encoding='utf-8') as f:
                result = json.load(f)

            st.session_state.ac_result = result
            
            time.sleep(1)
            st.session_state.stage = 'result'
            st.rerun()

        except Exception as e:
            st.error(f"❌ 节能测算失败: {str(e)}")
            if st.button("🔄 重新计算", type="secondary"):
                st.session_state.ac_result = None
                st.rerun()
    else:
        st.success("✅ 节能测算完成")
        if st.button("📋 查看结果", type="primary"):
            st.session_state.stage = 'result'
            st.rerun()


def render_air_conditioner_result_stage():
    """空调模块：结果展示阶段"""

    # 打印提示
    st.info("📋 **呼叫 SR 前，请点击右上角打印本页**")

    st.header("📈 测算结果")

    result = st.session_state.ac_result

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
    st.subheader("📥 下载计算结果")
    
    # 下载格式化结果（简化版）
    st.info("**简化版表格**：只包含原始电量和节能量，单位为'万'")
    
    # 下载简化版 Excel 表格
    st.subheader("📥 下载简化版 Excel 表格")
    st.info("**简化版Excel表格**：已删除不必要的行和工作表，保留核心计算结果")
    
    # 从会话目录读取简化版 Excel
    session_dir = st.session_state.session_dir
    simplified_excel_path = session_dir / "simplified_result.xlsx"
    
    if simplified_excel_path.exists():
        with open(simplified_excel_path, "rb") as f:
            simplified_excel_data = f.read()
        
        st.download_button(
            label="📥 下载简化版 Excel 表格",
            data=simplified_excel_data,
            file_name=f"简化版节能测算结果_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    else:
        st.warning("⚠️ 简化版 Excel 文件未找到")
    
    st.markdown("---")
    
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

    # 仿真分析入口
    st.subheader("🔬 进阶：冷站性能仿真分析")
    st.caption("基于主机COP性能曲线，仿真全年8760小时运行，输出优化控制策略报告")
    if st.button("进入仿真分析 →", use_container_width=True):
        st.session_state.stage = 'simulation_input'
        st.rerun()

    st.markdown("---")

    # 重新开始
    if st.button("🔄 开始新的测算", type="primary", use_container_width=True):
        reset_flow()
        st.rerun()


# ==================== 空压机模块阶段 ====================

def apply_filling_suggestions(data: dict, suggestions: dict) -> dict:
    """应用空压机数据填充建议到数据中"""
    import copy
    import re
    filled_data = copy.deepcopy(data)
    
    # 确保rawData结构存在
    if 'rawData' not in filled_data:
        filled_data['rawData'] = {}
    if 'projectLevel' not in filled_data['rawData']:
        filled_data['rawData']['projectLevel'] = {}
    if 'equipmentLevel' not in filled_data['rawData']:
        filled_data['rawData']['equipmentLevel'] = []
    
    fillable_suggestions = suggestions.get('fillable_suggestions', [])
    
    for suggestion in fillable_suggestions:
        field = suggestion.get('field', '')
        suggested_value = suggestion.get('suggested_value')
        
        # 处理设备列表字段: equipmentList[{i}].fieldName
        if field.startswith('equipmentList['):
            try:
                match = re.match(r'equipmentList\[(\d+)\]\.(.+)', field)
                if match:
                    index = int(match.group(1))
                    field_name = match.group(2)
                    
                    equipment_list = filled_data['rawData']['equipmentLevel']
                    while len(equipment_list) <= index:
                        equipment_list.append({})
                    
                    equipment_list[index][field_name] = suggested_value
            except (ValueError, IndexError) as e:
                print(f"应用设备字段填充建议失败: {field}, 错误: {e}")
        
        # 处理项目级字段（直接字段名）
        elif not field.startswith('equipmentList['):
            filled_data['rawData']['projectLevel'][field] = suggested_value
    
    return filled_data

def render_air_compressor_extract_stage():
    """空压机模块：数据提取阶段"""
    st.markdown("### 📤 数据提取")
    
    # 使用空压模块独立stage
    if st.session_state.get('compressor_stage') is None:
        st.session_state.compressor_stage = 'upload'
    
    if st.session_state.compressor_extracted_data is None:
        expander, container = create_streaming_container("🤖 AI 正在分析调研表...")
        
        try:
            skill_caller = SkillCaller()
            file_path = st.session_state.session_dir / st.session_state.original_filename
            
            with open(file_path, 'wb') as f:
                f.write(st.session_state.uploaded_file.getvalue())
            
            streaming_texts = []
            def log_callback(message: str, *args):
                streaming_texts.append(f"🔄 {message}")
                update_streaming_container(container, streaming_texts)
                time.sleep(0.1)
            
            streaming_texts.append("📋 开始提取空压机调研表数据...")
            update_streaming_container(container, streaming_texts)
            
            # 准备输出文件路径
            extracted_text_path = st.session_state.session_dir / "extracted_air_compressor_text.json"
            
            result = skill_caller.call_skill(
                'extract-air-compressor-data-llm',
                str(file_path),
                str(extracted_text_path),
                st.session_state.original_filename,
                callback=log_callback
            )
            
            streaming_texts.append("✅ 数据提取完成！")
            update_streaming_container(container, streaming_texts)
            
            # 处理提取结果 - 从extracted_data.json文件中读取最终结构化数据（AI生成的文件名）
            extracted_data_path = st.session_state.session_dir / "extracted_data.json"
            
            if extracted_data_path.exists():
                with open(extracted_data_path, 'r', encoding='utf-8') as f:
                    actual_extracted_data = json.load(f)
                print(f"✅ [数据处理] 从文件读取到结构化数据")
            else:
                # 如果文件不存在，尝试从ai_responses中解析
                print(f"⚠️  [数据处理] extracted_data.json不存在，尝试从ai_responses解析")
                actual_extracted_data = result
                if 'ai_responses' in result and len(result['ai_responses']) > 0:
                    try:
                        import re
                        response_text = result['ai_responses'][0]
                        # 查找 JSON 代码块
                        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1)
                            actual_extracted_data = json.loads(json_str)
                        else:
                            # 如果没有代码块，尝试直接解析整个响应
                            actual_extracted_data = json.loads(response_text)
                    except (json.JSONDecodeError, AttributeError) as e:
                        print(f"解析 ai_responses 失败: {e}")
                        actual_extracted_data = result
            
            st.session_state.compressor_extracted_data = actual_extracted_data
            
            # 从AI生成的数据中提取质量报告
            ai_quality_report = actual_extracted_data.get('quality_report', {})
            if ai_quality_report:
                st.session_state.compressor_quality_report = ai_quality_report
            else:
                st.session_state.compressor_quality_report = None
            
            # 检查打回条件 - 使用处理后的数据
            rejection_check = actual_extracted_data.get('rejectionCheck', {})
            if rejection_check.get('shouldReject', False):
                st.error("❌ 数据质量检查未通过，请完善调研表后重新上传")
                
                critical_issues = rejection_check.get('criticalIssues', [])
                if critical_issues:
                    st.markdown("**致命错误：**")
                    for issue in critical_issues:
                        st.error(f"• {issue}")
                
                high_issues = rejection_check.get('highSeverityIssues', [])
                if high_issues:
                    st.markdown("**高严重性错误：**")
                    for issue in high_issues:
                        st.warning(f"• {issue}")
                
                if st.button("🔄 重新上传", type="secondary", use_container_width=True):
                    reset_flow()
                    st.rerun()
                return
            
            time.sleep(1)
            st.session_state.compressor_stage = 'calculate'
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 数据提取失败: {str(e)}")
            if st.button("🔄 重新尝试", type="secondary"):
                st.session_state.compressor_extracted_data = None
                st.rerun()
    else:
        st.success("✅ 数据提取完成")
        
        raw_data = st.session_state.compressor_extracted_data.get('rawData', {})
        project_level = raw_data.get('projectLevel', {})
        equipment_level = raw_data.get('equipmentLevel', [])
        
        # 显示质量报告（使用空压模块独立状态）
        quality_report = st.session_state.compressor_quality_report or {}
        confidence = quality_report.get('confidence', 'medium')
        completeness = quality_report.get('completeness', 0)
        
        # 主数据展示区域
        st.markdown("---")
        st.markdown("### 📋 提取的关键数据")
        
        # 企业信息
        with st.expander("🏢 企业基本信息", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("企业名称", project_level.get('companyName', '未知'))
            with col2:
                st.metric("行业类型", project_level.get('industryType', '未知'))
            with col3:
                st.metric("项目地点", project_level.get('projectLocation', '未知'))
        
        # 能耗与压力数据
        with st.expander("⚡ 能耗与压力数据", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                annual_energy = project_level.get('totalAnnualEnergyConsumption', 0)
                st.metric("年耗电量", f"{annual_energy / 10000:.1f} 万kWh")
            with col2:
                st.metric("平均电价", f"{project_level.get('electricityPrice', 0):.4f} 元/kWh")
            with col3:
                st.metric("报警压力下限", f"{project_level.get('alarmPressureLowerLimit', 0):.1f} bar")
            with col4:
                st.metric("近14天平均压力", f"{project_level.get('averagePressure', 0):.1f} bar")
        
        # 设备清单
        with st.expander("🔧 设备清单", expanded=True):
            if equipment_level:
                # 统计设备类型
                type_counts = {}
                running_count = 0
                backup_count = 0
                
                for eq in equipment_level:
                    eq_type = eq.get('equipmentType', '未知')
                    type_counts[eq_type] = type_counts.get(eq_type, 0) + 1
                    status = eq.get('runningStatus', '')
                    if status == '运行':
                        running_count += 1
                    elif status == '备用':
                        backup_count += 1
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("设备总数", len(equipment_level))
                with col2:
                    st.metric("运行中", running_count)
                with col3:
                    st.metric("备用", backup_count)
                with col4:
                    st.metric("螺杆/离心机", f"{type_counts.get('螺杆', 0)}/{type_counts.get('离心', 0)}")
                
                # 设备详情表格
                st.markdown("**设备详情：**")
                equipment_data = []
                for eq in equipment_level:
                    equipment_data.append({
                        '设备编号': eq.get('equipmentId', ''),
                        '类型': eq.get('equipmentType', ''),
                        '品牌': eq.get('brand', ''),
                        '功率(kW)': eq.get('ratedPower', 0),
                        '流量(m³/min)': eq.get('ratedFlow', 0),
                        '状态': eq.get('runningStatus', '')
                    })
                
                st.dataframe(equipment_data, use_container_width=True)
            else:
                st.warning("暂无设备数据")
        
        # 质量评估
        with st.expander("📊 数据质量评估", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("数据完整度", f"{completeness * 100:.0f}%")
            with col2:
                confidence_color = "green" if confidence == "high" else "yellow" if confidence == "medium" else "red"
                st.metric("置信度", f":{confidence_color}[{confidence}]")
            
            # 问题列表
            issues = quality_report.get('issues', [])
            if issues:
                st.markdown("**注意事项：**")
                for issue in issues:
                    severity = issue.get('severity', 'low')
                    if severity == 'high':
                        st.warning(f"⚠️ {issue.get('description', '')}")
                    else:
                        st.info(f"ℹ️ {issue.get('description', '')}")
            else:
                st.success("✅ 数据质量良好，未发现问题")
        
        # 确认按钮
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 重新上传", type="secondary", use_container_width=True):
                reset_flow()
                st.rerun()
        with col2:
            if st.button("➡️ 确认数据并计算", type="primary", use_container_width=True):
                st.session_state.stage = 'calculate'
                st.session_state.compressor_stage = 'calculate'
                st.rerun()


def render_air_compressor_calculate_stage():
    """空压机模块：节能计算阶段"""
    st.markdown("### 📊 节能率计算")
    
    # 使用空压模块独立stage
    if st.session_state.get('compressor_stage') is None:
        st.session_state.compressor_stage = 'upload'
    
    if st.session_state.compressor_result is None:
        expander, container = create_streaming_container("🧮 AI 正在计算节能率...")
        
        try:
            skill_caller = SkillCaller()
            
            streaming_texts = []
            def log_callback(message: str, *args):
                streaming_texts.append(f"🔄 {message}")
                update_streaming_container(container, streaming_texts)
                time.sleep(0.1)
            
            extracted_data_path = st.session_state.session_dir / "compressor_extracted_data.json"
            with open(extracted_data_path, 'w', encoding='utf-8') as f:
                json.dump(st.session_state.compressor_extracted_data, f, ensure_ascii=False, indent=2)
            
            streaming_texts.append("🧠 生成数据填充建议...")
            update_streaming_container(container, streaming_texts)
            
            # 生成空压机数据填充建议（使用空压模块独立文件）
            filling_suggestions_path = st.session_state.session_dir / "compressor_filling_suggestions.json"
            
            # 使用AI生成的质量报告，如果没有则创建默认报告
            if st.session_state.compressor_quality_report is None:
                quality_report = {
                    "completeness": 0.8,
                    "confidence": "medium",
                    "issues": []
                }
                st.session_state.compressor_quality_report = quality_report
            
            # 保存质量报告到文件
            quality_report_path = st.session_state.session_dir / "compressor_quality_report.json"
            with open(quality_report_path, 'w', encoding='utf-8') as f:
                json.dump(st.session_state.compressor_quality_report, f, ensure_ascii=False, indent=2)
            
            filling_result = skill_caller.call_skill(
                'suggest-air-compressor-data-filling',
                str(extracted_data_path),
                str(quality_report_path),
                str(filling_suggestions_path),
                callback=log_callback
            )
            
            # 应用填充建议到数据中
            if filling_suggestions_path.exists():
                with open(filling_suggestions_path, 'r', encoding='utf-8') as f:
                    filling_suggestions = json.load(f)
                
                if filling_suggestions.get('can_proceed', False):
                    streaming_texts.append("📝 应用填充建议...")
                    update_streaming_container(container, streaming_texts)
                    
                    # 应用填充建议
                    filled_data = apply_filling_suggestions(st.session_state.compressor_extracted_data, filling_suggestions)
                    
                    # 保存填充后的数据
                    with open(extracted_data_path, 'w', encoding='utf-8') as f:
                        json.dump(filled_data, f, ensure_ascii=False, indent=2)
            
            streaming_texts.append("🧮 开始计算第二部分输入字段...")
            update_streaming_container(container, streaming_texts)
            
            streaming_texts.append("📈 计算系统级参数...")
            update_streaming_container(container, streaming_texts)
            
            streaming_texts.append("⚡ 计算节能率和节能量...")
            update_streaming_container(container, streaming_texts)
            
            result_path = st.session_state.session_dir / "compressor_calculation_result.json"
            
            result = skill_caller.call_skill(
                'calculate-air-compressor-energy-saving',
                str(extracted_data_path),
                str(result_path),
                callback=log_callback
            )
            
            if result_path.exists():
                with open(result_path, 'r', encoding='utf-8') as f:
                    calculation_result = json.load(f)
                st.session_state.compressor_result = calculation_result
            else:
                st.session_state.compressor_result = result
            
            streaming_texts.append("✅ 节能率计算完成！")
            update_streaming_container(container, streaming_texts)
            
            streaming_texts.append("📄 正在生成报告...")
            update_streaming_container(container, streaming_texts)
            
            # 自动生成报告
            try:
                report_path = generate_air_compressor_report()
                if report_path:
                    streaming_texts.append(f"✅ 报告生成完成: {report_path.name}")
                    st.session_state.compressor_report_generated = True
                    st.session_state.compressor_report_path = report_path
                else:
                    streaming_texts.append("⚠️ 报告生成失败")
                    st.session_state.compressor_report_generated = False
            except Exception as e:
                streaming_texts.append(f"⚠️ 报告生成异常: {str(e)}")
                st.session_state.compressor_report_generated = False
            
            update_streaming_container(container, streaming_texts)
            
            time.sleep(1)
            st.session_state.compressor_stage = 'result'
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 节能计算失败: {str(e)}")
            if st.button("🔄 重新计算", type="secondary"):
                st.session_state.result = None
                st.rerun()
    else:
        st.success("✅ 节能率计算完成")
        
        result = st.session_state.compressor_result
        energy_saving_rate = result.get('energy_saving_rate', 0) * 100
        st.metric("节能率", f"{energy_saving_rate:.1f}%")
        
        if st.button("📋 查看详细结果", type="primary", use_container_width=True):
            st.session_state.stage = 'result'
            st.rerun()


def render_air_compressor_result_stage():
    """空压机模块：结果展示阶段"""
    st.markdown("### 📋 节能测算结果")
    
    result = st.session_state.compressor_result
    
    # 主要指标
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        energy_saving_rate = result.get('energy_saving_rate', 0) * 100
        st.metric("节能率", f"{energy_saving_rate:.1f}%", help="系统优化后的节能率")
    
    with col2:
        energy_saving = result.get('energy_saving', 0) / 10000
        st.metric("年节能量", f"{energy_saving:.1f} 万kWh", help="每年可节约的电量")
    
    with col3:
        current_energy = result.get('current_total_energy', 0) / 10000
        st.metric("当前年耗电量", f"{current_energy:.1f} 万kWh", help="系统当前年度总耗电量")
    
    with col4:
        optimized_energy = result.get('optimized_total_energy', 0) / 10000
        st.metric("优化后年耗电量", f"{optimized_energy:.1f} 万kWh", help="系统优化后年度总耗电量")
    
    # 节能率范围
    st.markdown("#### 📊 节能率估算范围")
    energy_saving_range = result.get('energy_saving_rate_range', '0% - 0%')
    st.info(f"**节能率范围**: {energy_saving_range}")
    
    # 系统参数
    st.markdown("#### ⚙️ 系统参数")
    system_params = result.get('system_parameters', {})
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("系统压缩机功率因子", f"{system_params.get('systemCompressorPowerFactor', 0):.3f}")
    with col2:
        st.metric("系统比功率", f"{system_params.get('systemSpecificPower', 0):.2f} kW/(m³/min)")
    with col3:
        st.metric("系统压缩空气流量", f"{system_params.get('systemCompressedAirFlow', 0):.1f} m³/min")
    
    # 操作按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 重新测算", type="secondary", use_container_width=True):
            reset_flow()
            st.rerun()
    with col2:
        # 检查报告是否已生成（使用空压模块独立的键名）
        report_generated = st.session_state.get('compressor_report_generated', False)
        report_path = st.session_state.get('compressor_report_path', None)
        
        if report_generated and report_path and report_path.exists():
            # 报告已生成，提供下载按钮
            try:
                with open(report_path, 'rb') as f:
                    st.download_button(
                        label="📥 下载报告",
                        data=f.read(),
                        file_name=report_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        type="primary"
                    )
            except Exception as e:
                st.error(f"❌ 读取报告文件失败: {str(e)}")
        else:
            # 报告未生成，显示提示信息
            st.warning("⚠️ 报告未生成")


# ==================== 报告生成函数 ====================

def generate_air_compressor_report():
    """生成空压系统数智化升级方案报告"""
    try:
        # 获取数据（使用空压模块的session_state键名）
        extracted_data = st.session_state.get('compressor_extracted_data', {})
        result = st.session_state.get('compressor_result', {})
        
        if not extracted_data or not result:
            st.error("没有可用的数据生成报告")
            return None
        
        # 保存数据到临时文件
        output_dir = st.session_state.session_dir
        extracted_data_path = output_dir / "extracted_data_for_report.json"
        calculation_result_path = output_dir / "calculation_result_for_report.json"
        
        with open(extracted_data_path, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, ensure_ascii=False, indent=2)
        
        with open(calculation_result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 调用skill生成报告
        skill_caller = SkillCaller()
        skill_result = skill_caller.call_skill(
            "generate-air-compressor-report",
            str(extracted_data_path),
            str(calculation_result_path),
            str(output_dir)
        )
        
        # 检查生成的文件（支持多种格式）
        word_files = list(output_dir.glob("空压系统数智化升级方案_*.docx"))
        md_files = list(output_dir.glob("空压系统数智化升级方案_*.md"))
        html_files = list(output_dir.glob("空压系统数智化升级方案_*.html"))
        
        # 优先返回DOCX文件，其次MD文件，最后HTML文件
        if word_files:
            print(f"✅ [报告生成] 成功生成Word报告: {word_files[0]}")
            return word_files[0]
        elif md_files:
            print(f"✅ [报告生成] 成功生成MD报告: {md_files[0]}")
            return md_files[0]
        elif html_files:
            print(f"✅ [报告生成] 成功生成HTML报告: {html_files[0]}")
            return html_files[0]
        else:
            print(f"⚠️ [报告生成] 未找到生成的报告文件")
            print(f"⚠️ [报告生成] 目录中的文件: {list(output_dir.glob('*'))}")
            return None
            
    except Exception as e:
        print(f"生成报告失败: {str(e)}")
        return None


def generate_air_compressor_quote():
    """生成空压云智控报价单（调用generate_air_compressor_report）"""
    generate_air_compressor_report()


# ==================== 主应用 ====================

def main():
    """主函数"""
    st.set_page_config(
        page_title="节能率智能测算工具",
        page_icon="⚡",
        layout="wide"
    )
    
    # 添加CSS样式
    st.markdown("""
    <style>
    .main > div { background: #F8FAFC; min-height: 100vh; padding: 0; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    .main .block-container { max-width: 1200px !important; margin: 0 auto !important; padding: 0 24px !important; }
    .stMetric { background: #FFFFFF !important; border-radius: 12px !important; padding: 24px !important; 
                box-shadow: 0 4px 20px rgba(0,0,0,0.06) !important; border: 1px solid #E2E8F0 !important; }
    .stInfo { background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%) !important; 
              border: 1px solid #BAE6FD !important; border-radius: 12px !important; }
    .stSuccess { background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%) !important; 
                 border: 1px solid #A7F3D0 !important; border-radius: 12px !important; }
    .stWarning { background: linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%) !important; 
                 border: 1px solid #FDE68A !important; border-radius: 12px !important; }
    .stError { background: linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%) !important; 
               border: 1px solid #FCA5A5 !important; border-radius: 12px !important; }
    .stButton > button[kind="primary"] { background: #4F46E5 !important; border: none !important; 
                                         color: white !important; border-radius: 8px !important; font-weight: 600 !important; }
    .stButton > button[kind="secondary"] { background: #FFFFFF !important; border: 1px solid #E2E8F0 !important; 
                                           color: #475569 !important; border-radius: 8px !important; font-weight: 600 !important; }
    </style>
    """, unsafe_allow_html=True)
    
    init_session_state()
    
    # 模块选择
    if 'module_type' not in st.session_state:
        render_module_selection()
        return
    
    # 空调/空压已迁移，拦截并跳转
    if st.session_state.module_type in ('air_conditioner', 'air_compressor'):
        st.warning("""
        🚀 **该模块已迁移到新版前端**

        空调和空压机节能率计算已升级到 Next.js + FastAPI 架构，
        请前往新版工具：[http://localhost:3000](http://localhost:3000)
        """)
        if st.button("← 返回模块选择", type="primary"):
            del st.session_state.module_type
            st.rerun()
        return
    
    # 页面标题
    col_back, col_title, col_logout = st.columns([1, 8, 1])
    
    with col_back:
        if st.button("←", help="返回模块选择", use_container_width=True):
            del st.session_state.module_type
            st.rerun()
    
    with col_title:
        if st.session_state.module_type == 'air_conditioner':
            st.markdown("""
            <div style="text-align: center; margin: 40px 0 30px 0;">
                <h1 style="color: #1E293B; font-size: 28px; font-weight: 600; margin: 0;">
                    ❄️ 空调节能率智能测算工具
                </h1>
                <p style="color: #64748B; font-size: 14px; margin-top: 8px;">基于AI的智能节能评估系统</p>
            </div>
            """, unsafe_allow_html=True)
        elif st.session_state.module_type == 'plant_simulation':
            st.markdown("""
            <div style="text-align: center; margin: 40px 0 30px 0;">
                <h1 style="color: #1E293B; font-size: 28px; font-weight: 600; margin: 0;">
                    🔬 冷站性能仿真分析
                </h1>
                <p style="color: #64748B; font-size: 14px; margin-top: 8px;">基于设备拓扑的全年8760h仿真</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="text-align: center; margin: 40px 0 30px 0;">
                <h1 style="color: #1E293B; font-size: 28px; font-weight: 600; margin: 0;">
                    🔧 空压AI节能率测算
                </h1>
                <p style="color: #64748B; font-size: 14px; margin-top: 8px;">基于AI的智能节能评估系统</p>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 滚动到顶部
    if st.session_state.get('scroll_to_top', False):
        scroll_to_here(0, key='scroll_to_top_marker')
        st.session_state.scroll_to_top = False
    
    # 进度指示器
    render_progress_indicator()
    
    # 根据模块类型和阶段渲染对应界面
    stage = st.session_state.stage
    
    if st.session_state.module_type == 'air_conditioner':
        # 空调模块：5步流程 + 可选仿真
        if stage == 'upload':
            render_upload_stage()
        elif stage == 'extract_check':
            render_air_conditioner_extract_check_stage()
        elif stage == 'filling':
            render_air_conditioner_filling_stage()
        elif stage == 'calculate':
            render_air_conditioner_calculate_stage()
        elif stage == 'result':
            render_air_conditioner_result_stage()
        elif stage == 'simulation_input':
            from simulation_ui import render_simulation_input_stage
            render_simulation_input_stage()
        elif stage == 'simulation_result':
            from simulation_ui import render_simulation_result_stage
            render_simulation_result_stage()
    elif st.session_state.module_type == 'plant_simulation':
        # 独立仿真模块：无需调研表
        from simulation_ui import render_simulation_input_stage, render_simulation_result_stage
        if stage == 'simulation_input':
            render_simulation_input_stage()
        elif stage == 'simulation_result':
            render_simulation_result_stage()
        else:
            st.session_state.stage = 'simulation_input'
            st.rerun()
    else:
        # 空压机模块：4步简化流程
        # 使用空压模块独立stage，避免与空调模块冲突
        compressor_stage = st.session_state.get('compressor_stage', 'upload')
        
        if compressor_stage == 'upload' or stage == 'upload':
            render_upload_stage()
        elif compressor_stage == 'extract_check' or stage == 'extract_check':
            render_air_compressor_extract_stage()
        elif compressor_stage == 'calculate' or stage == 'calculate':
            render_air_compressor_calculate_stage()
        elif compressor_stage == 'result' or stage == 'result':
            render_air_compressor_result_stage()


if __name__ == "__main__":
    main()