"""冷站性能仿真模块 - Streamlit UI

支持两种场景:
1. 旧站房仿真 (从空调节能率计算结果页跳转, 有调研表历史工况)
2. 新站房仿真 (独立入口, 无调研表, 用户手动输入)

4步流程: 拓扑收集 → 性能曲线 → 工况需求 → 仿真执行
"""
import streamlit as st
import json
import time
from pathlib import Path
from core.skill_caller import SkillCaller, SkillError


# ==================== 辅助函数 ====================

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


def init_simulation_state():
    """初始化仿真模块 session state"""
    if 'sim_stage' not in st.session_state:
        st.session_state.sim_stage = 'topology'
        st.session_state.sim_mode = 'new_station'  # new_station / old_station
        st.session_state.sim_topology = None
        st.session_state.sim_cop_data = {}
        st.session_state.sim_operating_conditions = None
        st.session_state.sim_result = None
        st.session_state.sim_project_name = ''


def reset_simulation():
    """重置仿真流程"""
    st.session_state.sim_stage = 'topology'
    st.session_state.sim_topology = None
    st.session_state.sim_cop_data = {}
    st.session_state.sim_operating_conditions = None
    st.session_state.sim_result = None
    st.session_state.sim_project_name = ''


# ==================== 拓扑输入示例 ====================

TOPOLOGY_EXAMPLE = """冷水主机：
- 约克 YZ系列 3000RT 中温变频离心机 × 2台，额定制冷量10551kW，额定功率750kW，额定COP 6.5
- 约克 YZ系列 1800RT 低温变频离心机 × 1台，额定制冷量6331kW，额定功率480kW，额定COP 5.8

冷却泵：90kW × 4台，变频
冷冻泵：75kW × 3台 + 37kW × 2台，变频
冷却塔：45kW风机 × 12台，变频，闭式
特殊结构：无"""

OPERATING_EXAMPLE = """过渡季节(3-5月,10-11月)工作日开2台约克3000RT中温变频，75%负载
过渡季节休息日开1台约克1800RT低温变频，75%负载
冬季(12-2月)不开机
夏季(6-9月)工作日开3台3000RT中温变频，80%负载
夏季休息日开1台3000RT中温变频和1台1800RT低温变频，70%负载"""


# ==================== 主渲染函数 ====================

def render_simulation_module():
    """仿真模块主入口"""
    init_simulation_state()

    # 进度指示器
    sim_stages = ['拓扑信息', '性能曲线', '工况需求', '仿真执行']
    sim_stage_map = {'topology': 0, 'cop_curves': 1, 'operating': 2, 'simulate': 3}
    current = sim_stage_map.get(st.session_state.sim_stage, 0)

    cols = st.columns(len(sim_stages))
    for i, (col, name) in enumerate(zip(cols, sim_stages)):
        with col:
            if i < current:
                st.success(f"✅ {name}")
            elif i == current:
                st.info(f"▶️ {name}")
            else:
                st.text(f"⏸️ {name}")

    st.markdown("---")

    # 路由
    stage = st.session_state.sim_stage
    if stage == 'topology':
        render_topology_stage()
    elif stage == 'cop_curves':
        render_cop_curves_stage()
    elif stage == 'operating':
        render_operating_stage()
    elif stage == 'simulate':
        render_simulate_stage()


# ==================== Step 1: 拓扑信息收集 ====================

_INVALID_TEXT_PATTERNS = [
    "例如：", "示例:", "选填", "选框勾选", "是否", "有没有",
    "请注意", "举例", "需要让运维", "询问运维", "各设备铭牌",
    "描述一下", "客户", "末端", "该项目", "涉及", "整体情况",
    "运行规律", "特殊情况说明", "设备启停方式", "末端设备数量",
    "通讯接口", "供水温度", "运行台数", "运行频率", "出水温度",
    "工频运行则为", "变频运行可填写", "整个冷站", "填写大致的范围",
]


def _is_real_equipment(entry: dict) -> bool:
    """判断一条记录是否是真实设备数据，而不是调研表的说明文本"""
    brand = str(entry.get("brand", "") or "")
    model = str(entry.get("model", "") or "")

    # 如果 brand 太长（包含说明性文本），大概率不是设备数据
    if len(brand) > 40:
        return False

    # brand/model 包含常见调研表提示文本 → 不是设备数据
    combined = brand + model
    for pattern in _INVALID_TEXT_PATTERNS:
        if pattern in combined:
            return False

    # 至少有一个数值字段大于0 或 brand/model 是短文本
    capacity = entry.get("capacity_kw") or entry.get("额定制冷量") or entry.get("制冷量") or 0
    power = entry.get("power_kw") or entry.get("额定功率") or entry.get("功率") or 0
    cop = entry.get("rated_cop") or entry.get("COP") or entry.get("cop") or 0
    fan_power = entry.get("fan_power_kw") or entry.get("风机功率") or 0

    try:
        if float(capacity) > 0 or float(power) > 0 or float(cop) > 0 or float(fan_power) > 0:
            return True
    except (ValueError, TypeError):
        pass

    # brand/model 是合理的文本（品牌名、型号）
    if brand and model:
        return True
    if brand and len(brand) <= 20 and not any(p in brand for p in ["类型", "否", "是", "/"]):
        return True
    if model and len(model) <= 60:
        return True

    return False


def _normalize_topology(raw: dict) -> dict:
    """标准化 AI 输出的拓扑 JSON，兼容多种键名格式"""
    # 处理嵌套结构：AI 可能输出 {"source_file": ..., "topology": {...}, "notes": [...]}
    if "topology" in raw and isinstance(raw["topology"], dict):
        inner = raw["topology"]
        project_name = raw.get("project_name", inner.get("project_name", raw.get("项目名称", "未知项目")))
        raw = inner
    else:
        project_name = raw.get("project_name", raw.get("项目名称", "未知项目"))

    topology = {"project_name": project_name}

    # 冷水主机 - 兼容多种键名 + 过滤无效数据
    chillers = (
        raw.get("chillers") or raw.get("冷水主机") or raw.get("主机") or
        raw.get("chiller") or raw.get("冷水机组") or []
    )
    normalized_chillers = []
    for ch in chillers:
        if not isinstance(ch, dict):
            continue
        if not _is_real_equipment(ch):
            continue
        normalized_chillers.append({
            "brand": ch.get("brand", ch.get("品牌", "")) or "",
            "model": ch.get("model", ch.get("型号", "")) or "",
            "type": ch.get("type", ch.get("类型", "")) or "",
            "count": int(ch.get("count", ch.get("台数", ch.get("数量", 1))) or 1),
            "capacity_kw": float(ch.get("capacity_kw", ch.get("额定制冷量", ch.get("制冷量", ch.get("额定制冷量kW", 0)))) or 0),
            "power_kw": float(ch.get("power_kw", ch.get("额定功率", ch.get("功率", ch.get("额定功率kW", 0)))) or 0),
            "rated_cop": float(ch.get("rated_cop", ch.get("COP", ch.get("额定COP", ch.get("cop", 0)))) or 0),
            "vfd": ch.get("vfd", ch.get("变频", True)),
        })
    topology["chillers"] = normalized_chillers

    # === 后处理：纠正AI错误分类 ===
    # 如果 chillers 中有条目的 COP > 10，它很可能是水泵（被AI误分到了chillers）
    misclassified_pumps = []
    real_chillers = []
    for ch in normalized_chillers:
        cop = ch.get('rated_cop', 0)
        power = ch.get('power_kw', 0)
        capacity = ch.get('capacity_kw', 0)
        # 判断标准：COP > 10 或 (容量/功率) > 10 且 功率 <= 100kW
        computed_ratio = capacity / power if power > 0 else 0
        if cop > 10 or (computed_ratio > 10 and power <= 200):
            misclassified_pumps.append(ch)
        else:
            real_chillers.append(ch)

    topology["chillers"] = real_chillers

    # 将误分类的泵添加到 chilled_pumps
    extra_chilled_pumps = [
        {
            "power_kw": p.get("power_kw", 0),
            "count": p.get("count", 1),
            "vfd": p.get("vfd", True),
        }
        for p in misclassified_pumps
    ]

    # 冷却泵
    cooling_pumps = raw.get("cooling_pumps") or raw.get("冷却泵") or []
    topology["cooling_pumps"] = [
        {
            "power_kw": float(p.get("power_kw", p.get("功率", 0)) or 0),
            "count": int(p.get("count", p.get("台数", 1)) or 1),
            "vfd": p.get("vfd", p.get("变频", True)),
        }
        for p in cooling_pumps if isinstance(p, dict) and _is_real_equipment(p)
    ]

    # 冷冻泵（包含从 chillers 纠正过来的水泵）
    chilled_pumps = raw.get("chilled_pumps") or raw.get("冷冻泵") or []
    normalized_chilled = [
        {
            "power_kw": float(p.get("power_kw", p.get("功率", 0)) or 0),
            "count": int(p.get("count", p.get("台数", 1)) or 1),
            "vfd": p.get("vfd", p.get("变频", True)),
        }
        for p in chilled_pumps if isinstance(p, dict) and _is_real_equipment(p)
    ]
    # 合并纠正过来的水泵（避免重复）
    existing_powers = {p["power_kw"] for p in normalized_chilled}
    for ep in extra_chilled_pumps:
        if ep["power_kw"] not in existing_powers:
            normalized_chilled.append(ep)
    topology["chilled_pumps"] = normalized_chilled

    # 冷却塔
    towers = raw.get("towers") or raw.get("冷却塔") or []
    topology["towers"] = [
        {
            "fan_power_kw": float(t.get("fan_power_kw", t.get("风机功率", t.get("功率", 0))) or 0),
            "count": int(t.get("count", t.get("台数", 1)) or 1),
            "vfd": t.get("vfd", t.get("变频", True)),
            "type": t.get("type", t.get("类型", "开式")),
        }
        for t in towers if isinstance(t, dict) and _is_real_equipment(t)
    ]

    # 特殊结构
    special = raw.get("special") or raw.get("特殊结构") or {"type": "none"}
    if isinstance(special, dict):
        # 处理 features 列表格式
        features = special.get("features", [])
        if features and not special.get("type"):
            type_map = {"热回收": "heat_recovery", "蓄冷": "storage", "蓄冰": "ice"}
            for feat in features:
                if feat in type_map:
                    special["type"] = type_map[feat]
                    break
        sp_type = special.get("type", "none")
        # 清理 type 字段：如果包含垃圾文本，尝试关键词匹配
        if isinstance(sp_type, str) and len(sp_type) > 20:
            # 从长文本中提取关键词
            detected = []
            if "热回收" in sp_type:
                detected.append("heat_recovery")
            if "蓄冷" in sp_type or "蓄冰" in sp_type:
                detected.append("storage")
            if detected:
                sp_type = "_and_".join(detected) if len(detected) > 1 else detected[0]
            else:
                sp_type = "none"
        special["type"] = sp_type
    elif isinstance(special, str):
        special = {"type": special if len(special) <= 20 else "none"}
    else:
        special = {"type": "none"}
    topology["special"] = special

    return topology


def render_topology_stage():
    """Step 1: 站房拓扑信息收集"""
    st.header("📋 步骤 1: 站房拓扑信息收集")

    # 已有拓扑数据时展示编辑界面
    if st.session_state.sim_topology is not None:
        topology = st.session_state.sim_topology
        _display_topology(topology)
        st.session_state.sim_topology = topology  # 保存编辑后的数据

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 重新收集", use_container_width=True):
                st.session_state.sim_topology = None
                st.rerun()
        with col2:
            can_proceed = bool(topology.get('chillers'))
            if st.button("✅ 确认拓扑信息，进入下一步", type="primary",
                         use_container_width=True, disabled=not can_proceed):
                st.session_state.sim_stage = 'cop_curves'
                st.rerun()
        return

    sim_mode = st.session_state.sim_mode
    if sim_mode == 'old_station':
        _render_topology_old_station()
    else:
        _render_topology_new_station()


def _render_topology_old_station():
    """旧站房: 从调研表自动识别拓扑"""
    st.info("ℹ️ 将从已上传的调研表中自动识别站房设备拓扑信息")

    session_dir = st.session_state.session_dir
    upload_path = session_dir / "upload_survey.xlsx"

    # 如果没有调研表，提供上传入口
    if not upload_path.exists():
        st.warning("⚠️ 未找到调研表文件，请上传")
        uploaded_file = st.file_uploader("上传调研表", type=['xlsx', 'xls'], key="sim_survey_upload")
        if uploaded_file:
            with open(upload_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"✅ 文件已上传：{uploaded_file.name}")
            st.rerun()
        return

    st.success(f"✅ 调研表已就绪：{upload_path.name}")

    if st.button("🔍 开始识别设备拓扑", type="primary", use_container_width=True):
        _run_topology_extraction(upload_path)


def _render_topology_new_station():
    """新站房: 上传调研表或手动输入拓扑"""

    # 方式选择: 上传调研表 或 手动输入
    input_method = st.radio(
        "选择拓扑信息输入方式",
        ["📁 上传调研表（推荐）", "✍️ 手动输入"],
        horizontal=True
    )

    session_dir = st.session_state.session_dir

    if "上传调研表" in input_method:
        # 上传调研表方式
        st.info("ℹ️ 上传调研表后，AI 将自动识别站房设备拓扑信息")

        uploaded_file = st.file_uploader(
            "上传调研表",
            type=['xlsx', 'xls'],
            key="sim_survey_upload_new"
        )

        if uploaded_file:
            upload_path = session_dir / "upload_survey.xlsx"
            with open(upload_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"✅ 文件已上传：{uploaded_file.name}")

            if st.button("🔍 开始识别设备拓扑", type="primary", use_container_width=True):
                _run_topology_extraction(upload_path)
    else:
        # 手动输入方式
        _render_topology_manual_input()


def _render_topology_manual_input():
    """手动输入拓扑信息"""
    with st.expander("📝 查看填写示例", expanded=True):
        st.code(TOPOLOGY_EXAMPLE, language="text")

    # 项目名称
    project_name = st.text_input(
        "项目名称",
        value=st.session_state.sim_project_name,
        placeholder="如：德丽科技冷站"
    )

    # 拓扑输入
    topology_input = st.text_area(
        "设备拓扑信息",
        height=250,
        placeholder="请参照上方示例填写设备信息..."
    )

    if st.button("🔍 AI 解析拓扑信息", type="primary", use_container_width=True):
        if not topology_input.strip():
            st.warning("⚠️ 请先输入设备拓扑信息")
            return

        _, log_container = create_streaming_container("🤖 AI 正在解析拓扑信息...")
        streaming_logs = []

        def on_text(timestamp, text):
            streaming_logs.append(f"**[{timestamp}]** 灵知 AI：{text}")
            update_streaming_container(log_container, streaming_logs)

        try:
            caller = SkillCaller(timeout=180)
            session_dir = st.session_state.session_dir
            output_path = session_dir / "sim_topology.json"

            # 将用户输入保存
            input_path = session_dir / "sim_topology_input.txt"
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write(topology_input)

            prompt = (
                f"请将以下冷站设备拓扑描述解析为结构化 JSON，输出到 {output_path}。\n\n"
                f"用户输入：\n{topology_input}\n\n"
                f"项目名称：{project_name or '未知项目'}\n\n"
                f"输出 JSON 格式（必须使用英文键名）：\n"
                f'{{"project_name": "项目名称", "chillers": [{{"brand": "", "model": "", '
                f'"type": "", "count": 0, "capacity_kw": 0, "power_kw": 0, "rated_cop": 0}}], '
                f'"cooling_pumps": [{{"power_kw": 0, "count": 0, "vfd": true}}], '
                f'"chilled_pumps": [{{"power_kw": 0, "count": 0, "vfd": true}}], '
                f'"towers": [{{"fan_power_kw": 0, "count": 0, "vfd": true, "type": "闭式"}}], '
                f'"special": {{"type": "none"}}}}\n'
                f"同类设备按型号汇总台数。"
            )

            skill_result = caller.call_skill(
                "plant-simulation",
                str(input_path),
                str(output_path),
                "parse_topology",
                callback=on_text
            )

            if output_path.exists():
                with open(output_path, 'r', encoding='utf-8') as f:
                    raw_topology = json.load(f)
                topology = _normalize_topology(raw_topology)
                st.session_state.sim_topology = topology
                st.session_state.sim_project_name = topology.get('project_name', project_name)
                st.rerun()
            else:
                st.error("❌ 解析完成但未生成输出文件")

        except (SkillError, Exception) as e:
            st.error(f"❌ 解析失败：{str(e)}")


def _run_topology_extraction(upload_path: Path):
    """从调研表提取拓扑（共用逻辑）"""
    _, log_container = create_streaming_container("🤖 AI 正在识别设备拓扑...")
    streaming_logs = []

    def on_text(timestamp, text):
        streaming_logs.append(f"**[{timestamp}]** 灵知 AI：{text}")
        update_streaming_container(log_container, streaming_logs)

    try:
        caller = SkillCaller(timeout=300)
        session_dir = st.session_state.session_dir
        output_path = session_dir / "sim_topology.json"

        prompt = (
            f"你是一个暖通数据解析专家。请从调研表 Excel 文件中提取冷站设备拓扑信息。\n\n"
            f"## 文件路径\n"
            f"- 输入: {upload_path}\n"
            f"- 输出: {output_path}\n\n"
            f"## 解析步骤\n\n"
            f"### 第一步：读取 Excel 文件\n"
            f"用 openpyxl 读取 Excel，重点关注以下工作表：\n"
            f"- 名称包含“冷站”的 sheet：这里包含设备规格表\n"
            f"- 名称包含“项目总体情况”的 sheet：包含项目基本信息\n\n"
            f"### 第二步：在“冷站”sheet 中定位设备表\n"
            f"调研表的设备表格式通常是：\n"
            f"- 表头行包含列名如：类型、品牌、型号、台数、制冷量/kW、功率/kW、COP、变频/工频\n"
            f"- 设备分类可能包括：冷机、一次侧冷却泵、一次冷冻泵、二次冷冻泵、冷却塔\n"
            f"- 每个分类下面有多行数据，每行是一个设备型号\n\n"
            f"### 第三步：只提取真正的设备数据行\n"
            f"**必须提取的数据行特征**：\n"
            f"- 该行有具体的品牌名（如“约克”“特灵”“开利”“康迈斯”“元亨”等）\n"
            f"- 该行有具体的型号（如“YKWEPEP96CQH”等）\n"
            f"- 该行有数值型的制冷量/功率数据（如 3516、90、75、45 等）\n"
            f"- 该行有台数信息（如 1、2、3、4 等正整数）\n\n"
            f"**必须跳过的行**：\n"
            f"- 表头行（包含“类型”“品牌”“型号”等字样的行）\n"
            f"- 说明性文字（如“例如：”“示例：”“选填”等）\n"
            f"- 调研表问题文本（如“现场是否有上位机系统”“询问运维人员”等）\n"
            f"- 运行记录数据（如月度运行台数、供水温度等时间序列数据）\n"
            f"- 空行或合并单元格\n\n"
            f"### 第四步：输出 JSON\n"
            f"使用 Write 工具将解析结果写入 {output_path}，格式如下：\n"
            f"```json\n"
            f'{{\n'
            f'  "project_name": "项目名称",\n'
            f'  "chillers": [\n'
            f'    {{"brand": "约克", "model": "YKWEPEP96CQH", "type": "变频", "count": 2, "capacity_kw": 3516, "power_kw": 680, "rated_cop": 5.17, "vfd": true}}\n'
            f'  ],\n'
            f'  "cooling_pumps": [\n'
            f'    {{"power_kw": 90, "count": 4, "vfd": true}}\n'
            f'  ],\n'
            f'  "chilled_pumps": [\n'
            f'    {{"power_kw": 75, "count": 3, "vfd": true}}\n'
            f'  ],\n'
            f'  "towers": [\n'
            f'    {{"fan_power_kw": 45, "count": 12, "vfd": true, "type": "闭式"}}\n'
            f'  ],\n'
            f'  "special": {{"type": "none"}}\n'
            f'}}\n'
            f"```\n\n"
            f"## 重要约束\n"
            f"1. 必须用英文键名，不能用中文键名\n"
            f"2. capacity_kw/power_kw/rated_cop/fan_power_kw 必须是数字，不是 null\n"
            f"3. 同类设备如果型号相同，合并台数（如2台相同参数的冷机 → count: 2）\n"
            f"4. vfd 字段根据“变频”/“工频”判断，默认 true\n"
            f"5. 不要包含调研表的问题文本和说明性文字\n"
            f"6. special 字段如果调研表提到蓄冷/蓄冰/热回收，填入对应类型，否则 type 为 none\n"
        )

        skill_result = caller.call_skill(
            "plant-simulation",
            str(upload_path),
            str(output_path),
            "extract_topology",
            callback=on_text
        )

        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                raw_topology = json.load(f)
            topology = _normalize_topology(raw_topology)
            st.session_state.sim_topology = topology
            st.session_state.sim_project_name = topology.get('project_name', '未知项目')
            st.rerun()
        else:
            st.error("❌ 拓扑识别完成但未生成输出文件")

    except (SkillError, Exception) as e:
        st.error(f"❌ 拓扑识别失败：{str(e)}")


def _display_topology(topology: dict):
    """展示并编辑拓扑识别结果"""
    st.success("✅ 设备拓扑识别完成")

    # 项目名称可编辑
    topology['project_name'] = st.text_input(
        "项目名称", value=topology.get('project_name', '未知项目'), key="edit_project_name"
    )

    # === 冷水主机 ===
    chillers = topology.get('chillers', [])
    st.subheader(f"❄️ 冷水主机 ({len(chillers)} 条)")
    if chillers:
        with st.expander("展开编辑", expanded=True):
            to_delete_ch = []
            for idx, ch in enumerate(chillers):
                st.markdown(f"**--- 主机 #{idx+1} ---**")
                c1, c2, c3 = st.columns(3)
                with c1:
                    ch['brand'] = st.text_input("品牌", value=ch.get('brand', ''), key=f"ch_brand_{idx}")
                    ch['model'] = st.text_input("型号", value=ch.get('model', ''), key=f"ch_model_{idx}")
                with c2:
                    ch['capacity_kw'] = st.number_input("制冷量(kW)", min_value=0.0, value=float(ch.get('capacity_kw', 0) or 0), key=f"ch_cap_{idx}")
                    ch['power_kw'] = st.number_input("功率(kW)", min_value=0.0, value=float(ch.get('power_kw', 0) or 0), key=f"ch_pwr_{idx}")
                with c3:
                    ch['rated_cop'] = st.number_input("COP", min_value=0.0, value=float(ch.get('rated_cop', 0) or 0), step=0.01, key=f"ch_cop_{idx}")
                    ch['count'] = st.number_input("台数", min_value=1, value=int(ch.get('count', 1) or 1), key=f"ch_cnt_{idx}")
                ch['vfd'] = st.checkbox("变频", value=ch.get('vfd', True), key=f"ch_vfd_{idx}")
                ch['type'] = st.text_input("类型", value=ch.get('type', ''), key=f"ch_type_{idx}")
                if st.button("🗑️ 删除", key=f"ch_del_{idx}"):
                    to_delete_ch.append(idx)
            if to_delete_ch:
                topology['chillers'] = [c for i, c in enumerate(chillers) if i not in to_delete_ch]
                st.session_state.sim_topology = topology
                st.rerun()

    # 添加主机按钮
    if st.button("➡️ 添加冷水主机", key="add_chiller"):
        topology.setdefault('chillers', []).append({
            "brand": "", "model": "", "type": "", "count": 1,
            "capacity_kw": 0, "power_kw": 0, "rated_cop": 5.0, "vfd": True
        })
        st.session_state.sim_topology = topology
        st.rerun()

    # === 冷却泵 ===
    cooling_pumps = topology.get('cooling_pumps', [])
    st.subheader(f"🔄 冷却泵 ({len(cooling_pumps)} 条)")
    if cooling_pumps:
        with st.expander("展开编辑"):
            to_delete_cp = []
            for idx, p in enumerate(cooling_pumps):
                c1, c2, c3 = st.columns(3)
                with c1:
                    p['power_kw'] = st.number_input("功率(kW)", min_value=0.0, value=float(p.get('power_kw', 0) or 0), key=f"cp_pwr_{idx}")
                with c2:
                    p['count'] = st.number_input("台数", min_value=1, value=int(p.get('count', 1) or 1), key=f"cp_cnt_{idx}")
                with c3:
                    p['vfd'] = st.checkbox("变频", value=p.get('vfd', True), key=f"cp_vfd_{idx}")
                if st.button("🗑️ 删除", key=f"cp_del_{idx}"):
                    to_delete_cp.append(idx)
            if to_delete_cp:
                topology['cooling_pumps'] = [c for i, c in enumerate(cooling_pumps) if i not in to_delete_cp]
                st.session_state.sim_topology = topology
                st.rerun()
    if st.button("➡️ 添加冷却泵", key="add_cooling_pump"):
        topology.setdefault('cooling_pumps', []).append({"power_kw": 0, "count": 1, "vfd": True})
        st.session_state.sim_topology = topology
        st.rerun()

    # === 冷冻泵 ===
    chilled_pumps = topology.get('chilled_pumps', [])
    st.subheader(f"💧 冷冻泵 ({len(chilled_pumps)} 条)")
    if chilled_pumps:
        with st.expander("展开编辑"):
            to_delete_hc = []
            for idx, p in enumerate(chilled_pumps):
                c1, c2, c3 = st.columns(3)
                with c1:
                    p['power_kw'] = st.number_input("功率(kW)", min_value=0.0, value=float(p.get('power_kw', 0) or 0), key=f"hp_pwr_{idx}")
                with c2:
                    p['count'] = st.number_input("台数", min_value=1, value=int(p.get('count', 1) or 1), key=f"hp_cnt_{idx}")
                with c3:
                    p['vfd'] = st.checkbox("变频", value=p.get('vfd', True), key=f"hp_vfd_{idx}")
                if st.button("🗑️ 删除", key=f"hp_del_{idx}"):
                    to_delete_hc.append(idx)
            if to_delete_hc:
                topology['chilled_pumps'] = [c for i, c in enumerate(chilled_pumps) if i not in to_delete_hc]
                st.session_state.sim_topology = topology
                st.rerun()
    if st.button("➡️ 添加冷冻泵", key="add_chilled_pump"):
        topology.setdefault('chilled_pumps', []).append({"power_kw": 0, "count": 1, "vfd": True})
        st.session_state.sim_topology = topology
        st.rerun()

    # === 冷却塔 ===
    towers = topology.get('towers', [])
    st.subheader(f"🌡️ 冷却塔 ({len(towers)} 条)")
    if towers:
        with st.expander("展开编辑"):
            to_delete_tw = []
            for idx, t in enumerate(towers):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    t['fan_power_kw'] = st.number_input("风机功率(kW)", min_value=0.0, value=float(t.get('fan_power_kw', 0) or 0), key=f"tw_pwr_{idx}")
                with c2:
                    t['count'] = st.number_input("台数", min_value=1, value=int(t.get('count', 1) or 1), key=f"tw_cnt_{idx}")
                with c3:
                    t['vfd'] = st.checkbox("变频", value=t.get('vfd', True), key=f"tw_vfd_{idx}")
                with c4:
                    t['type'] = st.text_input("类型", value=t.get('type', '开式'), key=f"tw_type_{idx}")
                if st.button("🗑️ 删除", key=f"tw_del_{idx}"):
                    to_delete_tw.append(idx)
            if to_delete_tw:
                topology['towers'] = [c for i, c in enumerate(towers) if i not in to_delete_tw]
                st.session_state.sim_topology = topology
                st.rerun()
    if st.button("➡️ 添加冷却塔", key="add_tower"):
        topology.setdefault('towers', []).append({"fan_power_kw": 0, "count": 1, "vfd": True, "type": "开式"})
        st.session_state.sim_topology = topology
        st.rerun()

    # === 特殊结构 ===
    special = topology.get('special', {})
    st.subheader("🏗️ 特殊结构")
    sp_type = special.get('type', 'none')
    special_options = ['none', 'storage', 'ice', 'heat_recovery', 'storage_and_heat_recovery']
    sp_labels = ['无', '水蓄冷', '冰蓄冷', '热回收', '蓄冷+热回收']
    try:
        sp_idx = special_options.index(sp_type) if sp_type in special_options else 0
    except ValueError:
        sp_idx = 0
    new_sp = st.selectbox("类型", options=special_options, index=sp_idx, format_func=lambda x: sp_labels[special_options.index(x)], key="sp_type")
    special['type'] = new_sp
    topology['special'] = special


# ==================== Step 2: 性能曲线收集 ====================

def render_cop_curves_stage():
    """Step 2: 设备性能铭牌信息收集"""
    st.header("📈 步骤 2: 设备性能曲线收集")

    topology = st.session_state.sim_topology
    if not topology:
        st.error("❌ 请先完成拓扑信息收集")
        if st.button("⬅️ 返回上一步", use_container_width=True):
            st.session_state.sim_stage = 'topology'
            st.rerun()
        return

    chillers = topology.get('chillers', [])
    if not chillers:
        st.warning("⚠️ 未识别到冷水主机，请返回上一步检查")
        return

    st.info("ℹ️ 请为每种型号主机上传性能曲线图片（COP vs 负荷率/冷却水温度），AI 将自动识别数据。")

    session_dir = st.session_state.session_dir

    # 为每种型号主机显示上传区域
    for idx, chiller in enumerate(chillers):
        model_name = f"{chiller.get('brand', '')} {chiller.get('model', '')} ({chiller.get('type', '')})"
        st.subheader(f"🔧 {model_name} × {chiller.get('count', 0)} 台")

        col_upload, col_manual = st.columns(2)

        with col_upload:
            uploaded_img = st.file_uploader(
                "上传性能曲线图片",
                type=['png', 'jpg', 'jpeg'],
                key=f"cop_img_{idx}"
            )

            if uploaded_img:
                # 保存图片
                img_path = session_dir / f"cop_curve_{idx}_{uploaded_img.name}"
                with open(img_path, "wb") as f:
                    f.write(uploaded_img.getbuffer())

                if st.button(f"🔍 AI 识别 COP 数据", key=f"parse_cop_{idx}", use_container_width=True):
                    _parse_cop_from_image(img_path, idx, model_name, chiller)

        with col_manual:
            st.markdown("**或手动输入/跳过**")
            skip = st.checkbox(
                "使用额定COP + 典型曲线（跳过图片识别）",
                key=f"skip_cop_{idx}"
            )
            if skip:
                # 使用默认曲线
                rated_cop = chiller.get('rated_cop', 5.0)
                default_cop = _generate_default_cop_table(rated_cop)
                st.session_state.sim_cop_data[model_name] = default_cop
                st.success(f"✅ 已使用额定COP {rated_cop:.2f} 生成典型部分负荷曲线")

        # 展示已识别的 COP 数据
        if model_name in st.session_state.sim_cop_data:
            cop_info = st.session_state.sim_cop_data[model_name]
            cw_temps = cop_info.get('cw_temps', [])
            load_ratios = cop_info.get('load_ratios', [])
            cop_table = cop_info.get('cop_table', [])

            if cop_table and cw_temps and load_ratios:
                # 安全检查：确保维度匹配
                actual_cols = len(cop_table[0]) if cop_table else 0
                actual_rows = len(cop_table)
                if actual_cols != len(load_ratios):
                    # 维度不匹配时，截断或填充 load_ratios
                    if actual_cols > len(load_ratios):
                        load_ratios = load_ratios + [0.0] * (actual_cols - len(load_ratios))
                    else:
                        load_ratios = load_ratios[:actual_cols]
                if actual_rows != len(cw_temps):
                    if actual_rows > len(cw_temps):
                        cw_temps = cw_temps + [0] * (actual_rows - len(cw_temps))
                    else:
                        cw_temps = cw_temps[:actual_rows]

                st.success(f"✅ COP 数据已收集 ({len(cw_temps)} 个温度点 × {len(load_ratios)} 个负荷点)")
                with st.expander("查看 COP 数据表"):
                    import pandas as pd
                    df = pd.DataFrame(
                        cop_table,
                        index=[f"{t}°C" for t in cw_temps],
                        columns=[f"{int(r*100)}%" for r in load_ratios]
                    )
                    st.dataframe(df, use_container_width=True)
            else:
                st.warning("⚠️ COP 数据不完整")

    st.markdown("---")

    # 检查是否所有主机都有 COP 数据
    all_have_cop = all(
        f"{ch.get('brand', '')} {ch.get('model', '')} ({ch.get('type', '')})" in st.session_state.sim_cop_data
        for ch in chillers
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ 返回上一步", use_container_width=True):
            st.session_state.sim_stage = 'topology'
            st.rerun()
    with col2:
        if all_have_cop:
            if st.button("✅ 确认，进入工况收集", type="primary", use_container_width=True):
                st.session_state.sim_stage = 'operating'
                st.rerun()
        else:
            st.caption("⚠️ 请为所有主机提供 COP 数据（上传图片或勾选跳过）")


def _parse_cop_from_image(img_path: Path, idx: int, model_name: str, chiller: dict):
    """调用 AI 从性能曲线图片识别 COP 数据"""
    _, log_container = create_streaming_container(f"🤖 AI 正在识别 {model_name} 性能曲线...")
    streaming_logs = []

    def on_text(timestamp, text):
        streaming_logs.append(f"**[{timestamp}]** 灵知 AI：{text}")
        update_streaming_container(log_container, streaming_logs)

    try:
        caller = SkillCaller(timeout=300)
        session_dir = st.session_state.session_dir
        output_path = session_dir / f"sim_cop_{idx}.json"

        prompt = (
            f"请识别性能曲线图片 {img_path} 中的 COP 数据。\n"
            f"设备: {model_name}\n"
            f"额定COP: {chiller.get('rated_cop', '未知')}\n\n"
            f"请提取二维 COP 查找表：\n"
            f"- 行: 冷却水温度 (通常 18~33°C)\n"
            f"- 列: 负荷率 (通常 100%, 90%, 80%, ..., 20%)\n"
            f"- 值: COP\n\n"
            f"输出 JSON 到 {output_path}，格式：\n"
            f'{{"cw_temps": [18,19,...,33], "load_ratios": [1.0,0.9,...,0.2], '
            f'"cop_table": [[...], ...]}}\n'
            f"请读取图片并提取数据。"
        )

        skill_result = caller.call_skill(
            "plant-simulation",
            str(img_path),
            str(output_path),
            "parse_cop_curve",
            callback=on_text
        )

        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                cop_data = json.load(f)
            st.session_state.sim_cop_data[model_name] = cop_data
            st.rerun()
        else:
            st.error("❌ COP 识别完成但未生成输出文件")

    except (SkillError, Exception) as e:
        st.error(f"❌ COP 识别失败：{str(e)}")


def _generate_default_cop_table(rated_cop: float) -> dict:
    """基于额定 COP 生成典型部分负荷曲线"""
    cw_temps = list(range(18, 34))  # 18~33°C
    load_ratios = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]

    # 典型离心机部分负荷 COP 修正系数
    # 满载时COP=额定值，60-70%负荷时COP最高（约1.15倍），低负荷下降
    plr_factors = [1.00, 1.08, 1.14, 1.18, 1.15, 1.08, 0.95, 0.78, 0.58]

    # 冷却水温度修正: 每升高1°C, COP下降约3%
    base_cw_temp = 30.0  # 额定工况冷却水温度

    cop_table = []
    for cw_t in cw_temps:
        row = []
        temp_factor = 1.0 - 0.03 * (cw_t - base_cw_temp)
        for plr_f in plr_factors:
            cop = rated_cop * plr_f * temp_factor
            row.append(round(max(cop, 2.0), 2))
        cop_table.append(row)

    return {
        "cw_temps": cw_temps,
        "load_ratios": load_ratios,
        "cop_table": cop_table
    }


# ==================== Step 3: 工况需求收集 ====================

def render_operating_stage():
    """Step 3: 当前工况需求信息收集"""
    st.header("⚙️ 步骤 3: 工况需求信息收集")

    sim_mode = st.session_state.sim_mode

    if sim_mode == 'old_station':
        _render_operating_old_station()
    else:
        _render_operating_new_station()


def _render_operating_old_station():
    """旧站房: 从调研表数据生成月度运行组合"""
    st.info("ℹ️ 将基于调研表中的运行数据生成月度运行组合表格，您可以补充或修改。")

    session_dir = st.session_state.session_dir

    if st.session_state.sim_operating_conditions is not None:
        _display_operating_table(st.session_state.sim_operating_conditions)
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ 返回上一步", use_container_width=True):
                st.session_state.sim_stage = 'cop_curves'
                st.rerun()
        with col2:
            if st.button("✅ 确认工况信息，开始仿真", type="primary", use_container_width=True):
                st.session_state.sim_stage = 'simulate'
                st.rerun()
        return

    if st.button("🔍 生成月度运行组合", type="primary", use_container_width=True):
        _, log_container = create_streaming_container("🤖 AI 正在整理运行数据...")
        streaming_logs = []

        def on_text(timestamp, text):
            streaming_logs.append(f"**[{timestamp}]** 灵知 AI：{text}")
            update_streaming_container(log_container, streaming_logs)

        try:
            caller = SkillCaller(timeout=300)
            extracted_path = session_dir / "extracted_data.json"
            topology_path = session_dir / "sim_topology.json"
            output_path = session_dir / "sim_operating.json"

            prompt = (
                f"请基于调研表提取数据 {extracted_path} 和设备拓扑 {topology_path}，"
                f"生成月度运行组合表格，输出到 {output_path}。\n\n"
                f"输出 JSON 格式：\n"
                f'{{"months": [1,2,...,12], '
                f'"chiller_combination": ["1×3000RT", ...], '
                f'"load_ratio": [0.6, ...], '
                f'"cooling_demand_kwh": [100000, ...], '
                f'"chw_supply_temp": [7, ...], '
                f'"cw_temp": [28, ...], '
                f'"notes": ["冬季", ...]}}\n'
                f"请读取数据文件并生成。"
            )

            skill_result = caller.call_skill(
                "plant-simulation",
                str(extracted_path),
                str(output_path),
                "generate_operating",
                callback=on_text
            )

            if output_path.exists():
                with open(output_path, 'r', encoding='utf-8') as f:
                    operating = json.load(f)
                st.session_state.sim_operating_conditions = operating
                st.rerun()
            else:
                st.error("❌ 生成完成但未生成输出文件")

        except (SkillError, Exception) as e:
            st.error(f"❌ 生成失败：{str(e)}")


def _render_operating_new_station():
    """新站房: 用户输入运行规律"""
    st.markdown("请输入设备运行规律，AI 将整理为月度运行组合表格。")

    with st.expander("📝 查看填写示例", expanded=True):
        st.code(OPERATING_EXAMPLE, language="text")

    operating_input = st.text_area(
        "运行规律描述",
        height=200,
        placeholder="请参照上方示例填写各季节运行组合..."
    )

    # 补充信息
    st.markdown("**补充信息（可选）**")
    col1, col2 = st.columns(2)
    with col1:
        project_region = st.selectbox(
            "项目所在地区",
            ["华南", "华东", "华中", "西南", "西北", "华北", "东北"]
        )
    with col2:
        electricity_price = st.number_input(
            "电价 (元/kWh)", min_value=0.3, max_value=2.0, value=0.65, step=0.05
        )

    if st.button("🔍 AI 整理为月度表格", type="primary", use_container_width=True):
        if not operating_input.strip():
            st.warning("⚠️ 请先输入运行规律")
            return

        _, log_container = create_streaming_container("🤖 AI 正在整理运行组合...")
        streaming_logs = []

        def on_text(timestamp, text):
            streaming_logs.append(f"**[{timestamp}]** 灵知 AI：{text}")
            update_streaming_container(log_container, streaming_logs)

        try:
            caller = SkillCaller(timeout=180)
            session_dir = st.session_state.session_dir
            output_path = session_dir / "sim_operating.json"

            topology = st.session_state.sim_topology or {}
            topology_str = json.dumps(topology, ensure_ascii=False)

            prompt = (
                f"请将以下运行规律描述整理为月度运行组合表格，输出到 {output_path}。\n\n"
                f"运行规律：\n{operating_input}\n\n"
                f"设备拓扑：{topology_str}\n"
                f"项目地区：{project_region}\n\n"
                f"输出 JSON 格式：\n"
                f'{{"months": [1,2,...,12], '
                f'"chiller_combination": ["1×3000RT+1×1800RT", ...], '
                f'"load_ratio": [0.6, ...], '
                f'"cooling_demand_kwh": [100000, ...], '
                f'"chw_supply_temp": [7, ...], '
                f'"cw_temp": [28, ...], '
                f'"notes": ["冬季停机", ...], '
                f'"region": "{project_region}", '
                f'"electricity_price": {electricity_price}}}\n'
                f"请根据地区气候特征估算冷却水温度和冷量需求。"
            )

            skill_result = caller.call_skill(
                "plant-simulation",
                operating_input,
                str(output_path),
                "generate_operating",
                callback=on_text
            )

            if output_path.exists():
                with open(output_path, 'r', encoding='utf-8') as f:
                    operating = json.load(f)
                st.session_state.sim_operating_conditions = operating
                st.rerun()
            else:
                st.error("❌ 整理完成但未生成输出文件")

        except (SkillError, Exception) as e:
            st.error(f"❌ 整理失败：{str(e)}")

    # 展示已生成的表格
    if st.session_state.sim_operating_conditions is not None:
        st.markdown("---")
        _display_operating_table(st.session_state.sim_operating_conditions)
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ 返回上一步", use_container_width=True):
                st.session_state.sim_stage = 'cop_curves'
                st.rerun()
        with col2:
            if st.button("✅ 确认工况信息，开始仿真", type="primary", use_container_width=True):
                st.session_state.sim_stage = 'simulate'
                st.rerun()


def _display_operating_table(operating: dict):
    """展示月度运行组合表格（支持工作日/休息日区分）"""
    import pandas as pd

    st.success("✅ 月度运行组合已生成")

    # 数据后处理：填充 cooling_demand_kw
    topology = st.session_state.sim_topology or {}
    chillers = topology.get('chillers', [])
    # 取最大单机制冷量用于估算需求冷量
    max_chiller_capacity = max([ch.get('capacity_kw', 0) for ch in chillers]) if chillers else 0

    # 优先从 monthly_table 获取数据，其次从顶层数组
    monthly_table = operating.get('monthly_table',
                       operating.get('operating_conditions', {}).get('monthly_table', []))

    if monthly_table:
        # AI 输出了详细的 monthly_table 结构
        rows = []
        for row in monthly_table:
            month = row.get('month', 0)
            weekday_op = row.get('weekday_operation', {})
            weekend_op = row.get('weekend_operation', {})

            wd_units = weekday_op.get('on_units', 0)
            wd_lr = weekday_op.get('load_ratio', 0)
            we_units = weekend_op.get('on_units', 0)
            we_lr = weekend_op.get('load_ratio', 0)

            # 计算需求冷量（如果为空则自动估算）
            demand = row.get('cooling_demand_kw')
            if demand is None or demand == 0:
                # 加权平均：工作日×22天 + 休息日×8天
                wd_demand = wd_units * max_chiller_capacity * wd_lr if wd_units else 0
                we_demand = we_units * max_chiller_capacity * we_lr if we_units else 0
                demand = (wd_demand * 22 + we_demand * 8) / 30 if (wd_units or we_units) else 0

            rows.append({
                '月份': f"{month}月",
                '季节': row.get('season', ''),
                '工作日': weekday_op.get('description', f"{wd_units}台@{wd_lr*100:.0f}%"),
                '休息日': weekend_op.get('description', f"{we_units}台@{we_lr*100:.0f}%"),
                '负载率': f"{row.get('representative_load_ratio', 0)*100:.0f}%" if row.get('representative_load_ratio', 0) else "-",
                '估算冷量(kW)': f"{demand:.0f}" if demand else "-",
                '备注': row.get('note', '')
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 保存计算后的需求冷量到 operating 数据中
        for i, row in enumerate(monthly_table):
            if row.get('cooling_demand_kw') is None or row.get('cooling_demand_kw') == 0:
                wd_op = row.get('weekday_operation', {})
                we_op = row.get('weekend_operation', {})
                wd_d = wd_op.get('on_units', 0) * max_chiller_capacity * wd_op.get('load_ratio', 0)
                we_d = we_op.get('on_units', 0) * max_chiller_capacity * we_op.get('load_ratio', 0)
                monthly_table[i]['cooling_demand_kw'] = (wd_d * 22 + we_d * 8) / 30 if (wd_d or we_d) else 0

    else:
        # 简单数组结构
        # 处理可能的嵌套结构：operating_conditions wrapper
        inner = operating.get('operating_conditions', operating)
        months = inner.get('months', operating.get('months', list(range(1, 13))))
        combinations = inner.get('chiller_combination', operating.get('chiller_combination', [''] * 12))
        load_ratios_raw = inner.get('load_ratio', operating.get('load_ratio', [0] * 12))
        cooling_demands = inner.get('cooling_demand_kwh',
                          inner.get('cooling_demand_kw',
                          operating.get('cooling_demand_kwh', operating.get('cooling_demand_kw', [0] * 12))))
        notes = inner.get('notes', operating.get('notes', [''] * 12))

        # 安全提取 load_ratios（可能包含 dict 而非 float）
        load_ratios = []
        for r in load_ratios_raw:
            if isinstance(r, dict):
                load_ratios.append(float(r.get('load_ratio', r.get('value', 0)) or 0))
            elif isinstance(r, (int, float)):
                load_ratios.append(float(r))
            else:
                try:
                    load_ratios.append(float(r))
                except (ValueError, TypeError):
                    load_ratios.append(0.0)

        # 自动填充冷却需求
        for i in range(len(months)):
            d = cooling_demands[i] if i < len(cooling_demands) else 0
            lr = load_ratios[i] if i < len(load_ratios) else 0
            if not d and lr > 0:
                on_units = 1  # 默认1台
                cooling_demands[i] = on_units * max_chiller_capacity * lr

        df = pd.DataFrame({
            '月份': [f"{m}月" for m in months[:12]],
            '冷机运行组合': combinations[:len(months)],
            '负载率': [f"{r*100:.0f}%" if r else "-" for r in load_ratios[:len(months)]],
            '需求冷量(kW)': [f"{d:.0f}" if d else "-" for d in cooling_demands[:len(months)]],
            '备注': notes[:len(months)]
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

    # 编辑功能
    with st.expander("✏️ 编辑月度数据"):
        st.caption("修改后点击保存生效")
        edit_df = pd.DataFrame(monthly_table) if monthly_table else pd.DataFrame()
        if not edit_df.empty:
            edited = st.data_editor(
                edit_df[['month', 'season', 'chiller_combination', 'representative_load_ratio', 'cooling_demand_kw', 'note']],
                num_rows="fixed",
                key="operating_editor"
            )
            if st.button("💾 保存修改"):
                for i, row_data in edited.iterrows():
                    monthly_table[i]['representative_load_ratio'] = row_data.get('representative_load_ratio', 0)
                    monthly_table[i]['cooling_demand_kw'] = row_data.get('cooling_demand_kw', 0)
                    monthly_table[i]['note'] = row_data.get('note', '')
                operating['monthly_table'] = monthly_table
                st.session_state.sim_operating_conditions = operating
                st.rerun()


# ==================== Step 4: 仿真执行 ====================

def render_simulate_stage():
    """Step 4: 仿真执行与结果展示"""
    st.header("🚀 步骤 4: 仿真执行")

    # 检查前置数据
    topology = st.session_state.sim_topology
    cop_data = st.session_state.sim_cop_data
    operating = st.session_state.sim_operating_conditions

    if not all([topology, cop_data, operating]):
        st.error("❌ 前置数据不完整，请返回补充")
        if st.button("⬅️ 返回工况收集", use_container_width=True):
            st.session_state.sim_stage = 'operating'
            st.rerun()
        return

    sim_mode = st.session_state.sim_mode
    mode_label = "旧站房（基准+优化对比）" if sim_mode == 'old_station' else "新站房（需求冷量+COP计算）"
    st.info(f"ℹ️ 仿真模式: **{mode_label}**")

    # 展示汇总信息
    with st.expander("📋 查看仿真输入汇总"):
        st.json({
            "topology": topology,
            "cop_data_keys": list(cop_data.keys()),
            "operating_conditions": operating,
            "sim_mode": sim_mode
        })

    if st.session_state.sim_result is not None:
        # 已有结果，展示
        _display_simulation_results(st.session_state.sim_result)
        return

    st.markdown("---")

    if st.button("🔬 开始仿真", type="primary", use_container_width=True):
        _execute_simulation()


def _execute_simulation():
    """执行仿真"""
    _, log_container = create_streaming_container("🤖 AI 正在生成并执行仿真代码...")
    streaming_logs = []

    def on_text(timestamp, text):
        streaming_logs.append(f"**[{timestamp}]** 灵知 AI：{text}")
        update_streaming_container(log_container, streaming_logs)

    try:
        session_dir = st.session_state.session_dir
        sim_mode = st.session_state.sim_mode

        # 打包所有输入数据到一个 JSON
        sim_input = {
            "project_name": st.session_state.sim_project_name,
            "sim_mode": sim_mode,
            "topology": st.session_state.sim_topology,
            "cop_data": st.session_state.sim_cop_data,
            "operating_conditions": st.session_state.sim_operating_conditions,
        }

        input_path = session_dir / "sim_input_all.json"
        with open(input_path, 'w', encoding='utf-8') as f:
            json.dump(sim_input, f, ensure_ascii=False, indent=2)

        output_dir = str(session_dir / "sim_output")
        Path(output_dir).mkdir(exist_ok=True)

        caller = SkillCaller(timeout=600)  # 仿真可能需要更长时间

        skill_result = caller.call_skill(
            "plant-simulation",
            str(input_path),
            output_dir,
            sim_mode,
            callback=on_text
        )

        # 检查输出
        output_path = Path(output_dir)
        result = {
            "success": True,
            "output_dir": output_dir,
            "files": []
        }

        # 查找输出文件
        for f in output_path.iterdir():
            result["files"].append(f.name)

        # 尝试读取报告
        report_files = list(output_path.glob("*报告*.md")) + list(output_path.glob("*report*.md"))
        if report_files:
            with open(report_files[0], 'r', encoding='utf-8') as f:
                result["report"] = f.read()

        # 尝试读取汇总 JSON
        summary_files = list(output_path.glob("*汇总*.json")) + list(output_path.glob("*summary*.json"))
        if summary_files:
            with open(summary_files[0], 'r', encoding='utf-8') as f:
                result["summary"] = json.load(f)

        st.session_state.sim_result = result
        st.rerun()

    except (SkillError, Exception) as e:
        st.error(f"❌ 仿真执行失败：{str(e)}")


def _display_simulation_results(result: dict):
    """展示仿真结果"""
    st.success("✅ 仿真完成！")

    output_dir = Path(result.get("output_dir", ""))

    # 关键指标
    summary = result.get("summary", {})
    if summary:
        st.subheader("🎯 核心指标")
        cols = st.columns(4)
        with cols[0]:
            st.metric("全年加权COP", f"{summary.get('annual_cop', 0):.2f}")
        with cols[1]:
            st.metric("年总耗电量", f"{summary.get('annual_power_mwh', 0):.0f} MWh")
        with cols[2]:
            st.metric("年总供冷量", f"{summary.get('annual_cooling_mwh', 0):.0f} MWh")
        with cols[3]:
            saving_rate = summary.get('energy_saving_rate')
            if saving_rate is not None:
                st.metric("节能率", f"{saving_rate * 100:.1f}%")
            else:
                st.metric("年节省电费", f"{summary.get('annual_saving_yuan', 0)/10000:.1f} 万元")

    st.markdown("---")

    # 图表展示
    chart_files = list(output_dir.glob("*.png")) if output_dir.exists() else []
    if chart_files:
        st.subheader("📊 分析图表")
        for chart_path in chart_files:
            st.image(str(chart_path), caption=chart_path.stem, use_container_width=True)

    st.markdown("---")

    # 报告展示
    report = result.get("report", "")
    if report:
        st.subheader("📄 仿真分析报告")
        st.markdown(report)

    st.markdown("---")

    # 文件下载
    st.subheader("📥 下载仿真结果")
    files = result.get("files", [])
    if files:
        for fname in files:
            fpath = output_dir / fname
            if fpath.exists() and fpath.suffix in ['.xlsx', '.csv', '.md', '.json']:
                with open(fpath, "rb") as f:
                    st.download_button(
                        label=f"📥 {fname}",
                        data=f.read(),
                        file_name=fname,
                        use_container_width=True
                    )

    st.markdown("---")

    # 操作按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 重新仿真", use_container_width=True):
            st.session_state.sim_result = None
            st.rerun()
    with col2:
        if st.button("🏠 返回首页", type="primary", use_container_width=True):
            reset_simulation()
            st.session_state.stage = 'upload'
            st.rerun()
