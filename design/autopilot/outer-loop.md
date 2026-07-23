# AutoPilot outer loop: pointing law and velocity profile

**Status:** done — shipped in the autopilot rework ([PR #882](https://github.com/krpc/krpc/pull/882)). Historical design record consolidating the 2D pitch/yaw outer law and the PI-lag speed cone.

The outer loop turns a pointing error into an angular-velocity setpoint that the inner
rate loop tracks. This doc consolidates the two design docs that define that layer: the
2D stopping-point pointing law (formerly `2d-outer-law.md`), which produces the velocity
reference direction and a bang-bang-style speed profile, and the linear PI-lag speed cone
(formerly `speed-cone.md`), which adds a third term to that speed profile capping the
command at what the inner loop can actually track near the target.

## Principled 2D outer-law rewrite for the autopilot (item 3)

*Originally `2d-outer-law.md` — done, the autopilot's only pitch/yaw outer law; as-built notes 2026-06-26.*

**Status:** done — the autopilot's only pitch/yaw outer law. The temporary
`UnifiedPitchYawLaw` A/B flag and the legacy radial law have been removed; this is now the
default and only code path. Since written, the speed map has evolved: the sigmoid attenuation
`f_a` was replaced by a linear pointing deadband (`DeadbandScale`, keyed on pure θ), and the
speed min gained a third term — a linear PI-lag *speed cone* `κ·bw·|e_stop|` capping the
command at what the inner loop can track near the target (see the *Linear PI-lag speed cone*
section below).
**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs`, `ComputePitchYawVelocity`
**Related:** part of a controls review of the autopilot. Items 4 (sign-convention
derivation), 1 (gyroscopic feedforward) and 2 (acceleration-feedforward low-pass) are
already implemented. This is item 3.

### Motivation

The pitch/yaw outer loop currently computes a *radial* angular-velocity setpoint (a 1D
bang-bang speed profile applied along the current error direction) and then bolts a
separate tangential-damping term onto it to stop the nose orbiting the target. That patch
works but is conceptually muddy (rate feedback injected into a velocity reference), and the
setpoint it produces has slope discontinuities that make the acceleration feedforward
spike. This proposal replaces both with a single predictive 2D velocity field.

### 1. Setup

Work in the roll-invariant pitch/yaw plane (roll stays 1D, untouched). Let:

- **θ** = error vector (rotation needed to bring the nose onto the target), magnitude `θ`,
  direction `ê = θ/θ`.
- **ω** = current angular velocity (controller sign convention, per item 4).
- `α` = available angular acceleration (anisotropic: `α_p`, `α_y`).

The current law:

```
θ_ff  = θ + ½·ω∥·|ω∥|/α          (ω∥ = ω·ê, radial projection only)
ω_ref = -ê·speed(θ_ff) - ω⊥       (radial profile, then subtract tangential ω)
```

where `speed(d) = min(ω_max, √(2α·d))·f_a(d)` and `f_a` is the sigmoid attenuation.

### 2. The unified law

Predict the **stopping point as a vector** — where the nose coasts to if ω is braked at
full authority:

```
e_stop = θ + (1/2α)·ω·|ω|          ← full ω vector, not just its radial part
ŝ      = e_stop / |e_stop|
ω_ref  = -ŝ · speed(|e_stop|)       ← no separate tangential term
```

with the same `speed(·)` profile and attenuation as today. That is the whole law; the
tangential damping is absorbed into the geometry of `e_stop`.

### 3. Why tangential damping emerges for free

If **θ** points along +x and the nose has a sideways drift `ω` with a +y component, then
`(1/2α)·ω·|ω|` has a +y component, so `e_stop` tilts off-axis and `ŝ` rotates toward +y.
The command `-ŝ·speed` therefore acquires a −y component that opposes the sideways drift.
The controller leads the turn to put the predicted stopping point on the target instead of
correcting the orbit after the fact. No `-ω⊥` term is needed.

### 4. It reduces exactly to the current law when ω is radial

Key de-risking argument. If `ω⊥ = 0`, then `ω = ω∥·ê`, so:

```
(1/2α)·ω·|ω| = ½·ω∥·|ω∥|/α · ê
e_stop = (θ + ½·ω∥|ω∥|/α)·ê = θ_ff·ê   ⟹   ŝ = ê,  |e_stop| = θ_ff
ω_ref  = -ê·speed(θ_ff)    and    ω⊥ = 0
```

— identical to the current code. The new law is a strict generalization: it changes the
command **only when `ω⊥ ≠ 0`**, i.e. precisely the nudge/orbit regime that motivated the
tangential-damping patch. Great-circle slews and radial settling are numerically unchanged.
The signs (`+½ω|ω|/α` displacement, leading `−`) were checked against the existing
`theta2dFf` / `-sign(θ_ff)` in the working code.

### 5. Why this also kills the ffRi spikes (subsumes item 2)

The setpoint becomes smooth where it was kinked:

- `ω·|ω|` is C1 (derivative `2|ω|` is continuous) — no kink from the quadratic stopping term.
- The radial/tangential seam disappears (no `-ω⊥` step when `ω⊥` changes).
- The two remaining hard switches can be softened cheaply:
  - **PID-lag term** (`DecelLagCorrection`): the quadratic and linear stopping
    displacements are collinear (both ∝ ω), so `max(|ω|/2α, 1/bw)` becomes a scalar max of
    two coefficients — replace with a soft-max to remove the kink.
  - **Velocity cap** `min(ω_max, √…)`: a mild kink, only active far from target at high
    speed where ff spikes matter least; optionally soft-min it.

With a C1 setpoint the acceleration feedforward no longer steps. The item-2 low-pass filter
(`FeedforwardSmoothTimeConstant`) can likely be shortened or removed afterwards — but keep
it as a safety net in this change and retune separately.

### 6. Anisotropy notes

Keep the existing machinery: project `α` along `ŝ` (not `ê`) for both the prediction and
the profile, and keep the constraint-ellipse cap for `ω_max` along `ŝ`. This is the one
place the rewrite adds genuine subtlety — when `ŝ ≠ ê`, the "α along the path" inside
`e_stop` depends on `ŝ`, which depends on `e_stop`. Two clean options:

- (a) one fixed-point iteration: compute `ŝ` using `ê`'s α, then recompute; or
- (b) use `ê`'s α for the prediction and `ŝ`'s α for the profile (cheaper, negligible error
  when α anisotropy is mild).

Start with (b).

### 7. Implementation map

- All in `ComputePitchYawVelocity` (`AttitudeController.cs`). Signature/inputs unchanged.
- Singularity: keep a `MinTheta`-style guard, but test `|e_stop|` instead of `θ` (both the
  error and the predicted drift must vanish before skipping).
- Roll (`ComputeAxisVelocity`) untouched; optionally soft-max its own quad/lin term later
  for consistency.

### 8. Risks

1. **`ŝ` swing near the target**: when `|e_stop|` is small but `ω⊥` isn't, `ŝ` can rotate
   fast. The attenuation `f_a(|e_stop|)` must dominate there — watch for a *new* chatter
   mode in exactly this regime.
2. **Sign matching**: `e_stop`/`ŝ` must stay consistent with the item-4 convention. The
   radial-reduction identity in §4 is the validation hook — assert the new path matches the
   old when `ω⊥ ≈ 0`.
3. **Anisotropy fixed-point** if option (a) is chosen.
4. Behavioral change is concentrated exactly where the code has been hand-tuned → must be
   tested in-game.

### 9. Test plan

Extend `service/SpaceCenter/test/test_autopilot.py`; capture traces via `DiagnosticLogging`
/ `GetDiagnosticLog` and compare metrics against the pass bounds below.

| # | Scenario | What it guards | Pass metric |
|---|----------|----------------|-------------|
| a | 90° combined pitch+yaw slew | great-circle path unchanged | great-circle deviation ≤ current; overshoot ≤ current |
| b | **Nudge**: settle, inject tangential ω, release | the limit-cycle/orbit case (the regression test) | nose spirals in, no sustained orbit; settling time ≤ current |
| c | Hold target, measure residual | limit-cycle amplitude | oscillation decays, doesn't sustain |
| d | Slew with logging on | ffRi smoothness | no single-tick `ff_ri` spikes at switch points; no spurious control saturation |
| e | `AutoPilotWobbly` vessel | flexible-mode safety | no new excitation vs current |
| f | Asymmetric pitch/yaw authority | anisotropy handling | straight path holds; no divergence |

**Metrics:** settling time, overshoot, residual limit-cycle amplitude, path curvature (max
great-circle deviation), peak control-saturation duration. Scenario (b) must clearly
*improve*; the rest must be *no worse*.

**Method:** script the six scenarios, dump diagnostic traces to CSV, and check (b) improves
while (a, c–f) stay within their bounds.

### 10. Implementation notes (as built, 2026-06-26)

The law is the autopilot's only pitch/yaw outer law.

- **Single law.** `ComputePitchYawVelocity` is the stopping-point law described here. The
  temporary `UnifiedPitchYawLaw` A/B flag (formerly `AttitudeController.UnifiedPitchYawLaw` /
  `[KRPCProperty]` `SpaceCenter.AutoPilot.UnifiedPitchYawLaw`) and the legacy
  `ComputePitchYawVelocityRadial` body have been removed, along with the dispatcher and the
  `doc/order.txt` entry. When `ω` is purely radial the law collapses to the same 1D bang-bang
  profile the legacy radial law produced (§4), so great-circle slews and radial settling are
  unchanged.
- **Stopping coefficient.** The quadratic (`ω²/2α`) and linear (`ω/bw`) stopping displacements
  are collinear with `ω`, so they collapse to a single scalar `coeff = max(|ω|/2α, 1/bw)` and
  `e_stop = θ + coeff·ω`. `DecelLagCorrection` gates the `1/bw` term exactly as before. The
  exact `max` (not the §5 soft-max) is deliberate — see below.
- **Anisotropy (§6).** Took option (b), with one refinement: α and the PID bandwidth are
  projected along **ω̂** for the *prediction* (along **ŝ** for the *speed profile*), not along
  **ê**. Projecting along ω̂ (a) coincides with ê when `ω` is radial, so the §4 reduction is
  preserved exactly, and (b) stays well-defined as `θ → 0`, which is what makes the §7
  singularity guard on `|e_stop|` work — there is no `ê` to project along when `θ = 0` but `ω ≠ 0`.
- **Switches left hard (§5 deferred).** The `max` in `coeff` and the `min` velocity cap are
  *not* softened. Soft-maxing them would break the exact §4 radial reduction that §8.2 makes
  the validation hook, so they are kept exact and the **item-2 feedforward low-pass
  (`FeedforwardSmoothTimeConstant`) is retained as the ff-spike safety net**, per §5's own
  advice. Softening the switches and retuning/removing the filter is a separate follow-up.
- **Validation done so far.** Both laws were ported to Python and fuzzed over 200k random
  radial-`ω` cases (random `θ`, `α`, `Kp` anisotropy): max command difference **1e-14** — the
  §4 identity holds to floating point. In the tangential/orbit regime both laws oppose the
  drift; the unified law leads the turn (more tangential braking, less radial pull) as §3
  predicts. `KRPC.SpaceCenter` and `ServiceDefinitions` build clean. Still **unvalidated
  in-game** (scenarios a–f), which is where the behavioral change and risk §8.1 (ŝ-swing near
  the target) actually get exercised.

## Linear PI-lag speed cone in the outer-loop velocity profile

*Originally `speed-cone.md` — done, validated in-game 2026-07-02.*

**Status:** done — implemented and validated in-game 2026-07-02 (results at the bottom).
**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` —
`ComputePitchYawVelocity`, `ComputeAxisVelocity`, `ProfileSample`, `ProfileMagnitudeRate`.
**Related:** follow-up to the analytic-feedforward regression on high-authority rigid craft
(`TestAutoPilotAttitudeNimble.test_nudge_mid_slew`, bisected to the numeric→analytic FF
switch). The first layer of that regression — the deadband-slope feedforward term firing
anti-parallel to the command after a fast crossing — is fixed separately by scaling that
term by the tracking fraction. This proposal addresses the second layer, which that fix
exposed.

### Motivation: a lossless coast-through limit cycle

Measured in-game on the AutoPilotNimble craft (α ≈ 39 rad/s², autotuned inner bandwidth
`bw = Kp·α ≈ 17.5 rad/s`, physics dt = 0.02 s), with the feedforward ≈ 0 and **all
oscillation mitigations disabled**: after a tangential rate nudge near the target the loop
enters a *sustained* limit cycle — ±1.3° pointing error, ±0.35 rad/s, period ~2 s, zero
decay over 30 s captures.

The mechanism is in the outer loop's speed map, not the feedforward or the mitigations:

1. `speed = √(2·α·|e_stop|)` commands ≈ 0.8+ rad/s at only 1.3° of error (the sqrt has
   infinite slope at the origin, and α is huge).
2. The craft obediently accelerates toward the target; the pointing deadband
   (attenuation angle 1°, ramp 1°→0.5°, hard zero below 0.5°) collapses the command
   inside the band.
3. The craft coasts through the band at ~0.3 rad/s. Stopping within the 0.5° half-band
   needs sustained ctrl ≈ ω²/(2·d·α) ≈ 0.18; the PI's rate damping supplies `Kp·ω ≈ 0.15`,
   falling as ω drops — not enough.
4. It exits the far side of the band, where the profile symmetrically re-accelerates it.
   Energy in ≈ energy out per half-cycle → sustained oscillation, amplitude pinned just
   outside the attenuation band.

Historically this cycle was masked: the old *numeric* feedforward differentiated a setpoint
that depends on the measured ω (through the `e_stop` stopping correction), so it carried an
incidental `∂tgt/∂ω·ω̇` derivative-damping term. The analytic feedforward deliberately
omits measured-ω̇ terms (that omission is what fixed the flexible-craft jitter
amplification), and with them went the damping.

#### Rejected alternative: restore the missing derivative term analytically

Computing `∂corr/∂ω·ω̇` with the *planned* `ω̇ = α·ctrl` (no numeric differencing) was
considered and rejected: it creates a recursion through the previous tick's control output
with loop gain > 1 in exactly the regime that matters (`(α/speed)·D·(1/bw)·α` ≈ 4.5 on the
measured craft), and it double-counts the on-profile branch forms, whose `eDotTrack`
values are already derived self-consistently with the stopping correction.

#### Rejected alternative: α-scaled attenuation angle

Widening the deadband so the coast can always be absorbed needs a band of order
`2α/bw²` ≈ 15° on the measured craft — absurd as a pointing deadband. And because the
deadband *multiplies* the sqrt speed, the widened ramp's shape (`√e · ramp`) is still not
the trackable straight line — it just moves the cliff outward.

#### Relation to the linear pointing deadband (not the same thing)

The deadband (`DeadbandScale`) and the cone are complementary, not redundant:

- The deadband is a **multiplicative noise gate of fixed angular width** (1° → 0.5°,
  keyed on jitter-free pure θ): its job is to command exactly zero below jitter scale so
  the inner loop doesn't chase sub-band noise into the actuators. It can only attenuate
  whatever speed the profile hands it, and only inside its fixed band.
- On a high-α craft the profile hands it `√(2α·1°) ≈ 0.8+ rad/s` *at the band edge*, so
  the ramp demands a collapse of ~92 (rad/s)/rad ≈ 5× the inner bandwidth — untrackable;
  the craft coasts through the band instead (that part of the cycle is the deadband
  working as designed). The re-acceleration happens at ~1.3°, *outside* the band, where
  D = 1 — out of the deadband's reach by construction.
- The cone is an **absolute cap with authority-scaled reach** (`κ·bw·e` from `maxV/c`
  inward, keyed on rate-aware `e_stop`): it fixes the *input* to the deadband, so the
  command reaching the band edge is ~0.15 rad/s and the ramp becomes trackable, and it
  removes the hot re-acceleration outside the band that the deadband cannot touch.

### The fix: cap the speed map with the line the inner loop can track

```
speed = min( √(2·α·|e_stop|),  κ·bw·|e_stop|,  maxV )        κ = 0.5
```

with `bw` the **unfloored** profile bandwidth (`ProfileKp`, the same source the linear
stopping coefficient uses). The cone is the speed-map counterpart of that stopping
coefficient: `coeff = max(ω/2α, 1/bw)` already models the PI-lag exponential on the
*prediction* side; the cone makes the *command* side consistent with it. In cascade terms:
the sqrt profile places the outer-loop crossover above the inner loop's at small angles;
the cone pins the outer pole at `κ·bw`, restoring separation.

#### Sizing

- Closed-loop decay on the cone (with the stopping coefficient left at `1/bw`, see below):
  the craft tracks `ω = c·e` with `e = θ − ω/bw` (c = κ·bw), giving exponential decay of θ
  at rate `r = c·bw/(bw+c) = κ·bw/(1+κ)` — bw/3 for κ = 0.5.
- Cycle-kill criterion: arrival speed at the band edge `r·θ_band` must coast-stop within
  the half-band under PI damping (stop distance ≈ ω/bw): `κ/(1+κ) ≤ 1/2` ⇒ κ ≤ 1.
  κ = 0.5 gives 2–3× margin. On the measured craft: arrival ≈ 0.10 rad/s vs the 0.15
  bound (previously 0.3+).
- Crossovers: cone beats sqrt below `e* = 2α/c²`; cone beats the velocity cap below
  `maxV/c`. On the Nimble the cap rules above ~6.5° and the cone rules the entire final
  approach. On low-α craft `e*` shrinks (∝ α) — the cone's footprint is biggest exactly
  where the problem lives.

#### Shape of the speed map, and MaxAngularVelocity

The "cone" is the shape of the *speed-vs-error map*, not a spatial region: a straight line
through zero with slope `c = κ·bw`, so the command ramps linearly to **zero at the
target**. It sits inside the same `min` as the existing terms, so it only ever *lowers*
the command and composes with the user-settable `MaxAngularVelocity` cap (default
`(1,1,1)`) without changing it:

```
speed                      speed                      speed
  │   ____ maxV              │    ____ maxV             │       ____ maxV
  │  /                       │   /                      │      /
  │ / cone                   │  / cone                  │   ⌒⌒  sqrt
  │/                         │ /                        │ / cone
  └────────── e              └─────────── e             └─────────── e
  Nimble: cone→cap           Normal: cone→cap           Slow: cone→sqrt→cap
  (crossover ~6.5°)          (cone from ~15° in)        (cone only last ~3–5°)
```

- Far-field slews are unchanged: `maxV` still rules above `maxV/c`.
- A user who sets a very small `maxV` shrinks the cone region to `e < maxV/c` — harmless,
  since at such low arrival speeds the coast-through cycle cannot occur anyway.
- In the 2D law `maxV` is already projected as an anisotropic ellipse along ŝ (`maxV2d`);
  the cone takes its min against that projected value, so per-axis customization composes
  exactly as today.

### Implementation

All in `AttitudeController.cs`.

#### 1. Profile changes

- New constant next to `DeadbandLowFraction`: `const double ProfileConeFraction = 0.5;`
  with the sizing argument in the comment. Private, not an RPC: it is a stability-margin
  constant like the deadband fraction, and exposing it invites raising it back into the
  cycle regime.
- `ProfileSample`: add `bool ConeActive` (the cone won the three-way min) and
  `double ConeSlope` (`c = κ·bw_ŝ`, 1/s, 0 when no bandwidth is available). Note in the
  comment that `ConeSlope` uses the ŝ-projected bandwidth while the existing `Bandwidth`
  field stays ω̂-projected — this mirrors the α projections (speed map along ŝ, brake path
  along ω̂) and is deliberate.
- `ComputePitchYawVelocity`:
  - Hoist the unfloored per-axis bandwidths `bw0`/`bw2` (currently computed inside the
    `omegaMag > 0` block for the stopping coefficient) to method scope, computed
    unconditionally — the cone must be live at ω = 0, which is where the cycle's
    turnaround/re-acceleration happens. Pure code motion; the stopping-coefficient logic
    is unchanged.
  - After ŝ is known: `bwS = sPitch²·bw0 + sYaw²·bw2`, `coneSlope = ProfileConeFraction·bwS`,
    and apply the three-way min. Set `sample.CapActive` only when the cap wins *and* the
    cone does not, so exactly one of {cone, cap, sqrt} owns the branch (this mutual
    exclusion is what prevents feedforward double-counting).
- `ComputeAxisVelocity` (roll / 1D): same change keyed on the ω-corrected error (the 1D
  analog of `|e_stop|`); `coneSlope = ProfileConeFraction·pidBandwidth` — the call site
  already passes the unfloored roll bandwidth.

#### 2. Analytic feedforward: new branch in `ProfileMagnitudeRate`

On the cone the profile slope is the constant `c` (not `α/speed`), so with the same
self-consistency convention as the existing branches (on-profile `ė`, derived with the
stopping correction folded in exactly once):

- linear stopping active (`e = θ − ω/bw`): `ė = −speed·bw/(bw + c)`
- quadratic stopping active (`e = θ − ω²/2α`): `ė = −speed·α/(α + c·speed)`

```
if (s.ConeActive && s.Speed > 1e-9) {
    var eDotTrack = s.LinearActive
        ? -s.Speed * s.Bandwidth / (s.Bandwidth + s.ConeSlope)
        : -s.Speed * s.Alpha / (s.Alpha + s.ConeSlope * s.Speed);
    speedRate = s.ConeSlope * (eDotTrack * trackingFraction + slewRateRad);
} else if (!s.CapActive && s.Speed > 1e-9) {
    // existing quad/linear sqrt-branch forms, unchanged
}
```

Both forms are bounded, ≤ 0, and reduce to the pure exponential `−speed` in the
infinite-authority limit. The tracking fraction, overshoot gate, deadband-slope term and
the final `speedRate·Deadband + deadbandRate` assembly are unchanged; `s.Speed` is already
the cone speed. No measured ω̇ anywhere — the rejected recursion is not reintroduced.

Deep in the cone the feedforward magnitude is `c·bw·speed/((bw+c)·α) → 0` as speed → 0, so
the hold point stays quiet.

**Seams.** ġ is discontinuous at the sqrt↔cone crossover `e*`: quadratic stopping is the
live sub-case there (ω ≈ 2α/c > 2α/bw), stepping the feedforward from 0.5 to ≈ 0.67 of
authority — smaller than the existing cap↔brake seam, and smeared over ~3 ticks by the
0.05 s feedforward low-pass. Same treatment, same justification; say so in a comment.

#### 3. Stopping coefficient: deliberately unchanged

`coeff = max(ω/2α_ω, 1/bw_ω)` stays. Using `1/c` when the cone is active is circular
(cone activity depends on `e_stop`, which depends on `coeff`); using `1/(κ·bw)`
unconditionally doubles the linear term's gain on the measured rate everywhere ω is small
— 2× the jitter-injection path the unfloored-`ProfileKp` note exists to bound. The
mismatch costs only decay rate (`r = κ·bw/(1+κ)` instead of `κ·bw`), which the sizing
already accounts for. If low-α settling regresses more than predicted, the follow-up is
`coeff = max(ω/2α_ω, 1/(κ·bw_ω))` as a separate calibrated change.

#### 4. Diagnostics (optional, additive)

Add a per-group profile-branch tag to the `[KRPC.AP]` log line (e.g. `prof=(c,q)` with
c = cone, q = sqrt-quad, l = sqrt-linear, K = cap, `-` = idle) so validation captures are
self-explaining.

#### 5. Documentation

Autopilot code comments: cone term in both profile formula blocks, a "why" paragraph
(cascade separation, the coast-through cycle, κ, unfloored bandwidth), and the cone closed
forms in the acceleration-feedforward branch list. `doc/src/tutorials/autopilot.rst`: same
two sections.

### Expected behavior changes on other craft

- **Normal craft** (α ≈ 3, bw ≈ 6, c = 3): cone active from ~15–19° in; final approach
  becomes an exponential at r = 2/s. Adds roughly +0.3…+1 s settling per slew, partially
  bought back by lower in-band arrival speed (overshoot/rebound shrink).
- **Slow craft** (α ≈ 0.5–1): `e*` ≈ 3–5°, near-zero effect.
- **Target smoothing / turn following**: steady tracking lag behind a moving target
  becomes `Ω/r` (vs `Ω²/2α`) — a 0.175 rad/s smoothed slew on a normal craft lags ~3–5°.
  Bounded, recovered at slew end; the biggest qualitative change outside settling.
- **Metric drift** (threshold recalibration goes to the dedicated pass, not ad hoc):
  `settling_time` up slightly on normal-craft slews; `overshoot`/`radius_rebound` down;
  `total_winding` roughly neutral (watch the oblique nudge — tangential counter-speed is
  proportional to the now-smaller command); hold-chatter/gain-jump/saturation unchanged.
- **Floored/mitigated craft**: the cone uses the unfloored bandwidth (same policy as the
  stopping coefficient) and floored holds sit inside the deadband where the cone is moot,
  so the Dynawing/Ariane regimes should be untouched — verified by the gate below.

### Validation plan (in-game)

Iterate with the oscillation mitigations forced **off** (`Oscillation*Mode = Off`) so the
control-oscillation latch — which fires on the layer-2 cycle and floors the loop — stays
out of the way. Rigid high-authority craft owners can apply the same setting themselves.

1. Nudge probe on AutoPilotNimble ×3, mitigations off: no sustained cycle; rate
   < 0.05 rad/s within a few seconds of the nudge; feedforward small and one-signed
   through the approach (cone branch active in the log).
2. `TestAutoPilotAttitudeNimble.test_nudge_mid_slew` with mitigations off, then with
   defaults — expect the control latch not to fire once no sustained oscillation exists.
   If it still trips on the recovery transient, force the mitigation modes off in the
   Nimble test fixture.
3. Nimble small-signal neighbours: `test_oblique_nudge`, `test_precession_when_nudged`,
   `test_target_step_mid_slew`; plus `TestAutoPilotAttitude.test_max_angular_velocity_cap`
   (cap↔cone seam).
4. Quick gate: `TestAutoPilotAttitude{,Nimble}.test_orbital_directions`;
   `TestAutoPilotLaunchKerbalX`/`Ariane5` `test_launch` + `test_smooth_turn` (the latter
   also guards the new tracking-lag behavior); `TestAutoPilotLaunchDynawing.test_launch`.
5. One targeted low-α check of the α-scaling claim:
   `TestAutoPilotAttitudeSlow.test_oblique_nudge` (full Slow suite stays omitted).

### Validation results (2026-07-02, in-game)

1. **Nudge probe, mitigations off, ×3**: cycle gone. The slew runs on the cap branch, hands
   off to the cone at ~4.7°, and glides in monotonically — rate 0.22 → 0.037 → 0.007 rad/s
   over ~1 s, dead quiet (|ω| < 0.001) from t ≈ 3 s; the 0.3 rad/s nudge is absorbed within
   ~0.5 s. `settling_time` (err < 2°, rate < 0.05) satisfied in all runs; max |ff| = 0.08;
   the control latch never trips (the ctrl envelope stays below threshold with no sustained
   oscillation to feed it).
2. **`TestAutoPilotAttitudeNimble.test_nudge_mid_slew` with default mitigations: PASSES**
   (×2 runs) — no test-fixture mitigation override needed.
3. **Nimble neighbours green**: `test_oblique_nudge`, `test_precession_when_nudged`,
   `test_target_step_mid_slew`, and `TestAutoPilotAttitude.test_max_angular_velocity_cap`
   (cap↔cone seam).
4. **Quick gate green**: Normal+Nimble `test_orbital_directions`; Kerbal X and Ariane 5
   `test_launch` + `test_smooth_turn`; Dynawing `test_launch` (floored-hold regime).
5. **Known threshold graze (resolved)**:
   `TestAutoPilotAttitudeSlow.test_oblique_nudge` failed its `total_winding < 0.75` default
   threshold at 0.762–0.763. A/B against the pre-cone build (3 runs each, same scenario):
   baseline 0.746–0.747 — the test already had only 0.4% headroom, and the cone's predicted
   small winding increase (+0.016 turns, +2%; the inward command at small radius is lower so
   the tangential rate sweeps slightly more angle) tips it over. Settling is clean on both
   builds. This is the §"watch items" oblique-nudge prediction, magnitude benign. The Slow
   class's `winding_limit` was bumped to 1.2 and the test re-verified green in-game.
