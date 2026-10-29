> Historical source audit for the flat 1.0.6/1.0.7 package. Current source paths are listed in [README](../README.md).

# Source audit and implementation map

The inspected source is `ChickenBench_v1.0.6.zip`, 68,610 bytes, SHA-256:

`b50a4a3ded44e3a065728c035914a341fd740ddf4b6364ca6417720fde1efaf2`

The package contains a PowerShell runner, Python analyzer, settings, launchers,
documentation, 20 placement-stage CFG files and a tools placeholder. PresentMon is
assumed installed and operational in the user's existing `tools` directory, as
instructed. Its absence from the archive is not treated as a defect.

## Verified original behavior

`cb_runner.ps1:Invoke-Lap` starts PresentMon and emits per-lap metadata to
`Results/<run>/laps.csv`, pointing at `frames/*.csv`. Fields include configuration
label, mode, integer level, pass, timescale, intended/found counts, pre-spawn and
post-spawn counts, requested capture duration, status and notes. `run_info.txt`
records the package version, hardware snapshot, schedule and settings.

The bundled Python analyzer identifies itself as **v1.0.2**, even though the
capture package is **v1.0.6**. These are distinct version identifiers.

| Original function | Verified responsibility |
| --- | --- |
| `load_frametimes(path)` | reads one of `MsBetweenPresents`, `msBetweenPresents`, `FrameTime`; accepts positive values below 120000 ms; keeps the swap chain with the most valid presents |
| `percentile` | linear-interpolated empirical percentile |
| `lap_metrics` | frames/time average FPS, reciprocal p99/p99.9 low-FPS values, native frame-time percentiles, maximum, population SD, CV |
| `timeline` | one-second capture-time FPS bins |
| `summarize`, `t95` | equal-lap mean, sample SD, historical approximate Student-t CI across usable laps |
| `gap` | percentage difference between configuration means at the same load, with historical approximate CI |
| `svg_chart`, `svg_timeline` | static SVG graphs |
| `main` | scans run manifests, handles flags/short captures, groups by mode/label/level, writes the four outputs and generates the report |

The four verified outputs are exactly `lap_metrics.csv`, `summary.csv`,
`comparison.csv`, and `report.html`. Raw individual-lap metrics and native
FPS/frame-time measures are present. Legacy usable groups accept only status `ok`
with loaded metrics. A too-short capture is excluded; few-frame warnings alone do
not exclude the original tail statistics. `TEST` labels are excluded unless enabled.

Original baseline selection is only the cross-configuration label `--baseline`
(default `JEDEC`). There is no within-configuration starting-load reference,
retention curve, degradation curve, local slope layer, versioned formula schema
or covariance-aware uncertainty for those quantities.

The original report limits plotted labels to the first three, uses evenly spaced
categorical x positions for its load plots, and connects available points across
missing levels. Those historical plots remain available. New plots include all
configurations, use numeric coordinates and break at missing endpoints. The new
layer does not silently reinterpret the old charts as corrected statistics.

The original Student-t lookup/ratio CI approximations are retained for compatibility;
the new section uses a separately specified cluster-bootstrap method. The historical
paragraph calling gaps between percentile lines a "variance" remains in the old
section, while the new section correctly distinguishes dispersion, repeatability
and uncertainty. Percentile spacing is not literally a variance estimator.

## Exact implementation changes

| Module/function | Change |
| --- | --- |
| `cb_analyze.py:main` | adds optional reference/output/uncertainty/import flags; retains original source status/notes internally; calls new adapter; snapshots prior analytical outputs before writing; appends the new report section and writes a standalone report |
| `cb_analyze.py:load_frametimes` | optional diagnostics argument counts accepted/rejected/other-chain rows; preserves original frame-selection behavior and return signature |
| `cb_analyze.py:svg_chart`, `svg_timeline` | guard a zero-width log axis for a flat power-of-ten curve; otherwise a flat 100 FPS test divided by zero |
| `cb_formulas.py` | pure retention, degradation, secant-slope, per-metric workload integration and repeated-unit joint bootstrap functions; no benchmark dependencies |
| `cb_stability.py:build_metrics` | ChickenBench metadata/validity adapter, per-metric lap eligibility, reference selection and portable observations |
| `cb_stability.py:write_outputs` | per-load CSV, workload-wide `stability_summary.csv`, lap audit CSV and reproducibility metadata |
| `cb_stability_report.py:render_stability`, `write_standalone` | self-contained HTML/SVG, visible per-metric score cards, metric controls, all configurations, native numeric x positions, uncertainty/validity display and embedded CSV download |

`lap_metrics`, `percentile`, `timeline`, `summarize`, `t95`, `gap` and original CSV
headers/values are unchanged. For release 1.0.7, the runner, settings, launchers and
command reference receive version-label changes only. Their behavior/settings values
and all 20 stage CFG files are unchanged. There is no MemLat Pro dependency.

New report generation is separate from the formulas. The one small historical
renderer fix is necessary for the required flat-curve case and changes no capture
or native numerical result.

## Output preservation

The three original CSV schemas remain exact. Before an analysis replaces any known
analytical output in its destination, existing files are copied byte-for-byte to
`analysis_backups/<timestamp>/`. A separate `--output-dir` can keep every prior
output in the input Results directory untouched. Existing report measurements,
tables, graphs and timelines remain in `report.html`; the new section is appended.

The original source archive remains a separate unmodified input. This delivery is
a separate updated package; copy only its analyzer/new files into an existing
installation to retain the user's installed PresentMon executable and settings.

## Verification boundaries

`VALIDATION.md` records automated checks and sample-output replay. The Testrun5
frame files were available, but their original lap manifests and run metadata were
not found. Their supplied example report is explicitly an **unverified offline
replay**: load/pass coordinates come from filenames, counts and requested capture
windows are unknown, and only one pass is present. It is excluded from legacy
usable summaries and has no inferred repeatability CI.

No actual CS2, PowerShell benchmark execution or PresentMon capture session was
run in this environment. Validation is of analysis, serialization, preservation and
report generation, not the live capture path.
