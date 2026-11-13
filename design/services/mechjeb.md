# MechJeb2 service

**Status:** in progress. Phase 1, the port, done in PR #1326; phases 2 and 3 not scheduled. Issues [#288](https://github.com/krpc/krpc/issues/288) (MechJeb2 and Kerbal
Engineer Redux services; KER is in [kerbal-engineer-redux.md](kerbal-engineer-redux.md)) and
[#311](https://github.com/krpc/krpc/issues/311) (stage stats), from the
[mod integrations index](../../issues/mod-integrations-index.md).

## Goals

* A MechJeb2 service in `krpc`, ported from Genhis' third-party
  [KRPC.MechJeb](https://github.com/Genhis/KRPC.MechJeb) and improved.
* Stage stats from MechJeb's fuel-flow simulation, the open ask in #311.

## Context

| | |
| --- | --- |
| KRPC.MechJeb | 0.7.1, 2024-12-23, for KSP 1.12, kRPC 0.5.4 and MechJeb 2.14.3.0. GPL-3.0, as kRPC's mod services are |
| Covers | Ascent autopilot (classic, gravity turn, PVG), landing, docking, rendezvous and airplane autopilots, node executor, maneuver planner, SmartASS, SmartRCS, staging, thrust, RCS and deployable controllers, Translatron, target |
| Its to-do list | Advanced transfer maneuver, attitude adjustment, rover autopilot, spaceplane autoland |
| Fuel-flow simulation | `MechJebLib/FuelFlowSimulation`. Splits a KSP stage where its engines burn out at different times, and handles Realism Overhaul residuals and HTP, which the stock delta-v simulation behind `Stage` does not |

In #311, lamont-granquist (MechJeb) suggested a kRPC binding to the fuel-flow simulation, once it can
be shared with other mods outside MechJeb.

## Plan

1. **Port** KRPC.MechJeb into `service/MechJeb`, built, documented and tested as the other mod
   services, and listed under GPLv3 in `LICENSE`.
2. **Overhaul** it: the API layout, the members from #29, the to-do list and the inherited
   defects, in [mechjeb-overhaul.md](../../issues/mechjeb-overhaul.md).
3. **Stage stats** from the fuel-flow simulation (#311), once MechJeb can share it.

## Phase 1: the port

KRPC.MechJeb 0.7.1 does not load on MechJeb 2.15: most members were renamed to PascalCase, and
ascent guidance was rebuilt. The port targets MechJeb 2.15.4.0, the latest release. The dev
release stream is out of scope.

| Decision | Detail |
| --- | --- |
| API | Kept as in 0.7.1: service `MechJeb`, the same classes, members and enumerations |
| Ascent | `AscentAutopilot`, `AscentClassic` and `AscentPVG` read `MechJebModuleAscentSettings`. `Enabled`, `Status` and timed launches use the selected path's autopilot, and disabling releases both paths' autopilots (from #29) |
| Behavior change | `AscentPathIndex` keeps 0 (classic) and 2 (PVG), and throws for any other value. 0.7.1 ignored an invalid value |
| Removed with MechJeb | `AscentGT` and `AscentPathGT` (the GT path), `NodeExecutor.Tolerance`, `ThrustController.SmoothThrottle` and `ThrottleSmoothingTime`, `OperationTransfer.PeriodOffset` (now a lag time in seconds, a different setting) |
| Kept, but rejected | `SmartRCSMode.ZeroVelocity`, `TranslatronMode.KeepRelative`: MechJeb has no such mode |
| Remapped | `OperationTransfer.InterceptOnly` is the inverse of `Capture`, `SimpleTransfer` is `Coplanar`. `OperationLan.NewLAN` and `OperationLongitude.NewSurfaceLongitude` share the target controller's `targetLongitude`. `AttitudeReference` maps by name, as MechJeb inserted CoT variants |
| Internals | `KRPC.Utils.Accessor` delegates bound by name at load. Each call resolves the active vessel's master MechJeb, so the 0.7.1 per-vessel initialization and its pop-ups are gone; a missing member is logged at load and throws when used |
| License and credit | `service/MechJeb/*` is GPLv3 in `LICENSE`, credited to Genhis there, in the assembly copyright and on the docs page |
| Tests | In-game tests round-trip every settable member, which checks each binding against 2.15.4.0. They drive the maneuver planner, node executor, Smart A.S.S. and timed launches, plus the circularize, periapsis and plane cases of #13 |
| Review | The branch imports the 0.7.1 sources unchanged, then ports them in one commit per area, then adds the build, the tests and the docs |

## External work on KRPC.MechJeb

Reviewed for phase 1, on 2026-11-10. Genhis said in #28 that he no longer plays KSP or
maintains the mod, though he would review a PR and release it. Neither open port is merged.

| Item | What it is | Phase 1 |
| --- | --- | --- |
| [#28](https://github.com/Genhis/KRPC.MechJeb/issues/28) | Issue: 0.7.1 is incompatible with MechJeb 2.15 | Fixed by the port |
| [#22](https://github.com/Genhis/KRPC.MechJeb/issues/22) | Issue: Genhis' plan for 1.0, an API laid out like MechJeb's windows rather than its modules, so Ascent Guidance holds the staging and thrust settings. Names match the game, and the API depends less on MechJeb's internals | Input to phase 2 |
| [#29](https://github.com/Genhis/KRPC.MechJeb/pull/29) | PR by darchambault (fork releases 0.8.0, 0.8.1): a 2.15 port that flattens `AscentAutopilot` and adds members | The fix to disabling the ascent autopilot. Its member mapping matches the port's |
| [#30](https://github.com/Genhis/KRPC.MechJeb/pull/30) | PR by eontech64: a smaller 2.15 port | Nothing. It drops the auto turn readouts, which 2.15 still has, keeps a stub `AscentGT`, and binds the throttle smoothing 2.15 removed |
| [#13](https://github.com/Genhis/KRPC.MechJeb/pull/13) | Genhis' unfinished in-game test suite for the 0.7 API | Its circularize, periapsis and plane cases, rewritten as krpctools tests. The other modules are stubs that fail |

## Phase 2: follow-up from #29

What to take from #29 into a later PR. Code taken from it credits darchambault in `LICENSE`,
next to Genhis. MechJeb names are fields of `MechJebModuleAscentSettings` unless given.

| Member | MechJeb | Verdict | Notes |
| --- | --- | --- | --- |
| `SmartASS.Roll` | `MechJebModuleSmartASS.rol` | Take | Degrees. Applies with `ForceRoll` in the orbital, target, kill rotation and node modes |
| `AscentAutopilot.DesiredLan`, `LaunchToLan(lan)` | `DesiredLan`, `LaunchingToLan` | Take | MechJeb offers the launch for PVG only; #29 does not check the path. Decide whether to match |
| `AscentAutopilot.LaunchToMatchLan()` | `LaunchingToMatchLan` | Take, fixed | #29 times it with the minimum time to the target's plane and sets the inclination, as `LaunchToTargetPlane` does. MechJeb's "Launch to target LAN" (PVG only) times it to `target.LAN - LaunchLANDifference` at `DesiredInclination`, which it keeps |
| `AscentLaunchMode.Lan`, `MatchLan` | | Take | Without them both launches report `Unknown`, which `AbortTimedLaunch` refuses |
| `AscentAutopilot.OverrideWarpToPlane` | `OverrideWarpToPlane` | Take | |
| `AscentAutopilot.RollAltitude` | `RollAltitude` | Take | Meters, the altitude above which the roll is controlled |
| `LimitQa`, `LimitQaEnabled` | `LimitQa`, `LimitQaEnabled` | Take | Pa.rad, the Q-alpha limit. MechJeb's ascent window sets `LimitQaEnabled` to whether the path is PVG each frame it draws, which overrides a set value |
| `LimitingAoA`, `CurrentMaxAoA` | `LimitingAoA`, the autopilot's `CurrentMaxAoA` | Take | Read-only. Degrees |
| PVG settings: `DesiredAttachAltFixed`, `DesiredFPA`, `CoastBeforeFlag`, `MinDeltaV`, `LastStage`, `OptimizeStage(Flag)`, `CoastStage(Flag)`, `SpinupStage(Flag)`, `SpinupAngularVelocity`, `SpinupLeadTime`, `UnguidedStages(Flag)` | Same names, the stages from their `...Internal` fields | Take | `DesiredFPA` and `SpinupAngularVelocity` hold radians and rad/s, while the window shows degrees and rpm; pick one and document it. #29 exposes `UnguidedStages` read-only. MechJeb also has `MaxCoast`, `MinCoast`, `PreStageTime` and `OptimizerPauseTime`, which #29 omits |
| `AscentAutopilot.TimedLaunch` | the autopilot's `TimedLaunch` | Skip | `LaunchMode` covers it |
| `OperationTransfer.Capture`, `PlanCapture`, `Rendezvous`, `LagTime`, `Coplanar` | `OperationGeneric` | Take | `LagTime` in seconds replaces the removed `PeriodOffset`. Keep `InterceptOnly` and `SimpleTransfer` as deprecated aliases |
| Flat `AscentAutopilot`, `AscentType` 0 or 1 | | Decide with #22 | Breaks `AscentPathClassic`, `AscentPathPVG` and `AscentPathIndex`. If taken, deprecate them rather than remove them |
| Quickload re-initialization | | Not needed | The port looks up MechJeb on each call |
| Throttle smoothing bindings | | Do not take | MechJeb 2.15.4.0 has no such members |
| Removing `OperationLan.NewLAN`, `OperationLongitude.NewSurfaceLongitude` | | Do not take | The port keeps them on the target controller's longitude |

Beyond the PRs, MechJeb 2.15 adds `OperationEccentricity`, which 0.7.1 never wrapped. KRPC.MechJeb's
to-do list (advanced transfer, attitude adjustment, rover, spaceplane autoland) is still open.

## Open questions

* Genhis' agreement, credit, and what happens to the external project and its users: keep its API,
  or break it in the move. Genhis no longer maintains it (#28), and the #29 fork has users.
* Which MechJeb versions to support.
* The phase 2 API: #22's window layout, #29's flat ascent autopilot, or the 0.7.1 layout with
  members added.
