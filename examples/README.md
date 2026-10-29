# Example reports

- [Synthetic report](synthetic_report/report.html): generated sample data for two
  configurations, three passes, and both sweep modes. No game or hardware result
  is claimed.
- [Testrun5 replay](testrun5_replay/report.html): analysis of previously supplied
  captures whose original manifests/counts/capture windows were unavailable.
  It is explicitly unverified and has no inferred repeatability interval.

Download the HTML reports and open them locally. GitHub's source view does not
execute the report's interactive controls. Keep the adjacent CSV/JSON files with
each HTML report to retain its audit links. The raw Testrun5 frame captures are
not included here.

Generate new synthetic input from the repository root with
`python examples/generate_demo.py DemoResults`, then run
`python analysis/cb_analyze.py DemoResults --baseline Demo-A --output-dir DemoAnalysis`.
