# Orbit position and velocity, and the gaps around them

**Status:** in progress. Implemented and building; no PR opened and no issue filed yet, one should
be filed.

`Orbit` pairs `Radius` with `RadiusAt` and `Speed` with `SpeedAt`. The vector members have no such
pair: `PositionAt (ut, frame)` and `VelocityAt (ut, frame)` exist, and there is no `Position` and no
`Velocity`. Asking where an orbit is and how fast it is going right now takes a round trip through
`SpaceCenter.UT`.

Two smaller gaps sit alongside it:

| Gap | Evidence |
| --- | --- |
| `RadiusAtTrueAnomaly` has no position, velocity or speed counterpart | A true anomaly names a point on the orbit, and only a distance can be read at it |
| The shape scalars stop short | `ApoapsisAltitude` and `PeriapsisAltitude` with no `Altitude`; `SpecificEnergy` with no angular-momentum sibling |

## The decision: read the state fields, not the propagated conic

`Position` and `Velocity` could be built two ways. Read from the disassembly of the game's `Orbit`:

| | `Orbit.pos` / `Orbit.vel` | `getPositionAtUT (now)` |
| --- | --- | --- |
| Written by | `UpdateFromFixedVectors` (physics) and `UpdateFromUT` (rails, and a constructed orbit) | Nothing; evaluated from the elements on each call |
| For a vessel under physics | The state the vessel is actually in | The conic it would be on, a few meters away |
| `norm (Position)` against `Radius` | Equal, since `radius = pos.magnitude` in both writers | Drifts |
| `norm (Velocity)` against `Speed` | Equal, since `Speed` reads `vel.magnitude` | Drifts |

**Decision: read `pos` and `vel`.** `Radius` and `Speed` already read them, so the magnitudes agree
by construction. This is the same choice as the fix for `Orbit.OrbitalSpeed`, which had been reading
KSP's `orbitalSpeed` field and reporting the speed a vessel had when it was last on rails.

The consequence to accept: `Position ()` is not `PositionAt (SpaceCenter.UT)` for a vessel inside the
physics bubble, and the origin of `Orbit.ReferenceFrame` is a few meters from `Position ()`. The
`<remarks>` on `Orbit.ReferenceFrame` already describes that gap.

### Axis and frame conventions

The traps, all confirmed against the disassembly:

| Member | Convention |
| --- | --- |
| `Orbit.pos`, `Orbit.vel` | Body-relative, in the game's Z-up axis order. `GetRelativeVel ()` is `vel.xzy`, which kRPC spells `SwapYZ` |
| `getPositionAtUT`, `getPositionFromTrueAnomaly` (one argument) | Already world space. No swap |
| `getRelativePositionFromTrueAnomaly`, the two-argument overloads | Body-relative and Z-up. The inverted convention is an easy trap |
| `getOrbitalVelocityAtUT`, `getOrbitalVelocityAtTrueAnomaly` | Body-relative and Z-up, so `.SwapYZ () + referenceBody.GetWorldVelocity ()` |
| `RadiusAtTrueAnomaly` and the true-anomaly family | Radians, matching kRPC |

## Members added

| Member | Reads |
| --- | --- |
| `Position (frame = null)`, `Velocity (frame = null)` | `pos` and `vel`, converted to world space |
| `PositionAtTrueAnomaly`, `VelocityAtTrueAnomaly`, `SpeedAtTrueAnomaly` | The true-anomaly counterparts of the `AtUT` family |
| `SpeedAtRadius` | `getOrbitalSpeedAtDistance`, which `SpeedAt` already reached indirectly |
| `Altitude`, `MeanMotion`, `SemiLatusRectum`, `SpecificAngularMomentum` | `altitude`, `meanMotion`, `semiLatusRectum`, `h.magnitude` |

`PositionAt` and `VelocityAt` take their reference frame as an optional parameter, matching the new
members. Not breaking: a call that passes a frame is unchanged, and a client that omits it transmits
a null.

**The default frame is the non-rotating frame of the body being orbited**, which is the frame
`CreateFromPositionAndVelocity` already defaults to, so the two round-trip against each other.
`Orbit.DefaultReferenceFrame`, which the closest-approach members use, is the *orbital* frame of the
object the orbit belongs to and would make `Position ()` report about zero.

## Testing

Split the way the existing orbit tests are split:

| Where | What it carries |
| --- | --- |
| `TestOrbit`, on a live vessel | `norm (position)` is `radius` and `norm (velocity)` is `speed`; both follow the vessel rather than its conic. The physics-vessel test that already discriminates the `Speed` fix gains a velocity assertion, so the decision above is tested directly |
| `TestCreateFromPositionAndVelocity`, on chosen numbers | A constructed orbit is stepped to its epoch once and never again, so no physics frame can move the answer. The state vectors round-trip, the true-anomaly family agrees with the `AtUT` family, and the scalars match their closed forms |

## Files touched

- `service/SpaceCenter/src/Services/Orbit.cs`
- `doc/order.txt`, which `docgen` reads to order and to admit members
- `doc/src/dictionary.txt`, for "latus"
- `service/SpaceCenter/test/test_orbit.py`
- `service/SpaceCenter/CHANGELOG.md`

No `.csproj` change, since no new source file is added.
