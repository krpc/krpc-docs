# AutoPilot antipodal (180°) flip handling

**Status:** done — antipodal flip handling shipped in the autopilot rework ([PR #882](https://github.com/krpc/krpc/pull/882)). Historical design record consolidating the original minimal-change design and the out-of-plane-instability follow-on fix (2026-07-01).

A 180° flip is the singularity of the autopilot's error-axis construction: the direction-error
axis is ill-conditioned exactly antipodal and precesses fastest near it. This doc consolidates the
two former design docs covering how the flip is handled — the original minimal-change design
(`antipodal-flip.md`) that made `test_antipodal_flip` pass, and the done follow-on
(`antipodal-flip-plane-instability.md`) that root-caused an out-of-plane bow and extended
`ResolveAntipodalAxis` to fix it.

## Deterministic antipodal (180°) flip handling for the autopilot

*Originally `antipodal-flip.md` — the minimal-change design, scoped to make `test_antipodal_flip` pass; superseded in part by the plane-instability follow-on below, which extended `ResolveAntipodalAxis`.*

**Status (original):** proposal — scoped as the minimal change to make `test_antipodal_flip` pass; no
new tests or `test_orbital_directions` TODO cleanup in this change.
**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs`,
`ComputeTargetAngularVelocity`; plus an already-applied reporting fix in
`service/SpaceCenter/src/Services/AutoPilot.cs`.
**Related:** part of the ongoing autopilot controls review. Builds directly on the 2D
outer-law ([`outer-loop.md`](outer-loop.md)) — the error vector this proposal conditions is the
`θ = (θ_pitch, θ_yaw)` consumed by `ComputePitchYawVelocity`.

### Motivation

A 180° flip is the singularity of the error-axis construction. `test_antipodal_flip` (a
surface-frame `0,90 → 0,270` flip) exposed two separate problems.

#### Problem 1 — `Wait` returns immediately (reporting; already fixed)

`AutoPilot.Wait` loops while `Error > stoppingAngleThreshold || ω > stoppingVelocityThreshold`.
The direction-only error path computed:

```
NormAngle(Vector3.Angle(nose, targetDir))
```

`Vector3.Angle` already returns `[0,180]`, and `NormAngle` wraps to `(-180,180]`, so an exact
antipode maps `180 → -180`. The guard `-180 > 1` is false, so a settled, exactly-backwards
craft satisfied the "reached target" condition and `Wait` returned instantly. This is why
inserting `self.wait(3)` "fixed" it — a brief wait drifts the craft microscopically off the
exact antipode (`179.99 → +179.99`), keeping the value positive.

**Fix (applied):** take the absolute value, matching the roll-controlled branch which already
did. Two call sites in `AutoPilot.cs`: `TotalError`'s direction branch and the SAS branch of
`Error`.

#### Problem 2 — arbitrary, momentum-blind flip direction (this proposal)

The controller does **not** hard-stall at the antipode. `GeometryExtensions.FromToRotation`
detects exact antiparallel (`dot ≤ -1 + 1e-10`) and substitutes an arbitrary world-frame
perpendicular axis:

```
perp = |from.x| < 0.9 ? Cross(from, right) : Cross(from, up)
```

so the pitch/yaw error keeps full 180° magnitude — there is no zero or NaN. The defect is
that this axis direction is **arbitrary, discontinuous across the antipode, and blind to any
rotation the craft already has**. The flip is therefore commanded in an essentially random
transverse direction. With the craft sitting at an exact antipode (or arriving at one under a
moving target, as in the prograde→retrograde case `test_orbital_directions` flags as
intermittently exceeding 60 s), this produces an unpredictable and sometimes poor geodesic.

A "kick" (inject a one-shot rate bias to break symmetry) would start motion, but it injects
angular momentum that must later be braked back out, and the right magnitude is
craft-dependent (a low-authority craft needs a large kick, a high-authority one a tiny one).
The better fix injects no energy: it only resolves the *direction* of the existing
full-magnitude command, deterministically and in a way that continues — never fights — any
momentum the craft already carries through the antipode. The existing velocity-profile and
braking logic then does all the work unchanged.

### 1. Setup

Work in the roll-invariant pitch/yaw plane, exactly as the 2D outer law does. After
`ComputeTargetAngularVelocity` builds the error vector from `FromToRotation`
(`dirRotation → angle, axis → anglesRI`, with `anglesRI.y` forced to 0), we have:

- `anglesRI` — the error vector, `x = θ_pitch`, `z = θ_yaw`. Its *magnitude* ≈ `dirError`;
  near 180° its *direction* is the ill-conditioned, arbitrary one described above.
- `dirError = Vector3d.Angle(currentDirection, targetDirection)` — robust at 180°
  (already computed in the roll block; hoist it to the top of the method and reuse).
- `ω_perp` — the current angular velocity's transverse components in the roll-invariant
  frame, `(ω_ri.x, ω_ri.z)`, controller sign convention.
- `α_pitch, α_yaw = torque[i]/moi[i]` — available angular accelerations.

The fix touches only the error *direction* in an antipodal regime; the magnitude and
everything downstream are untouched.

### 2. The rule

Define an antipodal regime by direction error, with hysteresis so it cannot chatter at the
boundary:

```
enter the regime when  dirError > AntipodalEnterAngle   (≈ 178°)
leave  the regime when  dirError < AntipodalExitAngle    (≈ 160°)
```

While in the regime, replace the pitch/yaw error direction `û` (and rescale to `dirError`):

```
if |ω_perp| > AntipodalOmegaEps:          # craft already turning
    û = -ω̂_perp                            # continue the established geodesic
else:                                      # zero-rate start
    û = higher-authority transverse axis   # (1,0) if α_pitch ≥ α_yaw else (0,1)

anglesRI.x = dirError · û.x
anglesRI.z = dirError · û.z
```

That is the whole rule. Magnitude (`dirError`), the 2D speed/braking profile, roll, and the
inner loop are all unchanged.

#### Sign of the momentum branch

Downstream, `ComputePitchYawVelocity` commands `target ω = -ŝ·speed` with
`ŝ = e_stop/|e_stop|` and `e_stop = θ + coeff·ω`. With `θ = dirError·û` and `dirError`
(~π rad) dominating the stopping term `coeff·ω`, choosing `û = -ω̂_perp` makes
`e_stop ≈ -dirError·ω̂_perp`, so `ŝ ≈ -ω̂_perp` and `target ω ≈ +ω̂_perp·speed` — parallel to
the current rate. The craft continues its rotation rather than reversing. As it speeds up,
`coeff·ω` grows, `|e_stop|` shrinks, and `speed` falls off naturally — the same braking the
normal law provides. **This sign depends on the controller's left-handed convention and must
be validated in-game** (prograde↔retrograde must not reverse); if it does, invert `û`.

### 3. Why this composes cleanly

- **No regression surface.** The override fires only above ~178° direction error, so every
  normal slew and hold is byte-for-byte unchanged on every already-calibrated craft.
- **Smooth handoff.** Just below an exact 180°, `FromToRotation` is already well-conditioned
  and momentum-consistent, so `û = -ω̂_perp` agrees with the natural axis there. Inside the
  hysteresis band the override is redundant-but-consistent, not a competing command, and the
  exit-threshold handoff is smooth.
- **`targetNominal` falls out correctly.** `ComputeTargetAngularVelocity` is called twice per
  tick: `target` with the real rate, and `targetNominal` with `ω = 0` (the rate-independent
  setpoint a latched holding axis tracks). With zero omega the override takes the
  authority-axis branch — exactly what `targetNominal` should be. `dirError` is identical in
  both calls, so updating the regime flag is idempotent within a tick.
- **Roll untouched.** Roll control is fully disengaged above 20° error (`RollWeight = 0`), so
  the override never interacts with `anglesRI.y`.

### 4. Implementation notes

All in `AttitudeController.cs`:

- New field `bool antipodalRegime;` alongside the other loop-state fields; cleared in
  `Start()` (and therefore `Reset()`, which calls `Start()`).
- Constants near the existing tuning constants: `AntipodalEnterAngle = 178.0`,
  `AntipodalExitAngle = 160.0` (degrees), `AntipodalOmegaEps = 0.02` (rad/s). The band only
  needs to bracket the immediate neighborhood of 180° where `FromToRotation` is degenerate;
  these are tunable.
- Hoist `dirError` to the top of `ComputeTargetAngularVelocity` and reuse it in the existing
  roll block (currently recomputed there).
- Insert the regime check / override immediately after `anglesRI.y = 0;`.

`FromToRotation` itself is left as-is: its arbitrary-perpendicular fallback is a reasonable
generic default, and it has no access to the controller state (rate, torque, MoI) needed for
a meaningful choice. The selection belongs in the controller.

### 5. Verification

This is a C# server change — rebuild/reinstall the mod and restart the game (per CLAUDE.md):

1. `pkill -f KSP.x86_64`, then `nohup bash tools/run-ksp.sh &` from the repo root; poll
   `krpc.connect()` until the server is up.
2. `test_antipodal_flip` passes with the `self.wait(3)` workaround removed:
   `(cd service/SpaceCenter/test; python -m unittest
   test_autopilot.TestAutoPilotAttitude.test_antipodal_flip -v)`.
3. Momentum sign / no-reverse: spot-check `test_orbital_directions` (prograde↔retrograde) on
   `TestAutoPilotAttitude` reaches the target without reversing or stalling. If it reverses,
   invert the `û = -ω̂_perp` sign.
4. Regression smoke: the broader `TestAutoPilotAttitude` slew/hold tests plus a low-authority
   class (`TestAutoPilotAttitudeSlow`) confirm the >178° gate leaves normal maneuvers
   untouched.

## Antipodal-flip out-of-plane instability

*Originally `antipodal-flip-plane-instability.md` — done, root cause found and fixed with a plane-latch extension 2026-07-01.*

**Status (original):** done (2026-07-01) — root cause found and fixed with a plane-latch extension (no
authority reduction); orbit-sweep holds plane to ~0.5° everywhere.
**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` (`ResolveAntipodalAxis`).

---

### TL;DR

A commanded 180° "antipodal" flip (e.g. east→west, level) completes the heading but the nose bows
out of plane during the slew — up to ~32° at seed 0.08, and **~61° as the seed → 0 (a from-rest
flip)**, deterministically per orbital position.

**Root cause:** the direction-error axis `â = FromToRotation(current, target)` — the live geodesic
plane normal — **precesses fastest exactly when current and target are near-antipodal**, and the
vessel unavoidably *crawls* through that region while the rate loop ramps the angular velocity up
against inertia. The controller tracks that precessing axis, so the commanded rotation plane rotates
under the nose and pumps it out of plane. The slower the traverse of the near-antipode region, the
more pump accumulates — which is why a **from-rest / lightly-seeded** flip (longest crawl) bows most,
a strongly-seeded flip (fast traverse) bows least, and a **90° slew — never near-antipodal —** is
clean at every orbital position and every seed.

**Fix:** extend the existing antipode plane-latch (`ResolveAntipodalAxis`) to *hold the committed
flip plane through the whole crawl region* instead of releasing at 15°:
- **Widen the band** to `AntipodeBlendAngle = 50°` and hold the latched plane **fully** within
  `AntipodeHoldAngle = 35°` of antipodal (spanning the pump zone, err ~145–180), then smoothstep back
  to the live geodesic axis between 35° and 50° for a continuous hand-back.
- **Latch even from rest:** lower `AntipodeLeadRate` to `0.004`; latch the plane from the
  perpendicular rate when the vessel is already turning, else from the (arbitrary-but-consistent)
  geodesic axis. Either way a *fixed* plane is held rather than the precessing live axis.

The latched plane is a great circle through the current nose and its antipode = the target, so
holding it still carries the nose to the target — no authority is reduced and the flip runs at full
`MaxAngularVelocity`.

**Result (in-game orbit sweep, seed 0.08, full authority):** peak out-of-plane **0.4–0.6° at every
orbital position** (was 0.4°→32°); at seed 0.01 (near from-rest) **0.6°** (was 61°). 90° slews
unchanged (~0.2°).

---

### What it is NOT (rejected hypotheses)

- **Gyroscopic amplification / gyro feedforward (the original diagnosis).** Disproved in-game: the
  `gyro` feedforward is ≈0 throughout the flip (a near-single-axis spin, so `ω×(Iω)`≈0), and
  `|ω_inertial| ≈ |ω_relative|` to 4 decimals (the surface-frame term is only planet spin ~8e-5
  rad/s). "Use inertial ω in the gyro FF" corrects a negligible term — a red herring.
- **Joint-law cross-track dilution + a rate cap (a mid-investigation attempt).** A rate-schedule cap
  *made it worse*: slowing the vessel makes it crawl through the near-antipode region longer, so the
  precession pump accumulates more. Reverted. The rate-dependence is real but the cure is to stop
  chasing the precessing axis, not to slow down.
- **A bad seed / test artifact only.** The tiny 0.08 seed is unrealistic, but it exposes a genuine
  deficiency: a realistic *from-rest* 180° flip bows ~61°. Raising the seed hides it (momentum
  carries the plane); the controller fix removes it at the source.

The **antipode singularity** (`FromToRotation` ill-conditioned at exactly 180°) was a separate,
already-fixed issue — the *same* latch, which this change extends — covered by the minimal-change
design in the section above. Note the original diagnosis doc
also recorded "larger seed makes it worse"; that was an artifact of a since-fixed test-harness bug
(the pod auto-crewed with a non-pilot → "partial control" → flips that didn't reliably slew after a
warp). With that fixed (`SetCrewToPilot`, committed separately) a larger seed clearly *helps*.

---

### Evidence (in-game, `AutoPilot` craft at Eve, full authority)

Seed sweep at a bad orbital position, 180° flip peak out-of-plane (degrees), **before** the fix:

| seed | 0.01 | 0.02 | 0.05 | 0.08 | 0.15 | 0.30 | 0.50 | 0.80 |
|------|------|------|------|------|------|------|------|------|
| 180° | 61.5 | 23.3 | 21.9 | 20.2 | 14.3 | 5.7  | 2.0  | 0.8  |
| 90°  | 0.2  | 0.2  | 0.2  | 0.2  | 0.2  | 0.2  | 0.2  | 0.2  |

Monotonic in seed (faster traverse → less pump), and 90° immune — the crawl/precession signature.
Decomposing the measured rate about the live `â` shows the out-of-plane component being *pumped*
positive during err 170→147 (the crawl) then recovering — a tilted-great-circle bow peaking mid-flip.

**After** the fix, full-orbit sweep at seed 0.08: peak out-of-plane 0.4–0.6° at all 12 sampled
positions (worst 0.0105, limit 0.10), every flip slewing to the target.

---

### Files touched (this fix)

- `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` — `ResolveAntipodalAxis`: latch from rest
  as well as from ω⊥; full-hold within `AntipodeHoldAngle`; widened `AntipodeBlendAngle`; lowered
  `AntipodeLeadRate`.
- `service/SpaceCenter/test/test_autopilot.py` — updated the
  `test_antipodal_flip_holds_plane_over_orbit` comment (root cause + fix).

Committed separately (test-harness bug found alongside): `SetCrewToPilot` RPC + `set_crew_to_pilot`
helper + `setUpClass` call — forces the test pod's crew to Pilot for deterministic full control
(auto-crew otherwise gave "partial control" and unreliable post-warp slews). Kerbal mass is
profession-independent, so calibrated MOI/torque are unchanged.

### Follow-ups (not required)

- Run the other attitude craft (TVC/Nimble/Slow/Chatter/Flexible) — the change only affects
  near-antipodal (>130°) slews, so low regression risk, but worth a run before merge.
- `AntipodeHoldAngle`/`AntipodeBlendAngle` are tuned on the `AutoPilot` craft at Eve; if another
  craft/orbit shows residual bow, widen the band or the hold angle.
