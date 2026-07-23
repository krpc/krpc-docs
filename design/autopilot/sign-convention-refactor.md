# AutoPilot — right-handed sign-convention refactor

**Status:** proposal — design note (2026-07-02), not yet implemented. Addresses §4 ("the left-handed
sign convention is a standing hazard") of [`inner-loop.md`](inner-loop.md).

## Problem

The attitude controller runs its inner rate loop in a **left-handed** angular-velocity convention,
established by a *matched pair of negations*:

- **Measurement** — `ComputeCurrentAngularVelocity` (`AttitudeController.cs:1055`) returns
  `-ApToBody(localAngularVelocity)`.
- **Command** — the velocity profile commands `ω_target = −sign(θ)·speed` (the leading minus in
  `ComputePitchYawVelocity` `:1453–1454` and `ComputeAxisVelocity` `:1521`).

The direction error is built by `FromToRotation(current, target)`, whose axis is the **right-handed**
cross product `current × target` (`GeometryExtensions.cs:324`). The command then defines positive
angular velocity as the *left-handed* sense about that axis, and the measurement is negated to match.
The PI loop compares setpoint against measurement, so the two negations must flip together; removing
either alone makes them disagree and the loop diverges.

The critique (§4) rates this "well-commented but a matched pair that any future contributor can break
by fixing one of them," and the status update (`inner-loop.md`) leaves it
**open**. Note KSP/Unity are themselves left-handed by convention, so the current internal convention
is not unusual for the platform — the hazard is the *two-point, manually-synchronized* definition, not
the handedness per se.

## Finding — the coupled surface is larger than "the matched pair"

Tracing every consumer of the negated ω (it propagates `currentRaw → current → currentRi → omegaRi`
and `currentOmegaRi`) shows the convention is load-bearing at **~9 code sites**, not 3. A consumer is
**sign-sensitive** when it dots ω against an error/command direction or forms `e_stop = θ + coeff·ω`;
it is **invariant** when ω enters only through a linear op, a quadratic form, or amplitude/frequency.

| Site | File:line | Class | Note |
|---|---|---|---|
| Measurement negation | `:1055` | source | the negation itself |
| Pitch/yaw command | `:1453–1454` | sign-sensitive | `−sPitch·speed`, `−sYaw·speed` |
| Roll command | `:1521` | sign-sensitive | `−Math.Sign(θ)·speed` |
| Pitch/yaw FF `d|θ|/dt` | `:1599` | sign-sensitive | `+(θ̂·ω)/θ` term inverts |
| Pitch/yaw FF `omegaAlongCommand` | `:1602` | sign-sensitive | `−(ŝ·ω)`, command dir is `−ŝ` |
| Roll FF `d|θ|/dt` | `:1623` | sign-sensitive | `Math.Sign(θ)·ω` inverts |
| Roll FF `omegaAlongCommand` | `:1626` | sign-sensitive | `−(ŝ·ω)` |
| Stopping distance `e_stop` | `~:1362–1382` | sign-sensitive | `e_stop = θ + coeff·ω`, `coeff ≥ 0` |
| Gyroscopic FF | `:1115–1123` | **invariant** | `ω×(Iω)` quadratic |
| Detectors (chatter/trackers) | `:669,:674` | **invariant** | amplitude/frequency |
| Rate filters / roll-invariant rotation | `:690–716` | **invariant** | linear |
| PID `RunAxis` | `:830–832` | **invariant** | target + `currentRi` flip together |

The subtle one is **`e_stop = θ + coeff·ω`** (`ComputePitchYawVelocity`). With the negated ω, ω points
*with* θ while closing, so `+coeff·ω` correctly predicts overshoot. Un-negate ω and it points
*against* θ, so preserving behavior requires **`e_stop = θ − coeff·ω`** (negate the ω contribution to
`eStopPitch/eStopYaw`, not `coeff`). Miss this and the profile predicts stopping short.

## Options

**Option A — right-handed refactor (chosen).** Remove *both* negations: measurement un-negated
(`:1055`), command `+sign(θ)` (B sites), and flip every sign-sensitive consumer (C/D sites). The loop
then runs right-handed, anchored directly to the `FromToRotation` axis, with **zero negations** and no
matched pair to break. The code's own comment (`:1054`) asserts this is behavior-equivalent.
Cost: ~9 coupled edits + comments + antipodal re-validation + full in-game retest. Trades KSP-native
left-handedness for algebraic-cross-product handedness.

**Option B — single `ConventionSign` constant (fallback).** Keep the (empirically-validated,
platform-matching) left-handed convention but route both halves through one
`const double ConventionSign = -1.0;` so they cannot drift independently. **Bit-identical by
construction**, ~3 lines, no re-validation. Structurally removes the "fix one of them" trap without
touching the FF/stopping-distance math. Recommended if the Option-A in-game equivalence proves
stubborn.

## Implementation (Option A)

All in `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` unless noted.

1. `:1055` — drop the leading `-`.
2. `:1453`, `:1454`, `:1521` — drop the leading `-` (roll: `Math.Sign(theta)`).
3. `:1599`, `:1602`, `:1623`, `:1626` — flip each sign-sensitive FF term.
4. `~:1362–1382` — change `e_stop` to `θ − coeff·ω`; verify the `eStop*` assembly and confirm the roll
   `ComputeAxisVelocity` path has no analogous `θ + coeff·ω` term.
5. Comments: rewrite `:1040–1054`, `:1428–1435`, `:1497–1499`, `:1111–1113`, `:1595–1596`, and audit
   `:1206–1211`/`:1326–1345` (no negation now; loop is right-handed).
6. **Antipodal** (`ResolveAntipodalAxis` `:1149–1195`): reads `Rigidbody.angularVelocity` directly, so
   `antipodeLatchedNormal` is unchanged — ship it as-is, then validate in-game. Its output feeds the
   same error→command path whose command sign we flipped, and `antipodal-flip.md` warns
   the sign is convention-dependent. If prograde↔retrograde reverses, swap the final cross-product
   operand order at `:1194` (`Vector3d.Cross(tBlend, currentDirection)`) and update that doc note.

## Verification

Behavior-preserving, so the primary test is **before/after equivalence of control outputs**. Rebuild
with `tools/run-ksp.sh` after C# changes.

1. **Equivalence (primary).** The controller logs `omega_ri`, `tgt_omega_ri`, and control outputs
   (`~:989–995`). Fly a fixed scenario on the current build and capture the log; apply the change and
   fly the identical scenario. `omega_ri`/`tgt_omega_ri` will read negated between the two runs
   (expected), but `state.Pitch/Roll/Yaw` and the trajectory must match within FP tolerance. A
   mismatch = a sign-sensitive site missed or wrongly flipped.
2. **No divergence.** Project quick gate from `service/SpaceCenter/test/`: `test_autopilot` →
   `orbital_directions`, the Ariane launch (`test_ascent_no_wobble`), and `smooth_turn`.
3. **Antipodal flip.** 180° prograde→retrograde reversal (and back): correct direction, stays
   in-plane. If reversed, apply the `:1194` operand swap and re-test.

## Status

Open. On completion, move §4 in `inner-loop.md` from "Still open" to
resolved and record the expanded coupled-site surface.
