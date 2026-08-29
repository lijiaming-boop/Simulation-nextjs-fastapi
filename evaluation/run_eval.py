"""回归评测运行器

以确定性模式（RuleBrain，零 LLM 成本）对标注样例调研表逐个执行
agent 主线流程，比对预期结果并产出报告。

用法：
    python -m evaluation.run_eval                    # 运行并输出报告
    python -m evaluation.run_eval --save-baseline    # 保存结果为回归基线
    python -m evaluation.run_eval --compare-baseline # 与基线比对（回归检查）

产出：
    evaluation/runs/<run_id>/report.json   本次运行明细
    evaluation/report.md                   人类可读报告（覆盖更新）
    evaluation/baselines.json              回归基线（--save-baseline 时更新）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 保证从任意工作目录运行都能找到项目根
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import AgentOrchestrator, RuleBrain  # noqa: E402
from agent.tools import build_default_registry  # noqa: E402
from evaluation.dataset import load_cases  # noqa: E402
from evaluation.metrics import aggregate, judge_case  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "evaluation"
RUNS_DIR = EVAL_DIR / "runs"
BASELINE_PATH = EVAL_DIR / "baselines.json"
REPORT_MD_PATH = EVAL_DIR / "report.md"


def run_case(case, run_dir: Path) -> dict:
    """对单个用例跑完整 agent 主线（确定性策略，零 token）"""
    session_dir = run_dir / case.key
    session_dir.mkdir(parents=True, exist_ok=True)

    orch = AgentOrchestrator(
        session_id=case.key,
        session_dir=session_dir,
        survey_path=case.survey_path,
        original_filename=case.filename,
        brain=RuleBrain(),
        registry=build_default_registry(),
    )
    t0 = time.monotonic()
    final = orch.run()
    duration_s = round(time.monotonic() - t0, 1)

    result = orch.ctx.get("result")
    extracted = orch.ctx.get("extracted_data") or {}
    judgment = judge_case(case, final["status"], result, extracted.get("project_region"))
    judgment["duration_s"] = duration_s
    judgment["agent_summary"] = final["summary"][:200]
    judgment["steps"] = [s["tool"] for s in orch.trace.steps]
    return judgment


def save_report(run_id: str, results: list, summary: dict) -> None:
    """写 JSON 明细 + Markdown 报告"""
    run_dir = RUNS_DIR / run_id
    with open(run_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "summary": summary, "results": results},
                  f, ensure_ascii=False, indent=2)

    lines = [
        "# Agent 主线回归评测报告",
        "",
        f"- 运行时间：{run_id}",
        "- 决策模式：deterministic（RuleBrain，零 LLM 成本，结果可复现）",
        f"- 评测集：{summary['total']} 份标注样例调研表（00_sample/示例调研表/）",
        "",
        "## 汇总指标",
        "",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 流程决策正确率（全部用例） | {summary['outcome_accuracy']:.0%} |",
    ]
    if summary.get("outcome_accuracy_excl_gaps") is not None:
        lines.append(
            f"| 流程决策正确率（剔除已知缺口） | {summary['outcome_accuracy_excl_gaps']:.0%} "
            f"（已知缺口 {summary['known_gap_count']} 例，见文末说明） |"
        )
    lines += [
        f"| 低质量数据中断正确 | {summary['interrupt_correctness']} |",
        f"| 节能率达标（≤{summary['rate_tolerance_pp']}pp） | {summary['rate_pass']}/{summary['rate_evaluated']}"
        + (f"（{summary['rate_pass_rate']:.0%}）" if summary.get("rate_pass_rate") is not None else "") + " |",
        f"| 节能率平均偏差 | {summary.get('rate_deviation_mean_pp', 'n/a')} pp |",
        f"| 节能率最大偏差 | {summary.get('rate_deviation_max_pp', 'n/a')} pp |",
    ]
    if summary.get("region_accuracy") is not None:
        lines.append(f"| 地区识别正确率 | {summary['region_accuracy']:.0%} |")
    lines += [
        "",
        "## 用例明细",
        "",
        "| 用例 | 预期 | 实际 | 预期节能率 | 计算区间 | 偏差(pp) | 达标 | 地区 | 耗时(s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        exp = r["expected_outcome"]
        rate = f"{r['expected_rate']}%" if r["expected_rate"] else "—"
        rng = r["rate_range"] or "—"
        dev = r["rate_deviation_pp"] if r["rate_deviation_pp"] is not None else "—"
        ok = "✅" if r["outcome_correct"] and r["rate_pass"] is not False else ("⚠️" if r["outcome_correct"] else "❌")
        region = "—"
        if r["expected_region"]:
            region = f"{'✅' if r['region_correct'] else '❌'} {r['actual_region'] or '?'}"
        lines.append(
            f"| {r['key']} | {exp} | {r['actual_outcome']} | {rate} | {rng} | {dev} | {ok} | {region} | {r['duration_s']} |"
        )

    failing = [r for r in results if not r["outcome_correct"] or r["rate_pass"] is False]
    if failing:
        lines += ["", "## 未达标用例与已知缺口说明", ""]
        for r in failing:
            if r.get("known_gap"):
                lines.append(
                    f"- **{r['key']}**（已知能力缺口）：{r['known_gap']}。"
                    f"系统行为：{r['actual_outcome']}（按设计拦截，待补齐提取规则后预期可算）。"
                )
            else:
                lines.append(
                    f"- **{r['key']}**：{r['note']}。实际 {r['actual_outcome']}，"
                    f"区间 {r['rate_range'] or '无'}，摘要：{r['agent_summary'][:120]}"
                )
    lines += ["", "## 复现", "", "```bash", "python -m evaluation.run_eval", "```", ""]
    REPORT_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def load_baseline() -> dict:
    if BASELINE_PATH.exists():
        with open(BASELINE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def compare_baseline(results: list) -> list:
    """与基线比对节能率区间，返回回归差异列表"""
    baseline = load_baseline()
    diffs = []
    for r in results:
        b = baseline.get(r["key"], {}).get("rate_range")
        if b and b != r["rate_range"]:
            diffs.append({"key": r["key"], "baseline": b, "current": r["rate_range"]})
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent 主线回归评测")
    parser.add_argument("--save-baseline", action="store_true", help="把本次结果保存为回归基线")
    parser.add_argument("--compare-baseline", action="store_true", help="与已存基线比对")
    args = parser.parse_args()

    cases = load_cases()
    if not cases:
        print("❌ 评测集为空：未找到样例调研表")
        return 1

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Agent 回归评测（{len(cases)} 用例，确定性模式，零 LLM 成本）===")
    results = []
    for case in cases:
        print(f"▶ {case.key}: {case.filename[:50]}...")
        try:
            r = run_case(case, run_dir)
        except Exception as e:
            r = {
                "key": case.key, "expected_outcome": case.expected_outcome,
                "actual_outcome": "error", "outcome_correct": False,
                "expected_rate": case.expected_rate, "rate_min": None, "rate_max": None,
                "rate_range": None, "rate_deviation_pp": None, "rate_pass": None,
                "expected_region": case.expected_region, "actual_region": None,
                "region_correct": None, "note": case.note, "duration_s": 0,
                "agent_summary": f"{type(e).__name__}: {e}", "steps": [],
            }
        mark = "✅" if r["outcome_correct"] else "❌"
        print(f"  {mark} {r['actual_outcome']} 区间={r['rate_range'] or '—'} "
              f"偏差={r['rate_deviation_pp'] if r['rate_deviation_pp'] is not None else '—'}pp "
              f"({r['duration_s']}s)")
        results.append(r)

    summary = aggregate(results)
    save_report(run_id, results, summary)

    if args.save_baseline:
        baseline = {r["key"]: {"rate_range": r["rate_range"],
                               "rate_min": r["rate_min"], "rate_max": r["rate_max"],
                               "actual_outcome": r["actual_outcome"]} for r in results}
        with open(BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)
        print(f"📌 基线已保存: {BASELINE_PATH}")

    if args.compare_baseline:
        diffs = compare_baseline(results)
        if diffs:
            print(f"❌ 与基线存在 {len(diffs)} 处差异（CI 门禁失败）:")
            for d in diffs:
                print(f"  - {d['key']}: 基线 {d['baseline']} → 当前 {d['current']}")
            return 2
        print("✅ 与基线完全一致，无回归")

    print(f"\n=== 汇总: 决策正确率 {summary['outcome_accuracy']:.0%}, "
          f"节能率达标 {summary['rate_pass']}/{summary['rate_evaluated']}, "
          f"平均偏差 {summary.get('rate_deviation_mean_pp', 'n/a')}pp ===")
    print(f"报告: {REPORT_MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
