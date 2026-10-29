> Historical 1.0.7 analysis validation record. The grouped 1.0.8 release adds launcher and layout checks; see [release validation](RELEASE_VALIDATION.md).

# Validation record

Analysis verification completed 2026-10-28. Python standard-library tests only; no
third-party runtime dependency was added to ChickenBench.

* **80 automated tests passed.** Run `python scripts/run_tests.py` from
  the ChickenBench directory. The complete result log is in `docs/validation_tests.txt`.
* Formula tests cover flat, linear, nonlinear and improving curves, actual irregular
  intervals, baseline changes, absent references, invalid values, duplicate coordinates,
  single/noisy repeated laps, exact reference identities, shared-baseline covariance,
  matched/missing support, and whole-run versus within-run uncertainty.
* Adapter/report tests cover first workload per configuration, repeated-reference
  aggregation, failed reference retention, short captures, known count/timescale
  contradictions, provisional missing metadata, reference/previous-endpoint validity
  propagation, metric-specific tail support, zero dispersion, source versions, missing
  scheduled levels, numeric x spacing, gaps, escaping and nearly flat-axis roundoff.
* End-to-end tests compare all three original CSVs to golden bytes produced by the
  original analyzer; preserve input hashes; verify unchanged original graph sections;
  inspect exports; reject invalid CLI references before mutation; and prove backups
  retain prior CSV/report bytes exactly.
* A separate 66-lap synthetic dataset (two labels, three passes, six chicken levels and
  five timescale levels) ran through both the original v1.0.2 analyzer and the updated
  v1.1.0 analyzer. `lap_metrics.csv`, `summary.csv` and `comparison.csv` were each
  **byte-for-byte identical**. Original and extended reports are both bundled in the
  synthetic example folder.
* Eleven actual Testrun5 frame CSVs were processed offline. Original lap manifests,
  workload-count evidence and requested capture windows were unavailable. The example
  is explicitly provisional/unverified, uses filename-derived coordinates and a single
  pass, and has no inferred repeatability intervals. Its capture version is unknown.
  Imported laps are deliberately excluded from historical usable summaries.
* Seven representative embedded SVG plots were rendered and visually inspected,
  including native means, retention, degradation, local rates, between-lap variation
  and within-lap SD/CV. An axis artifact that magnified tiny roundoff on a flat CV
  curve was corrected and regression-tested. No image is required to run the report.
* Embedded CSV downloads matched the separately exported files byte-for-byte for both
  sample reports. All 30 metric selections across the reports were exercised by
  executing the report's actual JavaScript in an isolated Node VM with DOM stubs.
  Reports contain no external script/stylesheet dependency.
* A full Chromium HTML layout/interaction test was unavailable: this environment
  lacked a browser executable and the browser download failed. SVG rendering and
  JavaScript/structure checks do not constitute full desktop/mobile browser validation.
* For the 1.0.7 distribution, the runner, settings, launchers and command reference
  receive version-label changes only. Settings values and capture behavior are unchanged;
  all 20 stage files remain byte-identical to the original archive. CS2, PowerShell
  execution and live PresentMon capture were **not** run.

Machine-readable hashes and preservation results are in `docs/validation_summary.json`.
The statistical coverage of bootstrap intervals, especially from three sweeps, has
not been empirically validated; the report labels these small-sample intervals exploratory.

## Release 1.0.7 aggregate update

Distribution/runner 1.0.7 now includes analyzer 1.2.0 and formulas 1.1.0.
Nineteen new tests cover flat/linear/nonlinear curves, irregular spacing, insertion
of collinear samples, unclipped improvements, missing levels/references, one-point
runs, reciprocal normalization, zero dispersion, joint-reference bootstrap behavior,
unmatched supports, run-level clustering and export/presentation consistency.

All three legacy CSVs from the 66-lap synthetic example and eleven-capture Testrun5
replay are byte-identical to the preceding release. Per-load native values, retention,
degradation, rates and their existing interval bounds are also exactly preserved.
Fifty metric/configuration/mode aggregate rows were independently recomputed from
the exported per-load CSVs using trapezoids. Both embedded CSV downloads match
separate exports byte-for-byte. All 30 existing metric-control selections still work
in the Node DOM-stub checks; the three new visible FPS cards are present before curves.

Bundled examples are regenerated with current analyzer/formula identities. The
Testrun5 capture version remains unknown and the scores remain provisional. A single
sweep supplies no inferred aggregate repeatability interval. Original captured frame
files were not changed. The prior distribution is retained separately for comparison.

Full browser layout/interaction validation remains unavailable (no browser binary).
The HTML summary uses a three-column desktop card grid and one column below 760px;
checks verify markup, values, embedded exports and existing control behavior.
