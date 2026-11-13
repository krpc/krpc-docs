# Index of mod integrations

This issue indexes the mod support that is planned or worth considering. Each option gets its own issue when work starts. Download counts are lifetime CKAN totals from 2026-11-07, for rough comparison only. They include installs pulled in as dependencies, and some look too low: MechJeb2 shows about 36k.

## Existing Issues and Pull Requests

| Mod | Downloads | Tracked in | Notes |
| --- | --- | --- | --- |
| MechJeb2 | 36k | #288, #311 | Port the third-party [kRPC.MechJeb](https://genhis.github.io/KRPC.MechJeb) service into kRPC: [design/services/mechjeb.md](../design/services/mechjeb.md). |
| Kerbal Engineer Redux | 1.92M | #288 | `Vessel.DeltaV` and `Stage` already cover delta-v. Find which stats are missing: [design/services/kerbal-engineer-redux.md](../design/services/kerbal-engineer-redux.md). |
| Trajectories | 1.11M | PR #1253 | Merged. |
| Principia | not on CKAN | #767 | Phase 1 shipped as a docs page. Phases 2 and 3 wait on upstream. |
| Raster Prop Monitor | 2.05M | #375, #424, [design](../design/services/raster-prop-monitor.md) | The count likely includes installs as a dependency of IVA packs. Four phases: persistent variables, monitors, script pages, cameras. |
| IndividualRCS | - | PR #1245 | Merged. |
| [Near Future Solar](https://github.com/post-kerbin-mining-corporation/NearFutureSolar) | 1.50M | - | `SolarPanel` wraps the curved panels' `ModuleCurvedSolarPanel`, with in-game tests. Implemented and passing in game, awaiting a PR. |
| [B9PartSwitch](https://github.com/blowfishpro/B9PartSwitch) | 2.02M | - | Setting a `PartField` did not switch the subtype: B9PartSwitch acts only on the UI control's `onFieldChanged`, which `PartField` now calls as the right-click menu does. In-game tests switch the subtype in the editor and check resources and mass there and in flight. Implemented and passing in game, awaiting a PR. |
| [TweakScale](https://github.com/TweakScale/TweakScale), [TweakScale Rescaled](https://github.com/JonnyOThan/TweakScale) | 1.52M, 1.07M | - | Mass, thrust, torque and resources read correctly on scaled parts. `Part.Cost` ignored module costs, and now adds them as the game's ship cost does. TweakScale's own cost does not follow the scale, and adds nothing in flight. In-game tests for both. Implemented and passing in game, awaiting a PR. |
| RemoteTech, Kerbal Alarm Clock | 689k, 1.33M | [remotetech-kac-api](remotetech-kac-api.md) | Complete the existing services. |
| Infernal Robotics | - | [infernal-robotics-input-linking](infernal-robotics-input-linking.md) | Input linking and sun tracking. |
| Procedural Fairings, DockingCamera, LIDAR | 1.19M (Procedural Fairings) | [mod-compat-tests](mod-compat-tests.md) | Existing integrations with no in-game tests. |

[requires-mod-attribute](requires-mod-attribute.md) makes the server check that a service's mod is available before each RPC, which applies to any new service.

## New Services

| Mod | Downloads | Adds |
| --- | --- | --- |
| [SCANsat](https://github.com/KSPModStewards/SCANsat) | 1.43M | Scan coverage, terrain and biome data for choosing landing sites. |
| [Kerbalism](https://github.com/Kerbalism/Kerbalism) | 684k | Radiation, crew health and background resource state, through its `API` class. |

Kerbalism also needs a compatibility fix. It replaces `ModuleScienceExperiment` with its `Experiment` module, and `ModuleScienceContainer` with its `HardDrive` module. The `Experiment` class in SpaceCenter only wraps the stock experiment module.

## Compatibility Fixes and Checks

| Mod | Downloads | Work |
| --- | --- | --- |
| Real Solar System, Kopernicus, Realism Overhaul, RP-1 | 1.32M, 1.41M, 985k, 581k | Check reference frames, orbits and the auto-pilot at real scale and on changed bodies. Only RealFuels is integrated so far. |
| Contract Configurator | 1.50M | Check its contracts and parameters through the contracts API. |

## Considered and Not Planned

| Mod | Reason |
| --- | --- |
| BDArmory | Niche, and a large API to cover. Revisit on request. |
| TAC Life Support, USI Life Support | Their supplies should already be readable as resources. |
| Transfer Window Planner | Scripts can calculate transfer windows themselves. |
| KAS | No clear scripting use. |

## Suggested Order

1. Near Future Solar, as a small fix for a known gap. Implemented, awaiting a PR.
2. Smoke tests on Real Solar System and Kopernicus, then B9PartSwitch and TweakScale. A bug here returns wrong values with no error. B9PartSwitch and TweakScale are implemented, awaiting a PR.
3. A SCANsat service, as the first new integration.
4. Kerbalism, scoped separately because it spans a service and compatibility work.
