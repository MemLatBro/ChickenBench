HISTORICAL DOCUMENT: this describes the older flat 1.0.7 package.
For the current grouped layout, see ../../README.md.

ChickenBench v1.0.7
===================

Loops Angel's "CS2 FPS BENCHMARK DUST2" (Workshop 3240880604) and measures how
performance falls as load rises, so tuned and JEDEC memory can be compared.

Two sweeps:
  [1] Chickens   0 / 50 / 100 ... 500 chickens spread along the camera route
  [2] Timescale  1x / 2x / 4x / 8x / 12x  (host_timescale)
  [3] Quick test one 0-chicken lap, to check that everything works

NEW IN 1.0.7
  Retention, degradation, local degradation rate and variability exports.
  Original CSV outputs and report sections are preserved. See START_HERE.md
  and STABILITY_README.md for the new reports, formulas and usage.

ONE-TIME SETUP
  1. PresentMon: download the console version from
       https://github.com/GameTechDev/PresentMon/releases
     (the file named like PresentMon-2.x.x-x64.exe, NOT the "Capture Application" installer)
     and put it in this folder's "tools" subfolder.
  2. The chicken stage files (cs2_cfg\cb_s01.cfg ... cb_s20.cfg, 50 chickens each) are
     copied into CS2's cfg folder automatically at the start of a chicken sweep.
  3. Check the two paths at the top of cb_settings.ini.
  4. Python 3 is needed only for the report (CB_Analyze.bat).

RUNNING
  - Start Steam normally (not as administrator). Close CS2.
  - Double-click CB_Run.bat. Accept the administrator prompt (PresentMon needs it).
  - Pick a sweep, type the config label (TUNED, JEDEC, ...), press Enter for 3 passes.
  - Do not touch the PC while it runs. CS2 starts, loads the map and loops by itself.
    How it controls CS2:
    * Main menu: key binds do not work there, so it types ONE line into the console:
        hideconsole; exec cb_init; map_workshop 3240880604 de_dust2
    * In-game: it writes commands to cfg\cb_cmd.cfg and presses Page Down (bound to
      "exec cb_cmd"). Each batch ends with "exec cb_ack_N" (a file that does not
      exist on purpose); the resulting "couldn't exec ... cb_ack_N" line in
      console.log confirms the batch ran.
    It only sends keys while CS2 is the active window (otherwise it beeps and waits).
  - If typing the map command fails, it asks you to load the map by hand and continues.
    If the Page Down link fails, it asks you to type the bind once.
  - Close the CS2 console with the ~ key, never Escape: Escape opens the pause menu,
    which blocks key binds.
  - Do the same for each RAM config with the same Adrenalin profile and CS2 settings.
  - Then double-click CB_Analyze.bat -> Results\report.html opens.

WHAT EACH LAP DOES
  mp_restartgame 1
  -> chicken sweep only, during Angel's ~7 s countdown: count the chickens that survived
     the restart, spawn THIS lap's 50 new ones, keep counting until they all exist
     (must be confirmed by SpawnConfirmBy = 7 s; the capture starts at 9 s)
  -> PresentMon records the flythrough from 9 s to 113 s (game time)
  -> after PresentMon has finished: count the chickens again -> next lap.
  mp_restartgame does NOT remove chickens, so they accumulate within a pass (0, 50,
  100 ... 500). They are cleared once, at the start of each pass. Nothing is spawned
  at the end of a lap (in v1.0.4/1.0.5 that lost about half of every new batch).
  Passes always run low -> high in the chicken sweep.
  In timescale mode every time is divided by the timescale (12x = ~9 s laps).

RESULTS
  Results\<date>_<label>_<mode>\
     laps.csv        one row per lap (status, chickens found, ...)
     frames\*.csv    PresentMon frame data per lap
     run_info.txt    CPU / GPU / RAM speed / settings snapshot
     logs\           runner log + PresentMon output
  Results\report.html, summary.csv, comparison.csv, lap_metrics.csv  (from CB_Analyze.bat)

  Lap status: ok | no_frames | no_ack | disconnected | spawn_unconfirmed | chickens_lost |
  chickens_extra
  (count more than ChickenTolerancePct, default 10%, off the level).
  Only "ok" laps go into the averages; the rest are listed at the bottom of the report.

KNOWN LIMITS (v1.0.7)
  - GPU clocks are not logged on AMD. Keep the same Adrenalin profile for every run.
  - High timescales give short laps (8x ~13 s, 12x ~9 s); the report flags levels with
    too few frames for a trustworthy 0.1% low. Use more passes there.
  - Relies on CS2's -condebug (console.log) and on a key bind. CS2 ignores
    -netconport (tested 2026-10-25), so the network console is not used.
  - CS2 must stay the active window. If it loses focus the runner beeps and waits.
  - [Console]-channel lines (echo output, the round-start line) do not reach console.log
    after Angel's map has run, so the runner confirms via [InputService] lines and
    times each lap from its own key press if the round-start line is missing.
  - Angel's script can no longer set fps_max etc. (CS2 blocks it); the runner sets
    fps_max 0 itself every lap.
  - Chicken sweep: accumulated chickens are of different ages (older ones may have
    wandered or died). This is deliberate for now; compare pass-to-pass spread later.
  - About 3000 chickens crashed CS2 on the test PC.
