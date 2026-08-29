"""
从报价体系 Excel 构建 price_catalog.json
用法: python scripts/build_price_catalog.py [excel_path] [--force]
      excel_path 默认: 00_sample/报价模板/2025年云智控报价体系-全产品线11.xlsx
      --force: 强制重新生成，忽略缓存
"""
import sys, io, json, os, re
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_EXCEL = PROJECT_ROOT / "00_sample" / "报价模板" / "2025年云智控报价体系-全产品线11.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "quote" / "price_catalog.json"

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


def validate_anchors(catalog):
    """校验锚点价格"""
    failures = []
    for path, expected in ANCHORS.items():
        actual = deep_get(catalog, path)
        if actual is None:
            failures.append(f"  MISSING: {path} (expected {expected})")
        elif actual != expected:
            failures.append(f"  MISMATCH: {path} got {actual}, expected {expected}")
    return failures


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
        from core.quote.skill_caller import SkillCaller

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


def build_local(excel_path: str) -> dict:
    """本地解析 Excel（AI 不可用时的降级方案）"""
    print("[LOCAL] 使用本地解析构建价格目录...")
    import openpyxl
    from datetime import datetime

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

    # ── 软件: 【软件】平台 sheet（动态全量收录，处理合并单元格）──
    if "【软件】平台" in wb.sheetnames:
        ws = wb["【软件】平台"]
        used_keys = set()
        last_module = ""
        last_category = ""

        # 兼容旧 key 的映射表
        compat_map = {
            "基础平台": "platform", "系统基础平台": "platform",
            "批次单耗": "batch_analysis", "批次能耗": "batch_analysis",
            "移动端": "mobile_cloud", "微信小程序": "mobile_cloud",
            "定制化报表": "extra_report", "定制报表": "extra_report",
            "定制化大屏": "extra_dashboard", "定制大屏": "extra_dashboard",
            "站房组态": "extra_topology", "能流拓扑": "extra_topology",
            "标准API数据输出": "api_development", "接口开发": "api_development",
        }

        for r in range(3, ws.max_row + 1):
            raw_module = cell(ws, r, 1)
            raw_category = cell(ws, r, 2)
            func = cell(ws, r, 3)
            config_type = cell(ws, r, 4)  # 标配/选配

            # 追踪合并单元格：空模块名 = 属于上一个模块
            if raw_module and str(raw_module).strip() and str(raw_module) != "None":
                last_module = str(raw_module).strip()
            if raw_category and str(raw_category).strip() and str(raw_category) != "None":
                last_category = str(raw_category).strip()

            if not last_module or "总计" in last_module:
                continue

            # 功能描述（用于子项识别）
            func_str = str(func or "").strip()
            if func_str == "None":
                func_str = ""

            std_price = cell(ws, r, 12)
            ch_price = cell(ws, r, 13)
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
            item_name = func_str if func_str else last_module
            if not item_name or item_name == "None":
                continue

            # 生成唯一 key
            import re as _re
            name_key = _re.sub(r'[^\w]', '_', item_name).lower().strip('_')
            if not name_key:
                name_key = f"item_r{r}"

            # 检查兼容映射（同时匹配模块名和功能名）
            final_key = name_key
            for keyword, compat in compat_map.items():
                if (keyword in item_name or keyword in last_module) and compat not in used_keys:
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
            catalog["software"][final_key] = {
                "name": item_name,
                "module_group": last_module,
                "category": last_category,
                "config_type": "选配" if "选配" in config_str else "标配",
                "description": str(func)[:100] if func else "",
                "brand": "蘑菇物联",
                "model": "云智控4.0",
                "standard_price": std_price,
                "channel_price": ch_price,
            }

    # ── 软件: 【软件】空调 sheet ──
    if "【软件】空调" in wb.sheetnames:
        ws = wb["【软件】空调"]
        last_module = ""
        for r in range(2, ws.max_row + 1):
            raw_module = cell(ws, r, 1)
            func = cell(ws, r, 3)
            if raw_module and str(raw_module).strip() and str(raw_module) != "None":
                last_module = str(raw_module).strip()
            std_price = cell(ws, r, 12)
            ch_price = cell(ws, r, 13)
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

    # ── 软件: 空压 sheet（边缘智能控制系统等，价格列 7=标准/8=非联营渠道）──
    if "空压" in wb.sheetnames:
        ws = wb["空压"]
        last_module = ""
        for r in range(4, ws.max_row + 1):
            raw_module = cell(ws, r, 1)
            func = cell(ws, r, 4)  # 设备类型描述
            if raw_module and str(raw_module).strip() and str(raw_module) != "None":
                last_module = str(raw_module).strip()
            std_price = cell(ws, r, 7)
            ch_price = cell(ws, r, 8)
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

    # ── 硬件: 【一方硬件】（价格列 7=渠道/8=标准，名称列 3）──
    if "【一方硬件】" in wb.sheetnames:
        ws = wb["【一方硬件】"]
        for r in range(4, ws.max_row + 1):
            name = str(cell(ws, r, 3) or "")
            model = str(cell(ws, r, 4) or "")
            if not name or name == "None":
                continue
            ch_price = cell(ws, r, 7)
            std_price = cell(ws, r, 8)

            if "云盒" in name and "Maxw5Pro-C1" in model:
                catalog["hardware"]["cloud_box"] = {
                    "name": "能管云盒", "brand": "蘑菇物联", "model": "Maxw5Pro-C1",
                    "standard_price": std_price, "channel_price": ch_price
                }

    # ── 硬件: 【三方硬件】能管（价格列 9=渠道/10=标准，名称列 2）──
    if "【三方硬件】能管" in wb.sheetnames:
        ws = wb["【三方硬件】能管"]
        last_name = ""
        for r in range(4, ws.max_row + 1):
            raw_name = cell(ws, r, 2)
            if raw_name and str(raw_name).strip() and str(raw_name) != "None":
                last_name = str(raw_name).strip()
            name = last_name
            desc = str(cell(ws, r, 3) or "")
            if not name or name == "None":
                continue
            ch_price = cell(ws, r, 9)
            std_price = cell(ws, r, 10) or cell(ws, r, 9)

            if "ADL400" in str(cell(ws, r, 5) or "") or ("三相" in name and "ADL400" in desc):
                catalog["hardware"]["adl400_meter"] = {
                    "name": "三相多功能电表", "brand": "安科瑞", "model": "ADL400",
                    "standard_price": std_price, "channel_price": ch_price
                }
            elif "通讯线" in name or "RVSP" in name or "屏蔽双绞" in name:
                catalog["hardware"]["cable_per_meter"] = {
                    "name": "屏蔽双绞线", "brand": "国产优质", "model": "RVSP2×1.0",
                    "standard_price": std_price or 6.375, "channel_price": ch_price or 5.1
                }
            elif "通讯箱" in name and "comm_box" not in catalog["hardware"]:
                catalog["hardware"]["comm_box"] = {
                    "name": "通讯箱", "brand": "国产优质", "model": "/",
                    "standard_price": std_price or 350, "channel_price": ch_price or 350
                }
            elif "开关电源" in name and "power_supply" not in catalog["hardware"]:
                catalog["hardware"]["power_supply"] = {
                    "name": "开关电源", "brand": "国产优质", "model": "/",
                    "standard_price": std_price or 200, "channel_price": ch_price or 200
                }
            elif "空气开关" in name and "air_switch" not in catalog["hardware"]:
                catalog["hardware"]["air_switch"] = {
                    "name": "空气开关", "brand": "国产优质", "model": "/",
                    "standard_price": std_price or 50, "channel_price": ch_price or 50
                }

    # ── 硬件辅材兜底（报价体系中可能不列这些辅材，用默认值）──
    hw_defaults = {
        "comm_box": {"name": "通讯箱", "brand": "国产优质", "model": "/", "standard_price": 350, "channel_price": 350},
        "power_supply": {"name": "开关电源", "brand": "国产优质", "model": "/", "standard_price": 200, "channel_price": 200},
        "air_switch": {"name": "空气开关", "brand": "国产优质", "model": "/", "standard_price": 50, "channel_price": 50},
    }
    for key, defaults in hw_defaults.items():
        if key not in catalog["hardware"]:
            catalog["hardware"][key] = defaults

    # ── CT 互感器: 【三方硬件】能管 ──
    if "【三方硬件】能管" in wb.sheetnames:
        ws = wb["【三方硬件】能管"]
        last_ct_remark = ""
        for r in range(4, ws.max_row + 1):
            name = str(cell(ws, r, 2) or "")
            desc = str(cell(ws, r, 3) or "")
            if "电流互感器" not in name and "电流互感器" not in desc:
                continue
            ch_price = cell(ws, r, 9)
            std_price = cell(ws, r, 10)
            full_text = desc if desc else name

            # 备注列(K列)是CT形式的主要依据；同一备注覆盖下方连续行
            remark = str(cell(ws, r, 11) or "").strip()
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

    # ── 水表: 【三方硬件】能管 ──
    if "【三方硬件】能管" in wb.sheetnames:
        ws = wb["【三方硬件】能管"]
        for r in range(4, ws.max_row + 1):
            name = str(cell(ws, r, 2) or "")
            desc = str(cell(ws, r, 3) or "")
            if "水表" not in name and "水表" not in desc:
                continue
            full = desc if desc else name
            dn_match = re.search(r'DN(\d+)', full)
            if not dn_match:
                continue
            dn = f"DN{dn_match.group(1)}"
            ch_price = cell(ws, r, 9)
            std_price = cell(ws, r, 10)
            brand = str(cell(ws, r, 4) or "捷先数码(深水牌)")

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

    if "【三方硬件】空调" in wb.sheetnames:
        ws = wb["【三方硬件】空调"]
        for r in range(4, ws.max_row + 1):
            name = str(cell(ws, r, 3) or "").strip()
            model = str(cell(ws, r, 4) or "").strip()
            spec = str(cell(ws, r, 6) or "").strip()
            brand = str(cell(ws, r, 7) or "").strip()
            install_type = str(cell(ws, r, 8) or "").strip()
            ch_price = cell(ws, r, 11)
            std_price = cell(ws, r, 12)
            _add_flow_meter(name, model, spec, brand, install_type, std_price, ch_price)

    if "【三方硬件】空压" in wb.sheetnames:
        ws = wb["【三方硬件】空压"]
        for r in range(4, ws.max_row + 1):
            name = str(cell(ws, r, 3) or "").strip()
            model = str(cell(ws, r, 4) or "").strip()
            spec = str(cell(ws, r, 6) or "").strip()
            brand = str(cell(ws, r, 7) or "").strip()
            ch_price = cell(ws, r, 10)
            std_price = cell(ws, r, 11)
            _add_flow_meter(name, model, spec, brand, "", std_price, ch_price)

    # ── 施工: 【施工调试】 ──
    if "【施工调试】" in wb.sheetnames:
        ws = wb["【施工调试】"]
        for r in range(3, ws.max_row + 1):
            service = str(cell(ws, r, 2) or "")
            price = cell(ws, r, 6)  # 施工单价
            if "新装电表" in service:
                catalog["construction"]["meter_install"] = {
                    "name": "新装电表施工", "standard_price": price or 500, "channel_price": price or 500
                }
            elif "通讯箱" in service:
                catalog["construction"]["cloudbox_install"] = {
                    "name": "通讯箱安装", "standard_price": price or 350, "channel_price": price or 350
                }
            elif "集中区域" in service:
                catalog["construction"]["cable_concentrated"] = {
                    "name": "通讯线敷设(集中区域)", "standard_price": price or 100, "channel_price": price or 100
                }
            elif "分散区域" in service:
                catalog["construction"]["cable_scattered"] = {
                    "name": "通讯线敷设(分散区域)", "standard_price": price or 120, "channel_price": price or 120
                }

    # ── 税费: 报价模板 sheet ──
    if "报价模板" in wb.sheetnames:
        ws = wb["报价模板"]
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

    # 锚点校验
    failures = validate_anchors(catalog)
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
