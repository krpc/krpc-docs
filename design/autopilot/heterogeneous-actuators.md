# Heterogeneous fast/slow actuator allocation

**Status:** proposal — not started. The most speculative of the three attitude extensions; phase 1
decides whether it is worth building at all.
**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs`,
`service/SpaceCenter/src/AutoPilot/MitigationPolicy.cs`,
`service/SpaceCenter/src/Services/AutoPilot.cs`,
`service/SpaceCenter/src/Services/Parts/ControlSurface.cs`,
`service/SpaceCenter/src/ActuatorControlAddon.cs`.
**Related:** [`aero-extension.md`](aero-extension.md) (section A online `α̂` estimator, section E actuator
time-constant / bandwidth ceiling — both prerequisites), [`bank-to-turn.md`](bank-to-turn.md) (sibling
asymmetric-authority work).

## Motivation

One control axis can be driven by actuators of very different bandwidth *and* torque at once — for
example fast, low-torque reaction wheels together with slow, high-torque aerodynamic control
surfaces (grid fins, large elevators). The controller today models a single per-axis authority
`α = torque/MoI` and emits a single per-axis command, so it must pick one bandwidth for the axis:

- tune to the **slow** actuator (respect the surface's rate limit) and the fast reaction wheels sit
  idle below their capability — sluggish;
- tune to the **fast** actuator and the slow surface rate-limits and drives a limit cycle.

The single per-axis scalar cannot express "be agile using the wheels while the surfaces carry the
steady load."

## The hard constraint (verified against the code)

kRPC emits **aggregate** pitch/yaw/roll fractions to KSP's `FlightCtrlState`; **KSP** distributes
those across every actuator (reaction wheels, RCS, gimbals, control surfaces). kRPC cannot address
most actuators individually. The **one** exception is the control surface, via
`ControlSurface.DeflectionOverride` / `Deflection` (PR #917), which is already wired for
client-disconnect and vessel-change cleanup through `ClientOwnedOverrides` in
`ActuatorControlAddon.cs`.

And that override is not the surface's pitch/yaw/roll control throw — it drives the surface's
**`deploy` / `deployAngle`** path (`ActuatorControlAddon.ApplyControlSurfaceDeflection`, mapped onto
`deployAngleLimits`), i.e. a *persistent static* deflection, like an airbrake or trim tab held every
frame. That is a **low-frequency / steady** channel by nature — which is exactly what we want the
slow high-torque surfaces to be.

So the only realizable split is:

```
fast set  (reaction wheels, RCS, gimbals)  <- FlightCtrlState pitch/yaw/roll   (high-frequency)
slow set  (control surfaces)               <- DeflectionOverride via a mixer     (low-frequency/steady)
```

## The idea

**Complementary-filter frequency split.** Take the rate loop's per-axis command `u` and split it by
frequency at the slow actuator's crossover:

```
u_slow = LP(u)            // low-pass at ~1/τ_act (the surfaces' bandwidth)
u_fast = u − u_slow       // the residual high-frequency correction
```

Route `u_slow` to the control surfaces (via the mixer below) and `u_fast` to `FlightCtrlState`
(which drives the wheels/RCS/gimbals). Because the surfaces now carry the steady load, the autotuner
can run the **fast channel at a higher bandwidth** than the surfaces alone would allow — that is the
whole win: fast-set agility plus slow-set torque, instead of the min of the two.

**Surface mixer.** `u_slow` is a desired per-axis low-frequency *torque* (pitch/yaw/roll). The mixer
converts it into per-surface `Deflection` commands using, for each surface: its enabled axes
(`ignorePitch`/`ignoreYaw`/`ignoreRoll`), its mounting sign, and its torque per unit deflection.
That last term is aero-dependent (a deployed surface's torque scales with dynamic pressure, speed,
Mach, AoA), so the mixer needs the **online `α̂` estimator** from aero-extension section A to know
how much torque a given deploy produces — it cannot use the stock `GetPotentialTorque()` for the
deploy path. This makes the estimator a hard prerequisite, not an optimization.

**Bandwidth handling (ties into aero-extension section E, theme "slow actuators").** The slow channel
still respects the actuator bandwidth ceiling `ω₀·τ_act ≤ ~0.3–0.5`; with the split, the ceiling
applies to the **slow sub-band**, while the fast channel gets its own (higher) ceiling from the
wheels'/gimbals' time constants. The per-axis actuator inventory below is the shared source of both
`τ_act` values.

## Per-axis actuator inventory (shared infrastructure)

Enumerate, per axis, every contributor with `(torque share, bandwidth / time constant)`:

| Actuator | Torque source | Bandwidth / τ |
|---|---|---|
| Reaction wheel | `GetPotentialTorque()` | near-instant (fast) |
| RCS | `GetPotentialTorque()`, discrete/asymmetric | fast but quantized |
| Engine gimbal | gimbal range × thrust, only while thrusting | moderate (gimbal slew rate) |
| Control surface | aero-dependent (needs `α̂`) | slow (`actuatorSpeed` / `ctrlSurfaceRange`) |

This inventory is exactly what aero-extension section E's "per-axis dominant actuator time constant"
reads from; building it once serves both docs. `actuatorSpeed`/`ctrlSurfaceRange` are not exposed
yet — expose them as `ControlSurface` RPCs (aero-extension phase 1 already proposes this).

## Exposure

Gate behind a mode, `AutoPilot.ActuatorAllocationMode` = `Off` / `Auto` (default `Off`), mirroring
the existing oscillation-mitigation mode pattern (individually controllable, default-safe). In
`Auto`, the split engages only when the per-axis inventory actually contains both a fast and a slow
high-torque contributor; a pure-wheel or pure-surface axis is left on the aggregate path. `Off`
reproduces today's behavior exactly.

## Interactions / regression surface

| Concern | Rule |
|---|---|
| Disconnect / vessel change | `DeflectionOverride` cleanup is already handled by `ClientOwnedOverrides`; the allocator must release overrides on disengage/disconnect through that path. |
| Oscillation mitigation | The detectors and back-off must see the **aggregate** delivered command (fast + slow contribution), not just `u_fast`, or a slow-channel limit cycle is invisible to them. |
| `α̂` estimator (aero-ext A) | Consumes the suppressed rate; the mixer uses `α̂` for the deploy-path torque. In vacuum the estimator is inert → allocation should also be inert (no aero surfaces produce torque) → behavior identical to today. |
| Bandwidth ceiling (aero-ext E) | Now applied per sub-band; the fast channel's higher ceiling must not leak the slow channel's low-frequency content back onto the wheels. |
| Bank-to-turn | Composes: bank-to-turn chooses the roll orientation, allocation chooses which actuators fly it. Independent, but both should be exercised together on a plane. |

## Open questions (phase 1 must answer before phase 2)

1. **Double-drive (highest risk).** Does an overridden (deployed) surface *still* apply the
   `FlightCtrlState` pitch/yaw/roll control throw on top of `deployAngle`? The split's math assumes
   surfaces are driven **only** by the LF mixer. If deployed surfaces still respond to control input,
   `u_fast` on `FlightCtrlState` would wiggle the slow surfaces at high frequency — the exact
   rate-limit failure we are trying to avoid — and the whole approach needs rethinking (or the
   surfaces' `ignorePitch/Yaw/Roll` flags toggled while overridden). The `ControlSurface` docstring
   claims override "stops responding to pitch/yaw/roll control inputs"; **verify this in-game before
   building anything else.**
2. **Deploy-path torque quality.** How clean and linear is the torque a `deployAngle` deflection
   produces, per surface, across Q and sign? Is it good enough to mix, or too coupled/nonlinear?
3. **Is the win real in stock KSP?** Stock reaction wheels are strong and near-instant, so on many
   craft the wheels alone already dominate and the surfaces add little. The clearest value is a craft
   that *needs* the slow high-torque surface for authority — a grid-fin booster descent, or a plane
   flying with reaction wheels disabled. If phase 1 shows the wheels always suffice, this doc stops
   at phase 1.
4. **Crossover placement.** Where to set the complementary-filter corner relative to `1/τ_act`, and
   how it interacts with the oscillation machinery's frequency bands.

## Rejected alternatives

- **One `α̂` per axis that "averages" the two actuators:** rejected — averaging a fast-low-torque and
  a slow-high-torque source gives a fictitious actuator that is neither; it re-creates the
  single-bandwidth problem. The point is to keep them separate.
- **Lead/actuator-inverse on the surfaces to fake speed:** rejected for the same reason
  aero-extension E rejects it — surface rate limiting is a nonlinear saturation; lead deepens it.
- **Bypassing `FlightCtrlState` entirely for per-actuator allocation:** not possible — KSP owns the
  distribution for everything except control surfaces. The partial split is the ceiling of what the
  stock interface allows.

## Phased roadmap

1. **Instrumentation + de-risking (behavior-neutral).** Expose `actuatorSpeed`/`ctrlSurfaceRange`;
   build the per-axis actuator inventory; answer open questions 1–3 (especially the double-drive
   test) on a grid-fin booster and a wheels-off plane. **Go/no-go gate** for the rest.
2. **Surface mixer + complementary split.** Depends on aero-extension A (estimator) landing first.
   *Test:* red→green below.
3. **Per-sub-band bandwidth + `Auto` engagement logic.** Tie the fast/slow ceilings to the inventory;
   fold in aero-extension E's limit-cycle classifier.

New test craft: a grid-fin descent stage (slow high-torque surfaces + modest wheels) and a plane
flown with reaction wheels disabled. Vacuum and flexible-craft anchors must be unregressed after
every phase (allocation inert in vacuum by construction).

## Test scenarios (red→green, in-game via krpctest)

- **Double-drive check (phase 1):** enable `DeflectionOverride` on a surface, command pitch via
  `FlightCtrlState`, and confirm whether the surface deflection tracks only the override or also the
  control input. Gates the design.
- **Agility + authority:** grid-fin booster holding an attitude under disturbance with
  `ActuatorAllocationMode=Auto` settles faster than `Off` (fast wheels) *and* without the slow-surface
  limit cycle that a wheels-tuned aggregate loop produces.
- **`Off` regression:** the full existing suite passes unchanged at the default mode.
- **Vacuum inert:** a vacuum craft with `Auto` on behaves identically to `Off` (no aero torque → no
  slow channel).
