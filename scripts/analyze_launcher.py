#!/usr/bin/env python3
"""Prompt for a baseline and run the analyzer without passing input to a shell."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def validate_baseline(value):
    baseline = value.strip() or "JEDEC"
    if re.fullmatch(r"[A-Za-z0-9_-]+", baseline) is None:
        raise ValueError("Use only letters, numbers, underscores, and hyphens in the baseline label.")
    return baseline


def analyzer_command(baseline):
    # An argv list preserves argument boundaries. '=' also permits a label that
    # begins with a hyphen without treating that label as an analyzer option.
    baseline = validate_baseline(baseline)
    return [sys.executable, str(ROOT / "analysis" / "cb_analyze.py"),
            str(ROOT / "Results"), "--baseline=" + baseline]


def open_report(path):
    if os.name == "nt":
        os.startfile(str(path))
    else:
        print("Report: " + str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", help="baseline label; prompts when omitted")
    parser.add_argument("--no-open", action="store_true", help="do not open the report after analysis")
    args = parser.parse_args(argv)
    try:
        value = args.baseline
        if value is None:
            value = input("Baseline label to compare against [JEDEC]: ")
        baseline = validate_baseline(value)
    except (EOFError, KeyboardInterrupt):
        print("\nAnalysis cancelled.", file=sys.stderr)
        return 130
    except ValueError as error:
        parser.error(str(error))
    try:
        result = subprocess.run(analyzer_command(baseline), cwd=str(ROOT), shell=False)
    except OSError as error:
        print("Could not start the analyzer: " + str(error), file=sys.stderr)
        return 1
    if result.returncode:
        print("Analysis failed; an existing report has not been opened.", file=sys.stderr)
        return result.returncode
    report = ROOT / "Results" / "report.html"
    if not report.is_file():
        print("Analysis returned successfully but report.html was not created.", file=sys.stderr)
        return 1
    if not args.no_open:
        try:
            open_report(report)
        except OSError as error:
            print("Report saved at %s; could not open it: %s" % (report, error), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
