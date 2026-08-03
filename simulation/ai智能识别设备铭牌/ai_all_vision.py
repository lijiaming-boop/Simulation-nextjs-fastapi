"""AI 多图批量识别模块 — 多张铭牌照片一次性识别多组主机

独立的 AI 识图子模块，专注解决"上传多张设备铭牌，AI 自动分组填入"的场景。
与 ai_vision.py 解耦：ai_vision 处理单图场景（COP曲线、单组拓扑），
本模块处理多图批量场景。

对外暴露函数：
- extract_multi_chiller_topology(): 多张铭牌 → 多组主机参数

依赖：项目 .env 中的 ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / ANTHROPIC_MODEL
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

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


# ── 多图批量识别 Prompt ────────────────────────────────────────

MULTI_CHILLER_PROMPT = """你是一位资深暖通空调设备专家。你收到了 __IMAGE_COUNT__ 张设备铭牌照片。
**每张照片代表一台/一组不同型号的主机（冷水机组）**，请分别识别每张照片中的设备参数。

## 输出要求
严格输出纯JSON，不要Markdown代码块（不要 ```json），不要任何额外文字：

{
  "results": [
    {
      "image_index": 0,
      "status": "success",
      "warning": null,
      "data": {
        "name": "主机型号/名称",
        "qty": 台数(int),
        "capacity_kw": 单台额定制冷量kW(float),
        "rated_power_kw": 单台额定输入功率kW(float),
        "rated_cop": 额定COP(float),
        "variable_freq": true或false
      }
    },
    {
      "image_index": 1,
      "status": "partial",
      "warning": "个别参数无法识别：rated_cop字段照片模糊，建议核查主机组2",
      "data": {
        "name": "主机型号",
        "qty": 2,
        "capacity_kw": 3868,
        "rated_power_kw": 632,
        "rated_cop": null,
        "variable_freq": true
      }
    },
    {
      "image_index": 2,
      "status": "failed",
      "warning": "第3张图片画面模糊/反光严重，无法识别任何参数，建议核查主机组3",
      "data": null
    }
  ]
}

## status 取值规则
- **"success"**: 图片清晰，所有关键参数（name、capacity_kw、rated_power_kw、rated_cop）均成功识别
- **"partial"**: 图片基本可读，但个别关键参数模糊不清（warning字段中必须说明哪些参数无法识别），能识别的参数正常填入data
- **"failed"**: 图片严重模糊/反光/无内容/非铭牌照片，完全无法识别参数（data设为null，warning必须明确说明原因，如"第N张图片模糊无法识别"）

## 重要识别规则
1. **制冷量单位转换**：铭牌上的"冷吨"或"RT"请乘以3.517换算为kW
2. **COP推导**：铭牌没有直接标COP，但有制冷量kW和输入功率kW时，COP=制冷量÷输入功率
3. **变频判断**："变频/VFD/VSD/inverter/变频器"→true；"工频/定频/fixed speed"→false；无标注→false
4. **功率推导**：只有电流A和电压V时，三相电机额定功率≈电压×电流×1.732×0.85÷1000
5. **台数判断**：铭牌通常只显示单台设备的参数，台数默认为1；除非图片中有明确的多台标注（如"3台"、"Qty: 3"）
6. **缺失值**：确实看不清的参数填null，不要编造
7. **仔细核对数字**：小数点不要错位，数字不要多读或少读位数
8. **每张图独立识别**：每张图片的识别结果作为一个独立的数组元素，image_index从0开始递增

## 铭牌常见字段中英文对照
- Cooling Capacity / Rated Capacity / Nominal Capacity / 额定制冷量 / 制冷量 / 冷房能力 → capacity_kw
- Power Input / Rated Power / Power Consumption / 额定功率 / 输入功率 / 消耗电力 → rated_power_kw
- COP / EER / Coefficient of Performance / 能效比 / 性能系数 → rated_cop
- Model / Type / 型号 / 型式 → name
- Refrigerant / 冷媒 / 制冷剂 → 辅助信息"""


def _robust_extract_json(text: str) -> Optional[dict]:
    """4级容错 JSON 提取（与 ai_vision 保持一致）"""
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


def _build_failed_result(count: int, reason: str) -> Dict[str, Any]:
    """生成全部失败的兜底结果"""
    return {
        "total_count": count,
        "success_count": 0,
        "partial_count": 0,
        "failed_count": count,
        "chillers": [
            {
                "index": i,
                "status": "failed",
                "warning": f"第{i+1}张图片识别失败: {reason}",
                "data": None,
            }
            for i in range(count)
        ],
    }


def extract_multi_chiller_topology(
    images: List[bytes],
    media_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """从多张铭牌照片中一次性识别多组主机参数

    将多张图片打包在一次 API 调用中，AI 自动分析每张图片对应一组不同的主机，
    返回每组的识别状态和参数。

    参数:
        images: 多张图片的字节数据列表
        media_types: 每张图片的 MIME 类型列表（可选，默认均为 image/jpeg）

    返回:
        {
            "total_count": 3,       # 总图片数
            "success_count": 2,     # 成功识别的组数（status=="success"）
            "partial_count": 1,     # 部分识别的组数（status=="partial"）
            "failed_count": 0,      # 失败识别的组数（status=="failed"）
            "chillers": [           # 每组主机的详细结果
                {
                    "index": 0,                # 对应第几张图片（0-based）
                    "status": "success",       # "success" | "partial" | "failed"
                    "warning": None,           # None 或警告文字
                    "data": {                  # status!="failed" 时为参数dict，否则为None
                        "name": "...",
                        "qty": 1,
                        "capacity_kw": 5274.0,
                        "rated_power_kw": 800.0,
                        "rated_cop": 6.6,
                        "variable_freq": True
                    }
                },
                ...
            ]
        }

    调用示例:
        with open("plate1.jpg", "rb") as f1, open("plate2.jpg", "rb") as f2:
            result = extract_multi_chiller_topology(
                images=[f1.read(), f2.read()],
                media_types=["image/jpeg", "image/jpeg"]
            )
        for ch in result["chillers"]:
            if ch["status"] == "success":
                print(f"主机组{ch['index']+1}: {ch['data']['name']}")
            elif ch["warning"]:
                print(f"警告: {ch['warning']}")
    """
    if not images:
        return {
            "total_count": 0,
            "success_count": 0,
            "partial_count": 0,
            "failed_count": 0,
            "chillers": [],
        }

    # 默认 MIME 类型
    if media_types is None:
        media_types = ["image/jpeg"] * len(images)
    # 补齐长度（防止 media_types 比 images 短）
    while len(media_types) < len(images):
        media_types.append("image/jpeg")

    try:
        client = _get_client()
        msg_content = []

        # 将所有图片打包进 content 数组（每张图片作为独立的 image block）
        for img_data, mime_type in zip(images, media_types):
            b64 = base64.b64encode(img_data).decode()
            msg_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": b64,
                },
            })

        # 构建 prompt（告知 AI 总共有多少张图片）
        image_count = len(images)
        prompt = MULTI_CHILLER_PROMPT.replace("__IMAGE_COUNT__", str(image_count))
        msg_content.append({"type": "text", "text": prompt})

        response = client.messages.create(
            model=_get_model(),
            max_tokens=4000,
            temperature=0.1,
            messages=[{"role": "user", "content": msg_content}],
        )

        raw_text = response.content[0].text
        parsed = _robust_extract_json(raw_text)

        if parsed is None:
            return _build_failed_result(
                len(images),
                f"AI 返回格式异常，无法解析为JSON。原始返回前200字符: {raw_text[:200]}"
            )

        results = parsed.get("results", [])

        # 构建标准化输出：为每张图片匹配 AI 返回的结果
        chillers = []
        success_count = 0
        partial_count = 0
        failed_count = 0

        for i in range(len(images)):
            # 在 AI 返回中查找对应 image_index 的结果
            matched = None
            for r in results:
                if r.get("image_index") == i:
                    matched = r
                    break

            if matched is None:
                # AI 没有返回这张图片的结果
                failed_count += 1
                chillers.append({
                    "index": i,
                    "status": "failed",
                    "warning": f"第{i+1}张图片AI未返回识别结果，建议核查主机组{i+1}",
                    "data": None,
                })
                continue

            status = matched.get("status", "failed")
            warning = matched.get("warning")
            data = matched.get("data") if status != "failed" else None

            # 规范化 status
            if status not in ("success", "partial", "failed"):
                status = "partial" if data else "failed"

            if status == "success":
                success_count += 1
            elif status == "partial":
                partial_count += 1
                # 确保 partial 状态有 warning
                if not warning:
                    warning = f"第{i+1}张图片部分参数无法识别，建议核查主机组{i+1}"
            else:  # failed
                failed_count += 1
                data = None  # failed 状态下强制 data 为 None
                if not warning:
                    warning = f"第{i+1}张图片无法识别，建议核查主机组{i+1}"

            chillers.append({
                "index": i,
                "status": status,
                "warning": warning,
                "data": data,
            })

        return {
            "total_count": len(images),
            "success_count": success_count,
            "partial_count": partial_count,
            "failed_count": failed_count,
            "chillers": chillers,
        }

    except Exception as e:
        print(f"[ai_all_vision] 多图批量识别失败: {e}")
        return _build_failed_result(len(images), f"API调用异常: {str(e)}")
