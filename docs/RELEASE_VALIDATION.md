# Release validation — 1.0.8

Prepared on 2026-10-28 from the supplied ChickenBench 1.0.7 package.

## Verified locally

- **92 offline Python tests passed** with `python scripts/run_tests.py`.
- The 80 existing analysis tests still pass after the move into `analysis/`.
  These include exact golden CSV comparisons, input preservation, report output,
  and analytical-output backups.
- New launcher tests reject embedded spaces, quotes, shell operators, expansion
  characters, and newlines in baseline labels. Blank input uses JEDEC. Valid
  labels and paths are passed as separate process arguments with `shell=False`.
- A failed analyzer does not open an existing report. Missing output after a
  successful return is reported as an error.
- New package tests verify grouped runtime paths, included workflow/source,
  and exclusion of runtime binaries, captures, Git internals, and caches.
- All four analysis modules are byte-identical to the supplied versions. The
  twenty stage files retain the same text and coordinates; Windows source
  line endings are normalized for the release.
- The new README and release/dependency-document relative links resolve.
- The source ZIP was extracted into a temporary path containing spaces. The
  actual Python launcher rejected an invalid prompt before starting analysis;
  a synthetic dataset then passed through that launcher and produced the real
  CSV and HTML outputs successfully from outside the repository directory.
- Python source parses, Windows launcher/config line endings were checked,
  and the ZIP passed its integrity check with no bundled runtime binaries.

## Boundaries

Native Windows batch execution, the PowerShell elevation/keyboard path, CS2,
and PresentMon capture were not executed in this Linux preparation environment.
The supplied GitHub Actions workflow configures tests on Windows/Linux and a
PowerShell syntax parse on Windows; those hosted jobs have not run merely because
the workflow is included. Neither offline test results nor the MIT license
establish approval under Steam/game/addon terms or anti-cheat compatibility.

Historical 1.0.7 validation and example reports are retained as historical
records. They are not a claim that a new live capture was made for 1.0.8.
