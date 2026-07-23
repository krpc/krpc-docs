# Autopilot test plan

**Status:** in progress (2026-06-26) — infrastructure and most of the corner-case catalog are implemented
(but see **§11 for what is NOT yet implemented**, and the §10 caveat that these are
regression guards, not improvement proofs) — the `apply_angular_velocity` testing tool, the
`krpctest.diagnostics` parser + metrics, and the dynamic tests in `test_autopilot.py`, all
running across the five craft (§1) as separate, individually-tunable methods:

- `test_precession_when_nudged` (P1) — the headline orbit/limit-cycle guard.
- `test_oblique_nudge` (P3), `test_nudge_mid_slew` (P4) — mixed radial/tangential perturbations.
- `test_gyroscopic_cross_axis` (P5), `test_roll_nudge_isolation` (P6) — coupling/frame isolation.
- `test_great_circle_path` (§6A), `test_antipodal_flip` (§6B).
- `test_target_step_mid_slew` (§6C), `test_torque_dropout_recovery` (§6D).
- `test_anisotropic_authority` (§6E/F), `test_flexible_mode_slew` (§6G), `test_residual_hold` (P7).

Per-craft thresholds are factory kwargs (`winding_limit`, `path_deviation_limit`, `rebound_limit`,
`cross_axis_limit`, `roll_isolation_limit`, `ff_spike_limit`, `saturation_limit`, `nudge_rate`,
`recover_timeout`), loosened for the Slow/Flexible craft. Lint/build green; **none run in-game
yet**, so every numeric threshold is an initial estimate pending calibration against a live
game. The thresholds are isolated per test so they can be tuned independently.

**Scope:** `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` (+ `PIDController.cs`),
exercised through `service/SpaceCenter/test/test_autopilot.py`. KSP-in-the-loop integration
tests (the unit of truth — the controller is a closed loop against the physics engine).

**Goal:** move from "does it eventually point the right way?" to "does it point the right way
*well* and *safely* in the corner cases?" — settling time, overshoot, path straightness,
limit cycles, and especially **precession / orbit-when-nudged**, across the four authority
regimes. This catalog also covers the unified stopping-point pitch/yaw law (see
[`outer-loop.md`](outer-loop.md)).

---

## 1. Test craft matrix

The five craft span the axis that matters most (control authority vs. structural stiffness).
Characterise them explicitly so per-craft tolerances and expected behavior are intentional
rather than inherited.

| Craft | Regime | α = τ/I | Expectation | Tol (`angle_error`/`direction_error`) |
|-------|--------|---------|-------------|---------------------------------------|
| `AutoPilotNimble` | High authority | large | Fast, may chatter near target / spike ff | 2° / 0.1 |
| `AutoPilotNormal` | Normal | medium | Reference behavior | 2° / 0.1 |
| `AutoPilotSlow`   | Low authority | small | Slow, prone to overshoot if ff wrong | 2° / 0.1 |
| `AutoPilotFlexible` | Flexible | medium but flexible joints | Must not excite bending mode | 4° / 0.2 |
| `AutoPilotChatter` | Flexible, low authority, wheels at the tip | small | The §11.9 self-excitation fixture; must settle and hold chatter-free on **default** params (no per-craft tuning) — exercises the adaptive chatter detector | 3° / 0.2 |

Two gaps in the current matrix worth a fifth/sixth fixture:

- **Anisotropic authority** (pitch ≫ yaw or vice-versa). The joint pitch/yaw law projects α
  and the velocity cap onto an ellipse; nothing currently tests that a straight path holds
  when the ellipse is eccentric. Either a dedicated craft or reuse an existing one with
  `ap.max_angular_velocity` set asymmetrically (cheaper, see §6E).
- **Strongly asymmetric inertia** (long/flat craft) to exercise the gyroscopic term
  (`GyroscopicCompensation`). Again can be approximated on an existing craft by commanding a
  fast slew, but a purpose-built fixture makes the cross-axis precession unambiguous.

---

## 2. Telemetry and knobs available to tests

Everything below already exists on the service unless marked **[new]**.

**Read:**
- `ap.error`, `ap.roll_error` — pointing/roll error in degrees (only while engaged).
- `vessel.angular_velocity(ref_frame)` — body rate; magnitude is the limit-cycle/settle metric.
- `vessel.flight().pitch/heading/roll/direction`, `vessel.direction(frame)`.
- `ap.diagnostic_logging = True` then `ap.diagnostic_log` — CSV with a header row naming every
  column, then one row per physics tick (capped at 3000 rows / one minute, then logging switches
  itself off): `err`, per-axis `ang_err.p/.r/.y` (pitch/roll/yaw, roll-invariant frame),
  `omega_ri.*`, `tgt_omega_ri.*`, `ff_ri.*`, `gyro.*`, gains, `ctrl.*`, and the full
  profile/feedforward/detector/gate/mitigation state. This is the backbone of every dynamic
  metric below — `krpctest.diagnostics.parse_log` turns it into time series.

**Set:**
- Targets: `target_pitch/heading/roll`, `target_direction`, `target_rotation`, `reference_frame`.
- Settle gates: `stopping_angle_threshold` (default 1°), `stopping_velocity_threshold` (0.05 rad/s).
- Tuning: `time_to_peak`, `overshoot`, `auto_tune`.
- Outer-loop shaping: `max_angular_velocity`, `attenuation_angle`, `roll_start_angle`,
  `roll_engage_angle`.
- Feature flags: `decel_lag_correction`, `gyroscopic_compensation`.

**Testing tools:** `testing_tools.clear_rotation()` (zeroes attitude *and* rate),
`testing_tools.apply_rotation(angle, axis)` (attitude only — leaves rate at zero).

### 2.1 Required infrastructure (gaps)

1. **`testing_tools.apply_angular_velocity(angular_velocity, reference_frame, vessel)`
   — IMPLEMENTED.** There was previously *no* way to inject a deterministic angular velocity,
   which is exactly what the precession/nudge tests need (`apply_rotation` only re-orients).
   Added a procedure mirroring `ClearRotation` that puts the assembly into a rigid rotation
   about its center of mass — each part rigidbody gets the commanded spin (converted from the
   given frame, default the vessel surface frame) and the matching `v = v_com + ω×r` linear
   velocity, so it spins in place without shearing. Original sketch:

   ```csharp
   [KRPCProcedure]
   public static void ApplyAngularVelocity (
       Tuple<double,double,double> angularVelocity,
       ReferenceFrame referenceFrame = null,   // default: vessel surface frame
       Vessel vessel = null)
   {
       // world ω from frame; foreach part rb: rb.angularVelocity = worldOmega
       // (match ClearRotation's loop; keep rb.velocity = COM velocity so it spins in place)
   }
   ```

   Without this, the fallback is a **control pulse** (disengage AP, set `vessel.control.yaw =
   1` for N ticks, zero it, re-engage) — workable but timing-dependent and noisier; prefer the
   tool for repeatability.

2. **A diagnostic-log parser** (test helper). Parse `[KRPC.AP]` lines into a list of dicts /
   numpy arrays keyed by `t`, `err`, `ang_err_pitch/yaw`, `omega_ri`, `ff_ri`, `ctrl`. All
   §3 metrics derive from this. Put it in `krpctest` or a local helper in the test module.

3. **Metric helpers** computed from the parsed log — see §3.

---

## 3. Metrics (computed from the diagnostic log)

Define these once as helpers; every dynamic test asserts on them rather than only on the
final attitude.

- **Settling time** `t_settle`: first time after which `err(t)` stays below
  `stopping_angle_threshold` (e.g. 1°) and `|ω|` below `stopping_velocity_threshold`.
- **Overshoot**: `max(0, max_t(-(d/dt) crossing))` — operationally, the largest `err` excursion
  *after* the first zero-crossing of any `ang_err` component, as a fraction of the initial error.
- **Residual limit-cycle amplitude**: peak-to-peak of `err` over the last few seconds of a
  hold; should decay, not sustain.
- **Path deviation (great-circle straightness)**: treat `(ang_err_pitch, ang_err_yaw)` as a 2D
  point. For a pure slew it should travel radially to the origin. Max perpendicular distance of
  the trajectory from the straight line (initial point → origin), normalized by initial radius.
- **Orbit / precession radius decay** (the nudge metric): with
  `r(t) = hypot(ang_err_pitch, ang_err_yaw)` and `φ(t) = atan2(ang_err_yaw, ang_err_pitch)`:
  - *spiral-in (good):* `r(t)` monotone↓ (within noise), total `|Δφ|` bounded (< ~½ turn).
  - *limit-cycle orbit (bad):* `r(t)` ≈ const while `φ` keeps winding (`|Δφ|` ≫ 2π).
- **Feedforward spike count**: number of single-tick jumps in `ff_ri` exceeding a threshold
  (e.g. `|Δff_ri| > 0.5` between consecutive ticks). The whole point of items 2/3.
- **Control-saturation duration**: total time any of `ctrl.{p,r,y}` is at ±1.

---

## 4. Existing coverage (keep) and gaps

**Covered today** (endpoint-only — they assert the *final* attitude, not the journey):
set_pitch, set_heading, set_roll, set_rotation, set_direction, set_direction_and_roll,
orbital_directions, error, roll_error, invalid_reference_frame, reset/clean-disconnect, SAS
modes, other-vessel. These are good acceptance tests; leave them.

**Not covered at all:** every *dynamic* property — overshoot, settling time, path shape,
limit cycles, ff spikes, gyroscopic coupling, torque dropout, mid-slew target changes, the
180° antipodal singularity, and **precession/orbit-when-nudged**. The rest of this plan is
those.

> **Fix first — latent bug.** `test_autopilot.py:22` sets `cls.ap.decel_lagCorrection`
> (camelCase). The kRPC proxy silently accepts an unknown attribute as a plain Python field,
> so the Flexible fixture is **not** actually disabling decel-lag correction — it runs with the
> default `True`. Should be `cls.ap.decel_lag_correction = False`. This invalidates the one
> flexible-craft tuning the suite thinks it applies; fix before trusting any Flexible result.

---

## 5. Corner-case catalog — precession / nudge (the focus)

All of these settle on a target first, then perturb. The stopping-point law collapses to a 1D
bang-bang profile for radial perturbations (the §4 reduction); tangential perturbations are
where its lead-turn behavior matters and where the orbit/limit-cycle risk lives.

| # | Name | Setup (after settling on target) | Perturbation | Expected | Pass metric |
|---|------|----------------------------------|--------------|----------|-------------|
| P1 | **Tangential nudge at target** (the limit-cycle regression) | error ≈ 0 | inject ω ⟂ nose, in the pitch/yaw plane (`apply_angular_velocity`) | nose spirals in, no sustained orbit | radius decay monotone; `|Δφ| < ½ turn`; **no constant-radius orbit** |
| P2 | **Radial nudge** (1D-approach check) | error ≈ 0 | inject ω along the (small) error direction | behaves as 1D approach | radius decay monotone; no overshoot growth (the §4 reduction holds in-game) |
| P3 | **Oblique nudge** | small error | inject ω with both radial & tangential parts | path curves toward target, lead-turn | path deviation bounded; no overshoot growth vs P2 |
| P4 | **Nudge mid-slew** | large error (e.g. 90°) | inject tangential ω partway through the slew | great-circle re-converges, no S-curve | path deviation ≤ unperturbed slew + margin; overshoot ≤ baseline |
| P5 | **Gyroscopic precession** (asymmetric inertia) | error ≈ 0 on an asymmetric-MoI craft | command a *fast* slew about the low-inertia axis | ω×Iω drives cross-axis precession unless canceled | cross-axis `err` excursion smaller with `gyroscopic_compensation=True` than False |
| P6 | **Roll-rate nudge** (frame isolation) | error ≈ 0, roll controlled | inject pure roll (nose-axis) ω | roll bleeds off; pitch/yaw path uncontaminated | pitch/yaw `ang_err` stays within noise while roll settles |
| P7 | **Sustained-hold chatter** | error ≈ 0, hold 10 s | none (boundary-layer test) | residual decays | residual limit-cycle amplitude ↓ over the window; not sustained; worst on `Nimble` |

P1 is the headline regression test for the pitch/yaw outer law. Concretely:

```python
def test_precession_when_nudged(self):
    self.set_direction(self.vessel.flight().prograde, roll=0)
    self.ap.stopping_velocity_threshold = 0.02
    self.wait_for_autopilot()                       # settle on target
    self.ap.diagnostic_logging = True               # clears buffer
    # inject a pure tangential spin (perpendicular to the nose), e.g. about the
    # vessel "right" axis if the error plane is set up so it is tangential:
    self.connect().testing_tools.apply_angular_velocity(
        (0.0, 0.0, 0.3), self.vessel.surface_reference_frame)   # [new] tool
    self.ap.engaged = True
    self.ap.wait(30)
    self.ap.engaged = False
    log = parse_ap_log(self.ap.diagnostic_log)
    r = [math.hypot(s.ang_err_pitch, s.ang_err_yaw) for s in log]
    self.assert_monotone_decreasing(r, tol=...)     # spiral-in, not orbit
    self.assert_total_winding(log, max_turns=0.5)   # no sustained precession
```

Run it for all four craft; `Slow` (low authority, can't arrest the spin quickly) and `Nimble`
(can over-react) are the most likely to reveal an orbit or a new near-target chatter mode
(risk §8.1 of the design doc).

---

## 6. Other corner cases (beyond the nudge focus)

**A. Slew dynamics / great-circle path.** For combined pitch+yaw slews (e.g. 90° diagonal),
assert path-deviation and overshoot metrics, not just the endpoint. This is the test that the
joint pitch/yaw law actually produces a straight path rather than a per-axis curve. Cases:
30°, 90°, 150° diagonal slews. `Slow` guards overshoot; `Nimble` guards ff spikes.

**B. 180° antipodal flip.** Target exactly opposite the current nose. `FromToRotation` is
singular here (axis ill-defined); assert the vessel still converges and picks a consistent
geodesic rather than stalling or oscillating about the antipode. Add a slightly-perturbed
179.5° case to check the near-singular regime.

**C. Target step mid-slew.** Change `target_direction` while a slew is in progress; assert no
ff spike / saturation glitch at the discontinuity and clean convergence to the new target.
(`prev_target_ri` derivative across a target change is a known ff-spike risk.)

**D. Torque dropout / zero-torque axis.** Disable reaction wheels mid-slew (mirror the
existing `wheel.active = False` pattern) and/or use a craft with no authority on one axis;
assert the per-axis `RunAxis` zero-torque path clears the integral and the vessel doesn't
diverge or wind up. Re-enable and assert clean recovery (no kick from accumulated history).

**E. Anisotropy.** Set `ap.max_angular_velocity = (1, 1, 0.3)` (or use an asymmetric craft)
and run a diagonal slew; assert the path stays straight (the constraint-ellipse projection in
the joint law is correct) and there is no divergence — design-doc scenario (f).

**F. Parameter behavior.** `attenuation_angle` (boundary-layer width → trades chatter vs
settling time), `max_angular_velocity` cap (assert peak `|ω|` respects it), `auto_tune=False`
with hand-set `time_to_peak`/`overshoot` (assert the second-order response roughly matches the
requested ζ/ω₀ at small signal). `roll_start_angle`/`roll_engage_angle` blending: assert roll
stays suppressed above the start angle and engages below the engage angle (no roll kick at
large direction error).

**G. Flexible-mode safety (`Flexible`).** With the typo fixed (§4), assert that across a slew the
bending mode is *not* excited: `omega_ri` should not contain a growing oscillation, and
`decel_lag_correction=False` + large `time_to_peak` should be measurably calmer than the
defaults on this craft (design scenario e) — the stopping-point law must not introduce new
excitation.

---

## 7. Single pitch/yaw law (history)

The unified stopping-point law was developed behind a temporary `UnifiedPitchYawLaw` A/B flag so
it could be compared against the legacy radial + tangential-damping law in-game. The flag, the
legacy law, and the per-test A/B parameterization have since been removed: the stopping-point law
is now the only pitch/yaw outer law, and the dynamic tests (P1–P7, §6A/E/G) each run once against
it. The radial-reduction claim (unified ≡ legacy when ω is radial) was verified offline to 1e-14
over a 200k-case fuzz (see [`outer-loop.md`](outer-loop.md)); the dynamic tests now assert absolute
pass bounds rather than a legacy comparison.

---

## 8. Execution notes

- All of this requires a running KSP with the kRPC + TestingTools mods (same harness as the
  existing `test_autopilot.py`); it cannot run in CI without the game.
- The new craft (anisotropic, asymmetric-inertia) need `.craft` files in the test VAB set;
  the asymmetric cases can be approximated on existing craft via `max_angular_velocity` and
  fast slews first, and only promoted to dedicated fixtures if the approximation is too noisy.
- Build `apply_angular_velocity` into `TestingTools` first — P1–P6 depend on it.
- Keep tolerances per-craft (the table in §1); `Flexible` and `Slow` legitimately need looser
  bounds and longer timeouts.

---

## 9. Priority order

1. Fix the `decel_lagCorrection` typo (§4) — it silently disables a test's premise.
2. Add `apply_angular_velocity` + the log parser + metric helpers (unblocks everything dynamic).
3. **P1 tangential-nudge precession test**, all four craft — the corner case of interest
   and the pitch/yaw-law regression guard.
4. P2 (radial nudge / 1D-approach check) and §6A great-circle path metrics.
5. P3–P7, §6B–G as coverage broadens.

Audit follow-ups (2026-06-26, see §11.2 and §11.4–11.8). Items 7–9 are **done** (pending
in-game calibration); 10 remains:

7. **[DONE]** Added the untested API tests (§11.4): `pitch/roll/yaw_pid_gains`,
   `target_rotation`, `pitch_error`/`heading_error`.
8. **[DONE]** Wired up the `overshoot()` metric (§11.5) into `test_great_circle_path`.
9. **[DONE]** Roll-blending test (`roll_start_angle`/`roll_engage_angle`) and the
   `max_angular_velocity` cap assertion (§11.1).
10. Longer tail: **[DONE]** partial-torque-drop smoothing (§11.7) and reference-frame variety
    (§11.8). **Still open:** `attenuation_angle` and the autotune ζ/ω₀-response tests (§11.1/6F),
    the PRELAUNCH branch (§11.6), the moving-target / drifting-setpoint case and single-axis
    overshoot/roll dynamics (§11.3), and the §10 asymmetric-inertia / anisotropic fixtures (need
    new `.craft` assets).

---

## 10. Calibration watch-items (first in-game run)

All thresholds are estimates until run against a live game. Two tests need a closer look
before their results are trusted — they can pass or fail for reasons unrelated to a controller
regression:

- **`test_gyroscopic_cross_axis` (P5) is only a strong test on asymmetric inertia.** The four
  current craft are roughly inertially symmetric, so the `ω×Iω` cross-coupling it targets is
  small and the test may pass *trivially* (a near-zero cross-axis error) regardless of whether
  `gyroscopic_compensation` is doing anything. To make it bite, add a long/flat
  asymmetric-MoI fixture (per §1) or run it with `gyroscopic_compensation` off as the A/B
  baseline and require the on/off difference to be real. Until then, treat a pass as "not
  broken", not "gyroscopic compensation verified".

- **`test_antipodal_flip` (§6B) sits on a genuine singularity.** It commands an exact 180°
  flip (east→west heading), where the error-axis construction (`FromToRotation`) is undefined,
  and relies on physics noise to break the symmetry. A timeout/stall there may be a *real*
  finding (the controller parked at the antipode) rather than a flaky test — investigate
  before loosening it. If a deterministic version is wanted, bias the target a degree or two
  off exact-180 and add a separate near-singular (≈179.5°) case.

---

## 11. Not yet implemented

What the catalog above does **not** cover yet. None of these block a first calibration pass;
they are the known holes to close afterwards. §11.1–11.3 were noted with the original plan;
§11.4–11.8 were found by a coverage audit (2026-06-26) of the test file against the controller
and the full service API, and are **not** otherwise reflected above. §11.9 and §11.10 are
findings from Slow-craft calibration (2026-06-27): acceleration-feedforward self-excitation on
flexible craft (§11.9, controller follow-up, open) and excessive overshoot on low-authority rigid
craft (§11.10, root-caused to the available-torque model ignoring limiters — **fixed**, pending
Slow re-calibration). §11.11 is the full audit of the available-torque model that §11.10 prompted
(all four actuator limiters now applied; remaining gaps documented).

> **Closed since the audit (2026-06-26).** Items tagged **[DONE]** below now have tests:
> `test_max_angular_velocity_cap` and `test_roll_blending` cover the cap and roll-blend holes
> (§11.1); `test_pid_gains`, `test_target_rotation` and `test_pitch_and_heading_error` cover the
> untested API (§11.4); the `overshoot()` metric is now asserted in `test_great_circle_path`
> (§11.5); `test_partial_torque_smoothing` covers the one-sided smoothing (§11.7, via the
> now-parsed `Kp`/`Ki` log channels); and `test_reference_frame_switch_while_engaged` covers a
> non-surface frame and a mid-hold frame switch (§11.8). All thresholds are still uncalibrated
> estimates. Items still tagged open below — §11.1 (`attenuation_angle`, autotune ζ/ω₀), §11.3,
> §11.6 — remain to do.

### 11.1 Missing tests from this plan

- **P2 — radial-nudge / 1D-approach check.** The radial-reduction claim (the law collapses to a
  1D bang-bang profile when ω is radial) is verified offline (the 1e-14 fuzz in
  [`outer-loop.md`](outer-loop.md)). An in-game test that drives a purely radial (1D) slew and asserts
  a clean monotone approach with no overshoot growth would confirm the common case in the game.
- **§6F parameter-behavior tests.** Partly implemented:
  - **[DONE]** `max_angular_velocity` cap is actually *respected* — `test_max_angular_velocity_cap`
    asserts the commanded target rate stays within a low uniform cap. Asserts on the commanded
    target rate rather than measured `|ω|`; a measured-rate check is still possible.
  - `attenuation_angle` widens/narrows the boundary layer (chatter vs settling-time trade). Open.
  - `auto_tune = False` with hand-set `time_to_peak`/`overshoot` produces roughly the
    requested second-order ζ/ω₀ response at small signal. Open. (`test_pid_gains` covers the
    gain get/set API and the autotune-overwrite contract, but not the ζ/ω₀ response shape.)
  - **[DONE]** `roll_start_angle` / `roll_engage_angle` blending — `test_roll_blending` asserts
    roll stays un-actuated while the pointing error exceeds `roll_start_angle` (gyro disabled to
    isolate the roll law) and exercises both setters, covering the `RollWeight` path.

### 11.2 A/B coverage — resolved by removing the flag

This section previously tracked the legacy-vs-unified A/B coverage: that the dynamic tests should
exercise both laws, and that they asserted a shared absolute threshold rather than proving the
unified law *strictly better* than legacy. Both concerns are now moot — the `UnifiedPitchYawLaw`
flag and the legacy law have been removed, so there is a single law and a single code path. The
dynamic tests each run once and assert absolute pass bounds; the offline 1e-14 radial-reduction
fuzz (§7) remains the record that the law matches the old one in the radial regime.

### 11.3 Coverage beyond this plan (candidates, lower priority)

- **Roll-axis dynamics on its own.** Roll is only tested statically (endpoint) and via P6
  isolation; its settling time, overshoot, and `decel_lag_correction` behavior on the 1D
  `ComputeAxisVelocity` path are not dynamically tested.
- **Moving-target tracking.** Pointing at a frame-relative direction that drifts while the
  vessel orbits (e.g. `prograde`) means the setpoint moves; the rate-tracking behavior for a
  non-stationary target is untested (all current dynamic tests slew to a fixed attitude).
- **`decel_lag_correction` on/off A/B.** The Flexible fixture disables it in setup, but no test
  compares on vs off to confirm the flexible-mode benefit / rigid-craft overshoot trade.
- **First-tick / re-engage transient.** The `prevTargetRiValid` feedforward suppression on the
  first tick after `Start()` (and on re-engage) is not exercised by a dedicated test.

### 11.4 Untested public API surface — **[DONE]**

These service properties were exposed (`AutoPilot.cs`) with **no test at all** and not listed
elsewhere in this plan; all three now have tests:

- **[DONE] `pitch_pid_gains` / `roll_pid_gains` / `yaw_pid_gains`** — `test_pid_gains` sets and
  reads back the gains, asserts they survive an engage with `auto_tune = False`, and asserts the
  autotuner overwrites them (Kp changes, Kd → 0) with `auto_tune = True`.
- **[DONE] `target_rotation`** (quaternion) get/set — `test_target_rotation` round-trips the
  quaternion (compared via `|dot| ≈ 1` for the q/−q sign ambiguity) and confirms the
  `SetTargetRotation` path drives the vessel to the attitude.
- **[DONE] `pitch_error` / `heading_error`** — `test_pitch_and_heading_error` reads both getters
  (raise-when-disengaged, then known offsets against a torque-cut hold), mirroring `test_error`.

### 11.5 The `overshoot()` metric is implemented but never asserted — **[DONE]**

`krpctest.diagnostics.overshoot()` / `_component_overshoot()` existed and §3/§6A both call for
overshoot assertions, but no test used them. Now asserted in `test_great_circle_path` (with a
per-craft `overshoot_limit` loosened for `Slow` and `Flexible`). Still open: wiring it into the
single-axis slew tests (`test_set_pitch`/`test_set_heading` are still endpoint-only).

### 11.6 Unreachable code paths in the current harness

- **PRELAUNCH integral clear.** `AttitudeController.Update` zeroes the PID integral terms while
  `situation == PRELAUNCH`. Every test calls `set_orbit(...)` and runs in space, so this branch
  never executes. A pad-launch fixture (or a test that asserts no integral kick at lift-off)
  would close it.

### 11.7 One-sided torque smoothing — **[DONE]**

The `smoothedTorque` / `UpdateSmoothedTorque` logic exists specifically to avoid a single-tick
gain spike on a *partial* torque drop (e.g. engine shutdown while a reaction wheel keeps torque
> 0). `test_torque_dropout_recovery` cuts **all** torque (exercising `RunAxis`'s zero-torque
integral clear), but the smoothing needed a *partial* drop. `test_partial_torque_smoothing`
disables the reaction wheels mid-slew while keeping RCS, so torque drops sharply but stays > 0,
and asserts the per-tick fractional rise in autotuned `Kp` stays small (`diagnostics.max_gain_jump`,
fed by the now-parsed `Kp`/`Ki` log channels). Without the smoothing `Kp` would jump as
`moi/torque` grows.

### 11.8 Reference-frame coverage in the dynamic tests — **[DONE]**

Every other dynamic test uses `surface_reference_frame`. `test_reference_frame_switch_while_engaged`
now engages on a surface target, switches to `orbital_reference_frame` while still engaged,
re-points, and asserts re-convergence — covering both the switch-while-engaged path and a
dynamic slew/hold in a non-surface frame. Still open: the **moving-target / drifting-setpoint**
case (§11.3) — pointing at a frame-relative direction that moves while the vessel orbits — which
the orbital-frame hold here does not specifically stress.

### 11.9 Acceleration-feedforward self-excitation on flexible craft — **RESOLVED (adaptive flexible-craft handling), validated in-game on all five craft (2026-06-27)**

**Resolution.** A 90° slew of `AutoPilotChatter` (the wheels-at-the-tip fixture) on **default
parameters** went from *never settling* (±60° swings forever) to settling in ~15 s with ~0.4°
overshoot, holding within ~0.5° with **0% hold-chatter** (sign-reversals and saturation both zero,
measured bending oscillation collapsed). The other three fixtures — Normal, Nimble, Slow — are
**unaffected** and match their prior calibration exactly. The fix is three mechanisms, all **gated on
a runtime chatter detector** so they touch only a craft that is actually flexing:

- **Chatter detector** (`UpdateChatterDetector`): a per-axis `chatterLevel ∈ [0,1]` driven by a
  physics-based signature — the raw measured rate changing tick-to-tick by more than `α·dt` (the
  full-authority limit) can produce, i.e. `|Δω| > ChatterDetectThreshold·α·dt` (4×). Rigid-body
  motion and bang-bang reversals stay within `α·dt`, so they do not trip it. Asymmetric smoothing
  (rise 0.3 s, decay 30 s) holds the engaged state; `chatterLevel` persists across re-engages.
  Verified: Normal/Nimble/Slow all read `chatterLevel = 0` throughout (even Slow, whose low α gives a
  threshold of only 0.009 — its smooth-slew `Δω` is ~0.001, well under).
- **Three adaptations, each blended 0→1 by `chatterLevel`** (0 = original calibrated controller):
  1. *Rate filter* — `FilterAngularVelocity`, a 2nd-order low-pass (~2 Hz corner,
     `RateFilterTimeConstant = 0.08 s`) blended into the rate the loops consume.
  2. *Feedforward decoupling* — the acceleration feedforward differentiates a source blended from
     `target` (rigid) to `targetNominal` (the velocity profile with measured ω = 0, so it carries no
     bending content for the frequency-amplifying derivative to spike on). This was the single
     highest-leverage change: it dropped slew sign-reversals from ~40% to ~7%, overshoot 65°→0.4°.
  3. *Bandwidth reduction* — `DoAutoTuneAxis` ramps `Kp·α = 2ζω₀` toward `AdaptiveBandwidthFloor`
     (1 rad/s), preserving ζ; this gain-stabilises the mode and removes the residual hold-chatter.

**Why all three are gated rather than always-on (the dead ends, kept as a record):**
- A **static** rate filter destabilizes Nimble: its phase lag (~30° at Nimble's ~1.6 Hz rate-loop
  crossover) erodes the phase margin of Nimble's fast, integral-dominated loop (Kp≈0.4, Ki does the
  work) into a ~1.6 Hz limit cycle — Nimble's nudge tests time out. Off for `chatterLevel = 0`, fixed.
- A **static** bandwidth cap cannot serve both regimes: at ≈2 rad/s the flexible limit cycle vanishes
  completely, but Nimble then *orbits* after a nudge (precession winding 1.96 vs the 1.25 limit) — a
  high-authority craft needs a fast inner loop to arrest a spin. At 6 rad/s Nimble is fine but the
  flexible craft still chatters (~46% saturated). Flexible needs ≲ 3 rad/s, Nimble ≳ 4 — no overlap.
- Gating all three on the detector resolves it: by gain/authority alone a flexible craft is
  indistinguishable from a rigid one, but the `|Δω| > α·dt` signature distinguishes them directly.

**Residual / future work.** (a) An **approach-phase transient**: `chatterLevel` decays during a quiet
acceleration, the bandwidth drifts up, then re-clamps at the bang-bang brake — a few seconds of
partial chatter mid-slew before a clean hold (slew far-field and the settled hold are both clean).
(b) The preferred long-term upgrade remains a **bending-mode notch** (estimate the frequency — the
detector already isolates *when* to do so — and notch it), which would gain-stabilise the mode with
no bandwidth reduction at all, removing even the transient.

**Regression coverage (added).** `AutoPilotChatter` is now the fifth fixture
(`TestAutoPilotChatter`); the full dynamic suite runs against it on **default parameters** and is
green. Two new sign-reversal guards (via `diagnostics.control_reversal_rate`, the fraction of
adjacent ticks a >0.3 control axis flips sign — the limit-cycle signature) cover both halves of the
fix and run for every craft: `test_sustained_hold_chatter` asserts the **settled hold** is
chatter-free (the bandwidth-reduction fix; 0.0 on all five craft), and `test_flexible_mode_slew`
additionally asserts the **slew far-field** (err > 25°, excluding the approach transient) is
chatter-free (the feedforward-decoupling fix; 0.0 on the rigid craft, 0.083 on the vibrating craft,
vs ~0.40 when broken). `test_antipodal_flip` was changed to wait `recover_timeout` rather than the
default 30 s so a low-authority 180° flip has time to converge.

The original diagnosis that led to the fix above is retained here for context.

Found 2026-06-27 while building a low-authority "Slow" fixture. A long rocket with its reaction
wheels at the **far end** (rather than near the CoM) self-excites a Nyquist-frequency (25 Hz,
= half the 50 Hz physics tick rate) control limit cycle: pitch/yaw controls saturate ∓1 **every
tick**, the net (time-averaged) torque collapses to ≈0, and the craft behaves as if it had ~1/13
of its real authority — it never settles (overshoots ~60° per swing, rings indefinitely).

Diagnosis (all other suspects ruled out): electric charge is fine; `available_torque` is correct
and position-independent (reaction-wheel torque is a pure couple); MoI is correct (KSP's
`vessel.MOI` and kRPC's own parallel-axis `ComputeInertiaTensor` agree to 4 sig figs); and the
chatter is **not** a gain-magnitude problem — it persists at 100% of ticks even with `TimeToPeak`
raised to 30 s (`Kp` ≈ 8). The driver is the **acceleration feedforward** `ffRi`, which numerically
differentiates the *measured* angular velocity. The craft's lightly-damped bending mode sits near
25 Hz; the ff differentiation flips the control sign on a tiny rate perturbation, the ±1-every-tick
torque applied *at the tip* drives the bending mode resonantly, the root part (where
`Rigidbody.angularVelocity` is sampled) then swings ±0.043 rad/s — ~57× more than any real torque
could change the rate in one tick (`α·dt ≈ 0.0008`) — and ff differentiates *that* into ±2.5
control spikes, closing the loop. A steady manual input (AP off) shows the measured rate is smooth
(tick-to-tick variation 0.0004 rad/s vs ~0.043 under the AP), confirming the AP's own chatter is
what excites it. Rigid craft (Normal/Nimble) never trip this: ff sees only real rigid-body motion,
so it never saturates.

The existing flexible-craft mitigations do **not** suppress it: `DecelLagCorrection=False` only
removes the `corrLinear` stopping-distance term, and a larger `TimeToPeak` only lowers the PID
gains — neither touches the `ffRi` path that is actually driving the limit cycle (verified: both
still chatter ~91–100% of ticks). This is consistent with review weak-spot #2 (numerically-
differentiated ff is spike-prone) and the `FeedforwardSmoothTimeConstant = 0.05 s` low-pass being
too short (~2.5 ticks) to attenuate a 25 Hz oscillation.

Candidate fixes to prototype and verify against a wheels-at-the-tip fixture (a regression test
should assert net control efficiency `|mean ctrl| / mean|ctrl|` stays high / per-tick full
sign-reversals stay rare during a slew):
- Low-pass / rate-limit `ffRi`, or lengthen `FeedforwardSmoothTimeConstant`, so the ff cannot
  flip the command on a single-tick rate perturbation.
- Filter the measured angular velocity before it feeds the ff differentiation (a structural-mode /
  anti-alias filter at the sensor), separate from the value the PID tracks.
- Optionally gate ff-spike magnitude by available authority (a craft that physically cannot deliver
  `ffRi · τ_max` of acceleration should not be commanded a full-scale ff impulse).

Until fixed, the **Slow** fixture is built compact and stiff with weak central reaction wheels
(low authority via low torque, not via a long flexible body) so the rate sensor stays clean; the
flexible/bending regime remains the **Flexible** craft's job. The self-excitation case above would
need a dedicated wheels-at-the-tip flexible fixture (see §10 / §11.3) to regression-test the fix.

### 11.10 Excessive overshoot on low-authority (rigid) craft — **FIXED & RE-CALIBRATED (available-torque model)**

Found 2026-06-27 calibrating the rebuilt **Slow** fixture (the stock Normal airframe with RCS
thrust-limit and reaction-wheel authority both cut to 20%). The craft is rigid and chatter-free
(no §11.9 self-excitation — the stiff airframe's bending mode is well above 25 Hz), and it settles,
but it was badly **underdamped**: a bare 90° slew overshot ~30–40% (reached ~9° error, then
rebounded back out to ~32° before finally settling ~26 s), and the perturbation tests rebounded
16–19° on a nudge / torque-dropout — far past the autotuner's `Overshoot = 0.01` (1%) target.

**Root cause (NOT the control loop).** The original note here guessed inner-loop saturation and
asserted "torque and MoI are correct" — that was wrong. The available-torque the autopilot tunes
against was **overestimated ~5×** because neither limiter on this craft was reflected in it:

- **RCS thrust limiter ignored.** `RCS.GetTorqueVectors()`/`GetForceVectors()` built torque from
  `MaxThrust` (`GetThrust(1f, …)`), which ignores `ThrustLimit` (`thrustPercentage`). Thrusters at
  `thrustPercentage = 20` reported 100% torque.
- **Reaction-wheel authority limiter ignored.** `ReactionWheel.AvailableTorqueVectors` returned
  KSP's `GetPotentialTorque()` raw. Disassembly of `Assembly-CSharp.dll` confirms
  `ModuleReactionWheel.GetPotentialTorque` loads `PitchTorque/RollTorque/YawTorque` with **no**
  authority-limiter multiply — KSP applies `authorityLimiter * 0.01` only at actuation time. A wheel
  at `authorityLimiter = 20.4` reported full torque.

With τ inflated 5×, the autotune set `Kp = 2ζω₀·moi/τ` ~5× too small (sluggish inner loop), the
bang-bang peak rate `√(2(τ/I)θ)` ~2.2× too fast, and the stopping term `½ω²/(τ/I)` ~5× too short
(brakes too late) → large overshoot. It is **not** review weak-spot #5; it was a plant-model error.

**Fix applied (2026-06-27).** Available (not max) quantities are now limiter-aware:
`RCS.GetTorqueVectors`/`GetForceVectors` use `AvailableThrust` (thrust-limited + fuel-gated);
`ReactionWheel.AvailableTorqueVectors` multiplies by `authorityLimiter * 0.01`. `MaxTorque`/
`MaxThrust` keep their documented unlimited meaning. `KRPC.SpaceCenter` builds clean. The other
three fixtures (Normal/Nimble/Flexible) do **not** use limiters, so their torque and prior
calibration are unaffected — only Slow's baseline moves.

**Verified & re-calibrated (2026-06-27).** Re-probed Slow with the rebuilt DLL in-game: a 90° slew
now converges in ~12 s with the error decreasing **monotonically** (67→50→29→10→1.2→0.56°) — **zero
overshoot**. Across the full dynamic set the worst overshoot metric is `0.0` and `radius_rebound`
is ~0.005° (was 16–19°). The Slow per-craft thresholds were tightened to ~3× the worst observed
(floors for the near-zero metrics), matching the Normal/Nimble policy: `winding_limit` 2.0→0.8,
`path_deviation_limit` 0.7→0.25, `overshoot_limit` 0.8→0.1, `rebound_limit` 28→2.0,
`cross_axis_slack` 10→4.0, `control_spike_limit` 5→3, `saturation_limit` 15→1.0 (others unchanged).
Full `TestAutoPilotSlow` class is **33/33 green**. `recover_timeout` is left at 90 s because the
torque-cut tests still settle slowly even though the unperturbed slew is fast. The
inner-loop-saturation hypothesis is **not** needed — this was purely the plant-model error. **This
closes §11.10** (the success criterion — tightening the Slow bounds with the corrected torque in
place — is met).

### 11.11 Available-torque model — full audit of overlooked per-part settings (2026-06-27)

Triggered by §11.10: the limiter omission is one instance of a broader pattern. kRPC obtains
per-part torque three ways — reaction wheels, engine gimbals and control surfaces (plus any other
`ITorqueProvider`) route through KSP's `ModuleX.GetPotentialTorque`; RCS uses kRPC's own code — and
**KSP's `GetPotentialTorque` applies none of the per-part authority/limit sliders** (they are
applied only at actuation time). Audit of all torque providers, confirmed against the disassembled
`Assembly-CSharp.dll`:

| Provider | Source | Limiter slider | Other state correctly modelled | Status |
|---|---|---|---|---|
| Reaction wheel | KSP `GetPotentialTorque` | `authorityLimiter` | `moduleIsEnabled`, `wheelState`, `actuatorModeCycle==2` (SAS-only → 0) handled by KSP; `Active`/`Broken` by kRPC | **fixed** (×`authorityLimiter*0.01`) |
| RCS | kRPC custom | `thrustPercentage` | action group, `rcsEnabled`/`isEnabled`/shielded, per-axis `enablePitch/Yaw/Roll`, atm. pressure handled | **fixed** (`AvailableThrust` — also now fuel-gated; `MaxThrust` ignored fuel too) |
| Engine gimbal | KSP `GetPotentialTorque` | `gimbalLimiter` | `gimbalLock`, `moduleIsEnabled`, **`finalThrust`** (✓ scales with current thrust → 0 at zero throttle) handled by KSP; `Active`/`Gimballed` by kRPC | **fixed** (×`gimbalLimiter*0.01`) |
| Control surface | KSP `GetPotentialTorque` | `authorityLimiter` | `ignorePitch/Yaw/Roll`, **`Qlift`** (✓ aero-dependent → 0 in vacuum/at rest) handled by KSP | **fixed** (×`authorityLimiter*0.01`) |
| Other `ITorqueProvider` | KSP `GetPotentialTorque` | (per module) | whatever the module's own method does | inherits any omission; no per-type correction |

All four actuator limiters are now applied (commit pending). `MaxTorque`/`MaxThrust` deliberately
keep their unlimited meaning; only the `Available*` quantities the autopilot reads are
limiter-aware. `KRPC.SpaceCenter` builds clean.

**Smaller gaps left unfixed (situational; the autopilot's "constant max torque" assumption
already dominates here):**
- **Reaction-wheel electric charge** — `GetPotentialTorque` ignores EC; a power-starved wheel still
  reports full torque (was *not* the §11.10 cause — Slow's EC was confirmed fine).
- **Precision / fine-control mode (Caps Lock)** — halves RCS and reaction-wheel authority; not modelled.
- **Gimbal/control-surface torque is intrinsically throttle/airspeed-dependent**, so even when correct
  it makes `available_torque` time-varying while the autotuner treats it as constant. The limiter
  fixes remove the *static* overestimate, not this.

**Test coverage note:** none of the limiter paths have a unit/integration test asserting
`available_*_torque` tracks the slider. A cheap guard for a future session: a parts test that sets
`reaction_wheel`/`rcs`/`gimbal`/`control_surface` limiters to a known % and asserts the reported
available torque scales proportionally. Belongs with the §10 fixture work.

---

## 12. Atmospheric flight scenarios — not yet implemented

The current controller and test suite run entirely in vacuum (all test craft spawned in orbit via
`set_orbit`). This section documents the gaps for atmospheric use — ascent and re-entry — and
defines the planned controller improvement (aerodynamic disturbance feedforward) that is the primary
missing piece.

### 12.1 Why the current controller is insufficient for atmosphere

The controller is a closed-loop attitude tracker; disturbances (including aerodynamic torques)
appear as errors for the PI inner loop to reject. This is fine in vacuum, where disturbances are
small and slow. In atmosphere three things change:

1. **Large, rapidly-varying aerodynamic torques.** The weathervane effect (center of pressure
   ahead of the center of mass) produces a restoring torque toward the airstream. At max-Q this
   can easily exceed reaction-wheel authority. The PI rejects it reactively — error must first
   appear, then the integrator winds up — so tracking lag increases proportionally to `τ_aero /
   (Ki · τ_max)`. For a low-Ki (slow-authority) craft at high dynamic pressure this lag can be
   many degrees.

2. **Time-varying available torque.** Control-surface and gimbal authority scale with dynamic
   pressure (`Qlift`). The autotuner computes `Kp` once at engage time; if `q` changes
   significantly (as it does from pad to orbital altitude) the gains go stale. During ascent
   the craft transitions from high-q (fins dominate) to vacuum (reaction wheels only), so the
   effective torque authority changes by orders of magnitude. KSP's `GetPotentialTorque` does
   account for the instantaneous `Qlift` (per §11.11), which means the per-tick gain scheduling
   (`Kp ∝ τ/I` recomputed each tick) will adapt — but only as fast as the integrator winds up
   to the new equilibrium.

3. **No AoA management.** The controller will track the target attitude to within its authority
   regardless of angle of attack. The user is responsible for keeping AoA within structural and
   thermal limits from their script; nothing in the controller limits or signals an unsafe AoA.
   This is the correct division of responsibility but must be documented clearly so users are
   not surprised.

### 12.2 Aerodynamic feedforward — design

The planned improvement is a **disturbance feedforward** that estimates the current aerodynamic
torque and subtracts it from the control command before the PI sees it. This is distinct from the
existing *acceleration* feedforward (`ffRi`), which feeds the setpoint's angular acceleration into
the inner loop to handle trajectory tracking.

**What it would do.** At each tick, estimate the aero torque `τ_aero` about the vessel's center
of mass (in body frame), normalize by `τ_max` per axis, and add the result to the inner-loop
control output — counteracting the weathervane before the error grows:

```
ctrl = ctrl_pi + ctrl_ff_accel + ctrl_gyro + ctrl_aero_ff
```

With a good estimate, the PI no longer needs to drive a standing integrator state to cancel
`τ_aero`; it only fights residual estimation error, so tracking lag collapses even under large
aerodynamic loading.

**Estimating `τ_aero`.** Two options, in ascending complexity:

- **Option A — KSP aerodynamic torque sum.** Iterate over all parts, read the aerodynamic
  forces acting on each part via the FAR/stock aero model, compute the moment arm from the
  vessel CoM, and sum `r × F`. KSP exposes per-part aerodynamic forces through the stock
  model (via `Part.aerodynamicArea`, `Part.dragScalar`, etc.) but the cleanest route is
  `Vessel.GetAerodynamicForce()` or the `VesselAerodynamics` internal — neither is directly
  exposed via kRPC yet. A new kRPC property `vessel.aerodynamic_torque` (returning body-frame
  torque, normalized by `τ_max`) would expose this cleanly.

- **Option B — observer/estimator.** Compute the total body torque from `I · (dω/dt)` (angular
  momentum derivative), subtract the known control torque (`ctrl · τ_max`), and use the
  residual as `τ_aero`. This is a one-tick-delayed observer (needs a filtered `dω/dt`); it
  avoids any new KSP internals but is noisier and introduces a lag of at least one physics tick.
  Appropriate as a fallback or for a first prototype.

Option A is preferred for steady-state accuracy; Option B is easier to prototype in pure C# without
new service properties. The §11.9 rate filter (`FilterAngularVelocity`) is already in place and
would attenuate the derivative noise if Option B is used on a flexible craft.

**Implementation location.** A new method `AerodynamicFeedforward()` in `AttitudeController.cs`,
returning a body-frame control fraction vector, alongside `GyroscopicFeedforward()`. Gated by a
new public property `AerodynamicFeedforward` (default **on**, since it only activates when
`τ_aero` is non-negligible — or **off** until validated in-game, following the `UnifiedPitchYawLaw`
precedent). Exposed in `AutoPilot.cs` and `doc/order.txt`.

**Diagnostic logging.** Add `aero_ff=(p,r,y)` to the `[KRPC.AP]` log line alongside `gyro=`.
This allows the test harness to verify the term is engaging during atmospheric flight and is
comparable in magnitude to the gyro and accel-ff terms.

### 12.3 New test craft

Atmospheric tests cannot be run from orbit. Two new craft (`.craft` files in the test VAB set) are
needed:

| Craft | Purpose | Regime |
|-------|---------|--------|
| `AutoPilotAscent` | Launch vehicle: rocket body + engine (gimbal) + aerodynamic fins | Ascent through atmosphere; moderate dynamic pressure; moderate authority in thin air → very high authority during max-Q; must not diverge via weathervane |
| `AutoPilotReentry` | Re-entry capsule: blunt body + RCS only, no fins or gimbal | High AoA hold during re-entry; very high aero torque; minimal control authority; typical use: 30–40° AoA off retrograde |

The `AutoPilotAscent` craft exercises the aero feedforward under load. The `AutoPilotReentry` craft
provides the most demanding disturbance rejection scenario — low authority against peak aerodynamic
torque — and is the strongest test of the feedforward's benefit vs the pure-PI baseline.

### 12.4 New test infrastructure

The current `set_orbit(...)` harness spawns the craft in space. Atmospheric tests need:

1. **`testing_tools.set_surface_velocity(speed, direction, vessel)`** (or equivalent) — spawn the
   craft at a given altitude with a given airspeed so the test starts with a controlled, repeatable
   dynamic pressure. Without this, tests would have to fly a real ascent trajectory to reach
   the test condition, making them slow and sensitive to initial conditions.

2. **`testing_tools.apply_aerodynamic_state(altitude, airspeed, aoa, vessel)`** — the most useful
   primitive if KSP supports it: put the craft at altitude/airspeed without running a real ascent.
   Needs investigation into whether KSP allows this without a full scene transition.

3. **Atmospheric metrics** added to `krpctest.diagnostics`:
   - `aero_ff_magnitude(samples)` — RMS of the `aero_ff` log channel; confirms the term is
     engaging during atmospheric flight.
   - `tracking_lag(samples, reference)` — mean attitude error while a constant aerodynamic
     disturbance is applied; the primary metric showing feedforward benefit.
   - `pi_integrator_state(samples)` — tracks how much of the inner-loop correction is carried
     by the integrator (high = PI fighting a sustained disturbance, low = feedforward carrying
     it); should drop with feedforward on.

### 12.5 Proposed tests

All require the new craft and infrastructure above before they can run.

| Test | Craft | Setup | Assert |
|------|-------|-------|--------|
| `test_ascent_tracking` | `AutoPilotAscent` | set altitude + airspeed to give max-Q conditions; AP targets a pitch heading | attitude error stays below limit; no saturation-driven divergence |
| `test_aero_disturbance_rejection` | `AutoPilotAscent` | settled on target at moderate q; then increase q (airspeed) to amplify weathervane | error stays bounded; `pi_integrator_state` lower with feedforward on |
| `test_aero_ff_benefit` (A/B) | `AutoPilotAscent` | high-q steady hold; compare `AerodynamicFeedforward=True` vs `=False` | `tracking_lag(True) < tracking_lag(False) + margin` (strictly-better guard) |
| `test_max_q_no_divergence` | `AutoPilotAscent` | sweep dynamic pressure from low to max-Q; AP engaged throughout | craft does not diverge; `angle_error` stays within limit |
| `test_reentry_aoa_hold` | `AutoPilotReentry` | set re-entry-like conditions (high altitude, retrograde + AoA); AP holds target | converges to target and holds despite large weathervane; feedforward on reduces lag |
| `test_gain_scheduling_during_ascent` | `AutoPilotAscent` | engaged at sea level; climb to orbit | per-tick `Kp` tracks the changing `τ/I` as dynamic pressure changes (verify via `Kp` log channel) |

### 12.6 Caveats and out-of-scope items

- **AoA limiting is the user's job.** The controller does not and should not cap AoA; a script
  using the autopilot for ascent guidance should command safe headings and is responsible for
  structural limits. The plan could add a *test* that verifies the controller does not
  autonomously command an AoA above a user-set ceiling, but the enforcement is external.

- **Moving-target tracking** (continuously updating gravity-turn heading) overlaps §11.3 and is
  not explicitly repeated here. Atmospheric tests will naturally involve a moving target, but
  the dedicated moving-target test belongs in §11.3.

- **FAR (Ferram Aerospace Research) compatibility** is out of scope for the initial implementation.
  The Option A aero torque estimate would need to be FAR-aware. The Option B observer is
  model-agnostic and remains viable under FAR.

- **Reentry heating and G-force** are entirely the user's domain; the autopilot has no thermal or
  acceleration model.
