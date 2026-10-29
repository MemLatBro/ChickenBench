# Changelog

## 1.0.8 — 2026-10-28

- Move the baseline prompt out of `cmd.exe` and into a Python launcher. Labels
  accept only letters, digits, underscores, and hyphens; blank input uses JEDEC.
- Invoke the analyzer with a separate argument list and `shell=False`, preserving
  path boundaries and preventing label text from becoming shell commands.
- Return analyzer failures and avoid opening stale HTML after a failed analysis.
- Group capture code in `runner/`, Python modules in `analysis/`, and settings
  and placement lists in `config/`. Update launchers and runner resource paths.
- Add MIT licensing for covered original contributions, third-party notices,
  a GitHub README, publishing instructions, ignore/line-ending rules, source ZIP
  builder, and an offline test workflow.
- Add launcher and release-layout regression tests. The analyzer remains 1.2.0
  and the formulas remain 1.1.0. Capture timings and all 20 placement stages
  retain their previous behavior. Settings/binding restoration is not added.

Historical release notes and previous validation records are retained under
`docs/legacy/`, `docs/STABILITY_CHANGELOG.md`, and `docs/validation/`.
