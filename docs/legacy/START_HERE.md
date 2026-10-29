HISTORICAL DOCUMENT: this describes the older flat 1.0.7 package.
For the current grouped layout, see ../../README.md.

# ChickenBench 1.0.7

Run `CB_Run.bat` to capture and `CB_Analyze.bat` to analyze your Results folder.
Follow `README.txt` for PresentMon installation and path setup. When upgrading,
retain your existing settings, installed PresentMon executable and Results.

The analyzer now adds one workload-wide native aggregate and retention score for
each metric, alongside retention, degradation, local degradation rates and variability
to CSV and HTML exports. Each configuration's first recorded workload is its 100%
reference, with eligible repeated laps at that workload averaged. The measures are
reported separately. The original CSV schemas/calculations and original HTML
sections remain, and prior analysis outputs are backed up before regeneration.

## Files to open

- [Usage and new output files](STABILITY_README.md)
- [Testrun5 HTML report](examples/testrun5_replay/stability_report.html)
- [Testrun5 aggregate scores CSV](examples/testrun5_replay/stability_summary.csv)
- [Testrun5 stability CSV](examples/testrun5_replay/stability_metrics.csv)
- [Synthetic example report](examples/synthetic_report/stability_report.html)
- [Formula specification](FORMULAS.md)
- [Validation record](VALIDATION.md)

The Testrun5 report is an unverified offline replay of eleven original captures.
Its original manifests/counts/capture windows were unavailable. Coordinates come
from filenames; one pass supplies no inferred repeatability interval. These
examples are regenerated with analyzer 1.2.0 using the original unmodified captures;
native per-load measurements and the three historical CSV calculations are preserved.

Distribution/runner: **1.0.7**. Analyzer: **1.2.0**. Formulas: **1.1.0**.
The capture behavior and settings values from 1.0.6 are unchanged.
