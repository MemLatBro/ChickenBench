# ChickenBench 1.0.7 / analyzer 1.2.0 / formulas 1.1.0

* Added separate native workload averages and retention-area scores for every metric,
  with visible FPS/1% low/0.1% low cards, `stability_summary.csv`, full-range coverage
  checks, endpoint loss rates and joint sweep/run bootstrap intervals.
* Added a pure, portable formula layer for independent retention, degradation and
  actual-coordinate local degradation rates. Improvements remain unclipped.
* Uses each configuration's first recorded workload as its default reference;
  averages eligible repeated laps at that level. Explicit references are optional.
* Added `stability_metrics.csv`, `stability_laps.csv`, `stability_metadata.json`
  and `stability_report.html`; appended new plots to the original `report.html`.
* Added within-lap SD/CV and descriptive between-lap variation with distinct roles.
  No arbitrary composite stability score or workload utility weights were introduced.
* Added deterministic whole-sweep/run bootstrap intervals, with shared-reference
  dependence, small-sample flags and missing-support handling.
* Added per-metric sample thresholds, count/duration/metadata diagnostics, missing
  level preservation, duplicate rejection and source hashes.
* Preserved all original CSV schemas/calculations. Prior reports/CSVs are backed up
  before replacement; `--output-dir` permits a separate analytical destination.
* Retained original report graphs/tables. New SVGs use actual numeric coordinates,
  include every configuration and stop at missing levels.
* Fixed a zero-range logarithmic report axis for flat power-of-ten curves.
* Capture behavior, settings values, launch commands, stage files and PresentMon behavior unchanged. Package/runner version labels are 1.0.7.

See `FORMULAS.md`, `AUDIT.md`, `STABILITY_README.md` and `VALIDATION.md`.
