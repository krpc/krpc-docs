# Design proposal: bank-to-turn attitude control for asymmetric-authority craft

**Status:** proposal — not started.
**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs`,
`service/SpaceCenter/src/Services/AutoPilot.cs`.
**Related:** [`outer-loop.md`](outer-loop.md) (the anisotropic pitch/yaw law this reuses),
[`orientation-api.md`](orientation-api.md) (the roll reference / `TargetRoll` surface this hands back to),
[`aero-extension.md`](aero-extension.md) (aircraft regimes where this matters most).

## Motivation

An aircraft (and many spaceplanes) has strong pitch and roll authority but weak yaw authority. To
change heading it does not yaw the nose sideways — it **banks** (rolls) so the strong pitch axis
pulls the nose around, then rolls level. The current autopilot never does this.

What it does today: the direction error is decomposed into roll-invariant pitch/yaw components, and
the joint 2D outer law (`ComputePitchYawVelocity`) already carries *anisotropic* authority — it
projects separate `α_pitch`/`α_yaw` and per-axis bandwidths along the slew direction
([`outer-loop.md`](outer-loop.md), "option b"). So a weak-yaw craft still slews the nose straight along
the great-circle arc — it just does so at the weak yaw axis's speed for the yaw component of the
turn. It knows yaw is weak; it does not **exploit roll to avoid using yaw**.

Roll is also controlled only *near* the target today: `RollWeight(dirError)` ramps from 0 at
`RollStartAngle` (20°) to 1 at `RollEngageAngle` (15°), so during a large slew roll is free
(`AttitudeController.cs:1129`). Bank-to-turn needs the opposite — roll actively driven *during* the
slew — which is why it is a distinct mode rather than a tweak to the existing schedule.

## Scope decision

A new **opt-in** flag `AutoPilot.BankToTurn` (default `false`). When off, behavior is bit-for-bit
unchanged — rockets, vacuum craft, and any script relying on `TargetRoll` during a slew are
unaffected. When on, the roll *setpoint* is slaved to the maneuver geometry during the slew and
handed back to the user's `TargetRoll` as the turn completes.

Default-off is deliberate: bank-to-turn is only ever an improvement on genuinely asymmetric craft,
it takes ownership of roll during the slew (incompatible with a script that wants a fixed roll while
turning), and it presumes the craft is aerodynamically willing to be banked (a reaction-wheel-only
station has no reason to). Auto-detection was considered and rejected — see below.

## The idea

Everything is expressed in the roll-invariant (RI) frame the controller already builds. The
pitch/yaw direction error there is a 2D vector

```
e = (anglesRI.x, anglesRI.z)          // (pitch error, yaw error), computed at AttitudeController.cs:1663
```

Pitch actuation moves the nose along the body pitch direction; yaw actuation along the body yaw
direction. **Bank-to-turn rolls the vessel so its strong axis (pitch, for a typical plane) points
along `e`** — i.e. it drives the roll that zeroes the *weak-axis* component of the error, leaving
the whole turn to the strong axis. The required roll offset relative to the current roll is

```
Δφ = atan2(e_yaw, e_pitch)             // sign per the left-handed ω convention, AttitudeController.cs:1407
```

Crucially, no new pitch/yaw law is needed. Once the vessel is rolled so its pitch axis lies along
`e`, the existing RI→body conversion (`FromRollInvariant`, using the current roll φ) naturally routes
the commanded RI angular velocity onto the body **pitch** control. The 2D outer law still aims at the
great-circle stopping point, so the nose still traces the correct arc — bank-to-turn only chooses the
*roll orientation* from which the arc is flown, and the anisotropic law then finds it cheap because
the strong axis is doing the work. As pitch error is consumed, `e` shrinks and rotates, `Δφ` is
recomputed each tick, and the craft rolls level naturally.

### Generalization

Do not hard-code "align with pitch". Align `e` with whichever of pitch/yaw has the higher authority
`α = torque/MoI`. For the normal plane that is pitch; the formulation is symmetric and needs no
special case for a (rare) strong-yaw/weak-pitch craft.

## Where it hooks

`AttitudeController.ComputeTargetAngularVelocity` (`AttitudeController.cs:1638`), specifically the
roll-setpoint block (lines 1667–1689). Bank-to-turn replaces only the **roll setpoint** fed to the
existing roll 1D bang-bang (`ComputeAxisVelocity`); the pitch/yaw 2D law is untouched. Concretely,
when `BankToTurn` is on and the bank gate (below) is open, the block computes the bank target roll
instead of / blended with `RollRelativeTo(effectiveRotation, upReference)`.

## The two gates

**1. Anisotropy gate (how much banking is worth it).** A bank fraction from the authority ratio:

```
strong = max(α_pitch, α_yaw)          // the axis we bank toward
weak   = min(α_pitch, α_yaw)
bankFraction = smoothstep over (strong / weak), ~0 below a small ratio, →1 above a larger ratio
```

A near-symmetric craft (`strong ≈ weak`, e.g. a rocket with gimbal + RCS) gets `bankFraction ≈ 0`
→ behavior identical to today even with the flag on. Additionally, **do not bank if the strong axis
itself is weak** (both pitch and yaw poor, e.g. a tumbling debris core) — banking buys nothing and
risks a slow roll fighting a slow pitch; gate on `strong` exceeding an absolute floor, or better,
gate on `α_roll` being adequate (banking needs roll authority to pay off). Prefer expressing the gate
against roll authority explicitly: bank only when roll is strong enough to reorient faster than the
weak axis would complete the turn directly.

**2. Error-magnitude schedule (when to bank vs hold roll).** Bank-to-turn owns roll during the
*large-error* slew and hands back to `TargetRoll` as the nose arrives — the inverse of the existing
`RollWeight` ramp. Define a bank weight that is 1 for `dirError` above a hand-back band and ramps to
0 across it (reusing `RollStartAngle`/`RollEngageAngle` or a dedicated pair), then

```
rollSetpoint = blend(bankTargetRoll, userTargetRoll; bankWeight · bankFraction)
```

so the craft rolls into the turn at large error and rolls level to the user's roll as it settles.
`rollControlled` must be forced true throughout the slew when the mode is active (today it is only
effectively controlled once `RollWeight > 0`).

## Interactions / regression surface

| Concern | Rule |
|---|---|
| `TargetRoll` / orientation API | Bank owns roll only while the bank weight > 0; hands back to `TargetRoll` as `dirError` → 0. With `BankToTurn` off, nothing changes. |
| Symmetric craft | `bankFraction ≈ 0` → no banking even with the flag on. Standing regression: a rocket ascent with `BankToTurn=true` must match `BankToTurn=false`. |
| Roll bang-bang / anti-windup | Roll setpoint changes continuously during the slew; the roll axis already runs a full bang-bang profile, so a moving setpoint is in-band. Verify no roll integral wind-up as the setpoint sweeps. |
| Antipodal / 180° handling | Bank direction is `atan2`-derived and shortest-arc; verify it composes with `ResolveAntipodalAxis` (`AttitudeController.cs:1516`) at a 180° heading reversal. |
| `Wait()` termination | Unchanged — `Wait()` keys on pointing error and rate; bank-to-turn only changes the path, not the terminal condition. |
| Sideslip / coordination | Not modeled: pitching-into-the-bank assumes the airframe holds coordinated (little sideslip). Acceptable in stock aero; documented limitation. A coordinated-turn rudder feedforward is a possible later addition, out of scope here. |

## Rejected alternatives

- **Automatic (no flag):** detect asymmetry and bank whenever it helps. Rejected — it silently
  changes behavior for every anisotropic craft, can fight a script's `TargetRoll` mid-slew, and
  surprises existing users. The anisotropy gate already makes the *on* mode a no-op for symmetric
  craft, so opt-in costs nothing and removes the surprise.
- **A new great-circle-with-roll outer law:** rejected — the existing anisotropic 2D law already
  flies the arc correctly once the roll orientation is chosen; bank-to-turn is a roll-setpoint
  policy layered on top, not a new law.
- **Fixed bank angle:** rejected — the required bank is a continuous function of the remaining error
  geometry and authority ratio; a fixed angle over- or under-banks and never rolls level cleanly.

## Phased roadmap

1. **Instrumentation (behavior-neutral).** Build a weak-yaw plane test craft; log `α_pitch`,
   `α_yaw`, `α_roll`, `dirError`, and the roll needed to align `e` with the strong axis over a
   commanded heading change flown the *current* way. Quantify the real anisotropy ratio and how much
   slower the direct path is — this calibrates both gates.
2. **Bank-to-turn setpoint + gates.** Implement the flag, the `atan2` bank target, the anisotropy
   gate, and the hand-back schedule. *Test:* red→green below.
3. **Tuning + generalization.** Confirm the strong-axis generalization and the roll-strength gate;
   tune the gate curves against the phase-1 measurements.

New test craft: a weak-yaw plane (large elevators/ailerons, small rudder). The existing vacuum
regression gate (orbital directions + launch + smooth turn) and a symmetric rocket ascent remain the
zero-regression anchors.

## Test scenarios (red→green, in-game via krpctest)

- **Banks and wins:** weak-yaw plane, `BankToTurn=true`, commanded a 90° heading change — the craft
  banks (roll leaves neutral by a large angle during the slew) and completes the turn faster than the
  same craft with `BankToTurn=false`; measure time-to-settle both ways.
- **Rolls level after:** after the turn settles, roll returns to `TargetRoll` (or the pre-turn roll)
  within the hand-back band.
- **Symmetric craft unchanged:** a rocket with `BankToTurn=true` produces `bankFraction ≈ 0` and a
  slew trace identical to `BankToTurn=false`.
- **`Wait()` terminates:** `Wait()` returns once pointing error and rate are within thresholds, as
  today.
- **Default-off regression:** the full existing autopilot suite passes unchanged with the flag at its
  default.
