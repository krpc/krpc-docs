# MechJeb2 service

**Status:** proposal. Issues [#288](https://github.com/krpc/krpc/issues/288) (MechJeb2 and Kerbal
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
2. **Improve** it to current kRPC and fill its to-do list. What changes is decided when porting.
3. **Stage stats** from the fuel-flow simulation (#311), once MechJeb can share it.

## Open questions

* Genhis' agreement, credit, and what happens to the external project and its users: keep its API,
  or break it in the move.
* Which MechJeb versions to support.
