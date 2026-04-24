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
    st.session_state.original_filename = None
    st.session_state.extracted_data = None
    st.session_state.quality_report = None
    st.session_state.filling_suggestions = None
    st.session_state.result = None
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
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📁 项目结构")
        st.info("""
        该工具包含两个主要模块：
        - **空调节能率计算**：针对中央空调系统的节能评估
        - **空压机节能率计算**：针对压缩空气系统的节能评估
        """)
    
    with col2:
        st.markdown("### 🛠️ 选择模块")
        
        if st.button("❄️ 空调节能率计算", use_container_width=True, type="primary"):
            st.session_state.module_type = 'air_conditioner'
            st.rerun()
        
        if st.button("🔧 空压机节能率计算", use_container_width=True, type="primary"):
            st.session_state.module_type = 'air_compressor'
            st.rerun()


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
            st.session_state.scroll_to_top = True
            st.rerun()


# ==================== 空调模块阶段 ====================

def render_air_conditioner_extract_check_stage():
    """空调模块：数据提取与质量检查阶段"""
    st.header("🔍 步骤 2: 数据提取 + 质量检查")
    
    if st.session_state.extracted_data is None:
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

            result = skill_caller.call_skill(
                'extract-and-check-data',
                str(file_path),
                callback=log_callback
            )

            streaming_texts.append("✅ 数据提取和质量检查完成！")
            update_streaming_container(container, streaming_texts)

            st.session_state.extracted_data = result.get('extracted_data', {})
            st.session_state.quality_report = result.get('quality_report', {})

            time.sleep(1)
            st.session_state.stage = 'filling'
            st.rerun()

        except Exception as e:
            st.error(f"❌ 数据提取失败: {str(e)}")
            if st.button("🔄 重新尝试", type="secondary"):
                st.session_state.extracted_data = None
                st.rerun()
    else:
        st.success("✅ 数据提取和质量检查完成")
        if st.button("➡️ 继续数据填充", type="primary"):
            st.session_state.stage = 'filling'
            st.rerun()


def render_air_conditioner_filling_stage():
    """空调模块：数据填充阶段"""
    st.header("📝 步骤 3: 数据填充")
    
    if st.session_state.filling_suggestions is None:
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

            extracted_data_path = st.session_state.session_dir / "extracted_data.json"
            with open(extracted_data_path, 'w', encoding='utf-8') as f:
                json.dump(st.session_state.extracted_data, f, ensure_ascii=False, indent=2)

            result = skill_caller.call_skill(
                'suggest-data-filling',
                str(extracted_data_path),
                callback=log_callback
            )

            streaming_texts.append("✅ 填充建议生成完成！")
            update_streaming_container(container, streaming_texts)

            st.session_state.filling_suggestions = result

            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"❌ 生成填充建议失败: {str(e)}")
            if st.button("🔄 重新生成", type="secondary"):
                st.session_state.filling_suggestions = None
                st.rerun()
    else:
        st.success("✅ 填充建议已生成")
        
        suggestions = st.session_state.filling_suggestions.get('fillable_suggestions', [])
        if suggestions:
            st.info(f"发现 {len(suggestions)} 个可填充字段")
            
            # 显示填充建议
            for i, suggestion in enumerate(suggestions):
                with st.expander(f"字段 {i+1}: {suggestion.get('field_name', '未知字段')}"):
                    st.write(f"**建议值**: {suggestion.get('suggested_value', 'N/A')}")
                    st.write(f"**置信度**: {suggestion.get('confidence', 0):.1%}")
                    st.write(f"**说明**: {suggestion.get('reasoning', '无说明')}")
        
        if st.button("📊 开始节能测算", type="primary", use_container_width=True):
            st.session_state.stage = 'calculate'
            st.rerun()


def render_air_conditioner_calculate_stage():
    """空调模块：节能测算阶段"""
    st.header("⚡ 步骤 4: 节能测算")
    
    if st.session_state.result is None:
        expander, container = create_streaming_container("🧮 AI 正在计算节能率...")
        
        try:
            # 应用填充建议
            data_filler = DataFiller()
            filled_data = data_filler.apply_suggestions(
                st.session_state.extracted_data,
                st.session_state.filling_suggestions
            )
            
            # Excel计算
            calculator = ExcelCalculator()
            result = calculator.calculate_energy_saving(filled_data)
            
            st.session_state.result = result
            
            time.sleep(1)
            st.session_state.stage = 'result'
            st.rerun()

        except Exception as e:
            st.error(f"❌ 节能测算失败: {str(e)}")
            if st.button("🔄 重新计算", type="secondary"):
                st.session_state.result = None
                st.rerun()
    else:
        st.success("✅ 节能测算完成")
        if st.button("📋 查看结果", type="primary"):
            st.session_state.stage = 'result'
            st.rerun()


def render_air_conditioner_result_stage():
    """空调模块：结果展示阶段"""
    st.header("📊 步骤 5: 结果展示")
    
    result = st.session_state.result
    
    # 主要指标
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        rate = result.get("energy_saving_rate", 0)
        st.metric("节能率", f"{rate * 100:.1f}%")
    
    with col2:
        saving = result.get("total_energy_saving", 0)
        st.metric("年节能量", f"{saving:.1f} 万kWh")
    
    with col3:
        current = result.get("current_total_energy", 0)
        st.metric("当前年耗电量", f"{current:.1f} 万kWh")
    
    with col4:
        optimized = result.get("optimized_total_energy", 0)
        st.metric("优化后年耗电量", f"{optimized:.1f} 万kWh")
    
    # 操作按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 重新测算", type="secondary", use_container_width=True):
            reset_flow()
            st.rerun()
    with col2:
        st.button("📥 导出报告", type="primary", use_container_width=True, disabled=True)


# ==================== 空压机模块阶段 ====================

def render_air_compressor_extract_stage():
    """空压机模块：数据提取阶段"""
    st.markdown("### 🔍 数据提取与验证")
    
    if st.session_state.extracted_data is None:
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
            
            result = skill_caller.call_skill(
                'extract-air-compressor-data-llm',
                str(file_path),
                callback=log_callback
            )
            
            streaming_texts.append("✅ 数据提取完成！")
            update_streaming_container(container, streaming_texts)
            
            st.session_state.extracted_data = result
            
            # 检查打回条件
            rejection_check = result.get('rejectionCheck', {})
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
            st.session_state.stage = 'calculate'
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 数据提取失败: {str(e)}")
            if st.button("🔄 重新尝试", type="secondary"):
                st.session_state.extracted_data = None
                st.rerun()
    else:
        st.success("✅ 数据提取完成")
        
        raw_data = st.session_state.extracted_data.get('rawData', {})
        project_level = raw_data.get('projectLevel', {})
        equipment_level = raw_data.get('equipmentLevel', [])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("企业名称", project_level.get('companyName', '未知'))
        with col2:
            st.metric("行业类型", project_level.get('industryType', '未知'))
        with col3:
            st.metric("设备数量", len(equipment_level))
        
        if st.button("📊 开始节能计算", type="primary", use_container_width=True):
            st.session_state.stage = 'calculate'
            st.rerun()


def render_air_compressor_calculate_stage():
    """空压机模块：节能计算阶段"""
    st.markdown("### 📊 节能率计算")
    
    if st.session_state.result is None:
        expander, container = create_streaming_container("🧮 AI 正在计算节能率...")
        
        try:
            skill_caller = SkillCaller()
            
            streaming_texts = []
            def log_callback(message: str, *args):
                streaming_texts.append(f"🔄 {message}")
                update_streaming_container(container, streaming_texts)
                time.sleep(0.1)
            
            extracted_data_path = st.session_state.session_dir / "extracted_data.json"
            with open(extracted_data_path, 'w', encoding='utf-8') as f:
                json.dump(st.session_state.extracted_data, f, ensure_ascii=False, indent=2)
            
            streaming_texts.append("🧮 开始计算第二部分输入字段...")
            update_streaming_container(container, streaming_texts)
            
            streaming_texts.append("📈 计算系统级参数...")
            update_streaming_container(container, streaming_texts)
            
            streaming_texts.append("⚡ 计算节能率和节能量...")
            update_streaming_container(container, streaming_texts)
            
            result_path = st.session_state.session_dir / "calculation_result.json"
            
            result = skill_caller.call_skill(
                'calculate-air-compressor-energy-saving',
                str(extracted_data_path),
                str(result_path),
                callback=log_callback
            )
            
            if result_path.exists():
                with open(result_path, 'r', encoding='utf-8') as f:
                    calculation_result = json.load(f)
                st.session_state.result = calculation_result
            else:
                st.session_state.result = result
            
            streaming_texts.append("✅ 节能率计算完成！")
            update_streaming_container(container, streaming_texts)
            
            time.sleep(1)
            st.session_state.stage = 'result'
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 节能计算失败: {str(e)}")
            if st.button("🔄 重新计算", type="secondary"):
                st.session_state.result = None
                st.rerun()
    else:
        st.success("✅ 节能率计算完成")
        
        result = st.session_state.result
        energy_saving_rate = result.get('energy_saving_rate', 0) * 100
        st.metric("节能率", f"{energy_saving_rate:.1f}%")
        
        if st.button("📋 查看详细结果", type="primary", use_container_width=True):
            st.session_state.stage = 'result'
            st.rerun()


def render_air_compressor_result_stage():
    """空压机模块：结果展示阶段"""
    st.markdown("### 📋 节能测算结果")
    
    result = st.session_state.result
    
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
        st.button("📥 导出报告", type="primary", use_container_width=True, disabled=True)


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
        # 空调模块：5步流程
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
    else:
        # 空压机模块：4步简化流程
        if stage == 'upload':
            render_upload_stage()
        elif stage == 'extract_check':
            render_air_compressor_extract_stage()
        elif stage == 'calculate':
            render_air_compressor_calculate_stage()
        elif stage == 'result':
            render_air_compressor_result_stage()


if __name__ == "__main__":
    main()