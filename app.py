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
from config import WeatherService


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
        page_title="节能率智能测算工具",
        page_icon="⚡",
        layout="wide"
    )
    
    # 添加全局CSS样式 - 符合Figma设计
    st.markdown("""
    <style>
    .main > div {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        min-height: 100vh;
        padding: 20px;
    }
    .stApp > header {
        background: transparent;
    }
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    /* 隐藏Streamlit默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 自定义按钮样式 */
    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    </style>
    """, unsafe_allow_html=True)

    # ==================== 应用主逻辑 ====================

    # 初始化
    init_session_state()
    
    # 如果还没有选择模块类型，显示模块选择页面
    if 'module_type' not in st.session_state:
        render_module_selection()
        return

    # 标题和退出按钮
    col_back, col_title, col_logout = st.columns([1, 6, 1])
    
    with col_back:
        if st.button("←", help="返回模块选择", use_container_width=True):
            del st.session_state.module_type
            st.rerun()
    
    with col_title:
        if st.session_state.module_type == 'air_conditioner':
            st.title("❄️ 空调节能率智能测算工具")
        else:
            st.markdown("""
            <div style="text-align: center; margin: 20px 0;">
                <h1 style="color: #333; font-size: 2.5rem; font-weight: 600; margin: 0;">空压AI节能率测算</h1>
            </div>
            """, unsafe_allow_html=True)
    
    with col_logout:
        st.markdown("""
        <div style="display: flex; align-items: center; justify-content: center; height: 60px;">
            <div style="background: #f0f0f0; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">
                <span style="font-weight: 600; color: #333;">冯</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")

    # 滚动到顶部逻辑（在标题之后立即执行）
    if st.session_state.get('scroll_to_top', False):
        scroll_to_here(0, key='scroll_to_top_marker')
        st.session_state.scroll_to_top = False  # 重置标志

    # 流程进度指示器
    if st.session_state.module_type == 'air_conditioner':
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
    else:
        # 空压模块的进度指示器 - 完全符合Figma设计
        stages = [
            {'id': 'upload', 'name': '上传调研表', 'number': '1'},
            {'id': 'extract_check', 'name': '数据提取', 'number': '2'},
            {'id': 'filling', 'name': '节能测算', 'number': '3'},
            {'id': 'calculate', 'name': '输出结果', 'number': '4'}
        ]
        
        # 创建进度指示器容器 - 完全符合Figma设计
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    border-radius: 60px; 
                    padding: 25px 50px; 
                    margin: 40px auto; 
                    max-width: 800px;
                    position: relative;
                    box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);">
            <!-- 连接线 -->
            <div style="position: absolute; 
                        top: 50%; 
                        left: 15%; 
                        right: 15%; 
                        height: 2px; 
                        background: rgba(255,255,255,0.3); 
                        z-index: 1;"></div>
        """, unsafe_allow_html=True)
        
        # 创建水平布局
        col1, col2, col3, col4 = st.columns(4)
        cols = [col1, col2, col3, col4]
        
        for i, stage in enumerate(stages):
            with cols[i]:
                # 检查当前阶段
                is_completed = st.session_state.stage in ['extract_check', 'filling', 'calculate', 'result'] if i == 0 else \
                              st.session_state.stage in ['filling', 'calculate', 'result'] if i == 1 else \
                              st.session_state.stage in ['calculate', 'result'] if i == 2 else \
                              st.session_state.stage == 'result' if i == 3 else False
                
                is_current = (st.session_state.stage == 'upload' and i == 0) or \
                            (st.session_state.stage == 'extract_check' and i == 1) or \
                            (st.session_state.stage == 'filling' and i == 2) or \
                            (st.session_state.stage in ['calculate', 'result'] and i == 3)
                
                # 根据Figma设计的圆形指示器
                if is_completed or is_current:
                    # 活跃状态 - 白色背景，蓝色边框
                    circle_style = "background: white; border: 2px solid white; box-shadow: 0 2px 8px rgba(0,0,0,0.15);"
                    number_color = "#4A90E2"
                    text_color = "white"
                    text_opacity = "1"
                else:
                    # 未激活状态 - 半透明白色背景
                    circle_style = "background: rgba(255,255,255,0.4); border: 2px solid rgba(255,255,255,0.4);"
                    number_color = "white"
                    text_color = "rgba(255,255,255,0.7)"
                    text_opacity = "0.7"
                
                st.markdown(f"""
                <div style="display: flex; flex-direction: column; align-items: center; 
                            position: relative; z-index: 2; margin: 15px 0;">
                    <div style="width: 36px; height: 36px; border-radius: 50%; 
                                {circle_style}
                                display: flex; align-items: center; justify-content: center; 
                                margin-bottom: 12px;
                                transition: all 0.3s ease;">
                        <span style="color: {number_color}; font-weight: 700; font-size: 16px;">{stage["number"]}</span>
                    </div>
                    <div style="color: {text_color}; font-weight: 600; font-size: 13px; 
                                text-align: center; opacity: {text_opacity};
                                text-shadow: 0 1px 2px rgba(0,0,0,0.1);">
                        {stage["name"]}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

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
    
    st.markdown("---")
    st.markdown("### ℹ️ 使用说明")
    st.markdown("""
    1. 选择您需要使用的计算模块
    2. 上传对应的调研表（Excel格式）
    3. 系统将自动提取数据并进行质量检查
    4. 如有缺失数据，系统会提供智能填充建议
    5. 确认数据后，系统将进行节能率计算
    6. 查看计算结果并下载相关报告
    """)


def render_upload_stage():
    """阶段 1: 上传调研表"""
    if st.session_state.module_type == 'air_conditioner':
        st.header("📁 步骤 1: 上传调研表")
        st.info("请上传标准的中央空调节能调研表 (Excel 格式)")
        file_description = "中央空调节能调研表"
    else:
        # 空压模块的上传页面 - 完全符合Figma设计
        st.markdown("""
        <div style="background: white; 
                    border-radius: 16px; 
                    padding: 35px; 
                    margin: 30px auto;
                    max-width: 900px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.12);
                    border: 1px solid rgba(255,255,255,0.8);
                    position: relative;
                    overflow: hidden;">
            <!-- 顶部渐变条 -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        height: 4px; 
                        border-radius: 2px; 
                        margin: -35px -35px 30px -35px;"></div>
            <!-- 背景渐变 -->
            <div style="position: absolute; 
                        top: 0; 
                        left: 0; 
                        right: 0; 
                        height: 60px; 
                        background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
                        z-index: 0;"></div>
            <div style="position: relative; z-index: 1;">
                <h2 style="color: #2c3e50; font-size: 1.9rem; font-weight: 700; margin-bottom: 18px; letter-spacing: -0.5px;">
                    步骤 1: 上传调研表
                </h2>
                <p style="color: #5a6c7d; font-size: 1.05rem; margin-bottom: 30px; line-height: 1.6;">
                    请上传空压节能调研表，支持同时上传多个文件（最多10个，支持 Excel、PPT、Word 格式）
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        file_description = "空压机节能调研表"

    # 上传区域
    if st.session_state.module_type == 'air_conditioner':
        uploaded_file = st.file_uploader(
            f"选择{file_description}",
            type=['xlsx', 'xls'],
            help="请使用标准调研表模板",
            key=f"file_uploader_{st.session_state.uploader_key}"  # 动态 key，reset 时强制刷新
        )
    else:
        # 空压模块的上传区域 - 完全符合Figma设计
        st.markdown("""
        <div style="border: 2px dashed #9E9E9E; 
                    border-radius: 14px; 
                    padding: 50px 30px; 
                    text-align: center; 
                    background: linear-gradient(135deg, #fafbfc 0%, #f8f9fa 100%);
                    margin: 25px auto;
                    max-width: 800px;
                    transition: all 0.3s ease;
                    position: relative;
                    overflow: hidden;">
            <!-- 背景装饰 -->
            <div style="position: absolute; 
                        top: -50%; 
                        left: -50%; 
                        width: 200%; 
                        height: 200%; 
                        background: radial-gradient(circle, rgba(102, 126, 234, 0.03) 0%, transparent 70%);
                        z-index: 0;"></div>
            <div style="position: relative; z-index: 1;">
                <div style="font-size: 4rem; color: #9E9E9E; margin-bottom: 20px; 
                           filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));">📁</div>
                <h3 style="color: #2c3e50; font-size: 1.3rem; font-weight: 700; margin-bottom: 12px; letter-spacing: -0.3px;">
                    点击上传或拖拽文件到此处
                </h3>
                <p style="color: #6c757d; font-size: 0.95rem; margin: 0; line-height: 1.4;">
                    支持 Excel、PPT、Word 格式，最多上传10个文件，单个文件不超过 200MB
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "选择调研表文件",
            type=['xlsx', 'xls', 'pptx', 'ppt', 'docx', 'doc'],
            help="支持 Excel、PPT、Word 格式，最多上传10个文件，单个文件不超过 200MB",
            key=f"file_uploader_{st.session_state.uploader_key}",
            label_visibility="collapsed"
        )

    if uploaded_file:
        st.session_state.uploaded_file = uploaded_file
        st.session_state.original_filename = uploaded_file.name  # 新增：保存原始文件名

        # 修改：保存到会话目录（不再使用硬编码的 tmp 目录）
        session_dir = st.session_state.session_dir
        upload_path = session_dir / "upload_survey.xlsx"

        with open(upload_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if st.session_state.module_type == 'air_conditioner':
            st.success(f"✅ 文件已上传：{uploaded_file.name}")
            st.info(f"文件大小：{uploaded_file.size / 1024:.2f} KB")
            st.info(f"📂 会话目录：{session_dir.name}")  # 新增：显示会话目录名

            if st.button("🚀 开始分析", type="primary", use_container_width=True):
                st.session_state.stage = 'extract_check'
                st.session_state.scroll_to_top = True  # 新增：触发滚动
                st.rerun()
        else:
            # 空压模块的文件上传成功提示
            st.markdown("""
            <div style="background: linear-gradient(135deg, #e8f5e8 0%, #f1f8e9 100%); 
                        border: 1px solid #4CAF50; 
                        border-radius: 12px; 
                        padding: 20px; 
                        margin: 25px auto;
                        max-width: 800px;
                        box-shadow: 0 4px 12px rgba(76, 175, 80, 0.15);
                        position: relative;
                        overflow: hidden;">
                <!-- 成功图标背景 -->
                <div style="position: absolute; 
                            top: -10px; 
                            right: -10px; 
                            width: 60px; 
                            height: 60px; 
                            background: rgba(76, 175, 80, 0.1); 
                            border-radius: 50%;
                            z-index: 0;"></div>
                <div style="position: relative; z-index: 1;">
                    <div style="color: #2E7D32; font-weight: 700; font-size: 1.1rem; margin-bottom: 8px;">
                        ✅ 文件已上传：{filename}
                    </div>
                    <div style="color: #5a6c7d; font-size: 0.95rem; font-weight: 500;">
                        文件大小：{size:.2f} KB
                    </div>
                </div>
            </div>
            """.format(filename=uploaded_file.name, size=uploaded_file.size / 1024), unsafe_allow_html=True)

    # 空压模块的按钮区域 - 符合Figma设计
    if st.session_state.module_type == 'air_compressor':
        st.markdown("""
        <div style="display: flex; gap: 15px; margin: 30px 0; justify-content: flex-end;">
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.markdown("""
            <div style="margin-right: 10px;">
            """, unsafe_allow_html=True)
            if st.button("上一步", use_container_width=True, type="secondary"):
                if st.session_state.get('module_type'):
                    del st.session_state.module_type
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        with col2:
            st.markdown("""
            <div style="margin-left: 10px;">
            """, unsafe_allow_html=True)
            if uploaded_file:
                if st.button("下一步", use_container_width=True, type="primary"):
                    st.session_state.stage = 'extract_check'
                    st.session_state.scroll_to_top = True  # 新增：触发滚动
                    st.rerun()
            else:
                st.button("下一步", use_container_width=True, type="primary", disabled=True)
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)


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

                # 根据模块类型选择不同的技能
                if st.session_state.module_type == 'air_conditioner':
                    skill_name = "extract-and-check-data"
                else:
                    skill_name = "extract-air-compressor-data-llm"
                    
                # 调用合并的 Skill: 提取和质量检查，传递原始文件名和回调
                skill_result = caller.call_skill(
                    skill_name,
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

    # 根据模块类型显示不同的数据提取结果
    if st.session_state.module_type == 'air_conditioner':
        # 空调模块的显示逻辑
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
    else:
        # 空压机模块的显示逻辑 - 根据Figma设计稿
        # 空压模块的数据提取页面 - 符合Figma设计
        st.markdown("""
        <div style="background: white; 
                    border-radius: 16px; 
                    padding: 35px; 
                    margin: 30px auto;
                    max-width: 900px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.12);
                    border: 1px solid rgba(255,255,255,0.8);
                    position: relative;
                    overflow: hidden;">
            <!-- 顶部渐变条 -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        height: 4px; 
                        border-radius: 2px; 
                        margin: -35px -35px 30px -35px;"></div>
            <!-- 背景渐变 -->
            <div style="position: absolute; 
                        top: 0; 
                        left: 0; 
                        right: 0; 
                        height: 60px; 
                        background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
                        z-index: 0;"></div>
            <div style="position: relative; z-index: 1;">
                <h2 style="color: #2c3e50; font-size: 1.9rem; font-weight: 700; margin-bottom: 25px; letter-spacing: -0.5px;">
                    步骤 2: 数据提取
                </h2>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 数据完整度显示
        completeness = quality_report.get("completeness", 0)
        
        # 创建数据完整度卡片 - 符合Figma设计
        st.markdown("""
        <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
                    padding: 30px; 
                    border-radius: 16px; 
                    border: 1px solid #e9ecef; 
                    margin: 25px auto;
                    max-width: 900px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                    position: relative;
                    overflow: hidden;">
            <!-- 装饰元素 -->
            <div style="position: absolute; 
                        top: -20px; 
                        right: -20px; 
                        width: 80px; 
                        height: 80px; 
                        background: radial-gradient(circle, rgba(102, 126, 234, 0.1) 0%, transparent 70%);
                        border-radius: 50%;"></div>
        """, unsafe_allow_html=True)
            
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown(f"""
            <div style="text-align: center; position: relative; z-index: 1;">
                <div style="width: 100px; height: 100px; 
                           background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%); 
                           border-radius: 50%; 
                           display: flex; 
                           align-items: center; 
                           justify-content: center; 
                           margin: 0 auto 15px auto;
                           box-shadow: 0 4px 15px rgba(76, 175, 80, 0.3);">
                    <div style="color: white; font-size: 24px; font-weight: 800;">{completeness * 100:.0f}%</div>
                </div>
                <div style="color: #5a6c7d; font-size: 16px; font-weight: 600;">数据完整度</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            # 缺失字段显示 - 符合Figma设计
            issues = quality_report.get("issues", [])
            missing_fields = [issue for issue in issues if "缺失" in issue.get("description", "")]
            
            st.markdown("""
            <div style="position: relative; z-index: 1; padding: 10px 0;">
            """, unsafe_allow_html=True)
            
            if missing_fields:
                st.markdown(f"""
                <div style="margin-bottom: 20px;">
                    <div style="color: #e74c3c; font-weight: 700; font-size: 16px; margin-bottom: 15px;">
                        ⚠️ 缺失字段（{len(missing_fields)}项，均为非必填）
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 显示缺失字段标签 - 现代化设计
                missing_tags_html = ""
                for i, issue in enumerate(missing_fields[:5]):  # 最多显示5个
                    field_name = issue.get("field", "未知字段")
                    missing_tags_html += f"""
                    <span style="display: inline-block; 
                                 background: linear-gradient(135deg, #ffebee 0%, #fce4ec 100%); 
                                 color: #c62828; 
                                 padding: 8px 12px; 
                                 border-radius: 20px; 
                                 font-size: 13px; 
                                 font-weight: 600; 
                                 margin: 4px 8px 4px 0;
                                 border: 1px solid #ffcdd2;
                                 box-shadow: 0 2px 4px rgba(198, 40, 40, 0.1);">
                        {field_name}
                    </span>
                    """
                
                if len(missing_fields) > 5:
                    missing_tags_html += f"""
                    <span style="display: inline-block; 
                                 background: #f5f5f5; 
                                 color: #666; 
                                 padding: 8px 12px; 
                                 border-radius: 20px; 
                                 font-size: 13px; 
                                 font-weight: 600; 
                                 margin: 4px 8px 4px 0;">
                        +{len(missing_fields) - 5}项
                    </span>
                    """
                
                st.markdown(missing_tags_html, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="color: #2E7D32; font-weight: 700; font-size: 16px;">
                    ✅ 所有必填字段完整
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

        # 项目核心信息 - 符合Figma设计
        st.markdown("""
        <div style="background: white; 
                    border-radius: 16px; 
                    padding: 30px; 
                    margin: 25px auto;
                    max-width: 900px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                    border: 1px solid #e9ecef;">
            <h3 style="color: #2c3e50; font-size: 1.5rem; font-weight: 700; margin-bottom: 20px; letter-spacing: -0.3px;">
                📋 项目核心信息
            </h3>
        """, unsafe_allow_html=True)
        
        # 企业信息卡片 - 符合Figma设计
        company_name = extracted_data.get("companyName", "未知企业")
        project_name = extracted_data.get("projectName", "未知项目")
        project_location = extracted_data.get("projectLocation", "未知地址")
        industry_type = extracted_data.get("industryType", "未知行业")
        
        # 创建信息网格
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
                        padding: 20px; 
                        border-radius: 12px; 
                        border: 1px solid #e9ecef; 
                        margin-bottom: 15px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                        transition: all 0.3s ease;">
                <div style="color: #6c757d; font-size: 13px; font-weight: 600; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                    企业名称
                </div>
                <div style="font-weight: 700; color: #2c3e50; font-size: 16px; line-height: 1.4;">
                    {company_name}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
                        padding: 20px; 
                        border-radius: 12px; 
                        border: 1px solid #e9ecef; 
                        margin-bottom: 15px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                        transition: all 0.3s ease;">
                <div style="color: #6c757d; font-size: 13px; font-weight: 600; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                    项目地址
                </div>
                <div style="font-weight: 600; color: #2c3e50; font-size: 15px; line-height: 1.4;">
                    {project_location}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
                        padding: 20px; 
                        border-radius: 12px; 
                        border: 1px solid #e9ecef; 
                        margin-bottom: 15px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                        transition: all 0.3s ease;">
                <div style="color: #6c757d; font-size: 13px; font-weight: 600; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                    项目名称
                </div>
                <div style="font-weight: 600; color: #2c3e50; font-size: 15px; line-height: 1.4;">
                    {project_name}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
                        padding: 20px; 
                        border-radius: 12px; 
                        border: 1px solid #e9ecef; 
                        margin-bottom: 15px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                        transition: all 0.3s ease;">
                <div style="color: #6c757d; font-size: 13px; font-weight: 600; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                    行业类型
                </div>
                <div style="font-weight: 600; color: #2c3e50; font-size: 15px; line-height: 1.4;">
                    <span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                 color: white; 
                                 padding: 6px 12px; 
                                 border-radius: 20px; 
                                 font-size: 13px; 
                                 font-weight: 700;">
                        {industry_type}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        </div>
        """, unsafe_allow_html=True)
        
        # 企业简称
        company_short = extracted_data.get("companyShortName", "未知")
        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                    border: 1px solid #e0e0e0; margin-bottom: 8px;">
            <span style="color: #666; font-size: 12px;">企业简称</span><br>
            <span style="font-weight: 500; color: #333;">{company_short}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 项目名称（高亮显示）
        project_name = extracted_data.get("projectName", "空压系统节能项目")
        st.markdown(f"""
        <div style="background-color: #e8f5e8; padding: 12px; border-radius: 10px; 
                    border: 1px solid #4caf50; margin-bottom: 8px;">
            <span style="color: #666; font-size: 12px;">项目名称</span><br>
            <span style="font-weight: 500; color: #333;">{project_name}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 项目所在地
        location = extracted_data.get("projectLocation", "未填写")
        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                    border: 1px solid #e0e0e0; margin-bottom: 8px;">
            <span style="color: #666; font-size: 12px;">项目所在地（省市）</span><br>
            <span style="font-weight: 500; color: #333;">{location}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 行业类型
        industry = extracted_data.get("industryType", "其他")
        st.markdown(f"""
        <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                    border: 1px solid #e0e0e0; margin-bottom: 8px;">
            <span style="color: #666; font-size: 12px;">行业类型</span><br>
            <span style="font-weight: 500; color: #333;">{industry}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 空压系统年度总用量（高亮显示）
        total_energy = extracted_data.get("totalAnnualEnergyConsumption")
        if total_energy:
            st.markdown(f"""
            <div style="background-color: #fff3e0; padding: 12px; border-radius: 10px; 
                        border: 1px solid #ff9800; margin-bottom: 8px;">
                <span style="color: #666; font-size: 12px;">空压系统年度总用量</span><br>
                <span style="font-weight: bold; color: #e65100; font-size: 18px;">{total_energy}</span>
                <span style="color: #e65100; font-size: 14px;"> 万 kWh</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                        border: 1px solid #e0e0e0; margin-bottom: 8px;">
                <span style="color: #666; font-size: 12px;">空压系统年度总用量</span><br>
                <span style="font-weight: 500; color: #333;">未填写</span>
            </div>
            """, unsafe_allow_html=True)
        
        # 其他关键参数
        col1, col2 = st.columns(2)
        
        with col1:
            # 平均电价
            electricity_price = extracted_data.get("electricityPrice")
            price_text = f"{electricity_price} 元/kWh" if electricity_price else "未填写"
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                        border: 1px solid #e0e0e0; margin-bottom: 8px;">
                <span style="color: #666; font-size: 12px;">平均电价</span><br>
                <span style="font-weight: 500; color: #333;">{price_text}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # 近14天系统平均压力
            avg_pressure = extracted_data.get("averagePressure")
            pressure_text = f"{avg_pressure} bar" if avg_pressure else "未填写"
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                        border: 1px solid #e0e0e0; margin-bottom: 8px;">
                <span style="color: #666; font-size: 12px;">近14天系统平均压力</span><br>
                <span style="font-weight: 500; color: #333;">{pressure_text}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # 年运行天数
            annual_days = extracted_data.get("annualRunningDays")
            days_text = f"{annual_days} 天" if annual_days else "未填写"
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                        border: 1px solid #e0e0e0; margin-bottom: 8px;">
                <span style="color: #666; font-size: 12px;">年运行天数</span><br>
                <span style="font-weight: 500; color: #333;">{days_text}</span>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            # 现有系统报警压力（下限）
            alarm_pressure = extracted_data.get("alarmPressureLowerLimit")
            alarm_text = f"{alarm_pressure} bar" if alarm_pressure else "未填写"
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                        border: 1px solid #e0e0e0; margin-bottom: 8px;">
                <span style="color: #666; font-size: 12px;">现有系统报警压力（下限）</span><br>
                <span style="font-weight: 500; color: #333;">{alarm_text}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # 每天开机时间
            daily_hours = extracted_data.get("dailyRunningHours")
            hours_text = f"{daily_hours} 小时" if daily_hours else "未填写"
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 12px; border-radius: 10px; 
                        border: 1px solid #e0e0e0; margin-bottom: 8px;">
                <span style="color: #666; font-size: 12px;">每天开机时间</span><br>
                <span style="font-weight: 500; color: #333;">{hours_text}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
        
        # 设备清单 - 符合Figma设计
        st.markdown("""
        <div style="background: white; 
                    border-radius: 16px; 
                    padding: 30px; 
                    margin: 25px auto;
                    max-width: 900px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                    border: 1px solid #e9ecef;">
            <h3 style="color: #2c3e50; font-size: 1.5rem; font-weight: 700; margin-bottom: 20px; letter-spacing: -0.3px;">
                🔧 设备清单
            </h3>
        """, unsafe_allow_html=True)
        
        equipment_list = extracted_data.get("equipmentList", [])
        if equipment_list:
            # 按站房分组显示设备
            stations = {}
            for equipment in equipment_list:
                station = equipment.get("station", "未知站房")
                if station not in stations:
                    stations[station] = []
                stations[station].append(equipment)
            
            for i, (station_name, equipments) in enumerate(stations.items()):
                # 站房标题
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                            color: white; 
                            padding: 15px 20px; 
                            border-radius: 12px; 
                            margin: 20px 0 15px 0;
                            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
                    <h4 style="margin: 0; font-size: 1.2rem; font-weight: 700;">
                        🏭 {station_name}
                    </h4>
                </div>
                """, unsafe_allow_html=True)
                    # 创建设备卡片 - 符合Figma设计
                if equipments:
                    for j, eq in enumerate(equipments):
                        # 设备状态颜色
                        status = eq.get("runningStatus", "未知")
                        if status == "运行":
                            status_color = "#4CAF50"
                            status_bg = "#e8f5e8"
                        elif status == "备用":
                            status_color = "#FF9800"
                            status_bg = "#fff3e0"
                        else:
                            status_color = "#9E9E9E"
                            status_bg = "#f5f5f5"
                        
                        st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%); 
                                    border: 1px solid #e9ecef; 
                                    border-radius: 12px; 
                                    padding: 20px; 
                                    margin-bottom: 15px;
                                    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                                    transition: all 0.3s ease;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                                <h5 style="color: #2c3e50; font-size: 1.1rem; font-weight: 700; margin: 0;">
                                    {eq.get("equipmentNumber", "未知设备")}
                                </h5>
                                <span style="background: {status_bg}; 
                                             color: {status_color}; 
                                             padding: 6px 12px; 
                                             border-radius: 20px; 
                                             font-size: 12px; 
                                             font-weight: 700;">
                                    {status}
                                </span>
                            </div>
                            
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                                <div>
                                    <div style="color: #6c757d; font-size: 12px; font-weight: 600; margin-bottom: 4px;">品牌型号</div>
                                    <div style="color: #2c3e50; font-weight: 600;">{eq.get("brand", "未知")} {eq.get("model", "")}</div>
                                </div>
                                <div>
                                    <div style="color: #6c757d; font-size: 12px; font-weight: 600; margin-bottom: 4px;">设备类型</div>
                                    <div style="color: #2c3e50; font-weight: 600;">{eq.get("equipmentType", "未知")}</div>
                                </div>
                                <div>
                                    <div style="color: #6c757d; font-size: 12px; font-weight: 600; margin-bottom: 4px;">铭牌功率</div>
                                    <div style="color: #2c3e50; font-weight: 600;">{eq.get("ratedPower", "未知")} kW</div>
                                </div>
                                <div>
                                    <div style="color: #6c757d; font-size: 12px; font-weight: 600; margin-bottom: 4px;">铭牌流量</div>
                                    <div style="color: #2c3e50; font-weight: 600;">{eq.get("ratedFlow", "未知")} m³/min</div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="background: #f8f9fa; 
                                border: 1px solid #e9ecef; 
                                border-radius: 12px; 
                                padding: 20px; 
                                text-align: center;
                                color: #6c757d;">
                        该站房暂无设备信息
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background: #f8f9fa; 
                        border: 1px solid #e9ecef; 
                        border-radius: 12px; 
                        padding: 30px; 
                        text-align: center;
                        color: #6c757d;">
                <div style="font-size: 2rem; margin-bottom: 15px;">📦</div>
                <div style="font-weight: 600; font-size: 1.1rem;">未检测到设备信息</div>
                <div style="font-size: 0.9rem; margin-top: 8px;">请检查调研表中的设备清单部分</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

    # 根据模块类型显示不同的问题列表
    if st.session_state.module_type == 'air_conditioner':
        # 空调模块的问题列表显示
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
    else:
        # 空压机模块的问题列表显示 - 已在数据完整度卡片中显示，这里不重复显示
        pass

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

    # 提供确认按钮进入下一阶段 - 符合Figma设计
    if st.session_state.module_type == 'air_compressor':
        st.markdown("""
        <div style="margin: 40px auto; max-width: 900px; text-align: center;">
        """, unsafe_allow_html=True)
        
        if st.button("✅ 确认，进行下一步", type="primary", use_container_width=True):
            st.session_state.stage = 'filling'
            st.session_state.scroll_to_top = True
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("---")
        if st.button("✅ 确认，进行下一步", type="primary", use_container_width=True):
            st.session_state.stage = 'filling'
            st.session_state.scroll_to_top = True
            st.rerun()



def render_filling_stage():
    """阶段 3: 填充建议 (需要用户确认)"""
    if st.session_state.module_type == 'air_conditioner':
        st.header("🔧 步骤 3: 数据填充建议")
    else:
        st.markdown("## 步骤 3：节能测算")

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

                # 根据模块类型选择不同的技能
                if st.session_state.module_type == 'air_conditioner':
                    skill_name = "suggest-data-filling"
                else:
                    skill_name = "suggest-air-compressor-data-filling"
                    
                # 调用 Skill 3: 填充建议，传递回调
                skill_result = caller.call_skill(
                    skill_name,
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
            if st.session_state.module_type == 'air_conditioner':
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
                # 空压机模块的填充建议显示
                st.success(f"✅ 生成了 {len(fillable)} 个智能填充建议")
                
                st.markdown("### 📝 填充建议详情")
                
                # 使用卡片式布局显示填充建议
                for i, s in enumerate(fillable):
                    field_name = s.get("field", "未知字段")
                    original_value = s.get("original_value") or "缺失"
                    suggested_value = s.get("suggested_value", "")
                    method = s.get("method", "")
                    confidence = s.get("confidence", "")
                    reasoning = s.get("reasoning", "")
                    
                    st.markdown(f"""
                    <div style="background-color: #f8f9fa; padding: 16px; border-radius: 10px; 
                                border: 1px solid #e0e0e0; margin-bottom: 12px;">
                        <div style="font-weight: bold; color: #333; margin-bottom: 8px;">
                            📊 {field_name}
                        </div>
                        <div style="display: flex; gap: 20px; margin-bottom: 8px;">
                            <div>
                                <span style="color: #666; font-size: 12px;">原始值:</span><br>
                                <span style="color: #e74c3c;">{original_value}</span>
                            </div>
                            <div>
                                <span style="color: #666; font-size: 12px;">建议值:</span><br>
                                <span style="color: #27ae60; font-weight: bold;">{suggested_value}</span>
                            </div>
                            <div>
                                <span style="color: #666; font-size: 12px;">置信度:</span><br>
                                <span style="color: #3498db;">{confidence}</span>
                            </div>
                        </div>
                        <div style="color: #666; font-size: 14px;">
                            <strong>推理说明:</strong> {reasoning}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
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
    if st.session_state.module_type == 'air_conditioner':
        st.header("⚙️ 步骤 4: 执行计算")
    else:
        st.markdown("## 步骤 4：输出结果")

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

        if st.session_state.module_type == 'air_conditioner':
            # 使用气象数据服务（空调需要）
            weather_service = WeatherService()
            calculator = ExcelCalculator(weather_service=weather_service)  # 不传 template_path，自动根据 station_type 选择

            result_path = calculator.calculate(
                filled_path,
                str(session_dir / "result_data.json")
            )
        else:
            # 空压机计算逻辑 - 使用新的计算skill
            print("🔢 [空压计算] 调用空压机节能计算skill...")
            
            # 调用空压机节能计算skill
            calc_caller = SkillCaller(timeout=300)
            calc_result = calc_caller.call_skill(
                "calculate-air-compressor-energy-saving",
                filled_path,
                str(session_dir / "result_data.json")
            )
            
            result_path = str(session_dir / "result_data.json")

        # 读取结果
        with open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        # 保存格式化结果
        if st.session_state.module_type == 'air_conditioner':
            formatted_result = calculator.format_export_results(filled_data, result)
            with open(session_dir / "formatted_result.json", 'w', encoding='utf-8') as f:
                json.dump(formatted_result, f, ensure_ascii=False, indent=2)
        else:
            # 空压机模块直接使用计算结果
            with open(session_dir / "formatted_result.json", 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

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

    if st.session_state.module_type == 'air_conditioner':
        st.header("📈 测算结果")
    else:
        st.markdown("## 📈 测算结果")

    result = st.session_state.result

    if not result:
        st.error("❌ 未找到计算结果")
        if st.button("🔄 重新开始", use_container_width=True):
            reset_flow()
            st.rerun()
        return

    # 核心指标卡
    st.subheader("🎯 核心指标")

    # 根据模块类型显示不同的核心指标
    if st.session_state.module_type == 'air_conditioner':
        # 空调模块的核心指标展示
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

        # 分项节能明细 - 空调
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
    else:
        # 空压机模块的核心指标展示
        # 检查是否为范围计算结果
        if "energy_saving_rate_range" in result:
            # 展示范围
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
                # 添加总节能量范围
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
            # 单一值
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                rate = result.get("energy_saving_rate", 0)
                rate_min = result.get("energy_saving_rate_min", 0)
                rate_max = result.get("energy_saving_rate_max", 0)

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
                total_saving = result.get("energy_saving", 0) / 10000  # 转换为万 kWh
                st.metric("总节能量", f"{total_saving:.2f} 万 kWh")

            with col3:
                completeness = result.get("completeness", 0)
                st.metric("数据完整度", f"{completeness * 100:.1f}%")

            with col4:
                filled_count = result.get("filled_count", 0)
                st.metric("填充字段数", filled_count)

        st.markdown("---")

        # 分项节能明细 - 空压机
        st.subheader("📊 系统能耗分析")
        
        # 显示空压机系统的能耗分析
        current_energy = result.get("current_total_energy", 0) / 10000  # 转换为万 kWh
        optimized_energy = result.get("optimized_total_energy", 0) / 10000  # 转换为万 kWh
        energy_saving = result.get("energy_saving", 0) / 10000  # 转换为万 kWh
        
        energy_data = {
            "项目": ["当前系统年能耗", "优化后系统年能耗", "年节能量"],
            "数值 (万 kWh)": [current_energy, optimized_energy, energy_saving]
        }
        
        df_energy = pd.DataFrame(energy_data)
        st.dataframe(df_energy, use_container_width=True, hide_index=True)
        
        # 设备分析
        if "equipment_analysis" in result:
            st.subheader("🔧 设备分析")
            analysis = result["equipment_analysis"]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("空压机总台数", analysis.get("total_air_compressors", 0))
            with col2:
                st.metric("总装机功率 (kW)", f"{analysis.get('total_power', 0):.1f}")
            with col3:
                st.metric("平均效率", f"{analysis.get('average_efficiency', 0) * 100:.1f}%")
            
            # 设备类型分布
            if analysis.get("equipment_types"):
                st.subheader("设备类型分布")
                types_df = pd.DataFrame(
                    list(analysis["equipment_types"].items()),
                    columns=["设备类型", "数量"]
                )
                st.dataframe(types_df, use_container_width=True, hide_index=True)

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
    if result.get("calculation_method") == "dual_sheet" or result.get("calculation_method") == "air_compressor_standard":
        st.info(
            "📊 **节能率范围说明**\n\n"
            "- **下限（保守估计）**: 基于常规优化参数，考虑实际约束\n"
            "- **上限（理想情况）**: 基于最优运行条件，理想化假设\n"
            "- **实际节能效果**: 通常在此范围内，具体取决于项目实施情况"
        )

    st.markdown("---")

    # 下载区域
    st.subheader("📥 下载计算结果")
    
    if st.session_state.module_type == 'air_conditioner':
        # 空调模块的下载内容
        # 下载简化版 Excel 表格
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
                file_name=f"简化版空调节能测算结果_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
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
                        file_name=f"空调节能率计算结果_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                else:
                    st.warning("⚠️ Excel 文件未找到")
            else:
                st.error("❌ 密码错误，请联系管理员")
    else:
        # 空压机模块的下载内容
        st.subheader("📥 下载空压机节能方案")
        
        # 下载空压系统数智化升级方案
        st.info("**空压系统数智化升级方案**：包含节能分析、优化建议和投资回报分析")
        
        # 下载报价单
        session_dir = st.session_state.session_dir
        quotation_files = list(session_dir.glob("空压系统报价单_*.xlsx"))
        
        if quotation_files:
            quotation_file = quotation_files[0]
            with open(quotation_file, "rb") as f:
                quotation_data = f.read()
            
            st.download_button(
                label="📥 下载空压系统报价单",
                data=quotation_data,
                file_name=quotation_file.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.warning("⚠️ 报价单文件未找到")

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