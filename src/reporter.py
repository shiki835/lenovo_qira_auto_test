"""HTML report generator and version comparison."""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .config import Config
from .executor import RunResults, ResultEntry
from .judge import JudgeResult, judge


def generate_report(version: str, config: Config) -> str:
    """Generate an HTML report for a test run.

    Returns the path to the generated report.
    """
    results_dir = Path(__file__).parent.parent / "results" / version
    results_path = results_dir / "raw_responses.json"
    report_path = results_dir / "report.html"

    if not results_path.exists():
        raise FileNotFoundError(f"No results found for version: {version}")

    with open(results_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    results = RunResults(
        version=raw["version"],
        source_file=raw["source_file"],
        started_at=raw["started_at"],
        completed_at=raw.get("completed_at", ""),
        total=raw["total"],
        completed=raw["completed"],
    )
    for k, v in raw.get("results", {}).items():
        results.results[int(k)] = ResultEntry(**v)

    judge_results = judge(results, config)
    summary = _summarize(judge_results)
    rows_html = _build_rows(judge_results)

    html = _HTML_TEMPLATE.format(
        version=version,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        source=results.source_file,
        total=results.total,
        completed=results.completed,
        pass_count=summary["pass"],
        fail_count=summary["fail"],
        uncertain_count=summary["uncertain"],
        pass_rate=summary["pass_rate"],
        rows=rows_html,
    )

    report_path.write_text(html, encoding="utf-8")
    return str(report_path)


def compare_versions(version_a: str, version_b: str, config: Config) -> str:
    """Compare two test versions, highlighting regressions.

    Returns the path to the comparison report.
    """
    results_dir = Path(__file__).parent.parent / "results"
    compare_dir = results_dir / f"compare_{version_a}_vs_{version_b}"
    compare_dir.mkdir(parents=True, exist_ok=True)
    report_path = compare_dir / "comparison.html"

    for v in (version_a, version_b):
        p = results_dir / v / "raw_responses.json"
        if not p.exists():
            raise FileNotFoundError(f"Results not found for version: {v}")

    def _load(v):
        p = results_dir / v / "raw_responses.json"
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        r = RunResults(
            version=raw["version"],
            source_file=raw["source_file"],
            started_at=raw["started_at"],
            completed_at=raw.get("completed_at", ""),
            total=raw["total"],
            completed=raw["completed"],
        )
        for k, val in raw.get("results", {}).items():
            r.results[int(k)] = ResultEntry(**val)
        return r

    results_a = judge(_load(version_a), config)
    results_b = judge(_load(version_b), config)

    idx_a = {r.index: r for r in results_a}
    idx_b = {r.index: r for r in results_b}

    regressions = []
    improvements = []
    all_indices = sorted(set(list(idx_a.keys()) + list(idx_b.keys())))

    for idx in all_indices:
        a = idx_a.get(idx)
        b = idx_b.get(idx)
        if a and b:
            if a.verdict == "PASS" and b.verdict == "FAIL":
                regressions.append((idx, a, b))
            elif a.verdict == "FAIL" and b.verdict == "PASS":
                improvements.append((idx, a, b))

    rows = ""
    if regressions:
        rows += '<tr class="section"><td colspan="6"><b>Regressions (PASS → FAIL)</b></td></tr>'
    else:
        rows += '<tr class="section"><td colspan="6"><b>No regressions found</b></td></tr>'

    for idx, a, b in regressions:
        rows += _build_compare_row(idx, a, b, "regression")

    if improvements:
        rows += '<tr class="section"><td colspan="6"><b>Improvements (FAIL → PASS)</b></td></tr>'
        for idx, a, b in improvements:
            rows += _build_compare_row(idx, a, b, "improvement")

    html = _COMPARE_TEMPLATE.format(
        version_a=version_a,
        version_b=version_b,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        regressions=len(regressions),
        improvements=len(improvements),
        rows=rows,
    )

    report_path.write_text(html, encoding="utf-8")
    return str(report_path)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _summarize(results: list[JudgeResult]) -> dict[str, Any]:
    total = len(results)
    p = sum(1 for r in results if r.verdict == "PASS")
    f = sum(1 for r in results if r.verdict == "FAIL")
    u = sum(1 for r in results if r.verdict == "UNCERTAIN")
    return {
        "pass": p,
        "fail": f,
        "uncertain": u,
        "pass_rate": f"{(p / total * 100):.1f}%" if total > 0 else "N/A",
    }


def _build_rows(results: list[JudgeResult]) -> str:
    rows = []
    for r in results:
        cls = {"PASS": "pass", "FAIL": "fail", "UNCERTAIN": "uncertain"}.get(r.verdict, "")
        screenshot = _esc(r.screenshot_path) if r.screenshot_path else ""
        expected_escaped = _esc(r.expected[:200])
        reason_escaped = _esc(r.l2_reason) if r.l2_reason else _esc(r.error)
        rows.append(
            f'<tr class="{cls}">'
            f"<td>{r.index}</td>"
            f'<td class="q">{_esc(r.question[:80])}</td>'
            f'<td class="expected">{expected_escaped}</td>'
            f'<td class="response">{screenshot}</td>'
            f'<td class="verdict">{r.verdict}</td>'
            f'<td class="reason">{reason_escaped}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


def _build_compare_row(idx: int, a: JudgeResult, b: JudgeResult, kind: str) -> str:
    return (
        f'<tr class="{kind}">'
        f"<td>{idx}</td>"
        f'<td class="q">{_esc(a.question[:80])}</td>'
        f'<td class="expected">{_esc(a.expected[:200])}</td>'
        f'<td>{a.verdict}</td>'
        f'<td>{b.verdict}</td>'
        f'<td class="reason">{_esc(b.l2_reason)}</td>'
        f"</tr>"
    )


def _esc(text: str) -> str:
    """Basic HTML escape."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ------------------------------------------------------------------
# HTML Templates
# ------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Chat Test Report — {version}</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; margin: 40px; background: #f5f5f5; }}
  h1 {{ color: #333; }}
  .summary {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; display: flex; gap: 30px; flex-wrap: wrap; }}
  .summary .stat {{ text-align: center; }}
  .summary .stat .num {{ font-size: 32px; font-weight: bold; }}
  .summary .stat.pass .num {{ color: #22c55e; }}
  .summary .stat.fail .num {{ color: #ef4444; }}
  .summary .stat.uncertain .num {{ color: #f59e0b; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; }}
  th {{ background: #1e293b; color: white; padding: 10px 12px; text-align: left; font-size: 14px; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }}
  tr.pass {{ border-left: 4px solid #22c55e; }}
  tr.fail {{ border-left: 4px solid #ef4444; background: #fef2f2; }}
  tr.uncertain {{ border-left: 4px solid #f59e0b; background: #fffbeb; }}
  .q, .expected, .response {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .verdict {{ font-weight: bold; }}
  .reason {{ color: #6b7280; max-width: 200px; }}
  .meta {{ color: #6b7280; font-size: 13px; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>Chat Module Test Report</h1>
<div class="meta">
  Version: <b>{version}</b> | Generated: {generated_at}<br>
  Source: {source} | Questions: {completed}/{total}
</div>
<div class="summary">
  <div class="stat pass"><div class="num">{pass_count}</div>PASS</div>
  <div class="stat fail"><div class="num">{fail_count}</div>FAIL</div>
  <div class="stat uncertain"><div class="num">{uncertain_count}</div>UNCERTAIN</div>
  <div class="stat"><div class="num">{pass_rate}</div>Pass Rate</div>
</div>
<table>
<thead><tr>
  <th>#</th><th>Question</th><th>Expected</th><th>Screenshot</th><th>Verdict</th><th>Reason</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""

_COMPARE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Version Comparison — {version_a} vs {version_b}</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; margin: 40px; background: #f5f5f5; }}
  h1 {{ color: #333; }}
  .summary {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; display: flex; gap: 30px; }}
  .summary .stat {{ text-align: center; }}
  .summary .stat .num {{ font-size: 32px; font-weight: bold; }}
  .summary .stat.bad .num {{ color: #ef4444; }}
  .summary .stat.good .num {{ color: #22c55e; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; }}
  th {{ background: #1e293b; color: white; padding: 10px 12px; text-align: left; font-size: 14px; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }}
  tr.regression {{ border-left: 4px solid #ef4444; background: #fef2f2; }}
  tr.improvement {{ border-left: 4px solid #22c55e; background: #f0fdf4; }}
  tr.section td {{ background: #e2e8f0; font-weight: bold; padding: 10px 12px; }}
  .meta {{ color: #6b7280; font-size: 13px; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>Version Comparison</h1>
<div class="meta">
  <b>{version_a}</b> vs <b>{version_b}</b> | Generated: {generated_at}
</div>
<div class="summary">
  <div class="stat bad"><div class="num">{regressions}</div>Regressions</div>
  <div class="stat good"><div class="num">{improvements}</div>Improvements</div>
</div>
<table>
<thead><tr>
  <th>#</th><th>Question</th><th>Expected</th><th>{version_a}</th><th>{version_b}</th><th>Reason</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>"""
