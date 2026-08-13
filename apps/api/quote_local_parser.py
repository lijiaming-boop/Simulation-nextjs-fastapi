"""报价模块 — 本地调研表降级解析 + 数据后处理

这两个函数原在源项目 quote_ui.py 中（Streamlit 单体 UI 层），
目标项目拆分架构后搬到此处作为适配层辅助，quote_module/ 保持一字不改。

- read_survey_local:    AI 不可用时的本地降级解析（硬编码"标准调研表"sheet）
- enrich_project_data:  对 AI / 本地两条路径的输出做矛盾检测 + 数据归一
"""
from __future__ import annotations


def read_survey_local(survey_path: str) -> dict:
    """本地解析调研表（降级方案）"""
    import openpyxl
    wb = openpyxl.load_workbook(survey_path, data_only=True)
    ws = wb["标准调研表"]

    def get(col_row):
        v = ws[col_row].value
        return v if v is not None else ""

    def safe_int(v):
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    def get_bool(v):
        s = str(v).strip()
        return s in ("选用", "是", "TRUE", "True", "true", "yes", "Y", "1")

    client_name = str(get("C7"))
    project_name = str(get("C8"))
    project_location = str(get("C9"))
    deploy_raw = str(get("D12"))
    if "私有部署（我方" in deploy_raw:
        deploy = "private_our"
    elif "私有部署（客户" in deploy_raw:
        deploy = "private_client"
    else:
        deploy = "cloud"

    elec_acc = safe_int(get("C18"))
    elec_ret = safe_int(get("D18"))
    water_acc = safe_int(get("C19"))
    water_ret = safe_int(get("D19"))
    flow_cooling_acc = safe_int(get("C20"))
    flow_cooling_ret = safe_int(get("D20"))
    heat_acc = safe_int(get("C21"))
    heat_ret = safe_int(get("D21"))
    flow_air_acc = safe_int(get("C22"))
    flow_air_ret = safe_int(get("D22"))
    steam_acc = safe_int(get("C23"))
    steam_ret = safe_int(get("D23"))
    gas_acc = safe_int(get("C24"))
    gas_ret = safe_int(get("D24"))
    other_acc = safe_int(get("C25"))
    other_ret = safe_int(get("D25"))

    electric = []
    for r in range(29, 35):
        qty = safe_int(get(f"C{r}"))
        if qty > 0:
            electric.append({
                "location": str(get(f"B{r}")), "quantity": qty,
                "ct_current": safe_int(get(f"D{r}")),
                "ct_type": str(get(f"E{r}")),
                "site_condition": str(get(f"F{r}"))
            })

    water = []
    for r in range(39, 47):
        qty = safe_int(get(f"D{r}"))
        if qty > 0:
            water.append({
                "location": str(get(f"B{r}")), "dn": str(get(f"C{r}")),
                "quantity": qty, "need_install": get_bool(get(f"E{r}")),
                "site_condition": str(get(f"F{r}"))
            })

    flow_meters = []
    for r in range(49, 57):
        medium = str(get(f"B{r}"))
        qty = safe_int(get(f"D{r}"))
        if qty > 0 or (medium and medium != "None" and medium.strip()):
            flow_meters.append({
                "medium": medium if medium != "None" else "",
                "dn": str(get(f"C{r}")), "quantity": qty,
                "install_type": str(get(f"E{r}")),
                "site_condition": str(get(f"F{r}"))
            })

    third_party = []
    for r in range(59, 65):
        name = str(get(f"B{r}"))
        if name and name != "None" and name.strip():
            third_party.append({
                "name": name, "type": str(get(f"C{r}")),
                "direction": str(get(f"D{r}")),
                "description": str(get(f"E{r}"))
            })

    # 板块七：可选软件（含矛盾检测）
    data_warnings = []
    selected_modules = []
    for r in range(69, 76):
        opt_name = str(get(f"B{r}")).strip()
        if not opt_name or opt_name == "None":
            continue
        c_val = str(get(f"C{r}")).strip()
        scope = str(get(f"D{r}")).strip()
        qty_name = str(get(f"E{r}")).strip()
        cust_req = str(get(f"F{r}")).strip()
        explicitly_selected = "选用" in c_val and "不选" not in c_val
        has_content = any(
            v and v not in ("-", "无", "None", "0")
            for v in (scope, qty_name, cust_req)
        )
        if not explicitly_selected and has_content:
            filled_fields = []
            if scope:
                filled_fields.append(f"范围={scope}")
            if qty_name:
                filled_fields.append(f"数量={qty_name}")
            if cust_req:
                filled_fields.append(f"客户要求={cust_req}")
            data_warnings.append({
                "type": "contradiction",
                "source": "可选软件清单",
                "item": opt_name,
                "message": f"[{opt_name}] 标记为'不选'，但填写了{'、'.join(filled_fields)}，已纳入计算",
                "detail": f"列C={c_val}、列D={scope or '(空)'}、列E={qty_name or '(空)'}、列F={cust_req or '(空)'}",
            })
        if not explicitly_selected and not has_content:
            continue
        selected_modules.append({
            "name": opt_name, "scope": scope,
            "quantity_name": qty_name, "customer_request": cust_req,
            "explicitly_selected": explicitly_selected,
        })

    # 板块七附加：大屏/组态/报表
    extra_items = []
    for r in range(79, 85):
        item_type = str(get(f"B{r}")).strip()
        item_qty = safe_int(get(f"C{r}"))
        name_topic = str(get(f"D{r}")).strip()
        artwork_flag = str(get(f"E{r}")).strip()
        item_notes = str(get(f"F{r}")).strip()
        if not item_type or item_qty <= 0:
            continue
        customer_artwork = name_topic
        if artwork_flag and artwork_flag not in ("-", "无", "None", ""):
            customer_artwork = f"{name_topic} {artwork_flag}".strip()
        extra_items.append({
            "type": item_type, "quantity": item_qty,
            "customer_artwork": customer_artwork, "notes": item_notes,
        })

    extra_dashboards = sum(
        it["quantity"] for it in extra_items
        if any(kw in it["type"] for kw in ("大屏", "看板", "dashboard"))
    ) or 0
    extra_topology = sum(
        it["quantity"] for it in extra_items
        if any(kw in it["type"] for kw in ("组态", "拓扑", "能流", "topology"))
    ) or 0
    extra_reports = sum(
        it["quantity"] for it in extra_items
        if any(kw in it["type"] for kw in ("报表", "报告", "report"))
    ) or 0
    unmatched = [
        it for it in extra_items
        if not any(kw in it["type"] for kw in ("大屏", "看板", "dashboard", "组态", "拓扑", "能流", "topology", "报表", "报告", "report"))
    ]
    if unmatched and extra_topology == 0 and extra_dashboards == 0 and extra_reports == 0:
        extra_topology = sum(it["quantity"] for it in unmatched)

    optional_modules = {
        "selected_modules": selected_modules,
        "extra_dashboards": extra_dashboards,
        "extra_topology": extra_topology,
        "extra_reports": extra_reports,
        "extra_items": extra_items,
    }

    current_status = str(get("C89"))
    goals = str(get("C91"))
    wb.close()

    return {
        "client_name": client_name, "project_name": project_name,
        "project_location": project_location, "deployment_mode": deploy,
        "existing_meters": {
            "electric_accessible": elec_acc, "electric_need_retrofit": elec_ret,
            "water_accessible": water_acc, "water_need_retrofit": water_ret,
            "flow_cooling_accessible": flow_cooling_acc, "flow_cooling_need_retrofit": flow_cooling_ret,
            "heat_accessible": heat_acc, "heat_need_retrofit": heat_ret,
            "flow_air_accessible": flow_air_acc, "flow_air_need_retrofit": flow_air_ret,
            "steam_accessible": steam_acc, "steam_need_retrofit": steam_ret,
            "gas_accessible": gas_acc, "gas_need_retrofit": gas_ret,
            "other_accessible": other_acc, "other_need_retrofit": other_ret,
        },
        "new_meters": {"electric": electric, "water": water, "flow_meters": flow_meters},
        "third_party_systems": third_party,
        "optional_modules": optional_modules,
        "project_notes": {
            "current_status": current_status, "problems": "",
            "goals": goals, "smart_analysis": [goals] if goals else [],
            "special_requirements": [], "other_notes": [], "has_site_plan": True,
        },
        "logic_gaps": [],
        "data_warnings": data_warnings,
    }


def enrich_project_data(project: dict) -> dict:
    """对 project_data 做后处理：检测矛盾、生成 extra_items、补齐 data_warnings

    AI 路径与本地降级路径解析完成后都应调用一次。
    """
    data_warnings = list(project.get("data_warnings") or [])

    om = project.get("optional_modules", {})
    if not isinstance(om, dict):
        om = {}
        project["optional_modules"] = om

    selected_modules = om.get("selected_modules", [])
    if isinstance(selected_modules, list):
        for m in selected_modules:
            if not isinstance(m, dict):
                continue
            name = m.get("name", "")
            scope = str(m.get("scope", "")).strip()
            qty_name = str(m.get("quantity_name", "")).strip()
            cust_req = str(m.get("customer_request", "")).strip()
            explicitly_selected = m.get("explicitly_selected", None)
            # explicitly_selected 为 None 表示 AI 路径（AI 已自行判断），不重复检测
            if explicitly_selected is False:
                has_content = any(
                    v and v not in ("-", "无", "None", "0")
                    for v in (scope, qty_name, cust_req)
                )
                if has_content:
                    already_warned = any(
                        w.get("item") == name and w.get("type") == "contradiction"
                        for w in data_warnings
                    )
                    if not already_warned:
                        filled_fields = []
                        if scope:
                            filled_fields.append(f"范围={scope}")
                        if qty_name:
                            filled_fields.append(f"数量={qty_name}")
                        if cust_req:
                            filled_fields.append(f"客户要求={cust_req}")
                        data_warnings.append({
                            "type": "contradiction",
                            "source": "可选软件清单",
                            "item": name,
                            "message": f"[{name}] 标记为'不选'，但填写了{'、'.join(filled_fields)}，已纳入计算",
                            "detail": f"列D={scope or '(空)'}、列E={qty_name or '(空)'}、列F={cust_req or '(空)'}",
                        })

    extra_items = om.get("extra_items")
    if not extra_items:
        extra_items = []
        extra_dashboards = om.get("extra_dashboards", 0) or 0
        extra_topology = om.get("extra_topology", 0) or 0
        extra_reports = om.get("extra_reports", 0) or 0
        if extra_dashboards > 0:
            extra_items.append({"type": "大屏", "quantity": extra_dashboards, "customer_artwork": "", "notes": ""})
        if extra_topology > 0:
            extra_items.append({"type": "组态/拓扑图", "quantity": extra_topology, "customer_artwork": "", "notes": ""})
        if extra_reports > 0:
            extra_items.append({"type": "报表", "quantity": extra_reports, "customer_artwork": "", "notes": ""})
        om["extra_items"] = extra_items

    logic_gaps = project.get("logic_gaps", [])
    if isinstance(logic_gaps, list):
        for gap in logic_gaps:
            if not isinstance(gap, dict):
                continue
            data_warnings.append({
                "type": "logic_gap",
                "source": gap.get("section", ""),
                "item": gap.get("option", ""),
                "message": gap.get("description", ""),
                "detail": f"严重程度: {gap.get('severity', 'warning')}",
            })

    project["data_warnings"] = data_warnings
    return project
