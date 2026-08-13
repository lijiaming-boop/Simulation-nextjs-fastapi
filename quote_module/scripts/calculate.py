"""
标准能管报价计算引擎
从项目 JSON + price_catalog.json 计算出内部报价底稿
"""
import math
import json
import re
from pathlib import Path
from typing import Optional


# ===================== 默认规则常量 =====================

# 软件点位系数
POINTS_PER_ELECTRIC_METER = 12
POINTS_PER_FLUID_METER = 3
POINTS_PER_THIRD_PARTY_SYSTEM = 1000
POINTS_ROUND_TO = 1000

# 云盒配置
ELECTRIC_METERS_PER_CLOUDBOX = 8

# 标准交付（不另收费）
DEFAULT_DASHBOARDS = 1
DEFAULT_TOPOLOGY = 3
DEFAULT_REPORTS = 3

# 调试
DEBUG_DAYS_PER_CLOUDBOX = 1
STANDARD_DEBUG_PRICE = 2000
CHANNEL_DEBUG_PRICE = 1500

# 数据点位梯级定价表（业务计算规则，保留在代码中）
POINT_PRICE_TIERS = [
    (1000,  35,  24.5), (2000,  34,  23.8), (3000,  33,  23.1),
    (4000,  32,  22.4), (5000,  31,  21.7), (6000,  30,  21.0),
    (7000,  29,  20.3), (8000,  28,  19.6), (9000,  27,  18.9),
    (10000, 26,  18.2), (20000, 25,  17.5), (30000, 24,  16.8),
    (40000, 23,  16.1), (50000, 22,  15.4),
]

# 默认价格目录路径
DEFAULT_CATALOG = Path(__file__).parent.parent / "outputs" / "price_catalog.json"

# 全局价格目录缓存
_catalog_cache = None


def load_price_catalog(path=None):
    """加载价格目录 JSON（带缓存）。日常运行时直接读缓存，不每次调 AI。"""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    if path is None:
        path = DEFAULT_CATALOG
    _catalog_cache = json.loads(Path(path).read_text(encoding="utf-8"))
    return _catalog_cache


def _get_soft(catalog, key):
    """获取软件模块 (标准价, 渠道价)"""
    item = catalog["software"].get(key, {})
    return (item.get("standard_price"), item.get("channel_price"))


def _get_hw(catalog, key):
    """获取硬件 (标准价, 渠道价)"""
    item = catalog["hardware"].get(key, {})
    return (item.get("standard_price"), item.get("channel_price"))


def _get_const(catalog, key):
    """获取施工价格 (标准价, 渠道价)"""
    item = catalog["construction"].get(key, {})
    return (item.get("standard_price"), item.get("channel_price"))


def _find_ct(catalog, current, ct_type, aperture=None):
    """从 catalog.ct_mapping 查找 CT 互感器。
    返回: (model, standard_price, channel_price, is_multi, all_matches)

    匹配策略：
    - 两个都没填 → 返回全部 catalog 条目作为候选
    - 只填了其中一个 → 按填写的字段模糊匹配
    - 两个都填 → 精确匹配
    """
    has_current = bool(current)
    has_type = bool(ct_type)

    if not has_current and not has_type:
        all_entries = catalog["ct_mapping"]
        return (None, None, None, len(all_entries) > 1, all_entries)

    if has_current and has_type:
        candidates = [e for e in catalog["ct_mapping"]
                      if e["current"] == current and e["type"] == ct_type]
    elif has_current:
        candidates = [e for e in catalog["ct_mapping"]
                      if e["current"] == current]
    else:
        candidates = [e for e in catalog["ct_mapping"]
                      if e["type"] == ct_type]

    if not candidates:
        return (None, None, None, False, [])
    if aperture:
        aperture_match = [e for e in candidates if e.get("aperture") == aperture]
        if aperture_match:
            return (aperture_match[0]["model"], aperture_match[0]["standard_price"],
                    aperture_match[0]["channel_price"], len(aperture_match) > 1, aperture_match)
    first = candidates[0]
    is_multi = len(candidates) > 1
    return (first["model"], first["standard_price"], first["channel_price"], is_multi, candidates)


def _get_water(catalog, dn):
    """获取水表信息。返回 dict 或 None。"""
    return catalog["water_meters"].get(dn)


_MEDIUM_CATEGORY_MAP = {
    "水能量计": ["冷/热量表"],
    "能量计": ["冷/热量表"],
    "冷量": ["冷/热量表"],
    "热量": ["冷/热量表"],
    "冷热量": ["冷/热量表"],
    "压缩空气": ["涡街流量计", "差压式流量计", "热式质量流量计"],
    "空气": ["涡街流量计", "差压式流量计", "热式质量流量计"],
    "压差": ["超声波流量计", "涡街流量计"],
    "压损": ["超声波流量计", "涡街流量计"],
    "电磁": ["超声波流量计"],
    "超声波": ["超声波流量计"],
    "涡街": ["涡街流量计"],
    "冷冻水": ["超声波流量计"],
    "冷却水": ["超声波流量计"],
    "冷水": ["超声波流量计"],
    "热水": ["超声波流量计"],
    "水": ["超声波流量计"],
}

_INSTALL_TYPE_MAP = {
    "管段": "管段式",
    "法兰": "管段式",
    "切管": "管段式",
    "管道": "管段式",
    "插入": "插入式",
    "外夹": "外夹式",
    "夹持": "管段式",
}


def _normalize_install_type(raw):
    raw = (raw or "").strip()
    for keyword, canonical in _INSTALL_TYPE_MAP.items():
        if keyword in raw:
            return canonical
    return raw


def _medium_to_categories(medium):
    medium = (medium or "").strip()
    for keyword, categories in _MEDIUM_CATEGORY_MAP.items():
        if keyword in medium:
            return categories
    return None


def _get_flow_meter(catalog, dn, medium="", install_type=""):
    flow_list = catalog.get("flow_meters", [])
    if not flow_list:
        return None, False, []
    try:
        dn_num = int(str(dn).replace("DN", "").replace("dn", ""))
    except (ValueError, TypeError):
        return None, False, []

    candidates = [
        fm for fm in flow_list
        if fm.get("dn_min", 0) <= dn_num <= fm.get("dn_max", 0)
    ]

    categories = _medium_to_categories(medium)
    if categories:
        filtered = [fm for fm in candidates if fm.get("name") in categories]
        if filtered:
            candidates = filtered

    norm_install = _normalize_install_type(install_type)
    if norm_install in ("管段式", "插入式", "外夹式"):
        filtered = [fm for fm in candidates if fm.get("type") == norm_install]
        if filtered:
            candidates = filtered

    if not candidates:
        return None, False, []

    candidates.sort(key=lambda fm: fm.get("channel_price", 0))
    return candidates[0], len(candidates) > 1, candidates


_GENERIC_WORDS = {"分析", "能耗", "能源", "管理", "系统", "功能", "模块", "应用"}

# 调研表选项名称 → 报价体系中实际条目名称片段（用于语义归一化，非价格硬编码）
_OPTION_NAME_ALIASES = {
    "设备能效分析": ["能源效率分析", "能效分析"],
    "能耗对标": ["能源目标管理", "能源对比分析", "基准", "考核"],
    "单位能耗": ["能源效率分析", "单位产品能耗", "单位产值能耗"],
    "能耗强度": ["能源效率分析", "单位产品能耗", "单位产值能耗"],
}


def _core_keywords(text):
    """去除调研表选项中的通用词，保留核心关键词。"""
    core = text
    for w in _GENERIC_WORDS:
        core = core.replace(w, "")
    return core.strip()


def _expand_option_names(raw_alternatives):
    """根据别名表扩展选项名称的同义表述，返回去重后的列表。"""
    expanded = []
    for alt in raw_alternatives:
        if alt not in expanded:
            expanded.append(alt)
        for alias_key, alias_values in _OPTION_NAME_ALIASES.items():
            if alias_key in alt:
                for v in alias_values:
                    if v not in expanded:
                        expanded.append(v)
    return expanded


def _match_optional_module(catalog, option_name):
    """板块七可选项三级降级匹配，仅在 catalog['software'] 中搜索。
    返回匹配列表 [{key, name, brand, model, standard_price, channel_price}]。
    """
    software = catalog.get("software", {})
    raw_alternatives = [p.strip() for p in option_name.split("/") if p.strip()]
    alternatives = _expand_option_names(raw_alternatives)

    # 预计算每个 alternative 的小写形式和核心关键词
    prepared = []
    for alt in alternatives:
        alt_lower = alt.lower()
        core = _core_keywords(alt_lower)
        prepared.append((alt_lower, core if len(core) >= 2 else None))

    pred_budget_kws = ("预测", "预算")
    opt_chars = set(option_name.replace("/", ""))

    matches = []
    for key, item in software.items():
        item_name = (item.get("name", "") or "")
        item_name_lower = item_name.lower()
        search_text = None
        matched = False

        for alt_lower, core in prepared:
            if alt_lower in item_name_lower or item_name_lower in alt_lower:
                matched = True
                break
            if core:
                if search_text is None:
                    item_cat = (item.get("category", "") or "")
                    item_desc = (item.get("description", "") or "")
                    search_text = f"{item_name} {item_cat} {item_desc}".lower()
                if core in search_text:
                    matched = True
                    break

        if not matched:
            continue

        if any(kw in option_name for kw in pred_budget_kws) and "自动分析" in item_name:
            continue

        std_p = item.get("standard_price")
        ch_p = item.get("channel_price")
        if std_p is not None or ch_p is not None:
            matches.append({
                "key": key,
                "name": item_name,
                "brand": item.get("brand", "蘑菇物联"),
                "model": item.get("model", "云智控4.0"),
                "standard_price": std_p,
                "channel_price": ch_p,
                "category": item.get("category", ""),
            })

    if len(matches) > 1:
        for m in matches:
            item_chars = set(m["name"])
            m["_rel"] = len(opt_chars & item_chars)
        best_rel = max(m["_rel"] for m in matches)
        if best_rel > 0:
            threshold = max(1, best_rel - 2)
            matches = [m for m in matches if m["_rel"] >= threshold]
        for m in matches:
            m.pop("_rel", None)

    return matches


def _parse_quantity(qty_text):
    """从数量文本中提取整数，无法解析返回 None。"""
    if not qty_text:
        return None
    m = re.search(r"\d+", str(qty_text))
    return int(m.group()) if m else None


def _check_deployment_conflict(project, scope, matches):
    """检测移动端与部署方式的兼容性冲突。
    同时检查用户填写的 scope 文本和匹配到的 catalog 条目的 category 字段。
    返回 (conflict_note_or_None, deployment_filtered_matches)。
    """
    deployment = (project.get("deployment_mode") or "").lower()
    is_cloud = "云" in deployment or deployment == "cloud"
    is_local = "本地" in deployment or "私有" in deployment or deployment.startswith("private")

    if not is_cloud and not is_local:
        return None, matches

    mobile_matches = [m for m in matches if _is_mobile_item(m)]
    non_mobile_matches = [m for m in matches if not _is_mobile_item(m)]

    if not mobile_matches:
        return None, matches

    def _catalog_is_cloud(m):
        cat = (m.get("category") or "").lower()
        return "云端" in cat or "云部署" in cat

    def _catalog_is_local(m):
        cat = (m.get("category") or "").lower()
        return "本地" in cat or "私有" in cat or "本地化" in cat

    scope_lower = (scope or "").lower()
    scope_says_local = any(kw in scope_lower for kw in ("本地", "app", "安卓", "ios", "android"))
    scope_says_cloud = "云" in scope_lower and ("小程序" in scope_lower or "微信" in scope_lower)

    compatible = []
    incompatible = []
    for m in mobile_matches:
        cat_cloud = _catalog_is_cloud(m)
        cat_local = _catalog_is_local(m)
        if is_cloud and cat_local:
            incompatible.append(m)
        elif is_local and cat_cloud:
            incompatible.append(m)
        else:
            compatible.append(m)

    if scope_says_local and is_cloud:
        return f"部署方式为云端，但移动端填写了本地APP相关描述，请确认", matches
    if scope_says_cloud and is_local:
        return f"部署方式为本地，但移动端填写了云端小程序相关描述，请确认", matches

    if compatible and not incompatible:
        return None, compatible + non_mobile_matches
    if incompatible and not compatible:
        names = "、".join(m.get("name", "") for m in incompatible[:2])
        deploy_text = "云端" if is_cloud else "本地"
        return f"部署方式为{deploy_text}，但匹配到的移动端产品（{names}）需要{('本地' if is_cloud else '云端')}部署，请确认", matches
    if compatible and incompatible:
        return None, compatible + non_mobile_matches

    return None, matches


def _is_mobile_item(m):
    """判断 catalog 条目是否为移动端产品"""
    cat = (m.get("category") or "").lower()
    name = (m.get("name") or "").lower()
    return "移动端" in cat or "移动" in cat or any(
        kw in name for kw in ("小程序", "app", "移动端")
    )


def _get_tax_rates(catalog):
    """从 catalog 读取税率，fallback 13%/6%"""
    tax = catalog.get("tax_info", {})
    return (
        tax.get("software_hardware_rate", 0.13),
        tax.get("construction_rate", 0.06),
        tax.get("template_note", "")
    )


_user_rules_cache = {}


def _read_user_rule(rule_id: str) -> Optional[dict]:
    """从 SKILL.md 的用户规则章节读取指定规则。返回 dict 或 None。"""
    if rule_id in _user_rules_cache:
        return _user_rules_cache[rule_id]

    skill_path = Path(__file__).parent.parent / ".claude" / "skills" / "standard-energy-quote" / "SKILL.md"
    if not skill_path.exists():
        return None

    text = skill_path.read_text(encoding="utf-8")
    in_section = False
    for line in text.splitlines():
        if line.startswith("## 用户规则"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        if line.startswith("|") and rule_id in line and "---" not in line and "规则ID" not in line:
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 5:
                rule = {
                    "id": cells[0],
                    "scope": cells[1],
                    "content": cells[2],
                    "status": cells[3],
                    "effective_date": cells[4],
                }
                _user_rules_cache[rule_id] = rule
                return rule
    return None


def _is_unidirectional(direction: str) -> bool:
    """判断接口方向是否属于标准能管的单向读取。"""
    return "单向" in (direction or "")


def _get_api_item_status(catalog, direction) -> dict:
    """根据接口方向和 catalog 动态决定 API 项的价格和状态。"""
    rule = _read_user_rule("RULE-001")
    cat_item = catalog["software"].get("api_development", {})
    cat_std = cat_item.get("standard_price")
    cat_ch = cat_item.get("channel_price")

    if not _is_unidirectional(direction):
        return {
            "standard_price": cat_std,
            "channel_price": cat_ch,
            "status": "NONSTANDARD",
            "confirm_note": f"接口方向为'{direction}'，超出标准能管（单向读取）范围，需人工评估",
        }

    if rule:
        rule_confirmed = "✅" in rule.get("status", "")
        if rule_confirmed:
            return {
                "standard_price": 20000,
                "channel_price": 20000,
                "status": "AUTO",
                "confirm_note": None,
            }
        else:
            return {
                "standard_price": 20000,
                "channel_price": 20000,
                "status": "CONFIRM",
                "confirm_note": f"RULE-001：统一按2万报价（{rule.get('status', '待确认')}）",
            }

    if cat_std is not None:
        return {
            "standard_price": cat_std,
            "channel_price": cat_ch,
            "status": "AUTO",
            "confirm_note": None,
        }

    return {
        "standard_price": None,
        "channel_price": None,
        "status": "INQUIRY",
        "confirm_note": "API 开发无价格来源，需询价后填入",
    }


def get_point_price(quote_points: int) -> tuple:
    """根据报价点位返回 (标准单价, 渠道单价)，匹配梯级定价表"""
    for limit, std, ch in POINT_PRICE_TIERS:
        if quote_points <= limit:
            return (std, ch)
    return POINT_PRICE_TIERS[-1][1], POINT_PRICE_TIERS[-1][2]


def _classify_zone(text: str) -> str:
    """根据关键词将非标项自动归类到 software / hardware / construction 分区。
    返回 'software' / 'hardware' / 'construction'。
    """
    text_lower = text.lower()
    hw_keywords = ['表', '传感', '网关', '硬件', '设备', '仪表', '云盒', '通讯箱',
                   '流量计', '水表', '电表', '蒸汽', '天然气', '冷机', '阀门']
    ct_keywords = ['施工', '安装', '调试', '培训', '人天', '布线', '敷设', '改造',
                   '接线', '配电']
    for kw in ct_keywords:
        if kw in text_lower:
            return 'construction'
    for kw in hw_keywords:
        if kw in text_lower:
            return 'hardware'
    return 'software'


def _try_match_equipment_price(catalog: dict, name: str, spec: str) -> dict:
    """尝试在报价体系中匹配设备价格。返回含 is_multi 和 all_matches 的 dict，或空 dict。"""
    search_text = f"{name} {spec}".lower()
    matches = []
    for category in ['software', 'hardware']:
        items = catalog.get(category, {})
        if isinstance(items, dict):
            for key, val in items.items():
                item_name = (val.get('name', '') or '').lower()
                if item_name and (item_name in search_text or name.lower() in item_name):
                    std_p = val.get('standard_price')
                    ch_p = val.get('channel_price')
                    if std_p is not None or ch_p is not None:
                        matches.append({
                            'brand': val.get('brand', ''),
                            'model': val.get('model', key),
                            'standard_price': std_p,
                            'channel_price': ch_p,
                        })
    if matches:
        best = dict(matches[0])
        best['is_multi'] = len(matches) > 1
        if len(matches) > 1:
            best['all_matches'] = matches
        return best
    water_meters = catalog.get('water_meters', {})
    if isinstance(water_meters, dict):
        for dn, prices in water_meters.items():
            if dn in spec:
                return {
                    'standard_price': prices.get('standard_price'),
                    'channel_price': prices.get('channel_price'),
                    'is_multi': False,
                }
    return {}


def _match_extra_item(catalog, extra_item):
    """对单个超出默认项在价格目录中匹配。
    extra_item: {type, quantity, customer_artwork, notes}
    返回: (matches, domain) — matches 为匹配列表，domain 为识别到的搜索域
    """
    item_type = extra_item.get("type", "")
    quantity = extra_item.get("quantity", 0) or 0
    customer_artwork = (extra_item.get("customer_artwork", "") or "").strip()
    notes = (extra_item.get("notes", "") or "").strip()

    # ── 1. 确定搜索域 ──
    type_lower = item_type.lower()
    is_dashboard = any(kw in item_type for kw in ("大屏", "看板", "dashboard"))
    is_topology = any(kw in item_type for kw in ("组态", "拓扑", "能流", "topology"))
    is_report = any(kw in item_type for kw in ("报表", "报告", "report"))

    # 搜索文本：类型 + 备注，尽量多提取关键词
    search_text = f"{item_type} {customer_artwork} {notes}"

    # ── 2. 在 catalog 中搜索匹配项 ──
    software = catalog.get("software", {})
    candidates = []

    for key, item in software.items():
        item_name = item.get("name", "") or ""
        item_cat = item.get("category", "") or ""
        item_group = item.get("module_group", "") or ""
        item_desc = item.get("description", "") or ""
        item_search = f"{item_name} {item_cat} {item_group} {item_desc}".lower()

        # 域过滤：优先用 category 字段区分（管理看板/站房组态/定制化报表）
        if is_dashboard:
            if not any(kw in item_cat for kw in ("管理看板", "大屏", "看板", "dashboard")):
                continue
            if any(kw in item_cat for kw in ("组态", "报表")):
                continue  # 排除站房组态和报表条目
        if is_topology:
            if not any(kw in item_cat + item_desc for kw in ("组态", "站房组态", "拓扑", "能流", "topology")):
                continue
        if is_report:
            if not any(kw in item_cat + item_name for kw in ("报表", "报告", "report")):
                continue

        # 对于无法判断域的情况，仅在定制化服务域中搜索
        if not is_dashboard and not is_topology and not is_report:
            if not any(kw in item_cat for kw in ("管理看板", "站房组态", "定制化报表", "定制化大屏", "报表")):
                continue

        # 关键词评分
        score = 0
        keywords = _extract_keywords(search_text)

        for kw in keywords:
            if kw in item_search:
                score += 1

        # 客户供图筛选
        has_artwork_keyword = any(kw in customer_artwork for kw in ("是", "有", "客户提供", "客户供图"))
        item_is_artwork = "客户供图" in item_search or "客户自行提供" in item_search

        if has_artwork_keyword:
            if item_is_artwork:
                score += 3  # 强匹配客户供图
            elif "需UED" in item_search or "建模" in item_search:
                score -= 1  # 不匹配：客户供图不需要建模
        elif customer_artwork and any(kw in customer_artwork for kw in ("否", "无", "不需")):
            if item_is_artwork:
                score -= 3  # 客户不供图，排除客户供图条目
            else:
                score += 1  # 匹配

        # 梯级匹配：组态按quantity找≤max_points的最小梯级
        tier = item.get("tier_info") or {}
        if tier.get("type") == "topology" and quantity > 0:
            max_pts = tier.get("max_points", 0)
            if max_pts >= quantity:
                score += 5  # 能覆盖的梯级
                # 越小越精确：最接近 quantity 的梯级加分更多
                gap = max_pts - quantity
                if gap <= 5:
                    score += 3  # 几乎精确匹配
                elif gap <= 20:
                    score += 1  # 接近匹配
            else:
                score -= 5  # 不能覆盖的梯级

        if tier.get("type") == "report" and quantity > 0:
            max_cnt = tier.get("max_count", 0)
            if max_cnt >= quantity:
                score += 5
                gap = max_cnt - quantity
                if gap <= 2:
                    score += 3
                elif gap <= 5:
                    score += 1
            else:
                score -= 5

        if score > -3:  # 只保留不是完全无关的候选
            candidates.append({
                "key": key,
                "name": item_name,
                "brand": item.get("brand", "蘑菇物联"),
                "model": item.get("model", "云智控4.0"),
                "standard_price": item.get("standard_price"),
                "channel_price": item.get("channel_price"),
                "category": item_cat,
                "tier_info": tier,
                "score": score,
            })

    # ── 3. 按分数排序，过滤低分 ──
    candidates.sort(key=lambda x: x["score"], reverse=True)
    if candidates and candidates[0]["score"] > 0:
        best_score = candidates[0]["score"]
        # 保留所有得分接近的候选（容差3分）
        matches = [c for c in candidates if c["score"] >= max(1, best_score - 4)]
    else:
        matches = []  # 无有效匹配，返回空列表触发 INQUIRY

    # 清理内部字段
    for m in matches:
        m.pop("score", None)

    # 确定 domain
    domain = "大屏" if is_dashboard else ("组态" if is_topology else ("报表" if is_report else "未知"))
    if not is_dashboard and not is_topology and not is_report:
        # 从未分类中推断
        if matches and matches[0].get("category"):
            cat = matches[0]["category"]
            if "大屏" in cat or "看板" in cat:
                domain = "大屏"
            elif "组态" in cat:
                domain = "组态"
            elif "报表" in cat:
                domain = "报表"

    return matches, domain


def _extract_keywords(text):
    """从文本中提取关键词，用于模糊匹配价格目录条目。
    同时提取：完整词组 + 2-3字滑动窗口子串（弥补中文无空格分词的问题）。
    """
    import re as _re
    if not text:
        return []
    # 移除常见分隔符，但保留中文连续字符
    cleaned = _re.sub(r'[，,、/\s≤≥]+', '', text)
    stop = {"的", "了", "是", "在", "和", "与", "或", "及", "等", "为", "以", "可"}
    keywords = []

    # 按数字/英文字母边界切分
    segments = _re.split(r'([A-Za-z0-9]+)', cleaned)
    for seg in segments:
        if not seg:
            continue
        seg = seg.strip()
        if not seg:
            continue
        # 英文/数字段直接添加
        if _re.match(r'^[A-Za-z0-9]+$', seg):
            if len(seg) >= 2:
                keywords.append(seg.lower())
            continue
        # 中文段：加完整段
        if len(seg) >= 2 and seg not in stop:
            keywords.append(seg)
        # 中文段：加2-3字滑动窗口
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                bigram = seg[i:i+2]
                if bigram not in stop:
                    keywords.append(bigram)
            if len(seg) >= 3:
                for i in range(len(seg) - 2):
                    trigram = seg[i:i+3]
                    if trigram not in stop:
                        keywords.append(trigram)

    # 去重，保持顺序
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


def calculate(project: dict, catalog_path=None, tax_mode="exclusive", section9_analysis=None) -> dict:
    """从项目 JSON + price_catalog.json 计算出完整报价底稿。
    tax_mode: 'exclusive'（另算税）| 'inclusive'（含税不另加）
    section9_analysis: 板块八语义分析结果（来自 section9_analyzer.py）
    """
    catalog = load_price_catalog(catalog_path)

    # ---------- 1. 表计统计 ----------
    em = project["existing_meters"]

    total_electric = (
        em["electric_accessible"] + em["electric_need_retrofit"]
        + sum(m["quantity"] for m in project["new_meters"]["electric"])
    )
    total_water = (
        em["water_accessible"] + em["water_need_retrofit"]
        + sum(m["quantity"] for m in project["new_meters"]["water"])
    )

    # 既有流体类表计（rows 20-25 对应的 6 种类型，C列+D列）
    existing_fluid = (
        em.get("flow_cooling_accessible", 0) + em.get("flow_cooling_need_retrofit", 0)
        + em.get("heat_accessible", 0) + em.get("heat_need_retrofit", 0)
        + em.get("flow_air_accessible", 0) + em.get("flow_air_need_retrofit", 0)
        + em.get("steam_accessible", 0) + em.get("steam_need_retrofit", 0)
        + em.get("gas_accessible", 0) + em.get("gas_need_retrofit", 0)
        + em.get("other_accessible", 0) + em.get("other_need_retrofit", 0)
    )

    # 新增流量计/冷热量表
    new_flow = sum(m["quantity"] for m in project["new_meters"]["flow_meters"])

    # 流体类表计总数 = 既有水表 + 新增水表 + 既有流体类 + 新增流量计
    total_fluid = total_water + existing_fluid + new_flow
    third_party_count = len(project["third_party_systems"])

    # ---------- 2. 软件点位 ----------
    raw_points = (
        total_electric * POINTS_PER_ELECTRIC_METER
        + total_fluid * POINTS_PER_FLUID_METER
        + third_party_count * POINTS_PER_THIRD_PARTY_SYSTEM
    )
    quote_points = math.ceil(raw_points / POINTS_ROUND_TO) * POINTS_ROUND_TO

    # ---------- 3. 云盒 ----------
    electric_cloudbox = math.ceil(total_electric / ELECTRIC_METERS_PER_CLOUDBOX)
    # 流体类表计 1:1 配云盒（水表+流量计+热量表+蒸汽+天然气）
    fluid_cloudbox = total_fluid
    total_cloudbox = electric_cloudbox + fluid_cloudbox

    # ---------- 4. CT 映射（按规格合并，避免同规格多行重复） ----------
    ct_grouped = {}  # key: (current, ct_type, aperture) -> {quantity, model, prices, locations, is_multi}
    for meter in project["new_meters"]["electric"]:
        model, std_price, ch_price, is_multi, ct_candidates = _find_ct(
            catalog,
            meter["ct_current"], meter["ct_type"],
            meter.get("ct_aperture")
        )
        group_key = (meter["ct_current"], meter["ct_type"], meter.get("ct_aperture"), model)
        if group_key not in ct_grouped:
            ct_current = meter.get("ct_current")
            ct_type = meter.get("ct_type", "")
            if ct_current and ct_type:
                spec = f"{ct_current}A/{ct_type}"
            else:
                spec = "规格未填写"
            ct_grouped[group_key] = {
                "quantity": 0,
                "spec": spec,
                "model": model or "待确认",
                "brand": "安科瑞",
                "unit": "个",
                "standard_price": std_price,
                "channel_price": ch_price,
                "is_multi": is_multi,
                "locations": [],
                "ct_candidates": ct_candidates,
                "ct_current": ct_current,
                "ct_type": ct_type,
            }
        ct_grouped[group_key]["quantity"] += meter["quantity"] * 3
        ct_grouped[group_key]["locations"].append(meter["location"])
        if is_multi:
            ct_grouped[group_key]["is_multi"] = True

    ct_items = []
    for _key, g in ct_grouped.items():
        if g["is_multi"]:
            status = "CONFIRM"
            if not g.get("ct_current") and not g.get("ct_type"):
                note = "调研表未指定CT电流规格和形式，请从报价体系中选择"
            else:
                note = "有多个匹配选项，请确认"
        elif g["model"] == "待确认":
            status = "INQUIRY"
            note = "CT规格未在报价体系中找到，需确认型号并询价"
        else:
            status = "AUTO"
            note = None
        ct_item = {
            "location": "、".join(g["locations"]),
            "quantity": g["quantity"],
            "spec": g["spec"],
            "model": g["model"],
            "brand": g["brand"],
            "unit": g["unit"],
            "standard_price": g["standard_price"],
            "channel_price": g["channel_price"],
            "status": status,
            "confirm_note": note,
            "ct_type": g.get("ct_type", ""),
        }
        if status == "CONFIRM" and g.get("ct_candidates"):
            ct_item["candidates"] = [
                {"brand": "安科瑞", "model": c["model"],
                 "standard_price": c["standard_price"],
                 "channel_price": c["channel_price"],
                 "aperture": c.get("aperture", ""),
                 "current": c.get("current", ""),
                 "type": c.get("type", "")}
                for c in g["ct_candidates"]
            ]
        elif status == "CONFIRM" and not g.get("ct_candidates"):
            seen = set()
            ct_item["candidates"] = []
            for c in catalog["ct_mapping"]:
                key = c["current"]
                if key not in seen:
                    seen.add(key)
                    ct_item["candidates"].append({
                        "brand": "安科瑞", "model": c["model"],
                        "standard_price": c["standard_price"],
                        "channel_price": c["channel_price"],
                        "aperture": c.get("aperture", ""),
                        "current": c.get("current", ""),
                        "type": c.get("type", ""),
                    })
        ct_items.append(ct_item)

    # ---------- 5. 水表映射 ----------
    water_items = []
    for meter in project["new_meters"]["water"]:
        wm = _get_water(catalog, meter["dn"])
        if wm is not None:
            water_items.append({
                "location": meter["location"],
                "dn": meter["dn"],
                "quantity": meter["quantity"],
                "brand": wm["brand"],
                "model": wm["model"],
                "unit": "个",
                "standard_price": wm["standard_price"],
                "channel_price": wm["channel_price"],
                "install_price": wm.get("install_price", 500),
                "status": "AUTO"
            })
        else:
            water_items.append({
                "location": meter["location"],
                "dn": meter["dn"],
                "quantity": meter["quantity"],
                "brand": "待询价",
                "model": "待询价",
                "unit": "个",
                "standard_price": None,
                "channel_price": None,
                "install_price": None,
                "status": "INQUIRY"
            })

    # ---------- 5.5 流量计/冷热量表映射 ----------
    flow_meter_items = []
    for meter in project["new_meters"]["flow_meters"]:
        fm, is_multi, flow_candidates = _get_flow_meter(
            catalog, meter["dn"],
            medium=meter.get("medium", ""),
            install_type=meter.get("install_type", "")
        )
        if fm is not None:
            status = "CONFIRM" if is_multi else "AUTO"
            fm_item = {
                "location": meter.get("location", ""),
                "medium": meter.get("medium", "流量计"),
                "dn": meter["dn"],
                "quantity": meter["quantity"],
                "install_type": meter.get("install_type", ""),
                "brand": fm["brand"],
                "model": fm["model"],
                "unit": "个",
                "standard_price": fm["standard_price"],
                "channel_price": fm["channel_price"],
                "install_price": fm.get("install_price", 800),
                "status": status,
                "confirm_note": "同管径有多种型号可选，请确认" if is_multi else None,
            }
            if status == "CONFIRM" and flow_candidates:
                fm_item["candidates"] = [
                    {"brand": c.get("brand", ""), "model": c["model"],
                     "name": c.get("name", ""), "type": c.get("type", ""),
                     "standard_price": c.get("standard_price"),
                     "channel_price": c.get("channel_price"),
                     "install_price": c.get("install_price", 800)}
                    for c in flow_candidates
                ]
            flow_meter_items.append(fm_item)
        else:
            flow_meter_items.append({
                "location": meter.get("location", ""),
                "medium": meter.get("medium", "流量计"),
                "dn": meter["dn"],
                "quantity": meter["quantity"],
                "install_type": meter.get("install_type", ""),
                "brand": "待询价",
                "model": "待询价",
                "unit": "个",
                "standard_price": None,
                "channel_price": None,
                "install_price": None,
                "status": "INQUIRY",
            })


    # ---------- 6. 通讯线估算 ----------
    # 配电室电表按每块约3米做内部估算（含既有+新增）
    new_electric_count = sum(m["quantity"] for m in project["new_meters"]["electric"])
    cable_meters = (total_electric + total_fluid) * 3
    # 默认所有仪表算集中区域（配电房）
    cable_points = total_electric + total_fluid

    # ---------- 7. 调试 ----------
    debug_days = total_cloudbox * DEBUG_DAYS_PER_CLOUDBOX

    # ---------- 8. 附加模块 ----------
    opts = project["optional_modules"]
    extra_dashboards = max(0, opts.get("extra_dashboards", 0))
    extra_topology = max(0, opts.get("extra_topology", 0))
    extra_reports = max(0, opts.get("extra_reports", 0))
    extra_items = opts.get("extra_items", [])

    # ---------- 组装内部底稿 ----------
    # 添加软件基础项时先查梯级点价
    point_std, point_ch = get_point_price(quote_points)

    result = {
        "project_info": {
            "client_name": project["client_name"],
            "project_name": project["project_name"],
            "project_location": project["project_location"],
            "deployment_mode": project["deployment_mode"],
        },
        "calculations": {
            "total_electric_meters": total_electric,
            "total_water_meters": total_water,
            "total_fluid_meters": total_fluid,
            "third_party_count": third_party_count,
            "raw_points": raw_points,
            "quote_points": quote_points,
            "electric_cloudbox": electric_cloudbox,
            "fluid_cloudbox": fluid_cloudbox,
            "total_cloudbox": total_cloudbox,
            "cable_meters": cable_meters,
            "cable_points": cable_points,
            "debug_days": debug_days,
        },
        "software_items": [
            {
                "module": "系统基础平台", "quantity": 1, "unit": "套",
                "description": "能源管理系统基础平台，B/S架构",
                "brand": "蘑菇物联", "model": "云智控4.0",
                "standard_price": _get_soft(catalog, "platform")[0],
                "channel_price": _get_soft(catalog, "platform")[1],
                "status": "AUTO",
                "source": "platform"
            },
            {
                "module": "数据点位", "quantity": quote_points, "unit": "点",
                "description": "能源管理系统数据点位授权",
                "brand": "蘑菇物联", "model": "云智控4.0",
                "standard_price": point_std,
                "channel_price": point_ch,
                "status": "AUTO",
                "source": "platform"
            },
        ],
        "hardware_items": [
            {
                "module": "能管云盒", "quantity": total_cloudbox, "unit": "个",
                "description": "现场数据采集、边缘通讯与数据上传",
                "brand": "蘑菇物联", "model": "Maxw5Pro-C1",
                "standard_price": _get_hw(catalog, "cloud_box")[0],
                "channel_price": _get_hw(catalog, "cloud_box")[1],
                "status": "AUTO"
            },
            {
                "module": "通讯箱", "quantity": total_cloudbox, "unit": "个",
                "description": "挂墙安装通讯箱（报价体系无此硬件价格，需人工询价）",
                "brand": "国产优质", "model": "/",
                "standard_price": _get_hw(catalog, "comm_box")[0],
                "channel_price": _get_hw(catalog, "comm_box")[1],
                "status": "AUTO" if _get_hw(catalog, "comm_box")[0] is not None else "INQUIRY"
            },
            {
                "module": "开关电源", "quantity": total_cloudbox, "unit": "个",
                "description": "配套能管云盒供电",
                "brand": "国产优质", "model": "/",
                "standard_price": _get_hw(catalog, "power_supply")[0],
                "channel_price": _get_hw(catalog, "power_supply")[1],
                "status": "AUTO"
            },
            {
                "module": "空气开关", "quantity": total_cloudbox, "unit": "个",
                "description": "配套能管云盒供电保护",
                "brand": "国产优质", "model": "/",
                "standard_price": _get_hw(catalog, "air_switch")[0],
                "channel_price": _get_hw(catalog, "air_switch")[1],
                "status": "AUTO"
            },
            {
                "module": "三相多功能电表", "quantity": new_electric_count, "unit": "个",
                "description": "新增配电回路电能数据采集",
                "brand": "安科瑞", "model": "ADL400",
                "standard_price": _get_hw(catalog, "adl400_meter")[0],
                "channel_price": _get_hw(catalog, "adl400_meter")[1],
                "status": "AUTO"
            },
            {
                "module": "屏蔽双绞线", "quantity": cable_meters, "unit": "米",
                "description": "用于RS485通讯接线，RVSP2×1.0",
                "brand": "国产优质", "model": "RVSP2×1.0",
                "standard_price": _get_hw(catalog, "cable_per_meter")[0],
                "channel_price": _get_hw(catalog, "cable_per_meter")[1],
                "status": "AUTO" if project["project_notes"].get("has_site_plan") is True else "CONFIRM"
            },
        ],
        "construction_items": [
            {
                "module": "新装电表施工", "quantity": new_electric_count, "unit": "台",
                "description": "含设备安装及二次接线",
                "standard_price": _get_const(catalog, "meter_install")[0],
                "channel_price": _get_const(catalog, "meter_install")[1],
                "status": "AUTO"
            },
            {
                "module": "通讯箱安装", "quantity": total_cloudbox, "unit": "台",
                "description": "挂墙安装，固定通讯箱到指定位置",
                "standard_price": _get_const(catalog, "cloudbox_install")[0],
                "channel_price": _get_const(catalog, "cloudbox_install")[1],
                "status": "AUTO"
            },
            {
                "module": "通讯线敷设(集中区域)", "quantity": cable_points, "unit": "点",
                "description": "配电房、站房等仪表通讯线敷设",
                "standard_price": _get_const(catalog, "cable_concentrated")[0],
                "channel_price": _get_const(catalog, "cable_concentrated")[1],
                "status": "AUTO"
            },
            {
                "module": "系统调试+培训", "quantity": debug_days, "unit": "人天",
                "description": "现场设备接入、系统联调、基础培训",
                "standard_price": STANDARD_DEBUG_PRICE,
                "channel_price": CHANNEL_DEBUG_PRICE,
                "status": "AUTO"
            },
        ],
        "tax_confirm_item": None,
        "tax_warning": None,
        "ct_items": ct_items,
        "water_meter_items": water_items,
        "flow_meter_items": flow_meter_items,
        "optional_modules": {
            "selected_modules": opts.get("selected_modules", []),
            "extra_dashboards": extra_dashboards,
            "extra_topology": extra_topology,
            "extra_reports": extra_reports,
            "extra_items": extra_items,
        },
        "third_party_systems": project["third_party_systems"],
        "project_notes": project["project_notes"],
        "api_count": third_party_count,
        "price_source": catalog.get("_meta", {}).get("source_name", "未知"),
        "price_catalog_meta": catalog.get("_meta", {}),
    }

    # 添加水表和 CT 到 hardware_items
    for wm in result["water_meter_items"]:
        result["hardware_items"].append({
            "module": f"RS485光电直读水表({wm['dn']})",
            "quantity": wm["quantity"],
            "unit": "个",
            "description": f"新增水计量点数据采集，{wm['dn']}",
            "brand": wm["brand"],
            "model": wm["model"],
            "standard_price": wm["standard_price"],
            "channel_price": wm["channel_price"],
            "status": wm["status"],
        })
        wm_install_status = wm["status"] if wm["status"] == "INQUIRY" else "AUTO"
        result["construction_items"].append({
            "module": f"水表安装({wm['dn']})",
            "quantity": wm["quantity"],
            "unit": "台",
            "description": f"含水表安装及现场改造，{wm['dn']}",
            "standard_price": wm["install_price"],
            "channel_price": wm["install_price"],
            "status": wm_install_status,
        })

    # 添加流量计到 hardware_items + construction_items
    for fm in result["flow_meter_items"]:
        medium = fm.get("medium", "流量计")
        fm_hw = {
            "module": f"{medium}({fm['dn']})",
            "quantity": fm["quantity"],
            "unit": "个",
            "description": f"新增{medium}数据采集，{fm['dn']}",
            "brand": fm["brand"],
            "model": fm["model"],
            "standard_price": fm["standard_price"],
            "channel_price": fm["channel_price"],
            "status": fm["status"],
        }
        if fm.get("candidates"):
            fm_hw["candidates"] = fm["candidates"]
        if fm.get("confirm_note"):
            fm_hw["confirm_note"] = fm["confirm_note"]
        result["hardware_items"].append(fm_hw)
        install_status = fm["status"] if fm["status"] == "INQUIRY" else "AUTO"
        result["construction_items"].append({
            "module": f"{medium}安装({fm['dn']})",
            "quantity": fm["quantity"],
            "unit": "台",
            "description": f"含{medium}安装及现场改造，{fm['dn']}",
            "standard_price": fm["install_price"],
            "channel_price": fm["install_price"],
            "status": install_status,
        })

    for ct in result["ct_items"]:
        ct_type_name = ct.get("ct_type", "") or "电流互感器"
        if ct_type_name != "电流互感器":
            ct_type_name = f"{ct_type_name}电流互感器"
        ct_hw = {
            "module": f"{ct_type_name}({ct['spec']})",
            "quantity": ct["quantity"],
            "unit": "个",
            "description": f"配套新增电表使用，{ct['spec']}",
            "brand": ct["brand"],
            "model": ct["model"],
            "standard_price": ct["standard_price"],
            "channel_price": ct["channel_price"],
            "status": ct["status"],
        }
        if ct.get("candidates"):
            ct_hw["candidates"] = ct["candidates"]
        if ct.get("confirm_note"):
            ct_hw["confirm_note"] = ct["confirm_note"]
        result["hardware_items"].append(ct_hw)

    # ---------- 板块七可选软件动态匹配 ----------
    selected_modules = opts.get("selected_modules", [])
    for opt in selected_modules:
        opt_name = opt.get("name", "").strip()
        scope = opt.get("scope", "")
        qty_text = opt.get("quantity_name", "")

        needs_confirm = False
        qty = _parse_quantity(qty_text)
        if qty is None:
            qty = 1
            needs_confirm = True

        matches = _match_optional_module(catalog, opt_name)

        is_mobile_opt = any(kw in opt_name for kw in ("移动端", "手机", "APP", "小程序"))
        has_mobile_match = any(_is_mobile_item(m) for m in matches)

        conflict = None
        if (is_mobile_opt or has_mobile_match) and matches:
            conflict, matches = _check_deployment_conflict(project, scope, matches)

        if conflict:
            status = "BLOCKED"
            confirm_note = conflict
        elif not matches:
            status = "INQUIRY"
            confirm_note = "报价体系软件平台中无此项，需询价"
        elif len(matches) == 1 and not needs_confirm:
            status = "AUTO"
            confirm_note = None
        else:
            status = "CONFIRM"
            if needs_confirm:
                confirm_note = f"数量/名称未填写，默认1套，请确认"
            elif len(matches) > 1:
                confirm_note = f"匹配到 {len(matches)} 个候选模块，请选择"
            else:
                confirm_note = None

        best = matches[0] if matches else {}
        item = {
            "module": best.get("name", opt_name),
            "quantity": qty,
            "unit": "套",
            "description": opt.get("customer_request", "") or best.get("name", opt_name),
            "brand": best.get("brand", ""),
            "model": best.get("model", ""),
            "standard_price": best.get("standard_price"),
            "channel_price": best.get("channel_price"),
            "status": status,
            "source": "optional",
        }
        if confirm_note:
            item["confirm_note"] = confirm_note
        if status == "CONFIRM" and len(matches) > 1:
            item["candidates"] = matches
        result["software_items"].append(item)

    # ---------- 超出默认（大屏/组态/报表） ----------
    # 优先使用结构化 extra_items，否则降级为旧的数字字段
    if extra_items:
        for ei in extra_items:
            qty = ei.get("quantity", 0) or 0
            if qty <= 0:
                continue

            matches, domain = _match_extra_item(catalog, ei)

            # 状态判定
            if not matches:
                status = "INQUIRY"
                confirm_note = f"报价体系{domain}区域中未找到与'{ei.get('type','')}'匹配的条目，需询价"
            elif len(matches) == 1:
                status = "AUTO"
                confirm_note = None
            else:
                status = "CONFIRM"
                confirm_note = f"匹配到 {len(matches)} 个候选{domain}条目，请选择"

            best = matches[0] if matches else {}
            ei_type = ei.get("type", "未指定类型")

            # 确定单位
            if domain == "报表":
                unit = "张"
            elif domain == "组态":
                unit = "页"
            elif domain == "大屏":
                unit = "页"
            else:
                unit = "项"

            item = {
                "module": f"定制化{domain}(额外)",
                "quantity": qty,
                "unit": unit,
                "description": ei.get("notes", "") or f"超出默认的额外{domain}：{ei_type}",
                "brand": best.get("brand", "蘑菇物联"),
                "model": best.get("model", "云智控4.0"),
                "standard_price": best.get("standard_price"),
                "channel_price": best.get("channel_price"),
                "status": status,
                "source": "extra",
            }
            if confirm_note:
                item["confirm_note"] = confirm_note
            if status == "CONFIRM" and len(matches) > 1:
                item["candidates"] = [
                    {"name": m["name"], "brand": m.get("brand", ""), "model": m.get("model", ""),
                     "standard_price": m.get("standard_price"), "channel_price": m.get("channel_price")}
                    for m in matches
                ]
            result["software_items"].append(item)
    else:
        # 向后兼容：旧的数字字段模式
        if extra_reports > 0:
            result["software_items"].append({
                "module": "定制化报表(额外)", "quantity": extra_reports, "unit": "张",
                "description": "超出默认3张标准报表的额外报表",
                "brand": "蘑菇物联", "model": "云智控4.0",
                "standard_price": _get_soft(catalog, "extra_report")[0],
                "channel_price": _get_soft(catalog, "extra_report")[1],
                "status": "AUTO",
                "source": "extra"
            })

        if extra_dashboards > 0:
            result["software_items"].append({
                "module": "定制化大屏(额外)", "quantity": extra_dashboards, "unit": "页",
                "description": "超出默认1张能源大屏的额外大屏",
                "brand": "蘑菇物联", "model": "云智控4.0",
                "standard_price": _get_soft(catalog, "extra_dashboard")[0],
                "channel_price": _get_soft(catalog, "extra_dashboard")[1],
                "status": "AUTO",
                "source": "extra"
            })

        if extra_topology > 0:
            result["software_items"].append({
                "module": "组态/能流拓扑(额外)", "quantity": extra_topology, "unit": "页",
                "description": "超出默认3张组态/能流拓扑的额外页面",
                "brand": "蘑菇物联", "model": "云智控4.0",
                "standard_price": _get_soft(catalog, "extra_topology")[0],
                "channel_price": _get_soft(catalog, "extra_topology")[1],
                "status": "AUTO",
                "source": "extra"
            })

    # 添加第三方系统 API（动态判断状态和价格）
    for sys in project["third_party_systems"]:
        api_status = _get_api_item_status(catalog, sys["direction"])
        result["software_items"].append({
            "module": f"第三方接口开发({sys['name']})",
            "quantity": 1, "unit": "套",
            "description": f"与{sys['name']}进行数据对接，{sys['direction']}",
            "brand": "蘑菇物联", "model": "云智控4.0",
            "standard_price": api_status["standard_price"],
            "channel_price": api_status["channel_price"],
            "status": api_status["status"],
            "confirm_note": api_status["confirm_note"],
            "source": "platform",
        })

    # ---------- 板块八语义分析结果注入 ----------
    if section9_analysis and not section9_analysis.get('is_standard', True):
        for ns_item in section9_analysis.get('nonstandard_items', []):
            keyword = ns_item.get('keyword', '未知')
            context = ns_item.get('context', '')
            severity = ns_item.get('severity', 'hard')
            zone = _classify_zone(keyword + ' ' + context)
            target_key = f"{zone}_items"
            result[target_key].append({
                "module": f"[非标] {keyword}",
                "quantity": 1, "unit": "项",
                "description": context or f"板块八检测到非标需求: {keyword}",
                "brand": "", "model": "",
                "standard_price": None,
                "channel_price": None,
                "status": "NONSTANDARD",
                "confirm_note": f"板块八语义分析: {keyword} (severity={severity})，需手动定价或转非标评估",
                "section9_zone": zone,
                "source": "section9",
            })

        for eq_item in section9_analysis.get('equipment_specs', []):
            eq_name = eq_item.get('name', '未知设备')
            eq_spec = eq_item.get('spec', '')
            zone = _classify_zone(eq_name + ' ' + eq_spec)
            target_key = f"{zone}_items"
            matched_price = _try_match_equipment_price(catalog, eq_name, eq_spec)
            if matched_price:
                if matched_price.get('is_multi'):
                    eq_status = "CONFIRM"
                    eq_note = f"板块八设备'{eq_name}'在报价体系中有多个匹配项，请确认具体型号"
                else:
                    eq_status = "AUTO"
                    eq_note = None
            else:
                eq_status = "INQUIRY"
                eq_note = f"板块八提到的设备'{eq_name}'无匹配价格，需询价"
            s9_item = {
                "module": f"[板块八] {eq_name}",
                "quantity": 1, "unit": "台",
                "description": eq_spec or f"板块八备注中提到的设备: {eq_name}",
                "brand": "", "model": eq_spec,
                "standard_price": matched_price.get('standard_price'),
                "channel_price": matched_price.get('channel_price'),
                "status": eq_status,
                "confirm_note": eq_note,
                "section9_zone": zone,
                "source": "section9",
            }
            if eq_status == "CONFIRM" and matched_price.get('all_matches'):
                s9_item["candidates"] = matched_price['all_matches']
            result[target_key].append(s9_item)

    # ---------- 汇总计算 ----------
    def calc_totals(items):
        std_total = sum((i["standard_price"] or 0) * i["quantity"] for i in items)
        ch_total = sum((i["channel_price"] or 0) * i["quantity"] for i in items)
        return std_total, ch_total

    sw_std, sw_ch = calc_totals(result["software_items"])
    hw_std, hw_ch = calc_totals(result["hardware_items"])
    ct_std, ct_ch = calc_totals(result["construction_items"])

    # 税费: 从 catalog 读取税率（可配置，不硬编码）
    tax_rate_sw_hw, tax_rate_ct, tax_template_note = _get_tax_rates(catalog)

    # 税前小计
    subtotal_sw_hw_std = sw_std + hw_std
    subtotal_sw_hw_ch = sw_ch + hw_ch
    subtotal_ct_std = ct_std
    subtotal_ct_ch = ct_ch
    subtotal_all_std = subtotal_sw_hw_std + subtotal_ct_std
    subtotal_all_ch = subtotal_sw_hw_ch + subtotal_ct_ch

    # 按类别计算税额
    tax_sw_hw_std = round(subtotal_sw_hw_std * tax_rate_sw_hw, 2)
    tax_sw_hw_ch = round(subtotal_sw_hw_ch * tax_rate_sw_hw, 2)
    tax_ct_std = round(subtotal_ct_std * tax_rate_ct, 2)
    tax_ct_ch = round(subtotal_ct_ch * tax_rate_ct, 2)

    if tax_mode == "inclusive":
        # 含税模式：单价已含税，不另加税
        tax_std, tax_ch = 0.0, 0.0
        grand_std = subtotal_all_std
        grand_ch = subtotal_all_ch
    else:
        # 未税模式（默认）：税前价 + 另算增值税
        tax_std = tax_sw_hw_std + tax_ct_std
        tax_ch = tax_sw_hw_ch + tax_ct_ch
        grand_std = subtotal_all_std + tax_std
        grand_ch = subtotal_all_ch + tax_ch

    # 税费明细（供审核台展示）
    result["tax_breakdown"] = {
        "tax_mode": tax_mode,
        "rates": {
            "software_hardware": tax_rate_sw_hw,
            "construction": tax_rate_ct,
        },
        "pre_tax": {
            "software_hardware_standard": round(subtotal_sw_hw_std, 2),
            "software_hardware_channel": round(subtotal_sw_hw_ch, 2),
            "construction_standard": round(subtotal_ct_std, 2),
            "construction_channel": round(subtotal_ct_ch, 2),
            "subtotal_standard": round(subtotal_all_std, 2),
            "subtotal_channel": round(subtotal_all_ch, 2),
        },
        "tax_amount": {
            "software_hardware_standard": tax_sw_hw_std,
            "software_hardware_channel": tax_sw_hw_ch,
            "construction_standard": tax_ct_std,
            "construction_channel": tax_ct_ch,
            "total_standard": round(tax_std, 2),
            "total_channel": round(tax_ch, 2),
        },
        "post_tax": {
            "grand_total_standard": round(grand_std, 2),
            "grand_total_channel": round(grand_ch, 2),
        },
        "pricing_basis": catalog.get("tax_info", {}).get("pricing_basis", ""),
        "template_note": tax_template_note,
    }

    result["totals"] = {
        "software_standard": round(sw_std, 2),
        "software_channel": round(sw_ch, 2),
        "hardware_standard": round(hw_std, 2),
        "hardware_channel": round(hw_ch, 2),
        "construction_standard": round(ct_std, 2),
        "construction_channel": round(ct_ch, 2),
        "tax_standard": round(tax_std, 2),
        "tax_channel": round(tax_ch, 2),
        "grand_total_standard": round(grand_std, 2),
        "grand_total_channel": round(grand_ch, 2),
    }
    result["tax_mode"] = tax_mode
    result["tax_template_note"] = tax_template_note

    # 条件化税费确认：检测 template_note 与实际 tax_mode 是否矛盾
    # "含税" 类措辞 + exclusive 模式 = 矛盾 → BLOCKED
    # "税前/另算" 类措辞 + exclusive 模式 = 一致 → 无需确认
    note_says_inclusive = ("含" in tax_template_note and "税" in tax_template_note
                           and "另算" not in tax_template_note
                           and "税前" not in tax_template_note)
    note_says_exclusive = "另算" in tax_template_note or "税前" in tax_template_note

    tax_confirm_mismatch = False
    if tax_mode == "exclusive" and note_says_inclusive:
        tax_confirm_mismatch = True
        mismatch_desc = (
            f"报价模板标注价格已含税（'{tax_template_note}'），"
            f"但当前系统按税前价另算税费（软硬件{tax_rate_sw_hw*100:.0f}%、施工{tax_rate_ct*100:.0f}%）。"
            f"请确认：单价是含税还是税前？"
        )
    elif tax_mode == "inclusive" and note_says_exclusive:
        tax_confirm_mismatch = True
        mismatch_desc = (
            f"报价模板标注价格为税前价（'{tax_template_note}'），"
            f"但当前系统按含税模式处理（不另加税）。"
            f"请确认：单价是含税还是税前？"
        )

    if tax_confirm_mismatch:
        result["tax_confirm_item"] = {
            "module": "税费口径确认",
            "quantity": 1,
            "unit": "项",
            "description": mismatch_desc,
            "standard_price": None,
            "channel_price": None,
            "status": "BLOCKED",
            "confirm_note": "税费口径与模板描述矛盾，请确认后选择正确的税费模式",
        }
        result["tax_warning"] = {
            "status": "BLOCKED",
            "message": mismatch_desc,
        }
    else:
        result["tax_confirm_item"] = None
        result["tax_warning"] = None

    # 状态统计
    all_items = result["software_items"] + result["hardware_items"] + result["construction_items"]
    # 税费确认项纳入统计
    tax_item = result.get("tax_confirm_item")
    if tax_item:
        all_items.append(tax_item)
    result["status_summary"] = {
        "AUTO": sum(1 for i in all_items if i["status"] == "AUTO"),
        "CONFIRM": sum(1 for i in all_items if i["status"] == "CONFIRM"),
        "INQUIRY": sum(1 for i in all_items if i["status"] == "INQUIRY"),
        "NONSTANDARD": sum(1 for i in all_items if i["status"] == "NONSTANDARD"),
        "BLOCKED": sum(1 for i in all_items if i["status"] == "BLOCKED"),
    }

    return result


if __name__ == "__main__":
    import sys
    project_path = sys.argv[1] if len(sys.argv) > 1 else "sample_project.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "outputs/internal_bottom_sheet.json"

    project = json.loads(Path(project_path).read_text(encoding="utf-8"))
    result = calculate(project)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[OK] 内部底稿已生成: {output_path}")
    print(f"    标准价总计: {result['totals']['grand_total_standard']:,.2f}")
    print(f"    渠道价总计: {result['totals']['grand_total_channel']:,.2f}")
    print(f"    状态: AUTO={result['status_summary']['AUTO']} "
          f"CONFIRM={result['status_summary']['CONFIRM']} "
          f"INQUIRY={result['status_summary']['INQUIRY']} "
          f"NONSTANDARD={result['status_summary']['NONSTANDARD']} "
          f"BLOCKED={result['status_summary']['BLOCKED']}")
