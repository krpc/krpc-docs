# Editor scene API: part tree and stage delta-v

**Status:** done, all six phases built, phase 6 added after the first five as a deliberate
reversal of this document's scope. One follow-up is left open: what a part proxy taken in the
editor should do when the craft is reloaded or launched, described under
[Testing](#testing). Covers
[issue #263](https://github.com/krpc/krpc/issues/263) and supersedes the draft
[PR #788](https://github.com/krpc/krpc/pull/788), whose entry-point shape is kept and whose
implementation approach is not (see [Why not PR #788 as it stands](#why-not-pr-788-as-it-stands)).
Where the build diverged from this design, see [As built](#as-built).

Make the parts of the SpaceCenter service that describe a *design* rather than a *flight* usable
from the VAB and SPH: traverse the part tree of the ship under construction, and read stock delta-v
and stage information for it.

## Motivation

The stated use is external design tooling: a script that walks the craft you are building, checks
stage delta-v and TWR against a mission profile, and reports back, without launching anything.
Requested repeatedly since 2016, most concretely for adjusting solid booster thrust limits, which
can only be done in the editor.

The other half of #263, "much of the SpaceCenter service should be available in other game scenes",
was solved by [#471](https://github.com/krpc/krpc/issues/471) (0.4.8): `GameScene` became a per-RPC
set with inheritance, which closed [#430](https://github.com/krpc/krpc/issues/430),
[#434](https://github.com/krpc/krpc/issues/434) and
[#470](https://github.com/krpc/krpc/issues/470). What that release could not open up was the parts
API, because it is built on a `Vessel`, which does not exist in the editor. That is what this
document is about.

## What already works in the editor

| Area | Notes |
|---|---|
| Scene switching | `KRPC.GameScene` is settable to `EditorVAB`/`EditorSPH`; `test_game_scene.py` already drives it |
| Celestial bodies | `SpaceCenter.Bodies`, orbits, reference frames |
| Launching | `LaunchableVessels`, `LaunchVessel`, `LaunchVesselFromVAB`/`FromSPH`, `LaunchSites` |
| Managers | `ContractManager`, `AlarmManager` |

The gap is everything reached through a vessel. `SpaceCenter.ActiveVessel` is `GameScene.Flight`,
and there is no other way to obtain a `Parts` object.

## What KSP provides

Read from a `monodis` disassembly of the real `Assembly-CSharp.dll`, not the API stubs.

### The ship under construction

`EditorLogic.fetch.ship` is a `ShipConstruct`. `ShipConstruct` implements `IShipconstruct`, and that
interface declares exactly one member:

```
List<Part> Parts { get; }
```

So `IShipconstruct` is the common ground between a `Vessel` and an editor ship, and it is enough for
tree traversal and nothing else. Useful `ShipConstruct` fields beyond it: `shipName`,
`shipDescription`, `shipFacility` (an `EditorFacility`), `shipSize`, `persistentId`, `parts`,
`vesselDeltaV`.

`EditorLogic.LoadShipFromFile(string path)` loads a craft file into the editor.

### Part identity in the editor

`Part` carries four ids: `persistentId`, `craftID`, `flightID`, `launchID`. **`flightID` is not
assigned until launch**, which is why the current `Part` proxy cannot work in the editor at all.

Of the other three, **`craftID` is the one that is stable in the editor**, measured in-game (see
[Measured behavior](#measured-behavior)): `persistentId` is regenerated on every craft load and on
every undo, while `craftID` survives both, is unique within a ship, and carries through launch
unchanged.

`craftID` is persisted in the craft file itself, as part of each part's key
(`part = mk1-3pod_4294138784`), which is why it survives a reload. Writers are `Part.Awake` (from
the Unity instance id, for a newly placed part), `ShipConstruct.LoadShip` (from the file),
`ProtoPartSnapshot.ConfigurePart` (in flight), and `ShipConstruction.SanitizeCraftIDs`, which
reassigns ids to resolve collisions when ships are merged.

Two limits on it, both acceptable:

* Uniqueness is **within one ship**. Two separately built craft can hold the same `craftID`, so it
  is an editor identity only; flight keeps using `flightID`.
* `SanitizeCraftIDs` can reassign, so merging a subassembly can renumber parts. No worse than what
  the game does to its own references, and it does not happen during ordinary editing.

### Delta-v

`ShipConstruct.vesselDeltaV` is a `VesselDeltaV`, the same type as `Vessel.VesselDeltaV`, created by
`EditorLogic` through `VesselDeltaV.Create(ShipConstruct)`. It exposes `IsReady`, `GetStage(int)`
returning `DeltaVStageInfo`, `TotalDeltaVVac`/`ASL`/`Actual`, `TotalBurnTime`,
`GetSituationTotalDeltaV(DeltaVSituationOptions)`, and `EnableStockSimluation()` /
`DisableStockSimluation()` (KSP's spelling).

This is exactly what the `Stage` class added by
[PR #920](https://github.com/krpc/krpc/pull/920) already wraps, so the editor needs no new delta-v
math, only a second way to reach a `VesselDeltaV`.

The "actual" figures (`deltaVActual`, `thrustActual`, `TWRActual`, `ispActual`) are relative to a
situation the player picks in the stock delta-v app, held in the static
`DeltaVGlobals.DeltaVAppValues`:

| Field | Type | Meaning |
|---|---|---|
| `body` | `CelestialBody` | body whose gravity and atmosphere the figures assume |
| `altitude` | `double` | altitude on that body, feeding `atmPressure`/`atmDensity` |
| `situation` | `DeltaVSituationOptions` | `SeaLevel`, `Altitude` or `Vaccum` (KSP's spelling) |

Measured, not assumed (see [Measured behavior](#measured-behavior)): **`body` and `altitude` drive
the numbers; `situation` only selects which of the three columns is read out.** `DeltaVEngineInfo`
computes isp and thrust from `body` and the pressure implied by `altitude`, and
`DeltaVStageInfo.CalculateTWR` reads `body` for gravity. Setting `situation` to `Vaccum` at
altitude 0 leaves the actual figures at sea-level values; raising `altitude` to 70 km is what makes
them match vacuum. `body` also moves the *sea level* column, which is the selected body's sea
level, not Kerbin's.

Changes to these values do not take effect until the simulation is re-run:
`VesselDeltaV.SetCalcsDirty(bool resetPartCaches, bool syncListInstances = false)` is public and is
what the stock app's own `DeltaVAppSituation.UpdateVesselDeltaVValues` path amounts to.

## Design

### Entry point

```
SpaceCenter.Editor                  -> Editor          (GameScene.Editor)
Editor.Ship                         -> EditorShip      (nullable, pending the check below)
Editor.Facility                     -> EditorFacility
Editor.LoadCraft(directory, name)   -> void
```

`EditorFacility` already exists as a kRPC enum (`Services/EditorFacility.cs`), added for
`LaunchSite`, and is reused unchanged.

Whether `Ship` needs to be nullable at all depends on what a fresh editor holds; see
[Editor ship lifetime](#editor-ship-lifetime).

`EditorShip` carries what a `ShipConstruct` knows about itself:

| Member | Source |
|---|---|
| `Name`, `Description` | `shipName`, `shipDescription`, both settable |
| `Facility` | `shipFacility` |
| `Size` | `shipSize` |
| `Parts` | `Parts` object over the `ShipConstruct` |
| `Stages`, `StageAt`, `DecoupleStages`, `DecoupleStageAt` | as `Vessel` |
| `Mass`, `DryMass`, `Cost`, `CrewCapacity` | summed over parts |
| `DeltaV`, `VacuumDeltaV`, `SeaLevelDeltaV`, `BurnTime` | `vesselDeltaV` totals |

`Editor.LoadCraft` is worth having on its own terms, and it is also the only way the in-game tests
can get a known craft into the editor.

### Part identity

`Part` currently stores `partFlightId` and re-derives through `FlightGlobals.FindPartByID`
(`Services/Parts/Part.cs:24,55`). A part proxy created in the editor stores `craftID` instead and
resolves by scanning the editor ship's part list; a proxy created in flight keeps `flightID` and
`FindPartByID`. Two id kinds in one proxy, discriminated by which scene made it, because neither id
is usable in both scenes: `flightID` is 0 in the editor, and `craftID` is only unique within a
single ship.

**Not** a single id that follows a part from the editor into flight. `craftID` does survive launch
unchanged, so that correspondence is available to a client that wants it, but a proxy that silently
switched scenes would have to survive the ship being launched, reverted or reloaded, which is a
lifetime question this feature should not answer on its own.

This must not be done by capturing the `global::Part` reference. Re-deriving from an id is the
invariant the in-progress [object lifetime work](../object-lifetime.md) is built on, and capturing
Unity objects is the direct cause of [#885](https://github.com/krpc/krpc/issues/885),
[#764](https://github.com/krpc/krpc/issues/764) and
[#771](https://github.com/krpc/krpc/issues/771). The editor is a second reason to key on a stable
id, not a reason to abandon the rule.

Sequencing against that work matters: it is reworking the same lookup path, so the editor branch
should land on top of it rather than beside it.

### Parts over `IShipconstruct`

`Parts` stores a `Guid vesselId` and resolves through `FlightGlobalsExtensions.GetVesselById`.
Generalize it to hold either a vessel id or a marker for "the editor ship" (there is only ever one,
so no id is needed), resolving to an `IShipconstruct`.

| Members | Editor |
|---|---|
| `All`, `Root`, `WithName`, `WithTitle`, `WithTag`, `WithModule`, `InStage`, `InDecoupleStage`, `ModulesWithName`, and all 24 typed collections (`Engines`, `Decouplers`, …) | work, via `IShipconstruct.Parts` |
| `Controlling` | flight only, needs `GetReferenceTransformPart` |
| `InternalVessel` | flight only |

`Root` needs care: `Vessel.rootPart` has no `IShipconstruct` equivalent. `ShipConstruct.parts[0]` is
the root by KSP's own convention; walking `parent` links from any part is the safe form and is what
PR #788 does.

This replaces PR #788's `EditorParts`, a 406-line copy of `Parts`. The PR author reached the same
conclusion in the issue thread.

### Part member audit

`Part` has 86 RPC members. They fall into three groups, and every one must be classified before the
tree is exposed, or the editor gets `NullReferenceException`s instead of errors.

| Group | Members | Action |
|---|---|---|
| Static part data | `Name`, `Title`, `Config`, `Tag`, `Cost`, `Mass`, `DryMass`, `Massless`, `CrewCapacity`, `ImpactTolerance`, `Max(Skin)Temperature`, `Parent`, `Children`, `AxiallyAttached`, `RadiallyAttached`, `Stage`, `DecoupleStage`, `Modules`, the typed accessors | available in the editor |
| Needs `part.vessel` | `Vessel`, `FuelLinesTo`/`From`, `Resources` (flow-dependent; as built the flow worry was unfounded and phase 5 opened it, see [Resources](#resources)) | `GameScene.Flight` |
| Needs live physics | `Velocity`, `Position`, `CenterOfMass`, `BoundingBox`, `Direction`, `Rotation`, `Lift`, `Drag`, `MomentOfInertia`, `InertiaTensor`, `ReferenceFrame`, `CenterOfMassReferenceFrame`, `AddForce`, `InstantaneousForce`, `DynamicPressure`, `Shielded`, the eight `Thermal*` members, `Temperature`, `SkinTemperature` | `GameScene.Flight` (`part.rb` and `part.orbit` are null in the editor) |

`Highlighted`/`HighlightColor`/`Glow` go through `PartHighlightAddon`, a flight addon, and need
checking rather than assuming. The same audit is owed to the 24 typed part classes; `Engine.Thrust`
and friends are meaningless without a running engine, while `Engine.ThrustLimit` is exactly what
issue #263's commenter wanted from the editor.

### Stage delta-v

Generalize `Stage` the same way `Parts` is generalized: its stored source resolves to a
`VesselDeltaV`, from either a vessel id or the editor ship. Every existing member then works with no
other change, because they are all reads off `DeltaVStageInfo`
(`Services/Stage.cs:123-227`), and the existing `IsReady` guard
(`RequireBurnStage`, `Stage.cs:228`) already produces the right error when the simulation has not
run.

New API, with no flight equivalent, for the situation the actual figures assume:

```
Editor.DeltaVBody       -> CelestialBody   (get/set)
Editor.DeltaVAltitude   -> double          (get/set)
Editor.DeltaVSituation  -> DeltaVSituation (get/set: SeaLevel, Altitude, Vacuum)
```

mapped onto `DeltaVGlobals.DeltaVAppValues`. A new kRPC enum spells `Vacuum` correctly.

Each setter must call `SetCalcsDirty(true)` on the ship's `VesselDeltaV`, or the change has no
effect on anything read afterwards. `situation` is included for completeness with the stock app,
but it is `Body` and `Altitude` that a script actually wants: kRPC already exposes all three columns
as separate members (`DeltaV`, `VacuumDeltaV`, `SeaLevelDeltaV`), so nothing on our side needs the
column selector. Document it as affecting only the game's own readout.

Note these are global game state, not editor state: the same values back the delta-v app in flight,
and they persist across scene changes and across VAB/SPH. Exposing them on `Editor` is a scoping
choice, on the grounds that a hypothetical situation is only meaningful for a design. If they turn
out to matter in flight too, they move to `SpaceCenter` and `Editor` keeps aliases.

### Recalculation is asynchronous

Delta-v figures are produced by a coroutine, and `IsReady` goes false while it runs, after a craft
load and after every `SetCalcsDirty`. Measured: false for roughly 0.6 to 0.9 seconds after loading
an 81-part craft. So a script that changes the ship or the situation and immediately reads delta-v
will hit the existing "not been calculated yet" error rather than a stale value.

`RequireBurnStage` (`Stage.cs:228`) already throws exactly that, which is the correct floor. Whether
kRPC should additionally offer a wait, either by yielding server-side the way `ActiveVessel`'s
setter does or by exposing `Editor.DeltaVReady` for the client to poll, is a phase 4 decision.
Exposing the flag is the smaller change and is enough to make the wait writable in a script.

### Resources

PR #788 opens `Resources` to `GameScene.Editor`. Editor resource totals per stage are a reasonable
thing to want when sanity-checking delta-v, but `Resources` resolves both a vessel id and a part,
and its flow-mode members are flight concepts. Deferred to its own phase, after the tree and
delta-v land.

As built, the flow-mode worry was unfounded: `Density` and `FlowMode` are static lookups in
`PartResourceLibrary` that never involved a vessel, and `Enabled` reads and writes the flow state a
player sets in the editor. The vessel id and the part id are the only things that had to change.

### Out of scope

* Editing the ship: placing, removing, re-rooting or re-staging parts. A much larger surface than
  introspection, and none of it is asked for in #263.
* Subassemblies, the craft browser, and craft file manipulation beyond `LoadCraft`. Saving the
  vessel to its craft file stays out; launching it does not, see
  [Scene manipulation, reinstated](#scene-manipulation-reinstated).
* The other non-flight scenes (tracking station, astronaut complex). #263's thread mentions them;
  they share no mechanism with this work.

## Why not PR #788 as it stands

| What it does | Problem |
|---|---|
| `Part`, `Resource`, `Resources` capture `global::Part` references instead of ids | Reintroduces #885/#764/#771 and contradicts the object-lifetime design |
| `EditorParts` duplicates `Parts` (406 lines) | Diverges on every future change; the author proposed `IShipconstruct` instead |
| No member audit | `Part.Velocity` and the thermal members will `NullReferenceException` in the editor |
| No tests | See below; the harness cannot currently load a craft into the editor |
| `Editor.SwitchEditor`, `Editor.LaunchVessel` | Scene manipulation mixed into an introspection API. Reversed in phase 6, which builds both in a different shape, see [Scene manipulation, reinstated](#scene-manipulation-reinstated) |

The entry-point shape (`SpaceCenter.Editor` → ship → parts) is good and is kept.

## Phases

Each is independently mergeable.

| # | Phase | Content | Status |
|---|---|---|---|
| 1 | Entry point and harness | `SpaceCenter.Editor`, `EditorShip` scalars, `Editor.LoadCraft`; `krpctest` support for entering the editor with a named craft | built |
| 2 | Part identity | `Part` keyed on `craftID` in the editor and `flightID` in flight, resolved per scene. On top of the object-lifetime work | built, without the object-lifetime work |
| 3 | Part tree | `Parts` over `IShipconstruct`, `EditorShip.Parts`, full `Part` and typed-part member audit | built; typed-part audit inverted, see [As built](#as-built) |
| 4 | Stage delta-v | `Stage` over either delta-v source, `EditorShip.Stages` and totals, situation settings with forced recalculation | built |
| 5 | Resources | `Resources` in the editor, if phase 3's audit says it is coherent | built |
| 6 | Scene workflow | Switching between the editors by setting `KRPC.GameScene`, and `Editor.LaunchVessel` | built, added after phases 1-5, see [Scene manipulation, reinstated](#scene-manipulation-reinstated) |

## Scene manipulation, reinstated

Phases 1-5 kept scene manipulation out, and rejected PR #788's `SwitchEditor` and `LaunchVessel`
as "scene manipulation mixed into an introspection API". Phase 6 reverses that, on the argument
that introspection alone does not complete a workflow: a script that opens an editor, loads a
vessel and analyzes it has no way to act on the analysis, and a user who has just edited a vessel
by hand has no way to hand it to a script to check and fly. The two operations that close the loop
are switching editor and launching.

| PR #788 | As built | Why |
|---|---|---|
| `Editor.SwitchEditor()`, a new RPC that toggles | Setting `KRPC.GameScene` to `EditorVAB` or `EditorSPH` | The scene setter already accepted both editors, so a second way to change scene would have been redundant. Doing it exposed a bug that predates this work, see below. |
| `Editor.LaunchVessel(siteName)`, delegating to `EditorLogic.launchVessel` | `Editor.LaunchVessel(launchSite, crew, recover, flagUrl)`, saving to the auto-saved craft file and reusing `SpaceCenter.LaunchVessel`'s configuration, pre-flight checks and flight driver | Delegating to the game's own launch shows a dialog on a failed pre-flight check rather than reporting it, returns before the launch happens, and silently substitutes the default launch site for an invalid one. Reusing the existing path makes the two launch RPCs behave identically. |

Saving is deliberately not exposed. Writing the vessel to its own craft file is the one operation
here that destroys user data, and no workflow needs it: launching writes only the auto-saved craft
file, which is scratch space the game already overwrites on every launch.

### The editor switch was already broken

`KRPC.GameScene` accepted `EditorVAB` and `EditorSPH` from the start, and set either by calling
`EditorDriver.StartEditor`, which loads the editor scene. Requesting a scene load while the editor
scene is already the loaded one makes `FlightCamera`'s `onGameSceneLoadRequested` handler throw,
after which the flight camera cannot follow a vessel for the rest of the session. Present since
the scene became settable in 0.6.0, and unnoticed because nothing switched between the editors
directly: the scene test moved between them via the space center, and the damage only shows on the
next entry into flight.

Fixed by routing the editor-to-editor case through `EditorLogic.SwitchEditor`, which restarts the
editor in place instead of loading a scene, and carries the vessel across as the game's own switch
button does. An in-place restart never re-runs `Addon.Awake`, so the reported game scene is
refreshed from `GameEvents.onEditorRestart`, which fires once the editor being started is current.

The lesson for testing: both the switch tests and the launch tests passed against the broken
build. Only the game's log showed it, so the test asserts against the log as well.

## Testing

No editor test infrastructure exists today. Every existing SpaceCenter test class assumes flight.

**Harness.** `krpctest` can switch scenes and can stage craft files into a save
(`testcase.py:123`), but cannot load a craft into the editor. Phase 1 adds a helper, roughly
`cls.enter_editor("VAB", craft="Staging")`, built on `Editor.LoadCraft`, with teardown back to the
space center. Editor tests need no mods, so they group with the default game instance.

As built, `enter_editor` always goes via the space center, because switching straight from one
editor to the other with a craft loaded kills the game, and it waits for the editor to answer before
loading a craft into it. `leave_editor` returns to the space center.

**New test modules.**

| File | Covers |
|---|---|
| `test_editor.py` | loaded ship name/facility/mass/cost; VAB and SPH; `Facility` tracks the current editor after a VAB to SPH switch |
| `test_editor_parts.py` | tree, root, parent/child links, filters, typed collections; **cross-checked against the same craft launched**; flight-only members raise rather than crash |
| `test_editor_stage.py` | stage count and per-stage delta-v/TWR/thrust/isp/mass against the same craft in flight; changing body or altitude moves the actual figures, and does so only after the forced recalculation; reading during the recalculation window raises; decouple stages still throw |

A fourth module, `test_editor_resources.py`, came with phase 5: per-craft, per-part and per-stage
resource totals, flow state, and the same craft cross-checked against its launched self.

**Existing tests to extend.** `test_game_scene.py` for scoping in both directions: editor RPCs fail
in flight, `ActiveVessel` still fails in the editor. As built it only covers the first direction:
`ActiveVessel` is not scoped to flight and returns null in the editor, so there is nothing to
assert there.

**Cross-checking editor against flight is the valuable assertion here** and is what makes these
tests more than smoke tests: the same `.craft` file, inspected in the VAB and after launch, must
report the same tree and the same vacuum delta-v per stage. As built each module does this against
the craft it loads, rather than against the expectations `test_parts.py` already holds, so the two
sides of the comparison are always the same craft.

There is no test for a fresh editor. The editor keeps whatever craft it last held, so a test cannot
get one without a fresh game; the zero-part ship in the table above was measured by hand instead.

**Lifetime.** A part proxy obtained in the editor, then the ship reloaded or launched: decide
between throwing and following the part, and test whichever is chosen. Reloading the same craft is
the sharp case, since `craftID` makes the proxy keep resolving, to a part that is a different Unity
object than the one the client asked about.

**Not done.** The lifetime question above is unanswered and untested. As built the behaviour falls
out of the lookup rather than being chosen: a proxy whose `craftID` is still in the editor's craft
keeps resolving, so it follows the part across a reload of the same craft and silently refers to a
different Unity object; one whose `craftID` has gone raises. Worth settling on its own, alongside
the [object lifetime work](../object-lifetime.md), which is reworking the same lookup.

## As built

Where the implementation diverged from the design above:

| Design | As built | Why |
|---|---|---|
| `Editor.Ship` nullable, pending a check on a fresh editor | Not nullable | Measured: a first entry into the editor on a new save holds an empty `ShipConstruct`, named "Untitled Space Craft", with zero parts. There is no craft-less editor to report. |
| `Editor.LoadCraft` calls `EditorLogic.LoadShipFromFile` | Yields until the editor has looked ready for 60 frames in a row, calls `LoadShipFromFile`, then resets `EditorDriver.StartupBehaviour` | See [Loading a craft is fragile](#loading-a-craft-is-fragile). |
| `Editor.DeltaVReady` | `EditorShip.DeltaVReady` | The flag describes the craft's own simulation, and belongs with the totals it gates. |
| Phase 2 lands on top of the [object lifetime work](../object-lifetime.md) | Landed without it | That work is not merged. `Part` already re-derived from an id, so the change is confined to which id it stores and how it resolves, and does not touch the lookup path being reworked. The typed part classes still capture their `PartModule`, unchanged. |
| Phase 3's "full typed-part member audit" | Each typed part class defaults to `GameScene.Flight`; members that read or write the part's design are opened to the editor as well | Inverting the default means an unclassified member cannot reach the editor and cannot throw a `NullReferenceException` there. The opened set is deliberately conservative, covering the design-time members (`Engine.ThrustLimit` and its performance figures, `ControlSurface`'s axis and authority settings, `Decoupler.Impulse`, `ReactionWheel.MaxTorque`, and each class's `Part`) and leaving the rest flight-only until there is a reason to widen it. No existing client loses anything: these classes are only reachable through `Vessel.Parts`, which is already flight-only. |
| `Part.Mass` and `DryMass` as static part data | Same, but the underlying computation changed | Both read the part's rigidbody, which does not exist until physics is running, so they returned zero in the editor. They now fall back to the part's own mass fields. |
| Phase 5 conditional on phase 3's audit | Built, and the whole of `Resources` and `Resource` came with it | The audit found nothing in either class that needs a running vessel. Every member reads what a part can hold, not how it is being drawn on, and `Density` and `FlowMode` are library lookups that never touched the vessel. `Vessel.Resources` and `Vessel.ResourcesInDecoupleStage` stay flight-only because a vessel does. |

### Loading a craft is fragile

Three ways of driving a craft load over RPC were tried, in this order. Only the third survives.

| Approach | Result |
|---|---|
| `EditorLogic.LoadShipFromFile` on the frame the request arrives | The game dies, hard, about a second later, taking the log with it. It rebuilds the editor in place, and the second load in a session was reliably fatal. |
| `EditorDriver.StartAndLoadVessel`, which asks for an editor scene reload and lets the game defer it | Works in the VAB, but `HighLogic.LoadScene(EDITOR)` from the editor is not reliably honoured: entering the SPH and then loading a craft leaves the request unanswered, the craft's persistent id never changes, and the yielded RPC waits forever. The reload also restarts the kRPC server, which a client is holding a yielded call across. |
| `LoadShipFromFile`, but only after the editor has looked ready for 60 consecutive frames | Works in both editors, and across repeated loads. |

So the fatal part was never the in-place rebuild; it was rebuilding an editor that had not finished
starting up. The scene reports itself as an editor, and `EditorLogic.fetch.ship` is set, some way
before the editor is actually usable, so readiness has to be a settle window rather than a flag.

`LoadShipFromFile` also leaves `EditorDriver.StartupBehaviour` set to `LOAD_FROM_FILE`, which the
game never resets. Left alone, the next entry into either editor re-reads that file, springing a
craft on a client that did not ask for one - and, with an 81-part craft, killing the game on the way
back out to the space center. `Editor.LoadCraft` sets it back to `LOAD_FROM_CACHE`.

### One part reference, shared

`Part`, `Resource` and `Resources` all key on a part, and all had to learn the same thing: which
identifier to store and how to resolve it. That is a `PartId` value type, and each of the three
holds one rather than restating the rule.

### The situation settings, re-measured

The design's account of `DeltaVGlobals.DeltaVAppValues` holds up. Measured again through the built
API with `Staging.craft` in the VAB, sweeping one setting at a time and reading per-stage figures as
well as totals:

| Setting | Effect |
|---|---|
| `altitude` 0 to 70 km, over Kerbin | Specific impulse 280 to 320 s, total delta-v 2647 to 3038 m/s. The ends match the craft's sea-level and vacuum figures exactly, and the middle rises monotonically. |
| `situation` | Nothing. Identical figures under `SeaLevel`, `Altitude` and `Vaccum`. |
| `body` at altitude 0 | Kerbin isp 280 s, TWR 2.46; Duna 317 s, 9.29; Mun 320 s, 16.93; Eve 57 s, 0.30. Gravity moves TWR, atmosphere moves isp. |

The disassembly agrees. `DeltaVEngineInfo.CalculateISP` and `CalcThrustActual` each branch on the
scene: the flight branch reads live state, and the `LoadedSceneIsEditor` branch computes the actual
figures from `DeltaVAppValues.atmPressure` and `atmDensity`, which are `body.GetPressure(altitude)`
and the matching density. `situation` is never read by the simulation at all - every read site is a
UI class (`DeltaVAppSituation`, `DeltaVAppValues`, `StageGroup`, `StageManager`).

**The trap is a stale read**, and it is easy to mistake for the settings doing nothing.
`SetCalcsDirty` marks the simulation dirty, but `IsReady` stays true until the game gets round to
starting the run, so an RPC that sets one of these values and immediately reads a figure gets the
one from before the change. It comes back as exactly the previous answer rather than as anything
obviously wrong, which is what makes it convincing.

**So `EditorShip.DeltaVReady` has to account for a request the game has not picked up yet**, which
is the option this design picked over a server-side wait, on the grounds that the flag is the
smaller change. `EditorDeltaV` records the fixed time at which it asked for a re-run, and the flag
is false until the clock has moved past it as well as the game reporting ready and not running. One
fixed update is enough, because `VesselDeltaV.CheckDirtyAndRun` is called from `FixedUpdate` and
acts on the dirty flag immediately.

The setters return straight away, so a script can change body, altitude and situation together and
wait once, and the flag can be streamed. A server-side wait would have blocked everything else the
client had queued, and would have fixed only the changes made through kRPC, leaving the player's own
edits to be polled for - two contracts for one property.

The same stale read makes the whole-craft totals look as though they lag behind the per-stage
figures: a vacuum total of 1737 m/s, and then 0 m/s, against a per-stage sum of 3038 m/s, all with
the flag reading true. There is no separate settling problem, and the tests wait on the flag alone.

Flight-only, as the audit sets out: `Parts.Controlling`, `Part.Vessel`, `Part.Crew`,
`Part.AvailableSeats`, the fuel-line members, the thermal members, highlighting, and everything
positional.

## Measured behavior

Measured in KSP 1.12.5 through a scratch RPC on the SpaceCenter service, in the VAB of the sandbox
test save, with the 81-part `Staging.craft` from the SpaceCenter test fixtures. The probe was not
committed.

### Delta-v is ready without prompting

| Observation | Result |
|---|---|
| `DoStockSimulation` in a sandbox editor | already true, nothing to enable |
| `DeltaVGlobals.ready` | true |
| `vesselDeltaV` after entering the editor | non-null |
| `IsReady` after loading a craft | false for ~0.6s, `SimulationRunning` true, then true |
| `ActiveMode` | `Ship` |
| Stage figures | complete: 11 stages, per-stage vac/ASL/actual delta-v, TWR, thrust, isp, masses |

So kRPC needs neither `EnableStockSimluation` nor any other prod: there is no question of the
server switching stock simulation on as a side effect. The real constraint is the recalculation
window described above.

### Part ids

Same craft loaded twice, then undone, then launched, comparing all 81 parts:

| Operation | `craftID` | `persistentId` |
|---|---|---|
| reload the same craft file | identical | **all regenerated** |
| undo (`EditorLogic.RestoreState`) | identical | **all regenerated** |
| launch | identical | regenerated |
| uniqueness within the ship | 81 distinct, none zero | 81 distinct |

`persistentId` is therefore unusable as an editor part identity, despite being the id `EditorLogic`
is most visibly seen assigning. `craftID` is stable across every operation tested, including launch,
where all 81 editor `craftID`s reappeared on the flight vessel alongside freshly assigned, distinct,
non-zero `flightID`s.

The craft file confirms the mechanism: it stores `part = <name>_<craftID>` per part, and separately
a `persistentId` that the game *ignores on load in the editor*, generating a fresh one instead.

### Editor ship lifetime

Incidental findings, both of which affect the API's contract:

* The editor keeps the ship across a round trip through the space center, and **across VAB/SPH**:
  a craft loaded in the VAB was still present after switching to the SPH, with
  `ShipConstruct.shipFacility` then reporting `SPH`. So `EditorShip.Facility` reports the editor you
  are in, not where the craft was designed, and must be documented that way.
* `DeltaVGlobals.DeltaVAppValues` persisted across scene switches, holding the body and situation
  set several minutes earlier in a different editor.

Not observed: a genuinely empty editor. Every entry during the session inherited a ship. Whether
`EditorLogic.ship` is null or an empty `ShipConstruct` on first entry in a fresh game is still open,
and decides whether `Editor.Ship` needs to be nullable or can be a ship with zero parts. Phase 1
should check it on a new save; it is a small detail and blocks nothing else.

Checked during phase 1: an empty `ShipConstruct` named "Untitled Space Craft", with zero parts, so
`Editor.Ship` is not nullable. See [As built](#as-built).
