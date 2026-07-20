"""AI 月度运行参数推荐引擎

两阶段流程：
  阶段一：分析项目特征 → 推荐班制
  阶段二：基于确认的曲线 → 推荐月度开机台数 + 月度负载系数
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

# ── API 配置 ──────────────────────────────────────────────────
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _val = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _val.strip())


def _get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or None
    return anthropic.Anthropic(api_key=api_key, base_url=base_url)


def _get_model():
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


def _robust_extract_json(text: str) -> Optional[dict]:
    """从 AI 返回文本中提取 JSON。"""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    clean = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(clean[start:end])
        except json.JSONDecodeError:
            pass
    if start >= 0 and end > start:
        j = text[start:end]
        j = re.sub(r",\s*}", "}", j)
        j = re.sub(r",\s*]", "]", j)
        try:
            return json.loads(j)
        except json.JSONDecodeError:
            pass
    return None


# ═══════════════════════════════════════════════════════════════
#  阶段一 Prompt
# ═══════════════════════════════════════════════════════════════

STAGE1_PROMPT = """你是一位资深暖通空调系统运行专家。请根据提供的项目信息，分析该冷站项目的特征。

## 你需要输出的内容

严格输出纯JSON，不要Markdown代码块，不要额外文字：

{
  "analysis": {
    "project_type": "办公楼 / 工厂车间 / 数据中心 / 商场 / 酒店 / 医院 / 其他",
    "project_type_reason": "判断依据（来自调研表的哪条信息）",
    "region": "华南 / 华东 / 华中 / 华北 / 西南 / 西北 / 东北 / 未知",
    "schedule_label": "单班制办公 / 双班制工厂 / 三班制工厂 / 24h数据中心 / 商场营业制 / 酒店制 / 医院制",
    "schedule_reason": "为什么选择这个班制",
    "total_chiller_count": 主机总台数(int),
    "can_identify": true,
    "summary": "2-3句话的项目概述"
  }
}

## 重要规则

1. schedule_label 必须从以下列表中精确选择：单班制办公、双班制工厂、三班制工厂、24h数据中心、商场营业制、酒店制、医院制
2. total_chiller_count 若能识别；否则填 3
3. can_identify：如果调研表内容足以判断项目类型和班制，填 true；否则填 false
4. can_identify=false 时，project_type 填"无法识别"，schedule_label 填"单班制办公"作为默认值
5. 地区识别：从调研表提取省市关键词，华南/华东/华中/华北/西南/西北/东北；无法判断填"未知"

## 班制参考
- 单班制办公：工作日白天运行，夜间值班，周末关闭
- 双班制工厂：早班+晚班，夜间热备，周末减半
- 三班制工厂：24h 全天候，周末轮班
- 24h数据中心：全年无波动满负荷
- 商场营业制：工作日营业时间运行，周末客流更高
- 酒店制：全天运行，夜间偏低
- 医院制：全天运行，全年供冷稳定"""


def ai_stage1_from_text(survey_text: str) -> Optional[Dict[str, Any]]:
    """阶段一：从调研表文本分析项目特征。"""
    client = _get_client()
    truncated = survey_text[:8000] + "\n\n...(内容已截断)" if len(survey_text) > 8000 else survey_text
    prompt = (
        f"以下是某个冷站项目的调研表原始内容。请分析项目特征。\n\n"
        f"=== 调研表内容 ===\n{truncated}\n=== 结束 ===\n\n"
        f"{STAGE1_PROMPT}"
    )
    response = client.messages.create(
        model=_get_model(), max_tokens=1500, temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )
    return _robust_extract_json(response.content[0].text)


# ═══════════════════════════════════════════════════════════════
#  阶段二 Prompt
# ═══════════════════════════════════════════════════════════════

STAGE2_PROMPT = """你是一位资深暖通空调系统运行专家。用户已经确认了该项目的负载曲线配置，请基于此推荐月度运行参数。

## 你需要输出的内容

严格输出纯JSON，不要Markdown代码块：

{
  "monthly_chiller_count": [1月台数, ..., 12月台数],
  "monthly_load_factors": [1月系数, ..., 12月系数],
  "recommendation_summary": "2句话说明推荐理由"
}

## 参数规则
- monthly_chiller_count：整数 1~总台数，夏季全开、冬季减半、过渡居中
- monthly_load_factors：0.0~1.0，12个值中最大值为 1.0，保留两位小数

## 行业参考
| 类型 | 冬季负荷 | 开机策略 |
|------|---------|---------|
| 办公楼 | 0.35-0.45 | 冬1-2台,夏3-4台 |
| 工厂车间 | 0.50-0.70 | 冬2-3台,夏3-5台 |
| 数据中心 | 0.75-0.85 | 全年全开 |
| 商场 | 0.35-0.50 | 冬2-3台,夏3-4台 |
| 酒店 | 0.50-0.65 | 冬2-3台,夏3-4台 |
| 医院 | 0.55-0.70 | 冬2-3台,夏3-4台 |

## 特别规则
1. 如果负载曲线已经体现了运行班制对月度总负荷的影响，月度负载系数仅反映季节气候差异
2. 华南冬季负载系数高于东北
3. 确认后的班制和曲线是准确可靠的，优先根据曲线特征反推月度参数"""


def ai_stage2_recommend(
    analysis: dict,
    schedule_label: str,
    workday_curve: List[float],
    offday_curve: List[float],
    total_count: int,
    user_region: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """阶段二：基于确认的曲线推荐月度参数。

    Args:
        analysis: 阶段一分析结果
        schedule_label: 当前选择的班制
        workday_curve: 工作日 24 小时逐时系数
        offday_curve: 休息日 24 小时逐时系数
        total_count: 主机总台数
        user_region: 用户选择的地区（优先级高于 AI 识别）
    """
    client = _get_client()
    region = user_region or analysis.get("region", "未知")

    context = (
        f"## 项目分析结果\n"
        f"- 项目类型: {analysis.get('project_type', '未知')}\n"
        f"- 项目地区: {region}\n"
        f"- 运行班制: {schedule_label}\n"
        f"- 主机总台数: {total_count}\n"
        f"- 分析摘要: {analysis.get('summary', analysis.get('recommendation_summary', ''))}\n\n"
        f"## 已确认的负载曲线\n"
        f"工作日逐时系数: {workday_curve}\n"
        f"休息日逐时系数: {offday_curve}\n"
    )

    prompt = f"{context}\n\n{STAGE2_PROMPT}"
    response = client.messages.create(
        model=_get_model(), max_tokens=1500, temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )
    return _robust_extract_json(response.content[0].text)


def ai_parse_calendar(user_text: str) -> Optional[List[int]]:
    """AI 兜底：解析工作日历规则，返回 365 天 day_type 数组。"""
    client = _get_client()
    prompt = (
        f"把下面的运行日历需求转成一个365天的JSON数组。\n\n"
        f"用户需求：{user_text}\n\n"
        f"规则：\n"
        f"1. 2024-01-01=周一=day 0。从用户话里推断工作/休息的循环周期"
        f"（如\"上七修二\"=7工作+2休息=9天循环），默认5+2。\n"
        f"   循环周期可以是任意N+M组合。0=工作日，1=休息日。\n"
        f"2. 节假日处理：\n"
        f"   - \"考虑所有节假日\"→ 所有7个节日标记为休息(1)\n"
        f"   - \"除了XX节\"→ 排除该节日\n"
        f"   - \"XX节上班\"→ 该节覆盖为0\n"
        f"   七个法定假日及2024年日期：\n"
        f"   元旦 day 0 | 春节 day 28~34 | 清明 day 94 | 劳动节 day 121 |\n"
        f"   端午 day 161 | 中秋 day 260 | 国庆 day 273~279\n"
        f"3. 输出：一个纯JSON数组 [0,0,1,...]，共365个整数。\n"
    )
    try:
        response = client.messages.create(
            model=_get_model(), max_tokens=3500, temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text

        digits = [int(c) for c in raw if c in '01']
        if len(digits) >= 365:
            return digits[:365]

        m = re.search(r'\[([01,\s]+)\]', raw, re.DOTALL)
        if m:
            nums = [int(x.strip()) for x in m.group(1).split(',') if x.strip() in ('0', '1')]
            if len(nums) >= 365:
                return nums[:365]

        result = _robust_extract_json(raw)
        if result:
            arr = result if isinstance(result, list) else result.get("day_type", [])
            if len(arr) == 365:
                return [int(d) for d in arr]

        return None
    except Exception as e:
        print(f"[calendar_parse] Error: {e}")
        return None
