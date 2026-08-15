# Orbits from state vectors, and reference frames that coast

**Status:** proposal — no issue filed yet, one should be filed.

Let a script construct an orbit from an initial position and velocity, and derive reference frames
from it whose origin then coasts under gravity. This gives a frame that tracks where a vessel
*would* have travelled had it existed, without that vessel existing.

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

### `Orbit.CreateFromStateVectors`

A static `[KRPCMethod]`, alongside the existing static `ReferencePlaneNormal` and
`ReferencePlaneDirection`, and mirroring the `ReferenceFrame.CreateRelative` / `CreateHybrid`
factory precedent.

```csharp
[KRPCMethod]
public static Orbit CreateFromStateVectors (
    CelestialBody body, Tuple3 position, Tuple3 velocity,
    ReferenceFrame referenceFrame = null, double ut = double.NaN)
```

`referenceFrame` defaults to `body.NonRotatingReferenceFrame`. A `ut` of `NaN` means the current
universal time; `NaN`-as-unset is already the idiom in this class, in `Orbit.TimeToSOIChange`.

```csharp
var worldPosition = frame.PositionToWorldSpace (p);
var worldVelocity = frame.VelocityToWorldSpace (p, v);
var relativePosition = worldPosition - internalBody.position;
var relativeVelocity = worldVelocity - internalBody.GetWorldVelocity ();

var orbit = new global::Orbit ();
orbit.UpdateFromStateVectors (
    relativePosition.SwapYZ (), relativeVelocity.SwapYZ (), internalBody, epoch);
orbit.Init ();
orbit.UTsoi = -1;
```

Each line is backed by a row of the table above. `GetWorldVelocity` is in
`service/SpaceCenter/src/ExtensionMethods/CelestialBodyExtensions.cs`.

Validation: null arguments; a zero-magnitude relative position; a non-finite `semiMajorAxis` or
`eccentricity` after `Init()`. `Debug.cs` already records why a NaN conic is worth guarding against
— the patched-conic solver fills with NaN and takes down the flight scene.

No `GameScene` restriction, matching `Orbit`, which carries none. Propagation needs only
`Planetarium` and the body.

### `Orbit.VelocityAt`

`Orbit.PositionAt(ut, referenceFrame)` exists with no velocity counterpart. Add one, using the
pattern already proven in `service/SpaceCenter/src/Services/ClosestApproach.cs`, which reads world
state vectors at a future UT as `getPositionAtUT(ut)` and `GetFrameVelAtUT(ut).SwapYZ()`.

Useful on its own, independent of everything else here.

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
| `Transform` | throws, joining the `Maneuver` arm | same |

`Velocity` is the `Maneuver` case verbatim with `ut = now`. `OrbitOrbital`'s `AngularVelocity` is
the `VesselOrbital` case, with `r` and `v` taken against `referenceBody.position` and
`referenceBody.GetWorldVelocity()`.

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

`Orbit.Equals` is reference equality on `InternalOrbit`, so every `CreateFromStateVectors` call
yields a distinct `Orbit` and distinct frames, and each is retained for the server's lifetime —
`ObjectStore` is cleared only when the last server stops. A script constructing an orbit per tick
leaks steadily.

This is the problem [`object-lifetime.md`](../object-lifetime.md) tracks; its
[reference frames](../object-lifetime.md#reference-frames) section and phase 3h cover frame
liveness, and `ClientOwnedObjects` — already used by the Drawing service and `Parts.Force` — is the
eventual fix. Out of scope here, but the retention belongs in the `CreateFromStateVectors` doc
comment so it is not a surprise, and `object-lifetime.md` should gain a pointer back to this doc as
a new producer of retained frames.

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

| Phase | Scope |
| --- | --- |
| 1 | `Orbit.CreateFromStateVectors` and `Orbit.VelocityAt`. A constructed orbit is usable for prediction on its own, with no new frame types |
| 2 | The `OrbitNonRotating` and `OrbitOrbital` frames |
| 3 | Not proposed yet: sphere-of-influence patching via `PatchedConics.CalculatePatch`; frame lifetime under `ClientOwnedObjects`, which belongs with the general work in [`object-lifetime.md`](../object-lifetime.md) |

Phase 1 is independently useful and mergeable. Phase 2 depends on it.

## Limitations to document

- **Single conic.** Past the edge of the sphere of influence the conic continues as if the body's
  gravity extended forever. A frame property read must not throw there — that would break streams —
  so the limit is documented rather than enforced, and a script can detect it with `Orbit.RadiusAt`
  against `CelestialBody.SphereOfInfluence`.
- **No drag**, so a constructed orbit inside an atmosphere diverges from a real coasting vessel.
- A vessel inside physics range is integrated rather than held on rails, so it drifts slightly from
  its own conic. A constructed orbit matches an on-rails vessel exactly.

## Risks

- **The velocity convention is the one thing not settled from first principles.** `Debug.cs`'s
  `SetPosition` and `SetVelocity` pass an unsubtracted world velocity into
  `UpdateFromStateVectors`, which contradicts the body-relative reading the disassembly supports.
  Do not copy `Debug.cs`; let the round-trip test below decide. If it fails, the fix is a single
  subtraction and the test says which way.
- Whether `Debug.cs` is itself wrong here is worth checking once the convention is pinned down. If
  so it is a separate bug, a separate issue and a separate change.

## Verification

In-game tests, in `service/SpaceCenter/test/test_orbit.py` (following the `TestOrbit` class pattern)
and `service/SpaceCenter/test/test_referenceframe.py`.

The first one is load-bearing — it is what pins down the vector convention, and it fails loudly and
immediately if any part of the conversion is wrong.

| Test | Assertion |
| --- | --- |
| **Round trip from a live vessel** | Build an orbit from the vessel's `position` and `velocity` in `body.non_rotating_reference_frame` at `sc.ut`, then assert apoapsis, periapsis, eccentricity, inclination, argument of periapsis, longitude of ascending node and period all match `vessel.orbit` tightly |
| Prediction agreement | `position_at` and the new `velocity_at` match `vessel.orbit`'s across a range of future UTs |
| Rotating construction frame | Constructing in `body.reference_frame` yields the same orbit as constructing in the non-rotating frame |
| No patch | `next_orbit` is `None` and `time_to_soi_change` is `NaN` |
| Origin tracks the vessel | `vessel.orbit.position_at(sc.ut, frame)` in the constructed orbit's frame stays near zero over time. Compare against the vessel's **orbit** position, not `vessel.position`, per the offset decision above |
| `orbital_reference_frame` axes | Velocity along +y, orbit normal along +z, matching the assertions already used for `vessel.orbital_reference_frame` |
| `reference_frame` axes | Zero angular velocity, and axes fixed against `body.non_rotating_reference_frame` across a time step |
| Composition | Both frames compose with `create_hybrid` and `create_relative` |

Also worth a manual check outside the flight scene, in the space center and tracking station, since
no `GameScene` restriction is applied.

## Files an implementation would touch

- `service/SpaceCenter/src/Services/Orbit.cs`
- `service/SpaceCenter/src/Services/ReferenceFrameType.cs`
- `service/SpaceCenter/src/Services/ReferenceFrame.cs`
- `doc/src/tutorials/reference-frames.rst` — "Available Reference Frames" lists the frames in five
  per-language tabs; all five need the new entries
- `service/SpaceCenter/CHANGELOG.md`

No `.csproj` change, since no new source file is added.
