# License scope and external dependencies

The [MIT license](LICENSE) covers the original ChickenBench code and associated
documentation made available in this repository, to the extent its contributors
hold rights to grant that license. It also covers original example-generation
code and report templates. The notice does not claim exclusive rights in facts,
benchmark measurements, command names, or other material that is not copyrightable.

It does not license, transfer, or claim ownership of Valve's or other parties'
games, engines, maps, artwork, trademarks, Workshop contributions, or software.
Third-party material remains subject to its own terms, even if referenced by
ChickenBench. The MIT license does not grant permission to automate a third-party
product or override that product's terms.

## Installed separately

| Dependency | Purpose and source | Distribution |
| --- | --- | --- |
| Steam and Counter-Strike 2, including Dust2 | Game and local simulation workload, provided by Valve through Steam | Not included. Users install and use them under Valve's applicable terms. |
| CS2 FPS BENCHMARK DUST2 by Angel / ANGELFPS and the Workshop page's listed contributors | Benchmark scenario, [Workshop item 3240880604](https://steamcommunity.com/sharedfiles/filedetails/?id=3240880604) | Not included. Users obtain the original through Steam Workshop. No license to copy or modify that addon is granted here. |
| PresentMon | Frame capture, [official project](https://github.com/GameTechDev/PresentMon) and [releases](https://github.com/GameTechDev/PresentMon/releases) | Not included. Download the console executable separately and follow the selected release's terms and notices. |
| Python | Offline analysis runtime, [python.org](https://www.python.org/) | Not included. Analysis uses the Python standard library. |

ChickenBench supplies separate console-command placement lists under
`config/cs2_cfg/`. They target locations along the external benchmark scenario;
they are not a distribution of its packaged map or script. They do not grant
rights over the underlying map, scenario, or any third-party contributions.

ChickenBench is an independent community project. It is not an official Valve,
Steam, Counter-Strike, ANGELFPS, or PresentMon product. Their names identify
dependencies; no endorsement is claimed. The applicable game and service terms,
including any automation restrictions, continue to apply. There is no claim that
Valve has approved the runner or guaranteed its account/anti-cheat compatibility.

If third-party code or binaries are added in a future release, record their
actual license and required notices before distributing them. Do not apply this
repository's MIT notice to someone else's material.
