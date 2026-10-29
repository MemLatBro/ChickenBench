# Contributing

Use Python 3.13 or newer and run `python scripts/run_tests.py` from the repository
root before proposing analysis or launcher changes. No pip dependencies are
required. Tests never launch CS2 or PresentMon.

Keep native frame measurements, retention, workload rates, and repeatability
distinct. Document any calculation changes in `docs/FORMULAS.md`; update version
identifiers when formulas or capture behavior change. Preserve the legacy CSV
fixtures unless a deliberate compatibility change is explained.

When reporting a capture issue, include the ChickenBench, CS2, and PresentMon
versions, the sweep mode, relevant settings, and a short log excerpt. Review logs
and hardware/path information before posting them publicly. Do not commit local
`Results/`, installed executables, or third-party game/addon files.

Contributions should be your original work or material you are authorized to
contribute under this project's MIT license. Identify any third-party material
and preserve its actual license and notices.
