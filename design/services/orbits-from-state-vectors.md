# Orbits from state vectors, and reference frames that coast

**Status:** in progress. Phases 1 to 3 are implemented and verified in game; no PR opened and no
issue filed yet, one should be filed. Where the implementation departed from what is proposed
below, the section says so and
[Departures from the design](#departures-from-the-design) collects them.

Let a script construct an orbit, from an initial position and velocity or from orbital elements, and
derive reference frames from it whose origin then coasts under gravity. This gives a frame that
tracks where a vessel *would* have travelled had it existed, without that vessel existing.

## Motivation

Every reference frame kRPC offers is attached to a live game object: a vessel, part, docking port,
maneuver node, thruster or celestial body. A user who wants an inertial frame today picks a vessel
that never thrusts and uses its orbital frame. That works, but the vessel has to exist, has to stay
unpowered, and cannot be placed where the user wants the frame to be.

"Inertial" here means **free-fall**, not constant-velocity. The frame follows a conic under gravity,
which is what a coasting vessel does. A straight-line frame diverges from a real vessel within
seconds and is not what the use case asks for.

Prior art:

| Issue | Outcome |
| --- | --- |
| [#252](https://github.com/krpc/krpc/issues/252) "Custom reference frames" | Closed 2016. Produced `ReferenceFrame.CreateRelative` and `CreateHybrid` — a frame offset by a *fixed* position, rotation, velocity and angular velocity, arbitrarily nestable. `CreateRelative` already takes a velocity offset, but its origin is a fixed offset from the parent, so the velocity never integrates into the position. Nothing drifts. |
| [#639](https://github.com/krpc/krpc/issues/639), [#823](https://github.com/krpc/krpc/issues/823) | Closed bugs on hybrid-frame velocity and a missing Coriolis term. Evidence that the velocity and angular-velocity semantics of composed frames are already a place users get lost, so a new frame type needs its four quantities spelled out. |

## Feasibility: no fake vessel is needed

The obvious worry is that simulating a coasting vessel needs a vessel to simulate. It does not.

- **A kRPC `ReferenceFrame` is a pure computation, not a game object.** It has no physics and needs
  no `Transform`. The `Maneuver` frame already proves this: it is positioned purely by evaluating an
  orbit at a UT (`service/SpaceCenter/src/Services/ReferenceFrame.cs`, `Position`), and its
  `Transform` property deliberately throws.
- **KSP's `Orbit` does analytic Keplerian propagation standalone**, with no `Vessel`, no
  `OrbitDriver` and no `PatchedConicSolver` attached. `service/Debug/src/Debug.cs` already builds a
  throwaway `new global::Orbit()` from state vectors to read its elements back out.

So the whole feature is arithmetic on an `Orbit` object that no vessel owns.

## What KSP provides

Read from a `monodis` disassembly of the real `Assembly-CSharp.dll`, not from the API stubs.

| Finding | Consequence |
| --- | --- |
| `Orbit.UpdateFromStateVectors(pos, vel, refBody, UT)` runs both vectors through `Planetarium.CelestialFrame.LocalToWorld`, then calls `UpdateFromFixedVectors` | Its inputs are **body-relative**, in KSP's internal `xzy` ordering (`.SwapYZ()`) |
| Both in-game callers, `SpawnCometFragment` and `GetProtoVesselNode`, pass `orbit.pos` and `orbit.vel`; and `Orbit.GetRelativeVel()` is literally `vel.xzy` | Confirms `vel` is the body-relative orbital velocity, not an absolute one |
| Both callers call `orbit.Init()` immediately afterwards | `Init()` populates `meanMotion`, `meanAnomaly`, `ObT`, `ObTAtEpoch`, `period`, `eccVec`, `h` and `an` — everything propagation reads. `Debug.cs` omits it only because it reads elements straight back out and never propagates |
| `Init()` does **not** touch `UTsoi`, `nextPatch` or `patchEndTransition` | A standalone orbit is a single conic, and the sphere-of-influence members degrade to "no change" on their own |
| `getPositionAtUT(UT)` → `getPositionAtT(T)` = `referenceBody.position` (the body's **current** world position) + the relative position at `T` | Automatically floating-origin safe, and consistent with how the service already uses it. Contrast `getTruePositionAtUT`, which anchors on the body's position *at that UT* |
| `Orbit.GetVel()` is `GetFrameVel()` minus the **active vessel's** orbitDriver frame velocity | Every world velocity in the service carries a common Krakensbane offset, which cancels whenever two of them are differenced |
| `GetOrbitalStateVectorsAtUT(UT, out pos, out vel)` exists | Position and velocity in one call, if a caller wants both |
| `UTsoi`, `nextPatch`, `period` and `epoch` are all public fields | A standalone orbit can be explicitly marked as having no patch |
| `PatchedConics.CalculatePatch` is a **public static delegate** taking plain `Orbit` objects, no vessel, and is present in the `@ksp` stub assembly the mod compiles against | Sphere-of-influence patching is reachable in a later phase, still with no fake vessel |

## Proposed API

Make `SpaceCenter.Orbit` constructible from state vectors, and hang the reference frames off `Orbit`.

Reusing `Orbit` rather than adding a new class means a constructed orbit gets apoapsis, periapsis,
period, `PositionAt` and closest-approach-to-a-target for free, and adds no class to the API — so no
new `doc/api/space-center/*.tmpl` is needed, since `orbit.tmpl` renders the whole class and picks up
new members on its own.

### `Orbit.CreateFromPositionAndVelocity`

A static `[KRPCMethod]`, alongside the existing static `ReferencePlaneNormal` and
`ReferencePlaneDirection`, and mirroring the `ReferenceFrame.CreateRelative` / `CreateHybrid`
factory precedent.

```csharp
[KRPCMethod]
public static Orbit CreateFromPositionAndVelocity (
    CelestialBody body, Tuple3 position, Tuple3 velocity, double ut,
    ReferenceFrame referenceFrame = null)
```

`referenceFrame` defaults to `body.NonRotatingReferenceFrame`.

> **Departed from the design.** This was proposed as `..., ReferenceFrame referenceFrame = null,
> double ut = double.NaN)`, with `NaN` meaning the current universal time, on the grounds that
> `NaN`-as-unset is already the idiom in `Orbit.TimeToSOIChange`. That reads well in C# but does not
> survive client generation: a `double` default falls through to `str(value)` in every language
> backend (`tools/krpctools/krpctools/lang/cpp.py`, and the same in `csharp.py` and `java.py`), which
> writes the bare literal `nan` into the generated stubs and does not compile. `NaN` is only an idiom
> for a *returned* value, which is never rendered as a literal. So `ut` is required, and moves ahead
> of the optional `referenceFrame`.

```csharp
var worldPosition = frame.PositionToWorldSpace (p);
var worldVelocity = frame.VelocityToWorldSpace (p, v);
var relativePosition = worldPosition - internalBody.position;
var relativeVelocity = worldVelocity - internalBody.GetWorldVelocity ();

var orbit = new global::Orbit ();
orbit.UpdateFromStateVectors (
    relativePosition.SwapYZ (), relativeVelocity.SwapYZ (), internalBody, ut);
orbit.Init ();
orbit.UpdateFromUT (ut);
orbit.UTsoi = -1;
```

Each line is backed by a row of the table above. `GetWorldVelocity` is in
`service/SpaceCenter/src/ExtensionMethods/CelestialBodyExtensions.cs`.

> **Added during implementation.** The `UpdateFromUT (ut)` call is not in the design. Without it a
> constructed orbit reports `Orbit.Speed` as **zero**: `UpdateFromFixedVectors` fills in `radius`,
> `trueAnomaly`, `altitude`, `timeToAp`, `timeToPe` and `orbitalEnergy`, but not `orbitalSpeed`, and
> nothing steps the orbit afterwards because no object is following it. `UpdateFromUT` sets the whole
> instantaneous state together, so the members that say where the orbit has got to are right at `ut`
> rather than partly filled. They then stay at `ut`, which the RPC documents; the reference frames
> and the `...At (ut)` members are what follow the orbit as time passes.

Validation: null arguments; a zero-magnitude relative position; a non-finite `semiMajorAxis` or
`eccentricity` after `Init()`. `Debug.cs` already records why a NaN conic is worth guarding against
— the patched-conic solver fills with NaN and takes down the flight scene.

No `GameScene` restriction, matching `Orbit`, which carries none. Propagation needs only
`Planetarium` and the body.

### `Orbit.CreateFromOrbitalElements`

> **Added after the design.** Not proposed originally. It arrived once the pair had to be named
> together: an orbit stated as elements is the other half of the same feature, and naming the
> position-and-velocity form without a sibling in view would have spent the obvious short name on it.

The counterpart, stating the same conic the other way round. KSP has a constructor for exactly this
shape, read from the disassembly:

```
Orbit(double inc, double e, double sma, double lan, double argPe, double mEp, double t,
      CelestialBody body)  ->  SetOrbit(...)
```

| Finding | Consequence |
| --- | --- |
| `SetOrbit` assigns the seven fields and then calls `Init()` itself | Unlike the state-vector path, no explicit `Init()` is needed. `UpdateFromUT(epoch)` and `UTsoi = -1` still are, for the same reasons |
| `SetOrbit` writes `inc`, `lan` and `argPe` straight into `Orbit.inclination`, `Orbit.LAN` and `Orbit.argumentOfPeriapsis`, which the service getters run through `ToRadians` | The game holds those three in **degrees**; the RPC takes radians and converts, so it round-trips against the getters |
| `mEp` goes into `meanAnomalyAtEpoch`, which `Init()` divides by `meanMotion` (rad/s) to get `ObTAtEpoch`; the service getter returns it unconverted | The mean anomaly is in **radians** on both sides, so it is the one angle not converted |
| `getObtAtUT(UT)` computes from `UT - epoch` | `epoch` is a **universal time**, not an offset. `Orbit.Epoch` documented it as "the time since the epoch", which is wrong and would have contradicted the new parameter; corrected in the same change |

```csharp
[KRPCMethod]
public static Orbit CreateFromOrbitalElements (
    CelestialBody body, double semiMajorAxis, double eccentricity,
    double inclination, double longitudeOfAscendingNode,
    double argumentOfPeriapsis, double meanAnomalyAtEpoch, double epoch)
```

Validation is stricter than the state-vector form, because elements that do not describe a conic can
be stated directly rather than only arrived at: a null body, any non-finite element, a negative
eccentricity, an eccentricity of exactly one (a parabola, which has no semi-major axis to give), and
a semi-major axis whose sign disagrees with the eccentricity — an ellipse needs a positive one and a
hyperbola a negative one. Getting this wrong is what `Debug.cs` warns about: a NaN conic reaching the
patched-conic solver takes down the flight scene.

### `Orbit.VelocityAt`

`Orbit.PositionAt(ut, referenceFrame)` exists with no velocity counterpart. Add one. Useful on its
own, independent of everything else here.

```csharp
var worldVelocity =
    InternalOrbit.getOrbitalVelocityAtUT (ut).SwapYZ () +
    InternalOrbit.referenceBody.GetWorldVelocity ();
return referenceFrame.VelocityFromWorldSpace (
    InternalOrbit.getPositionAtUT (ut), worldVelocity).ToTuple ();
```

> **Departed from the design.** This was proposed as "the pattern already proven in
> `ClosestApproach.cs`", reading the world velocity as `GetFrameVelAtUT(ut).SwapYZ()`. **That pattern
> is wrong, and the design should not have recommended it.** `GetFrameVelAtUT` is an *absolute*
> velocity, while every world velocity a reference frame is built from comes from `Orbit.GetVel()`,
> which subtracts the active vessel's orbit driver frame velocity. Feeding one into
> `VelocityFromWorldSpace` leaves that offset in the answer: measured in game it was wrong by
> 9284 m/s, Kerbin's speed around the Sun, for an orbit around Kerbin. Body-relative orbital velocity
> plus the body's own `GetWorldVelocity()` is the correct form, and is what `ReferenceFrame.Velocity`
> already does for the maneuver node frames.
>
> This is not only a defect in the design. `ClosestApproach.Velocity` and
> `ClosestApproach.TargetVelocity` are wrong in the same way in shipped code, and have been since
> they were added. `ClosestApproach.RelativeVelocity` differences two of them, so the offset cancels
> and it is correct, which is why the tests never caught it. Fixed separately, on the
> `fix-closest-approach-velocity` branch, which follows this one as its own pull request.

### Two new reference frame types

Added to `ReferenceFrameType` and to each switch in `ReferenceFrame`, mirroring the existing
`Maneuver` / `ManeuverOrbital` pair.

| | `OrbitNonRotating` | `OrbitOrbital` |
| --- | --- | --- |
| Exposed as | `Orbit.ReferenceFrame` | `Orbit.OrbitalReferenceFrame` |
| `Position` | `getPositionAtUT (now)` | same |
| `Velocity` | `getOrbitalVelocityAtUT (now).SwapYZ () + referenceBody.GetWorldVelocity ()` | same |
| `Up` (y axis) | `Planetarium.up` | `getOrbitalVelocityAtUT (now).SwapYZ ()` |
| `Forward` (z axis) | `Planetarium.forward` | `GetOrbitNormal ().SwapYZ ()` |
| `AngularVelocity` | `Vector3d.zero` | `Cross (r, v) / r.sqrMagnitude` |
| `Transform` | throws, in an arm of its own | same |

`Velocity` is the `Maneuver` case verbatim with `ut = now`. `OrbitOrbital`'s `AngularVelocity` is
the `VesselOrbital` case; it reads `r` and `v` straight off the orbit with
`getRelativePositionAtUT` and `getOrbitalVelocityAtUT`, which are already body-relative, rather than
differencing against `referenceBody` as the design put it.

The frames are constructed by `ReferenceFrame.NonRotating (Orbit)` and
`ReferenceFrame.Orbital (Orbit)`, named after the frame types and overloading the existing
`NonRotating` and `Orbital` factories. `ReferenceFrame` gains an `Orbit` field, compared in `Equals`
and mixed into `GetHashCode` alongside the other things a frame can be named against.

`Transform` throws for these as it does for the maneuver frames, but nothing can observe it: it has
no callers anywhere in the tree and is not a `[KRPCProperty]`, so no client can reach it. The arm is
there for the C# surface and is untested for that reason.

Anything else a user wants — the coasting origin with a vessel's orientation, say — composes from
these with `CreateHybrid`, which is what that RPC is for.

## Decisions

### The maneuver frame's offset correction does not apply

The `Maneuver` frame corrects its orbit position by `vesselPos - vesselOrbitPos`. That correction is
deliberate — see [`todo-fixme-sweep.md`](../todo-fixme-sweep.md), which records that `getPositionAtUT`
anchors on the body's *current* position, so orbit space and transform space genuinely differ by a
residual, and that the offset is measured on the node's own vessel.

A constructed orbit has no transform position. It **is** its orbit, so there is nothing to correct
toward, and no correction is applied.

The consequence matters and must be documented: an orbit built from a live vessel's state sits at
that vessel's **orbit** position, not its **transform** position, and the two differ by metres. Tests
must compare against `vessel.orbit.position_at(...)`, never `vessel.position(...)`.

### The frames land on every `Orbit`

Including a real vessel's and a celestial body's. That is a small bonus, and it means
`vessel.orbit.reference_frame` and `vessel.orbital_reference_frame` are close but not identical, for
exactly the reason above. Both doc comments should say so.

### Object lifetime

`Orbit.Equals` is reference equality on `InternalOrbit`, so every `Orbit.CreateFromPositionAndVelocity` call
yields a distinct `Orbit` and distinct frames, and each is retained for the server's lifetime —
`ObjectStore` is cleared only when the last server stops. A script constructing an orbit per tick
leaks steadily.

This is the problem [`object-lifetime.md`](../object-lifetime.md) tracks. It now carries the case
under [constructed orbits](../object-lifetime.md#constructed-orbits), in phase 8, alongside `Force`.
The retention belongs in the `Orbit.CreateFromPositionAndVelocity` and
`Orbit.CreateFromOrbitalElements` doc comments meanwhile, so it is not a surprise.

**Tying the orbits to the client that made them is the right model, and it does not work today.**
Scoping it to constructed orbits is easy and correct — `ownerVessel`, `ownerBody` and `ownerNode`
are all null for one, and orbits read off a vessel or body dedupe on `InternalOrbit` and are already
bounded. The obstacle is underneath: `ClientOwnedObjects` releases the *game-side* resource, and
`ObjectStore.RemoveInstance` has **no production caller anywhere in the tree**. For a drawing that
frees the `GameObject` and leaves a small entry behind; for a constructed orbit the entry is the
whole cost, so a collection on its own would release nothing. Nor can a service do it directly:
`ObjectStore` is `internal` to the core assembly with no `InternalsVisibleTo`, so dropping a proxy
needs a core API change. That change is phase 8's, which is why this waits rather than being
attempted here.

An alternative considered and rejected for now: key the frame on `(body, epoch, position, velocity)`
and rebuild the KSP orbit lazily, so structurally equal frames dedupe in the store. It fixes the
frame half of the leak but not the `Orbit` half, and it trades a plain field for a cache on an
otherwise immutable object. Not worth it before the general lifetime work lands.

### Behavior of existing `Orbit` members on an ownerless orbit

Checked, all degrade acceptably; no changes needed.

| Member | Behavior |
| --- | --- |
| `DefaultReferenceFrame` | Already falls back to `Body.NonRotatingReferenceFrame` when there is no owner |
| `OwnerVessel` / `OwnerBody` | Feed only `ClosestApproach.Vessel` / `Body` / `TargetVessel` / `TargetBody`, which report nothing for a constructed orbit. Correct |
| `TimeToSOIChange`, `NextOrbit` | `NaN` and `null`, given `UTsoi = -1`. Without setting it, `UTsoi` defaults to `0`, which is right for every UT except exactly `0`, where `NextOrbit` would wrap a null `nextPatch` |
| `ClosestApproaches` | Steps by `period`, which `Init()` sets. A hyperbolic constructed orbit inherits the same weakness real hyperbolic orbits already have — not a regression, not fixed here |

## Phases

| Phase | Scope | State |
| --- | --- | --- |
| 1 | `Orbit.CreateFromPositionAndVelocity` and `Orbit.VelocityAt`. A constructed orbit is usable for prediction on its own, with no new frame types | Implemented |
| 2 | The `OrbitNonRotating` and `OrbitOrbital` frames | Implemented |
| 3 | `Orbit.CreateFromOrbitalElements`, the counterpart to phase 1. Independent of phase 2 | Implemented |
| 4 | Not proposed yet: sphere-of-influence patching via `PatchedConics.CalculatePatch`; frame lifetime under `ClientOwnedObjects`, which belongs with the general work in [`object-lifetime.md`](../object-lifetime.md) | Open |

Phase 1 is independently useful and mergeable, and was checked to build and pass
`//doc:check-documented` on its own before phase 2 was added on top. Phase 2 depends on it. Phase 3
depends on neither, and is ordered after them only because it was thought of later.

## Limitations to document

- **Single conic.** Past the edge of the sphere of influence the conic continues as if the body's
  gravity extended forever. A frame property read must not throw there — that would break streams —
  so the limit is documented rather than enforced, and a script can detect it with `Orbit.RadiusAt`
  against `CelestialBody.SphereOfInfluence`.
- **No drag**, so a constructed orbit inside an atmosphere diverges from a real coasting vessel.
- A vessel inside physics range is integrated rather than held on rails, so it drifts slightly from
  its own conic. A constructed orbit matches an on-rails vessel exactly.

## Risks

- ~~**The velocity convention is the one thing not settled from first principles.**~~ **Settled, and
  the design was right.** Body-relative position and velocity, `.SwapYZ()`, then `Init()` is
  correct. An orbit built from a live vessel's own state reproduces that vessel's apoapsis,
  periapsis, eccentricity, inclination, longitude of ascending node, argument of periapsis and
  period, and states chosen by hand give exactly the circular, polar, equatorial and hyperbolic
  conics they should. `Debug.cs` was the wrong thing to copy, as the design suspected.
- ~~Whether `Debug.cs` is itself wrong here is **still open**.~~ **Investigated and closed: it is
  correct.** `Debug.SetPosition` and `Debug.SetVelocity` do pass an unsubtracted world velocity into
  `UpdateFromStateVectors`, and that is right, for a reason worth writing down because it is the
  thing that makes the whole velocity story hang together.

  A kRPC world velocity is **not absolute**. Every one of them is built from `Orbit.GetVel()` or
  `CelestialBody.GetWorldVelocity()` (which is `body.GetOrbit().GetVel()`), and `GetVel()` is
  `GetFrameVel()` minus the **active vessel's reference body's** frame velocity. So kRPC's world
  space is already centered on the active vessel's reference body, and for that body `B`,
  `B.GetWorldVelocity()` is identically **zero**: `CelestialBody.GetFrameVel()` and
  `Orbit.GetFrameVel()` compute the same chain sum for the same body, so the difference cancels.

  All three callers of `SetStateVectors` are therefore feeding it a body-relative velocity already:

  | Caller | Velocity it passes | Why it is body-relative |
  | --- | --- | --- |
  | `SetFlight` | `Cross(body.angularVelocity, positionFromBody) + speed * flightPath` | Constructed body-relative from scratch, for whatever body was asked for. Never touches world space |
  | `SetPosition` | `internalVessel.orbit.GetVel()` | The active vessel's velocity relative to its own reference body, which is the `celestialBody` being passed |
  | `SetVelocity` | `frame.VelocityToWorldSpace(...)` | A world velocity, and world is relative to the active vessel's reference body, which is again the `celestialBody` being passed |

  The subtraction `Orbit.CreateFromPositionAndVelocity` performs would be a subtraction of zero
  here. It is needed there and not here because there the body is an arbitrary argument — building
  an orbit around the Mun while the vessel orbits Kerbin has `Mun.GetWorldVelocity()` at some
  hundreds of meters per second — whereas `Debug` always uses the active vessel's own body.

  Confirmed in game, not only on paper. The existing `test_set_velocity` round-trips through
  `kerbin.non_rotating_reference_frame`, whose own velocity term is zero, so it cannot tell the two
  conventions apart. A throwaway test doing the same round trip through the **Mun's** non-rotating
  frame, which carries hundreds of meters per second of its own motion, passes to within 5 m/s. That
  test is not kept; it is recorded here as what was run.

  So the three functions that look interchangeable are three different conventions, and this is the
  distinction to keep straight: `GetFrameVel()`/`GetFrameVelAtUT()` are **absolute** (the chain sum
  to the Sun) and are what `ClosestApproach` wrongly used; `GetVel()` is relative to the **active
  vessel's** reference body and is what kRPC world space means; `GetRelativeVel()` and
  `getOrbitalVelocityAtUT()` are relative to the **orbit's own** reference body.

## Departures from the design

Collected for a reader who only wants to know where the shipped code differs from what is above.
Each is explained in place in the section it belongs to.

| Departure | Why |
| --- | --- |
| The RPCs are named `Orbit.CreateFromPositionAndVelocity` and `Orbit.CreateFromOrbitalElements`, not `Orbit.CreateFromStateVectors` | The astrodynamics term was dropped on the vector side in favor of naming the two arguments outright, so the pair reads without the vocabulary. kRPC method names are unique per class, so there is no overloading to fall back on and the two had to be distinguished by name |
| `Orbit.CreateFromOrbitalElements` exists at all | Not in the design; see the section above. The pair had to be named together, and an orbit stated as elements is the other half of the same feature |
| `Orbit.Epoch` documentation corrected | It described a universal time as "the time since the epoch". The new `epoch` parameter takes the same quantity, so leaving it would have put two contradictory descriptions of one field in the same class |
| `ut` is a required parameter, ahead of the optional `referenceFrame`, rather than defaulting to `NaN` for "now" | A `double` default is written into the generated client stubs as a bare `nan` literal, which does not compile |
| `orbit.UpdateFromUT (ut)` is called after `Init ()` | Otherwise `Orbit.Speed` is zero: nothing fills in `orbitalSpeed` for an orbit no object is following |
| `Orbit.VelocityAt` uses body-relative velocity plus the body's own motion, not `GetFrameVelAtUT` | The design recommended a pattern that is wrong by the active vessel's frame velocity, and that is a live bug in `ClosestApproach` too |
| The "`Transform` throws" row of the frame table is not covered by a test | `ReferenceFrame.Transform` has no callers anywhere and is not a `[KRPCProperty]`, so no client can reach it. The arm is still implemented for the C# surface |
| `doc/order.txt` needed the four new members added | The design said no new `.tmpl` was needed, which is true, but missed that `docgen` also takes the member order file, and `//doc:check-documented` fails without it |
| The tutorial's "Available Reference Frames" has six per-language tabs, not five | Miscounted; C is a tab of its own alongside C++ |

Two results that looked like defects during implementation but are correct behavior, recorded so
they are not re-investigated:

- **In the orbital frame of a circular orbit, the body being orbited is at rest.** The frame's
  rotation contributes an omega-cross-r term at the body's center that is equal and opposite to the
  frame's motion along the orbit. Only the non-rotating frame can be used to measure the frame's
  translational speed this way.
- **Angular velocity can only be observed through something that rotates**, and for these frames the
  only such thing to hand is the body itself. A reading of the body's spin in the frame is the spin
  *minus* the frame's rotation, not the frame's rotation. For a polar orbit the two are
  perpendicular and separate in quadrature.

## Verification

In-game tests, in `service/SpaceCenter/test/test_orbit.py` (following the `TestOrbit` class pattern)
and `service/SpaceCenter/test/test_referenceframe.py`.

| Test | Assertion |
| --- | --- |
| **States chosen by hand** | In the body's non-rotating frame the y-axis points at the north pole and x and z lie in the equatorial plane, so a position on z with a velocity along y is a polar orbit and the same position with a velocity along x is an equatorial one. Assert radius, eccentricity, inclination and period for circular, eccentric and hyperbolic cases |
| **Round trip from a live vessel** | Build an orbit from the vessel's `position` and `velocity` in `body.non_rotating_reference_frame` at `sc.ut`, then assert apoapsis, periapsis, eccentricity, inclination, argument of periapsis, longitude of ascending node and period all match `vessel.orbit` |
| State vectors recovered | `position_at` and `velocity_at` at the epoch return the vectors the orbit was built from |
| Prediction agreement | `position_at`, `velocity_at` and `radius_at` are self-consistent across a range of future UTs, with speed matching the vis-viva equation |
| Rotating construction frame | The same numbers given in `body.reference_frame` describe a **different** orbit than in the non-rotating frame |
| No patch | `next_orbit` is `None` and `time_to_soi_change` is `NaN`, including well outside the sphere of influence |
| Origin tracks the vessel | `vessel.orbit.position_at(sc.ut, frame)` in the constructed orbit's frame stays near zero over time. Compare against the vessel's **orbit** position, not `vessel.position`, per the offset decision above |
| `orbital_reference_frame` axes | Velocity along +y, orbit normal along +z, matching the assertions already used for `vessel.orbital_reference_frame` |
| `reference_frame` axes | Axes fixed against `body.non_rotating_reference_frame`, and no angular velocity of its own |
| Frame velocity | The body being orbited recedes at the orbit's own speed in the non-rotating frame |
| Composition | Both frames compose with `create_hybrid` and `create_relative` |
| **Elements against a position and velocity** | Build an orbit with `create_from_position_and_velocity`, rebuild it from the elements it reports, and assert the two agree in `position_at` and `velocity_at` over a range of UTs. This is the load-bearing check for the elements form: it pins the unit conversions and the epoch convention against a path already verified independently |
| Elements recovered | The orbit reports back the seven elements it was built from. Catches the radians-to-degrees conversion on its own, since a raw radian value handed to a degree field comes back a factor of 180/pi out |
| Shape from the elements | Apoapsis and periapsis are the semi-major axis scaled by one plus and one minus the eccentricity |
| Inclination is physical | A quarter turn of inclination takes the orbit over the poles, reaching nearly its full radius along the non-rotating frame's y-axis, where an equatorial orbit stays near zero |
| Mean anomaly at the epoch | `mean_anomaly` at construction is the value given, and `mean_anomaly_at_ut` a quarter period on has advanced by a quarter turn |
| Elements round trip from a live vessel | Build from `vessel.orbit`'s own elements and assert `position_at` agrees over a range of UTs. Unlike the vector round trip every input comes from one orbit, so there is no physics frame between them and the tolerances are tight |
| Elements that are not a conic | A negative eccentricity, an eccentricity of exactly one, an ellipse with a negative semi-major axis and a hyperbola with a positive one each raise |

> **Two rows changed.** The design had the round trip from a live vessel as *the* load-bearing check.
> It is not the one to lean on: `position`, `velocity` and `ut` come from three separate RPCs and the
> game advances a physics frame between them, so the state is not one the vessel was ever in and the
> tolerances have to be loose. States chosen by hand have no such race and pin the conversion down
> far more tightly, so they carry the weight and the round trip corroborates.
>
> The design also asserted that constructing in `body.reference_frame` "yields the same orbit as
> constructing in the non-rotating frame". **That is wrong.** The rotating frame carries the surface
> motion, which at these radii is a sixth of orbital speed, so the same numbers describe a
> substantially different orbit. Testing that they differ is the point; testing that they agree would
> only pass if the frame were being ignored.

Result: 144 tests pass across the two files. `bazel test //:test`, `//:lint`, `//doc:spelling` and
`//doc:check-documented` all pass.

**Out of scope, decided:** the check outside the flight scene, in the space center and tracking
station. No `GameScene` restriction is applied, matching `Orbit`, so those scenes are reachable and
stay untested. Flight is the scene this is for and is sufficient.

## Files touched

- `service/SpaceCenter/src/Services/Orbit.cs`
- `service/SpaceCenter/src/Services/ReferenceFrameType.cs`
- `service/SpaceCenter/src/Services/ReferenceFrame.cs`
- `doc/order.txt`, which `docgen` reads to order and to admit members; `//doc:check-documented`
  fails until the new members are listed there
- `doc/src/tutorials/reference-frames.rst`, whose "Available Reference Frames" lists the frames in
  six per-language tabs, all of which need the new entries
- `service/SpaceCenter/test/test_orbit.py`, `service/SpaceCenter/test/test_referenceframe.py`
- `service/SpaceCenter/CHANGELOG.md`

No `.csproj` change, since no new source file is added, and no new `doc/api/space-center/*.tmpl`,
since `orbit.tmpl` renders the whole class.
