# Mod-compatibility integration-test coverage

**Status:** in progress (2026-11-10). Every integration in scope is covered except Procedural
Fairings (section 3), which is the one open item in
[issues/mod-compat-tests.md](../../issues/mod-compat-tests.md). Done:

| Mod | Section | PR |
|---|---|---|
| FAR | 1 | [#1032](https://github.com/krpc/krpc/pull/1032) |
| Action Groups Extended | 2 | [#968](https://github.com/krpc/krpc/pull/968) |
| kOS name tag | 4 | [#1155](https://github.com/krpc/krpc/pull/1155) |
| Firespitter, KerbalActuators | 5, 6 | implemented, PR not yet opened |
| RealFuels | added after the audit | [#1039](https://github.com/krpc/krpc/pull/1039) |
| B9PartSwitch, Near Future Solar, TweakScale Rescaled | added after the audit | [#1314](https://github.com/krpc/krpc/pull/1314) |

The test plumbing moved into `krpctools.game` in [PR #1299](https://github.com/krpc/krpc/pull/1299).
"Test plumbing to reuse" below describes the current layout; the `_MOD_*` registries named in the
older sections are gone.

kRPC integrates with a number of third-party KSP mods, and several of those integrations have **no
integration-test coverage**. This doc catalogs every mod integration in the repo, cross-references
it against the integration-test suite, and lays out how to close the gaps using the mod-gating
plumbing that the RealChute (#382) and DMagic (#550) test work already established.

Out of scope: the `LiDAR` and `DockingCamera` bridge services, tracked separately in
[`design/services/dockingcam-lidar-tests.md`](dockingcam-lidar-tests.md). That work is done:
DockingCamera has in-game tests since [PR #1264](https://github.com/krpc/krpc/pull/1264), and LIDAR
was deprecated in [PR #1263](https://github.com/krpc/krpc/pull/1263), so it gets no tests.

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

As of 2026-11-10. Test files are under `service/SpaceCenter/test/` unless a path is given.

| Mod | Integration | Test coverage |
|---|---|---|
| InfernalRobotics | Bridge service | `service/InfernalRobotics/test/` |
| RemoteTech | Bridge service + SpaceCenter autopilot/throttle gating | `service/RemoteTech/test/` |
| KerbalAlarmClock | Bridge service | `service/KerbalAlarmClock/test/` |
| DockingCamera | Bridge service | `service/DockingCamera/test/` (#1264) |
| RealChute | Part-module compat (`Parachute`) | `test_parts_realchute.py` (#382) |
| DMagic | Part-module compat (`Experiment`) | `test_parts_experiment_dmagic.py` (#550) |
| AGExt | `ExternalAPI/AGExt.cs` (`Control`) | `test_action_groups_extended.py` (#968) |
| FAR | `ExternalAPI/FAR.cs` (`Flight`, `Part`) | `test_flight.py`, two classes (#1032) |
| RealFuels | `ExternalAPI/RealFuels.cs`, `RealFuelsTank` | `test_parts_realfuels.py` (#1039) |
| kOS, KSPCommunityPartModules | Name tag module (`Part.Tag`) | `test_parts_tag.py`, four mod sets (#1155) |
| B9PartSwitch | `PartField` subtype switching | `test_parts_b9partswitch.py` (#1314) |
| Near Future Solar | `SolarPanel` curved panels | `test_parts_solar_panel_nearfuturesolar.py` (#1314) |
| TweakScale Rescaled | Scaled part stats, `Part.Cost` | `test_parts_tweakscale.py` (#1314) |
| Firespitter, KerbalActuators | `ThrustReverser` | `test_parts_engine.py` (PR not yet opened) |
| Procedural Fairings | `Fairing` | **none** (section 3) |

## The gaps — mod integrations with no test coverage

### 1. Ferram Aerospace Research (FAR) — done in PR #1032

The analysis below predates the tests. [PR #1032](https://github.com/krpc/krpc/pull/1032) added two
FAR test classes to `test_flight.py`.

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
by a ProceduralFairings part in the catalog (`_PartMod`).

### 4. kOS — name-tag part field — done in PR #1155

The analysis below predates the fix. [PR #1155](https://github.com/krpc/krpc/pull/1155) resolved
#829 and added `test_parts_tag.py`, which runs over five mod sets.

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

### 5. Firespitter - thrust reverser - implemented, PR not yet opened

`ThrustReverser.cs` detects the `"FSswitchEngineThrustTransform"` module and drives reverse thrust
via its `isReversed` field and `reverseTTAction` / `normalTTAction` / `switchTTAction` actions.

**As built:** Firespitter v7.17 (`snjo/Firespitter`, no dependencies). The archive has no
`GameData/` root, so the installer's `copy_folder` also takes a folder at the top of an archive.
Craft `PartsEngineReverserFirespitter`: pod, tank and `FSnoseEngine` on
launch clamps. `TestPartsEngineReverserFirespitter` round-trips `thrust_reversed` and checks the
thrust direction turns 180 degrees and back. Detected by its part, `FSnoseEngine`.

### 6. KerbalActuators - prop-spinner thrust reverser - implemented, PR not yet opened

`ThrustReverser.cs` detects the `"WBIPropSpinner"` module and drives it via its `reverseThrust` and
`canReverseThrust` fields and the `ToggleThrustTransform` event.

**As built:** the module ships in KerbalActuators (`Angel-125/KerbalActuators` v1.9.0, installs
as `GameData/WildBlueIndustries/001KerbalActuators`), not Wild Blue Tools. It has no
dependencies, and its bundled ModuleManager is not installed. The mod ships no part that uses the
module, so an overlay (`ksp/mods/WildBlueIndustries/TestPart.cfg` in the mods registry) clones the Juno into
`kerbalActuatorsReverserTest` and `kerbalActuatorsFixedTest`. The Juno's one thrust transform
serves as both forward and reverse, so the test checks state only, not direction. Craft
`PartsEngineReverserKerbalActuators`. `TestPartsEngineReverserKerbalActuators` round-trips the
reversible part and checks the fixed part reports no reverser.

**Negative control (both):** pointing each adapter at the wrong state field fails both reverser
tests in game.

### 7. Miscellaneous engine thrust-reverser shims — likely not worth pinning

`ThrustReverser.cs` (roughly lines 70–90) also matches thrust reversers by animation/part signature
(`moduleID` / `animationName` / part name) rather than a mod assembly: stock turbofans
(`TF1ThrustReverser` / `TF2ThrustReverser`), Aircraft Carrier Accessories, Mk3 Expansion, Neist
Airliner, WaterDrinker, and Orbital Tug. Each is a niche part pack, and covering all of them means
pinning several mods for one `bool` toggle apiece.

**Recommendation:** do **not** add per-mod tests for these. If the stock-turbofan branch
(`TF1/TF2ThrustReverser`) is reachable with a stock part, cover that one with a no-mod test; leave the
rest documented-as-untested. Note the omission explicitly rather than letting it read as covered.
This stays the decision: these shims are untested on purpose, and are not open work.

The stock turbofans are covered: `TestPartsEngineReverser` drives the J-90 "Goliath" and J-33
"Wheesley" reversers with no mod installed.

## Non-integrations (nothing to test)

For the record, these were searched for and were **not** integrated in-repo at the time of the audit:
MechJeb (external project, `doc/src/third-party.rst` link only), Procedural Parts (#594 confirmed
kRPC reads the stock `SolidFuel` resource with no special-casing), Modular Fuel Tanks, Realism
Overhaul (its science parts ride on the DMagic module, already covered by #550), Kerbal Engineer, and
TweakScale.

RealFuels and TweakScale Rescaled have since gained support and tests (see the status table). Planned
integrations, MechJeb and Kerbal Engineer among them, are indexed in
[issues/mod-integrations-index.md](../../issues/mod-integrations-index.md).

## Test plumbing to reuse

Since [PR #1299](https://github.com/krpc/krpc/pull/1299) the plumbing lives in `krpctools.game`,
under `tools/krpctools/krpctools/game/`. Adding a mod is a registry entry, a craft and a test class.

* **Declare the requirement**: set `mods = ["<Name>"]` on the `TestCase` subclass from
  `krpctools.game.ksp`. The runner restarts KSP at most once per distinct mod set.
* **Register the mod**: a class in `ksp/mods/__init__.py`, added to `MODS`. It pins the archive
  (`source` URL and `sha256`), names the GameData `folders` (and top-level `files`) it installs, and
  lists the mods it `requires`. Archives download to `~/.cache/krpctools`; nothing goes in
  `MODULE.bazel`.
* **Detection**: the class's base gives the presence check. `_PartMod` probes a part in the catalog,
  `_ServiceMod` a service's `available` property, `_AssemblyMod` a loaded assembly's version. A mod
  that patches a module onto every part overrides `present` (AGExt).
* **Overlays**: `ksp/mods/<folder>/` is copied over the installed folder, to suppress a first-run
  popup or to add a test-only part (DMagic, B9PartSwitch, KerbalActuators). `ksp/mods/README.md`
  lists them.
* **Install**: GameData is reconciled to exactly the requested set and its dependencies.
* **Craft**: a `.craft` under `service/<Service>/test/craft/`, loaded with
  `launch_vessel_from_vab(...)`. Craft must be VAB-built (RealChute lesson).

Each mod that pulls in a plugin framework may need its own dependency stack and popup suppression;
budget for that per mod, not just the headline archive.

## Suggested phasing

Test-only, so **no changelog** unless a compat bug is fixed along the way, in which case that fix
gets the entry.

| Phase | Mod | State |
|---|---|---|
| 1 | Action Groups Extended | done, PR #968 (section 2) |
| 2 | Procedural Fairings | **open**, the one remaining item (section 3) |
| 3 | Firespitter, KerbalActuators | implemented, PR not yet opened (sections 5, 6) |
| 4 | FAR | done, PR #1032 (section 1) |
| 5 | kOS name tag | done, PR #1155 (section 4) |

## Verification

None of these reproduce headless or with stock parts — verification is in-game via `krpctools.game` with the
mod installed, exactly as RealChute and DMagic were validated. Each phase's test must be run against a
real install of its mod and confirmed to go red without the compat code / green with it (or at least
to exercise the mod-present branch that stock parts never reach).
