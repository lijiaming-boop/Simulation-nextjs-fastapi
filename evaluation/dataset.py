"""回归评测集

6 份标注样例调研表（00_sample/示例调研表/），文件名自带预期节能率与数据
质量等级（见该目录 readme.md），构成可复现的回归评测锚点。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SURVEY_DIR = PROJECT_ROOT / "00_sample" / "示例调研表"


@dataclass
class EvalCase:
    """一个评测用例"""
    key: str
    filename: str
    expected_outcome: str                 # completed | needs_input
    expected_rate: Optional[float]        # 预期节能率（%，文件名锚点）；中断用例为 None
    expected_region: Optional[str]        # 预期地区（从文件名城市可推断时才有）
    note: str = ""
    known_gap: Optional[str] = None       # 已定位的能力缺口说明（计入 known_gap 分桶）

    @property
    def survey_path(self) -> Path:
        return SURVEY_DIR / self.filename


# 与 00_sample/示例调研表/readme.md 的标注一一对应
CASES = [
    EvalCase(
        key="complete_huizhou",
        filename="【齐全】15.2%惠州光弘-中央空调节能调研表.xlsx",
        expected_outcome="completed", expected_rate=15.2, expected_region="华南",
        note="数据齐全，高置信度",
    ),
    EvalCase(
        key="missing_winter",
        filename="【缺冬季】10.4%石家庄仁和药业中央空调节能调研表.xlsx",
        expected_outcome="completed", expected_rate=10.4, expected_region="华北",
        note="缺冬季数据，需填充",
    ),
    EvalCase(
        key="missing_summer",
        filename="【缺夏季】12.1%上海和元-机房智能化调研表模板（深度调研）.xlsx",
        expected_outcome="completed", expected_rate=12.1, expected_region="华东",
        note="缺夏季能耗数据，需填充",
        known_gap=("深度调研模板变体的行位与标准模板不同，供水温度/泵频率等字段"
                   "提取不到，完整率被低估为 14% 触发低置信度门禁（提取规则待扩展）"),
    ),
    EvalCase(
        key="patchy",
        filename="【参差不齐】11.9%中央空调节能调研表（首页含问题指引）.xlsx",
        expected_outcome="completed", expected_rate=11.9, expected_region=None,
        note="月份间隔填写，插值填充",
    ),
    EvalCase(
        key="summer_only",
        filename="【仅有夏季】6.5%和光同程-机房智能化调研表2023年5月版.xlsx",
        expected_outcome="needs_input", expected_rate=None, expected_region=None,
        note=("含中温/热回收机组，按系统设计应拦截转人工评估"
              "（readme 标注的 6.5% 为人工测算参考值，对应混合温度工况）"),
    ),
    EvalCase(
        key="insufficient",
        filename="【数据缺失过多 无法计算节能率】02-中央空调节能调研表（首页含问题指引）-工业板块.xlsx",
        expected_outcome="needs_input", expected_rate=None, expected_region=None,
        note="模板级缺失，必须中断并要求补充数据",
    ),
]


def load_cases() -> list:
    """加载评测集，过滤掉文件缺失的用例"""
    available = []
    for case in CASES:
        if case.survey_path.exists():
            available.append(case)
    return available
