"""
轻量级 AI 客户端 — 直接调用 .env 中配置的代理 API
替代 claude_agent_sdk 的 heavyweight Agent 调用，用于调研表解析等简单 AI 任务
"""
import os
import json
import re
from pathlib import Path
from typing import Optional, Callable

# 读取 .env 配置
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _val = _line.split("=", 1)
            os.environ[_key.strip()] = _val.strip()


class AIClientError(Exception):
    pass


class AIClient:
    """通过 OpenAI 兼容接口调用 .env 配置的 AI 代理"""

    def __init__(self):
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "")
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("ANTHROPIC_MODEL", "gpt-4o")

        if not self.base_url or not self.api_key:
            raise AIClientError(
                f"AI 配置不完整: base_url={'OK' if self.base_url else 'MISSING'}, "
                f"api_key={'OK' if self.api_key else 'MISSING'}"
            )

    def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        timeout: int = 120,
        temperature: float = 0.1,
    ) -> str:
        try:
            from openai import OpenAI
            import httpx
        except ImportError:
            raise AIClientError("openai 包未安装，请运行: pip install openai")

        # trust_env=False：绕过 Windows 系统代理（避免走 127.0.0.1:7897）
        http_client = httpx.Client(trust_env=False)
        client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
            http_client=http_client,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content


_client_instance: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = AIClient()
    return _client_instance


_OPTION_NAME_MAP = {
    "批次能耗分析": "batch_energy_analysis",
    "批次单耗分析": "batch_energy_analysis",
    "移动端": "mobile_app",
    "移动端应用": "mobile_app",
    "手机APP": "mobile_app",
    "单位能耗": "energy_efficiency_analysis",
    "能耗强度分析": "energy_efficiency_analysis",
    "能源效率分析": "energy_efficiency_analysis",
    "设备能效分析": "equipment_efficiency",
    "能耗对标": "energy_benchmarking",
    "运维工单": "ops_work_order",
    "巡检": "ops_work_order",
}


def _normalize_project_json(raw: dict) -> dict:
    """标准化 AI 输出结构：兼容新旧格式，统一为 calculate.py 期望的结构"""

    def _si(v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    # ---- existing_meters ----
    if "existing_meters" not in raw:
        raw["existing_meters"] = {
            "electric_accessible": _si(raw.pop("electric_accessible", 0)),
            "electric_need_retrofit": _si(raw.pop("electric_need_retrofit", 0)),
            "water_accessible": _si(raw.pop("water_accessible", 0)),
            "water_need_retrofit": _si(raw.pop("water_need_retrofit", 0)),
        }

    # ---- new_meters ----
    if "new_meters" not in raw:
        raw["new_meters"] = {}
    nm = raw["new_meters"]
    for old, new in [
        ("new_electric_meters", "electric"),
        ("new_water_meters", "water"),
        ("new_flow_meters", "flow_meters"),
    ]:
        if old in raw and new not in nm:
            nm[new] = raw.pop(old)
    nm.setdefault("electric", [])
    nm.setdefault("water", [])
    nm.setdefault("flow_meters", [])

    raw.setdefault("third_party_systems", [])

    # ---- optional_modules ----
    # AI 新格式输出 selected_modules 数组，需转换为 calculate.py 期望的布尔字段
    om = raw.get("optional_modules", {})
    if not isinstance(om, dict):
        om = {}

    selected_arr = om.pop("selected_modules", [])
    if isinstance(selected_arr, list) and selected_arr:
        normalized_modules = []
        for item in selected_arr:
            if not isinstance(item, dict):
                continue
            name = str(item.get("option_name", "")).strip()
            if not name:
                continue
            is_selected = item.get("selected", False)
            scope = str(item.get("scope", "")).strip()
            qty = str(item.get("quantity_or_name", "")).strip()
            req = str(item.get("customer_request", "")).strip()
            has_content = any(
                v and v not in ("-", "无", "0")
                for v in (scope, qty, req)
            )
            if not is_selected and not has_content:
                continue
            normalized_modules.append({
                "name": name,
                "scope": scope,
                "quantity_name": qty,
                "customer_request": req,
            })
        om["selected_modules"] = normalized_modules
    else:
        legacy_modules = []
        if om.pop("batch_energy_analysis", False):
            legacy_modules.append({"name": "批次能耗分析", "scope": "", "quantity_name": "1", "customer_request": ""})
        if om.pop("mobile_app", False):
            legacy_modules.append({"name": "移动端", "scope": "", "quantity_name": "1", "customer_request": ""})
        for mod_key in om.pop("selected_software_modules", []):
            reverse_name = mod_key
            for cn, eng in _OPTION_NAME_MAP.items():
                if eng == mod_key:
                    reverse_name = cn
                    break
            legacy_modules.append({"name": reverse_name, "scope": "", "quantity_name": "1", "customer_request": ""})
        om["selected_modules"] = legacy_modules

    om.setdefault("extra_dashboards", _si(om.get("extra_dashboards", 0)))
    om.setdefault("extra_topology", _si(om.get("extra_topology", 0)))
    om.setdefault("extra_reports", _si(om.get("extra_reports", 0)))
    raw["optional_modules"] = om

    # ---- project_notes ----
    if "project_notes" not in raw or not isinstance(raw["project_notes"], dict):
        raw["project_notes"] = {}
    pn = raw["project_notes"]

    for key in ("current_status", "problems", "goals"):
        if key in raw and key not in pn:
            pn[key] = raw.pop(key)

    pn.setdefault("current_status", "")
    pn.setdefault("problems", "")

    pn.setdefault("smart_analysis", [])
    pn.setdefault("special_requirements", [])
    pn.setdefault("other_notes", [])
    for arr_key in ("smart_analysis", "special_requirements", "other_notes"):
        if isinstance(pn[arr_key], str):
            pn[arr_key] = [pn[arr_key]] if pn[arr_key].strip() else []

    # 向后兼容：goals 字段从 special_requirements + other_notes 拼接
    if "goals" not in pn or not pn["goals"]:
        combined = pn["special_requirements"] + pn["other_notes"]
        pn["goals"] = "\n".join(combined) if combined else pn.get("goals", "")

    pn["has_site_plan"] = raw.pop("has_site_plan", pn.get("has_site_plan", True))

    # ---- logic_gaps ----
    raw.setdefault("logic_gaps", [])
    if not isinstance(raw["logic_gaps"], list):
        raw["logic_gaps"] = []

    # ---- 新增顶层字段 ----
    raw.setdefault("industry", "")
    raw.setdefault("scope", "")
    raw.setdefault("current_management", "")

    return raw


def read_survey_with_ai(
    survey_path: str,
    output_path: str,
    callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """使用 AI 解析调研表，返回结构化 JSON"""
    import openpyxl

    def _notify(msg):
        if callback:
            callback(msg)

    _notify("📖 正在读取调研表文件...")
    wb = openpyxl.load_workbook(survey_path, data_only=True)

    all_cells = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        _notify(f"📋 正在扫描工作表: {sheet_name}")
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None and str(cell.value).strip():
                    all_cells.append(f"{cell.coordinate}={cell.value}")
    wb.close()

    cell_text = "\n".join(all_cells)
    _notify(f"📊 共提取 {len(all_cells)} 个非空单元格，发送给 AI 解析...")

    system_prompt = """你是一个专业的表格数据提取助手。你的任务是从标准能管项目调研表的原始单元格数据中，提取结构化信息。

## 核心原则：自适应定位

**禁止使用固定行号。** 你必须通过以下两步定位每个板块的数据：

### 第一步：定位板块
通过关键词找到每个板块的起始位置（C1 列包含中文数字编号的行）：
- "一" 且同行有"项目基础信息" → 板块一起始
- "二" 且同行有"既有表计"或"设备接入" → 板块二起始
- "三" 且同行有"新增电表"或"ADL400" → 板块三起始
- "四" 且同行有"新增水表" → 板块四起始
- "五" 且同行有"新增流量计"或"冷热量表" → 板块五起始
- "六" 且同行有"第三方系统" → 板块六起始
- "七" 且同行有"可选软件" → 板块七起始
- 含"超出默认"且同行有"大屏"或"组态"或"报表" → 板块七附加起始
- "八" 且同行有"项目需求"或"需求补充" → 板块八起始

### 第二步：定位数据行
在每个板块内，找到**表头行**（含"序号"或含该板块特有字段名如"安装位置""介质""系统名称"的行）。数据从表头行的**下一行**开始，遇到**连续2行全空**或**下一个板块起始**时停止。

### 第三步：动态列映射
在每个板块的表头行中，读取各列标题文字，建立列字母到字段名的映射。
- 例：表头行 C 列="管径 DN" → 后续数据行的 C 列就是 dn 字段
- 例：表头行 E 列="安装方式" → 后续数据行的 E 列就是 install_type 字段
- 如果表头行缺失或无法识别，按该板块的默认列序读取（见下方各板块说明）

---

## 各板块提取规则

### 板块一：项目基础信息
定位后，在数据区中按 B 列（调研项）的文字匹配：
- B含"客户名称" → C列 = client_name
- B含"项目名称" → C列 = project_name
- B含"项目地点" → C列 = project_location
- B含"所属行业" → C列 = industry
- B含"项目范围"或"区域" → C列 = scope
- B含"部署方式" → D列(辅助选择列) = deployment_mode，映射：
  - "云端部署" → "cloud"
  - "私有部署（我方" → "private_our"
  - "私有部署（客户" → "private_client"
  - 如果C列有值而D列为空，读C列
- B含"现有能源管理" → D列或C列 = current_management

### 板块二：既有表计/设备接入
定位后跳过表头行，在数据行中按 B 列文字匹配设备类型：
- B含"电表" → C=electric_accessible(整数), D=electric_need_retrofit(整数)
- B含"水表" → C=water_accessible(整数), D=water_need_retrofit(整数)
- 空值视为 0
- 其他行（流量计、蒸汽表等）也读取 C/D 列，如果有值记入 existing_meters 的对应字段

### 板块三：新增电表
定位后跳过表头行。默认列序：B=位置, C=数量, D=CT电流(A), E=CT形式, F=现场条件。
- 每行输出: {location, quantity(int), ct_current(int), ct_type, site_condition}
- **只取 C 列（数量）有正整数值的行**
- 连续2行C列为空则停止

### 板块四：新增水表
定位后跳过表头行。默认列序：B=位置/介质, C=管径DN, D=数量, E=是否需安装, F=现场条件。
- 每行输出: {location, dn, quantity(int), need_install(bool), site_condition}
- **只取 D 列（数量）有正整数值的行**

### 板块五：新增流量计/冷热量表
定位后跳过表头行。默认列序：B=介质, C=管径DN, D=数量, E=安装方式, F=现场条件。
- 每行输出: {medium, dn, quantity(int), install_type, site_condition}
- **只取 D 列（数量）有正整数值的行**
- 注意：某些行的介质可能是"水流量计"，这也属于流量计，不要遗漏

### 板块六：第三方系统接入
定位后跳过表头行。默认列序：B=系统名称, C=系统类型, D=接口方向, E=数据范围, F=实现内容。
- 每行输出: {name, type, direction, description, implementation}
- **跳过表头关键词行**：如果 B 列内容恰好是"系统名称"、C 列是"系统类型"等表头文字，跳过该行
- 只取 B 列有实际系统名称（非空且非表头文字）的行

### 板块七：可选软件确认清单
定位后跳过表头行。默认列序：B=可选项名称, C=是否选用, D=对象/范围, E=数量/名称, F=客户要求。

逐行读取所有可选项：
- 每行输出: {option_name, selected(bool), scope, quantity_or_name, customer_request}
- selected 判定：C 列含"选用"且不含"不选" → true；**D/E/F 任一列有实质内容（非"-"、"无"、空）也视为 true**；仅当 C 列含"不选"且 D/E/F 均无内容时为 false
- **必须读取所有行**，直到连续2行全空或遇到"超出默认"文字
- **所有 selected=true 的模块必须输出到 selected_modules 数组**，不要仅放入 logic_gaps

**逻辑漏洞检测** — 检查以下情况，发现则记录到 logic_gaps：
1. selected=true 但 E 列（数量/名称）为空 → 漏洞描述："选中了[模块名]但未填写数量/名称"
2. selected=true 但 D 列（对象/范围）为空 → 漏洞描述："选中了[模块名]但未填写对象/范围"
3. E 列有值但 C 列为"不选"或空 → 漏洞描述："[模块名]填写了数量/名称但未标记选用"

### 板块七附加：超出默认（大屏/组态/报表）
在板块七数据区结束后，查找含"超出默认"的行。

该行下方如果有表头行（含"序号"），跳过表头后读取数据行：
- 按 B 列关键词分类：含"大屏"→extra_dashboards, 含"组态"或"拓扑"→extra_topology, 含"报表"→extra_reports
- C 列或 D 列为数量（整数）

**逻辑漏洞检测**：
1. 数据行有类型但数量列为空 → 漏洞描述："[类型]未填写数量"

**注意**：如果"超出默认"行下方没有数据行，说明用户不需要超出默认数量的设备，这是正常情况，**不要**将其记录为逻辑漏洞或信息缺失。

### 板块八：项目需求补充
定位后跳过表头行。按 B 列（补充项）的文字分类，读取 C 列内容：

- B 含"项目现状"或"管理问题" → 内容存入 current_status（字符串）
- B 含"智能分析" → 内容存入 smart_analysis（**数组**）
- B 含"特殊要求"或"其他要求" → 内容存入 special_requirements（**数组**）
- B 含其他文字 → 内容存入 other_notes（数组）

**多行处理规则（重要）**：
1. **同一标签多行**：如果连续多行的 B 列标签相同（如连续3行都是"智能分析需求"），将每行 C 列内容作为数组的一个元素
2. **单行多条目**：如果一行 C 列包含编号（如"1.xxx 2.xxx"）或换行分隔，拆分为数组的多个元素
3. **所有内容塞入一个格子**：如果某个标签的 C 列文本很长且包含多个独立需求，按编号或标点拆分
4. **跨行混合**：板块八可能有额外插入行（序号>3），按 B 列标签归类即可

**逻辑漏洞检测**：
1. smart_analysis 或 special_requirements 文本中提到"AI""大模型""预测""闭环控制""自动启停""自动调节""固定节能率" → 漏洞描述："板块八出现非标需求：[原文摘录]"
2. 文本中提到具体设备型号/规格（如"DN150蒸汽流量计3台"）但在前面板块中未列出 → 漏洞描述："板块八提到设备[型号]但未在表计板块中列出"
3. 文本中提到"分期建设""一期""二期" → 漏洞描述："板块八提到分期建设，需确认本次范围"

---

## 输出 JSON Schema

```json
{
  "client_name": "",
  "project_name": "",
  "project_location": "",
  "industry": "",
  "scope": "",
  "deployment_mode": "cloud|private_our|private_client",
  "current_management": "",
  "existing_meters": {
    "electric_accessible": 0,
    "electric_need_retrofit": 0,
    "water_accessible": 0,
    "water_need_retrofit": 0
  },
  "new_meters": {
    "electric": [
      {"location": "", "quantity": 0, "ct_current": 0, "ct_type": "", "site_condition": ""}
    ],
    "water": [
      {"location": "", "dn": "", "quantity": 0, "need_install": false, "site_condition": ""}
    ],
    "flow_meters": [
      {"medium": "", "dn": "", "quantity": 0, "install_type": "", "site_condition": ""}
    ]
  },
  "third_party_systems": [
    {"name": "", "type": "", "direction": "", "description": "", "implementation": ""}
  ],
  "optional_modules": {
    "selected_modules": [
      {"option_name": "", "scope": "", "quantity_or_name": "", "customer_request": ""}
    ],
    "extra_dashboards": 0,
    "extra_topology": 0,
    "extra_reports": 0
  },
  "project_notes": {
    "current_status": "",
    "smart_analysis": [],
    "special_requirements": [],
    "other_notes": [],
    "has_site_plan": true
  },
  "logic_gaps": [
    {"section": "板块七", "option": "xxx", "description": "选中了xxx但未填写数量/名称", "severity": "warning|nonstandard"}
  ]
}
```

## 输出要求
- 必须严格输出纯 JSON，不要包含 markdown 代码块标记
- 数量字段必须是整数类型（0 表示未填写）
- CT 电流是数字（150, 200, 250...）
- smart_analysis 和 special_requirements **必须是数组**（即使只有一条也用数组包裹）
- 空行不纳入数组
- has_site_plan 默认 true
- logic_gaps 记录所有发现的逻辑漏洞，没有则为空数组 []
- severity 取值："warning"（可修正）或 "nonstandard"（超出标准能管边界）"""

    user_prompt = f"""以下是调研表的所有非空单元格数据（共 {len(all_cells)} 个）：

{cell_text}

请按照自适应定位规则提取数据，检测逻辑漏洞，输出完整的 JSON。"""

    _notify("🤖 AI 正在解析调研表...")
    client = get_ai_client()
    raw_response = client.chat(
        prompt=user_prompt,
        system_prompt=system_prompt,
        timeout=120,
    )
    _notify("✅ AI 解析完成，正在提取结果...")

    json_match = re.search(r'\{[\s\S]*\}', raw_response)
    if not json_match:
        raise AIClientError("AI 返回内容中未找到 JSON")

    result = json.loads(json_match.group())
    result = _normalize_project_json(result)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _notify(f"💾 已保存到 {output_path}")
    return result
