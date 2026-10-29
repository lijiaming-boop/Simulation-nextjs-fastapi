"""Run the five approved standard-energy surveys through the production quote core.

The business-owned package stays outside the repository.  This runner writes a
clean acceptance output directory containing the ten expected quote workbooks,
the normalized project JSON files, bottom sheets, and a machine-readable report.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
QUOTE_MODULE_ROOT = REPO_ROOT / "quote_module"
QUOTE_SCRIPTS_ROOT = QUOTE_MODULE_ROOT / "scripts"
for import_root in (QUOTE_MODULE_ROOT, QUOTE_SCRIPTS_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ai_client import read_survey_with_ai  # noqa: E402
from calculate import calculate  # noqa: E402
from generate_quote import write_quote_xlsx  # noqa: E402
from section9_analyzer import analyze_section9  # noqa: E402


PACKAGE_BASENAME = "standard-energy-five-project-test-20260807"
DEFAULT_PACKAGE_PARENT = Path.home() / "Desktop" / "标准能管5项目模拟测试包_20260807"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "quote" / "five_project_acceptance"


@dataclass(frozen=True)
class Case:
    case_id: str
    folder: str
    survey: str
    standard_file: str
    channel_file: str
    raw_points: int
    quote_points: int
    existing_meters: int
    new_meters: int
    total_meters: int
    cloudboxes: int
    status: str
    standard_total: float
    channel_total: float


CASES = (
    Case("P01", "P01_华南精密制造基础接入", "P01_标准能管项目调研表_模拟测试.xlsx",
         "P01_云智控报价清单_标准价_模拟测试.xlsx", "P01_云智控报价清单_渠道价_模拟测试.xlsx",
         792, 1000, 72, 0, 72, 16, "AUTO", 167737.0, 123473.6),
    Case("P02", "P02_华东食品本地化选配", "P02_标准能管项目调研表_模拟测试.xlsx",
         "P02_云智控报价清单_标准价_模拟测试.xlsx", "P02_云智控报价清单_渠道价_模拟测试.xlsx",
         600, 1000, 56, 0, 56, 14, "AUTO", 279781.0, 202914.8),
    Case("P03", "P03_华中汽车新增计量", "P03_标准能管项目调研表_模拟测试.xlsx",
         "P03_云智控报价清单_标准价_模拟测试.xlsx", "P03_云智控报价清单_渠道价_模拟测试.xlsx",
         651, 1000, 46, 15, 61, 16, "AUTO", 189333.225, 142128.58),
    Case("P04", "P04_华北化工蒸汽天然气待询价", "P04_标准能管项目调研表_模拟测试.xlsx",
         "P04_云智控报价清单_标准价_待询价测试.xlsx", "P04_云智控报价清单_渠道价_待询价测试.xlsx",
         405, 1000, 36, 3, 39, 11, "INQUIRY", 143755.875, 104458.7),
    Case("P05", "P05_华南医药非标写回控制", "P05_标准能管项目调研表_模拟测试.xlsx",
         "P05_云智控报价清单_标准价_非标阻断测试.xlsx", "P05_云智控报价清单_渠道价_非标阻断测试.xlsx",
         990, 1000, 90, 0, 90, 20, "NONSTANDARD", 185921.25, 137717.0),
)


def resolve_package_root(path: Path) -> Path:
    nested = path / PACKAGE_BASENAME
    return nested if nested.is_dir() else path


def section9_input(project: dict) -> tuple[str, str]:
    notes = project.get("project_notes", {}) or {}
    lines: list[str] = []

    def append(value) -> None:
        if isinstance(value, str):
            value = value.strip()
            if value and value not in lines:
                lines.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                append(item)

    for key in ("goals", "smart_analysis", "special_requirements", "other_notes"):
        append(notes.get(key))
    for system in project.get("third_party_systems", []) or []:
        append("；".join(
            str(system.get(key, "")).strip()
            for key in ("name", "type", "direction", "description", "implementation", "remark")
            if str(system.get(key, "") or "").strip()
        ))
    return str(notes.get("current_status", "") or ""), "\n".join(lines)


def assert_close(actual: float, expected: float, label: str, tolerance: float = 0.01) -> None:
    if abs(float(actual) - expected) > tolerance:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def run_case(case: Case, package_root: Path, output_root: Path) -> dict:
    survey_path = package_root / case.folder / case.survey
    if not survey_path.is_file():
        raise FileNotFoundError(f"缺少验收输入: {survey_path}")

    case_output = output_root / case.case_id
    case_output.mkdir(parents=True, exist_ok=True)
    project = read_survey_with_ai(str(survey_path))
    current_status, goals = section9_input(project)
    section9 = analyze_section9(current_status=current_status, goals=goals)
    bottom_sheet = calculate(project, tax_mode="inclusive", section9_analysis=section9)

    calculations = bottom_sheet["calculations"]
    totals = bottom_sheet["totals"]
    actual = {
        "raw_points": calculations["raw_points"],
        "quote_points": calculations["quote_points"],
        "existing_meters": calculations["existing_meter_count"],
        "new_meters": calculations["new_meter_count"],
        "total_meters": calculations["total_meter_count"],
        "cloudboxes": calculations["total_cloudbox"],
        "status": bottom_sheet["quote_status"],
        "release_ready": bottom_sheet["release_ready"],
        "standard_total": totals["grand_total_standard"],
        "channel_total": totals["grand_total_channel"],
    }
    expected = {
        "raw_points": case.raw_points,
        "quote_points": case.quote_points,
        "existing_meters": case.existing_meters,
        "new_meters": case.new_meters,
        "total_meters": case.total_meters,
        "cloudboxes": case.cloudboxes,
        "status": case.status,
        "standard_total": case.standard_total,
        "channel_total": case.channel_total,
    }
    for key in ("raw_points", "quote_points", "existing_meters", "new_meters", "total_meters", "cloudboxes", "status"):
        if actual[key] != expected[key]:
            raise AssertionError(f"{case.case_id} {key}: expected {expected[key]}, got {actual[key]}")
    assert_close(actual["standard_total"], expected["standard_total"], f"{case.case_id} standard_total")
    assert_close(actual["channel_total"], expected["channel_total"], f"{case.case_id} channel_total")

    project_path = case_output / "project.json"
    bottom_sheet_path = case_output / "internal_bottom_sheet.json"
    project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    bottom_sheet_path.write_text(json.dumps(bottom_sheet, ensure_ascii=False, indent=2), encoding="utf-8")
    standard_path = case_output / case.standard_file
    channel_path = case_output / case.channel_file
    generated_standard = write_quote_xlsx(bottom_sheet, "standard", str(standard_path))
    generated_channel = write_quote_xlsx(bottom_sheet, "channel", str(channel_path))
    assert_close(generated_standard, expected["standard_total"], f"{case.case_id} generated standard")
    assert_close(generated_channel, expected["channel_total"], f"{case.case_id} generated channel")

    return {
        "case_id": case.case_id,
        "input": str(survey_path),
        "expected": expected,
        "actual": actual,
        "passed": True,
        "outputs": {
            "standard_quote": str(standard_path),
            "channel_quote": str(channel_path),
            "project_json": str(project_path),
            "bottom_sheet": str(bottom_sheet_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行标准能管5项目报价验收")
    parser.add_argument("--package-root", type=Path, default=DEFAULT_PACKAGE_PARENT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    package_root = resolve_package_root(args.package_root.expanduser().resolve())
    output_root = args.output_root.expanduser().resolve()
    if not package_root.is_dir():
        raise FileNotFoundError(f"测试包不存在: {package_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    results = [run_case(case, package_root, output_root) for case in CASES]
    report = {
        "package_root": str(package_root),
        "output_root": str(output_root),
        "tax_mode": "inclusive",
        "passed": all(item["passed"] for item in results),
        "cases": results,
    }
    report_path = output_root / "acceptance_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[PASS] {len(results)}/{len(CASES)} 项通过")
    print(f"[REPORT] {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
