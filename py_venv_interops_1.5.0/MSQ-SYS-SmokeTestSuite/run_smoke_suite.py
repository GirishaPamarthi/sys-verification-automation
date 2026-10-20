"""Run the Mosaiq smoke test suite from this workspace.

Usage examples:
    python MSQ-SYS-SmokeTestSuite/run_smoke_suite.py
    python MSQ-SYS-SmokeTestSuite/run_smoke_suite.py --list
    python MSQ-SYS-SmokeTestSuite/run_smoke_suite.py --test MSQ-SMK-001
"""

from __future__ import annotations

import argparse
import ast
import html
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

SUITE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SUITE_ROOT.parent

# msq_framework is importable via Lib/site-packages/msq_test_paths.pth.
from msq_framework import reporting

SUITE_REPORT_NAME = "SMK Test Suite"

# The suite page is styled like a native Squish html report, so it needs the same
# two asset directories the generator copies into every case report. They ship with
# the Squish runtime install; a generated case report is used as a fallback source.
WEBREPORT_TEMPLATE_DIR = Path(reporting.SQUISH_RUNTIME_ROOT) / "lib" / "webreport"
REPORT_ASSET_DIRS = ("css", "dist")

# Used only when neither asset source is reachable, so the page is still readable
# instead of unstyled.
FALLBACK_STYLE = """
    body { font-family: Arial; color: rgb(80, 80, 80); margin: 20px; }
    a { text-decoration: none; color: #4183c4; }
    h3 { margin: 0 0 10px 0; }
    .segment { border: 1px solid rgba(34,36,38,.15); border-radius: 4px;
               padding: 14px; margin-bottom: 14px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 10px; }
    th, td { border: 1px solid rgba(34,36,38,.1); padding: 8px; text-align: left; }
    th { background: #f9fafb; }
    tr.positive { background: #fcfff5; color: #2c662d; }
    tr.error { background: #fff6f6; color: #9f3a38; }
    tr.disabled { color: #b9b9b9; }
"""

# Row colouring per status, matching the Squish summary table.
STATUS_ROW_CLASS = {"completed": "positive", "not run": "disabled"}


def discover_cases() -> list[tuple[str, Path]]:
    """Every MSQ-SMK-* script in this folder is a test case of the suite.

    Membership is by filename, not by what a run selected: --test narrows what
    actually executes, but the suite report still accounts for all of them, so the
    totals describe the suite rather than the invocation.
    """
    cases: list[tuple[str, Path]] = []
    for case_path in sorted(SUITE_ROOT.glob("MSQ-SMK-*.py")):
        if case_path.name == Path(__file__).name:
            continue
        cases.append((case_path.stem, case_path))
    return cases


TEST_CASES = discover_cases()
CASE_PATHS = dict(TEST_CASES)

# case name -> the TEST_CASE_NAME its script reports under; see case_report_name().
_REPORT_NAMES: dict[str, str] = {}


def list_cases() -> list[str]:
    return [name for name, _ in TEST_CASES]


def case_report_name(case_name: str) -> str:
    """The name a case reports under -- its TEST_CASE_NAME, not its filename.

    start_reporting() defaults the output directory to <RESULTS_ROOT>/<TEST_CASE_NAME>,
    so linking by filename (MSQ-SMK-002) never resolves: the report is under the
    human-readable name the script declares. Read with ast rather than by importing
    the case, because importing one pulls in squishtest and interops.

    Falls back to the filename if the script does not declare a module-level
    TEST_CASE_NAME string, which is also where the report would land.
    """
    if case_name in _REPORT_NAMES:
        return _REPORT_NAMES[case_name]

    report_name = case_name
    case_path = CASE_PATHS.get(case_name)
    if case_path is not None:
        try:
            module = ast.parse(case_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            module = None
        for node in getattr(module, "body", []):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "TEST_CASE_NAME" in targets and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    report_name = node.value.value

    _REPORT_NAMES[case_name] = report_name
    return report_name


def case_report_dir(case_name: str) -> Path:
    return Path(reporting.default_report_dir(case_report_name(case_name)))


def suite_report_dir() -> Path:
    return Path(reporting.default_report_dir(SUITE_REPORT_NAME))


def copy_report_assets(suite_dir: Path, suite_cases: Iterable[str]) -> bool:
    """Copy the Squish web report css/ and dist/ next to the suite page.

    Tries the runtime's template copy first, then any case report that already has
    them, so the suite page still renders when Squish is not installed locally but
    a case report is present. Returns whether the assets landed.
    """
    sources = [WEBREPORT_TEMPLATE_DIR]
    sources += [case_report_dir(case_name) for case_name in suite_cases]

    for source in sources:
        if not all((source / name).is_dir() for name in REPORT_ASSET_DIRS):
            continue
        for name in REPORT_ASSET_DIRS:
            shutil.copytree(source / name, suite_dir / name, dirs_exist_ok=True)
        return True
    return False


def format_duration(seconds: float | None) -> str:
    """Same wording squish-lib.js' formatDiff() uses, so both pages read alike."""
    if seconds is None:
        return "-"
    total = int(seconds)
    if total == 0:
        return "< 1 sec."
    if total < 60:
        return f"{total} sec."
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} min. {secs} sec."
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}min. {secs}sec."


def status_row_class(status: str) -> str:
    """Semantic UI row colour: anything that is not completed or unrun is a failure."""
    return STATUS_ROW_CLASS.get(status, "error")


def format_timestamp(when: float | None) -> str:
    return "-" if when is None else str(datetime.fromtimestamp(when))


def write_suite_summary(
    suite_cases: Iterable[str],
    results: dict[str, dict],
    started_at: float | None = None,
    stopped_at: float | None = None,
) -> None:
    """Write the suite landing page.

    :param suite_cases: every case belonging to the suite, in report order
    :param results: status/duration per case that ran; anything absent is "not run"
    """
    suite_dir = suite_report_dir()
    suite_dir.mkdir(parents=True, exist_ok=True)
    summary_path = suite_dir / "index.html"

    suite_cases = list(suite_cases)
    has_assets = copy_report_assets(suite_dir, suite_cases)
    suite_duration = None
    if started_at is not None and stopped_at is not None:
        suite_duration = stopped_at - started_at

    rows = []
    passes = failures = not_run = 0
    for case_name in suite_cases:
        result = results.get(case_name, {})
        status = result.get("status", "not run")
        if status == "completed":
            passes += 1
        elif status == "not run":
            not_run += 1
        else:
            failures += 1

        # Case reports are siblings of the suite directory under RESULTS_ROOT, so a
        # relative href works wherever the results tree is copied to. quote() because
        # report names are prose and contain spaces.
        report_dir = case_report_dir(case_name)
        if (report_dir / "index.html").exists():
            href = f"../{quote(report_dir.name)}/index.html"
            report_cell = (
                f'<a href="{href}" title="{html.escape(report_dir.name)}">Open report</a>'
            )
        else:
            report_cell = '<span class="skippedColor">No report generated</span>'

        rows.append(
            f'                    <tr class="{status_row_class(status)}">'
            f"<td>{html.escape(case_name)}</td>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{format_duration(result.get('duration'))}</td>"
            f"<td>{report_cell}</td></tr>"
        )

    # The page covers one suite, so exactly one of these is 1: its status is the worst
    # of its cases, the way Squish rolls a suite up from the cases it contains. A
    # suite with cases left unrun is not a pass, so "not run" outranks "completed".
    total_cases = len(suite_cases)
    if failures:
        suite_status = "failed"
    elif not_run or not total_cases:
        suite_status = "not run"
    else:
        suite_status = "completed"

    pass_suites = int(suite_status == "completed")
    fail_suites = int(suite_status == "failed")
    not_run_suites = int(suite_status == "not run")

    # "not run" covers both a suite nothing ran for and one only partly run; say which.
    suite_label = "incomplete" if suite_status == "not run" and passes else suite_status

    # span.suiteHeader is red by default in the Squish stylesheet; the pass/skipped
    # rules follow it, so adding one of those recolours the bar.
    suite_header_class = {"completed": " pass", "not run": " skipped"}.get(suite_status, "")
    pass_percent = int(passes / total_cases * 100) if total_cases else 100

    suite_counts = f'<span class="big">{total_cases}</span><span class="small">Test Cases</span>'
    if failures:
        suite_counts += (
            f'<span class="fcount"><span class="big">{failures}</span>'
            f'<span class="small">failed</span></span>'
        )
    if not_run:
        suite_counts += (
            f'<span class="skippedColor">(<span class="big">{not_run}</span>'
            f'<span class="small">not run</span>)</span>'
        )

    if has_assets:
        head_styles = (
            '    <link rel="stylesheet" href="css/style.css" type="text/css" '
            'media="screen, projection">\n'
            '    <link rel="stylesheet" type="text/css" href="dist/semantic.min.css">'
        )
    else:
        head_styles = f"    <style>{FALLBACK_STYLE}    </style>"

    summary_html = f"""<!DOCTYPE html>
<html>

<head>
    <title>Squish Report</title>
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
{head_styles}
</head>

<body>

    <div id="squishTestReport" class="ui segment">

        <h3 class="ui top attached header">MOSAIQ Smoke Test Suite Results</h3>

        <div id="squishSummary" class="ui attached segment">
            <div class="ui two column grid">
                <div class="six wide column">
                    <div class="ui basic horizontal segment">   
                        <table class="ui celled striped table">
                            <thead>
                                <tr><th colspan="2">Time data</th></tr>
                            </thead>
                            <tbody>
                                <tr><td>Start</td><td id="startTime">{format_timestamp(started_at)}</td></tr>
                                <tr><td>End</td><td id="stopTime">{format_timestamp(stopped_at)}</td></tr>
                                <tr><td>Duration</td><td id="duration">{format_duration(suite_duration)}</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="five wide column">
                    <div class="ui basic horizontal segment">
                        <table class="ui celled table">
                            <thead>
                                <tr><th></th><th>Test Suites</th><th>Test Cases</th></tr>
                            </thead>
                            <tbody>
                                <tr class="positive">
                                    <td><i class="icon checkmark"></i>Passes</td>
                                    <td id="passTS">{pass_suites}</td><td id="passTC">{passes}</td>
                                </tr>
                                <tr class="error">
                                    <td><i class="warning circle icon"></i>Failures</td>
                                    <td id="failTS">{fail_suites}</td><td id="failTC">{failures}</td>
                                </tr>
                                <tr class="disabled">
                                    <td><i class="warning circle icon"></i>Not run</td>
                                    <td id="disTS">{not_run_suites}</td><td id="disTC">{not_run}</td>
                                </tr>
                                <tr>
                                    <td>Total</td>
                                    <td id="totalTS">1</td><td id="totalTC">{total_cases}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <div id="squishTitle" class="ui segment">
            <span class="suiteHeader{suite_header_class} suiteHeader_l0">
                <span class="proc">
                    <span class="big bigsize0">{pass_percent}</span><span class="small smallsize0">%</span>
                </span>
                <span class="failures smallsize0">{suite_counts}</span>
                <span class="name"><span class="big bigsize1">{html.escape(SUITE_REPORT_NAME)}</span>
                    <span class="small smallsize1">Test Suite - {html.escape(suite_label)}</span></span>
                <span class="duration smallsize1">{format_duration(suite_duration)}</span>
            </span>
        </div>

        <div id="squishResults" class="ui segment attached">
            <table class="ui celled striped table">
                <thead>
                    <tr><th>Test case</th><th>Status</th><th>Duration</th><th>Report</th></tr>
                </thead>
                <tbody>
{chr(10).join(rows)}
                </tbody>
            </table>
        </div>
    </div>

</body>

</html>
"""
    summary_path.write_text(summary_html, encoding="utf-8")
    print(f"\nSmoke suite report written to: {summary_path}")


def run_case(case_name: str, case_path: Path) -> tuple[str, dict]:
    print(f"\n=== Running {case_name} ===")
    started = time.time()
    completed = subprocess.run(
        [sys.executable, str(case_path)],
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    duration = time.time() - started

    if completed.returncode == 0:
        print(f"=== Completed {case_name} ===\n")
        return case_name, {"status": "completed", "duration": duration}

    print(f"=== Failed {case_name} (exit code {completed.returncode}) ===\n")
    return case_name, {
        "status": f"failed (exit code {completed.returncode})",
        "duration": duration,
    }


def run_suite(selected_cases: Iterable[str] | None = None) -> int:
    requested = set(selected_cases) if selected_cases else set(list_cases())
    missing = sorted(requested - set(list_cases()))
    if missing:
        raise SystemExit(f"Unknown test case(s): {', '.join(missing)}")

    results: dict[str, dict] = {}

    started_at = time.time()
    for case_name, case_path in TEST_CASES:
        if case_name not in requested:
            continue
        case_name, result = run_case(case_name, case_path)
        results[case_name] = result
    stopped_at = time.time()

    # Every discovered case, not just the requested ones: cases --test skipped belong
    # to the suite and are reported as "not run" rather than omitted.
    write_suite_summary(list_cases(), results, started_at, stopped_at)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Mosaiq smoke test suite.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the available smoke test case names.",
    )
    parser.add_argument(
        "--test",
        action="append",
        default=[],
        help="Run one or more named smoke tests. Repeat the flag to run multiple tests.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        print("Available smoke test cases:")
        for case_name in list_cases():
            print(f"- {case_name}")
        return 0

    return run_suite(args.test or None)


if __name__ == "__main__":
    raise SystemExit(main())
