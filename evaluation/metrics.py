"""评测指标

核心指标：
1. 流程决策正确率：该算的算完（completed）、该拦的拦下（needs_input）
2. 节能率偏差：预期值与计算区间 [min, max] 的距离（百分点），≤2pp 视为达标
3. 地区识别正确率：三级推断策略与文件名锚点一致
"""
from __future__ import annotations

from typing import Optional

# 节能率允许偏差（百分点）
RATE_TOLERANCE_PP = 2.0


def rate_band_deviation_pp(expected_rate: float, rate_min: Optional[float],
                           rate_max: Optional[float]) -> Optional[float]:
    """预期节能率到计算区间 [min, max] 的距离（百分点）

    预期落在区间内 → 0；低于下限/高于上限 → 到最近端点的距离。
    任一端点缺失返回 None。
    """
    if rate_min is None or rate_max is None:
        return None
    lo, hi = min(rate_min, rate_max) * 100, max(rate_min, rate_max) * 100
    if lo <= expected_rate <= hi:
        return 0.0
    return round(min(abs(expected_rate - lo), abs(expected_rate - hi)), 2)


def judge_case(case, final_status: str, result: Optional[dict],
               extracted_region: Optional[str]) -> dict:
    """汇总单个用例的评测判定"""
    outcome_correct = final_status == case.expected_outcome

    deviation = None
    rate_pass = None
    if case.expected_rate is not None and result is not None:
        deviation = rate_band_deviation_pp(
            case.expected_rate,
            result.get("energy_saving_rate_min"),
            result.get("energy_saving_rate_max"),
        )
        rate_pass = deviation is not None and deviation <= RATE_TOLERANCE_PP

    region_correct = None
    if case.expected_region is not None:
        region_correct = extracted_region == case.expected_region

    return {
        "key": case.key,
        "expected_outcome": case.expected_outcome,
        "actual_outcome": final_status,
        "outcome_correct": outcome_correct,
        "known_gap": getattr(case, "known_gap", None),
        "expected_rate": case.expected_rate,
        "rate_min": (result or {}).get("energy_saving_rate_min"),
        "rate_max": (result or {}).get("energy_saving_rate_max"),
        "rate_range": (result or {}).get("energy_saving_rate_range"),
        "rate_deviation_pp": deviation,
        "rate_pass": rate_pass,
        "expected_region": case.expected_region,
        "actual_region": extracted_region,
        "region_correct": region_correct,
        "note": case.note,
    }


def aggregate(results: list) -> dict:
    """汇总指标（overall 含已知缺口用例；excl_gaps 剔除后单独统计）"""
    total = len(results)
    if total == 0:
        return {"total": 0}
    outcome_correct = sum(1 for r in results if r["outcome_correct"])
    interrupted = [r for r in results if r["expected_outcome"] == "needs_input"]
    interrupt_correct = sum(1 for r in interrupted if r["outcome_correct"])
    rated = [r for r in results if r["rate_pass"] is not None]
    rate_pass = sum(1 for r in rated if r["rate_pass"])
    deviations = [r["rate_deviation_pp"] for r in rated if r["rate_deviation_pp"] is not None]
    regions = [r for r in results if r["region_correct"] is not None]
    region_correct = sum(1 for r in regions if r["region_correct"])

    gap_cases = [r for r in results if r.get("known_gap")]
    non_gap = [r for r in results if not r.get("known_gap")]
    non_gap_correct = sum(1 for r in non_gap if r["outcome_correct"])

    return {
        "total": total,
        "outcome_accuracy": round(outcome_correct / total, 4),
        "known_gap_count": len(gap_cases),
        "outcome_accuracy_excl_gaps": (
            round(non_gap_correct / len(non_gap), 4) if non_gap else None
        ),
        "interrupt_correctness": f"{interrupt_correct}/{len(interrupted)}" if interrupted else "n/a",
        "rate_evaluated": len(rated),
        "rate_pass": rate_pass,
        "rate_pass_rate": round(rate_pass / len(rated), 4) if rated else None,
        "rate_deviation_mean_pp": round(sum(deviations) / len(deviations), 2) if deviations else None,
        "rate_deviation_max_pp": round(max(deviations), 2) if deviations else None,
        "rate_tolerance_pp": RATE_TOLERANCE_PP,
        "region_accuracy": round(region_correct / len(regions), 4) if regions else None,
    }
