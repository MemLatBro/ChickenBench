# Capture behavior and limitations

Launch `CB_Run.bat` from the repository root. It runs `runner/cb_runner.ps1`,
which locates the repository through its own path, reads `config/cb_settings.ini`,
and writes captures under the root `Results/` folder.

The runner loads the installed Workshop benchmark, executes local console commands,
and collects frames through a separately installed PresentMon console executable.
It writes `cb_init.cfg`, `cb_cmd.cfg`, and chicken stage files into CS2's
`game/csgo/cfg` directory. It uses simulated keyboard input and log-file feedback;
this source does not use game-process injection or game-memory reads/writes.

## Existing side effects

- The chosen command key is rebound to `exec cb_cmd`.
- `fps_max` is set to zero; `sv_cheats`, `host_timescale`, and local round state
  are changed for the workload.
- The prior key binding and prior setting values are not saved/restored.
- Generated `cb_*.cfg` files remain installed; same-named files may be overwritten.
- An existing `console.log` is moved to `console.log.prev` where possible. If that
  move fails, the runner attempts to remove the log before starting a new capture.
- If `QuitWhenDone=1`, the runner asks CS2 to quit after the sweep.

The 1.0.8 release changes file locations and the analysis launcher. It does not
change lap timing, load generation, the placement lists, or these capture side
effects. Run the benchmark as a dedicated local test session and use an unused
command key. When the run finishes, close the benchmark and restore any preferred
settings/bindings before normal play.

## Workload and timing

Chicken mode adds stage files containing 50 positioned chickens each. Chickens
accumulate within a pass. Endpoint counts are checked, but do not prove their
number throughout the full capture. The default schedule remains 0 through 500
in steps of 50. Twenty stage files support up to 1,000 placed chickens.

Timescale mode changes simulation speed and divides the scheduled capture window
by that factor. It does not establish an equivalent chicken count or a measured
quantity of completed simulation work. High multipliers shorten capture duration.

The runner needs CS2 focused for its key commands and can attempt to bring the
window forward. Its checks identify a CS2 window and log events; they are not a
comprehensive verification of map identity or server security state.

## Permission and validation boundary

Valve's applicable Steam/game terms and the Workshop author's rights remain in
effect. The repository's MIT license applies to its own covered contributions;
it is not authorization from Valve or the addon creator. No account or anti-cheat
compatibility guarantee is made. See [dependency scope](../THIRD_PARTY_NOTICES.md).

Automated development tests run offline. Live Windows/CS2/PresentMon capture
behavior requires separate testing on an appropriately configured installation.
The historical command observations are retained in `CS2_COMMANDS.txt`.
