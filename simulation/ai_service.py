"""AI能力模块 - 设备拓扑识别 & 报告生成"""
import json
import os
from pathlib import Path
from typing import Optional

import anthropic

# 加载 .env 文件（确保环境变量可用）
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def _get_client():
    """获取 Anthropic 客户端，显式传入 key 和 base_url"""
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or None
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return anthropic.Anthropic(api_key=api_key, base_url=base_url)


def _get_model():
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def ai_extract_plant_topology(content: str, content_type: str = "text",
                              image_data: bytes = None, media_type: str = "image/jpeg") -> Optional[dict]:
    """
    AI识别设备拓扑结构

    支持输入:
    - content_type="text": 文本/表格描述
    - content_type="image": 图片 (铭牌照片、设备清单截图等)

    返回结构化设备参数 dict
    """
    prompt = """请从以下信息中提取冷站设备参数。输出严格的JSON格式，不要其他文字。

输出格式：
{
  "chillers": [
    {"name": "描述", "qty": 台数, "capacity_kw": 制冷量kW, "rated_power_kw": 功率kW, "rated_cop": COP值, "variable_freq": true/false}
  ],
  "chw_pumps": [
    {"name": "描述", "qty": 台数, "power_kw": 功率kW, "flow_m3h": 流量m³/h, "variable_freq": true/false}
  ],
  "cw_pumps": [
    {"name": "描述", "qty": 台数, "power_kw": 功率kW, "flow_m3h": 流量m³/h, "variable_freq": true/false}
  ],
  "towers": [
    {"name": "描述", "qty": 台数, "fan_power_kw": 单台风机功率kW, "fans_per_tower": 每塔风机数, "variable_freq": true/false}
  ],
  "monthly_chiller_count": [1月开机数, 2月, ..., 12月],
  "base_load_ratio": 0.7,
  "region": "华东/华南/华中/华北/西南/西北/东北"
}

注意：
- 制冷量单位统一为kW（如果是冷吨RT，1RT=3.517kW）
- 如果信息不完整，用合理默认值填充
- variable_freq：看描述中有无"变频"字样，否则为false
- 如果有月度运行台数信息请提取，没有则根据总台数合理推算
"""

    try:
        client = _get_client()
        messages_content = []

        if content_type == "image" and image_data:
            import base64
            b64 = base64.b64encode(image_data).decode()
            messages_content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64}
            })

        if content:
            messages_content.append({"type": "text", "text": content})

        messages_content.append({"type": "text", "text": prompt})

        response = client.messages.create(
            model=_get_model(),
            max_tokens=3000,
            messages=[{"role": "user", "content": messages_content}]
        )

        text = response.content[0].text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return None
    except Exception as e:
        print(f"AI设备识别失败: {e}")
        return None


def ai_generate_simulation_report(summary: dict, config_desc: str = "") -> Optional[str]:
    """
    AI生成仿真分析报告
    """
    prompt = f"""你是一位资深的暖通空调节能专家。请基于以下冷站仿真数据，生成一份专业的优化控制策略分析报告。

## 仿真数据汇总

```json
{json.dumps(summary, ensure_ascii=False, indent=2)}
```

{f"## 设备描述{chr(10)}{config_desc}" if config_desc else ""}

## 报告要求

请输出一份完整的Markdown格式报告，包含以下章节：

1. **系统概况** - 简述冷站配置和当前运行情况
2. **能效诊断** - 分析当前系统COP水平，指出效率短板（哪个设备/哪个季节效率低）
3. **优化策略** - 具体的控制策略改进方案：
   - 温差控制策略（冷冻侧/冷却侧）
   - 水泵变频优化（哪些泵可以优化，哪些是工频不可调）
   - 冷却塔联动优化
   - 主机加减载策略建议
4. **仿真结果** - 基线vs优化对比表格（月度COP、分项能耗）
5. **经济效益** - 投资回收分析（节电量、节电费、改造投资、回收期）
6. **实施建议** - 分阶段实施路径，优先级排序，注意事项

要求：
- 语言专业但简洁，面向甲方决策者
- 数据要引用仿真结果中的具体数字
- 节能率和节电量要与仿真结果一致
- 给出具体可操作的建议，不要泛泛而谈
"""

    try:
        client = _get_client()
        response = client.messages.create(
            model=_get_model(),
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"AI报告生成失败: {e}")
        return None
