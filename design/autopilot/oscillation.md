# AutoPilot oscillation mitigation

**Status:** done — oscillation mitigation as shipped in the autopilot rework ([PR #882](https://github.com/krpc/krpc/pull/882)). Historical design record; also covers one later-superseded fix (flexible-latch discrimination) and one negative result (adaptive TimeToPeak), each flagged in its section.

This is the structural-oscillation-mitigation layer of the autopilot control stack: the machinery that keeps a flexible craft's bending modes from turning into actuator limit cycles, sitting between the measured angular rate and the inner rate loop. This doc consolidates the former `oscillation-suppression.md` (the notch/low-pass design), `oscillation-calibration.md` (the in-game calibration that reshaped it), `oscillation-context.md` (MechJeb comparison and detection limits), `flexible-latch-discrimination.md` (the later-superseded flexible-craft latch fix), and `adaptive-timetopeak.md` (a negative result). Each appears below as its own section, in that order.

## Oscillation suppression (notch + low-pass, frequency-routed)

*Originally `oscillation-suppression.md` — done. The notch/low-pass signal-processing design landed and was later restructured; the current structure and outcomes are in [`inner-loop.md`](inner-loop.md), and the in-game calibration that reshaped it is the next section below. Historical design record.*

> **2026-07-02 update:** the machinery this section describes now lives in a three-layer structure —
> `OscillationDetectors` (observation), `MitigationPolicy` (gating/routing) and the
> `RateFilter`/`OutputFilter` primitives in `OscillationMitigations.cs` — with each mitigation
> individually controllable via the per-mitigation RPC surface (`RateFilterMode`,
> `MitigationMode`), and the acceleration feedforward is now analytic. The signal-processing
> design here (notch/low-pass routing, estimator, thresholds) is unchanged. See
> [`inner-loop.md`](inner-loop.md) for the current structure and outcomes.

> Structural oscillation is suppressed with **two tools routed by the estimated frequency**: a
> **notch** for low-frequency modes near the control band (e.g. the ~1.4 Hz Ariane mode) and a
> **second-order low-pass** for high-frequency / near-Nyquist modes the notch physically cannot reject
> (e.g. ~25 Hz at 50 Hz physics). Both are gated on the chatter latch; neither uses the old hold/slew
> state machine.

Background comparison (MechJeb) and the detector's boundary notes live in the *Context and detection
limits* section below; they inform the design but do not affect what is implemented here.

### Problem and approach

The autopilot's current wobbly-craft handling (introduced with the Ariane 5 test campaign) works but is
mechanically complex:

- a runtime chatter detector (Δω vs. rigid-body bound α·dt),
- a persistent latch per axis,
- a hysteretic hold/slew state machine (`holdingState`, `HoldErrorEnter/Exit`),
- feedforward decoupling (switching between `target` and `targetNominal`),
- a cascaded second-order low-pass applied to the measured angular rate (blended by `chatterLevel`),
- an inner-loop bandwidth floor (`OscillationBandwidthFloor`), and
- integral clearing on mitigation engage.

All of that complexity traces to **one** decision: applying a single broadband low-pass to *every*
flexible craft. A 2 Hz-corner filter adds significant phase lag across the sub-Hz control band, which
degrades rigid-craft performance, so on craft whose mode sits near the band the filter must be gated
off whenever the craft slews. Gating needs a state machine; the state machine needs hysteresis to avoid
chattering at the boundary; and so on — the `holdingState` machine, the `HoldErrorEnter/Exit`
hysteresis, the `mitigateAxis` latch-and-hold, the `targetNominal` feedforward decoupling and the
integral clearing are all downstream of that one filter.

The new design keeps the chatter detector + latch but **routes by the estimated mode frequency** to the
tool that is transparent in-band for *that* mode, so nothing ever needs hold-gating:

- **Low-frequency mode near the band (e.g. ~1.4 Hz Ariane):** a **notch**. It is transparent everywhere
  except its narrow rejection band, so it can sit permanently on a latched axis. (A broadband low-pass
  here would smear the control band — exactly why the old design had to gate it.)
- **High-frequency / near-Nyquist mode (e.g. ~25 Hz):** a **second-order low-pass**. A notch *cannot*
  reject a near-Nyquist mode (see *High-frequency regime*); but here the mode is far above the control
  band, so a 3–5 Hz corner kills it while adding negligible in-band lag.

What goes away in both branches: the hold/slew state machine, the hysteresis, the integral clearing,
the `targetNominal` feedforward decoupling. What is **retained**: the chatter detector + latch, and the
second-order low-pass filter (`FilterAngularVelocity`) — repurposed as the high-frequency tool, with
its corner now derived from the estimated frequency instead of a fixed broadband 2 Hz.

**The notch branch still needs a mild bandwidth reduction.**
A notch is only transparent *away from its center*, and the measured Ariane mode (~1.4 Hz) coincides
almost exactly with the default rate-loop bandwidth `2ζω₀ ≈ 9.2 rad/s ≈ 1.47 Hz` (see *Bandwidth must
track the notch frequency*). At default gains the notch would sit on the loop's crossover, where its
skirt's phase lag is destabilizing. So the notch branch pulls the crossover **below** the mode — but
only **much milder** than the old floor (~0.5 Hz vs 0.16 Hz, ~3× more bandwidth, sized relative to the
detected frequency), because the notch, not the reduced bandwidth, does the rejection. The low-pass
branch needs **no** bandwidth reduction at all (the mode is already far above the band).

Both tools require the mode frequency, which needs online estimation — described next.

### Online frequency estimation (Automatic mode)

To find the oscillation frequency we track the interval between sign changes of the Δω sequence:

- Consecutive same-sign peaks are separated by one full oscillation period T.
- An exponential moving average smooths the period estimate (τ ≈ 0.5 s), so the notch tracks slow
  drift as propellant is consumed without reacting to individual noisy measurements.
- The notch is configured from this estimate on every physics tick; biquad coefficients are
  recomputed when f₀ changes materially (> ~2%).

#### Estimator runs unconditionally; the latch decides whether to suppress

The frequency estimator is **always running** — fed every physics tick, regardless of the detector
state. It is only a handful of adds per tick, so there is no cost to leaving it on, and it means a
frequency estimate is always warm and ready the moment an axis is deemed flexible. This drops the
former `chatterLevel > 0.2` "start the estimator early" gate and its associated tuning knob.

What the estimator alone **cannot** decide is whether the interval it locked onto is a real structural
limit cycle or just a normal maneuver. A bang-bang slew produces a clean Δω sign-change pair separated
by the slew duration, which the estimator will lock onto just as confidently as a bending mode — and
that apparent frequency (~0.25–1 Hz) lands inside the control band, where a notch is actively harmful
(it removes rigid-body rate the loop needs). Frequency alone can't separate the two: on a long launch
vehicle the bending mode (~1.4 Hz) and slew transients are in adjacent ranges, so no fixed cutoff
divides them. The physical discriminator that does is exactly what the chatter detector already
computes — Δω > threshold·α·dt, the rate moving faster than the available torque physically allows. A
slew never trips it; a bending mode does.

So the division of labor is:

- **Estimator** (always on): *what* frequency, if any, the rate is oscillating at. Its frequency also
  selects the tool (notch below `f_split`, low-pass above — see *High-frequency regime*).
- **Chatter detector + latch** (unchanged, validated in-game): *whether* suppression is applied at all.
  Suppression engages on a latched axis (`Automatic` mode) — once Δω has confirmed a genuine structural
  limit cycle — and never on an axis that is merely slewing.

This is the `Automatic` mode of the per-group `*OscillationControl` selector. The other modes bypass
the detector entirely: `Notch` and `LowPass` assert the craft is flexible and force that tool on
unconditionally (no latch required) at the group's manual `*OscillationFrequency`; `Off` applies no
suppression at all. See *New public API*.

The estimate is seeded at the group's `*OscillationFrequency` (default 1.5 Hz, near the only
in-game-measured low-frequency mode — the Ariane 5's ~1.4 Hz first lateral bending mode; see
`test_autopilot.py`) until the estimator acquires, so a freshly-latched low-frequency axis is never
momentarily un-suppressed.

#### Frequency tracker algorithm

One `FrequencyTracker` per group (pitch/yaw, roll), fed the **raw (pre-notch, pre-filter)** Δω each
tick — see *Signal routing* below; feeding it the suppressed signal would starve it of the very
oscillation it measures (the old hunt).

1. **Input (pitch/yaw group):** feed the Δω of whichever transverse axis currently has the larger
   `EMA(|Δω|)`; the lateral mode is ~axisymmetric so either carries it, and picking the stronger avoids
   tracking a near-null axis. Roll group: roll Δω directly.
2. **Zero-crossing with hysteresis:** hold a sign state that flips only when Δω crosses zero by more
   than a deadband `ε = κ · EMA(|Δω|)` (`κ ≈ 0.25`), so jitter around an extremum does not manufacture
   spurious crossings.
3. **Half-period, doubled:** the ticks since the previous accepted flip are a **half**-period — Δω
   changes sign at each extremum of ω, twice per cycle — so `T = 2 · halfInterval · dt`. **Forgetting
   the factor of 2 notches at double the true frequency**; this is the single most likely bug.
4. **Plausibility gate:** accept `T` only if `f = 1/T` is within `[f_min, f_max]`; otherwise discard
   without updating (rejects slew transients at the low end and single-tick noise at the high end).
   Default `f_min ≈ 0.5 Hz`; `f_max` just under Nyquist (`< 25 Hz`). Note the gate spans the full
   representable range — it does **not** decide which suppression tool is used; that routing is by
   frequency (see *High-frequency regime*).
5. **Smoothing:** EMA the accepted period (τ ≈ 0.5 s); `EstimatedHz = 1 / T_ema`.
6. **Acquisition / loss:** `EstimatedHz` stays **NaN** until `K = 3` consecutive accepted half-periods
   agree within ±20% of the running EMA (the NaN-until-acquired API contract). Reset to NaN and clear
   the counter if `M ≈ 8` ticks pass with no accepted crossing (mode died / craft settled).
7. **Coefficient recompute:** reconfigure the consuming filter only when `EstimatedHz` moves > ~2%.

**Signal routing (get this ordering right).** Per tick: sample `currentRaw` → feed
`UpdateChatterDetector` and both `FrequencyTracker`s from `currentRaw`'s Δω (raw) → *then* apply the
suppression (notch/low-pass) to produce the rate the PID, feedforward and gyro feedforward consume.
The detector and the trackers always see the raw, un-suppressed rate; only the control loops see the
suppressed rate.

### High-frequency regime: low-pass routing

A notch **cannot** suppress a near-Nyquist mode. At 50 Hz physics, Nyquist is 25 Hz; the bilinear
biquad notch coefficient `K = tan(π·f₀·dt)` diverges as `f₀ → 25 Hz` (`tan(π/2) → ∞`), and the notch
has **unity gain at Nyquist by construction**, so a 25 Hz signal (the every-other-tick alternation)
passes through any notch untouched. There is no band left above it to be transparent in. At least one
flexible test craft oscillates up here (visible ~25 Hz control chatter), so this regime is real.

For a high-frequency mode the **second-order low-pass is the right tool**: the mode is far above the
sub-Hz control band, so a corner well below the mode still sits well above the band. The existing
`FilterAngularVelocity` (two cascaded first-order sections) is retained for exactly this.

**Routing.** Per axis-group, once latched:

```
f_detected < f_split   → notch (+ mild bandwidth reduction, see below)
f_detected ≥ f_split   → second-order low-pass, no bandwidth reduction
```

- `f_split` is an internal constant, default **~8 Hz**: below it the notch is well-conditioned and the
  mode is close enough to the band that a low-pass would smear it; above it the notch degrades toward
  Nyquist and the low-pass is comfortably in-band-transparent. (Exposed later only if needed.)
- **Low-pass corner** is derived from the detected frequency — `fc = f_detected / L_lp`,
  `L_lp ≈ 3` — clamped to a sane minimum (≈2 Hz) so it never drifts down into the control band. For a
  25 Hz mode this puts the corner near 8 Hz: ~10 dB on the mode per the first section, ~20 dB across the
  cascade, with negligible sub-Hz lag. Corner policy is a calibration item.
- The two tools are **mutually exclusive per axis-group per tick**: an axis is either notched or
  low-passed (or untouched), never both. The other tool's filter state is held reset so a regime change
  (a mode that drifts across `f_split`, rare) does not inject a transient.

### Bandwidth must track the notch frequency (notch branch only)

The default rate-loop bandwidth set by the autotuner is, at the default `Overshoot = 0.01`
(`ζ ≈ 0.826`) and `TimeToPeak = 1 s`:

```
ω₀   = π / (TimeToPeak · √(1−ζ²)) = 5.58 rad/s
2ζω₀ = 9.2 rad/s ≈ 1.47 Hz                 ← the quantity DoAutoTuneAxis sets, = "bandwidth"
```

That is essentially *on* the 1.4 Hz Ariane mode (the autotuner's own comment says as much —
"the bandwidth approaches the structural resonance ~10 rad/s"). A notch at the crossover is not
transparent: its skirt adds ~23° of phase lag at the crossover (Q=2.5, `f_crossover/f₀ ≈ 0.6`), eating
phase margin. So the crossover must be moved below the mode.

This bandwidth reduction applies **only in the notch branch** (`f_detected < f_split`). The low-pass
branch leaves the autotuned bandwidth untouched, since a high-frequency mode is already far above it.

**Rule: a latched (notch-branch) axis's bandwidth target tracks its detected notch frequency.** Rather
than a fixed floor, the target rate-loop bandwidth is

```
bw_target = 2π · f_detected / N        (rad/s)
```

where `f_detected` is the **same per-group estimator frequency that configures that axis's notch**
(pitch/yaw group → pitch and yaw; roll group → roll), and `N` is a fixed **separation ratio**
(`OscillationBandwidthSeparation`, default **3**). This guarantees a constant mode-to-crossover ratio
no matter where the mode sits or drifts to as propellant burns — the notch and the crossover move
together. Phase lag of the notch at the crossover is then fixed by `N` alone:

```
N = 2 → ~15°,  N = 2.8 → ~9°,  N = 3 → ~8.5°,  N = 4 → ~6°
```

`N = 3` keeps it under ~9° while costing the least bandwidth: at the 1.4 Hz mode the target lands at
`2π·1.4/3 ≈ 2.9 rad/s ≈ 0.47 Hz` — still ~3× above the old 1 rad/s floor, so the craft is *more*
responsive than under the old aggressive mitigation, not less.

Mechanics (reuses the existing `DoAutoTuneAxis` reduction, only the target changes):

- The reduction **only ever lowers** bandwidth: `bw = min(autotuned, bw_target)`. A latched craft whose
  mode is already well above its autotuned bandwidth gets no reduction (separation already exists); a
  rigid craft never latches, so is never touched.
- Before the estimator acquires, `f_detected` falls back to the 1.5 Hz seed, so a freshly-latched axis
  still gets a sane bandwidth target immediately.
- The reduction is ramped in by `chatterLevel` (as today) so the gains do not step when the axis
  latches; `ζ` is preserved (`Kp ← f·Kp`, `Ki ← f²·Ki`).

This replaces the removed `OscillationBandwidthFloor` (absolute floor) with
`OscillationBandwidthSeparation` (a ratio). It is the one piece of "bandwidth reduction" the notch does
*not* eliminate — but it is now self-tuning to the mode and far milder than before.

### Filter topology

Per axis, the raw rate passes through the suppression stage selected by that axis-group's estimated
frequency (notch, low-pass, or pass-through when unlatched/Off) before reaching the control loops:

```
                    f < f_split: notch(f)
                    f ≥ f_split: lowpass(f/L_lp)
                    unlatched/Off: pass-through
           ┌──────────────────────────┐   ┌──────────┐
pitch ω ─▶ │   suppress(x) [py group] │─▶ │  PID     │
yaw   ω ─▶ │   suppress(z) [py group] │─▶ │  +  ff   │─▶ control output
roll  ω ─▶ │   suppress(y) [roll grp] │─▶ │          │
           └──────────────────────────┘   └──────────┘
             ↑                ↑
             f(py)            f(roll)
```

- **Two frequency trackers**: one for pitch/yaw (coupled, matching the existing chatter latch coupling),
  one for roll. A long rocket's first lateral bending mode is axisymmetric, so pitch and yaw share one
  frequency; the torsional (roll) mode may differ.
- **Three notch instances** (pitch x, yaw z from the pitch/yaw tracker; roll y from the roll tracker),
  used only on axes routed to the notch branch.
- **Low-pass** via the retained `FilterAngularVelocity`, used per-axis on axes routed to the high-
  frequency branch, corner = `f_detected / L_lp`.

### Biquad notch coefficients

Standard bilinear-transform biquad notch (sampling period `dt`, quality factor `Q`):

```
K  = tan(π f₀ dt)

b0 = 1 + K²
b1 = 2(K² − 1)         = a1
b2 = 1 + K²             = b0
a0 = 1 + K/Q + K²
a1 = 2(K² − 1)
a2 = 1 − K/Q + K²

all coefficients divided by a0 before use
```

The notch has unity gain at DC and at the Nyquist frequency, and zero gain at f₀. Q controls the
bandwidth: a higher Q is a narrower notch (less in-band phase lag, but less tolerance to frequency
drift); a lower Q is wider (more drift tolerance, more in-band lag). Default `OscillationNotchQ = 2.5`.

The notch is only used below `f_split` (~8 Hz), where `K = tan(π·f₀·dt)` is well-conditioned
(`K ≈ 0.55` at 8 Hz, `1.0` at 12.5 Hz). Above `f_split` the coefficient grows toward the Nyquist
singularity and the unity-gain-at-Nyquist property makes the notch useless — which is why that regime
is routed to the low-pass instead (see *High-frequency regime*).

`Q` and the separation ratio `N` (see *Bandwidth must track the notch frequency*) together trade phase
margin against frequency-drift tolerance: higher `Q` (narrower) lowers in-band lag but leans harder on
the estimator tracking the mode; larger `N` lowers lag but costs bandwidth. Both want in-game
confirmation on the Ariane.

### New public API

#### `OscillationControl` enum (extended)

The existing per-group `OscillationControl` enum (currently `Automatic`/`Off`/`On`) is the single
suppression selector. The `On` value — which only said "treat as flexible" without saying *which* tool —
is replaced by the two explicit tool choices, so one per-group property fully describes the behavior
(no separate global mode that interacts with it):

```csharp
public enum OscillationControl {
    Automatic,  // Detect + latch, then route by estimated frequency (notch < f_split, low-pass above). Default.
    Off,        // No suppression at all: full authority, accepts wobble.
    Notch,      // Force the notch on unconditionally (no latch) at this group's OscillationFrequency.
    LowPass     // Force the low-pass on unconditionally (no latch) at this group's OscillationFrequency.
}
```

`Notch` and `LowPass` are the manual override: the user has asserted the craft is flexible, so the
chosen tool runs unconditionally at the group's `*OscillationFrequency` (the detector and `f_split`
routing are bypassed). `Automatic` keeps the detect-latch-route path; `Off` disables suppression.

The broadband low-pass machinery is **not** removed — the second-order `FilterAngularVelocity` is
*retained* as the high-frequency tool. What is removed is the hold/slew **gating** of it (the state
machine, hysteresis, `mitigateAxis`, integral clearing) and the `targetNominal` feedforward decoupling.
So there are two suppression filters but a single, ungated decision path: select tool (by mode, or by
estimated frequency in `Automatic`) → apply.

#### Properties added to / changed on `AutoPilot` service

| Property | R/W | Type | Default | Description |
|---|---|---|---|---|
| `PitchYawOscillationControl` / `RollOscillationControl` | RW | `OscillationControl` | `Automatic` | Per-group suppression selector (enum extended with `Notch`/`LowPass`, `On` removed) |
| `PitchYawOscillationFrequency` / `RollOscillationFrequency` | RW | `double` Hz | 1.5 | Per-group mode frequency: used directly in `Notch`/`LowPass` mode, and as the `Automatic`-mode estimator seed before acquisition. Replaces the single `OscillationFrequency` |
| `OscillationNotchQ` | RW | `double` | 2.5 | Notch quality factor (notch branch only) |
| `OscillationBandwidthSeparation` | RW | `double` | 3.0 | Ratio `N`: a notch-branch axis's rate-loop bandwidth target is held at `2π·f/N`. Replaces the removed `OscillationBandwidthFloor`. No effect in the low-pass branch |
| `PitchYawOscillationDetectedFrequency` | R | `double` Hz | NaN | Estimated pitch/yaw mode frequency. The estimator runs in **all** modes (it costs only a handful of adds per tick), so this is observable even under `Off`/`Notch`/`LowPass`; NaN only until the estimator acquires |
| `RollOscillationDetectedFrequency` | R | `double` Hz | NaN | Estimated roll mode frequency; observable in all modes (see above); NaN only until acquired |

Separate per-group frequencies let a craft whose lateral bending mode and torsional (roll) mode differ
be hand-tuned independently in `Notch`/`LowPass` mode — the same per-group split the trackers already
use in `Automatic`.

The low-pass corner ratio `L_lp` and the routing threshold `f_split` are internal constants for now
(not exposed); promote to properties only if in-game tuning shows a need.

#### Removed properties (breaking — version bump required)

- `OscillationControl.On` (enum value) — **replaced** by the explicit `Notch` / `LowPass` values, which
  also say which tool to force. Any client passing `On` must move to one of those.
- `OscillationHoldMitigation` — no longer meaningful; the notch has no hold/slew gate.
- `OscillationBandwidthFloor` — **replaced** by `OscillationBandwidthSeparation`: bandwidth *is* still
  reduced on a latched axis, but the target is now a ratio below the detected frequency rather than an
  absolute floor (see *Bandwidth must track the notch frequency*).
- `OscillationRateFilterTimeConstant` — removed as a *fixed* knob: the low-pass is retained but its
  corner is now derived from the detected frequency (`f_detected / L_lp`) rather than set as a fixed
  time constant. (Could be re-exposed later as a manual corner override if needed.)

These are **deleted entirely** (RPCs removed, not stubbed as no-ops), and the
existing tests that exercise them (`test_oscillation_config`, `test_oscillation_force_on`) are updated
to drop those assertions. This is a breaking change and requires a version bump; the removal is noted
in `CHANGES.txt` in the final pre-merge commit.

The read-only mitigation observability properties (`PitchYawOscillationMitigating`,
`RollOscillationMitigating`) and `OscillationLevel`'s tie to the hold gate also go away with the hold
state machine; see the AutoPilot.cs section.

### Code changes

#### `AttitudeController.cs`

**Remove:**
- `mitigateAxis[]`, `prevMitigateAxis[]` arrays and all code that sets/reads them
- `holdingState`, `HoldErrorEnter`, `HoldErrorExit` and the `holdingState`/`holdActive` logic
- `oscillationHoldMitigation` field and `OscillationHoldMitigation` property
- `oscillationRateFilterTimeConstant` field and `DefaultRateFilterTimeConstant` constant (the low-pass
  corner is now derived from `f_detected`, not a fixed τ)
- `DefaultAdaptiveBandwidthFloor` constant (replaced by the separation ratio)
- `targetNominal` computation and `ffSource` blend (feedforward decoupling)
- `pidTarget` mitigation branch (always use `target`)

**Keep but repurpose:**
- `FilterAngularVelocity()` and `rateFilterStage1/2`, `rateFilterValid` — retained as the
  **high-frequency low-pass** tool. Change its corner source: instead of `oscillationRateFilterTimeConstant`,
  compute `τ = 1/(2π·fc)` from `fc = max(fc_min, f_detected / L_lp)` each tick. Apply it per-axis (only
  on axes routed to the low-pass branch) rather than to all three axes unconditionally.

**Add:**
- `BiquadNotchFilter` inner struct (or separate file): holds (b0,b1,b2,a1,a2) + (s0,s1) state, exposes
  `Process(double x)` and `Reset()`. Reconfigure from `(f0, Q, dt)` via `SetFrequency()`.
- `FrequencyTracker` inner struct (algorithm above): `Update(double deltaOmega, double dt)` and
  `EstimatedHz` (NaN until acquired).
- Two `FrequencyTracker` instances: `pitchYawFreqTracker`, `rollFreqTracker`.
- Three `BiquadNotchFilter` instances: `pitchNotch`, `rollNotch`, `yawNotch`.
- `oscillationBandwidthSeparation` field + `OscillationBandwidthSeparation` property (default
  `DefaultBandwidthSeparation = 3.0`), `oscillationNotchQ` + property, and the per-group
  `pitchYawOscillationFrequency` / `rollOscillationFrequency` fields (manual value / seed) + properties
  (default `DefaultOscillationFrequency = 1.5` Hz). The mode selector reuses the existing per-group
  `oscillationControl` fields (enum now extended with `Notch`/`LowPass`).
- `DefaultSplitFrequency` (~8 Hz) and `DefaultLowpassSeparation` (`L_lp ≈ 3`) constants, and `fc_min`.
- In `Update()`: feed Δω into the trackers **every tick, unconditionally**. Then, per axis-group,
  select the tool from that group's `oscillationControl`:
    - `Off` ⇒ none;
    - `Notch` ⇒ notch (+ bandwidth reduction) at the group's `*OscillationFrequency`;
    - `LowPass` ⇒ low-pass at that frequency;
    - `Automatic` ⇒ active only while latched, then route by `f_detected`: `< f_split` ⇒ notch
      (configured from the tracker) **and** the bandwidth reduction; `≥ f_split` ⇒ low-pass.

  Apply the selected filter to `currentRaw` per axis before the PID, feedforward and gyro feedforward.
  The inactive filter's state is held reset so a regime change does not inject a transient.
- In `Start()`: reset trackers, both filters' state, and the bandwidth-ramp state.

**Modify (do not remove) — `DoAutoTuneAxis` bandwidth reduction (notch branch only):**
- Apply the reduction **whenever the notch is the active tool** on that axis — i.e. `Automatic` while
  latched with `f_detected < f_split`, *or* forced `Notch` mode; in the low-pass branch (`Automatic`
  above `f_split`, or forced `LowPass`) leave the autotuned gains untouched.
- Change its target from the fixed `oscillationBandwidthFloor` to the frequency-tracking
  `bw_target = 2π · f / oscillationBandwidthSeparation`, where `f` is the group frequency the notch is
  using — the tracker estimate in `Automatic` (pitch/yaw → `pitchYawFreqTracker`, roll →
  `rollFreqTracker`, falling back to the seed before acquisition), or the manual `*OscillationFrequency`
  in forced `Notch` mode. Still `min` against the autotuned bandwidth (only ever reduce) and still
  preserves ζ (`Kp ← f·Kp`, `Ki ← f²·Ki`).
- **Gate the reduction on the notch being active, not on instantaneous `chatterLevel`.** The reduction
  must persist exactly as long as the notch is applied — its job is to keep the notch's crossover phase
  lag out of the loop, which is needed whenever the notch is active, independent of whether the mode is
  currently ringing. In `Automatic` that means gating on the (persistent) latch rather than the
  (decaying) `chatterLevel`, which is what prevents the old decay-and-re-excite hunt **without** needing
  the long `ChatterDecayTimeConstant`; in forced `Notch` mode it is simply always on. To avoid a gain
  step when the notch engages, ease the applied reduction in with a short one-pole ramp (τ ≈ 0.5 s; one
  per-axis state value, reset in `Start`).

**Modify:**
- `ApplyOscillationOverride()` — the per-group enum it reads is now `Automatic`/`Off`/`Notch`/`LowPass`,
  not `Automatic`/`Off`/`On`. `Off` forces the group rigid for *control* purposes (`chatterLevel=0`,
  `chatterLatched=false`, no suppression applied), but the frequency estimator keeps running — its job
  is separate from the latch, and leaving it on costs nothing — so `*OscillationDetectedFrequency`
  stays observable under `Off`. `Notch`/`LowPass` no longer force the latch — they select the tool
  directly in `Update()` and bypass the detector — so the old `On` "force latched" branch is removed.

**Keep (unchanged):**
- `UpdateChatterDetector()`, `chatterLatched[]`, `chatterLevel`, `ChatterDecayTimeConstant` (the whole
  detector is untouched; in `Automatic` the latch it produces gates the notch + bandwidth reduction)
- `UpdateSmoothedTorque()`, `GyroscopicFeedforward()`, all velocity profile methods
- Diagnostic logging (extend to log the detected frequency, the active tool per group, and the per-axis
  bandwidth target)

#### `AutoPilot.cs`

- Add RPCs for `OscillationNotchQ`, `OscillationBandwidthSeparation`,
  `PitchYawOscillationFrequency`, `RollOscillationFrequency`,
  `PitchYawOscillationDetectedFrequency`, `RollOscillationDetectedFrequency`.
- The existing `PitchYawOscillationControl` / `RollOscillationControl` RPCs are kept; only their enum
  type gains `Notch`/`LowPass` and loses `On` (no signature change). No separate suppression-mode RPC.
- Remove the `OscillationHoldMitigation` RPC entirely (no stub).
- Remove the `OscillationRateFilterTimeConstant` RPC entirely; replace `OscillationBandwidthFloor` with
  `OscillationBandwidthSeparation` (different semantics — a ratio, not an absolute floor).
- Remove `PitchYawOscillationMitigating` and `RollOscillationMitigating` RPCs: they reported the
  `mitigateAxis` hold state, which no longer exists. (`OscillationLevel`,
  `PitchYawOscillationLatched`, `RollOscillationLatched` are kept — the detector and latch remain; in
  `Automatic` the latch gates suppression, while the estimator runs ungated.)

#### `OscillationControl.cs` (modified)

Extend the existing enum: add `Notch` and `LowPass`, remove `On` (see *`OscillationControl` enum
(extended)*). No new file is needed.

#### Autopilot code comments

Update the flexible-craft-handling and auto-tuning comments in `AttitudeController.cs`: the
`targetNominal` feedforward decoupling and the hold/slew state machine are gone; the second-order
rate filter is **retained** but repurposed as the high-frequency low-pass (corner derived from the
estimated frequency), and the bending-mode notch (with frequency tracking and the separation-ratio
bandwidth reduction) is added for low-frequency modes, the two routed by `f_split`. The comment
noting there is no bending-mode notch is now resolved and should describe the routed notch/low-pass
scheme.

#### `test_autopilot.py`

The oscillation API is exercised by a shared mixin (`test_oscillation_config`,
`test_oscillation_force_on`, `test_oscillation_force_off`, `test_oscillation_auto_detection`) plus three
`flexible=True` craft classes: `TestAutoPilotChatter`, `TestAutoPilotFlexible`, `TestAutoPilotAriane`.
Their existing hold/slew chatter assertions are the real regression signal and **all must stay green** —
that is what proves both branches (notch + low-pass) work. Changes:

- `test_oscillation_config`: drop the assertions on `oscillation_hold_mitigation` and
  `oscillation_rate_filter_time_constant` (removed properties). Add round-trip + reset assertions for
  the per-group `pitchyaw_oscillation_frequency` / `roll_oscillation_frequency` (default 1.5),
  `oscillation_notch_q` (default 2.5) and `oscillation_bandwidth_separation` (default 3.0, replacing
  the `oscillation_bandwidth_floor` assertion). Update the `*_oscillation_control` round-trip to cover
  the new `Notch`/`LowPass` values (default still `Automatic`). Replace the `*_oscillation_mitigating`
  default assertions with `pitchyaw_oscillation_detected_frequency` / `roll_oscillation_detected_frequency`
  defaulting to NaN before the craft has oscillated.
- `test_oscillation_force_on`: drop `oscillation_hold_mitigation = on` and the `mitigating`
  assertion; the force-on now sets `pitch_yaw_oscillation_control = Notch` (or `LowPass`) and asserts
  suppression engages without a latch. Keep the latch assertions for the separate `Automatic` path.
- `test_oscillation_force_off`: drop the `*_oscillation_mitigating` assertions; the latch/level
  assertions stay.
- `test_oscillation_auto_detection`: unchanged in intent (flexible craft latch, rigid do not).
- `TestAutoPilotAriane` (low-frequency, notch branch): add an assertion that
  `pitchyaw_oscillation_detected_frequency` settles near ~1.4 Hz (wide band, e.g. 1.0–2.0 Hz). Its
  `control_oscillation_amplitude` hold assertion must stay green — note this craft's mode reverses only
  every ~25 ticks, so amplitude, not `control_reversal_rate`, is the meaningful metric.
- `TestAutoPilotChatter` / `TestAutoPilotFlexible`: confirm in-game which branch each routes to
  (measure `*_detected_frequency` relative to `f_split`). Whichever branch, their existing chatter
  bounds must hold; if either is high-frequency it exercises the low-pass path. Assert the detected
  frequency lands in the expected regime once measured.
- Rigid craft classes: unaffected — they never latch, so no suppression engages.

#### `auto-pilot.tmpl`

Update API doc to document the new enum and properties; remove the removed ones.

### Key risk: frequency-estimator latency

The estimator needs roughly one oscillation period to acquire (~0.7 s at 1.4 Hz, ~0.08 s at 25 Hz).
Because it runs unconditionally from engage, it has been tracking for the entire pre-latch window by
the time an axis latches, so an estimate — and hence the tool selection (notch vs low-pass) — is
already settled when suppression first engages. The 1.5 Hz seed covers a latch that fires before the
estimator locks: it routes to the notch branch by default, which is the safe choice for the un-acquired
case (a low-frequency assumption with mild bandwidth reduction, rather than a low-pass that might smear
the band if the true mode were actually low). A genuinely high-frequency craft re-routes to the
low-pass within a few ticks of acquisition.

### Verification

0. **Measure the mode frequencies first.** Enable diagnostic logging and record
   `*_detected_frequency` for `AutoPilotChatter`, `AutoPilotFlexible` and `Ariane 5`. This confirms
   which branch each craft exercises and sets the `f_split` / `L_lp` / `f_min`/`f_max` constants on
   data rather than assumption. (The ~25 Hz observation says at least one is in the low-pass branch.)
1. **Ariane 5 (`TestAutoPilotAriane`, notch branch)** — `control_oscillation_amplitude` hold assertion
   must stay green; `PitchYawOscillationDetectedFrequency` settles near ~1.4 Hz (assert ~1–2 Hz).
2. **`TestAutoPilotChatter` / `TestAutoPilotFlexible` (likely low-pass branch)** — existing chatter
   bounds must stay green; confirm they route to the low-pass and that a high-frequency mode is
   rejected without the old hold-gating.
3. **Rigid craft** — chatter never latches; no suppression engages; tests stay green.
4. **Forced `Notch` / `LowPass` mode** — set a group's `*OscillationControl` to the tool matching its
   known mode and its `*OscillationFrequency` to that mode; confirm it damps identically to `Automatic`
   (which auto-selects the same tool). Cross-check that forcing the *wrong* tool degrades as expected
   (`Notch` on the ~25 Hz craft is ineffective; `LowPass` on the Ariane smears the band).
5. **`Off` mode** — confirm a flexible craft receives no suppression (full authority, expected to
   wobble): the explicit "accept the wobble" escape hatch.

## In-game calibration findings

*Originally `oscillation-calibration.md` — reference; in-game calibration findings that reshaped the design.*

This records what happened when the frequency-routed notch/low-pass design (the *Oscillation
suppression* section above) was implemented and then **calibrated in-game** against the stock flexible
test craft. The short version: the pure notch design did not hold up on real craft, and the
controller converged back toward the old gain-stabilising mitigation **plus** the new pieces. This
section explains every step of that convergence, with the measurements that forced each one, so the
reasoning is not lost and is not re-litigated.

### TL;DR

The original design's thesis was: *route the structural mode out of the measured rate with a tool
that is transparent in-band for that mode (notch below ~8 Hz, low-pass above), so the inner loop
keeps full bandwidth and stays responsive — no bandwidth floor, no feedforward decoupling, no
hold/slew state machine.*

In-game that thesis broke on three points:

1. **The online frequency estimator is unreliable on real craft.** The notch needs an accurate
   frequency; the stock craft give noisy, multi-modal, sometimes-near-Nyquist rates where the
   estimate is wrong or absent (Ariane reads ~7 Hz not the nominal ~1.4 Hz; Chatter reads
   6/8/22 Hz/NaN across runs).
2. **A surgical notch is not enough once the autotuner's gain is large.** On a high-MoI / low-torque
   craft (Ariane) the autotuned `Kp` is ~47; the notch leaks a few percent of the mode, and the loop
   re-amplifies that leakage into a full-scale control oscillation. Taming it needs the loop **gain**
   reduced, exactly as the old code did.
3. **Reducing the gain re-introduces the very coupling the old code's state machine handled.**
   Flooring the bandwidth makes the stopping-distance term `corrLinear = ω/bandwidth` re-inject the
   residual rate into the setpoint, which the feedforward then differentiates into a huge spike — so
   the feedforward must be cut and the setpoint made rate-independent **while holding**, which is the
   hold/slew gate the design had deleted.

The result is a hybrid. Everything below is gated on the **latch** (and, for the gate, on pointing
error), so a rigid craft never triggers any of it and runs the original calibrated controller
unchanged.

### What the test craft actually look like

Measured with diagnostic logging + FFT of the root-part rate during a steady hold. (Methodology
caveat below — these informed direction; the **tests** are the ground truth.)

| Craft | Estimator reads | Apparent dominant rate mode | Notes |
|---|---|---|---|
| **AutoPilotChatter** | 6.5 / 8.5 / 22 Hz / NaN (run-to-run) | hard to pin; high, near-Nyquist content | heavy, strong tip-mounted wheels; the high mode aliases badly |
| **AutoPilotFlexible** | ~2.8 Hz (Δω gave 3.9) | ~2.2 Hz | the cleanest case; roll mode ~25 Hz |
| **Ariane 5** | ~7 Hz | gimbal limit cycle historically ~1 Hz; rate content higher | huge MoI, tiny α≈0.085 even under thrust → autotuned Kp ~47 |

Takeaways that shaped the design:

- No clean low-vs-high split exists. The modes are smeared across ~2–25 Hz, often multi-modal, and
  the estimator cannot be trusted to land the notch on them.
- The `Δω`-fed estimator from the original design is **biased high** (differentiation amplifies high
  frequencies): on Flexible it reported 3.9 Hz while the rate actually oscillated at ~2.2 Hz, so the
  notch was placed above the mode and missed it. Feeding **high-passed ω** instead (ω minus its slow
  mean) tracks the dominant-amplitude component and fixed that particular bias — but did not make the
  estimator reliable in general.

### The convergence, step by step

Each row is one in-game build/measure cycle. "ctrl" = RMS of the pitch/yaw control output during a
hold (a *proxy* — see the methodology caveat; the final row is validated by the actual tests).

| Build | Ariane | Chatter | Flexible | Lesson |
|---|---|---|---|---|
| Original notch design | ctrl osc **0.82** | 0.6–0.9 | 0.6–0.9 | notch alone leaves a large limit cycle on all three |
| + estimator fixes (high-pass ω, Nyquist gate, sticky, f_split→12) | — | settles, ~8.5 Hz→notch | 2.8 Hz lock | Chatter now *settles* but residual chatter; routing 8.5 Hz to low-pass gave a slow limit cycle (corner 2.8 Hz × crossover 1.47 Hz ⇒ ~55° phase lag) — raised `f_split` so it notches instead |
| + absolute bandwidth **floor** (1.0 rad/s) | ff **explodes** (rms 3.6, max 9) | **0.14** | 0.36–0.61 | floor gain-stabilises Chatter; but flooring makes `corrLinear = ω/bw` re-inject ω → feedforward explosion on Ariane |
| + ff-cut + nominal-target (ungated, always-on when latched) | **0.005** ✓ | 0.65 (worse) | 1 Hz limit cycle | nominal-target removes the rate damping Chatter/Flexible need at hold → new slow cycle |
| + broadband ~2 Hz **fallback** when estimator unlocked | 0.005 ✓ | **0.003** ✓ | still poor (2 Hz corner too high for its 2.2 Hz mode) | fallback rescues the no-lock case (Chatter), but applying nominal-target during slew/settle removed braking |
| + **continuous hold gate** (nominal-target + ff-cut only while *holding*) | ✓ | ✓ | ✓ | the missing piece: damping/braking via the full target while slewing, rate-independent setpoint while holding |

The final row passes the real tests (`test_sustained_hold_chatter`, `test_flexible_mode_slew`,
`test_oscillation_auto_detection` on Chatter and Flexible; `test_ascent_hold_no_wobble` on Ariane).

### Final architecture

Pipeline on a latched axis (rigid axes skip all of it). `suppressionRamp ∈ [0,1]` is a one-pole ramp
that follows the latch; `holdFactor ∈ [0,1]` is a smooth function of pointing error (1 at ≤2.5°,
0 at ≥5°). `gate = suppressionRamp · holdFactor`.

1. **Detector + latch** — unchanged. `Δω > threshold·α·dt` drives `chatterLevel`; crossing
   `ChatterLatchThreshold` latches the axis (pitch/yaw coupled). The latch is the persistent "this
   craft is flexible" memory and gates everything below.

2. **Frequency estimator** — `FrequencyTracker`, one for pitch/yaw (fed the stronger transverse
   axis) and one for roll, fed **high-passed ω** every tick. Zero-crossing-interval method with a
   hysteresis deadband, a plausibility gate up to Nyquist, and an acquisition counter. The acquired
   value is **held sticky** (NaN only until first acquisition) so suppression quieting the mode does
   not lose the estimate and hunt. *Still unreliable on some craft — hence the fallback below.*

3. **Rate suppression** (`SelectSuppressionTool` / `ApplySuppression`), routed once latched:
   - estimator locked & `f < f_split` (12 Hz) → **notch** at `f` (`BiquadNotchFilter`, Q 2.5);
   - estimator locked & `f ≥ f_split` → **second-order low-pass**, corner `f / L_lp`;
   - **estimator not locked → broadband ~2 Hz low-pass fallback** (frequency-independent).
     This is what makes suppression robust without a trustworthy estimate.

4. **Bandwidth floor** (`DoAutoTuneAxis`) — a latched axis's rate-loop bandwidth is pulled toward
   `OscillationBandwidthFloor` (default **1.0 rad/s**), ramped by `suppressionRamp`, only ever
   lowering it, ζ preserved. **This is the primary gain-stabilizer** — dropping the crossover well
   below every structural mode stops the loop driving any of them, robustly and without needing the
   mode frequency. It replaced the design's `OscillationBandwidthSeparation` ratio (`2π·f/N`), which
   was too weak (it gave no reduction at all in the low-pass branch, where the mode is high) and
   depended on a good estimate.

5. **Continuous hold gate** — on a latched **and holding** axis (`gate → 1`):
   - the loop tracks the **nominal target** (velocity profile with measured ω = 0) instead of the
     full target, so the floored-but-still-large `Kp` does not amplify residual rate, and
   - the **feedforward is cut** (it is the loop path most able to drive the mode once the gain is
     floored; and differentiating a setpoint that contains ω — via `corrLinear` or via `dθ/dt` —
     re-creates the oscillation).
   While **slewing** (`gate → 0`) the axis keeps the full target (with its `corrLinear` braking) and
   its feedforward, so it tracks and brakes the maneuver. The blend is a smooth function of pointing
   error — **no hysteresis state machine** (the one simplification over the old design that survived).

6. **Output low-pass** (`SmoothOutput`) — a first-order ~2 Hz filter on the final actuator command,
   blended in by `suppressionRamp`. A MechJeb-style, gain-independent backstop that caps any residual
   control chatter; negligible phase cost at the floored ~0.16 Hz crossover.

#### Why this is mostly the *old* mitigation again

Floor + nominal-target-when-holding + feedforward-cut-when-holding **is** the old adaptive
flexible-craft handling. What is genuinely new and retained on top:

- the **notch / low-pass / broadband-fallback** rate cleaning (more surgical than the old single
  broadband filter when a good estimate exists; the fallback matches the old behavior when it
  does not),
- the **continuous** hold gate (replacing the old `HoldErrorEnter/Exit` hysteresis state machine),
- the **output low-pass** backstop,
- the **estimator** itself, now mainly an observability/routing aid rather than load-bearing.

The original design's bet — that a surgical notch lets you keep full bandwidth — does not survive
contact with a high-MoI craft whose autotuned gain re-amplifies the notch's leakage. Once you must
reduce the gain, in-band transparency stops mattering (the crossover is below the mode anyway), and
the gain reduction re-introduces the setpoint/feedforward coupling that the hold gate exists to
handle.

### MechJeb, for reference

MechJeb's default controller (`BetterController`, `MechJebLib/Control/PIDLoop2.cs`) does **no**
automatic structural-oscillation handling: its velocity loop reads the raw angular velocity, with
no detector, no notch, no estimator. It exposes manual per-craft knobs — `SmoothIn` (low-pass on the
measurement), `SmoothOut` (low-pass on the output), a filtered-derivative `N`, and an
`IntegralDeadband` — all defaulting to *off*. A user dials them in until a wobbly craft stops, or
accepts the wobble. It uses the same `MoI/torque` normalization we do, so on a craft like the Ariane
it would re-amplify residual rate the same way and would also need manual smoothing. The only idea
worth borrowing for our symptom (control-output oscillation) was the **output low-pass**, which is
point 6 above.

So there is no cleverer reference design to copy: taming these craft means reducing loop gain and/or
smoothing when flexible, whether automatically (us) or by hand (MechJeb).

### Public API as implemented

Unchanged from the original design except: `OscillationBandwidthSeparation` (a ratio) is **replaced
by `OscillationBandwidthFloor`** (absolute rad/s, default 1.0). The hold-gate band, the broadband
fallback corner, the output-filter corner, `f_split`, `L_lp` and the estimator constants are
internal (not exposed). `PitchYaw/RollOscillationDetectedFrequency` remains observable but should be
read as "the dominant high-passed-rate frequency the estimator locked", which on a multi-mode craft
need not equal the nominal first-bending figure (Ariane reads ~7 Hz).

### Results

In-game, against a freshly-restarted server:

- `test_oscillation_config`, `test_oscillation_force_on` (forces Notch / LowPass), `test_oscillation_force_off` — pass.
- **Ariane 5** ascent hold: `control_oscillation_amplitude` 0.82 → ~0.005 (bound 0.1); attitude held < 1°. Pass.
- **Chatter**, **Flexible**: `test_sustained_hold_chatter`, `test_flexible_mode_slew`, `test_oscillation_auto_detection` pass.
- Full Chatter + Flexible dynamic suites: running at time of writing.
- Rigid craft: every new mechanism is latch-gated, so they are byte-identical to the calibrated baseline.

### Methodology caveats (so the next person does not repeat them)

- **`ctrl` RMS is a misleading proxy.** A slow ~0.16 Hz reading is almost always a **window
  artifact** (the FFT's lowest bin over a 6 s capture catches settling/drift, not a real limit
  cycle). Optimize against the **actual test metrics** — `control_reversal_rate` (counts adjacent-tick
  sign reversals above a floor) and `control_oscillation_amplitude` — not the proxy. Several
  apparent "regressions" during calibration were the proxy lying; the real tests passed.
- **`pkill -f KSP.x86_64` does not reliably kill KSP** (it left a launcher+game pair and a stale
  server holding the kRPC port, so new launches connected to the *old* server). Kill by PID and
  verify `pgrep` is empty before relaunching.
- **The Python client is statically stubbed.** After any service-API rename, rebuild
  `//client/python` and copy the regenerated `krpc/services/spacecenter.py` into the env, or tests
  hit the old RPC names. `dir(conn.space_center.AutoPilot)` reflects the *client* stub, not the
  server — check the server with `strings` on the deployed DLL or by regenerating ServiceDefinitions.

### Open items / possible future work

- **The estimator is the weak link.** It is now mostly decorative (the floor + fallback carry the
  load). A more robust spectral/autocorrelation estimator could make the notch load-bearing again and
  recover some responsiveness on craft with a single clean mode — but only if a craft with a single
  clean mode is actually a target.
- **Integral deadband** (the one MechJeb idea not adopted) could be added if slow integral hunting
  shows up; deferred because it risks steady-state droop on a craft holding against a constant
  disturbance (e.g. gimbal under thrust).
- **`f_split` / `L_lp` / fallback corner / hold band** are compile-time; promote to properties only
  if in-game tuning on more craft shows a need.
- The detected-frequency test assertion for the Ariane was widened to 1–12 Hz to match the measured
  ~7 Hz; if a better estimator lands, tighten it back toward the structural figure.

#### Deferred test items (not controller work)

These are recorded as `TODO(deferred)` comments in `test_autopilot.py` at the named tests:

- **`test_partial_torque_smoothing` on `AutoPilotChatter`.** Its real assertion (`max_gain_jump`,
  the gain-smoothing the test exists for) passes; the trailing `check_rotation(45, 90)` is flaky
  because with its reaction wheels cut the heavy craft cannot hold attitude on RCS alone — it wanders
  ~±20°, so the final pointing check catches it at a random phase. Fix: give `AutoPilotChatter`
  adequate RCS (the same fix applied to the Nimble craft earlier), **not** loosen the threshold.
- **`test_orbital_directions` on the flexible craft.** It uses `wait_for_autopilot`'s *default* 60 s
  timeout; the prograde→retrograde step is a 180° slew through the antipodal singularity and can take
  longer than 60 s on a flexible craft, so it intermittently times out. Fix: thread `recover_timeout`
  through (or shrink the direction set).
- **Running the full 74-test suite in one go.** The marathon degrades KSP over its hour-long run, so
  tests that pass in isolation time out late in the run. Calibration here was done test-by-test for
  this reason; a one-shot green suite needs harness-stability work (e.g. periodic KSP restart between
  classes).

## Context and detection limits

*Originally `oscillation-context.md` — reference; MechJeb comparison and detection-limit notes.*

Background comparison and boundary notes that informed the design but do **not** affect what is
implemented in the *Oscillation suppression* section above.

### Comparison with MechJeb

MechJeb's attitude controllers do not detect or suppress structural oscillation automatically.
`MJAttitudeController` offers a `LowPassFilter` flag that applies a first-order filter to the **control
output** (not the measured rate), with a user-tunable time constant `Tf`. Users must tune it manually
or accept the wobble. MechJeb ships a generic `Biquad.cs` class but it is not used in the main attitude
control path.

### Detection limits (informational — no impact on the implementation)

These notes record the boundaries of what the detector can do, so the design's blind spots are
understood and don't get re-litigated. None of this changes what is implemented in the suppression
design.

1. **The detector is amplitude-based, not frequency-based.** It fires on `|Δω| > threshold·α·dt` — the
   measured rate changing faster than the available torque physically can — with no frequency content
   and no subtraction of the commanded motion. A structural mode that happens to sit at the
   "frequency" of a commanded slew is therefore **not** a special blind spot: a slew alone contributes
   at most `α·dt` per tick (full authority), well under the `threshold·α·dt` trip level, and a genuine
   structural swing adds to that and trips on its additive half-cycle regardless of how its frequency
   relates to the slew.

2. **The real blind spot is sub-threshold, low-acceleration modes.** Rearranging the trip condition, a
   mode goes undetected when its rate-amplitude `A < threshold·α/(2πf)` — i.e. when its peak angular
   *acceleration* `A·2πf` is below a few times the craft's control authority `α`. By construction those
   are modes the loop can reject as an ordinary disturbance without the feedforward pumping them; the
   destructive regime (loop resonantly drives the mode) is the high-`Δω` regime where the detector does
   fire. A mode straddling the threshold can latch intermittently — that is a sensitivity-tuning
   concern, exposed via `OscillationDetectionThreshold`, not a structural flaw. This is inherent to any
   *reactive* detector: below its threshold a small structural ripple is fundamentally indistinguishable
   from sensor noise or normal maneuvering without more information.

3. **Input shaping is a possible future preventive complement.** The notch is reactive — it damps a
   mode that has already been excited. The orthogonal approach is to avoid exciting the mode at all by
   shaping the outer-loop setpoint so its command spectrum does not overlap the mode (ZV / posicast
   input shaping, or simply rate-limiting the setpoint). For a craft whose mode straddles the detector
   threshold this would be a cleaner fix than hand-retuning slew rates. Out of scope; noted as a
   future option.

## Flexible-craft latch discrimination — findings and open problem

*Originally `flexible-latch-discrimination.md` — done (2026-07-02), resolved and since superseded. The quad-only nominal-target fix described in the *Resolution* subsection below shipped, and was later replaced by a stronger form in the control-loop redesign: the dual-target machinery is deleted entirely and the linear stopping coefficient is always computed from the unfloored gain (`ProfileKp`), which removes the failure at its cause. The latch itself remains deliberately permissive, as concluded here. The buzz-reduction changes (linear deadband, output + rate filters) are kept. See [`inner-loop.md`](inner-loop.md).*

**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` (`UpdateChatterDetector` /
`FrequencyPermitsLatch`, the flexible-craft mitigation), `PIDController.cs` (unchanged, net).

### The problem that started this

The new, rebuilt `AutoPilotFlexible` test craft (heavy, low-authority, mildly flexible) **times out**
on a simple 45° pitch slew: the autopilot never settles. `TestAutoPilotAttitudeFlexible.test_craft`
fails in `ap.wait()`.

Diagnosis (in-game, mitigation forced **off** vs **automatic**):

- With `PitchYawOscillationControl = Off` the craft **holds fine** — attitude settles to <1° (buzzy
  actuator, like stock SAS, but stable). So the craft does **not** need the mitigation.
- With `Automatic` (default) the chatter detector **latches** the craft as flexible, and the latched
  mitigation (bandwidth floor + hold-gate feedforward-cut + oscillation back-off) turns the holdable
  attitude into a **~0.28 Hz hold-gate limit cycle** that never satisfies `wait()`. The error bounces
  0.4°↔8° forever; the oscillation back-off is fed by the very cycle it creates, so it self-sustains.

So the root failure is a **false latch**: the detector treats benign root-part rate jitter on a
low-authority craft as a structural bending mode, and the mitigation then destabilizes a craft that was
fine without it.

#### Why the detector false-trips

The detector fires when the tick-to-tick raw-rate jump exceeds `k·α·dt` (`k = ChatterDetectThreshold
= 4`, `α = τ/I` the max angular acceleration). That bound is **authority-relative**: on a heavy,
low-authority craft `α` is tiny, so the bound is tiny, and ordinary root-part measurement jitter (a
few mrad/s, present even reaction-wheel-only) exceeds it every tick. The `AutoPilotFlexible` craft
trips it on ~100% of ticks while holding rock-steady at 0.5°.

### The core dilemma: the two craft are nearly identical to the detector

The mitigation exists for craft like the **Ariane 5** — a large flexible launch vehicle whose ~7 Hz
first bending mode genuinely limit-cycles the actuators *without* mitigation. The Ariane **needs** the
latch. The `AutoPilotFlexible` craft **must not** latch. But measured in-game they look the same:

| Signal | `AutoPilotFlexible` (orbit hold) | Ariane 5 (ascent hold) |
|---|---|---|
| MoI (p,r,y) | (1.07M, 0.29M, 0.79M) | (4.24M, 0.27M, 4.44M) |
| Torque | 71 k | 15.5 k |
| α (rad/s²) | ~0.067 | ~0.08 |
| Detector thr `4·α·dt` | ~5.4 mrad/s | ~6.5 mrad/s |
| Raw `|Δω|/tick` | ~7–8 rms, ~18 max | 8.6 median, 15.8 max |
| `chatterLevel` (pitch/yaw) | ~0.99 | ~0.99 |
| Needs mitigation? | **No** (holds fine off) | **Yes** (limit-cycles off) |

Same authority, same chatter level, same Δω magnitude. **Neither a frequency floor nor an absolute-Δω
floor separates them.** The only measured difference is behavioral: the Ariane limit-cycles without
mitigation; the `AutoPilotFlexible` craft does not.

#### The estimator is anti-correlated with reality (and deadlocks)

The obvious discriminator — "is there a real high-frequency mode?" via the online `FrequencyTracker` —
fails, because the estimator reads the *opposite* of the truth here:

- `AutoPilotFlexible` (no real mode): the impulsive jitter alternates sign nearly every tick, giving
  clean one-tick half-periods, so the estimator locks **rock-solid at exactly 25 Hz = Nyquist** on
  every run.
- Ariane (real ~7 Hz mode): while the mode runs uncontrolled its high-passed rate is messy and
  multi-modal, so the estimator gets no clean zero-crossings and stays **`NaN`** (never acquires).

Worse, gating the latch on the estimator **deadlocks** the Ariane: the estimator can only lock once
the mode is *controlled* (i.e. latched → suppressed), but the gate won't latch until the estimator
locks. No latch → mode runs wild → estimator never acquires → no latch. Before the change the Ariane
latched on `chatterLevel` alone and *then* the estimator acquired ~7 Hz (as `test_ascent_hold_no_wobble`
asserts). The gate inverted that dependency and broke it.

### What was implemented in the first session (WIP checkpoint, in `AttitudeController.cs`)

Three logically separate changes. Only the first is broken — **and it has since been reverted; see
*Resolution* below.**

#### 1. Frequency band-gate on the latch — **BROKEN, do not ship**

`UpdateChatterDetector` now latches an axis only if `chatterLevel ≥ ChatterLatchThreshold` **and**
`FrequencyPermitsLatch(i, dt)`, i.e. the estimator has acquired a frequency in
`[OscillationLatchFrequencyFloor = 3 Hz, OscillationLatchNyquistFraction = 0.8 · Nyquist]`. The band
was chosen to reject the `AutoPilotFlexible` craft's 25 Hz Nyquist artifact (25 > 0.8·25 = 20) and its
sub-Hz drift, while keeping a genuine 3–8 Hz mode.

- **Effect on `AutoPilotFlexible`:** works — the 25 Hz lock is rejected, the axis never latches, the
  craft runs the plain calibrated controller and settles (buzzy but stable). ✅
- **Effect on Ariane:** breaks — `fdet` is `NaN` for the whole ascent (deadlock above), so the latch
  never happens, the mitigation never engages, and the bending mode limit-cycles.
  `control_oscillation_amplitude ≈ 0.85` vs the test limit `0.4`. ❌

New symbols: consts `OscillationLatchFrequencyFloor`, `OscillationLatchNyquistFraction`; method
`FrequencyPermitsLatch(int, double)`; the `&& FrequencyPermitsLatch(...)` gate in
`UpdateChatterDetector`.

#### 2. Linear θ-keyed pointing deadband replacing the logistic attenuation — **keepable**

The outer loop used a logistic that attenuated the *target velocity* to ~0 near the target. Replaced
with a **linear** ramp (`DeadbandScale`): full above the high angle, ramping to 0 below
`DeadbandLowFraction = 0.5` of it. The high angle is the repurposed public
`PitchYawAttenuationAngle` / `RollAttenuationAngle` (default 1.0°, so band [0.5°, 1.0°]); their meaning
shifts from "logistic half-width" to "deadband high angle." Keyed on the **pure pointing error θ**, not
`e_stop = θ + coeff·ω`, so the measured-rate jitter is not fed through the ramp slope into the
setpoint/feedforward. Applied to the setpoint (outer loop) so the inner rate loop keeps full damping —
an earlier attempt that faded the *inner* proportional term instead lost rate damping and the hold
oscillated. Removed the now-unused `AttenuationSigmoidSlope`.

#### 3. Two chatterLevel-gated filters for a detector-firing-but-unlatched craft — **keepable**

Both blended by `chatterLevel` and **skipped on a latched axis** (the heavier suppression runs there),
so rigid craft (level ≈ 0) are untouched:

- **Output smoothing** (`DetectorOutputFilterTimeConstant ≈ 4.5 Hz`) on the delivered command, in
  `SmoothOutput`.
- **Measured-rate low-pass** (`DetectorRateFilterTimeConstant ≈ 5 Hz`) on `current` before the loops
  consume it — the real buzz fix, since the buzz is the inner loop chasing the ±7 mrad/s jitter
  (`Kp·ω`) and the stopping term (`ω/bandwidth`) re-injecting it into the feedforward.

These took the `AutoPilotFlexible` steady-hold actuator from **railing ±1.0** down to **rms ~0.08**
(peak ±0.35), holding dead-steady at ~0.5°, while staying stable. (`PIDController.cs` gained then lost a
`proportionalScale` param during the inner-deadband experiment; it is net-unchanged.)

### Current state (first session — superseded by *Resolution* below)

- `AttitudeController.cs`: all three changes above committed as a WIP checkpoint.
- Buzz work (changes 2 & 3) validated in-game on `AutoPilotFlexible`; user accepts the residual jitter.
- Change 1 (frequency gate) makes `AutoPilotFlexible` settle but **regresses Ariane** `test_launch`
  (and would regress the other Ariane hold/turn tests, and `test_ascent_hold_no_wobble`'s frequency
  assertion). Not yet run: the full rigid suite (the logistic→linear deadband change touches all craft).
- Throwaway probes left in `service/SpaceCenter/test/_ap_*.py` (not for commit).

### Candidate fixes (none yet chosen)

1. **Fix the mitigation, let both latch (attacks the real cause).** Revert change 1. Both craft latch
   on `chatterLevel` (Ariane works again). Then fix *why the latched mitigation limit-cycles the
   `AutoPilotFlexible` craft but not the Ariane* — prime suspect is the hold-gate + oscillation-back-off
   self-sustaining loop (`mitigationLevel = suppressionRamp · max(holdFactor, oscControlBackoff)`), which
   on this craft is fed by the cycle it creates. Risk: the back-off exists for flexible-craft maneuver
   recovery (Ariane pitch-overs), so it can't simply be removed. Open question: what, mechanically,
   makes the Ariane's latched hold stable and the `AutoPilotFlexible`'s not, given identical detector
   signatures? (Scenario differences: Ariane is under thrust with gimbal control during ascent; the
   flexible craft is coasting on reaction wheels + RCS.)

2. **Runtime behavioral discriminator.** Let both latch, but detect the *mitigation-induced* limit
   cycle (low-frequency, and the mitigation is making it worse rather than better) and back the
   mitigation off on that axis — an auto-disable when latching demonstrably hurts. Novel; needs a
   robust "mitigation is hurting" signal that doesn't false-positive on a genuine slow settle.

3. **Test whether the deadband already fixes the latched cycle.** — **TRIED, NEGATIVE (2026-07-02).**
   Disabled the frequency gate (latch on `chatterLevel` alone) and ran `AutoPilotFlexible` latched with
   the new linear deadband. It **still limit-cycles**: `wait()` times out, last-20s error mean 3.84°
   (0.02–6.05° swing, std 1.84), pitch actuator railing (ctrl rms 0.91, reversal 0.84). The deadband
   does not break the latched hold-gate cycle. So there is no discriminator-free path — the fix must be
   in the mitigation (option 1).

4. **Pause / rescope.** Revert to the original committed controller and rescope what's achievable this
   round (e.g. ship the buzz improvements only, behind the existing manual `Off` override for the
   flexible craft, and leave the auto-discrimination as future work).

### Recommendation

(3) is now ruled out (negative — see above), so the honest fix is **(1): fix the mitigation**, since
the latch decision genuinely cannot separate these two craft from any measured signal. The specific
target is the latched hold behavior on a craft that does not actually need mitigation: the bandwidth
floor (1 rad/s ≈ 0.16 Hz crossover) + hold-gate feedforward-cut + oscillation back-off together fail to
arrest the residual rate at the target → overshoot → ~0.28 Hz cycle, which the back-off then sustains.
The Ariane survives the same mitigation (its ~7 Hz mode sits far above the floored crossover and it is
under gimbal thrust); the `AutoPilotFlexible` cycle sits just above the floored crossover where the loop
can still drive it. Open question for that work: can the mitigation arrest the hold on a low-authority
craft without re-exciting a real mode — e.g. keep a *braking* feedforward while cutting only the
rate-injecting stopping term, or make the oscillation back-off not self-trigger on its own sub-Hz
output? Keep changes 2 & 3 regardless (real improvements, independent of the latch decision), pending a
rigid-suite regression run for the deadband linearization.

### Resolution (2026-07-02, second session) — option 1 implemented, probes green

Option (1) was implemented in `AttitudeController.cs`, on top of the WIP checkpoint:

#### What changed

1. **Frequency band-gate reverted.** `FrequencyPermitsLatch`, `OscillationLatchFrequencyFloor` and
   `OscillationLatchNyquistFraction` are gone; `UpdateChatterDetector` latches on
   `chatterLevel ≥ ChatterLatchThreshold` alone, as before this work. Both craft latch again — the
   latch is deliberately permissive, and the burden moved to making the latched mitigation benign on
   a craft that did not need it.

2. **Latched-hold nominal target: quad-only stopping (the actual fix).** The mitigation's "nominal
   target" was the velocity profile computed with measured **ω = 0** — no braking anticipation at
   all. That is precisely why the latched hold limit-cycled: a low-authority craft carrying residual
   rate had nothing in the setpoint to arrest it (feedforward also cut, inner loop floored to
   1 rad/s), so it systematically overshot the deadband; the hold gate + oscillation back-off then
   sustained the ~0.28 Hz cycle. The nominal target is now computed with the **actual (suppressed)
   rate** but with **only the quadratic stopping term** `ω²/2α` — the linear PID-lag term
   `ω/bandwidth` is dropped (`ComputeTargetAngularVelocity(..., linearStopping: false)`). The
   discriminating insight: the *linear* term's coefficient `1/bandwidth` is rate-independent and
   balloons ~5× at the floored bandwidth (1/1 rad/s = 1 s), so it injects mrad/s measurement jitter
   into the setpoint at large gain — that term was the real culprit and stays out. The *quadratic*
   coefficient `|ω|/2α` is self-scaling: for jitter-sized ω it injects sub-mrad nothing, for real
   motion it is genuine full-authority braking anticipation (and it flips the setpoint sign *before*
   the target when ω exceeds the braking profile — exactly the arrest that was missing).

Changes 2 & 3 from the first session (linear θ-keyed deadband, chatterLevel-gated output/rate
filters) are kept unchanged. Note the unlatched-axis filters are now mostly a transient/marginal
regime (the flexible craft latches again within ~1 s), but they are harmless and cover a craft whose
level hovers below the latch threshold.

#### Probe results (in-game, same probes as the analysis above)

- **`AutoPilotFlexible`** (`_ap_verify.py`, 45° pitch slew under `Automatic`): `ap.wait()`
  **SETTLED** with the axis **latched** — the previously-infinite limit cycle is gone. Final error
  0.96°. (Estimator stayed NaN this run; the fallback 2 Hz low-pass carried suppression.)
- **Ariane 5** (`_ap_ariane.py`, ascent): latches at **1.02 s** on chatterLevel alone (the estimator
  deadlock is moot again), estimator acquires **~8 Hz** at ~13 s once the mode is controlled, held
  ascent shows **`ctrl_osc_amp = 0.005`** vs the 0.4 test limit, max error 0.52°. The quad stopping
  term in the nominal target does not disturb the Ariane hold (its suppressed-rate residual is tiny,
  so the term is negligible there — by design).

#### Remaining work (paused here)

- **Full regression suite not yet run.** `TestAutoPilotAttitudeFlexible` was started and aborted on
  pause. Still to run: `TestAutoPilotAttitudeFlexible` (full class),
  `TestAutoPilotLaunch` (Ariane hold tests incl. `test_ascent_hold_no_wobble`'s frequency
  assertion), `TestAutoPilotLaunchAriane5` (+ other launch craft), and the rigid suite
  (`TestAutoPilotAttitude`, `Nimble`, `Slow`, `TVC`) — the deadband linearization touches all craft
  and has never been regression-run.
- The autopilot code comments still describe the old ω=0 nominal target (the "rate-independent
  target" wording, and the continuous hold gate) — update once the suite is green.
- Throwaway probes remain in `service/SpaceCenter/test/_ap_*.py` (not for commit).

## Adaptive TimeToPeak (bandwidth back-off)

*Originally `adaptive-timetopeak.md` — negative result; the proposed adaptive TimeToPeak mechanism was not built.*

> **Status:** negative result — the literal adaptive TimeToPeak proposed here was not built. The
> durable fix shipped instead is a per-group **control-output oscillation envelope** OR'd into the hold gate
> (`mitigationLevel = suppressionRamp · max(holdFactor, oscControlBackoff)`), so the existing mitigation
> (bandwidth floor + feedforward cut + nominal target) engages on a detected limit cycle regardless of
> pointing error — decoupling the floor from the hold gate, which was its blind spot during a maneuver.
> The manual `TimeToPeak` workaround has been removed from the Ariane tests
> (`TestAutoPilotLaunchAriane5`, `TestAutoPilotArianeNoSettle`, `TestAutoPilotArianeMidflightEngage`).
>
> **Why not the literal adaptive `TimeToPeak` below:** measured in-game, the limit cycle's driver is the
> feedforward/full-target *restoration* once the hold gate releases, not the loop bandwidth per se — so
> re-engaging the (feedforward-cutting) hold mitigation at the fixed 1.0 rad/s floor is sufficient, and
> no adaptive bandwidth is needed. The remaining cost is a slow (~several second) maneuver recovery at
> the floor; a faster recovery (adaptive global `TimeToPeak`, or retargeting the notch to the true
> bending mode) remains future work.
>
> The original note follows for context.

### Context

The kRPC autopilot tames structural oscillation on a latched (flexible) axis with three mechanisms
(see `service/SpaceCenter/src/AutoPilot/AttitudeController.cs`): a notch/low-pass
on the measured rate, an absolute **inner-loop bandwidth floor** (`OscillationBandwidthFloor`,
default 1.0 rad/s), and a hold-gated feedforward cut. The floor is the load-bearing gain stabilizer,
but it has two structural limits that *would* matter for a **low-frequency, in-band limit cycle**
(oscillation at a frequency at or below the loop's own bandwidth):

1. The frequency estimator cannot acquire below `MinFrequency = 0.5 Hz`
   (`service/SpaceCenter/src/AutoPilot/OscillationFilters.cs:120`), so a sub-0.5 Hz cycle never
   routes to the notch — it falls to the ~2 Hz broadband low-pass, which is far too high in
   frequency to touch it.
2. The bandwidth floor is gated on the **hold gate**
   (`mitigationLevel = suppressionRamp × holdFactor`, `AttitudeController.cs:~1263`), so a craft
   oscillating above ~2.5° pointing error never actually gets floored.

`TimeToPeak` already lowers the global inner-loop bandwidth (`ω₀ = π/(T_P·√(1−ζ²))`) and is *not*
hold-gated, so manually raising it (≈5 s) is the existing escape hatch. **Idea:** do that
automatically — ramp an effective TimeToPeak up until the oscillation subsides, then latch it for
the engagement.

**Validated case (supersedes the earlier "stale-config artifact" conclusion).** An earlier draft of
this note dismissed the sub-0.5 Hz cycle as a stale-config artifact, on the grounds that
`TestAutoPilotAriane.test_ascent_hold_no_wobble` passes (it does — but only because it engages and
then `wait(1)`s on the pad before staging, letting the loop settle). When the Ariane 5 is engaged and
staged **without that settle pause** — `ariane-launch.py` and `ariane-engage.py`, both of which *do*
call `ap.reset()`, so this is not stale config — the engagement transient seeds a genuine
low-frequency (<0.5 Hz) in-band limit cycle at the loop's own bandwidth. This is reproduced by
`TestAutoPilotArianeNoSettle` and `TestAutoPilotArianeMidflightEngage`
(`service/SpaceCenter/test/test_autopilot.py`). So the case the notch/low-pass cannot catch **does**
exist under default config.

**Current mitigations (interim).** Two are in place; neither is the durable fix:

- *Engagement soft-start* (`AutoPilot.SoftStartTime`, default 0.5 s): fades the actuator command in
  over the first second(s) of an engage, removing the max-deflection kick that *triggers* the cycle.
  Measured on the Ariane it helps but the 0.5 s default is not enough on its own (the cycle still
  builds); ~3 s removes the kick but introduces slight hold hunting. The soft-start attacks the
  trigger, not the loop's susceptibility, so it cannot be the whole answer.
- *Manual bandwidth reduction* `TimeToPeak = (5, 1, 5)`: lowers the pitch/yaw control bandwidth so the
  loop can no longer sustain the limit cycle. This is the reliable interim workaround, applied in the
  demo scripts and the two reproduction tests. The adaptive back-off below is exactly this, done
  automatically and only when needed (so well-behaved craft keep their responsive default bandwidth).

### Approach (sketch)

Generalize the existing fixed, hold-gated bandwidth floor into an **adaptive back-off**:

- **New effective-bandwidth state per axis group** (pitch/yaw coupled, roll separate — mirror the
  existing detector coupling). Equivalent to an internal "effective TimeToPeak" that only ever
  *raises* T_P above the user's setting (never lowers bandwidth below what the user asked for).
- **Adaptation law:** while an axis is latched *and* the oscillation signal is above threshold,
  ramp effective T_P up (lower bandwidth) on a slow time constant; when the signal stays quiet for
  a sustained window, **latch** the value for the rest of the engagement (no hunting). Reset on
  re-engage in `Start()` alongside `chatterLatched`.
- **Decouple from the hold gate** on this path — that gating is the current floor's blind spot.

#### The crux: the feedback signal

The adaptation needs a measure of *ongoing* oscillation that works in-band. The existing signals are
inadequate: `chatterLevel` is built on Δω (decays for slow cycles — was seen falling 0.9→0.04 while
the craft still oscillated), and `emaAbsHp` is high-passed at ~0.5 Hz (attenuates a 0.2 Hz cycle).
The test suite already has the right idea in `diagnostics.control_oscillation_amplitude`
(`tools/krpctest/krpctest/diagnostics.py`) — RMS of pitch/yaw control about its mean. A runtime
analogue (a band-limited envelope of the **control output**, or of the rate in a ~0.1–1 Hz band) is
the most promising signal. **This is the main thing to work out before any implementation.**

### Touch points (files)

- `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` — new per-group oscillation-amplitude
  signal; adaptation/latch state; apply the effective bandwidth in `DoAutoTuneAxis` (generalizing the
  `oscillationBandwidthFloor` block); reset in `Start()`; add a diagnostic-log field.
- `service/SpaceCenter/src/Services/AutoPilot.cs` — read-only observable (effective TimeToPeak /
  applied back-off) and likely an enable flag; follow the existing `[KRPCProperty]` patterns.
- `service/SpaceCenter/src/AutoPilotInfoWindow.cs` — optional readout in the OSCILLATION section.

### Verification

- Reuse `control_oscillation_amplitude` and the powered-ascent pattern of
  `TestAutoPilotAriane.test_ascent_hold_no_wobble`.
- **Fixture now exists:** `TestAutoPilotArianeNoSettle` / `TestAutoPilotArianeMidflightEngage`
  reproduce the sub-0.5 Hz in-band cycle. They currently pass *only* with the manual
  `TimeToPeak = (5, 1, 5)` workaround applied; the goal of the adaptive back-off is to make them pass
  with default `TimeToPeak`, at which point the workaround line can be removed from those tests.
- Must prove **zero regression** on rigid craft and on the already-good Ariane / Chatter / Flexible
  cases (rigid axes never latch, so the path must stay inert unless latched).

### Open questions

1. ~~Is there ever a real craft with a sub-0.5 Hz in-band limit cycle the notch can't catch?~~
   **Resolved: yes** — the Ariane 5 engaged without a settle pause (see "Validated case"). Build this.
2. Adapt TimeToPeak directly vs. adapt the bandwidth multiplier inside `DoAutoTuneAxis` (the latter
   reuses the existing floor arithmetic and keeps the user's TimeToPeak untouched).
3. Could simply **lowering `MinFrequency`** plus **decoupling the floor from the hold gate** cover
   the same cases more cheaply than a new adaptive loop? (Likely not: the chatter detector never
   *latches* an in-band cycle — its `Δω > threshold·α·dt` signature only trips on motion faster than
   rigid-body dynamics allow — so the notch/low-pass/floor path stays disabled regardless of
   `MinFrequency`. The control-output envelope signal with its own trigger is the mechanism that
   works. Confirm during implementation.)
