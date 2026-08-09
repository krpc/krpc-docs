# Principia support

**Status:** phase 1 implemented, for [krpc/krpc#767](https://github.com/krpc/krpc/issues/767).
Phase 1 was verified in-game against Principia `2026071410-Leray` and shipped as the
"Using kRPC with Principia" documentation page; its findings are recorded below, and one of them
contradicts the premise this doc started from. Phases 2 and 3 remain proposals, and still depend on
an upstream decision that has not been asked for.

## What was asked for

Issue #767 asks for three things:

| Ask | Principia's name for it |
| --- | --- |
| Read the predicted (purple) orbit | prediction |
| Read the historical (yellow) orbit | psychohistory (yellow is the *target* vessel's; the active vessel's is lime) |
| Read the planned (dotted) orbit | flight plan segments |
| Create manœuvres | `FlightPlanInsert` / `FlightPlanReplace` |
| Conduct manœuvres (burn, cut off on cue) | the guidance node, plus `FlightPlanGetGuidance` |

The stated benchmark is MechJeb, which "can already read Principia manœuvres and conduct
manœuvres". That premise is worth correcting up front, because it decides how much of this issue is
actually work.

## Principia has no API, and MechJeb does not use one

**Principia deliberately removed its external API.** The
[wiki page for other mods](https://github.com/mockingbirdnest/Principia/wiki/Interface-for-other-KSP-mods)
documents `principia.ksp_plugin_adapter.ExternalInterface`, obtained via a static `Get()`, offering
`CelestialGetPosition`, `CelestialGetSurfacePosition`, `GeopotentialGetCoefficient`,
`GeopotentialGetReferenceRadius` and `VesselGetPosition`. The same page ends with:

> Landau is the last version to support an external API for other KSP mods. Starting with November
> version Laplace, API entry points return `unimplemented`. Starting with December version Laurent,
> they are removed.

There is no `external_interface.cs` in `ksp_plugin_adapter/` today. The API is gone, and nothing
replaced it. [mockingbirdnest/Principia#1964](https://github.com/mockingbirdnest/Principia/issues/1964)
(expose KSP manœuvre nodes as an API) and
[#3458](https://github.com/mockingbirdnest/Principia/issues/3458) (MechJeb asking how to reach the
plugin pointer from another assembly) are both still open.

**MechJeb does not talk to Principia at all.** The MechJeb2 checkout in this workspace contains no
reference to Principia in any file. What MechJeb executes is a *stock* `ManeuverNode`, and Principia
is the thing that puts it there.

`ksp_plugin_adapter.cs` (`RenderGuidance`, around line 2000) does this every frame while "show
manœuvre on navball" is ticked:

 * find the first manœuvre whose `final_time` is in the future;
 * ask the plugin for `FlightPlanGetGuidance` (a world-space unit thrust direction) and the
   manœuvre's `Burn`;
 * **delete every maneuver node on the active vessel** and add one of its own at `burn.initial_time`;
 * set its `DeltaV` by projecting `guidance * |burn.intensity.xyz|` into the *stock osculating*
   patch's Frenet frame, then `solver.UpdateFlightPlan()`;
 * clear the node for one frame after each scheduled burnout so that followers "bail out instead of
   guiding to the next burn with engines still firing" — the comment names stock SAS and MechJeb
   explicitly.

So the interop contract that MechJeb enjoys is: *Principia writes one stock maneuver node, autopilots
read it*. kRPC already exposes stock maneuver nodes through `SpaceCenter.Control.Nodes`,
`SpaceCenter.Node` and `Node.BurnVector`.

**Half of the "conduct manœuvres" half of #767 therefore already works**, undocumented and
unverified. That is phase 1. Verification showed the split is *pointing works, cutoff does not*:
see [what phase 1 found](#what-phase-1-found).

## Constraint: what is reachable, and at what cost

Everything beyond the guidance node lives behind `PrincipiaPluginAdapter`'s private
`IntPtr plugin_`, reached through the internal generated `Interface` class, which P/Invokes
`principia__*` C entry points in the native `principia` library.

| Path | Reachable | Notes |
| --- | --- | --- |
| Guidance node | Yes, no Principia dependency | Stock `patchedConicSolver.maneuverNodes`, already exposed |
| `PluginRunning()` | Yes, `public` on the adapter | Clean availability check |
| `Plugin()` → `IntPtr` | `internal` method on a `public` `ScenarioModule` | Reflection |
| `Interface.*` entry points | `internal static extern` | Reflection, or re-declared `DllImport` |
| `Burn`, `NavigationManoeuvre`, `XYZ`, … | `internal` generated types | `Activator.CreateInstance` plus field reflection |

**Do not re-declare the P/Invokes.** Principia's `ksp_plugin_adapter.dll.config` carries a Mono
`dllmap`, and `.dll.config` applies to the declaring assembly only. Marshaling of the generated
structs is also non-trivial (custom UTF-8/UTF-16, optional and ownership-transfer marshalers). A
wrong signature is not a managed exception, it is a native crash of the whole game. Reflecting
Principia's own declarations reuses Principia's own marshaling and is the only defensible variant.

### What the entry points can and cannot give us

Derived from `serialization/journal.proto` (one message per interface method), `plotter.cs` and
`flight_planner.cs`.

**Available in world coordinates:**

 * Flight plan: `FlightPlanExists`, `FlightPlanCount`, `FlightPlanNumberOfManoeuvres`,
   `FlightPlanNumberOfAnomalousManoeuvres`, `FlightPlanGetInitialTime`,
   `FlightPlanGetDesiredFinalTime`, `FlightPlanGetActualFinalTime`, `FlightPlanGetAnomalousStatus`,
   `FlightPlanGetManoeuvre`, `FlightPlanGetManoeuvreFrenetTrihedron`, `FlightPlanGetGuidance`.
 * Writes: `FlightPlanCreate`, `FlightPlanDelete`, `FlightPlanInsert`, `FlightPlanReplace`,
   `FlightPlanRemove`, `FlightPlanRebase`, `FlightPlanSetDesiredFinalTime`, `FlightPlanSelect`,
   `FlightPlanDuplicate`.
 * Summarized geometry: `RenderedPredictionApsides`, `RenderedPredictionNodes`,
   `RenderedPredictionClosestApproaches`, and the `FlightPlanRendered*` equivalents. These return
   `Iterator*` handles over world positions and times.
 * Flight plan curve: `FlightPlanRenderedSegment` yields a discrete-trajectory iterator
   (`IteratorGetDiscreteTrajectoryQP` / `…Time` / `…XYZ`), in the current plotting frame.
 * Per-vessel: `VesselVelocity`, `VesselFromParent`, `VesselTangent` / `VesselNormal` /
   `VesselBinormal` (the Frenet trihedron the Principia navball uses), `NavballOrientation`,
   `CurrentTime`, `GetVersion`.

**Not available as data:** the prediction and psychohistory *curves* — the purple and yellow lines
the issue names. They are drawn through `PlanetariumPlotPrediction` and
`PlanetariumPlotPsychohistory`, which project straight into RP2 screen lines against a camera. There
is no world-space accessor. The closest substitutes are `RenderedPrediction{Apsides,Nodes,
ClosestApproaches}`, which give the events on those curves rather than the curves themselves.

**This gap should be stated in the issue.** Two of the three "read the orbit" asks can only be
answered with events, not point sets, unless upstream adds an accessor.

`Burn` and `NavigationManoeuvre` are the payload types:

```
Burn { thrust_in_kilonewtons, specific_impulse_in_seconds_g0, NavigationFrameParameters frame,
       initial_time, Intensity intensity, is_inertially_fixed }
NavigationManoeuvre { Burn burn, initial_mass_in_tonnes, final_mass_in_tonnes, mass_flow,
                      duration, final_time, time_of_half_delta_v, time_to_half_delta_v }
Intensity { CoordinateSystem coordinate_system, XYZ xyz, SphericalCoordinates spherical_coordinates }
```

### Risks

 * **No stability guarantee, by upstream's explicit choice.** Principia releases monthly and the C
   ABI is internal. Every kRPC release would be pinned to a window of Principia releases, and each
   Principia release could silently break the shim. kRPC currently has no such relationship with any
   mod.
 * **Failure mode is a native crash.** `APILoader`'s soft-fail model does not apply.
 * **Not CI-testable.** Principia is a large native mod with per-platform binaries and its own KSP
   version matrix; the `MODS` table in `tools/krpctest/krpctest/install.py` pins mod archives per
   platform and could not carry it usefully. Coverage would be manual, on this machine.
 * **Re-entrancy.** kRPC dispatches RPCs from `FixedUpdate` (`server/src/Addon.cs:365`), and
   Principia advances the plugin from its own `FixedUpdate` coroutine. Read-only queries mid-frame
   are fine; flight-plan mutations race against Principia's own use and would need to be deferred to
   a known point in the frame.

**Recommendation:** do not ship phases 2 or 3 against a reflected private ABI without first asking
upstream. File an issue on `mockingbirdnest/Principia` asking for a supported read path for the
flight plan (and ideally the prediction), referencing #1964 and #3458. Phase 1 stands on its own and
depends on none of this.

## Phase 1 — document and verify the interop that exists

No new service, no dependency on Principia, no reflection.

1. **Verify in-game** with Principia installed, on a flight-plan vessel with "show manœuvre on
   navball" ticked:
    * `Control.Nodes` reports Principia's guidance node, and only that node;
    * `Node.BurnVector`, `Node.Prograde/Normal/Radial`, `Node.UT`, `Node.RemainingDeltaV` are
      consistent with the Principia flight planner window;
    * `Node.RemainingBurnVector` and the existing autopilot pointing at
      `Node.ReferenceFrame` execute a burn correctly;
    * the one-frame node clear at burnout does not make kRPC throw — `Control.Nodes` briefly
      empties, and scripts polling it must tolerate that.
2. **Determine what breaks.** Expected sharp edges, each to be confirmed and then either fixed or
   documented:
    * `Control.AddNode` and `Control.RemoveNodes` fight the adapter, which clears all nodes each
      frame. Node creation through kRPC is effectively unusable under Principia.
    * `Node.Orbit` wraps `node.nextPatch`, a stock patched-conic result that is meaningless under
      n-body integration.
    * `Vessel.Orbit` is the *osculating* orbit — Principia writes it via
      `orbit.UpdateFromStateVectors` each frame. Instantaneous elements are right; anything
      predictive (`TimeToApoapsis`, `Period`, `NextOrbit`, `Orbit.ReferencePlane*`) is not.
    * Whether `Control.Nodes`' `OrderBy(UT)` and the node's identity are stable frame to frame,
      given the adapter recreates the node whenever it loses track of it.
3. **Write it down.** A "Using kRPC with Principia" section, either in `doc/src/third-party.rst` or
   as a short page beside it: what works, what the guidance node is, which RPCs return values that
   do not mean what they normally mean. This is the deliverable most likely to satisfy the majority
   of #767's readers.

Phase 1 answers "conduct manœuvres" and closes the MechJeb-parity gap, since MechJeb has no more
than this either.

## What phase 1 found

Verified in-game against Principia `2026071410-Leray` on KSP 1.12.5, on a crewed vessel in a 200 km
circular Kerbin orbit with a two-manœuvre flight plan and "show manœuvre on navball" ticked.
Shipped as `doc/src/principia.rst`.

| Claim | Result |
| --- | --- |
| `Control.Nodes` reports the guidance node and only that node | Confirmed. A two-manœuvre plan still yields exactly one node, the next manœuvre |
| `Node.DeltaV` matches the flight planner | Confirmed. 50 m/s planned read back as 50.000006, 100 m/s as 100.000012 |
| Autopilot on `Node.ReferenceFrame` flies the burn | Confirmed. 0.53° pointing error; resulting orbit matched a prograde burn |
| `Node.RemainingDeltaV` ends the burn | **Refuted. Does not count down at all** |
| One-frame node clear at burnout empties `Control.Nodes` | Not observed in 51328 samples; see below |
| `Control.AddNode` is unusable | Confirmed. Node deleted within a frame; the handle then throws |
| `Control.RemoveNodes` / `Node.Remove` | Confirmed. List empties, node restored next frame with a *new* identity |
| Node property writes | Confirmed futile. Take effect for one frame, then overwritten |
| `Node.Orbit` is a stock patched conic | Confirmed by source (`node.nextPatch`). Predicted 280965 m apoapsis against 283735 m actual, but the burn overshot by 0.9% (50.44 m/s applied against 50.00 planned), so this run does not measure the two-body error and no useful bound was obtained |
| `Vessel.Orbit` is osculating | Confirmed. Eccentricity wanders frame to frame as Principia integrates |
| Node identity stable frame to frame | Confirmed while the underlying `ManeuverNode` survives; a recreate yields a new object id and the old handle throws cleanly |

Three findings were not anticipated by this doc:

 * **`Node.RemainingDeltaV` never counts down.** `RenderGuidance` assigns `guidance_node_.DeltaV`
   from `|burn.intensity.xyz|`, the *planned* Δv of the flight-plan manœuvre, on every frame. Stock's
   `GetBurnVector`, which `RemainingDeltaV` reads, therefore has the planned value reset under it
   each frame. Measured constant at exactly 50.0000 across a complete 1.78 s burn, and at 100.0 for
   1211 samples across a 120 s burn that emptied the tank. The idiom
   `while node.remaining_delta_v > ε` cannot terminate. This is the single most consequential fact
   for #767, and it means "conduct manœuvres" is only half-served by the guidance node: kRPC can
   point at the burn but cannot end it without integrating Δv itself.
 * **`Node.UT` is the start of the burn, not its midpoint.** `RenderGuidance` sets
   `guidance_node_.UT = burn.initial_time`. Stock scripts burn from `UT - duration/2`; under
   Principia that starts half a burn early. `NavigationManoeuvre` carries `time_of_half_delta_v`
   separately, confirming `initial_time` is the start.
 * **The one-frame clear is not reliably observable.** `RenderGuidance` runs from Principia's
   `LateUpdate` (`LateUpdate` → `RenderNavballAndAccessories` → `RenderNavball` →
   `RenderGuidance`), while kRPC dispatches RPCs from `FixedUpdate` (`server/src/Addon.cs`). When
   the game renders faster than the physics tick, the clear and the recreate can fall between two
   physics steps and never be served to a client. It was not seen once in 51328 samples across a
   manœuvre handover. It is still in the code, so scripts must tolerate an empty `Control.Nodes`;
   they just cannot be tested for it by polling.

### The test harness cannot host Principia

`tools/TestingTools/src/AutoLoadGame.cs` loads the save itself from the main menu, calling
`GamePersistence.UpdateScenarioModules` and `HighLogic.CurrentGame.Start()` directly. Under that
path no `SCENARIO { name = PrincipiaPluginAdapter }` node is added to the game, so Principia's
`ScenarioModule` is never instantiated, its adapter never runs, and no guidance node is ever
written. Principia's native library loads normally and logs no error, so the failure is silent: the
toolbar button simply never appears.

Both `bazel run //:test-ingame` and `bazel run //:run-ksp -- --load-game=…` go through this path.
All phase 1 verification was done by launching with no auto-load and loading the save by hand from
the main menu. Any future in-game Principia work has the same constraint, which reinforces the
"not CI-testable" risk above: it is not merely that the mod is hard to pin, it is that the harness
cannot start it at all. Worth an issue in its own right, since it affects any mod that ships a
scenario module.

## Phase 2 — read-only `Principia` service

Only if upstream engages, or after an explicit decision to accept the pinning risk.

A dedicated service, per the one-service-per-mod convention — `service/Principia/`, modeled on
`service/RemoteTech/`. **`APILoader` cannot be reused**: it binds delegate-typed properties to
same-named public static methods, and Principia has no such class. The service needs its own loader
that resolves `PrincipiaPluginAdapter` (via `ScenarioRunner`'s loaded modules, or
`FindObjectOfType`), reads `PluginRunning()`, reflects `Plugin()` for the handle, and caches
`MethodInfo`s for the `Interface` entry points and `FieldInfo`s for the generated structs. That
shim is the bulk of the work and is where a version check must live — refuse to bind, rather than
bind wrong, when the reflected shapes do not match.

Service id: 8 and 9 are free (2 SpaceCenter, 3 Drawing, 4 InfernalRobotics, 5 KerbalAlarmClock,
6 RemoteTech, 7 UI, 10 LiDAR, 11 DockingCamera, 12 Debug). The
[KSPTrajectories proposal](trajectories-service.md) also claims 8; whichever lands first takes it.

Surface:

 * `Available`, `Version`, `CurrentTime`.
 * `Vessel.HasFlightPlan`, and a `FlightPlan` class: `ManoeuvreCount`, `AnomalousManoeuvreCount`,
   `InitialTime`, `DesiredFinalTime`, `ActualFinalTime`, indexed `Manoeuvre(i)`.
 * A `Manoeuvre` class: `InitialTime`, `Duration`, `FinalTime`, `TimeToHalfDeltaV`, `DeltaV`,
   `Thrust`, `SpecificImpulse`, `InitialMass`, `FinalMass`, `IsInertiallyFixed`, and the Frenet
   trihedron from `FlightPlanGetManoeuvreFrenetTrihedron`.
 * `GuidanceDirection(ReferenceFrame)` from `FlightPlanGetGuidance` — the piece that lets a script
   fly a burn without depending on the guidance node existing.
 * Apsides, nodes and closest approaches for the prediction and the flight plan, as time/position
   lists in a caller-chosen `ReferenceFrame`.
 * Flight plan segment sampling from `FlightPlanRenderedSegment`, if the plotting-frame dependence
   can be made comprehensible to a script. It cannot be made frame-agnostic: the points come out in
   whatever plotting frame the *user's UI* has selected.

All world-space `XYZ` results convert through SpaceCenter's existing `ReferenceFrame` helpers.
`Principia` would depend on `//service/SpaceCenter`, as `RemoteTech` already does.

## Phase 3 — writing manœuvres

`FlightPlanInsert`, `FlightPlanReplace`, `FlightPlanRemove`, `FlightPlanCreate`,
`FlightPlanSetDesiredFinalTime`. Deferred deliberately: writes need a `Burn` constructed with a
`NavigationFrameParameters`, which drags in Principia's plotting-frame model; they race with the
adapter's own `FixedUpdate`; and a malformed burn is the likeliest route to a native crash. Nothing
here should be attempted before phase 2 has been stable across at least two Principia releases.

## Open questions

 1. Will upstream restore a supported read path? Everything past phase 1 hinges on it.
 2. Is kRPC willing to carry a service pinned to an unversioned private ABI, and to break it monthly?
    If not, #767 closes at phase 1 with documentation and an upstream link.
 3. Can the prediction and psychohistory curves be exposed at all, given they are only ever
    projected to screen space? Currently: no, only their apsides, nodes and closest approaches.
 4. Should kRPC do anything about `Node.RemainingDeltaV` under Principia, or only document it?
    Phase 1 documents it. A fix inside `SpaceCenter` is possible in principle — track the node's
    delta-v across frames and report the drop — but it would be guessing at another mod's intent
    from a value that mod rewrites, and it would be wrong for any other mod that also drives the
    node. Doing nothing leaves every kRPC script that follows the standard burn idiom silently
    broken under Principia, which is the state #767's reporter is already in. A `Principia` service
    (phase 2) would answer it properly, via `FlightPlanGetGuidance` and the manœuvre's own state.

## References

 * kRPC issue: [krpc/krpc#767](https://github.com/krpc/krpc/issues/767)
 * [Interface for other KSP mods](https://github.com/mockingbirdnest/Principia/wiki/Interface-for-other-KSP-mods)
   — the removed API and the removal notice
 * [mockingbirdnest/Principia#1964](https://github.com/mockingbirdnest/Principia/issues/1964) —
   KSP manœuvre nodes as an API
 * [mockingbirdnest/Principia#3458](https://github.com/mockingbirdnest/Principia/issues/3458) —
   MechJeb/Principia compatibility, and the plugin-pointer problem
 * `ksp_plugin_adapter/ksp_plugin_adapter.cs` (`RenderGuidance`), `flight_planner.cs`, `plotter.cs`,
   `serialization/journal.proto` in the Principia repo
 * [KSPTrajectories service proposal](trajectories-service.md) — the same shape of problem, with a
   mod that does have an API
