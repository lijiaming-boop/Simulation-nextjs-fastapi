"""生成 AI设备铭牌自动识别 实施计划 Word 文档"""
import os
import datetime
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

# --- Style setup ---
style = doc.styles['Normal']
font = style.font
font.name = 'Microsoft YaHei'
font.size = Pt(11)
style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

# Chinese heading names for built-in styles
# We'll use add_heading directly (it works fine)

def add_heading_styled(doc, text, level):
    heading = doc.add_heading(text, level=level)
    for run in heading.runs:
        run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
    return heading

def add_para(doc, text, bold=False, size=11):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    return p

def add_code_block(doc, code_text):
    p = doc.add_paragraph()
    run = p.add_run(code_text)
    run.font.name = 'Consolas'
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    p.paragraph_format.left_indent = Cm(0.8)
    pf = p.paragraph_format
    pf.space_before = Pt(3)
    pf.space_after = Pt(3)
    shading_elm = OxmlElement('w:shd')
    shading_elm.set(qn('w:fill'), 'F0F0F0')
    shading_elm.set(qn('w:val'), 'clear')
    p.paragraph_format.element.get_or_add_pPr().append(shading_elm)
    return p

# ===== Cover =====
doc.add_paragraph()
doc.add_paragraph()
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('冷站性能仿真 — AI设备铭牌自动识别\n实施计划文档')
run.bold = True
run.font.size = Pt(26)
run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run('基于 DeepSeek V4 大模型的设备参数自动提取')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

doc.add_paragraph()
meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
today_str = datetime.date.today().strftime("%Y-%m-%d")
run = meta.add_run(f'文档版本: v1.0\n日期: {today_str}\n项目: conditioner_saving')
run.font.size = Pt(11)
run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

doc.add_page_break()

# ===== TOC =====
add_heading_styled(doc, '目  录', 1)
toc_items = [
    ('1. 需求概述', True),
    ('    1.1 问题描述', False),
    ('    1.2 目标', False),
    ('    1.3 范围说明', False),
    ('2. 现状分析', True),
    ('    2.1 当前架构总览', False),
    ('    2.2 现有 AI 服务模块', False),
    ('    2.3 当前数据流', False),
    ('    2.4 已有功能 vs 目标功能对比', False),
    ('3. 技术方案', True),
    ('    3.1 方案总览', False),
    ('    3.2 方案 A：通过代理网关接入（推荐）', False),
    ('    3.3 方案 B：直连 DeepSeek API（备选）', False),
    ('    3.4 方案对比与建议', False),
    ('4. 详细实施步骤', True),
    ('    4.1 第一步：ai_service.py — DeepSeek 客户端适配', False),
    ('    4.2 第二步：simulation_ui.py — UI 交互增强', False),
    ('    4.3 第三步：Prompt 工程优化', False),
    ('    4.4 第四步：容错与降级处理', False),
    ('    4.5 第五步：辅助函数完善', False),
    ('    4.6 第六步：配置文件更新', False),
    ('    4.7 第七步：测试验证', False),
    ('5. 需要修改的文件清单', True),
    ('6. 测试计划', True),
    ('7. 风险与应对', True),
    ('8. 实施排期', True),
]
for item_text, is_bold in toc_items:
    p = doc.add_paragraph()
    run = p.add_run(item_text)
    run.font.size = Pt(11)
    if is_bold:
        run.bold = True

doc.add_page_break()

# ===== 1. 需求概述 =====
add_heading_styled(doc, '1. 需求概述', 1)

add_heading_styled(doc, '1.1 问题描述', 2)
add_para(doc, '当前冷站性能仿真模块（simulation_ui.py）中，"主机COP性能曲线"部分的设备参数（主机名称、台数、单台制冷量、单台额定功率、额定COP、是否变频）需要用户逐个手动填入。当有多组主机（如1~6组）时，用户需要反复展开每个 expander 并手动填写，操作繁琐、效率低下。')

add_heading_styled(doc, '1.2 目标', 2)
add_para(doc, '利用 DeepSeek V4 大模型的多模态视觉能力，用户只需：')
items = [
    '上传设备铭牌照片/设备清单图片（支持多张），或粘贴设备参数文本；',
    '点击"AI识别并填入参数"按钮，系统自动提取所有设备参数；',
    '参数自动填入表单，用户可人工核对和修改（当前已有的预填机制）；',
    '大幅减少手动输入工作，提升使用体验。',
]
for item in items:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(item)

add_heading_styled(doc, '1.3 范围说明', 2)
add_para(doc, '本次改造仅涉及 simulation/ai_service.py 的后端模型适配和 simulation_ui.py 的前端交互优化，不涉及仿真引擎（simulator.py）、图表生成（chart_generator.py）、报告生成（report_generator.py）等模块的修改。')

doc.add_page_break()

# ===== 2. 现状分析 =====
add_heading_styled(doc, '2. 现状分析', 1)

add_heading_styled(doc, '2.1 当前架构总览', 2)
add_para(doc, '项目采用 Streamlit + Claude Agent SDK + 代理网关的三层架构：')

table = doc.add_table(rows=4, cols=3)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
headers = ['层级', '组件', '说明']
for i, h in enumerate(headers):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
data = [
    ['前端', 'simulation_ui.py (Streamlit)', 'UI渲染、文件上传、参数表单、AI识别按钮'],
    ['AI服务层', 'simulation/ai_service.py', '封装 AI 调用逻辑、prompt构建、响应解析'],
    ['模型网关', 'ANTHROPIC_BASE_URL 代理', '.env配置，协议转换，当前转发到 gpt-5.4'],
]
for r, row_data in enumerate(data):
    for c, val in enumerate(row_data):
        table.rows[r+1].cells[c].text = val

doc.add_paragraph()

add_heading_styled(doc, '2.2 现有 AI 服务模块', 2)
add_para(doc, '文件: simulation/ai_service.py (共150行)', bold=True)

add_para(doc, '当前实现包含两个函数：')
p = doc.add_paragraph(style='List Bullet')
run = p.add_run('ai_extract_plant_topology(content, content_type, image_data, media_type) → dict')
run.bold = True
add_para(doc, '    功能：接收文本或图片输入，调用 AI 返回结构化设备参数 JSON。支持两种输入模式：content_type="text"（纯文本/表格描述）和 content_type="image"（图片+可选文本，如铭牌照片）。输出格式：{chillers, chw_pumps, cw_pumps, towers, monthly_chiller_count, base_load_ratio, region}')

p = doc.add_paragraph(style='List Bullet')
run = p.add_run('ai_generate_simulation_report(summary, config_desc) → str')
run.bold = True
add_para(doc, '    功能：基于仿真结果生成 Markdown 格式的专业分析报告。')

add_para(doc, '当前客户端初始化逻辑：')
add_code_block(doc, '''def _get_client():
    """获取 Anthropic 客户端，显式传入 key 和 base_url"""
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return anthropic.Anthropic(api_key=api_key, base_url=base_url)

def _get_model():
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")''')

doc.add_paragraph()

add_heading_styled(doc, '2.3 当前数据流', 2)
add_para(doc, '用户操作流程（当前）：')
steps = [
    '用户在 simulation_ui.py 中点击「上传图片」或「粘贴文本」',
    '点击"AI识别并填入参数"按钮 → 调用 ai_extract_plant_topology()',
    '函数读取图片字节 / 文本内容',
    '构造 Anthropic 格式的 messages（含 image source 或 text）',
    '通过 anthropic.Anthropic 客户端发送到代理网关',
    '代理网关转发到后端大模型（当前: gpt-5.4）',
    '解析大模型返回的 JSON → 存入 st.session_state.ai_extracted_topology',
    '前端表单用 ai_extracted_topology 预填各字段（名称/台数/制冷量/功率/COP/变频等）',
]
for i, step in enumerate(steps):
    p = doc.add_paragraph(style='List Number')
    p.add_run(step)

doc.add_paragraph()

add_heading_styled(doc, '2.4 已有功能 vs 目标功能对比', 2)

table = doc.add_table(rows=8, cols=3)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, h in enumerate(['功能项', '当前状态', '改造后目标']):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
rows_data = [
    ['上传铭牌图片', '已支持', '保持不变，需更好的 prompt'],
    ['AI识别设备参数', '已支持（gpt-5.4）', '切换为 DeepSeek V4'],
    ['自动填入主机组数', '已支持', '保持不变'],
    ['自动填入主机参数', '已支持（预填）', '改进识别准确率'],
    ['自动填入辅机参数', '已支持', '保持不变'],
    ['自动填入月度运行参数', '已支持', '保持不变'],
    ['人工手动修改', '已支持', '保持不变'],
]
for r, row_data in enumerate(rows_data):
    for c, val in enumerate(row_data):
        table.rows[r+1].cells[c].text = val

doc.add_page_break()

# ===== 3. 技术方案 =====
add_heading_styled(doc, '3. 技术方案', 1)

add_heading_styled(doc, '3.1 方案总览', 2)
add_para(doc, '本项目当前已具备完整的 AI 识别 UI 和预填机制，核心改造点仅在于：')
items = [
    '后端大模型切换：从当前代理网关背后的 gpt-5.4 切换到 DeepSeek V4；',
    '协议适配：DeepSeek V4 兼容 OpenAI SDK 协议，需做 Anthropic → OpenAI 的消息格式转换；',
    'Prompt 优化：针对铭牌 OCR 和设备参数提取场景优化 prompt；',
    '容错增强：增强 JSON 解析的鲁棒性。',
]
for item in items:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(item)

add_heading_styled(doc, '3.2 方案 A：通过代理网关接入（推荐）', 2)
add_para(doc, '概述：', bold=True)
add_para(doc, '如果当前代理网关（http://61.29.254.79:4000）能够增加 DeepSeek V4 后端支持，则几乎无需修改代码。代理网关已承担 Anthropic 协议 → 后端模型协议的转换工作。')

add_para(doc, '前提条件：', bold=True)
items = [
    '代理网关运维方能够新增 DeepSeek V4 作为可用后端；',
    'DeepSeek V4 支持多模态（图片+文本）输入，或代理网关能传递图片给 DeepSeek；',
    'API Key 支持或新增 DeepSeek 的 key。',
]
for item in items:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(item)

add_para(doc, '实施步骤：', bold=True)
steps = [
    '与代理网关运维方确认是否支持 DeepSeek V4 后端；',
    '确认模型名称（如 deepseek-v4）；',
    '修改 .env : ANTHROPIC_MODEL=deepseek-v4（或网关约定的名称）；',
    '重启应用验证。',
]
for i, step in enumerate(steps):
    p = doc.add_paragraph(style='List Number')
    p.add_run(step)

add_para(doc, '优点：')
items = ['代码改动量 ≈ 0', '无需引入新 SDK 依赖', '模型切换透明，未来可灵活更换其他模型']
for item in items:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(item)

add_para(doc, '缺点：')
items = ['依赖代理网关运维方的配合和支持', 'DeepSeek V4 的多模态能力需通过代理网关的协议转换验证']
for item in items:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(item)

doc.add_paragraph()

add_heading_styled(doc, '3.3 方案 B：直连 DeepSeek API（备选）', 2)
add_para(doc, '概述：', bold=True)
add_para(doc, '绕过代理网关，直接在 ai_service.py 中使用 OpenAI SDK 直连 DeepSeek 官方 API。需做 Anthropic 到 OpenAI 的消息格式转换。')

add_para(doc, '核心改动点：', bold=True)

add_para(doc, '改动点 1：新增 DeepSeek 客户端工厂函数')
add_code_block(doc, '''# simulation/ai_service.py — 新增
import openai

def _get_deepseek_client():
    """获取 DeepSeek 客户端（兼容 OpenAI SDK）"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return openai.OpenAI(api_key=api_key, base_url=base_url)

def _get_deepseek_model():
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")  # DeepSeek V4''')

doc.add_paragraph()

add_para(doc, '改动点 2：消息格式转换函数')
add_code_block(doc, '''def _build_openai_vision_messages(content, content_type,
                                     image_data=None, media_type="image/jpeg",
                                     system_prompt=""):
    """将 Anthropic 格式的输入转换为 OpenAI Vision 格式"""
    import base64
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    user_content = []
    if content_type == "image" and image_data:
        b64 = base64.b64encode(image_data).decode()
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{b64}"}
        })
    if content:
        user_content.append({"type": "text", "text": content})
    messages.append({"role": "user", "content": user_content})
    return messages''')

doc.add_paragraph()

add_para(doc, '改动点 3：重写 ai_extract_plant_topology 的消息发送逻辑')
add_code_block(doc, '''def ai_extract_plant_topology(content, content_type="text",
                              image_data=None, media_type="image/jpeg"):
    try:
        client = _get_deepseek_client()  # ← 切换客户端
        messages = _build_openai_vision_messages(
            content, content_type, image_data, media_type, PLANT_TOPO_PROMPT
        )
        response = client.chat.completions.create(
            model=_get_deepseek_model(),   # ← 切换模型名
            max_tokens=3000,
            temperature=0.1,               # 低温度提高结构化输出稳定性
            messages=messages
        )
        text = response.choices[0].message.content  # ← 响应路径变更
        # JSON 解析逻辑见 4.4 节...
    except Exception as e:
        print(f"AI设备识别失败: {e}")
        return None''')

doc.add_paragraph()

add_para(doc, '改动点 4：重写 _ai_parse_cop_image（simulation_ui.py:424）')
add_para(doc, '将 COP 曲线图片识别的消息发送逻辑同步切换到 OpenAI 协议。建议将其逻辑合并到 ai_service.py，统一走 DeepSeek 客户端，避免代码分散。')

doc.add_paragraph()

add_para(doc, '改动点 5：重写 ai_generate_simulation_report')
add_para(doc, '该函数仅有纯文本输入（无图片），改动最简单——只需切换客户端和响应解析路径。')

doc.add_paragraph()

add_para(doc, '环境变量新增：')
add_code_block(doc, '''# .env 新增
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat''')

doc.add_page_break()

add_heading_styled(doc, '3.4 方案对比与建议', 2)

table = doc.add_table(rows=11, cols=3)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, h in enumerate(['对比维度', '方案 A (代理网关)', '方案 B (直连 DeepSeek)']):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
rows_data = [
    ['代码改动量', '约 0 行（仅改.env）', '约 80-120 行'],
    ['涉及文件数', '0（仅配置）', '2-3个文件'],
    ['新SDK依赖', '无', 'openai>=1.0.0（已安装）'],
    ['协议适配', '代理网关完成', '需自行编写转换函数'],
    ['对外部运维的依赖', '高（需网关方配合）', '无'],
    ['可维护性', '高（统一入口）', '中（双客户端并存）'],
    ['模型切换灵活性', '只需改配置', '需改代码'],
    ['调试难度', '低', '中'],
    ['JSON输出稳定性', '取决于网关+模型', '通过 temperature=0.1 控制'],
    ['推荐场景', '网关可支持DeepSeek时', '网关不支持DeepSeek时'],
]
for r, row_data in enumerate(rows_data):
    for c, val in enumerate(row_data):
        table.rows[r+1].cells[c].text = val

doc.add_paragraph()

p = doc.add_paragraph()
run = p.add_run('建议：优先尝试方案 A。如果代理网关无法支持 DeepSeek V4 或响应延迟过高，则采用方案 B。两个方案的 prompt 优化和容错处理是共通的，可并行推进。')
run.bold = True
run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)

doc.add_page_break()

# ===== 4. 详细实施步骤 =====
add_heading_styled(doc, '4. 详细实施步骤', 1)
add_para(doc, '以下步骤以方案 B（直连 DeepSeek）为主，方案 A 仅需第 6 步（配置更新）。')

# 4.1
add_heading_styled(doc, '4.1 第一步：ai_service.py — DeepSeek 客户端适配', 2)
add_para(doc, '目标：在 ai_service.py 中新增 DeepSeek 客户端支持，同时保留现有 Anthropic 客户端，通过环境变量 AI_PROVIDER 切换。')

add_para(doc, '具体操作：', bold=True)

add_para(doc, '1) 文件头部新增常量定义和 import：')
add_code_block(doc, '''import openai  # 新增（注意：openai>=1.0.0 已在 requirements.txt 中）

# 模型提供商选择（通过环境变量切换）
_AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic")  # "anthropic" | "deepseek"''')

add_para(doc, '2) 新增 DeepSeek 客户端工厂函数（约15行）：')
add_code_block(doc, '''def _get_deepseek_client():
    """获取 DeepSeek 客户端（兼容 OpenAI SDK）"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return openai.OpenAI(api_key=api_key, base_url=base_url)

def _get_deepseek_model():
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")''')

add_para(doc, '3) 新增消息格式转换函数（约25行）：')
add_code_block(doc, '''def _build_openai_vision_messages(content, content_type,
                                     image_data=None, media_type="image/jpeg",
                                     system_prompt=""):
    """构建 OpenAI Vision API 格式的消息列表
    输入：与现有 Anthropic 格式相同的参数
    输出：OpenAI Chat Completions 格式的 messages 列表"""
    import base64
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    user_content = []
    if content_type == "image" and image_data:
        b64 = base64.b64encode(image_data).decode()
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{b64}"}
        })
    if content:
        user_content.append({"type": "text", "text": content})
    messages.append({"role": "user", "content": user_content})
    return messages''')

add_para(doc, '4) 新增统一的 AI 调用适配器（约45行，是整个改造的核心）：')
add_code_block(doc, '''def _call_ai(prompt_text, system_prompt="",
             content_type="text", image_data=None, media_type="image/jpeg",
             max_tokens=3000, temperature=0.1):
    """统一的AI调用接口，根据 AI_PROVIDER 自动选择后端和协议"""
    if _AI_PROVIDER == "deepseek":
        # === DeepSeek 路径（OpenAI 协议）===
        client = _get_deepseek_client()
        messages = _build_openai_vision_messages(
            prompt_text, content_type, image_data, media_type, system_prompt
        )
        response = client.chat.completions.create(
            model=_get_deepseek_model(),
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages
        )
        return response.choices[0].message.content
    else:
        # === Anthropic 路径（现有逻辑，保持向后兼容）===
        client = _get_client()
        msg_content = []
        if content_type == "image" and image_data:
            import base64
            b64 = base64.b64encode(image_data).decode()
            msg_content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64}
            })
        msg_content.append({"type": "text", "text": prompt_text})
        response = client.messages.create(
            model=_get_model(),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": msg_content}]
        )
        return response.content[0].text''')

add_para(doc, '5) 修改 ai_extract_plant_topology()：')
add_para(doc, '将原来直接调用的 client.messages.create() 替换为 _call_ai()，prompt 作为参数传入。约改动15行。')

add_para(doc, '6) 修改 ai_generate_simulation_report()：')
add_para(doc, '同理替换为 _call_ai()。约改动10行。')

doc.add_paragraph()

# 4.2
add_heading_styled(doc, '4.2 第二步：simulation_ui.py — UI 交互增强', 2)
add_para(doc, '目标：优化"AI智能识别设备拓扑"的交互体验，使识别结果更透明、更易于手动修正。')

add_para(doc, '具体操作：', bold=True)

add_para(doc, '1) 增强按钮反馈（第50行附近，约改15行）：')
add_code_block(doc, '''if st.button("AI识别并填入参数", use_container_width=True, key="ai_extract_btn"):
    with st.spinner("AI正在分析设备信息..."):
        result = ai_extract_plant_topology(...)
        if result:
            n_ch = len(result.get("chillers", []))
            n_chw = len(result.get("chw_pumps", []))
            n_cw = len(result.get("cw_pumps", []))
            n_tw = len(result.get("towers", []))
            st.success(
                f"识别成功！检测到 {n_ch} 组主机、{n_chw} 组冷冻泵、"
                f"{n_cw} 组冷却泵、{n_tw} 组冷却塔"
            )
            st.session_state.ai_extracted_topology = result
            st.json(result)  # 显示识别结果供用户核对
        else:
            st.error("识别失败，请检查图片质量或尝试粘贴文本方式")''')

add_para(doc, '2) 参数预填逻辑优化（约改10行）：')
items = [
    '当 AI 识别到的 chiller_groups 数量 > 用户设置的 n_groups 时，自动调整 n_groups 数值',
    '对识别到的 COP 值做合理性校验（范围 3.0-10.0），超出范围的给出警告标签',
    '对制冷量做单位转换提示（如果检测到可能是冷吨 RT 而非 kW，给出提示）',
]
for item in items:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(item)

add_para(doc, '3) 将 _ai_parse_cop_image 函数中的 AI 调用改为使用 ai_service 的统一接口（约改10行）。')

doc.add_paragraph()

# 4.3
add_heading_styled(doc, '4.3 第三步：Prompt 工程优化', 2)
add_para(doc, '目标：针对设备铭牌 OCR 和设备参数提取场景，优化 AI prompt，提高识别准确率和 JSON 输出稳定性。')

add_para(doc, '优化后的 PLANT_TOPO_PROMPT（替换 ai_service.py 中原有的 prompt 字符串）：', bold=True)
add_code_block(doc, '''PLANT_TOPO_PROMPT = """你是一位暖通空调设备专家。请从上传的设备
铭牌照片/设备清单中精确提取冷站设备参数。

## 输出要求
严格输出JSON格式，不要Markdown代码块标记，不要其他任何文字：
{
  "chillers": [
    {"name": "主机型号", "qty": 台数(int),
     "capacity_kw": 制冷量kW(float),
     "rated_power_kw": 功率kW(float),
     "rated_cop": 额定COP(float),
     "variable_freq": true/false}
  ],
  "chw_pumps": [
    {"name": "型号", "qty": 台数, "power_kw": 功率,
     "flow_m3h": 流量, "variable_freq": true/false}
  ],
  "cw_pumps": [/* 同上 */],
  "towers": [
    {"name": "型号", "qty": 台数, "fan_power_kw": 风机功率,
     "fans_per_tower": 风机数, "variable_freq": true/false}
  ],
  "monthly_chiller_count": [1月台数,...,12月台数],
  "base_load_ratio": 0.70,
  "region": "华东/华南/华中/华北/西南/西北/东北"
}

## 识别规则（重要！）
1. 制冷量单位转换: 冷吨RT × 3.517 = kW
2. 变频判断: 铭牌含"变频/VFD/VSD/inverter"→true;
   含"工频/定频/fixed speed"→false
3. COP推导: 无标注时 COP=制冷量÷功率
4. 功率推导: 三相电机 功率≈电压×电流×1.732×0.85÷1000
5. 缺失值: 无法识别时用null，不要编造
6. 多台不同型号主机分别作为多个chiller组
7. 月度开机数: 按夏季多开、冬季少开合理推断
8. 仔细核对每个数字，小数点不要错位

## 铭牌常见关键词对照
- Cooling Capacity / 额定制冷量 / Nominal Capacity → 制冷量
- Power Input / 额定功率 / Rated Power / 输入功率 → 功率
- COP / EER / 能效比 → 性能系数
- Flow / 流量 / Rated Flow → 流量(m³/h)
"""''')

doc.add_paragraph()

# 4.4
add_heading_styled(doc, '4.4 第四步：容错与降级处理', 2)
add_para(doc, '目标：增强 JSON 解析的鲁棒性，处理 DeepSeek V4 可能输出非标准 JSON 的情况。')

add_para(doc, '在 ai_service.py 中新增多级 JSON 提取函数（约35行）：', bold=True)
add_code_block(doc, '''def _robust_extract_json(text: str) -> dict:
    """从 AI 返回文本中健壮地提取 JSON，支持4级容错"""
    import re
    text = text.strip()

    # 策略1: 直接解析（理想情况）
    try: return json.loads(text)
    except json.JSONDecodeError: pass

    # 策略2: 提取最外层 {} 之间的内容
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try: return json.loads(text[start:end])
        except json.JSONDecodeError: pass

    # 策略3: 移除 Markdown 代码块标记后重试
    clean = re.sub(r'```(?:json)?\\s*', '', text).replace("```", "")
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start >= 0 and end > start:
        try: return json.loads(clean[start:end])
        except json.JSONDecodeError: pass

    # 策略4: 尝试修复常见 JSON 格式问题
    if start >= 0 and end > start:
        json_str = text[start:end]
        json_str = re.sub(r',\\s*}', '}', json_str)   # 移除尾逗号
        json_str = re.sub(r',\\s*]', ']', json_str)
        try: return json.loads(json_str)
        except json.JSONDecodeError: pass

    return None  # 4级全部失败，返回None''')

doc.add_paragraph()

add_para(doc, '将 ai_extract_plant_topology() 中原有的简单 JSON 解析替换为 _robust_extract_json() 调用。')

doc.add_paragraph()

# 4.5
add_heading_styled(doc, '4.5 第五步：辅助函数完善', 2)
add_para(doc, '当前 _ai_parse_cop_image 函数（simulation_ui.py:424）直接使用 anthropic.Anthropic 客户端，需要同步改造。')

add_para(doc, '推荐方案：在 ai_service.py 中新增独立函数 ai_parse_cop_curve_image()，统一走 _call_ai() 接口：')
add_code_block(doc, '''def ai_parse_cop_curve_image(image_data: bytes,
                              media_type: str = "image/jpeg") -> dict:
    """AI识别COP性能曲线图片，返回 {load_ratio: cop_value}"""
    prompt = """请从这张COP性能曲线图/表格中提取数据点。
输出格式为每行：负载率百分比 COP值
例：
100 6.0
90 6.2
80 6.3
70 6.3
60 6.0
50 5.6
40 4.8
30 3.6
注意: 负载率按百分比(0-100)，COP保留1位小数，
仅输出数据，不要其他文字。"""
    try:
        text = _call_ai(
            prompt_text=prompt,
            system_prompt="你是精确的数据提取工具。",
            content_type="image",
            image_data=image_data,
            media_type=media_type,
            max_tokens=1000,
            temperature=0.0
        )
        from simulation.input_parser import parse_cop_curve_from_text
        return parse_cop_curve_from_text(text)
    except Exception as e:
        print(f"COP曲线识别失败: {e}")
        return None''')

add_para(doc, 'simulation_ui.py 中的 _ai_parse_cop_image() 简化为调用该函数。')

doc.add_paragraph()

# 4.6
add_heading_styled(doc, '4.6 第六步：配置文件更新', 2)

add_para(doc, '.env 文件更新（新增4行）：', bold=True)
add_code_block(doc, '''# ============ 现有配置（保留不动）============
ANTHROPIC_BASE_URL=http://61.29.254.79:4000
ANTHROPIC_API_KEY=REDACTED
ANTHROPIC_MODEL=gpt-5.4

# ============ 新增：AI提供商选择 ============
AI_PROVIDER=deepseek

# ============ 新增：DeepSeek API 配置 ============
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat''')

add_para(doc, '.env.example 文件同步更新，增加 DeepSeek 配置模板（含注释说明）。', bold=True)

doc.add_paragraph()

# 4.7
add_heading_styled(doc, '4.7 第七步：测试验证', 2)
add_para(doc, '详见第6节「测试计划」。')

doc.add_page_break()

# ===== 5. 需要修改的文件清单 =====
add_heading_styled(doc, '5. 需要修改的文件清单', 1)

add_para(doc, '方案 A（代理网关接入）：', bold=True)
table = doc.add_table(rows=2, cols=4)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, h in enumerate(['文件', '改动类型', '改动量', '说明']):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
table.rows[1].cells[0].text = '.env'
table.rows[1].cells[1].text = '配置修改'
table.rows[1].cells[2].text = '1行'
table.rows[1].cells[3].text = '修改 ANTHROPIC_MODEL 值为网关约定的DeepSeek模型名'

doc.add_paragraph()

add_para(doc, '方案 B（直连 DeepSeek API）：', bold=True)
table = doc.add_table(rows=6, cols=4)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, h in enumerate(['文件', '改动类型', '改动量', '核心内容']):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
rows_data = [
    ['simulation/ai_service.py', '核心改动', '约120行',
     '新增 import openai; 新增客户端工厂函数(15行); '
     '消息格式转换(25行); 统一调用适配器(45行); '
     'JSON容错解析(35行); 重写3个AI函数(30行)'],
    ['simulation_ui.py', '小幅改动', '约30行',
     'AI按钮反馈增强(15行); 参数预填优化(10行); '
     '_ai_parse_cop_image改用统一接口(5行)'],
    ['.env', '配置新增', '4行', '新增 AI_PROVIDER + DEEPSEEK_API_KEY/BASE_URL/MODEL'],
    ['.env.example', '配置模板', '6行', '同步新增 DeepSeek 配置模板及注释'],
    ['requirements.txt', '无需改动', '0行', 'openai>=1.0.0 已在依赖中无需额外添加'],
]
for r, row_data in enumerate(rows_data):
    for c, val in enumerate(row_data):
        table.rows[r+1].cells[c].text = val

add_para(doc, '总计改动量：约150行代码 + 10行配置，涉及2个源文件 + 2个配置文件。', bold=True)

doc.add_page_break()

# ===== 6. 测试计划 =====
add_heading_styled(doc, '6. 测试计划', 1)

add_heading_styled(doc, '6.1 单元测试', 2)
add_para(doc, '新增测试文件: tests/unit/test_ai_service_deepseek.py', bold=True)

test_cases = [
    ['_robust_extract_json', '策略1-标准JSON', '{"chillers":[],"region":"华东"}', '正确解析返回dict'],
    ['_robust_extract_json', '策略2-带额外文字', '识别结果如下：{"chillers":[]}谢谢', '正确解析'],
    ['_robust_extract_json', '策略3-Markdown代码块', '```json\\n{"chillers":[]}\\n```', '正确解析'],
    ['_robust_extract_json', '策略4-尾逗号', '{"chillers":[],}', '容错修复后正确解析'],
    ['_robust_extract_json', '全部失败-非法输入', '"这不是JSON"', '返回None不抛异常'],
    ['_build_openai_vision_messages', '纯文本模式', 'content="测试设备", content_type="text"', '构建含user text的消息列表'],
    ['_build_openai_vision_messages', '图片+文本', 'content="描述", image_data=mock_bytes', '构建含image_url+text的消息'],
    ['_build_openai_vision_messages', '带system_prompt', 'system_prompt="你是专家"', 'system消息排在messages[0]位置'],
]

table = doc.add_table(rows=len(test_cases)+1, cols=4)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, h in enumerate(['测试函数', '测试场景', '输入', '预期结果']):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
for r, row_data in enumerate(test_cases):
    for c, val in enumerate(row_data):
        table.rows[r+1].cells[c].text = val

doc.add_paragraph()

add_heading_styled(doc, '6.2 集成测试（手动，通过 Streamlit 界面）', 2)

test_items = [
    ('测试1-纯文本识别',
     '粘贴设备参数文本 → 点击AI识别 → 验证表单自动填入的数值与文本描述一致'),
    ('测试2-铭牌图片识别',
     '上传清晰的冷水机组铭牌照片 → AI识别 → 验证制冷量/功率/COP等参数提取准确'),
    ('测试3-设备清单图片',
     '上传设备清单截图 → AI识别 → 验证多组不同型号主机的识别结果'),
    ('测试4-模糊图片降级',
     '上传低质量/模糊/倾斜的图片 → 观察是否给出合理的错误提示'),
    ('测试5-手动修改',
     'AI识别后手动修改部分参数 → 确认修改在后续仿真中生效'),
    ('测试6-完整流程',
     'AI识别→手动核对→填写辅机→开始仿真→验证仿真结果COPs和节能率合理'),
    ('测试7-COP曲线图片',
     '上传COP性能曲线图 → AI识别 → 验证负载率-COP数据点提取正确'),
    ('测试8-后端切换',
     'AI_PROVIDER=anthropic → 验证原路径仍可用; '
     'AI_PROVIDER=deepseek → 验证新路径正常工作'),
]
for title, desc in test_items:
    p = doc.add_paragraph(style='List Number')
    run = p.add_run(title + '：')
    run.bold = True
    p.add_run(desc)

doc.add_paragraph()

add_heading_styled(doc, '6.3 回归测试', 2)
items = [
    '空调模块（air_conditioner）的 AI Skills 调用不受影响：pytest tests/ 全量通过',
    '空压机模块（air_compressor）的 AI Skills 调用不受影响',
    '仿真引擎（simulator.py）相同输入 → 相同输出（确定性验证）',
    '运行现有单元测试：pytest tests/unit/ 全部通过',
    '运行现有集成测试：pytest tests/integration/ 全部通过',
]
for item in items:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(item)

doc.add_page_break()

# ===== 7. 风险与应对 =====
add_heading_styled(doc, '7. 风险与应对', 1)

risks = [
    ['DeepSeek V4识别准确率不达标',
     '中',
     '铭牌照片模糊/反光/倾斜导致 OCR 准确率低',
     '1. 前端增加图片质量提示（建议清晰、正面拍摄）\n'
     '2. 所有AI识别结果均可手动修改（已实现）\n'
     '3. 保留文本粘贴输入作为备选方案\n'
     '4. 对关键参数做合理性范围校验'],
    ['JSON输出格式不稳定',
     '中',
     'DeepSeek V4 无原生 JSON Mode，可能输出非标准 JSON',
     '1. 使用低 temperature (0.1) 提高稳定性\n'
     '2. 实现4级JSON容错解析（详见4.4节）\n'
     '3. 解析失败时提示用户重试，不静默失败'],
    ['API调用延迟',
     '低',
     'DeepSeek API 响应时间可能超过用户等待耐心',
     '1. UI使用st.spinner显示加载动画\n'
     '2. 设置合理的超时时间(60s)\n'
     '3. 大文件图片自动压缩后再上传'],
    ['API调用费用',
     '低',
     '高频使用可能产生较多 API 调用费用',
     '1. DeepSeek定价远低于Anthropic/OpenAI\n'
     '2. 用户每次手动点击才触发调用，非自动\n'
     '3. 可考虑添加简单的调用计数统计'],
    ['向后兼容性',
     '低',
     '改造后原有 Anthropic 路径可能需要保留',
     '1. AI_PROVIDER环境变量保留双后端\n'
     '2. 设为anthropic即可切回原路径\n'
     '3. 单元测试覆盖两个路径'],
    ['代理网关不可用（仅方案A）',
     '低',
     '代理网关故障则整个AI识别功能不可用',
     '1. 方案B作为后备方案已就绪\n'
     '2. 双后端支持确保高可用'],
]

table = doc.add_table(rows=len(risks)+1, cols=4)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, h in enumerate(['风险项', '等级', '触发条件', '应对措施']):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
for r, row_data in enumerate(risks):
    for c, val in enumerate(row_data):
        table.rows[r+1].cells[c].text = val

doc.add_page_break()

# ===== 8. 实施排期 =====
add_heading_styled(doc, '8. 实施排期', 1)

schedule = [
    ['第1天（上午）', '方案确认 + 环境准备', '2h',
     '确认代理网关能力；申请DeepSeek API Key；配置.env环境变量'],
    ['第1天（下午）', 'ai_service.py 改造', '4h',
     '新增DeepSeek客户端工厂函数(15行); 消息格式转换函数(25行); '
     '统一调用适配器 _call_ai()(45行); JSON容错解析 _robust_extract_json()(35行)'],
    ['第2天（上午）', 'simulation_ui.py 改造', '2h',
     'AI按钮反馈增强(15行); 参数预填优化(10行); '
     '_ai_parse_cop_image 切换统一接口(5行)'],
    ['第2天（上午）', 'Prompt 工程优化', '2h',
     '优化设备识别 PLANT_TOPO_PROMPT; 优化COP曲线识别prompt; '
     '准备测试用铭牌图片验证提取效果'],
    ['第2天（下午）', '容错与降级', '2h',
     '参数合理性校验（COP范围3-10; 功率>0; 制冷量>0）; '
     '空值/异常值降级策略; 友好错误提示优化'],
    ['第3天（上午）', '单元测试编写', '3h',
     'tests/unit/test_ai_service_deepseek.py: '
     '覆盖8个单元测试场景; 两个AI_PROVIDER路径的切换测试'],
    ['第3天（下午）\n~第4天（上午）', '集成测试与回归', '3h',
     '手动执行8项集成测试; '
     '回归测试: pytest tests/ 全量通过; '
     '性能测试: 记录API延迟和识别准确率'],
    ['第4天（下午）', '文档与交付', '1h',
     '更新CLAUDE.md的AI服务章节; '
     '更新README.md使用说明; 更新.env.example模板'],
]

table = doc.add_table(rows=len(schedule)+1, cols=4)
table.style = 'Light Grid Accent 1'
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, h in enumerate(['时间', '任务', '工时', '产出物/详细说明']):
    table.rows[0].cells[i].text = h
    for p in table.rows[0].cells[i].paragraphs:
        for run in p.runs:
            run.bold = True
for r, row_data in enumerate(schedule):
    for c, val in enumerate(row_data):
        table.rows[r+1].cells[c].text = val

doc.add_paragraph()

add_para(doc, '总计预估工时：约 19 小时（2~3 个工作日）', bold=True)
add_para(doc, '核心代码改动量：约 150 行（ai_service.py: ~120行 + simulation_ui.py: ~30行）')
add_para(doc, '前置依赖：DeepSeek API Key 已申请、代理网关方案已确认')

doc.add_paragraph()
doc.add_paragraph()

# Footer
footer = doc.add_paragraph()
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = footer.add_run('— 文档结束 —')
run.font.size = Pt(10)
run.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

# Save
output_dir = r'D:\pyprogram\conditioner_saving\conditioner_saving\docs\plans'
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'AI设备铭牌自动识别实施计划.docx')
doc.save(output_path)
print(f'文档已成功生成: {output_path}')
