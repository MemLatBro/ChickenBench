# Using the stability analysis

The Python modules are grouped in `analysis/`. Run commands below from the
repository root. Keep the whole folder layout intact; no pip packages or
MemLat Pro installation are required. `CB_Analyze.bat` launches the analysis
through the validated baseline prompt.

```text
py -3 analysis/cb_analyze.py Results --baseline JEDEC
```

The starting workload of **each configuration/mode** becomes its 100% reference.
Repeated laps at that starting level are averaged. `--baseline JEDEC` still selects
the label used for the original cross-configuration comparisons; it does not select
the reference workload for the new retention curves.

To put all newly generated files elsewhere and leave existing Results outputs in place:

```text
py -3 analysis/cb_analyze.py Results --baseline JEDEC --output-dir Analysis
```

To select reference workload levels explicitly:

```text
py -3 analysis/cb_analyze.py Results --reference-chickens 50 --reference-timescale 1
```

Every prior analytical file in the selected output destination is preserved in
`analysis_backups/<timestamp>/` before replacement. Capture CSVs and lap manifests
are never modified. The three original CSV schemas and calculations are retained.
The original graphs/tables remain in `report.html` with a new analysis section.

New files:

| File | Contents |
| --- | --- |
| `stability_summary.csv` | one workload-wide aggregate and retention score per configuration/mode/metric, range, coverage, loss rate and joint uncertainty |
| `stability_metrics.csv` | native means, retention, degradation, local rates, repeated-lap dispersion, uncertainty, units, sample counts, flags and provenance |
| `stability_laps.csv` | individual lap statistics and per-metric inclusion/exclusion reasons, duration/count evidence, frame-row diagnostics and hashes |
| `stability_metadata.json` | formula/options, selected references, schedules, context hashes and methodological limits |
| `stability_report.html` | standalone interactive report, all configuration labels, embedded analytical CSV download |

Open `report.html` or `stability_report.html`. The first section shows separate
summary cards for average FPS, 1% low FPS and 0.1% low FPS. Each includes its
aggregate FPS, workload-average retention score and end-to-end loss rate. All
metrics also appear in an expandable summary table and `stability_summary.csv`.
Scores use trapezoidal integration across the actual workload span; compare the
same range/reference, and inspect coverage. Missing levels withhold an area score.
Choose a metric from the dropdown;
hover a point for values, interval, lap count and flags. Hollow points have
unverified workload/capture metadata. Expand the numerical table for exact
availability reasons. The analytical CSV download is embedded in the HTML; audit
and metadata links work when those files are kept alongside the report.

Each metric has its own singular summary; different metrics and sweep modes remain separate.
One pass supplies point estimates, not an inferred repeated-measurement interval.
The reference's exact 100% identity does not make its native measurement error zero.

## Validation and examples

From the repository root:

```text
py -3 scripts/run_tests.py
```

Generate deterministic synthetic captures and run the complete analyzer:

```text
py -3 examples/generate_demo.py DemoResults
py -3 analysis/cb_analyze.py DemoResults --baseline Demo-A --output-dir DemoAnalysis
```

The bundled `examples/synthetic_report/` is an example with two configurations,
three passes and both sweep modes. It is synthetic and makes no hardware claim.

`examples/testrun5_replay/` contains a report computed from the eleven available
Testrun5 frame files. Their original manifests, counts and requested capture windows
were unavailable. Its coordinates are inferred from filenames, every measurement is
marked provisional, and no repeatability interval is inferred from its one pass.
The raw captures are not duplicated in this package; they remain the original files.

To reproduce an unverified replay from a directory of original flat frame CSVs:

```text
py -3 examples/import_captures.py OriginalCaptures ReplayResults
py -3 analysis/cb_analyze.py ReplayResults --include-unverified-imports --output-dir ReplayAnalysis
```

The import creates new copies and an explicit `imported_unverified` manifest. It
never fabricates successful runner counts/statuses and never alters the source
captures. Such imports are excluded from the legacy usable summaries.

For methodology and the future adapter contract, read `FORMULAS.md`. For the
verified original pipeline and exact change locations, read `AUDIT.md`.
