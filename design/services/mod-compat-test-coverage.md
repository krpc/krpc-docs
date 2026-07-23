# Mod-compatibility integration-test coverage

**Status:** in progress (2026-07-17) — Action Groups Extended done and merged as
[PR #968 "AGExt tests"](https://github.com/krpc/krpc/pull/968) (2026-07-18, section 2);
the rest not yet implemented. kOS name-tag (was phase 2) is **blocked on issue #829** and demoted — see
section 4. No GitHub issue for the overall test effort yet — one should be filed (#829 covers only the
kOS module-duplication problem).

kRPC integrates with a number of third-party KSP mods, and several of those integrations have **no
integration-test coverage**. This doc catalogs every mod integration in the repo, cross-references
it against the integration-test suite, and lays out how to close the gaps using the mod-gating
plumbing that the RealChute (#382) and DMagic (#550) test work already established.

Out of scope: the `LiDAR` and `DockingCamera` bridge services. They are also untested, but they bind
to bespoke, non-public bridge builds and need mod-side work before kRPC support can be improved —
tracked separately in [`design/services/dockingcam-lidar-tests.md`](dockingcam-lidar-tests.md).

## Two integration styles

kRPC touches mods two ways, and the gaps are almost entirely in the second:

1. **Dedicated bridge services** — a whole `service/<Mod>/` directory that reflection-loads a mod
   assembly and exposes it as a kRPC service with an `Available` flag. These are
   `InfernalRobotics`, `KerbalAlarmClock`, `RemoteTech` (plus the out-of-scope `LiDAR` /
   `DockingCamera`). All of the in-scope bridge services are already tested.

2. **Mod-compatibility code embedded in SpaceCenter** — reflection wrappers under
   `service/SpaceCenter/src/ExternalAPI/` (registered in `ExternalAPIAddon.cs`), and string-named
   part-module lookups (`Part.HasModule("Name")` / `Part.Module("Name")`) scattered through the
   `Services/Parts/` wrappers. No compile-time dependency on the mod; behavior silently changes when
   the mod is present. **This is where the untested integrations live.**

## Current coverage

| Mod | Integration | Test coverage |
|---|---|---|
| InfernalRobotics | Bridge service | `service/InfernalRobotics/test/` — 4 classes |
| RemoteTech | Bridge service + SpaceCenter autopilot/throttle gating | `service/RemoteTech/test/` — 4 classes; gating in `service/SpaceCenter/test/test_control.py` |
| KerbalAlarmClock | Bridge service | `service/KerbalAlarmClock/test/` — 1 class |
| RealChute | Part-module compat (`Parachute`) | `service/SpaceCenter/test/test_parts_realchute.py` (#382) |
| DMagic | Part-module compat (`Experiment`) | `service/SpaceCenter/test/test_parts_experiment_dmagic.py` (#550) |

## The gaps — mod integrations with no test coverage

### 1. Ferram Aerospace Research (FAR) — highest value, hardest to test

`service/SpaceCenter/src/ExternalAPI/FAR.cs` binds
`APILoader.Load(typeof(FAR), "FerramAerospaceResearch", "FerramAerospaceResearch.FARAPI",
new Version(0,15))` and wraps `CalculateVesselAeroForces` plus delegates for dynamic pressure, lift
and drag coefficients, reference area, terminal velocity, ballistic coefficient, Mach, Reynolds,
angle of attack, sideslip, stall fraction, and TSFC.

When FAR is present, kRPC swaps its **entire aerodynamics reporting** over to FAR — this is the
deepest mod integration in the codebase. Consumers:

* `Services/Flight.cs` (roughly lines 190–925): every aerodynamic property (`DynamicPressure`,
  `AerodynamicForce`, `Lift`, `Drag`, `StallFraction`, `Mach`, `ReynoldsNumber`,
  `AngleOfAttack`, `SideslipAngle`, `TerminalVelocity`, `DragCoefficient`, `LiftCoefficient`,
  `BallisticCoefficient`, `ThrustSpecificFuelConsumption`, …) reads from FAR instead of the stock
  model when `FAR.IsAvailable`.
* `Services/SpaceCenter.cs` — the `FARAvailable` property (around line 1034).
* `Services/Parts/Part.cs` (around line 926).

**Testability:** FAR has public KSP 1.12.x releases, so it is pinnable in principle. The hard part is
*asserting* on the values: FAR's aero outputs depend on a stable flight condition (altitude, speed,
attitude, atmosphere), so a test must establish a controlled state — most robustly by teleporting a
craft to a fixed orbit/atmospheric condition, or asserting looser invariants (values are non-zero and
finite, `FARAvailable` is true, `AngleOfAttack`/`SideslipAngle` respond in the expected direction to
attitude) rather than exact magnitudes. Detected via a new `SpaceCenter.FARAvailable` probe in
`_MOD_SERVICES`-style plumbing (the property already exists), so no `_MOD_PARTS` part is needed.

### 2. Action Groups Extended (AGExt) — implemented

Status: **done** — merged as [PR #968 "AGExt tests"](https://github.com/krpc/krpc/pull/968) (2026-07-18).

`service/SpaceCenter/src/ExternalAPI/AGExt.cs` binds
`APILoader.Load(typeof(AGExt), "AGExt", "ActionGroupsExtended.AGExtExternal")` and reflects into
`AGX2VslGroupActions`, reading the `prt` and `ba` fields off the mod's action objects. Consumed in
`Services/Control.cs` (roughly lines 652–731): when AGExt is available, custom action-group state,
activate/toggle, and action enumeration route through the mod instead of the stock 10-group model,
extending the valid range from 0–9 to 0–250. (The kRPC class was formerly misnamed `AGX`; renamed to
`AGExt` to match the mod. The `AGX2Vsl*` delegate property names are kept because they mirror the
mod's own method names.)

**Detection.** AGExt adds no part of its own — its `part.cfg` is a ModuleManager `@PART[*]` patch
adding a `ModuleAGX` module to *every* part — and it has no kRPC service, so neither `_MOD_SERVICES`
nor the `_MOD_PARTS` part-name probe applies. Detection uses a new test-only
`TestingTools.PartModuleAvailable(name)` procedure that scans the loaded part prefabs for a module of
the given name, plus a `_MOD_MODULES = {"AGExt": "ModuleAGX"}` registry in
`tools/krpctest/krpctest/game.py`. This keeps detection test-only (no new public RPC, no changelog);
a public `SpaceCenter.AGExtAvailable` mirroring `FARAvailable` was considered and rejected to avoid
widening the public API for a test.

**Mod sourcing.** AGExt 2.4.1.4 (`GameData/Diazo/AGExt`, KSP 1.12.0–1.12.99) installs no
dependencies of its own but its plugin references the LGG UI stack, so it reuses RealChute's
ClickThroughBlocker/ToolbarControl/Harmony archives; ModuleManager (already bundled in every kRPC
test install) applies the `ModuleAGX` patch.

**Coverage.** `service/SpaceCenter/test/test_action_groups_extended.py`
(`TestActionGroupsExtended`, `mods = ["AGExt"]`) asserts: extended group state round-trips (10/50/250),
the extended 0–250 range (251 rejected), and `get_action_group_actions` for extended groups (multi-
action, single-action, empty), modeled on the stock `TestActionGroupActions`. Uses an AGExt-built
`ActionGroupsExtended.craft` with actions assigned to groups 11/12 (and 13 empty).

### 3. Procedural Fairings

`service/SpaceCenter/src/Services/Parts/Fairing.cs` (lines ~8–34): a `Fairing` wraps either the stock
`ModuleProceduralFairing` or the mod module `"ProceduralFairingDecoupler"` (the comment names the
ProceduralFairings mod explicitly). Only stock fairings are currently tested.

**Testability:** Procedural Fairings has public KSP 1.12 releases and self-contained parts. A single
mod-part craft plus a `Fairing` jettison/state test class, following the RealChute pattern. Detected
via `_MOD_PARTS` (a ProceduralFairings part in the catalog).

### 4. kOS — name-tag part field — blocked on #829, demoted

`service/SpaceCenter/src/Services/Parts/Part.cs` (lines ~100–113): the `Part.Tag`
getter/setter reads and writes the `nameTag` field of the `"KOSNameTag"` module via reflection.

This one is **not** the trivial round-trip it first looks like, because kRPC does **not** rely on kOS
to supply the module. kRPC ships **its own** `KOSNameTag : PartModule` (simple name `KOSNameTag`,
`service/SpaceCenter/src/NameTag/NameTag.cs`) and MM-patches it onto every part whenever neither kOS
nor the standalone NameTag mod is installed:

```
@PART[*]:FOR[kOS|kRPC]:NEEDS[!kOS&!NameTag] { MODULE { name = KOSNameTag } }
```

The design intent is a *single* shared name tag that works with kRPC, kOS, or both. Three
consequences for testing:

1. **The mod path is already exercised with no mod installed.** On a stock kRPC install the patch adds
   `KOSNameTag` to every part, so `Part.Tag` round-trips against kRPC's own module. A cheap **no-mod**
   test (set `Tag`, read it back) covers the getter/setter and kRPC's module today — but it does *not*
   touch kOS. (This corrects the earlier assumption that the module is absent on stock parts.)
2. **`_MOD_MODULES` detection cannot gate on kOS.** A module with simple name `KOSNameTag` is present
   whether or not kOS is installed (kRPC supplies it when kOS is absent, kOS supplies it otherwise), so
   the prefab-module probe added for AGExt can't distinguish the two — it would report the mod
   "available" in a stock install. The AGExt shim does **not** transfer here.
3. **The real kOS integration is the fragile dual-install scenario in #829.** With both mods present,
   two assemblies define a `KOSNameTag` simple type; KSP resolves the name by `loadedAssemblies` order
   and picks the first match, which currently works only by the luck of kOS sorting before kRPC
   alphabetically. Issue **#829** tracks this; the maintainer has agreed to move kRPC's module to a
   shared location (e.g. KSPCommunityPartModules) so the duplicate simple name goes away.

**Recommendation:** defer the kOS integration test until #829 is resolved, and design the test against
whatever shared-module arrangement replaces the current duplicate — pinning the present dual-mod
behavior would just lock in the fragile design #829 is about to change. The no-mod `Part.Tag`
round-trip (consequence 1) is a legitimate, independent quick win that can ship now regardless. kOS is
actively maintained with public KSP 1.12 releases, so sourcing is not the blocker — the module-identity
design is.

### 5. Firespitter — thrust reverser

`service/SpaceCenter/src/Services/Parts/ThrustReverser.cs` (around line 49): detects the
`"FSswitchEngineThrustTransform"` module and drives reverse thrust via its `isReversed` field and
`reverseTTAction` / `normalTTAction` / `switchTTAction` actions.

**Testability:** the Firespitter core plugin is public. Needs a craft with a Firespitter reversible
engine; test toggles `Reversed` and asserts it round-trips. Detected via `_MOD_PARTS`.

### 6. Wild Blue Industries — prop-spinner thrust reverser

`ThrustReverser.cs` (around line 52): detects the `"WBIPropSpinner"` module and drives its
reverse-thrust capability. WBIPropSpinner ships in Wild Blue Tools / associated WBI part packs.

**Testability:** public releases exist; needs release-sourcing to confirm which specific WBI download
provides `WBIPropSpinner` and pins cleanly on KSP 1.12. Same craft-plus-toggle test shape as
Firespitter. Detected via `_MOD_PARTS`.

### 7. Miscellaneous engine thrust-reverser shims — likely not worth pinning

`ThrustReverser.cs` (roughly lines 70–90) also matches thrust reversers by animation/part signature
(`moduleID` / `animationName` / part name) rather than a mod assembly: stock turbofans
(`TF1ThrustReverser` / `TF2ThrustReverser`), Aircraft Carrier Accessories, Mk3 Expansion, Neist
Airliner, WaterDrinker, and Orbital Tug. Each is a niche part pack, and covering all of them means
pinning several mods for one `bool` toggle apiece.

**Recommendation:** do **not** add per-mod tests for these. If the stock-turbofan branch
(`TF1/TF2ThrustReverser`) is reachable with a stock part, cover that one with a no-mod test; leave the
rest documented-as-untested. Note the omission explicitly rather than letting it read as covered.

## Non-integrations (nothing to test)

For the record, these were searched for and are **not** integrated in-repo, so there is no compat code
to test: MechJeb (external project, `doc/src/third-party.rst` link only), Procedural Parts (#594
confirmed kRPC reads the stock `SolidFuel` resource with no special-casing), RealFuels / Modular Fuel
Tanks, Realism Overhaul (its science parts ride on the DMagic module, already covered by #550),
Kerbal Engineer, and TweakScale.

## Test plumbing to reuse

The RealChute and DMagic work already built everything needed; adding a mod is mostly registry
entries plus a craft and a test class.

* **Declare the requirement** — set `mods = ["<Name>"]` on the `krpctest.TestCase` subclass
  (`tools/krpctest/krpctest/testcase.py`). The harness restarts KSP at most once per distinct mod set
  (`pytest_plugin.py` groups by mod set) and fails fast on sets that install but never become
  available (`game.py` `_unsatisfiable`).
* **Fetch the archive** — add an `http_archive` (URL + sha256) in `MODULE.bazel` (the mod block,
  ~lines 451–520) and a `filegroup` in `tools/mods/BUILD.bazel`.
* **Register install + GameData layout** — add the mod to the `MODS` registry in
  `tools/krpctest/krpctest/install.py` (name → Bazel target(s) + GameData subdir). `_reconcile_mods`
  makes GameData contain *exactly* the requested managed set.
* **Register detection** — either `_MOD_SERVICES` (mod exposes a kRPC service or an `Available` flag,
  e.g. FAR's `FARAvailable`) or `_MOD_PARTS` (probe a mod part in the loaded catalog, e.g. RealChute's
  `RC.stack`) in `game.py`.
* **Suppress first-run popups / add test parts** — config overlays under `tools/mods/config/<subdir>/`
  (RealChute needs the Harmony / ClickThroughBlocker / ToolbarControl dependency stack + popup
  suppression; DMagic ships no parts so a test-only part is defined in
  `tools/mods/config/DMagicScienceAnimate/TestPart.cfg`).
* **Craft** — a `.craft` under `service/<Service>/test/craft/` built from the mod's parts, loaded via
  `launch_vessel_from_vab(...)`. Craft must be VAB-built (RealChute lesson).

Each mod that pulls in a plugin framework may need its own dependency stack and popup suppression;
budget for that per mod, not just the headline archive.

## Suggested phasing

Roughly increasing difficulty; each phase is independently shippable and additive (test-only, so **no
changelog** unless a compat bug is fixed along the way, in which case that fix gets the entry).

1. **Action Groups Extended** — *done* (merged as PR #968); see section 2. The `_MOD_MODULES` /
   `TestingTools.PartModuleAvailable` detection shim added here is reusable by any future
   module-patch-only mod.
2. **Procedural Fairings** — self-contained parts, clean jettison/state assertions. Now the best next
   target: no module-identity complications, and it exercises the untested `_MOD_PARTS` path on a fresh
   mod.
3. **Firespitter** and **Wild Blue Industries** thrust reversers — same toggle-and-read shape; WBI
   needs release-sourcing to identify the exact download for `WBIPropSpinner`.
4. **FAR** — most valuable, most involved: pin the mod, establish a controlled flight condition, and
   assert FAR-sourced aero values (start with invariants/directional response, tighten to magnitudes
   only if a stable condition can be reproduced headless).
5. **kOS name-tag** — **blocked on #829** (see section 4); the AGExt `_MOD_MODULES` shim does not apply
   because kRPC ships its own `KOSNameTag` module. Revisit once #829's shared-module fix lands. The
   no-mod `Part.Tag` round-trip is a separable quick win that need not wait.

Each phase should also add the new test file(s) to `//:test` and `//:lint` and their `BUILD.bazel`
wiring (LiDAR/DockingCamera showed how easy it is to leave a service out of the root suites).

## Verification

None of these reproduce headless or with stock parts — verification is in-game via krpctest with the
mod installed, exactly as RealChute and DMagic were validated. Each phase's test must be run against a
real install of its mod and confirmed to go red without the compat code / green with it (or at least
to exercise the mod-present branch that stock parts never reach).
