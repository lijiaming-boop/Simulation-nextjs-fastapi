"""
板块八语义分析器 — 分析调研表第八栏自由文本，检测是否超出标准能管边界

标准能管 = 只看不动手（监测/展示/报表/告警）
非标 = 闭环控制 / AI决策 / 设备干预 / 固定节能率承诺

调用方式：
    from core.section9_analyzer import analyze_section9
    result = analyze_section9(current_status, goals)
"""
import json
import re
from typing import Optional


NONSTANDARD_KEYWORDS = [
    "AI", "人工智能", "大模型", "机器学习", "深度学习",
    "能源AI预测", "AI自动分析", "AI智控", "AI可视化",
    "闭环控制", "自动启停", "自动控制", "远程启停", "自动调节",
    "固定节能率", "保证节能", "节能率", "节能承诺",
    "双向写回", "反向控制", "下发指令", "设备控制",
    "冷冻站智控", "空调AI", "离心AI算法", "边缘智能控制",
    "APS对接", "生产排程",
]

STANDARD_KEYWORDS = [
    "监测", "监控", "数据采集", "能耗分析", "报表", "大屏",
    "告警", "预警", "能流图", "组态", "对标", "统计",
    "抄表", "趋势", "同比", "环比", "可视化",
]


def _keyword_prescreen(text: str) -> dict:
    detected_nonstandard = [kw for kw in NONSTANDARD_KEYWORDS if kw in text]
    detected_standard = [kw for kw in STANDARD_KEYWORDS if kw in text]
    return {
        "nonstandard_keywords": detected_nonstandard,
        "standard_keywords": detected_standard,
        "has_nonstandard_signal": len(detected_nonstandard) > 0,
    }


SYSTEM_PROMPT = """你是标准能管项目边界审核员。你的任务是分析客户在调研表第八栏（项目需求/备注）中填写的自由文本，判断其中是否包含超出"标准能管"范围的需求。

## 标准能管的定义
标准能管 = 能源监测与管理系统，核心原则是"只看不动手"：
- 数据采集、监测、展示、报表、告警、能耗分析、对标、趋势图
- 不包含任何对设备的控制、干预、自动决策

## 超出标准能管边界的信号（非标）
1. **AI/大模型相关**：AI预测、AI分析、人工智能、大模型、机器学习、深度学习
2. **闭环控制**：自动控制、自动启停、远程启停、自动调节、闭环、设备控制、下发指令
3. **节能承诺**：固定节能率、保证节能X%、节能率承诺
4. **双向数据流**：双向写回、反向控制、API下发指令到设备
5. **特定非标产品**：冷冻站智控、空调AI智控、离心AI算法、边缘智能控制、APS对接

## 不超出边界的信号（标准）
- 能耗监测、数据采集、报表、大屏展示、告警预警、能耗分析、对标、趋势图
- 设备能效分析（这是标准选配模块，不是AI）
- 单位能耗/能耗强度分析（标准选配）
- 能耗对标（标准选配）
- 运维工单/巡检（标准选配）

## 特殊情况
- "希望了解AI功能" / "未来考虑AI" → 标记为需要确认（不是当前需求，但需跟进）
- "节能" 出现在 "希望了解节能空间" 这类表述中 → 标准（只是分析，不是承诺）
- "节能" 出现在 "保证节能20%" 这类表述中 → 非标（固定节能率承诺）
- 提到气象仪/温湿度传感器 → 不一定非标，但如果用于控制环境则是非标

## 输出格式
必须输出纯JSON（不要markdown代码块），结构如下：
{
    "is_standard": true/false,
    "confidence": "high"/"medium"/"low",
    "nonstandard_items": [
        {"keyword": "检测到的关键词", "context": "原文中的上下文片段", "severity": "hard"/"soft"}
    ],
    "equipment_specs": [
        {"name": "设备名称", "spec": "规格描述"}
    ],
    "standard_items": ["检测到的标准能管需求"],
    "explanation": "判定理由的一句话说明",
    "needs_clarification": ["需要进一步确认的点（如有）"]
}

severity说明：
- hard: 明确超出边界（如"需要AI自动控制"）
- soft: 可能超出但需要确认（如"想了解AI功能"）"""


def analyze_section9(
    current_status: str,
    goals: str,
    callback: Optional[callable] = None,
) -> dict:
    """分析板块九自由文本，返回结构化分析结果"""
    from quote_module.ai_client import get_ai_client, AIClientError

    def _notify(msg):
        if callback:
            callback(msg)

    combined_text = f"{current_status}\n{goals}".strip()

    if not combined_text or combined_text in ("None", ""):
        return {
            "is_standard": True,
            "confidence": "high",
            "nonstandard_items": [],
            "equipment_specs": [],
            "standard_items": [],
            "explanation": "板块九为空，无非标信号",
            "needs_clarification": [],
            "prescreen": {"nonstandard_keywords": [], "standard_keywords": []},
            "source": "empty_input",
        }

    prescreen = _keyword_prescreen(combined_text)

    if not prescreen["has_nonstandard_signal"]:
        return {
            "is_standard": True,
            "confidence": "high",
            "nonstandard_items": [],
            "equipment_specs": [],
            "standard_items": prescreen["standard_keywords"],
            "explanation": "关键词预筛未检测到非标信号",
            "needs_clarification": [],
            "prescreen": prescreen,
            "source": "prescreen_pass",
        }

    _notify(f"板块八检测到非标关键词: {prescreen['nonstandard_keywords']}，启动AI语义分析...")

    user_prompt = f"""请分析以下调研表第八栏内容，判断是否超出标准能管边界。

## 项目现状/管理问题（C96单元格）：
{current_status}

## 其他特殊要求/目标（C98单元格）：
{goals}

请输出JSON分析结果。"""

    try:
        client = get_ai_client()
        raw_response = client.chat(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            timeout=60,
            temperature=0.1,
        )

        json_match = re.search(r'\{[\s\S]*\}', raw_response)
        if not json_match:
            raise AIClientError("AI返回内容中未找到JSON")

        result = json.loads(json_match.group())
        result["prescreen"] = prescreen
        result["source"] = "ai_analysis"
        _notify(f"AI语义分析完成: {'标准' if result.get('is_standard') else '非标'}")
        return result

    except Exception as e:
        _notify(f"AI分析失败({e})，降级为关键词判定")
        nonstandard_items = [
            {"keyword": kw, "context": combined_text[:100], "severity": "hard"}
            for kw in prescreen["nonstandard_keywords"]
        ]
        return {
            "is_standard": False,
            "confidence": "medium",
            "nonstandard_items": nonstandard_items,
            "equipment_specs": [],
            "standard_items": prescreen["standard_keywords"],
            "explanation": f"AI分析失败，基于关键词预筛判定非标: {prescreen['nonstandard_keywords']}",
            "needs_clarification": ["AI分析失败，建议人工复核板块九内容"],
            "prescreen": prescreen,
            "source": "prescreen_fallback",
            "error": str(e),
        }
