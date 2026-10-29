"""
从报价体系 Excel 构建 price_catalog.json
用法: python scripts/build_price_catalog.py [excel_path] [--force]
      excel_path 默认: templates/2025年云智控报价体系-全产品线11.xlsx
      --force: 强制重新生成，忽略缓存
"""
import sys, io, json, os, re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))  # 确保可以 import skill_caller
DEFAULT_EXCEL = PROJECT_ROOT / "templates" / "2025年云智控报价体系-全产品线11.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "price_catalog.json"

# ── 锚点校验表 ──
ANCHORS = {
    "hardware.adl400_meter.standard_price": 305,
    "hardware.adl400_meter.channel_price": 245,
    "water_meters.DN50.standard_price": 1080,
    "software.platform.standard_price": 60000,
    "software.platform.channel_price": 42000,
}


def deep_get(d, path):
    """按点号路径取值: 'hardware.adl400_meter.standard_price'"""
    for key in path.split("."):
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return None
    return d


def validate_anchors(catalog, anchors=None):
    """校验锚点价格"""
    if anchors is None:
        anchors = ANCHORS
    failures = []
    for path, expected in anchors.items():
        actual = deep_get(catalog, path)
        if actual is None:
            failures.append(f"  MISSING: {path} (expected {expected})")
        elif actual != expected:
            failures.append(f"  MISMATCH: {path} got {actual}, expected {expected}")
    return failures




SCHEMA_PATH = PROJECT_ROOT / "config" / "price_catalog_schema.json"


def _load_schema():
    """加载解析配置，不存在时返回 None"""
    if SCHEMA_PATH.exists():
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return None


def _find_sheet_by_keywords(sheetnames, keywords, exclude_keywords=None):
    """按关键词匹配 sheet 名称，返回首个匹配的 sheet 名（或 None）。
    所有 keywords 必须同时出现（AND），所有 exclude_keywords 不能出现（AND NOT）。
    """
    exclude_keywords = exclude_keywords or []
    for name in sheetnames:
        if all(kw in name for kw in keywords) and not any(kw in name for kw in exclude_keywords):
            return name
    return None


def _scan_columns(ws, header_row, column_specs):
    """扫描表头行，建立字段名→列号（1-based）的映射。
    column_specs: {"field_name": {"header_keywords": [...], "type": "number"}, ...}

    两遍匹配策略：
      Pass 1: 精确匹配 (==)，从左到右搜索 — 处理标准表头
      Pass 2: 子串匹配 (in)，从右到左搜索 — 处理复合表头（如"标准底价License底价"）

    搜索范围: max(1, header_row-2) ~ min(max_row, header_row+2)
    覆盖多行表头（如 Row2=名称/型号, Row3=价格）。
    """
    col_map = {}
    if header_row is None or header_row < 1:
        return col_map

    search_start = max(1, header_row - 2)
    search_end = min(ws.max_row, header_row + 2)

    for field, spec in column_specs.items():
        keywords = spec.get("header_keywords", [])

        # ── Pass 1: 精确匹配，从左到右 ──
        for r in range(search_start, search_end + 1):
            if field in col_map:
                break
            for c in range(1, ws.max_column + 1):
                cell_text = str(ws.cell(row=r, column=c).value or "").strip()
                if not cell_text:
                    continue
                for kw in keywords:
                    if kw == cell_text:
                        col_map[field] = c
                        break
                if field in col_map:
                    break

        # ── Pass 2: 子串匹配，从右到左（避免匹配到"旧版存档"等左侧废弃列）──
        if field not in col_map:
            for r in range(search_start, search_end + 1):
                if field in col_map:
                    break
                for c in range(ws.max_column, 0, -1):  # 右→左
                    cell_text = str(ws.cell(row=r, column=c).value or "").strip()
                    if not cell_text:
                        continue
                    for kw in keywords:
                        if kw in cell_text:
                            col_map[field] = c
                            break
                    if field in col_map:
                        break

    # ── 报告未匹配字段 ──
    unmatched = [f for f in column_specs if f not in col_map]
    if unmatched:
        print(f"  [WARN] 表头扫描未匹配到 {len(unmatched)}/{len(column_specs)} 字段 (header_row={header_row})")
        for f in unmatched[:5]:
            print(f"         - {f}: 关键词 {column_specs[f].get('header_keywords', [])} 未命中任何表头单元格")

    return col_map


def _match_hardware_rules(name, desc, model_text, rules):
    """按配置的规则匹配硬件类型，返回 (key, entry_dict) 或 None"""
    for rule in rules:
        rule_key = rule["key"]
        name_str = str(name or "")
        desc_str = str(desc or "")
        combined = f"{name_str} {desc_str}"

        # 解析 match 字段：简化版，支持常见模式
        match_spec = rule.get("match", "")

        # 手动实现规则匹配（比解析 DSL 更可靠）
        if rule_key == "adl400_meter":
            if "ADL400" in str(model_text or "") or ("三相" in name_str and "ADL400" in desc_str):
                return rule_key, {
                    "name": rule["name"], "brand": rule["brand"], "model": rule["model"]
                }
        elif rule_key == "cable_per_meter":
            if any(kw in name_str for kw in ["通讯线", "RVSP", "屏蔽双绞"]):
                return rule_key, {
                    "name": rule["name"], "brand": rule["brand"], "model": rule["model"]
                }
        elif rule_key == "comm_box":
            if "通讯箱" in name_str:
                return rule_key, {
                    "name": rule["name"], "brand": rule["brand"], "model": rule["model"]
                }
        elif rule_key == "power_supply":
            if "开关电源" in name_str:
                return rule_key, {
                    "name": rule["name"], "brand": rule["brand"], "model": rule["model"]
                }
        elif rule_key == "air_switch":
            if "空气开关" in name_str:
                return rule_key, {
                    "name": rule["name"], "brand": rule["brand"], "model": rule["model"]
                }
    return None


def _match_construction_rules(service_text, rules):
    """按配置的规则匹配施工类型，返回 (key, entry_dict) 或 None"""
    for rule in rules:
        match_spec = rule.get("match", "")
        if "新装电表" in match_spec and "新装电表" in str(service_text or ""):
            return rule["key"], {
                "name": rule["name"],
                "standard_price": rule.get("fallback_price", 500),
                "channel_price": rule.get("fallback_price", 500)
            }
        elif "通讯箱" in match_spec and "通讯箱" in str(service_text or ""):
            return rule["key"], {
                "name": rule["name"],
                "standard_price": rule.get("fallback_price", 350),
                "channel_price": rule.get("fallback_price", 350)
            }
        elif "集中区域" in match_spec and "集中区域" in str(service_text or ""):
            return rule["key"], {
                "name": rule["name"],
                "standard_price": rule.get("fallback_price", 100),
                "channel_price": rule.get("fallback_price", 100)
            }
        elif "分散区域" in match_spec and "分散区域" in str(service_text or ""):
            return rule["key"], {
                "name": rule["name"],
                "standard_price": rule.get("fallback_price", 120),
                "channel_price": rule.get("fallback_price", 120)
            }
    return None


def _validate_columns(cols, col_specs, sheet_label):
    """验证所有 schema 字段是否已在表头中匹配到列号。
    返回缺失字段列表；如果全部匹配则返回空列表。
    """
    missing = [f for f in col_specs if f not in cols]
    if missing:
        print(f"  [SKIP] {sheet_label}: 表头扫描失败 — 以下字段未匹配到列号:")
        for f in missing:
            print(f"         - {f}: 关键词 {col_specs[f].get('header_keywords', [])}")
        print(f"  [SKIP] 请更新 price_catalog_schema.json 中的 header_keywords 以匹配实际 Excel 表头")
    return missing


def _validate_catalog(catalog, validation_config):
    """解析后校验：检查必填 section、价格合法性"""
    issues = []
    # 检查必填 section
    for section in validation_config.get("required_sections", []):
        val = catalog.get(section)
        if val is None or (isinstance(val, (list, dict)) and len(val) == 0):
            issues.append(f"[WARN] 必填 section '{section}' 为空或缺失")

    # 价格合法性检查
    price_min = validation_config.get("price_min", 0)
    for sw_key, sw_item in catalog.get("software", {}).items():
        for pk in ("standard_price", "channel_price"):
            p = sw_item.get(pk)
            if p is not None and p < price_min:
                issues.append(f"[WARN] software.{sw_key}.{pk}={p} < {price_min}")

    return issues


def read_excel_sheets(excel_path: str) -> dict:
    """用 openpyxl 读取 Excel 全部 sheet 的原始数据，供 AI 解析使用"""
    import openpyxl
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    sheets_data = {}
    for name in wb.sheetnames:
        ws = wb[name]
        rows = []
        for r in range(1, ws.max_row + 1):
            row_data = []
            for c in range(1, ws.max_column + 1):
                v = ws.cell(row=r, column=c).value
                if v is not None:
                    row_data.append(str(v))
                else:
                    row_data.append("")
            # 跳过全空行
            if any(cell for cell in row_data):
                rows.append(row_data)
        sheets_data[name] = rows
    wb.close()
    return sheets_data


def build_with_ai(excel_path: str) -> dict:
    """通过 AI Skill 解析 Excel → price_catalog JSON"""
    print("[AI] 调用 read-price-catalog Skill 解析报价体系...")
    try:
        from quote_module.skill_caller import SkillCaller

        # 先本地读取原始数据
        sheets_data = read_excel_sheets(excel_path)
        raw_path = OUTPUT_PATH.parent / "_price_raw.json"
        raw_path.write_text(json.dumps(sheets_data, ensure_ascii=False), encoding="utf-8")

        caller = SkillCaller(timeout=300)
        result = caller.call_skill(
            "read-price-catalog",
            excel_path,
            str(OUTPUT_PATH),
        )

        if OUTPUT_PATH.exists():
            catalog = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            print("[AI] Skill 执行完成，已生成 price_catalog.json")
            return catalog
        else:
            print("[AI] Skill 执行完成但未生成文件")
            return None
    except Exception as e:
        print(f"[AI] Skill 调用失败: {e}")
        return None


def _derive_ct_type(remark_text, desc_text):
    """从备注/描述推导 CT 形式：圆孔 -> 穿缆圆孔式，方孔 -> 母排方孔式。"""
    if "方孔" in remark_text:
        return "母排方孔式"
    if "圆孔" in remark_text:
        return "穿缆圆孔式"
    # fallback：按孔型描述推断（φxx 圆孔，xx*xx 方孔）
    if re.search(r'\d+\s*[×x\*]\s*\d+\s*mm', desc_text):
        return "母排方孔式"
    if re.search(r'φ\d+\s*mm', desc_text):
        return "穿缆圆孔式"
    return "穿缆圆孔式"


def _extract_tier_info(desc_text: str) -> dict | None:
    """从功能描述中提取梯级信息。
    例如:
      "组态点数10点" → {"type": "topology", "max_points": 10}
      "报表数量5张" → {"type": "report", "max_count": 5}
      "2D/2.5D版，客户..." → {"type": "dashboard", "keywords": ["2D", "客户供图"]}
    """
    if not desc_text:
        return None

    # 组态点数: "组态数量≤10个" / "组态数量≤100个" / "拓扑点数50点"
    m = re.search(r'(?:组态|拓扑).*?(\d+)\s*(?:个|点|张)', desc_text)
    if m:
        return {"type": "topology", "max_points": int(m.group(1))}

    # 报表数量: "报表数量≤5张" / "报表数量5张" / "报表数量≤10张"
    m = re.search(r'报表.*?(\d+)\s*张', desc_text)
    if m:
        return {"type": "report", "max_count": int(m.group(1))}

    # 大屏类型关键词
    dash_keywords = []
    if re.search(r'3D', desc_text):
        dash_keywords.append("3D")
    if re.search(r'2D|2\.5D', desc_text):
        dash_keywords.append("2D")
    if re.search(r'客户.*供图|客户.*提供.*图', desc_text):
        dash_keywords.append("客户供图")
    if re.search(r'全厂|园区', desc_text):
        dash_keywords.append("全厂/园区")
    if re.search(r'产线|部门', desc_text):
        dash_keywords.append("产线/部门")
    if re.search(r'能源概览|目标体系', desc_text):
        dash_keywords.append("能源概览")
    if re.search(r'需.*建模|需.*渲染|UED', desc_text):
        dash_keywords.append("需UED")
    if re.search(r'标准模板|无地图', desc_text):
        dash_keywords.append("标准模板")
    if dash_keywords:
        return {"type": "dashboard", "keywords": dash_keywords}

    return None


def build_local(excel_path: str) -> dict:
    """本地解析 Excel（AI 不可用时的降级方案）—— 优化项 #1+#2：配置驱动 + 表头识别"""
    print("[LOCAL] 使用本地解析构建价格目录...")
    import openpyxl
    from datetime import datetime

    # ── 加载配置 ──
    schema = _load_schema()
    if schema is None:
        print("[LOCAL] 未找到 price_catalog_schema.json，回退到内嵌默认配置")
        schema = {}

    discovery = schema.get("sheet_discovery", {})
    software_key_map = schema.get("software_key_mapping", {})
    hw_rules = schema.get("hardware_rules", {}).get("rules", [])
    ct_rules = schema.get("construction_rules", {}).get("rules", [])
    hw_defaults = schema.get("hardware_defaults", {})
    validation = schema.get("validation", {})

    wb = openpyxl.load_workbook(excel_path, data_only=True)

    def cell(ws, row, col):
        v = ws.cell(row=row, column=col).value
        return v

    catalog = {
        "software": {},
        "hardware": {},
        "ct_mapping": [],
        "water_meters": {},
        "flow_meters": [],
        "construction": {},
        "tax_info": {},
        "_meta": {}
    }

    # ── 软件: 平台 sheet（优化项 #1+#2：配置驱动 + 表头扫描）──
    sw_cfg = discovery.get("software_platform", {})
    sw_sheet = _find_sheet_by_keywords(wb.sheetnames,
                                       sw_cfg.get("name_keywords", ["软件", "平台"]),
                                       sw_cfg.get("exclude_keywords", ["空调", "空压"]))
    if sw_sheet:
        ws = wb[sw_sheet]
        hdr_row = sw_cfg.get("header_row", 2)
        data_start = sw_cfg.get("data_start_row", 3)
        merged_cols = sw_cfg.get("merged_columns", [1, 2])
        col_specs = sw_cfg.get("columns", {})
        cols = _scan_columns(ws, hdr_row, col_specs)
        if not _validate_columns(cols, col_specs, sw_sheet):
            used_keys = set()
            last_module = ""
            last_category = ""

            for r in range(data_start, ws.max_row + 1):
                raw_module = cell(ws, r, cols["module_name"])
                raw_category = cell(ws, r, cols["category"])
                func = cell(ws, r, cols["function_name"])
                config_type = cell(ws, r, cols["config_type"])
                func_desc = cell(ws, r, cols["func_desc"])

                # 追踪合并单元格：空模块名 = 属于上一个模块
                if raw_module and str(raw_module).strip() and str(raw_module) != "None":
                    last_module = str(raw_module).strip()
                if raw_category and str(raw_category).strip() and str(raw_category) != "None":
                    last_category = str(raw_category).strip()

                if not last_module or "总计" in last_module:
                    continue

                # 功能描述（用于子项识别）：优先列C，空时用列E
                func_str = str(func or "").strip()
                if func_str == "None":
                    func_str = ""
                func_desc_str = str(func_desc or "").strip()
                if func_desc_str == "None":
                    func_desc_str = ""

                std_price = cell(ws, r, cols["standard_price"])
                ch_price = cell(ws, r, cols["channel_price"])
                if std_price is None and ch_price is None:
                    continue
                try:
                    std_price = float(std_price) if std_price else None
                    ch_price = float(ch_price) if ch_price else None
                except (ValueError, TypeError):
                    continue
                if std_price is None and ch_price is None:
                    continue

                # 确定这一行的实际名称：优先用功能描述（子项），否则用模块名
                item_name = func_str if func_str else (func_desc_str if func_desc_str else last_module)
                if not item_name or item_name == "None":
                    continue

                # 生成唯一 key
                import re as _re
                name_key = _re.sub(r'[^\w]', '_', item_name).lower().strip('_')
                if not name_key:
                    name_key = f"item_r{r}"

                # 检查兼容映射（同时匹配模块名、分类名和功能名）—— 优化项 #1：从配置加载
                final_key = name_key
                for keyword, compat in software_key_map.items():
                    if (keyword in item_name or keyword in last_module or keyword in last_category) and compat not in used_keys:
                        final_key = compat
                        break

                # 避免 key 重复
                if final_key in used_keys:
                    # 对于梯级定价（同名多行），用 _tier_N 后缀
                    base = final_key
                    counter = 2
                    while final_key in used_keys:
                        final_key = f"{base}_{counter}"
                        counter += 1
                used_keys.add(final_key)

                config_str = str(config_type or "")
                tier_info = _extract_tier_info(func_desc_str or func_str)

                entry = {
                    "name": item_name,
                    "module_group": last_module,
                    "category": last_category,
                    "config_type": "选配" if "选配" in config_str else "标配",
                    "description": func_desc_str if func_desc_str else (str(func)[:100] if func else ""),
                    "brand": "蘑菇物联",
                    "model": "云智控4.0",
                    "standard_price": std_price,
                    "channel_price": ch_price,
                }
                if tier_info:
                    entry["tier_info"] = tier_info
                catalog["software"][final_key] = entry

    # ── 软件: 空调 sheet（优化项 #1：配置驱动）──
    hvac_cfg = discovery.get("software_hvac", {})
    hvac_sheet = _find_sheet_by_keywords(wb.sheetnames,
                                         hvac_cfg.get("name_keywords", ["软件", "空调"]))
    if hvac_sheet:
        ws = wb[hvac_sheet]
        hdr_row = hvac_cfg.get("header_row", 1)
        data_start = hvac_cfg.get("data_start_row", 2)
        hvac_col_specs = hvac_cfg.get("columns", {})
        hvac_cols = _scan_columns(ws, hdr_row, hvac_col_specs)

        if not _validate_columns(hvac_cols, hvac_col_specs, hvac_sheet):
            last_module = ""
            for r in range(data_start, ws.max_row + 1):
                raw_module = cell(ws, r, hvac_cols["module_name"])
                func = cell(ws, r, hvac_cols["function_name"])
                if raw_module and str(raw_module).strip() and str(raw_module) != "None":
                    last_module = str(raw_module).strip()
                std_price = cell(ws, r, hvac_cols["standard_price"])
                ch_price = cell(ws, r, hvac_cols["channel_price"])
                if std_price is None and ch_price is None:
                    continue
                try:
                    std_price = float(std_price) if std_price else None
                    ch_price = float(ch_price) if ch_price else None
                except (ValueError, TypeError):
                    continue
                item_name = str(func or last_module or "").strip()
                if not item_name or item_name == "None":
                    item_name = last_module
                import re as _re
                key = "hvac_" + _re.sub(r'[^\w]', '_', item_name).lower().strip('_')
                base_key = key
                counter = 2
                while key in catalog["software"]:
                    key = f"{base_key}_{counter}"
                    counter += 1
                catalog["software"][key] = {
                    "name": f"[空调]{item_name}",
                    "module_group": last_module,
                    "category": "空调",
                    "config_type": "选配",
                    "description": str(func)[:100] if func else "",
                    "brand": "蘑菇物联",
                    "model": "云智控4.0",
                    "standard_price": std_price,
                    "channel_price": ch_price,
                }

    # ── 软件: 空压 sheet（优化项 #1：配置驱动）──
    comp_cfg = discovery.get("software_compressor", {})
    comp_sheet = _find_sheet_by_keywords(wb.sheetnames,
                                         comp_cfg.get("name_keywords", ["空压"]),
                                         comp_cfg.get("exclude_keywords", ["硬件", "三方"]))
    if comp_sheet:
        ws = wb[comp_sheet]
        data_start = comp_cfg.get("data_start_row", 4)
        comp_col_specs = comp_cfg.get("columns", {})
        comp_cols = _scan_columns(ws, comp_cfg.get("header_row", 3), comp_col_specs)

        if not _validate_columns(comp_cols, comp_col_specs, comp_sheet):
            last_module = ""
            for r in range(data_start, ws.max_row + 1):
                raw_module = cell(ws, r, comp_cols["module_name"])
                func = cell(ws, r, comp_cols["function_name"])
                if raw_module and str(raw_module).strip() and str(raw_module) != "None":
                    last_module = str(raw_module).strip()
                std_price = cell(ws, r, comp_cols["standard_price"])
                ch_price = cell(ws, r, comp_cols["channel_price"])
                if std_price is None and ch_price is None:
                    continue
                try:
                    std_price = float(std_price) if std_price else None
                    ch_price = float(ch_price) if ch_price else None
                except (ValueError, TypeError):
                    continue
                item_name = str(func or last_module or "").strip()
                if not item_name or item_name == "None":
                    item_name = last_module
                import re as _re
                key = "compressor_" + _re.sub(r'[^\w]', '_', item_name).lower().strip('_')
                base_key = key
                counter = 2
                while key in catalog["software"]:
                    key = f"{base_key}_{counter}"
                    counter += 1
                catalog["software"][key] = {
                    "name": f"[空压]{item_name}",
                    "module_group": last_module,
                    "category": "空压",
                    "config_type": "选配",
                    "description": str(func)[:100] if func else "",
                    "brand": "蘑菇物联",
                    "model": "云智控4.0",
                    "standard_price": std_price,
                    "channel_price": ch_price,
                }

    # ── 硬件: 一方硬件（优化项 #1：配置驱动）──
    hw_our_cfg = discovery.get("hardware_our", {})
    hw_our_sheet = _find_sheet_by_keywords(wb.sheetnames, hw_our_cfg.get("name_keywords", ["一方硬件"]))
    if hw_our_sheet:
        ws = wb[hw_our_sheet]
        hw_our_col_specs = hw_our_cfg.get("columns", {})
        hw_our_cols = _scan_columns(ws, hw_our_cfg.get("header_row", 2), hw_our_col_specs)
        if not _validate_columns(hw_our_cols, hw_our_col_specs, hw_our_sheet):
            data_start = hw_our_cfg.get("data_start_row", 4)
            for r in range(data_start, ws.max_row + 1):
                name = str(cell(ws, r, hw_our_cols["device_name"]) or "")
                model = str(cell(ws, r, hw_our_cols["model"]) or "")
                if not name or name == "None":
                    continue
                ch_price = cell(ws, r, hw_our_cols["channel_price"])
                std_price = cell(ws, r, hw_our_cols["standard_price"])

                if "云盒" in name and "Maxw5Pro-C1" in model:
                    catalog["hardware"]["cloud_box"] = {
                        "name": "能管云盒", "brand": "蘑菇物联", "model": "Maxw5Pro-C1",
                        "standard_price": std_price, "channel_price": ch_price
                    }

    # ── 硬件: 三方硬件能管（优化项 #1+#2：配置驱动 + 规则匹配）──
    hw_tp_cfg = discovery.get("hardware_third_party", {})
    hw_tp_sheet = _find_sheet_by_keywords(wb.sheetnames,
                                          hw_tp_cfg.get("name_keywords", ["三方硬件", "能管"]),
                                          hw_tp_cfg.get("exclude_keywords", ["空调", "空压"]))
    if hw_tp_sheet:
        ws = wb[hw_tp_sheet]
        hw_tp_col_specs = hw_tp_cfg.get("columns", {})
        hw_tp_cols = _scan_columns(ws, hw_tp_cfg.get("header_row", 2), hw_tp_col_specs)
        hw_tp_valid = not _validate_columns(hw_tp_cols, hw_tp_col_specs, hw_tp_sheet)
        data_start = hw_tp_cfg.get("data_start_row", 4)
        if hw_tp_valid:
            last_name = ""
            for r in range(data_start, ws.max_row + 1):
                raw_name = cell(ws, r, hw_tp_cols["device_name"])
                if raw_name and str(raw_name).strip() and str(raw_name) != "None":
                    last_name = str(raw_name).strip()
                name = last_name
                desc = str(cell(ws, r, hw_tp_cols["spec_desc"]) or "")
                model_text = str(cell(ws, r, hw_tp_cols["model"]) or "")
                if not name or name == "None":
                    continue
                ch_price = cell(ws, r, hw_tp_cols["channel_price"])
                std_price = cell(ws, r, hw_tp_cols["standard_price"]) or cell(ws, r, hw_tp_cols["channel_price"])

                # 优化项 #1：规则驱动的硬件匹配
                match = _match_hardware_rules(name, desc, model_text, hw_rules)
                if match:
                    hw_key, hw_entry = match
                    if hw_key not in catalog["hardware"]:
                        fb = next((r.get("fallback_price", {}) for r in hw_rules if r["key"] == hw_key), {})
                        catalog["hardware"][hw_key] = {
                            **hw_entry,
                            "standard_price": std_price if std_price else fb.get("standard"),
                            "channel_price": ch_price if ch_price else fb.get("channel"),
                        }
        else:
            hw_tp_sheet = None  # 标记为无效，跳过后续 CT/水表解析

    # ── 硬件: 三方硬件空压（开关电源、空气开关等辅材）──
    hw_comp_cfg = discovery.get("hardware_third_party_compressor", {})
    hw_comp_sheet = _find_sheet_by_keywords(wb.sheetnames,
                                             hw_comp_cfg.get("name_keywords", ["三方硬件", "空压"]))
    if hw_comp_sheet:
        ws = wb[hw_comp_sheet]
        hw_comp_col_specs = hw_comp_cfg.get("columns", {})
        hw_comp_cols = _scan_columns(ws, hw_comp_cfg.get("header_row", 2), hw_comp_col_specs)
        if not _validate_columns(hw_comp_cols, hw_comp_col_specs, hw_comp_sheet):
            data_start = hw_comp_cfg.get("data_start_row", 4)
            for r in range(data_start, ws.max_row + 1):
                name = str(cell(ws, r, hw_comp_cols["device_name"]) or "")
                desc = str(cell(ws, r, hw_comp_cols["spec_desc"]) or "")
                model_text = str(cell(ws, r, hw_comp_cols["model"]) or "")
                if not name or name == "None":
                    continue
                ch_price = cell(ws, r, hw_comp_cols["channel_price"])
                std_price = cell(ws, r, hw_comp_cols["standard_price"]) or cell(ws, r, hw_comp_cols["channel_price"])

                match = _match_hardware_rules(name, desc, model_text, hw_rules)
                if match:
                    hw_key, hw_entry = match
                    if hw_key not in catalog["hardware"]:
                        fb = next((r.get("fallback_price", {}) for r in hw_rules if r["key"] == hw_key), {})
                        catalog["hardware"][hw_key] = {
                            **hw_entry,
                            "standard_price": std_price if std_price else fb.get("standard"),
                            "channel_price": ch_price if ch_price else fb.get("channel"),
                        }

    # ── 硬件辅材兜底（优化项 #1：从配置加载）──
    for key, defaults in hw_defaults.items():
        if key.startswith("_"):
            continue
        if key not in catalog["hardware"]:
            catalog["hardware"][key] = defaults

    # ── CT 互感器: 三方硬件能管 ──
    if hw_tp_sheet and hw_tp_valid:
        ws = wb[hw_tp_sheet]
        last_ct_remark = ""
        for r in range(data_start, ws.max_row + 1):
            name = str(cell(ws, r, hw_tp_cols["device_name"]) or "")
            desc = str(cell(ws, r, hw_tp_cols["spec_desc"]) or "")
            if "电流互感器" not in name and "电流互感器" not in desc:
                continue
            ch_price = cell(ws, r, hw_tp_cols["channel_price"])
            std_price = cell(ws, r, hw_tp_cols["standard_price"])
            full_text = desc if desc else name

            # 备注列是CT形式的主要依据；同一备注覆盖下方连续行
            remark = str(cell(ws, r, hw_tp_cols["remark"]) or "").strip()
            if remark:
                last_ct_remark = remark

            # 解析半结构化描述 "150A/5A&口径K-φ24mm&AKH-0.66K"
            current_match = re.search(r'(\d+)A', full_text)
            aperture_match = re.search(r'[φΦ]([\d]+[×xX\*][\d]+\s*mm|[\d]+\s*mm)', full_text)
            model_match = re.search(r'AKH[\w./-]+', full_text)

            ct_entry = {
                "current": int(current_match.group(1)) if current_match else 0,
                "type": _derive_ct_type(last_ct_remark, full_text),
                "aperture": aperture_match.group(1).replace(" ", "") if aperture_match else "",
                "brand": "安科瑞",
                "model": model_match.group(0) if model_match else "",
                "standard_price": std_price if std_price else None,
                "channel_price": ch_price if ch_price else None,
            }
            catalog["ct_mapping"].append(ct_entry)

    # ── 水表: 三方硬件能管 ──
    if hw_tp_sheet and hw_tp_valid:
        ws = wb[hw_tp_sheet]
        for r in range(data_start, ws.max_row + 1):
            name = str(cell(ws, r, hw_tp_cols["device_name"]) or "")
            desc = str(cell(ws, r, hw_tp_cols["spec_desc"]) or "")
            if "水表" not in name and "水表" not in desc:
                continue
            full = desc if desc else name
            dn_match = re.search(r'DN(\d+)', full)
            if not dn_match:
                continue
            dn = f"DN{dn_match.group(1)}"
            ch_price = cell(ws, r, hw_tp_cols["channel_price"])
            std_price = cell(ws, r, hw_tp_cols["standard_price"])
            brand = str(cell(ws, r, hw_tp_cols["brand"]) or "捷先数码(深水牌)")

            # 安装费按 DN 档估算
            dn_int = int(dn_match.group(1))
            if dn_int <= 40:
                install = 300
            elif dn_int <= 50:
                install = 500
            else:
                install = 1000

            # 每个 DN 只保留第一条（优先 RS485 系列）
            if dn not in catalog["water_meters"] or "RS485" in name:
                catalog["water_meters"][dn] = {
                    "brand": brand,
                    "model": re.search(r'LX\w+-\d+', full).group(0) if re.search(r'LX\w+-\d+', full) else "",
                    "standard_price": std_price if std_price else None,
                    "channel_price": ch_price if ch_price else None,
                    "install_price": install,
                }

    # ── 流量计/冷热量表: 【三方硬件】空调 + 【三方硬件】空压 ──
    def _parse_dn_range(text, is_model=False):
        """从文本提取 DN 范围，返回 (min, max)；精确 DN 返回 (n, n)。
        is_model=True 时仅接受纯 'DNxx' 格式，避免型号中的数字被误解析。"""
        if not text:
            return None, None
        s = str(text).strip()
        upper = s.upper()
        # 1) 显式范围：DN50~DN1000 / DN50-DN1000 / 50~1000
        m = re.search(r'DN?\s*(\d+)\s*[~～-]\s*DN?\s*(\d+)', upper)
        if m:
            return int(m.group(1)), int(m.group(2))
        # 2) 最大可测管道 DN250
        m = re.search(r'最大可测管道\s*DN?\s*(\d+)', upper)
        if m:
            return 15, int(m.group(1))
        # 3) 管道口径：DN50
        m = re.search(r'管道口径[：:]\s*DN?\s*(\d+)', upper)
        if m:
            n = int(m.group(1))
            return n, n
        # 4) 型号列纯 DNxx
        if is_model and re.match(r'^DN?\s*\d+$', upper, re.IGNORECASE):
            n = int(re.search(r'(\d+)', upper).group(1))
            return n, n
        # 5) 其他文本中的显式 DN 标注（非型号列）
        if not is_model:
            m = re.search(r'DN\s*(\d+)', upper)
            if m:
                n = int(m.group(1))
                return n, n
        return None, None

    def _add_flow_meter(name, model, spec, brand, install_type, std_price, ch_price):
        if not name:
            return
        # 只保留流量计/热量表相关条目
        if not any(kw in name for kw in ("流量计", "热量表", "冷/热量表")):
            return
        dn_min, dn_max = _parse_dn_range(model, is_model=True)
        if dn_min is None:
            dn_min, dn_max = _parse_dn_range(spec, is_model=False)
        if dn_min is None:
            return
        # 标准化安装方式
        install_type = str(install_type or "").strip()
        if install_type in ("插入式", "外夹式", "管段式", "法兰夹持式", "对夹式", "法兰式"):
            pass
        elif "插入" in install_type:
            install_type = "插入式"
        elif "外夹" in install_type:
            install_type = "外夹式"
        elif "法兰" in install_type or "夹持" in install_type:
            install_type = "管段式"
        else:
            # 空压 sheet 无安装方式列，涡街/差压/热式默认管段式
            install_type = "管段式"
        catalog["flow_meters"].append({
            "name": name,
            "model": str(model or "").strip(),
            "brand": str(brand or "").strip() or "国产优质",
            "type": install_type,
            "dn_min": dn_min,
            "dn_max": dn_max,
            "standard_price": float(std_price) if std_price is not None else None,
            "channel_price": float(ch_price) if ch_price is not None else None,
        })

    # ── 流量计/冷热量表: 空调 + 空压 ──
    fm_ac_cfg = discovery.get("flow_meter_ac", {})
    fm_ac_sheet = _find_sheet_by_keywords(wb.sheetnames,
                                          fm_ac_cfg.get("name_keywords", ["三方硬件", "空调"]))
    if fm_ac_sheet:
        ws = wb[fm_ac_sheet]
        fm_ac_col_specs = fm_ac_cfg.get("columns", {})
        fm_ac_cols = _scan_columns(ws, fm_ac_cfg.get("header_row", 2), fm_ac_col_specs)
        if not _validate_columns(fm_ac_cols, fm_ac_col_specs, fm_ac_sheet):
            for r in range(fm_ac_cfg.get("data_start_row", 4), ws.max_row + 1):
                name = str(cell(ws, r, fm_ac_cols["device_name"]) or "").strip()
                model = str(cell(ws, r, fm_ac_cols["model"]) or "").strip()
                spec = str(cell(ws, r, fm_ac_cols["spec"]) or "").strip()
                brand = str(cell(ws, r, fm_ac_cols["brand"]) or "").strip()
                install_type = str(cell(ws, r, fm_ac_cols["install_type"]) or "").strip()
                ch_price = cell(ws, r, fm_ac_cols["channel_price"])
                std_price = cell(ws, r, fm_ac_cols["standard_price"])
                _add_flow_meter(name, model, spec, brand, install_type, std_price, ch_price)

    fm_comp_cfg = discovery.get("flow_meter_compressor", {})
    fm_comp_sheet = _find_sheet_by_keywords(wb.sheetnames,
                                            fm_comp_cfg.get("name_keywords", ["三方硬件", "空压"]))
    if fm_comp_sheet:
        ws = wb[fm_comp_sheet]
        fm_comp_col_specs = fm_comp_cfg.get("columns", {})
        fm_comp_cols = _scan_columns(ws, fm_comp_cfg.get("header_row", 2), fm_comp_col_specs)
        if not _validate_columns(fm_comp_cols, fm_comp_col_specs, fm_comp_sheet):
            for r in range(fm_comp_cfg.get("data_start_row", 4), ws.max_row + 1):
                name = str(cell(ws, r, fm_comp_cols["device_name"]) or "").strip()
                model = str(cell(ws, r, fm_comp_cols["model"]) or "").strip()
                spec = str(cell(ws, r, fm_comp_cols["spec"]) or "").strip()
                brand = str(cell(ws, r, fm_comp_cols["brand"]) or "").strip()
                ch_price = cell(ws, r, fm_comp_cols["channel_price"])
                std_price = cell(ws, r, fm_comp_cols["standard_price"])
                _add_flow_meter(name, model, spec, brand, "", std_price, ch_price)

    # ── 施工: 施工调试 ──
    ct_cfg = discovery.get("construction", {})
    ct_sheet = _find_sheet_by_keywords(wb.sheetnames, ct_cfg.get("name_keywords", ["施工调试", "施工"]))
    if ct_sheet:
        ws = wb[ct_sheet]
        ct_col_specs = ct_cfg.get("columns", {})
        ct_cols = _scan_columns(ws, ct_cfg.get("header_row", 2), ct_col_specs)
        if not _validate_columns(ct_cols, ct_col_specs, ct_sheet):
            for r in range(ct_cfg.get("data_start_row", 3), ws.max_row + 1):
                service = str(cell(ws, r, ct_cols["service_name"]) or "")
                price = cell(ws, r, ct_cols["unit_price"])

                match = _match_construction_rules(service, ct_rules)
                if match:
                    ct_key, ct_entry = match
                    actual_price = price if price else ct_entry.get("standard_price", 500)
                    catalog["construction"][ct_key] = {
                        "name": ct_entry["name"],
                        "standard_price": actual_price,
                        "channel_price": actual_price
                    }

    # ── 税费: 报价模板 sheet（优化项 #1：配置驱动 sheet 发现）──
    tax_cfg = discovery.get("tax_template", {})
    tax_sheet = _find_sheet_by_keywords(wb.sheetnames, tax_cfg.get("name_keywords", ["报价模板"]))
    if tax_sheet:
        ws = wb[tax_sheet]
        note = cell(ws, 27, 1)
        if note:
            note_text = str(note)
            # 提取原文中的税率
            if "13%" in note_text:
                catalog["tax_info"]["software_hardware_rate"] = 0.13
            if "6%" in note_text:
                catalog["tax_info"]["construction_rate"] = 0.06
            # 判断定价基础：报价表行项是税前价（税费单独列行另算）
            catalog["tax_info"]["template_note"] = "以上单价均为税前价，增值税另算——软件和硬件按13%、技术实施按6%"
            catalog["tax_info"]["pricing_basis"] = "税前价（line item prices are pre-tax, VAT calculated on top）"
        else:
            catalog["tax_info"]["template_note"] = "以上单价均为税前价，增值税另算——软件和硬件按13%、技术实施按6%"
            catalog["tax_info"]["pricing_basis"] = "税前价（line item prices are pre-tax, VAT calculated on top）"

    # ── 优化项 #2.4：解析后校验 ──
    validation_issues = _validate_catalog(catalog, validation)
    if validation_issues:
        print("[VALIDATE] 解析校验发现问题:")
        for issue in validation_issues:
            print(f"  {issue}")

    wb.close()
    return catalog


def build(excel_path=None, force=False, use_ai=True):
    """
    构建 price_catalog.json
    返回 (catalog, warnings)
    """
    if excel_path is None:
        excel_path = DEFAULT_EXCEL
    excel_path = Path(excel_path)

    if not excel_path.exists():
        return None, [f"报价体系文件不存在: {excel_path}"]

    # 检查缓存
    if not force and OUTPUT_PATH.exists():
        existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        meta = existing.get("_meta", {})
        cached_source = meta.get("source_file", "")
        if cached_source == str(excel_path.resolve()):
            excel_mtime = excel_path.stat().st_mtime
            cache_time = meta.get("generated_at", "")
            if cache_time:
                print(f"[CACHE] 价格目录已是最新 (来源: {excel_path.name}, 生成于 {cache_time[:19]})")
                return existing, []

    print(f"[BUILD] 从 {excel_path.name} 构建价格目录...")

    # 优先 AI，失败则本地解析
    catalog = None
    warnings = []

    if use_ai:
        catalog = build_with_ai(str(excel_path))

    if catalog is None:
        catalog = build_local(str(excel_path))
        if catalog:
            warnings.append("AI 解析不可用，使用本地解析。复杂格式（如多品牌水表）可能不完整，建议在 AI 可用时重新生成。")

    if catalog is None:
        return None, ["无法解析报价体系 Excel"]

    # 添加元数据
    catalog["_meta"] = {
        "source_file": str(excel_path.resolve()),
        "source_name": excel_path.name,
        "generated_at": datetime.now().isoformat(),
        "generated_by": "AI" if use_ai and catalog.get("_ai_generated") else "local",
        "excel_modified_at": datetime.fromtimestamp(excel_path.stat().st_mtime).isoformat(),
    }

    # 锚点校验（优化项 #1：从配置加载锚点）
    schema = _load_schema()
    anchors = (schema or {}).get("validation", {}).get("anchors", ANCHORS)
    failures = validate_anchors(catalog, anchors)
    if failures:
        print("[VALIDATE] 锚点校验失败:")
        for f in failures:
            print(f)
        warnings.extend(failures)
    else:
        print("[VALIDATE] 锚点校验通过")

    # 写入文件
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {OUTPUT_PATH}")
    print(f"  software: {len(catalog.get('software', {}))} items")
    print(f"  hardware: {len(catalog.get('hardware', {}))} items")
    print(f"  ct_mapping: {len(catalog.get('ct_mapping', []))} entries")
    print(f"  water_meters: {len(catalog.get('water_meters', {}))} DN entries")
    print(f"  flow_meters: {len(catalog.get('flow_meters', []))} entries")
    print(f"  construction: {len(catalog.get('construction', {}))} items")
    print(f"  source: {excel_path.name}")

    return catalog, warnings


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a.startswith("--")]
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    excel = positional[0] if positional else None
    force = "--force" in args
    use_ai = "--no-ai" not in args

    catalog, warnings = build(excel, force=force, use_ai=use_ai)

    if warnings:
        print("\n[WARNINGS]")
        for w in warnings:
            print(f"  [WARN]  {w}")

    if catalog is None:
        print("\n[FAIL] 构建失败")
        sys.exit(1)
