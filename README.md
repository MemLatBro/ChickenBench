# ChickenBench

Measure how CS2 frame performance changes as a repeatable local workload increases.
ChickenBench runs Angel's Dust2 benchmark at different chicken counts or simulation
timescales, records frames with PresentMon, and produces local CSV and HTML reports.

**Release:** 1.0.8 · **Analyzer:** 1.2.0 · **Formulas:** 1.1.0

The analysis reports absolute performance, retention, degradation rates, and
between-lap variation separately. A configuration that retains more of its starting
performance is not necessarily faster in absolute terms.

## Requirements

- Capture: Windows, Windows PowerShell 5.1, Steam, and Counter-Strike 2.
- Subscribe to [CS2 FPS BENCHMARK DUST2](https://steamcommunity.com/sharedfiles/filedetails/?id=3240880604).
- Download a compatible [PresentMon console executable](https://github.com/GameTechDev/PresentMon/releases)
  and put it in `tools/`. The configured command-line flags target the 2.x console
  interface; adjust `PresentMonArgs` if your selected release differs.
- Analysis: Python 3.9 or newer. No pip packages are needed. The analysis can run
  independently on Windows, Linux, or macOS using existing captures.

## Quick start

1. Download and extract the complete repository or release ZIP into a writable folder.
2. Install the dependencies above and let Steam finish downloading the Workshop item.
3. Edit the game/Steam paths in [`config/cb_settings.ini`](config/cb_settings.ini).
4. Start Steam normally and close CS2. Double-click **`CB_Run.bat`**.
5. Select a sweep and label the hardware configuration, for example `JEDEC` or `TUNED`.
6. After capturing the configurations, double-click **`CB_Analyze.bat`**. Enter the
   baseline label, or press Enter for `JEDEC`.
7. Open `Results/report.html` or `Results/stability_report.html`.

Labels in the analysis launcher accept letters, digits, underscores, and hyphens.
The prompt is handled in Python; its text is never inserted into a shell command.
If analysis fails, the launcher does not open a previous report as if it were new.

The capture runner requests administrator rights for PresentMon, writes command
files into CS2's `game/csgo/cfg` directory, binds the configured command key, and
sends simulated keystrokes while CS2 is focused. It changes `fps_max`,
`host_timescale`, and local-server settings. This release does not restore their
previous values or the prior key binding. Pick an unused key and review
[capture behavior and limits](docs/CAPTURE.md) before running it.

## Repository layout

| Location | Contents |
| --- | --- |
| `CB_Run.bat`, `CB_Analyze.bat` | Windows launch buttons |
| `runner/` | PowerShell capture and sweep controller |
| `analysis/` | Python calculations, CSV exports, HTML/SVG reports |
| `config/` | Settings and 20 chicken-placement stage files |
| `tools/` | Instructions for separately installed PresentMon |
| `scripts/` | Analysis launcher, offline test runner, ZIP builder |
| `tests/` | Formula, adapter, report, pipeline, and launcher tests |
| `examples/` | Synthetic examples and explicitly unverified capture replay |
| `docs/` | Methodology, capture behavior, release notes, historical audit records |
| `.github/workflows/` | Offline tests and PowerShell syntax checks |
| `Results/` | Created by capture; excluded from Git |

When moving from the old flat 1.0.7 layout, extract into a new folder. Copy your
existing `Results/` and installed PresentMon into the corresponding locations;
merge your settings into `config/cb_settings.ini`. Do not copy the old batch files
or runner over this layout.

## Offline analysis and development

From the repository root:

```sh
python analysis/cb_analyze.py Results --baseline JEDEC
python scripts/run_tests.py
```

To try the analyzer without starting Steam or CS2:

```sh
python examples/generate_demo.py DemoResults
python analysis/cb_analyze.py DemoResults --baseline Demo-A --output-dir DemoAnalysis
```

See [analysis usage](docs/STABILITY_README.md), [formula definitions](docs/FORMULAS.md),
and the [example reports](examples/README.md). Synthetic data makes no hardware
claim. The Testrun5 replay lacks its original capture manifests and is labeled
unverified; it cannot establish repeatability from a single pass.

## Publishing and contributing

See [GitHub setup and release instructions](docs/GITHUB.md) and
[contributing](CONTRIBUTING.md). To build a clean source ZIP:

```sh
python scripts/build_release.py
```

The builder excludes local captures, installed binaries, Git internals, caches,
and previous archives. Tests exercise only offline analysis and launch handling;
they do not demonstrate live CS2 compatibility or permission under Steam's terms.

## License and dependency scope

Original ChickenBench code and documentation are available under the [MIT license](LICENSE):
free use, modification, redistribution, and commercial use are permitted, with
the copyright and permission notice retained. See [third-party notices](THIRD_PARTY_NOTICES.md).

CS2, Steam, Dust2, the Workshop addon, and PresentMon are installed separately.
Their ownership and terms remain with their respective rights holders. This
project claims no endorsement or approval from those parties. Valve's published
automation terms are broad; this release makes no guarantee about account or
anti-cheat compatibility of the external controller.
