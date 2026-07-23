# Design proposal: extending the autopilot to aerodynamic flight

**Status:** proposal — not started. High-level control-loop plan; implementation details
deliberately deferred to per-phase design docs.
**Scope:** `service/SpaceCenter/src/AutoPilot/` (AttitudeController, OscillationDetectors,
MitigationPolicy), `service/SpaceCenter/src/Services/AutoPilot.cs`,
`service/SpaceCenter/src/Services/Parts/ControlSurface.cs`
**Related:** builds on the control-loop redesign ([`inner-loop.md`](inner-loop.md)) and the
oscillation-mitigation calibration ([`oscillation.md`](oscillation.md)). Two sibling proposals
extend the same asymmetric/aero-authority theme: [`bank-to-turn.md`](bank-to-turn.md) (roll so the strong
axis flies a heading change on a weak-yaw craft) and [`heterogeneous-actuators.md`](heterogeneous-actuators.md) (split a
single axis's command across fast and slow actuators). Section E below is the home of the
slow-actuator handling those docs build on.

## Open: whether to build this at all

Upstream of the roadmap below and of both sibling proposals is a go/no-go decision: growing kRPC's
own attitude controller into aerodynamic regimes is listed as "maybe don't do", against the
alternative of **deferring to a MechJeb integration** rather than reimplementing aerodynamic flight
control here. The asymmetric-torque / bank-to-turn work ([`bank-to-turn.md`](bank-to-turn.md))
stands on its own, but this aero-extension roadmap is the part a MechJeb integration would make
redundant. Settle this before starting phase 1.

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
