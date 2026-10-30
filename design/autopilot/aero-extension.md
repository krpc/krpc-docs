# Design proposal: extending the autopilot to aerodynamic flight

**Status:** done in [PR #1191](https://github.com/krpc/krpc/pull/1191), fixing
[#526](https://github.com/krpc/krpc/issues/526). The [Still open](#still-open-1) items under Port
findings were not part of it. Phase 1 measurements done (2026-10-24); the first set of changes
ported and tested (2026-10-25). See
[Phase 1 findings](#phase-1-findings-2026-10-24) and [Port findings](#port-findings-2026-10-25),
which supersede parts of sections A, D, E and the roadmap below.
**Scope:** `service/SpaceCenter/src/AutoPilot/` (AttitudeController, OscillationDetectors,
MitigationPolicy), `service/SpaceCenter/src/Services/AutoPilot.cs`,
`service/SpaceCenter/src/Services/Parts/ControlSurface.cs`
**Related:** builds on the control-loop redesign ([`inner-loop.md`](inner-loop.md)) and the
oscillation-mitigation calibration ([`oscillation.md`](oscillation.md)). Two sibling proposals
extend the same asymmetric/aero-authority theme: [`bank-to-turn.md`](bank-to-turn.md) (roll so the strong
axis flies a heading change on a weak-yaw craft) and [`heterogeneous-actuators.md`](heterogeneous-actuators.md) (split a
single axis's command across fast and slow actuators). Section E below is the home of the
slow-actuator handling those docs build on.

## Decided: build it, on the game's pitch/yaw/roll inputs

The go/no-go question (build here, or defer to a MechJeb integration) is settled: build it. Phase 1
showed most of the aircraft failures come from wrong plant figures and an unmodelled actuator law,
which are cheap to fix in kRPC's own controller.

The built-in auto-pilot keeps commanding the game's aggregate pitch, yaw and roll inputs and
models how the game distributes them. Per-actuator allocation is left to user scripts, which the
`ControlSurface` RPCs support. See [`heterogeneous-actuators.md`](heterogeneous-actuators.md).

## Phase 1 findings (2026-10-24)

Method: the basic loop (stopping-point profile, autotuned PI per axis) reimplemented as a server
side function and streamed every tick, so the control law could change without restarting the game.
Steps in pitch (10°), roll (30° bank), heading (5°) and a turn (bank 30°, heading +30°, roll level),
plus a pitch-step speed sweep, on three stock aircraft:

| Craft | Mass | Pitch MoI | Character |
|---|---|---|---|
| Aeris 3A | 5.6 t | 23 t·m² | stiff, high authority |
| Thunderbird | 14 t | 90 t·m² | middle |
| Mallard | 37 t | 1500 t·m² | low elevator authority, long wings |

### Plant figures were wrong (fixed)

| Defect | Effect | Fix | Verified |
|---|---|---|---|
| `Vessel.MOI` (and kRPC's own tensors) take each part's parallel-axis offset from its origin, not its CoM | Aeris pitch MoI 39% high, roll 10% low | Compute about `rb.worldCenterOfMass`, flight and editor | Reaction-wheel spin-up in vacuum: 1.000-1.002 on every axis of two craft |
| Stock `ModuleControlSurface.GetPotentialTorque` multiplies `r × ΔL` component-wise by the lever arm (`Vector3.Scale`) | Each axis scaled by the arm along that same axis: Mallard pitch 3.2× high, some yaw fins 0.46× | Form `r × ΔL` from `GetPotentialLift` | Early change in applied aero torque (`Flight.AerodynamicTorque`) matches prediction × measured deflection within 2% (pitch), 2-18% (roll, yaw) |

Also added `ControlSurface.DeflectionAngle` (read back), `ControlRange` and `ActuatorSpeed`. The
readback shows deflection is an exact linear ramp at `ActuatorSpeed` up to `ControlRange`.

Fixing the figures alone made the Mallard worse with the built-in controller: its gains rose 3×,
and its 0.6 s surface swing then rate-limits large commands into a limit cycle. The figures were
low enough before to hide this.

### The game's roll law

For roll the game deflects each surface by `clamp(K × roll input)`, K growing with the surface's
lateral distance from the CoM (about 0.26-0.5 × the distance in m, from geometry in
`FixedCtrlSurfaceUpdate`). Measured on the runway:

| Craft | Surface | K | Full deflection at roll input |
|---|---|---|---|
| Mallard | ailerons at 10-12 m | 3.4-3.9 | 0.27 |
| Aeris 3A | elevons at 3.3 m | 1.6 | 0.6 |
| Thunderbird | elevons / canards | 2.1 / 0.31 | 0.5 / never |

Roll torque is piecewise linear in the input. On the Mallard the small-signal gain is several times
the assumed one, which drove a ±60° roll limit cycle. `AvailableTorque` assumes full deflection, so
it overstates roll torque where K < 1 (Thunderbird by about 37%). Pitch and yaw deflection is the
input projected onto the hinge axis, at most 1.

### Controller changes that worked

| Change | Replaces | What it does |
|---|---|---|
| Actuator model | E's bandwidth ceiling | Rate-limit each axis's output to `1 / (ControlRange / ActuatorSpeed)` per second, and hold the integral while limited |
| Turn-rate cap | none | Cap commanded pitch and yaw rate at 0.7 × the steady rate the spare control torque holds, estimated from `Flight.SimulateAerodynamicTorqueAt`/`ForceAt` (pitch: lift at the incidence where the restoring moment uses the spare elevator; yaw: side force likewise; roll: rate where aero damping uses the spare torque). Trim is the slow average of the input |
| Roll linearization | none | PI and actuator model work in roll-torque fraction; the output inverts `Σ w·clamp(K·u)` |
| Narrow attenuation band | none | 0.05° instead of 1° on surface-controlled axes, which removes a 0.5° steady offset |

The bandwidth ceiling in E is too blunt: the Aeris and Mallard have the same 0.6 s actuator time,
yet the Aeris is fine at default bandwidth. Rate limiting bites only at large amplitude, so the
actuator model handles it without detuning small signals. A fixed load-factor cap was also tried and
rejected: n = 5 still limit-cycles the Mallard (its elevator holds only 3.3 g at 120 m/s) while a
fighter pulls 8 g or more. The aero-model estimate matches the full-elevator pitch rate measured on
the Mallard (0.20 vs 0.19-0.25 rad/s) and is an upper bound on the Aeris, where 8-14 g bleeds speed.

Results, worst step of each pair (built-in today / prototype):

| Craft | Pitch 10° | Bank 30° | Heading 5° |
|---|---|---|---|
| Aeris 3A | 7%, 0.5° offset / 5%, 1.5 s | 169%, limit cycle / 0%, 1.5 s | 12% / 1%, 1.6 s |
| Thunderbird | 103%, oscillates / 1.4%, 2.1 s | 29% / 0-3%, 1.6 s | departs, AoA 25° (#526) / 0.6%, 1.3 s |
| Mallard | 33%, oscillates / 0.7%, 2.3 s | 43% / 10-15%, rings | 276% / 0.6%, 1.2 s |

Speed sweep (pitch step, 100-300 m/s): the built-in limit-cycles on the Thunderbird and Mallard above
about 150 m/s; the prototype is clean throughout (worst: Aeris at 300 m/s, 7%, 3.8 s).

### Still open

- Mallard roll rings at about 1 Hz after a step (settles in 6-13 s). Likely wing flex; the oscillation
  mitigations in [`oscillation.md`](oscillation.md) target this.
- Heading changes while banked take 9-15 s and climb the nose 11-12°: the controller slews the nose
  by shortest rotation and leaves the turn to the weak yaw axis. Coordinated turns are
  [`bank-to-turn.md`](bank-to-turn.md).
- The online estimator (A) is not needed for the first set: with the figures fixed, α is right to
  within the measurement. It stays relevant for FAR and for trim (B).
- Unmeasured: false latching of the chatter detector at high Q (experiment 2), FAR parity (7).

### Port plan

All four steps are done; [Port findings](#port-findings-2026-10-25) records where the port diverged.

1. The two figure fixes and the `ControlSurface` RPCs (done, with tests).
2. Actuator model, roll linearization (K computed from the game's geometry, roll torque corrected
   by it), narrow band on surface-controlled axes.
3. Turn-rate cap, on by default, with a toggle that leaves only `MaxAngularVelocity`.
4. In-game aircraft step tests on the three craft above, and the full auto-pilot suite as the
   rocket regression gate (the figure fixes change rocket gains too).

## Port findings (2026-10-25)

The C# port into `AttitudeController`, tested in game on five aircraft (Aeris 3A, Aeris 4A, Gull,
Thunderbird, Mallard), the 14 launch craft and the two reentry craft. The rule for the PR: no
rocket ascent may get worse than `main`, and the design stays general. A craft the general scheme
handles less well gets a looser per-craft test limit, not a special case.

### What the port does

| Mechanism | How it works | Diverges from Phase 1 |
|---|---|---|
| Actuator model | Tracks a modeled surface command moving at the surfaces' rate, scaled by their share of the axis's torque. A tick where it lags the command holds that axis's integral and counts toward the back-off. | The command is not clamped. Clamping it also slowed gimbals and wheels on mixed craft. |
| Reversal lag | The stopping distance adds the surface reversal time times the angular velocity relative to the target. | New. Needs a target-rate estimate, see below. |
| Target-rate estimate | Angular velocity minus the rate of change of the error, low-passed at 0.5 s. A rate above 0.2 rad/s counts as a target step and is ignored. | A first, internal part of D. It feeds only the reversal lag, not the command. |
| Bandwidth back-off | Scales an axis's bandwidth down while the actuators lag over 50% of a 2 s window, then recovers at 0.1/s. The lag flags of the body axes are projected onto the roll-invariant pitch and yaw axes. | New. Replaces E's bandwidth ceiling and classifier for this set. |
| Roll linearization | As Phase 1, with K from the game's geometry. | None. |
| Attenuation band | Shrinks with the surfaces' share of the axis's torque. | Scaled by share, not switched. |
| Aero rate cap (`LimitAngularVelocity`) | As Phase 1, with four refinements below. 0.7 × the estimate. | See below. |

The aero cap needed four refinements before rockets flew as well as on `main`:

- **Weight across the flight path, by direction.** Subtracting the full weight in both directions,
  as for a level pull-up, held a climbing rocket's cap at 0. The weight now helps a turn toward it
  and opposes a turn away, so pitch and yaw each have a limit per direction.
- **Thrust.** `T·sin(incidence)` turns the flight path along with the aerodynamic force.
- **Surface share.** The cap divides by the surfaces' share of the axis's torque. An axis with no
  surfaces has no cap, as it has no surface lag to limit-cycle.
- **Floor.** Each pitch and yaw limit is at least the incidence the spare torque holds over 10 s.
  A zero limit in one direction otherwise zeroed the other axis through the limit ellipse.

### Tried and rejected

| Attempt | Why rejected |
|---|---|
| Clamp the command to the surface rate (the Phase 1 actuator model) | On mixed craft it slowed gimbals and wheels as well. The Dynawing's pitch command reversed in 0.5 s and it limit-cycled. Dropping the clamp took aircraft bank overshoot from 12-19% to under 1%. |
| Stricter anti-windup: hold the integral while the unclamped output is past a limit | Stopped the Gull's roll integral winding up through a bank, but slowed rockets out of a saturating launch transient. Orbiter One launch: 1.04-1.13° vs 0.73-0.79° on `main`. |
| Reversal lag on the absolute angular velocity | Penalized steady ramp tracking, where the surfaces never reverse. Kerbal 1 smooth turn: 0.85° vs 0.70° on `main`. |
| Latch the reversal lag, back-off and cap behind a detected surface limit cycle | Aircraft steps overshot 60-350%. A step is not a limit cycle, and the lag and cap must act from the first step. The latch engaged once in 15 step tests. |
| Gate the back-off on the command envelope | Aircraft limit cycles (0.21-0.30) and rocket ramps (up to 0.22) overlap, so no threshold separates them. |
| Lean floor of 2 s | The incidence search tops out at 30°, a 0.26 rad/s floor, above the steady yaw rate. The Thunderbird's rudder limit-cycled. |
| Low-pass the rate in the reversal lag (for the Aeris 4A's 8 Hz pitch chatter) | Overshoot rose to 10-21% and the activity did not drop. |
| Fixed bandwidth ceiling `k / swing time` | Slows high-authority craft. The Aeris 3A and 4A have the same 0.6 s actuator. |
| Back-off and integral hold shared between pitch and yaw | The Aeris 4A's elevator cycle crippled its rudder loop, and a heading step never settled. |

### Results

Aircraft steps, final code (overshoot, settle time):

| Craft | Pitch 10° | Bank 30° | Heading 5° |
|---|---|---|---|
| Aeris 3A | 0.7%, 2.8 s | 0%, 3.3 s | 1.6%, 2.8 s |
| Aeris 4A (100 m/s) | 4.8%, 3.6 s | 0.4%, 3.2 s | 2.5%, 3.1 s |
| Gull (35 m/s) | 0%, 8.1 s | 0%, 3.1 s | 0.8%, 2.3 s |
| Thunderbird | 1.1%, 2.5 s | 0%, 3.4 s | 0.7%, 2.9 s |
| Mallard | 0%, 3.7 s | 0%, 5.6 s | 0%, 4.2 s |

The two reentry tests pass. The Aeris 4A's pitch-upset recovery, skipped on `main`, now passes.

Launch tests, attitude error in degrees (`main` / port), where they differ by more than 0.1°:

| Craft | Test | `main` | Port | Cause |
|---|---|---|---|---|
| Kerbal 1, winglets on | sharp turn | 11.0, limit cycle | 0.08 | Surface model. The test disabled the winglets on `main`; they are now flown as built. |
| Dynawing | sharp turn | 4.2, limit cycle | 0.43 | |
| AeroEquus | launch, sharp turn | 0.63, 1.72 | 0.21, 0.49 | Oscillation after the pitch-over gone |
| Kerbal 1, Kerbal 2 | smooth, jittery turns | 0.70-0.74 | 0.35-0.59 | Reversal lag relative to the target |
| ZMAP | smooth, jittery turns | 0.70-0.74 | 0.97-1.11 | Back-off while its surfaces rate-limit in a turn. Within the default 1.2. |
| Orbiter One | smooth turn | 0.96 | 1.12 | Within spread; no surfaces |

### Info window and user guide

The info window has an AERODYNAMICS section with one row each for the surface share, the rate
limit, the actuator lag, the actuator-limited fraction and the bandwidth cut, on the roll-invariant
axes. Its sections now collapse. The user guide documents the mechanisms under "Aircraft and control
surfaces" and "Control surfaces".

### Test changes

- Kerbal 1 flies with its winglets; the test parameter that disabled control surfaces is gone.
- The Aeris 4A pitch-upset test is no longer skipped.
- AeroEquus limits drop to the defaults apart from a 2° turn error.
- Looser limits, each with a comment: Gull pitch settle 10 s, Learstar A1 turn oscillation 0.5,
  GDLV3 hold oscillation 1.5.

### Still open

- **GDLV3 bending mode.** The actuators at times limit-cycle through its 5 Hz mode, in a hold as
  well as a turn, and the chatter detector does not latch (level 0.2-0.34 vs the 0.6 threshold).
  The craft has no surfaces and its turns cycle on `main` too; a detector issue, see
  [`oscillation.md`](oscillation.md).
- **Dynawing.** An intermittent pitch limit cycle on `main` and the port alike, landing in a
  different test each run.
- **Learstar A1.** Pitch oscillation in a turn is 0.35-0.43 vs 0.29-0.31 on `main`. The corrected
  torque figures raise its gains: `main` overestimated its roll torque about 5×.
- **Aeris 4A 8 Hz pitch chatter** through the elevator rate limit, driven by the controller. A fix
  needs the rate loop's high-frequency phase (the one-tick delay plus the actuator) modeled.
- **Section D in full.** The target-rate estimate exists but feeds only the reversal lag.
- The cap is off under FAR, and a `RollGain` RPC is not exposed.

## Motivation

The redesigned autopilot works excellently for low-AoA ascent guidance and vacuum attitude hold,
including on structurally flexible craft. The next step is aerodynamic regimes:

1. holding attitude of an aircraft;
2. holding a descent trajectory with aero surfaces (e.g. grid fins);
3. more aggressive aero ascents than a smooth gravity turn (low-altitude ballistic trajectories,
   higher AoA);
4. aero surfaces that take time to deflect (slow grid fins / elevators).

**Scope decision:** the service stays an *attitude* controller. It gains velocity-relative target
modes (surface/orbital velocity ± AoA/sideslip/bank offsets) so client scripts can do
trajectory-level guidance against a target the service tracks tightly at 50 Hz; no in-service
trajectory loop. (A guidance layer would be a third cascade level with its own tuning, API and
test surface — revisit only if velocity-relative modes prove insufficient in practice.)

## The unifying observation

Almost everything the controller consumes about the plant reduces to **one per-axis scalar,
α = torque/MoI**: the autotuned gains (`Kp = 2ζω₀·moi/torque`), the profile's peak speed and
stopping distance, the analytic feedforward's normalization, and the chatter detector's physics
bound (`Δω ≤ k·α·dt`). The atmosphere breaks the loop primarily by

- **(a) making that scalar wrong** — control-surface authority scales with dynamic pressure,
  speed, Mach and AoA, and stock `ModuleControlSurface.GetPotentialTorque()` (consumed raw in
  `Parts/ControlSurface.cs`; the code already distrusts the analogous RCS API) is unreliable; and
- **(b) adding torques the model doesn't know about** — trim moments, and the destabilizing
  aero moment at AoA.

So the core change is not a new control structure — it is a **better α in the same slots**, plus
targeted feedforwards for the torques the PI shouldn't have to grind out.

## What breaks, per use case

| Use case | Dominant problems |
|---|---|
| Aircraft attitude hold | **Trim** — a level aircraft needs a steady elevator deflection, today ground out slowly by the PI integral, wandering with speed and sitting off-center against the anti-windup clamp and the oscillation machinery's centered-command assumptions. **Authority mis-estimation** — control surfaces are the *only* torque source on a pure aircraft. |
| Descent-trajectory hold | **Rotating target** — surface-retrograde rotates continuously, fastest exactly when precision matters (near the ground); with no target-rate feedforward the loop carries a permanent lag ≈ target-rate/bandwidth. **Authority variation** — Q sweeps orders of magnitude during the fall. Actuator lag if the fins are slow. |
| Aggressive aero ascent | **Destabilizing aero moment at AoA** — a *negative stiffness* (torque ∝ Q·AoA, growing with the error itself), which no integrator can ground out; the loop's positional stiffness must exceed the aero divergence rate, which requires the autotuned bandwidth to be right, which loops back to authority estimation. Rotating target (pitch program) secondary. |
| Slow aero surfaces | **Actuator lag** — phase loss at the default autotuned crossover (~5.6 rad/s at `TimeToPeak` = 1 s, easily above a slow grid fin's actuator bandwidth) → instability or rate-limit-induced limit cycles, which sit in the sub-Hz-to-~1 Hz band the mitigation machinery associates with structural modes. |

**Cross-cutting regression hazard.** The chatter detector's bound is invalid in atmosphere: aero
moments are not in the available-torque budget, so a *rigid* aircraft maneuvering at high Q can
produce `Δω` jumps the budget can't explain and **false-latch as flexible** — floored to
~1 rad/s bandwidth, which on an unstable airframe is loss of control, not just sluggishness.
Meanwhile the flagship flexible-craft scenario (Ariane 5 ascent) happens *in* atmosphere, so any
detector fix must preserve true latches. Both become standing regression scenarios.

## Control-loop changes

### A. Online per-axis effectiveness/bias estimator (the foundation)

A per-axis recursive least-squares (or equivalent two-state Kalman) fit of

```
ω̇ = α·u + b
```

on the **suppressed** measured rate (bending modes contaminate ω̇) versus the **delivered**
command, with:

- coefficients stored **Q-normalized** above a dynamic-pressure threshold, so they vary slowly
  across a speed sweep and scale automatically with Q;
- the physics torque model (available torque/MoI) as a **regularising prior**, blend weight → 1
  (pure prior) as Q → 0 — in vacuum the estimator is inert and behavior is identical to today
  by construction;
- prior-anchoring solving the quiet-hold identifiability problem (near-constant u makes α and b
  collinear; the prior pins α̂, b̂ absorbs the offset, maneuvers re-excite identification). No
  injected dither — it would fight the chatter machinery.

α̂ then replaces the raw torque/MoI scalar **consistently in every consumer** — autotune, profile
peak speed, stopping-distance feedforward, analytic-feedforward normalization, and the chatter
bound. Consistency matters: the analytic feedforward's on-profile closed forms assume the
profile's own α; mixing estimated and physics α across consumers breaks that self-consistency.

*Rejected alternative:* hand-correcting `GetPotentialTorque()` per known KSP bug — fragile,
stock-only (a measurement-based estimator works identically under FAR), and blind to the
aero-moment term that no `ITorqueProvider` reports.

**Chatter bound fix (part of A).** Subtract the *predicted smooth* angular acceleration
(α̂·u + b̂) from Δω before thresholding, rather than inflating the threshold multiplicatively.
Structural chatter is a tick-to-tick jump the smooth model cannot produce, so true latches
(Ariane in atmosphere) survive while sustained aero moments on a maneuvering aircraft no longer
count against the budget.

### B. Trim feedforward — integral relocation, not model inversion

A slow per-axis trim state that leaks the DC component **out of the PI integral** and into an
open-loop offset summed with the output (the classic auto-trim wheel), stored Q-normalized so it
tracks speed changes without re-learning.

Chosen over deriving trim from b̂/α̂: no dependency on estimator convergence, self-consistent by
construction, and the "slow mean of the delivered command" concept already exists in the
oscillation back-off's trim mean.

Interaction rules:

- **Exempt from the hold-gate feedforward cut** — a DC term cannot excite a bending mode, and
  cutting it would dump the trim back onto a floored integral and drop the craft off attitude.
- Trim and integral leak rates well separated, so the two states cannot pump against each other.
- Seeded from the pre-engagement control state at engagement, so soft-start doesn't dip a trimmed
  aircraft.

Keeping the PI centered also *helps* the back-off envelope's assumptions.

### C. Aero stiffness — no explicit compensation initially

Near a hold, the destabilizing moment is countered as long as loop stiffness ≫ aero divergence
rate; the slowly-varying part folds into b̂/trim. Measure first (phases 1 and 3) whether the
default-bandwidth loop suffices at realistic max-Q AoA. **Contingency:** extend the estimator to
`ω̇ = α·u + k·θ + b` and use k̂ to raise a bandwidth floor keeping ω₀ above the divergence rate —
a gain-schedule fix, not a profile change.

### D. Target-rate feedforward

The velocity profile currently drives commanded ω → 0 at the target; a target that rotates on
its own (surface-retrograde in a descent, a streamed pitch program) is chased with permanent lag.
The only moving-target term today is the user-driven target-smoothing slew rate, which feeds the
analytic feedforward's θ̇ term — that plumbing is the insertion point.

Generalize it to the full rotation rate of the effective target from *any* cause, and add it as a
**base term to the commanded ω**, so at zero pointing error the craft matches the target frame's
own rotation instead of being commanded to stop. Rules:

- the target-rate term **bypasses the deadband attenuation** — it is not error-chasing; without
  this a rotating target parks the craft at the band edge;
- `Wait()`'s stopping-velocity threshold is measured **relative to the target rate**;
- identically zero for static targets → vacuum behavior untouched.

### E. Actuator lag — bandwidth ceiling plus limit-cycle classification

Wrap `ModuleControlSurface.actuatorSpeed` / `ctrlSurfaceRange` (new `ControlSurface` RPCs, useful
regardless — they also feed the per-axis actuator inventory formalised in
[`heterogeneous-actuators.md`](heterogeneous-actuators.md)), derive a per-axis dominant actuator time constant, and add
a **bandwidth ceiling**
to the autotuner — `ω₀·τ_act ≤ ~0.3–0.5`, a phase-margin budget — the mirror of the existing
bandwidth floor. Unlike the floor, the profile's `corrLinear` uses the **ceilinged** gain: the
actuator genuinely cannot do better, so the unfloored-`ProfileKp` exemption logic does not apply.

Teach `MitigationPolicy` a second classification: a detected oscillation at/below the loop
crossover on an **unlatched** axis is a control/rate-limit cycle → respond with adaptive
bandwidth back-off (a temporary ceiling reduction), never with the flexible-craft latch. As with
the existing design, the robust action must not depend on an accurate frequency estimate; the
(weak) estimator is used only for routing.

*Rejected alternative:* lead compensation / actuator inverse — rate limiting is a nonlinear
saturation; lead amplifies command amplitude and *deepens* rate saturation. Respecting the
actuator's bandwidth is the robust choice.

### F. Velocity-relative target modes

Native target modes on the autopilot service: direction = surface/orbital velocity vector ±
AoA / sideslip / bank offsets, computed in-service at 50 Hz — the only place D's target rotation
rate is exact. Client-streamed targets remain supported (target smoothing plus the generalized D
makes them acceptable; native modes make them good). The existing `Flight` aero readouts (AoA,
sideslip, dynamic pressure, with stock/FAR branches) already provide the needed inputs — reuse,
don't duplicate.

## Interactions / regression surface

| Addition | Interacts with | Rule |
|---|---|---|
| α̂ (A) | autotune, profile, feedforwards, detector | Replace torque/MoI in all consumers together; estimator consumes the suppressed rate; vacuum gated to the physics prior → zero vacuum regression by construction |
| Detector bound fix (A) | chatter latch and everything downstream | Ariane 5 ascent must still latch; a rigid fighter at max Q must not — both standing regression tests |
| Trim FF (B) | hold-gate FF cut, anti-windup, back-off trim mean, soft-start | Exempt from the FF cut; separated leak rates; seed at engagement |
| Target-rate FF (D) | deadband, analytic FF θ̇ term, `Wait()`, stopping-distance FF | Bypass deadband; `Wait()` relative to target rate; zero for static targets |
| Bandwidth ceiling (E) | bandwidth floor, `ProfileKp` | Ceiling governs when below the floor; `ProfileKp` uses the ceilinged gain |
| Limit-cycle classifier (E) | `FrequencyTracker`, `MitigationPolicy` | Bandwidth back-off must not depend on an accurate frequency estimate |

## Phased roadmap (each phase independently game-testable)

Superseded in part by [Phase 1 findings](#phase-1-findings-2026-10-24): phase 1 is done, and the port
plan there replaces phases 3 and 5 for the first set of changes.

1. **Instrumentation, no behavior change.** Expose actuator params on `ControlSurface`; add the
   per-tick ω̇ residual (measured minus torque-model-predicted angular acceleration), Q and AoA to
   the diagnostic log. Fly all four scenarios; quantify the torque-model error per regime and
   whether false-latching already happens. De-risks every later phase.
2. **Target-rate feedforward + velocity-relative modes (D + F).** Independent of estimation;
   the biggest single win for descent and ascent. *Test:* hold surface-retrograde through a
   suborbital descent, measure steady tracking lag before/after; vacuum hold and static-target
   slews unchanged.
3. **Estimator + atmosphere-aware chatter bound (A).** *Test:* aircraft gain quality across a
   speed sweep; a rigid fighter never latches at max Q; Ariane 5 ascent still latches and holds;
   vacuum scenarios unchanged.
4. **Trim feedforward (B).** *Test:* aircraft pitch hold — integral stays near zero, disturbance
   recovery unchanged, no trim/integral pumping; flexible-craft hold envelope unregressed.
5. **Actuator-lag handling (E).** *Test:* slow-grid-fin booster descent and slow-elevator
   aircraft hold without limit cycles; flexible craft still classified structural.
6. **Contingency: explicit aero stiffness (C)** — only if phases 3/5 show divergence-limited
   high-AoA holds.

New test craft needed: a rigid aircraft (elevator/aileron/rudder), a grid-fin descent stage, and
a slow-actuator variant of each. The existing quick regression gate (orbital directions + launch
+ smooth turn) plus the Ariane 5 ascent remain the vacuum/flexible anchors after every phase.

## Early experiments / unknowns (phase 1 answers most)

1. Magnitude and sign of the `GetPotentialTorque()` error per regime — does α̂ merely correct it
   or fully replace it?
2. Does the detector false-latch **today** on a rigid aircraft at high Q? Sets the urgency and
   shape of the bound fix.
3. Estimator identifiability during quiet holds — does prior-anchoring hold α̂ steady over
   minutes of cruise?
4. KSP aero divergence rates at realistic max-Q AoA versus the default ~5.6 rad/s loop — decides
   whether phase 6 exists.
5. The rate-limit-cycle signature of slow grid fins (frequency, envelope) — calibrates the
   classifier split from structural chatter.
6. Per-direction effectiveness asymmetry (fin stall / deploy direction at high AoA) — one α̂ per
   axis, or a two-sided estimate? Resolved direction: keep **one α̂ per axis** here; a single axis
   that carries genuinely different actuators (a fast wheel + a slow high-torque surface) is handled
   not by a two-sided `α̂` but by the fast/slow command split in
   [`heterogeneous-actuators.md`](heterogeneous-actuators.md). Revisit a two-sided estimate only if phase-1 data shows
   fin-stall asymmetry the split does not already cover.
7. FAR parity — the measurement-based approach should be aero-model-agnostic; verify.
