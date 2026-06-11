"""CLI entry point for the chat test automation framework.

Commands:
    run      Execute tests from an Excel dataset
    judge    Run judgment on an existing test run
    report   Generate HTML report for a version
    compare  Compare two versions (find regressions)
"""

import argparse
import sys
from pathlib import Path

from .config import load_config, Config


def main():
    parser = argparse.ArgumentParser(
        prog="chat-test",
        description="Automated chat module testing framework",
    )
    parser.add_argument(
        "--config", "-c", type=str, default=None,
        help="Path to config.yaml",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    p_run = sub.add_parser("run", help="Execute tests")
    p_run.add_argument("--version", "-v", default=None, help="Version label (default from config.yaml)")
    p_run.add_argument("--excel", "-e", required=True, help="Path to Excel dataset")

    # --- judge ---
    p_judge = sub.add_parser("judge", help="Run judgment on results")
    p_judge.add_argument("--version", "-v", required=True, help="Version to judge")

    # --- report ---
    p_report = sub.add_parser("report", help="Generate HTML report")
    p_report.add_argument("--version", "-v", required=True, help="Version to report")

    # --- compare ---
    p_compare = sub.add_parser("compare", help="Compare two versions")
    p_compare.add_argument("--version-a", "-a", required=True, help="Baseline version")
    p_compare.add_argument("--version-b", "-b", required=True, help="New version")

    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "run":
        _cmd_run(args, config)
    elif args.command == "judge":
        _cmd_judge(args, config)
    elif args.command == "report":
        _cmd_report(args, config)
    elif args.command == "compare":
        _cmd_compare(args, config)


def _cmd_run(args, config: Config):
    from .executor import Executor

    excel_path = args.excel
    if not Path(excel_path).exists():
        print(f"Error: Excel file not found: {excel_path}")
        sys.exit(1)

    version = args.version or config.version
    executor = Executor(config, version)
    results = executor.run(excel_path)

    errors = sum(1 for r in results.results.values() if r.error)
    sys.exit(0 if errors == 0 else 1)


def _cmd_judge(args, config: Config):
    from .judge import judge_version

    results = judge_version(args.version, config)
    p = sum(1 for r in results if r.verdict == "PASS")
    f = sum(1 for r in results if r.verdict == "FAIL")
    u = sum(1 for r in results if r.verdict == "UNCERTAIN")

    print(f"Version: {args.version}")
    print(f"  PASS:      {p}")
    print(f"  FAIL:      {f}")
    print(f"  UNCERTAIN: {u}")
    print(f"  Pass rate: {p / len(results) * 100:.1f}%" if results else "N/A")

    for r in results:
        if r.verdict in ("FAIL", "UNCERTAIN"):
            print(f"\n  [{r.verdict}] Q{r.index}: {r.question[:60]}...")
            print(f"    Expected: {r.expected[:80]}...")
            print(f"    Got:      {r.response[:80]}...")
            if r.l2_reason:
                print(f"    Reason:   {r.l2_reason}")


def _cmd_report(args, config: Config):
    from .reporter import generate_report

    path = generate_report(args.version, config)
    print(f"Report generated: {path}")


def _cmd_compare(args, config: Config):
    from .reporter import compare_versions

    path = compare_versions(args.version_a, args.version_b, config)
    print(f"Comparison report generated: {path}")


if __name__ == "__main__":
    main()
