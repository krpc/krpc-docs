# Vessel physics range

**Status:** done — merged as [PR #987 "Add Vessel.PhysicsRange"](https://github.com/krpc/krpc/pull/987)
(2026-07-20). Historical design record.

Expose a per-vessel physics range over the SpaceCenter service, so a script can keep a specific
vessel loaded and off-rails beyond KSP's stock bubble without installing PhysicsRangeExtender.

## Motivation

Reported by a user who flies an upper stage under MechJeb control while the camera stays with
another vessel. PhysicsRangeExtender solves this globally — every vessel in the game gets an
extended bubble, which is both more physics load than needed and a well-known source of instability
(distant vessels held off-rails accumulate floating-point error and can be destroyed or flung).
The user only needs one vessel loaded past the limit, which KSP already supports per-vessel.

## What KSP provides

`Vessel.vesselRanges` is a public instance field of type `VesselRanges`. `VesselRanges` holds seven
public `VesselRanges.Situation` fields — `prelaunch`, `landed`, `splashed`, `flying`, `subOrbital`,
`orbit`, `escaping` — each with four public floats: `load`, `unload`, `pack`, `unpack`. There is
also `GetSituationRanges(Vessel.Situations)`, which maps `LANDED`, `SPLASHED`, `PRELAUNCH`,
`FLYING`, `SUB_ORBITAL` and `ESCAPING` to the like-named fields and sends everything else —
including `ORBITING` and **`DOCKED`** — to `orbit`.

Everything in this section was read from a `monodis` disassembly of the real
`Assembly-CSharp.dll`, not from the API stubs. Line references are to that disassembly.

### Two independent state machines

The four thresholds are not four points on one axis. They drive two separate booleans, evaluated by
different code in different Unity phases:

| state | meaning | driven by | phase | thresholds |
|-------|---------|-----------|-------|------------|
| `loaded` | real `Part` MonoBehaviours exist in the scene; otherwise the vessel is only a `ProtoVessel` snapshot plus an orbit | `Vessel.Update` | Update | `load`, `unload` |
| `packed` | "on rails": every part's rigidbody is `isKinematic` and the vessel is moved analytically by its `orbitDriver` rather than by PhysX | `OrbitPhysicsManager.LateUpdate` | LateUpdate | `pack`, `unpack` |

Both compare `Vector3.Distance(thisVessel, FlightGlobals.ActiveVessel)`, and both read the ranges of
**the vessel being tested**, taking only the position from the active vessel. The active vessel is
exempt from both distance tests. This is what makes a per-vessel override the right granularity for
this feature: raising the ranges on one vessel changes the treatment of that vessel and nothing
else.

The two states are coupled by the invariant **`!packed ⟹ loaded`**, defended at three points:

 * `Vessel.GoOffRails()` — the only writer of `packed = false` outside `Initialize` — returns
   immediately if `!loaded`.
 * `Vessel.Load()` calls `GoOnRails()` before `protoVessel.LoadObjects()`, so a vessel is
   **always** loaded-and-packed the moment it loads. Unpacking is a later, separate decision.
 * `Vessel.Unload()` calls `GoOnRails()` before `SetLoaded(false)`.

`loaded` has exactly one writer, `Vessel.SetLoaded(bool)`, called immediately after
`protoVessel.LoadObjects()` and immediately after every part has been destroyed and `parts.Clear()`
called. `packed`'s writers are `ProtoVessel.Load`, `Vessel.Initialize`, `GoOnRails` and
`GoOffRails`. Both are public fields with no property wrapper, so a mod can write them directly and
break the invariant; kRPC does not.

### What each threshold means

With `d` the distance to the active vessel:

 * **`load`** — an unloaded vessel instantiates its parts when `d < load` (strict).
 * **`unload`** — a loaded vessel destroys its parts when `d > unload` (strict). The `load`/`unload`
   gap is hysteresis around an expensive teardown/rebuild.
 * **`pack`** — a vessel goes on rails when `d > pack`.
 * **`unpack`** — a vessel comes off rails when `d < unpack`.

### Stock defaults

`VesselRanges..ctor`, read from the `ldc.r4` constants, in field order `load, unload, pack, unpack`:

| situation | load | unload | pack | unpack |
|-----------|------|--------|------|--------|
| `prelaunch` | 2250 | 2500 | 350 | 200 |
| `landed` | 2250 | 2500 | 350 | 200 |
| `splashed` | 2250 | 2500 | 350 | 200 |
| `flying` | 2250 | **22500** | **25000** | 2000 |
| `subOrbital` | 2250 | 15000 | 10000 | 200 |
| `orbit` | 2250 | 2500 | 350 | 200 |
| `escaping` | 2250 | 2500 | 350 | 200 |

Two things stand out.

**In orbit, `pack` (350) is far below `load` (2250).** The familiar "2.5 km bubble" is the *loading*
radius. A non-active vessel is on rails beyond 350 m and does not come off rails until it is inside
200 m. Between roughly 200 m and 2500 m the normal state is loaded-but-packed. The distance out to
which a non-active vessel can actually *fly* is therefore 200 m, not 2500 m — an order of magnitude
tighter than the number users quote, and the real constraint behind this feature request.

**In the `flying` row, `pack` (25000) exceeds `unload` (22500).** A flying vessel is unloaded before
the distance-based pack test can ever fire, so that `25000` is effectively dead for the stock
lifecycle; the vessel is packed by `Unload()` calling `GoOnRails()` instead. It only becomes live if
something raises `unload` past it — which this feature does.

### Why packed is useless for the requester's purpose

Being loaded is not enough. Read directly from IL:

 * **Engines produce exactly zero.** `ModuleEngines.TimeWarping()` returns true when `part.packed`,
   and `ModuleEngines.FixedUpdate` opens with
   `if (TimeWarping()) { finalThrust = 0f; return; }` — before `UpdateThrottle`,
   `UpdatePropellantStatus`, `ThrustUpdate` and `FXUpdate`. No thrust, no propellant draw, no
   throttle processing, no effects.
 * **Control inputs are silently discarded.** `Vessel.FeedInputFeed()` fires
   `OnPreAutopilotUpdate`, `OnAutopilotUpdate`, `OnPostAutopilotUpdate` and `OnFlyByWire` — so an
   autopilot mod's callbacks still run and still write a `FlightCtrlState` every frame — and then
   returns before `rootPart.propagateControlUpdate(ctrlState)` if `!loaded`, `packed`,
   `physicsHoldLock` or `!isControllable`. Nothing reaches the parts, with no warning.
   `GoOnRails()` additionally calls `ctrlState.Neutralize()`.
 * **Stock SAS does not tick.** `Vessel.Update` ends with
   `if (IsControllable && !packed) autopilot.Update()`.
 * **Forces are discarded.** `Part.Pack()` sets `rb.isKinematic = true`, so PhysX ignores
   `AddForceAtPosition`, RCS and aerodynamics. Position and velocity come from `orbitDriver`.
 * **PartModule `FixedUpdate`s still run.** `Part.Pack()` never touches `enabled`; each module opts
   out individually by reading `part.packed`. That `ModuleEngines.FixedUpdate` has to test it at all
   is the proof that Unity is still calling it.

So the state a remotely-piloted vessel needs is `loaded && !packed`, and `unpack` is the threshold
that gates it.

### Incidental: packed vessels in atmosphere are destroyed

`Vessel.CheckKill` destroys a vessel when it is `packed`, is not the active vessel, is not landed or
splashed, and `mainBody.GetPressure(altitude) > 1.0` — **unless** its squared distance to the active
vessel is below `pack²` (using `BestSituation`). Raising `pack` therefore widens the reprieve, so
this feature incidentally protects distant in-atmosphere craft rather than endangering them.

### `BestSituation`

`Vessel.BestSituation` is `(lastSituation == Situations.FLYING) ? lastSituation : situation`.
`lastSituation` is synced to `situation` at the tail of `updateSituation()`, which `Vessel.LateUpdate`
calls every frame. It is read in only two places: the **pack** threshold lookup in
`OrbitPhysicsManager.LateUpdate`, and `Vessel.CheckKill`. The **unpack** lookup in the same loop uses
the raw `situation` field. The apparent intent (inferred, not stated in IL) is sticky hysteresis
across the flying→sub-orbital transition, so the pack radius does not drop abruptly from 25000 to
10000 mid-ascent. Irrelevant to this feature, which sets every situation to the same value.

### No validation whatsoever

`VesselRanges.Situation` exposes four bare public floats. Both its constructors are nothing but
`stfld`s, and `Situation.Load(ConfigNode)` parses the four keys straight into the fields with no
try/catch. Nothing anywhere clamps the values, enforces `load < unload` or `unpack < pack`, or
checks for negatives or NaN. Both `Vessel.Update` comparisons use the `.un` branch variants, so a
NaN distance or NaN threshold silently freezes the state rather than throwing.

**There is a real thrash hazard if the ordering is inverted.** In `Vessel.Update` the load check is a
second `if` that re-reads `loaded`, not an `else`:

```
if (loaded)  { if (d > ranges(situation).unload) Unload(); }
if (!loaded) { if (d < ranges(situation).load)   Load();   }
```

With `load > unload`, a vessel in the gap calls `Unload()` and then `Load()` **in the same frame** —
destroying and re-instantiating every part, rebuilding `protoVessel`, and firing
`onVesselUnloaded`/`onVesselLoaded`/`onVesselGoOnRails` — every frame, indefinitely. Any value
kRPC writes must keep `load <= unload`.

The pack/unpack pair cannot thrash the same way: the pack branch `continue`s before the unpack check
is reached.

### `OrbitPhysicsManager.LateUpdate` in full

```
if (!FlightGlobals.ready || !started || FlightGlobals.overrideOrbit) return;
bool warping = (TimeWarp.WarpMode == HIGH) && (TimeWarp.CurrentRate > TimeWarp.MaxPhysicsRate);
Vessel active = FlightGlobals.ActiveVessel;

if (!FlightGlobals.warpDriveActive) {
    if (warping) { if (!active.packed) active.GoOnRails(); }
    else         { if (active.packed && !holdVesselUnpack) active.GoOffRails(); }
}

foreach (Vessel v in FlightGlobals.Vessels) {
    if (v == active || v == null || v.orbitDriver == null) continue;
    if (!FlightGlobals.warpDriveActive && warping && !v.packed) v.GoOnRails();   // no continue
    float d = Vector3.Distance(v.transform.position, active.transform.position);
    if (d > v.vesselRanges.GetSituationRanges(v.BestSituation).pack) {
        if (v.packed) continue;
        v.GoOnRails(); continue;
    }
    if (d >= v.vesselRanges.GetSituationRanges(v.situation).unpack) continue;
    if (!v.packed) continue;
    if (TimeWarp.CurrentRate > TimeWarp.MaxPhysicsRate) continue;   // strict; physics warp is OK
    if (holdVesselUnpack) continue;
    v.GoOffRails();
}
```

Points that matter here: there is no `loaded` check in the loop (`GoOffRails` self-guards); pack uses
`BestSituation` while unpack uses `situation`; unpacking is blocked by any time warp above the
physics rate and by `OrbitPhysicsManager.HoldVesselUnpack`, neither of which blocks packing.

### Lifetime — the reason this needs an addon

`Vessel.vesselRanges` is assigned in exactly two places, both in `Vessel.Awake()`: a deep copy of
`PhysicsGlobals.Instance.VesselRangesDefault` if `PhysicsGlobals.Instance` exists, otherwise a
freshly constructed `VesselRanges` with the defaults above. It is **not** persisted: `ProtoVessel`
never references it, and the only callers of `VesselRanges.Load`/`Save` are
`PhysicsGlobals.LoadDatabase`/`SaveDatabase`, which round-trip the *global default* through
Physics.cfg.

Nothing resets it on load, unload, pack or unpack — `Vessel.Load`, `Vessel.Unload`, `Vessel.Clean`,
`GoOnRails` and `GoOffRails` contain no store to the field. The effective reset is the Unity object
lifecycle: a scene change destroys the `Vessel` objects, and vessels rebuilt from their
`ProtoVessel` run `Awake` again and re-copy the global default.

So a one-shot setter would work within a flight scene and silently revert on the next scene change.
That is not an acceptable API, hence the re-applying addon below.

`PhysicsGlobals.VesselRangesDefault` is deliberately left alone. Writing it is what makes
PhysicsRangeExtender global; the static helpers `Vessel.loadDistance`/`Vessel.unloadDistance` write
it too (fanning out to all seven situations), so they are not usable here despite their names. The
per-vessel convenience properties `Vessel.distancePackThreshold` and friends have zero internal
callers and only cover subsets of the situations, so they are not used either.

`CometVessel.OnStart` is the one stock precedent for mutating a vessel's ranges in place, writing
`CometManager`'s override values into all seven situations.

## API

Deliberately minimal — one property, matching what was actually asked for.

```
[KRPCProperty (GameScene = GameScene.Flight)]
public float PhysicsRange { get; set; }
```

Reachable as `vessel.physics_range` in Python and the equivalent in the other clients.

### Setter

Sets, for all seven situations:

```
unload = pack   = value
load   = unpack = value * 0.9
```

Rationale for each choice:

 * **`pack = value`** is the point of the feature. Holding the vessel *loaded* is not enough — a
   loaded-but-packed vessel produces no thrust and ignores control input. `pack` is what keeps it in
   physics, and it is the stock value that is absurdly small (350 m in orbit).
 * **`unload = value`** because unloading forces packing, so leaving `unload` at its stock 2500
   would cap the effective physics range at 2500 regardless of `pack`.
 * **`load = unpack = 0.9 × value`** gives a 10% hysteresis band on both pairs. The ratio matches
   the stock 2250/2500 load-to-unload ratio. It is much tighter than the stock pack/unpack ratio
   (350/200, and 25000/2000 flying), which is acceptable because the band scales with the range: a
   50 km range gives 5 km of hysteresis, against stock orbit's 150 m.
 * `load == unpack` is deliberate and lands correctly rather than by luck. `Vessel.Update` runs in
   the Update phase and loads the vessel; `OrbitPhysicsManager.LateUpdate` runs later **in the same
   frame**, sees `loaded == true`, and unpacks it. No wasted frame, and `GoOffRails`'s `loaded`
   guard is satisfied.
 * `load (0.9v) < unload (v)` keeps clear of the same-frame load/unload thrash described above.

Setting every situation to the same value means no `VesselSituation` → `VesselRanges.Situation`
mapping is needed (so `Docked`, which has no counterpart, is a non-issue), and the range does not
change under the vessel as it transitions from `SubOrbital` to `Orbiting`.

Setting a value less than or equal to zero clears the override and restores the ranges the vessel
had when the override was first installed.

### Getter

Always reads the vessel's live `vesselRanges` — never a cached requested value — and returns

```
min(pack, unload)
```

for the vessel's current situation.

A vessel is packed when `d > pack` **or** when `d > unload` (because unloading forces `GoOnRails`),
so `min(pack, unload)` is the distance beyond which the vessel stops running physics — the honest
answer to "what is this vessel's physics range". For stock orbit it reports `min(350, 2500) = 350`,
not 2500; for stock flying, `min(25000, 22500) = 22500`. Reading `unload` alone would report 2500 in
orbit, which is exactly the misconception this feature exists to correct: the probe measured a
vessel at 1044 m reporting a 2500 m range while packed and unable to thrust.

Reading live state rather than the registry matters for a second reason. If the getter returned the
requested value, it would report success whenever the *registry entry* survived, whether or not the
values had actually been re-applied to the vessel — which would make the scene-change test
vacuous, since that is precisely the failure it is meant to catch. Reading through to the game
means a round-trip after a scene change proves re-application really happened.

Since the setter writes both `pack` and `unload` to `value`, an overridden vessel round-trips
exactly.

### Known sharp edge: the property can reduce a range

Stock `flying` has `unload = 22500` and `subOrbital` has `unload = 15000`. A user setting
`physics_range = 5000` — a reasonable-sounding "give me 5 km" — *reduces* the flying unload range by
4.5×. The name implies extension.

This is documented rather than clamped. Clamping each situation to `Math.Max(value, stockValue)`
would make the getter unable to report what was set, and would silently produce a vessel whose
behavior does not match its stated range. An explicit value that does what it says, including
downwards, is the lesser evil, and reducing a range is occasionally what a caller wants.

### Rejected alternatives

A faithful `VesselRanges`/`Situation` object tree — seven sub-objects with four settable floats
each — is the complete mapping, but 28 settable members and two new `KRPCClass`es for a request that
is "let me keep this one vessel loaded". `[KRPCStruct]` would be the natural modeling tool and is
not implemented (see [`../protocol/struct-types.md`](../protocol/struct-types.md)). Neither is foreclosed: the full object tree can be
added later alongside this property, which would then be documented as the convenience shortcut it
is. Anyone needing stock's asymmetric pack/unpack ratios, or a different range per situation, needs
that tree.

**Centering the hysteresis band on the requested range** — `pack = unload = 1.05 × R` and
`load = unpack = 0.95 × R`, so the range is the middle of the band rather than its outer edge — was
considered and rejected. It is arguably the simpler mental model, but it splits the one number into
two different meanings: `R` would no longer be the distance at which physics stops, so the getter
could not return `min(pack, unload)` without reading back `1.05 × R` and drifting upward on repeated
set-read-set. Preserving the round-trip would mean defining the getter as the midpoint of the band,
`(leaves + rejoins) / 2`, which reads sensibly for a range kRPC set but poorly for the stock
defaults, whose bands are wildly asymmetric — stock `flying` would report about 12250 for a vessel
that really does keep simulating out to 22500.

Anchoring the range to the outer edge keeps `R` meaning exactly one thing: it is simultaneously the
distance at which the vessel stops simulating and the value read back, and the hysteresis is an
implementation detail below it.

## Persistence

A static registry in a new `VesselPhysicsRangeAddon`, keyed by vessel `Guid` (not by the `Vessel`
object, which does not survive a scene change), holding the requested range and the vessel's
original `VesselRanges` for restoration.

The addon is `[KSPAddon (KSPAddon.Startup.Flight, false)]`, and re-applies every registered override
from `FixedUpdate`, to whichever of the registered vessels are currently in `FlightGlobals.Vessels`,
once `FlightGlobals.ready`. Re-application is periodic rather than driven by
`GameEvents.onVesselLoaded`, because the values must be restored after any `Vessel.Awake` —
including vessels rebuilt from `ProtoVessel` mid-scene as they come back into loading range — and a
periodic write is both cheaper to reason about than getting the event set exactly right, and what
PhysicsRangeExtender itself does. The registry is small (one entry per vessel a script has touched),
so the per-tick cost is a handful of float writes. Writes go into the existing per-vessel
`Situation` objects rather than replacing `vesselRanges` wholesale, so that a reference held by
another mod stays valid.

Scope of persistence: the override survives scene changes and vessel load/unload cycles for the
lifetime of the KSP process. It is **not** written to the save file, so it does not survive quitting
the game — consistent with KSP not persisting `vesselRanges` itself.

Entries are not pruned when a vessel is destroyed. `FlightGlobals.Vessels` is the only cheap
liveness signal available, and treating absence from it as "destroyed" risks discarding a live
override during a scene load; `GameEvents.onVesselDestroy` fires on scene unload too, so it does
not distinguish a crash from a scene change. Since an entry is a `Guid`, a float and a
`VesselRanges`, and the registry is bounded by the number of vessels a script has touched, leaving
dead entries in place is preferable to silently losing a live one.

### Not client-owned

The existing `ClientOwnedOverrides`/`ClientCleanupAddon` machinery in `server/src/Utils/` is the
closest precedent, and the addon is written in the same shape, but this override is deliberately
**not** client-owned and is **not** released on client disconnect or on scene change:

 * Releasing on disconnect would drop a distant vessel back to a 350 m physics bubble the moment a
   script exits or drops its connection, packing it onto rails mid-burn. Losing a craft as a side
   effect of a script disconnecting is a worse failure than leaking an override.
 * `ClientCleanupAddon` clears its collections in `Awake`/`OnDestroy` precisely to survive nothing
   across scenes, which is the opposite of what is wanted here.

Consequently this is one of the few pieces of kRPC state a client can set and not have cleaned up
for it. The escape hatch is setting the property to zero, and the whole registry is discarded when
the game exits. This is called out in the property's documentation. If leaked overrides become a
problem, a read-only collection of currently-overridden vessels on `SpaceCenter` is the cheap fix.

## Cheat status

Extending the physics bubble is gameplay-affecting in the same family as issue #145 (a DebugTools
service covering physics range among other things) and the open external PR #826. It is not a cheat
in the `CheatOptions` sense — no game rule is bypassed, and the same knob is reachable in stock via
Physics.cfg and by any number of mods — so it lands on `Vessel` in SpaceCenter rather than waiting
on a DebugTools service. If a DebugTools service later materializes, this property does not need to
move; it is per-vessel configuration, not a debug action.

## Verification

The analysis above is read from IL. All of it that this design depends on was then checked against
the running game, using `Multi.craft` undocked into two vessels with the active vessel teleported
along its orbit to place the other at chosen distances.

The measurements below came from throwaway probe scripts, not from the committed tests. The probes
swept threshold ladders and drifted the vessels apart under RCS to find numbers; the tests that
shipped assert the feature's behavior with wide margins and do not attempt to measure stock KSP's
constants. See "Testing" for what is actually in the suite.

### Method

Both halves of `Multi.craft` are undocked into two vessels in a 100 km circular Kerbin orbit, and
the active vessel is teleported along that orbit to place the other one at chosen distances.

Two properties of the setup had to be worked around, and both are worth recording because they will
bite anyone writing a similar test:

 * **A circular equatorial orbit is degenerate in its angles.** After `SetCircularOrbit` the vessel
   reports a non-zero `longitudeOfAscendingNode` and `argumentOfPeriapsis` (measured: 2.69 rad and
   2.23 rad) with `meanAnomalyAtEpoch` compensating. Rebuilding the orbit with those angles zeroed
   but the anomaly kept moves the vessel about 72° around the orbit — 880 km. The probe therefore
   does not reconstruct the phase from the other vessel's elements; it measures it, by placing the
   active vessel at an arbitrary anomaly, inverting the chord
   `d = 2a·sin(|Δ|/2)` for `|Δ|`, and resolving the sign with a second placement.
 * **Teleporting re-packs the vessel.** `PrepTeleport` puts vessels on rails, and
   `OrbitPhysicsManager.HoldVesselUnpack` blocks unpacking for a countdown of physics frames
   afterwards. Every teleport-based reading therefore observes the *unpack* threshold as the vessel
   comes back off rails, and can never observe the *pack* threshold. Measuring `pack` requires
   continuous motion, so a separate probe drifts the two vessels apart under RCS and samples until
   the transition.

Distances are measured center-of-mass to center-of-mass, while KSP compares
`vesselTransform.position`; on this craft that is a consistent offset of roughly 6 m, which is why
the brackets below sit slightly low.

### In-game results

Thresholds, as brackets between the last and first sample either side of each transition:

| threshold | expected | measured |
|-----------|----------|----------|
| stock `unpack` (orbit) | 200 | 188 – 234 |
| stock `pack` (orbit) | 350 | **341.6**, **339.5** (drift probe, two runs) |
| stock `load` (orbit) | 2250 | 2044 – 2244 |
| stock `unload` (orbit) | 2500 | 2131 – 2530 |
| `unpack` with `physics_range = 5000` | 4500 | 4269 – 4668 |
| `unload` with `physics_range = 5000` | 5000 | 4868 – 5468 |

The last two confirm the setter's mapping directly, including the 0.9 hysteresis factor.

The control probe is the decisive one. The same vessel, at the same distance, differing only in
whether a physics range was set:

| | stock, 1044 m | `physics_range = 5000`, 1089 m |
|---|---|---|
| `loaded` | `True` | `True` |
| `packed` | `True` | `False` |
| `control.state` | `full` | `full` |
| orbital speed after 5 s of full RCS | **+0.0001 m/s** | **−1.1347 m/s** |

This confirms the IL reading of `FeedInputFeed` and `ModuleEngines.TimeWarping` in the way that
matters: a packed vessel accepts every control RPC, reports itself fully controllable, and does
nothing at all. **`Control.State` is not a usable signal for whether commands will take effect** —
only `Packed` is.

Also confirmed across roughly forty samples: the loaded-but-packed state is the normal one at ~1 km
in orbit; the invariant `!packed ⟹ loaded` never broke; and an override held across nine teleports
and repeated load/unload cycles.

### Persistence across a scene change

Tested on the active vessel, which is the one vessel guaranteed to survive the round trip. The
first attempt used the undocked second vessel and failed because that vessel no longer existed
after returning to flight — `GetVesselById` threw. That is KSP's own debris auto-clean
(`Vessel.Update` calls `Clean()` on an unloaded auto-clean vessel when
`HighLogic.CurrentGame.CurrenciesAvailable`), not a defect in this feature, but it is a good
reminder that a vessel a script holds a handle to can be deleted by the game.

Flight → Space Center → Flight, with the getter reading live state throughout:

```
stock physics_range = 350.0
after setting       = 5000.0
after scene change  = 5000.0
after clearing      = 350.0
```

Since a scene change destroys the `Vessel` objects and the rebuilt ones re-copy
`PhysicsGlobals.VesselRangesDefault` in `Awake`, reading 5000 afterwards is direct evidence that the
addon's `FixedUpdate` re-application works. This is the case the addon exists for.

Note that an unload/reload cycle alone would *not* have exercised it: `Vessel.Unload` destroys the
parts but not the `Vessel` MonoBehaviour, so `Awake` does not re-run and `vesselRanges` survives
untouched. Only a scene change rebuilds the object.

## Testing

Headless: none meaningful — the thresholds are only consumed by `Vessel.Update` and
`OrbitPhysicsManager.LateUpdate` in a flight scene.

In-game, in `service/SpaceCenter/test/test_vessel.py`: round-trip, default read, and clear on the
active vessel — cheap, and covers the API surface.

The behavioral tests live in `service/SpaceCenter/test/test_vessel_physics_range.py`, in two
classes so the expensive two-vessel setup is paid once:

 * `TestVesselPhysicsRange` — undocks `Multi.craft` and teleports the active vessel to place the
   other one. Covers the default reading the pack distance rather than the unload distance; set and
   clear surviving the addon's re-application; a stock vessel being loaded-but-packed at 1 km; the
   headline case (same vessel, same distance, packed and inert versus unpacked and thrusting under
   RCS); and the raised thresholds, including a vessel coming back inside the range after having
   unloaded.
 * `TestVesselPhysicsRangeSceneChange` — a Flight → Space Center → Flight round trip on the active
   vessel, which is the case the re-applying addon exists for.

The fine-grained threshold ladders and the RCS-drift measurement of the `pack` distance that
produced the numbers in this document are deliberately **not** in the suite. They measure stock
KSP's own constants rather than anything kRPC controls, they need tight margins to be meaningful,
and they are slow. Their results are recorded above instead.

Assertions use wide margins — 1 km against a 350 m pack distance, 3 km and 7.5 km against a 5 km
range — so they do not depend on the placement accuracy of the teleport or on the roughly 6 m
difference between the center-of-mass distance the test measures and the transform distance the
game compares.

## Documentation

The property's XML docs cover three things beyond what it does, all of them user-visible surprises:

 * that reading it with no range set reports the game's default, which is much shorter than the
   distance at which the vessel unloads, and that a vessel on rails produces no thrust and ignores
   control input while still appearing controllable;
 * the 10% margin below the range, so that a vessel rejoining the simulation at 90% of the set
   distance does not look like a bug;
 * that the range applies in every situation and so can *shorten* the range of a vessel flying in
   atmosphere, whose stock default is 22.5 km.

The wording deliberately avoids `pack`/`unpack`/`load`/`unload`, saying "leaves the simulation" and
"rejoins it" instead. Those are KSP-internal concepts that kRPC does not otherwise expose — `Loaded`
and `Packed` are the only trace of them in the API — and the terms are not in
`doc/src/dictionary.txt`.

## Changelog

`service/SpaceCenter/CHANGES.txt`, under v0.6.0: a single additive entry for
`Vessel.PhysicsRange`, placed next to the existing `Vessel.Loaded`/`Vessel.Packed` entry. No
`**Breaking:**` marker.

It was committed together with the implementation rather than in a separate pre-merge commit, at the
maintainer's request, so it is more exposed than usual to a conflict on rebase if another branch
touches the v0.6.0 section first.
