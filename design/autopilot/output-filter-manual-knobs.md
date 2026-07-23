# Manual knobs for oscillation-mitigation internals

**Status:** proposal — primary proposal is the output-filter weight + corner in `Forced` mode
(below); an audit of the *other* mitigations' hidden constants, and which are worth exposing,
follows in [Other hidden parameters](#other-hidden-parameters).

## Context

The output filter is one of the autopilot's four oscillation mitigations: a per-axis first-order
low-pass on the *delivered actuator command* (`OutputFilter` in
`service/SpaceCenter/src/AutoPilot/OscillationMitigations.cs`, applied via
`AttitudeController.SmoothOutput`). Its strength is set by two quantities:

* a **blend weight** in `[0, 1]` (0 = pass-through, 1 = full filter), and
* a **corner frequency**, expressed internally as a time constant `τ` (corner `f = 1/(2πτ)`).

`OscillationOutputFilterMode` (`MitigationMode`) selects how these are chosen:

* `Automatic` — latched axis: `τ = LatchedTimeConstant` (0.08 s, ≈2 Hz), weight = suppression ramp;
  unlatched-but-detector-firing axis: `τ = DetectorTimeConstant` (0.035 s, ≈4.5 Hz), weight =
  chatter level; rigid axis: weight 0.
* `Off` — weight 0 (state kept tracking).
* `Forced` — `τ = LatchedTimeConstant`, weight = 1.0.

The `Forced` case is currently fixed at the heavy 2 Hz corner and full weight — the user can force the
filter fully on, but cannot force it on *weakly*, nor at a different corner. Everything the primitive
needs (`OutputFilter.Process(index, u, τ, weight, dt)`) is already parameterized by `τ` and `weight`;
only the `Forced` branch hard-codes them.

## Proposal

Expose the two quantities as manual knobs that take effect **only in `Forced` mode** (ignored in
`Automatic`/`Off`, where the detector/policy own them):

* **`OscillationOutputFilterWeight`** — blend weight in `[0, 1]`. Default 1.0 (current behavior).
  Clamp to `[0, 1]`.
* **`OscillationOutputFilterFrequency`** — corner frequency in Hz. Default ≈2 (the current
  `LatchedTimeConstant` corner). Must be `> 0`; convert to the primitive's time constant as
  `τ = 1/(2πf)`.

Both are plain `double` `[KRPCProperty]`s on `AutoPilot`, delegating to `AttitudeController`, in the
style of `OscillationBandwidthFloor` / `OscillationNotchQ`.

## Wiring

In `AttitudeController.SmoothOutput`, replace the `Forced` branch's hard-coded pair:

```csharp
} else if (outputFilterMode == Services.MitigationMode.Forced) {
    tau = 1.0 / (2.0 * Math.PI * outputFilterFrequency);  // was OutputFilter.LatchedTimeConstant
    weight = outputFilterWeight;                          // was 1.0
}
```

No change to `OutputFilter.Process`, `MitigationPolicy.ChooseOutputFilter`, or the `Automatic`/`Off`
branches. Defaults reproduce today's `Forced` behavior exactly, so this is backwards-compatible.

## Notes

* Scope creep check: the sibling mitigations (`OscillationBandwidthFloor`, `OscillationNotchQ`) already
  expose their tuning value alongside a mode, so a per-mitigation `*Forced*` tuning value is consistent
  with the existing surface; we are only filling the gap for the output filter.
* These knobs are advanced/rarely-needed — document them under *Flexible craft → Output filter* in
  `doc/src/tutorials/autopilot.rst` as taking effect in `FORCED` mode only, and add both to
  `doc/order.txt`.
* A very low corner (large `τ`) adds real phase lag; the tutorial should note this only makes sense on a
  craft already held at reduced bandwidth (the same caveat the section already gives for the automatic
  case).

## Other hidden parameters

The output filter is not the only mitigation with fixed internals. Auditing the compile-time constants
across `OscillationDetectors.cs`, `OscillationFilters.cs`, `MitigationPolicy.cs`,
`OscillationMitigations.cs` and `AttitudeController.cs`, the following are currently un-exposed. Two of
them — the detection and control-oscillation thresholds — were RPCs before the refactor
(`OscillationDetectionThreshold`, `OscillationControlThreshold`) and were dropped; re-exposing them
restores that capability.

**Worth exposing** (genuine tuning; behavior is monotonic and easy to reason about):

| Proposed property | Constant (value) | Mitigation | Role |
|---|---|---|---|
| `OscillationDetectionThreshold` | `DefaultChatterDetectThreshold` (4.0) | detector | `Δω > k·α·dt` sensitivity; lower = more eager to call a craft flexible. *(was an RPC)* |
| `OscillationLatchThreshold` | `ChatterLatchThreshold` (0.6) | detector | chatter level at which an axis latches for the engagement. |
| `OscillationControlThreshold` | `EnvelopeThreshold` (0.2) | hold gate / back-off | control-output envelope above which the holding mitigations re-engage mid-maneuver. *(was an RPC)* |
| `OscillationHoldErrorFull` / `OscillationHoldErrorNone` | `HoldErrorFull` (1.0°) / `HoldErrorNone` (2.5°) | hold gate | pointing-error band for holding-vs-slewing; gates the bandwidth floor, feedforward cut **and** output filter at once. |
| `OscillationLowPassSeparation` | `LowPassSeparation` (3.0) | rate filter | low-pass corner = `f / N` when the forced/estimated mode is high-frequency. |
| `OscillationLowPassCornerMin` | `LowPassCornerMin` (2.0 Hz) | rate filter | broadband fallback corner while the estimator has not acquired. |
| `OscillationSplitFrequency` | `SplitFrequency` (12 Hz) | rate filter | notch-vs-low-pass routing split in `Automatic`. |

Each would follow the same pattern as `OscillationBandwidthFloor` / `OscillationNotchQ`: a plain
`[KRPCProperty]` with a default equal to today's constant, plus a `doc/order.txt` entry and a line in
the tutorial's *Flexible craft* subsection for the relevant mitigation. The hold band and split
frequency deserve a note that they are shared across mitigations / axis groups.

**Recommend keeping internal** (dynamics-shaping time constants and estimator internals — narrow useful
range, easy to destabilize, low user value):

* Detector level dynamics — `ChatterRiseTimeConstant` (0.3 s), `ChatterDecayTimeConstant` (30 s).
* Frequency estimator — `MinFrequency` (0.5 Hz), `AcquireCount` (3), `AgreeTolerance` (0.2),
  `LossTicks` (8), `DeadbandFactor` (0.25), the high-pass / period / abs-delta time constants (≈0.3–0.5 s).
* Gating / envelope time constants — `RampTimeConstant` (0.5 s, mitigation ramp-in),
  `OscControlMeanTimeConstant` (0.5 s), `OscControlEnvelopeTimeConstant` (0.3 s).
* Rate-filter light unlatched one-pole — `DetectorInputTimeConstant` (0.03 s, ≈5.3 Hz).
* Feedforward smoothing (`FeedforwardSmoothTimeConstant`, 0.05 s) and torque smoothing
  (`TorqueSmoothTimeConstant`, 0.5 s).

If any of these later prove necessary they can be promoted individually; there is no need to expose the
whole set. (The feedforward cut has no tuning constant of its own — it is driven entirely by the hold
gate — so exposing the hold band covers it.)
