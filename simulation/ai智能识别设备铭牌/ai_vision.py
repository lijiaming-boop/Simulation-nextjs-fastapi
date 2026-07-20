"""AI 视觉识别模块 — 铭牌/设备清单多模态识别

独立的 AI 识图子模块，利用项目代理网关的 GPT 多模态能力：
- 从铭牌照片中直接提取设备参数
- 从 COP 性能曲线图片中提取数据点

对外仅暴露两个函数，项目其他模块只做调用，保持解耦。

依赖：项目 .env 中的 ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / ANTHROPIC_MODEL
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Optional

import anthropic

# ── 强制加载项目 .env（override=True 防止被系统环境变量覆盖）──
_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
if _ENV_PATH.exists():
    for _line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _val = _line.split("=", 1)
            os.environ[_key.strip()] = _val.strip()


def _get_client() -> anthropic.Anthropic:
    """获取 Anthropic 客户端（连代理网关）"""
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        base_url=os.environ.get("ANTHROPIC_BASE_URL", ""),
    )


def _get_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "gpt-5.4")


# ── Prompt ──────────────────────────────────────────────────

PLANT_TOPO_PROMPT = """你是一位资深暖通空调设备专家。请仔细查看上传的设备铭牌照片/设备清单图片，精确提取所有冷站设备参数。

## 输出要求
严格输出纯JSON，不要Markdown代码块（不要 ```json），不要任何额外文字：
{
  "chillers": [
    {
      "name": "主机型号/名称",
      "qty": 台数(int),
      "capacity_kw": 单台额定制冷量kW(float),
      "rated_power_kw": 单台额定输入功率kW(float),
      "rated_cop": 额定COP(float),
      "variable_freq": true或false
    }
  ],
  "chw_pumps": [
    {
      "name": "冷冻泵型号",
      "qty": 台数(int),
      "power_kw": 单台额定功率kW(float),
      "flow_m3h": 单台额定流量m3/h(float),
      "variable_freq": true或false
    }
  ],
  "cw_pumps": [
    {
      "name": "冷却泵型号",
      "qty": 台数(int),
      "power_kw": 单台额定功率kW(float),
      "flow_m3h": 单台额定流量m3/h(float),
      "variable_freq": true或false
    }
  ],
  "towers": [
    {
      "name": "冷却塔型号",
      "qty": 台数(int),
      "fan_power_kw": 单台风机功率kW(float),
      "fans_per_tower": 每塔风机数量(int),
      "variable_freq": true或false
    }
  ],
  "monthly_chiller_count": [1月台数,...,12月台数],
  "base_load_ratio": 0.70,
  "region": "华东/华南/华中/华北/西南/西北/东北，无法判断填null"
}

## 重要识别规则
1. **制冷量单位转换**：铭牌上的"冷吨"或"RT"请乘以3.517换算为kW
2. **COP推导**：铭牌没有直接标COP，但有制冷量kW和输入功率kW时，COP=制冷量÷输入功率
3. **变频判断**："变频/VFD/VSD/inverter/变频器"→true；"工频/定频/fixed speed"→false；无标注→false
4. **功率推导**：只有电流A和电压V时，三相电机额定功率≈电压×电流×1.732×0.85÷1000
5. **多台不同型号**：不同型号的设备要分成数组中多个元素
6. **缺失值**：确实看不清的参数填null，不要编造
7. **月度开机数**：根据总台数和规模合理推断（夏季全开、冬季减半）
8. **仔细核对数字**：小数点不要错位

## 铭牌常见字段中英文对照
- Cooling Capacity / Rated Capacity / Nominal Capacity / 额定制冷量 / 制冷量 / 冷房能力 → capacity_kw
- Power Input / Rated Power / Power Consumption / 额定功率 / 输入功率 / 消耗电力 → rated_power_kw
- COP / EER / Coefficient of Performance / 能效比 / 性能系数 → rated_cop
- Flow Rate / Rated Flow / 流量 / 额定流量 / 循环水量 → flow_m3h
- Model / Type / 型号 / 型式 → name
- Refrigerant / 冷媒 / 制冷剂 → 辅助信息"""

COP_CURVE_PROMPT = """请从这张COP性能曲线图/数据表格中提取所有可见的数据点。

输出格式：每行一个数据点，格式为"负载率百分比 COP值"，不要其他文字。
负载率按百分比（0-100），COP保留1位小数。

示例输出：
100 6.0
90 6.2
80 6.3
70 6.3
60 6.0
50 5.6
40 4.8
30 3.6

如果图表中有多条曲线，只提取"COP-负载率"那条曲线。
如果看不清楚具体数值，请尽力估算，不编造不存在的点。"""


# ── 核心函数 ────────────────────────────────────────────────


def _robust_extract_json(text: str) -> Optional[dict]:
    """4级容错 JSON 提取"""
    if not text:
        return None
    text = text.strip()

    # 策略1: 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 策略2: 提取 {} 之间内容
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # 策略3: 移除 Markdown 代码块后重试
    clean = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(clean[start:end])
        except json.JSONDecodeError:
            pass

    # 策略4: 修复尾逗号等常见问题
    if start >= 0 and end > start:
        json_str = text[start:end]
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    return None


def extract_plant_topology(
    content: str = "",
    content_type: str = "text",
    image_data: Optional[bytes] = None,
    media_type: str = "image/jpeg",
) -> Optional[dict]:
    """从图片或文本中提取冷站设备拓扑参数

    参数:
        content: 文本内容（content_type="text" 时使用，可选）
        content_type: "image"（图片+可选文本）| "text"（纯文本）
        image_data: 图片字节数据（content_type="image" 时必须）
        media_type: 图片 MIME 类型

    返回:
        成功 → {chillers, chw_pumps, cw_pumps, towers, monthly_chiller_count, ...}
        失败 → None

    示例:
        # 铭牌图片识别
        with open("nameplate.jpg", "rb") as f:
            result = extract_plant_topology(
                content_type="image",
                image_data=f.read(),
                media_type="image/jpeg"
            )

        # 文本描述识别
        result = extract_plant_topology(
            content="3台变频离心机，单台5274kW，COP 6.12"
        )
    """
    try:
        client = _get_client()
        msg_content = []

        if content_type == "image" and image_data:
            b64 = base64.b64encode(image_data).decode()
            msg_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            })

        # 构建用户消息文本
        user_text = ""
        if content:
            user_text = content + "\n\n" + PLANT_TOPO_PROMPT
        else:
            user_text = PLANT_TOPO_PROMPT

        msg_content.append({"type": "text", "text": user_text})

        response = client.messages.create(
            model=_get_model(),
            max_tokens=3000,
            temperature=0.1,
            messages=[{"role": "user", "content": msg_content}],
        )

        raw_text = response.content[0].text
        return _robust_extract_json(raw_text)

    except Exception as e:
        print(f"[ai_vision] 设备拓扑识别失败: {e}")
        return None


def extract_cop_curve(
    image_data: bytes,
    media_type: str = "image/jpeg",
) -> Optional[dict]:
    """从 COP 性能曲线图片中提取数据点

    参数:
        image_data: 图片字节数据
        media_type: 图片 MIME 类型

    返回:
        成功 → {load_ratio: cop_value}  例: {0.3: 3.6, 0.5: 5.6, 1.0: 6.0}
        失败 → None
    """
    try:
        from ..input_parser import parse_cop_curve_from_text

        client = _get_client()
        b64 = base64.b64encode(image_data).decode()

        response = client.messages.create(
            model=_get_model(),
            max_tokens=2000,
            temperature=0.0,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": COP_CURVE_PROMPT},
                ],
            }],
        )

        raw_text = response.content[0].text
        return parse_cop_curve_from_text(raw_text)

    except Exception as e:
        print(f"[ai_vision] COP曲线识别失败: {e}")
        return None
