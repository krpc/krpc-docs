# AutoPilot inner loop: PID, analytic feedforward, and oscillation-mitigation structure

**Status:** done — the redesign shipped in the autopilot rework ([PR #882](https://github.com/krpc/krpc/pull/882)). Historical design record consolidating the design critique (background) and the analytic-feedforward redesign as built.

This layer is the attitude controller's inner rate loop — the per-axis PI tracking, its feedforward, and the oscillation-mitigation structure wrapped around it. The doc consolidates two former design docs: `control-loop-critique.md` (a design summary and critique of the shipped attitude controller, taken from the code as ground truth) and `control-loop-redesign.md` (the analytic-feedforward and restructured-mitigation redesign that responded to that critique, as built). The critique came first and is presented first as background; the redesign follows as the shipped answer.

## AutoPilot control loop — design summary and critique

*Originally `control-loop-critique.md` — reference: a design summary and critique of the attitude controller taken from the code as ground truth (2026-07-02), with a post-redesign status update at the foot.*

An assessment of the attitude controller design, taken from the code as ground truth
(`service/SpaceCenter/src/AutoPilot/`: `AttitudeController.cs`, `PIDController.cs`,
`OscillationFilters.cs`), including the uncommitted latch-discrimination changes.

### Summary of the design

The controller is a **cascaded attitude→rate architecture** running once per physics tick:

1. **Target conditioning.** The commanded quaternion target is optionally slewed toward at a
   latched constant rate (`TargetSmoothingTime`), and each engagement fades the actuator command
   in with a smoothstep soft-start, with integrators held cleared during the fade. PRELAUNCH
   re-runs `Start()` every tick so the loop effectively engages at clamp release.

2. **Outer loop (guidance).** Attitude error is computed as a minimum-arc rotation, resolved
   through the 180° singularity by a latched flip-plane, and converted to a **target angular
   velocity** via a bang-bang profile: `e_stop = θ + coeff·ω` with
   `coeff = max(|ω|/2α, 1/bandwidth)`, speed `min(v_max, √(2·|e_stop|·α))`, evaluated jointly in
   2D for pitch/yaw (the stopping-point-vector formulation) and 1D for roll. A linear deadband
   scales the setpoint to exactly zero near the target. Pitch/yaw run in a **roll-invariant
   frame** (roll angle stripped out), propagated incrementally so the frame never sees the
   antipode singularity.

3. **Inner loop (rate).** Per-axis PI controllers track the target rate. Gains come from **pole
   placement**: `Overshoot`/`TimeToPeak` → (ζ, ω₀) → `Kp = 2ζω₀·I/τ`, `Ki = ω₀²·I/τ`, recomputed
   every tick against one-sided-smoothed available torque, so closed-loop bandwidth is
   craft-independent. Two feedforwards are added: an acceleration FF (numerical derivative of
   the rate setpoint, low-passed at τ=0.05 s) and a gyroscopic FF cancelling ω×(Iω).

4. **Flexible-craft adaptation layer.** A physics-based chatter detector (tick-to-tick |Δω|
   exceeding what available torque could produce, `k·α·dt`) drives a per-axis level with
   fast-rise/slow-decay smoothing; crossing 0.6 **latches** the axis as flexible for the
   engagement (pitch/yaw latch together). A latched axis gets, in order of stated priority: a
   **bandwidth floor** (~1 rad/s, the frequency-independent primary), **notch or low-pass** rate
   filtering routed by an online zero-crossing frequency estimator (notch <12 Hz, LP above or
   when unacquired), **feedforward cut + quad-only nominal target** while holding, and **output
   smoothing** as backstop. The hold mitigation is gated by a continuous pointing-error blend
   (1°–2.5°) OR'd with a control-output oscillation envelope so a limit cycle during a maneuver
   still engages it. Detector-firing-but-unlatched axes get lighter input/output filters blended
   by the live level.

### Strengths

- **The core loop is genuinely good.** The cascade with a physically-derived velocity profile
  plus physics-normalized PI is the right structure — the same shape as MechJeb/stock SAS but
  more principled in the details. The 2D stopping-point formulation for pitch/yaw is the
  standout: tangential damping emerges from geometry instead of a bolted-on `-ω⊥` term, it is C1
  in ω (so the acceleration FF doesn't step), and it degenerates exactly to the 1D profile when
  ω is radial.
- **Numerics and state hygiene are unusually careful.** Filter states seeded to steady-state (no
  engage transients), integrators cleared on zero torque / roll disengage / soft-start,
  one-sided torque smoothing so an engine shutdown doesn't spike gains, the incremental
  roll-invariant frame, the antipodal plane latch, and the notch retune-without-reset. Each of
  these kills a real failure mode and most are documented with *why*.
- **The chatter detector is a clever discriminator.** "Rate changed faster than the available
  torque permits" is gain-independent and maneuver-independent — a legitimate full-authority
  slew cannot trip it. A much better trigger than amplitude thresholds.
- **Defense in depth on flexibility is well-ordered.** Leaning on the frequency-independent
  bandwidth floor as primary, with the notch/LP as refinement and output smoothing as backstop,
  means the system degrades gracefully when the frequency estimator (the weakest component, and
  the code admits it) fails to acquire.
- **Sign conventions, gates, and thresholds are documented at the point of use**, including
  which pairs of negations must flip together. For a controller this stateful, that is what
  makes it maintainable at all.

### Critique

#### 1. The adaptation layer is a patch stack, and it shows

This is the main structural criticism. The flexible-craft path carries roughly a dozen coupled
persistent states (`chatterLevel`, latch, `suppressionRamp`, `holdFactor`, `oscControlAuto`,
`oscControlBackoff`, `mitigationLevel`, three filter families) and ~15 hand-tuned time
constants. Several comments narrate limit cycles caused by *earlier versions of the mitigation
itself* — the ω=0 nominal target creating a 0.28 Hz cycle, the hold gate's blind spot needing
the envelope OR, the slow chatter decay needed so the mitigation doesn't un-trigger itself.
Each fix is individually sound, but the composite is a gain-scheduled system whose schedule is
a web of EMAs feeding thresholds feeding EMAs. Nobody can verify stability of this
analytically; correctness rests entirely on the test fleet. Concretely: the gate blends
*setpoints* based on an error that depends on the dynamics the blend produces — a hidden outer
feedback loop, and the most likely source of the next regression.

**Recommendation:** consolidate the per-axis flexible-craft state into an explicit mode
structure (rigid / noisy / latched-slewing / latched-holding) with the blends as documented
transitions, even if the runtime math stays identical — the state space is currently implicit
and combinatorial.

#### 2. Torque asymmetry is ignored

Everything — the profile's α, the gains, both feedforwards, the chatter threshold — uses
`AvailableTorqueVectors.Item1` (positive authority) only. KSP craft are routinely asymmetric
(offset RCS, gimbal geometry, aero surfaces). Where negative authority is materially weaker,
the bang-bang profile over-commits braking in that direction and the craft overshoots; the
autotuned bandwidth is optimistic there too. Using min(|pos|, |neg|) per axis, or
direction-dependent α, would be a cheap robustness win — and given the
available-torque-vs-limiter bug already fixed on this branch, the torque model has form as a
source of error.

#### 3. The feedforward is a noise path by construction

The acceleration FF numerically differentiates a setpoint that contains measured ω (through
`e_stop`), so rate jitter enters the FF at gain 1/(dt·α) before the 0.05 s low-pass. The code
knows this — it is exactly why the FF must be cut on latched holds — but the cut is a patch on
a self-inflicted problem. An analytic FF (the profile's segments have known accelerations —
α/2 on the bang-bang arc, since the stopping term sits inside e_stop and the converged
trajectory is the half-authority curve; ~0 on the cap) would remove the jitter path, at the
cost of handling the min/max switching explicitly. *(Update 2026-07-02: implemented — see the
*AutoPilot control-loop redesign* section below, Phase 1. The original text here claimed ±α on the
bang-bang arc, which was wrong; in-game measurement confirmed ~α/2.)*

#### 4. The left-handed sign convention is a standing hazard

Negated measured ω matched against `-sign(θ)` commands works and is well-commented, but it is a
matched pair of negations that any future contributor can break by "fixing" one of them. The
comments mitigate this about as well as comments can; a right-handed refactor would eliminate
the trap but is high-churn for zero behavior change — a judgment call.

#### 5. Minor items

- **Thread safety:** target setters run on the RPC thread writing a 4-double `QuaternionD` the
  physics thread reads — a torn read is possible in principle. Worst case is one tick of
  garbage target; probably acceptable, but a lock or volatile snapshot would close it.
- **Anti-windup is partial:** the integrator clamps to the full output range [-1,1] independent
  of how much headroom P+FF have consumed. Conditional integration catches the rail cases;
  mid-range saturation with a large P term can still wind up briefly. Standard back-calculation
  would be tidier; the fast rate loop makes this low-impact.
- **Frequency tracker fragility is real but priced in:** half-period counting fails on
  multi-mode content, and the design correctly doesn't depend on it (broadband LP fallback +
  floor). Fine as-is; a Goertzel bank would be the upgrade path if the notch ever needs to be
  trustworthy on its own.
- **`PIDController.Kd` and the derivative path are dead code** in autotune mode (always set 0).
  Harmless, slightly misleading about what the controller actually is (a PI rate loop).
- The per-axis plant model assumes diagonal inertia; the ω×(Iω) FF covers the gyroscopic
  coupling but products of inertia don't exist in the KSP API anyway, so this is as good as the
  data allows.

### Verdict

The rigid-craft core — profile, roll-invariant frame, pole-placement autotune, the two
feedforwards — is clean, well-reasoned, and better-engineered than the usual genre standard;
little needs changing beyond the torque-asymmetry gap. The flexible-craft layer is effective
and impressively validated, but it has grown by accretion into the least analyzable part of the
codebase: many interacting gates whose stability is empirical. The highest-value next steps are
(a) an explicit per-axis mode representation to make the adaptation state space legible, and
(b) direction-dependent torque in the profile and gains. Documentation quality in the code
itself is exceptional and is doing a lot of the load-bearing work — keep that bar.

### Status update (2026-07-02, same day — post-redesign)

The redesign (the *AutoPilot control-loop redesign* section below) addressed several findings above:

- **§3 (FF noise path): fixed.** The feedforward is analytic (no differencing); the numeric
  form's transverse-nudge spikes measured ~92× full scale before removal. Note the FF *cut* on
  latched holds survives on new evidence: even a noise-free FF is an open-loop authority path
  after the floored-gain PI, and retiring the cut measurably lost the Ariane hold. A follow-up
  defect in the analytic form itself: its braking closed forms are on-profile
  values and, applied off-profile at maneuver start, fought the PI at up to ~94% authority on
  low-α axes — fixed by tracking-fraction scaling. The general lesson stands: a model-derived FF
  is only as valid as the trajectory assumption baked into it.
- **§1 (patch-stack adaptation layer): restructured.** Detectors / gating policy / mitigation
  primitives are now explicit classes (shadow-verified bit-identical), each mitigation
  individually controllable via the API, and the dual-target machinery is deleted (the linear
  stopping coefficient uses the unfloored gain instead). The gating *behavior* is unchanged —
  the web of EMAs is now legible, not gone.
- **Still open:** §2 torque asymmetry, §4 sign convention, §5 minor items (thread-safe target
  writes, partial anti-windup, frequency-tracker fragility — the tracker's occasional
  high-harmonic lock is now a known-marginal test assertion awaiting the recalibration pass).

## AutoPilot control-loop redesign: analytic feedforward + restructured oscillation mitigation

*Originally `control-loop-redesign.md` — done: analytic feedforward + restructured oscillation mitigation, implemented 2026-07-02 (commits listed in the outcome summary below).*

### Outcome summary (2026-07-02)

- **Phase 1 (analytic FF): landed.**
  The self-consistent braking acceleration is α/2 as predicted; the numeric FF measured up to
  ~92× full scale of spike in the transverse-nudge regime, the analytic form is bounded ~1.5.
  The ŝ̇ term is neglected — chasing it turned out to be the numeric FF's worst pathology, not a
  fidelity loss. The cheap slew term overestimates ~30% rms (PI absorbs it; smooth-turn green).
- **Phase 2 (detectors/primitives/policy + per-mitigation API): landed** — the shadow scaffold,
  OscillationDetectors, RateFilter/OutputFilter, MitigationPolicy, scaffold removal, and the new
  RPC surface.
  Every extraction verified tick-for-tick bit-identical in-game via the in-process shadow
  compare (~5,400 samples per run across Automatic/Notch/LowPass/Off on the latching flexible
  craft). One subtle live semantic surfaced: chatterLevel persists across re-engagements (only
  the latch is per-engagement).
- **Phase 3.1 (delete dual-target machinery): landed.** The linear stopping
  coefficient now uses the unfloored gain (ProfileKp); Flexible hold envelope ~0.01, no 0.28 Hz
  limit cycle; Ariane hold amplitude 0.006–0.011 (limit 0.1).
- **Phase 3.2 (retire automatic FF cut): REJECTED with data.** With the cut retired, the Ariane 5
  hold amplitude rose from ~0.01 to 0.28–0.41 and one run lost the ascent attitude (19° error).
  The FF is an open-loop authority path summed after the floored-gain PI — destructive on a
  floored hold even with zero differencing noise. The "analytic FF ≈ 0 in-hold" hypothesis fails
  because disturbance-driven corrections keep the profile out of the deadband during a powered
  ascent. The automatic cut STAYS; `OscillationFeedforwardMode` still allows manual Off/Forced.
- **Phase 3.3 (remove oscControlBackoff): resolved as KEEP, by the 3.2 evidence.** The backoff
  exists to keep the gate (floor + FF cut) engaged when a limit cycle parks the error outside
  the hold band; 3.2 demonstrated the exact failure a backoff-less gate would restore. The
  manual `OscillationControlLevel` floor was absorbed into the Forced mitigation modes.
- **Known-marginal test assertion** (recalibration pass): the Ariane no-wobble test's estimator
  band (3–9 Hz) flakes — probe distribution 5.7/7.0/9.0/11.0/12.2 Hz across runs with the hold
  quiet in every case. Routing splits at 12 Hz so the high readings still select the notch.
- **Plan deviations:** the "revive TestAutoPilotAttitudeChatter" pre-requisite was vetoed by the
  user (disabled tests stay disabled; validation used the quick gate + targeted probes instead),
  and TestAutoPilotAttitudeSlow is omitted from routine runs (too slow).
- **Follow-up — in-game info window:** the oscillation
  section now mirrors detector → GATES → MITIGATIONS with one combined mode+engagement lamp per
  mitigation (dim when not acting, amber when engaged), gate lamps, and data registers (white
  text; detected frequency, chatter level, control envelope, live post-floor bandwidth); navball
  colors; amber HELD lamp in PRELAUNCH. New internal accessors expose the previously-transient
  hold factor, FF-cut, output-filter weight and applied bandwidth.
- **Post-redesign fix — off-profile feedforward:** the analytic FF's braking
  closed forms are on-profile values and were applied unconditionally; at maneuver start the
  linear branch commanded `−bw·s/(bw·s+α)` ≈ −0.94 against the saturated PI, producing a
  ~5%-authority crawl on low-α axes (the user-reported slow-starting 20° roll; high-α axes were
  hidden on the cap branch, which is why Phase 1 validation missed it). Fixed by scaling the
  braking terms by the tracking fraction `clamp(ω∥/speed, 0, 1)`. Lesson: an FF derived from
  on-trajectory assumptions must be gated on actually being on the trajectory.
- **Post-redesign fix — per-axis hold factor:** the hold gate keyed all three axes
  on the pointing error, so a latched roll axis stayed floored (FF cut) through a pure roll
  maneuver — observed live when the pre-fix FF fight excited and latched roll mid-maneuver and
  the tail crawled. Roll now keys on max(pointing error, roll error); pitch/yaw unchanged; the
  info window's HOLD row shows both factors. Diagnosis probe: `_ap_rollslew.py` (AP_CRAFTS env
  selects craft; note roll-latching proved stochastic — post-FF-fix, neither Flexible nor
  Chatter reliably latch roll on a 20° maneuver).
- **Post-redesign fix — high-α nudge regression** (overshoot gate — superseded in
  effect by — deadband-slope tracking scale, then speed cone): the
  analytic FF switch regressed `TestAutoPilotAttitudeNimble.test_nudge_mid_slew` (bisected to
  the Phase-1 analytic-FF switch) in two layers. (1) The deadband-slope term `speed·D′·θ̇` was the only FF term not
  scaled by the tracking fraction; after a fast crossing flips ŝ, ω is anti-parallel to the
  command and the term kicks at full authority *along* ω — the overshoot gate `min(1, speed/ω∥)`
  cannot catch this because it passes ω∥ ≤ 0 by design. Same lesson as the off-profile feedforward fix, completed:
  *every* on-profile FF term must be tracking-gated. (2) With the FF quiet, a sustained
  ±1.3° coast-through limit cycle remained — the sqrt profile's infinite origin slope commands
  speeds the inner loop cannot shed inside the deadband; previously masked by the numeric FF's
  incidental ∂tgt/∂ω·ω̇ damping (the flip side of §"an FF derived from on-trajectory
  assumptions": the numeric FF's measured-state coupling was both the spike pathology *and* a
  hidden stabilizer). Fixed by the linear PI-lag speed cone — see
  [`outer-loop.md`](outer-loop.md) for the full analysis, sizing and validation.

### Context

Two problems identified in the critique:

1. The acceleration feedforward numerically differentiates a setpoint containing measured ω,
   amplifying rate jitter by 1/(dt·α) — it is the path through which the bending mode reaches the
   actuators most destructively.
2. The oscillation-mitigation suite has grown by accretion into coupled EMAs/gates/blends that
   cannot be reasoned about or individually controlled.

Goals: a noise-free analytic feedforward; then restructure into **detectors → gating policy →
independent mitigation primitives**, each mitigation individually toggleable via the RPC API;
then retire what the redesign makes unnecessary.

Decisions taken:

- All three phases sequenced, each validated in-game before the next.
- The Phase-2 refactor must be numerically identical in Automatic mode (pure restructuring);
  simplifications land as separate individually-tested commits (Phase 3).
- The oscillation RPC surface may be redesigned freely — confirmed unreleased (`main` has zero
  oscillation members; the whole surface was added on this branch).

### Mitigation inventory: motivation and verdict

Signals (observation only): chatterLevel + latch (Δω > k·α·dt — gain/maneuver-independent
excitation test; the latch is persistent memory since the mitigated state is quiet), frequency
trackers + held Hz (tool routing), holdFactor (1°→2.5° — mitigate holds, keep slews responsive),
control-output envelope → oscControlBackoff (the hold gate is blind mid-maneuver),
suppressionRamp (no step at engage/release).

| # | Mitigation | Motivation | Verdict |
|---|---|---|---|
| M1 | Rate filter: notch(f,Q) / 2-stage LP on measured rate (latched, freq-routed, broadband-LP fallback) | remove the mode from feedback; keeps latched *slews* stable at full bandwidth | **Keep** — one primitive, mode {None, Notch, LowPass} |
| M2 | Bandwidth floor (~1 rad/s, × mitigationLevel) | primary frequency-independent stabilizer | **Keep** — the core |
| M3 | FF cut (× (1−gate)) | FF differencing noise re-drives the mode at floored gain | **Retire from Automatic after Phase 1** (noise source gone; the analytic FF is ≈ 0 in-hold anyway); primitive kept for manual forcing |
| M4 | Quad-only nominal target + dual-profile blend | the 1/bw stopping coefficient balloons ~5× when floored, re-injecting jitter | **Replace** with computing the linear coefficient from the *unfloored* bandwidth (flooring can then never inflate it); deletes the targetNominal / linearStopping / pidTarget-blend machinery |
| M5/M6 | Output LP, latched (τ=0.08 × ramp) and unlatched (τ=0.035 × chatterLevel) | backstop residual chatter / unlatched-noisy buzz | **Merge** — one OutputFilter primitive, (τ, weight) chosen by policy |
| M7 | Rate-input LP, unlatched (τ=0.03 × chatterLevel) | stop the loop chasing jitter at source | **Merge into M1** — same primitive, light stage |
| — | oscControlBackoff (envelope OR into gate) | close the hold-gate blind spot while the FF re-drove the mode mid-slew | **Candidate for removal in Phase 3.3** once M3/M4 land; keep the observables |

Net: 7 mitigations → 4 primitives (RateFilter, BandwidthFloor, FeedforwardScale, OutputFilter);
M4 collapses to a coefficient clamp; the backoff is possibly deleted from the policy.

---

### Phase 1 — analytic acceleration feedforward

Replace `(pidTarget − prevTargetRi)/(dt·α)` + 0.05 s LP with the profile's *planned*
acceleration, computed algebraically (no finite differencing).

**Key correction (verified):** the on-profile braking acceleration is **−α/2, not −α** — the
stopping term sits inside `e_stop`, so the converged trajectory is ω = √(αθ) (deceleration α/2).
Today's numeric FF reads ~0.5 during a steady brake; emitting ±1 would double the braking FF and
change behavior. Use the self-consistent closed forms:

- **Braking (sqrt) segment**: quad branch `a = −α/2` along ŝ (per axis FF_i = ∓ŝ_i·α₂d/(2α_i));
  linear branch (coeff = 1/bw active) `a = −α·bw·s/(bw·s + α)` → −bw·ω as ω→0 (the PID-lag
  exponential the term models).
- **Velocity-cap segment**: a = 0.
- **Deadband ramp**: product rule on speed(e)·D(θ): `a = −[(α/speed)·ė·D + speed·D′·θ̇]`,
  θ̇ = −ω projected on ŝ (bounded gain on ω — never divided by dt); the slope vanishes at the
  hold point so there is no jitter amplification.
- **Target slew** (TargetSmoothingTime > 0): add slewSpeed's component to θ̇/ė in all segments.
- **e_stop ≈ 0 guard**: FF = 0. Roll: same treatment 1D via a shared helper.

**Segment classification without chatter**: don't re-derive from thresholds — have
`ComputePitchYawVelocity` / `ComputeAxisVelocity` return a `ProfileSample` struct (ŝ, speed,
α₂d, bw₂d, CapActive, LinearCoeffActive, D(θ), |θ|) recording which branches their own
min/max/deadband arithmetic took. The only chattery seam is cap↔brake; the retained 0.05 s FF LP
smears genuine transitions over ~3 ticks — add a narrow smooth-min blend at that seam only if
logs show clustered `feedforward_spikes`. No hysteresis state unless both fail.

**ŝ̇ term**: FF_vec = −ŝ̇·speed − ŝ·d(speed·D)/dt; neglect ŝ̇ initially (it matters in the
nudge/orbit regime and antipodal flips; the deadband caps it near hold). Quantify from
side-by-side logs on nudge + 180°-flip tests; an analytic ŝ̇ formula is available as fallback
(all terms bounded products of ω).

**Hold-gate compatibility (Phase-1-only)**: today's FF also differentiates the gate blend.
Compute the analytic FF for both the full and nominal profiles (the two samples the two existing
calls already produce), blend by gate — matching the pidTarget structure; keep the (1−gate) cut
and the smoothedFfRi LP untouched.

**Commits:**

1. Profile functions return `ProfileSample` (behavior-neutral). Smoke: TestAutoPilotAttitude.
2. Analytic FF computed + logged side-by-side (`ff_num`/`ff_an` in LogDiagnostics); the loop
   still uses the numeric FF. In-game scripted session (slew / brake / hold / nudge / flip /
   capped slew / smoothing sweep) with DiagnosticLogging; offline compare: agreement in mean,
   analytic quieter tick-to-tick, quantified nudge-regime disagreement (the ŝ̇ signature).
3. Switch the loop to the analytic FF; delete prevTargetRi. Full validation: all five attitude
   suites + revived Chatter suite + TestAutoPilotLaunch* (`control_oscillation_amplitude < 0.1`,
   estimator 3–9 Hz), `feedforward_spikes` ≤ baseline.
4. Remove the transition logging.

**Pre-requisite**: investigate why `TestAutoPilotAttitudeChatter` is commented out
(test_autopilot.py:1293, git log) and revive it (manual-run if flaky) — it uniquely exercises
the unlatched chatterLevel-blend paths where the FF jitter lives.

---

### Phase 2 — numerically-identical structural refactor

**Layout** (`service/SpaceCenter/src/AutoPilot/`):

- `OscillationDetectors.cs` (new): chatterLevel/latch (+ pitch-yaw coupling), FrequencyTrackers
  + held Hz, high-pass bookkeeping (emaOmega/emaAbsHp), control envelope
  (controlMean/controlOscEnvelope), holdFactor. Observation only; owns the
  Chatter*/HoldError*/envelope constants.
- `OscillationMitigations.cs` (new): `RateFilter` (notch + 2-stage LP + light 1-pole stage in
  today's exact sequencing incl. inactive-state resets; absorbs M1+M7 state), `OutputFilter`
  (M5+M6 state, (τ, weight) per tick from policy), `BandwidthFloor` (floor + per-axis weight,
  consumed by DoAutoTuneAxis), `FeedforwardScale`.
- `MitigationPolicy.cs` (new): suppressionRamp, oscControlAuto/backoff, mitigationLevel, tool
  selection (SelectSuppressionTool routing, 12 Hz split, broadband fallback), override handling,
  gate computation; owns the routing/gate constants.
- `AttitudeController.cs`: frames, profiles, FF, PIDs, wiring; `Update` call order preserved
  exactly; keep Vector3d vs double[] types per signal to preserve float op order. The
  targetNominal blend stays here until Phase 3.1.

**Identity verification — in-process shadow mode** (cross-run comparison is defeated by physics
nondeterminism): a temporary scaffold keeps the old path verbatim as `LegacyOscillationPath`;
both paths run each tick on identical inputs; every signal (suppressed rate, gate, ffScale,
floor weights, output-filter result, chatterLevel, heldHz, envelopes) compared exactly, max-diff
+ first-divergence logged as `shadow=` in the diagnostic log; scripted scenarios (Flexible
slew/hold/nudge, Chatter, Ariane5 ascent, forced modes) must show 0.0 everywhere.

**New RPC API** (replaces the old surface; enums in their own files per the KRPCEnum pattern):
`RateFilterMode { Automatic, Off, Notch, LowPass }`, `MitigationMode { Automatic, Off, Forced }`.

Settable (9, same count as today): `PitchYawRateFilterMode`, `RollRateFilterMode`,
`PitchYaw/RollOscillationFrequency` (Hz, 1.5), `OscillationNotchQ` (2.5),
`OscillationBandwidthFloorMode` (+ `OscillationBandwidthFloor`, 1.0 rad/s),
`OscillationFeedforwardMode`, `OscillationOutputFilterMode`. Forced pins weight 1 (floor/output)
or scale 0 (FF) regardless of latch; Off disables that mitigation only. The rate filter keeps
the pitch-yaw/roll grouping (physical); the other mitigations are single knobs (per-axis
Automatic weighting stays internal). Removed: `PitchYaw/RollOscillationControl` +
`OscillationControl` enum, `OscillationControlLevel`, `OscillationControlThreshold`,
`OscillationDetectionThreshold` (→ policy constants; note: per-axis manual granularity is lost —
acceptable, the latch is already group-coupled; the detection threshold is trivially re-addable
if a sensitivity knob is missed). Observables unchanged: `OscillationLevel`,
`PitchYaw/RollOscillationLatched`, `PitchYaw/RollOscillationDetectedFrequency`,
`PitchYaw/RollControlOscillation`.

Note: today's `Off` clears the latch (killing floor/output/backoff too) and forced Notch/LowPass
drive the ramp — the new per-mitigation semantics are deliberately orthogonal, so
`test_oscillation_force_on/off` (test_autopilot.py:1023-1055) are rewritten alongside
`test_oscillation_config`, not re-pointed.

**Commits:** (1) shadow scaffold; (2) detectors extraction + shadow run; (3) primitives
extraction + shadow run; (4) policy extraction + constants relocation + shadow run; (5) delete
the legacy path; one full-suite in-game run here; (6) new RPC surface + rewrite the three
oscillation tests + rebuild stubs (`bazel build client/python tools/krpctest` + pip
force-reinstall) + config/force tests + Flexible + Ariane5 no-wobble in-game.

---

### Phase 3 — simplifications (one validated commit each, revert path = the commit)

**3.1 Delete the dual-target machinery.** The autotuner exposes a per-axis *unfloored* Kp:
`kp0 = twiceZetaOmega[i]·moi/smoothedTorque` (when AutoTune is off, `kp0 = pid.Kp` — already
unfloored). The profile always uses `bw = kp0·torque_actual/moi` for the linear coefficient
(keeps today's torque_actual/smoothedTorque factor — do NOT use twiceZetaOmega directly). Delete
targetNominal, the linearStopping threading, the pidTarget gate blend, and the FF nominal branch
from Phase 1. Watch: during a latched hold the linear term is now present at the calibrated
bandwidth (it was absent) — validate no ~0.28 Hz limit-cycle signature on Flexible hold;
Chatter; Ariane5.

**3.2 Retire the automatic FF cut.** The policy stops driving FeedforwardScale (scale ≡ 1);
Forced is retained. The residual risk is the FF as plant inversion during a floored hold — the
analytic FF is ≈ 0 there (the deadband slope → 0), which is exactly what the in-game run must
confirm. Validate: Flexible hold + Ariane pitch-over recovery + no-wobble.

**3.3 Re-examine oscControlBackoff.** After 3.1+3.2 the gate only feeds the bandwidth floor.
Test whether holdFactor alone suffices on the scenario the backoff was built for: a large
flexible launcher pitch-over recovery at default TimeToPeak. Keep it if recovery regresses; keep
the envelope observables regardless (they are the test oracle).

Each phase/commit updates the autopilot code comments (the target-angular-velocity and
flexible-craft-handling logic, incl. the "most destructively" feedforward path) and, at the end,
the design docs (the [`oscillation.md`](oscillation.md) pointer note and the critique section's
verdict above — also fix its "±α on bang-bang arcs" line to α/2).

### Risks

| Risk | Mitigation |
|---|---|
| FF braking value wrong (±1 vs α/2) | use the self-consistent closed forms; side-by-side logging gates the switchover |
| Seam chatter (cap↔brake, quad↔linear, slew-end) | 0.05 s FF LP; smooth-min at the cap seam only if spikes cluster; no hysteresis unless both fail |
| ŝ̇ neglect degrades nudge/flip | quantify from transition logs before deciding; analytic formula as fallback; the antipode plane latch bounds flips |
| Float-order divergence in the refactor | in-process shadow compare, exact equality per tick; pure code motion per commit |
| Chatter suite dead | revive before Phase 1 commit 3 (manual-run if flaky) |
| 3.1 latent limit cycle | explicit 0.28 Hz watch on the Flexible hold envelope; single-commit revert |
| 3.3 breaks pitch-over recovery | the dedicated Ariane pitch-over scenario is the accept/revert criterion |

### Verification protocol

Build/deploy loop per iteration: `bazel build //service/SpaceCenter` → `tools/install.sh` deploy
→ `pkill -f KSP.x86_64; nohup bash tools/run-ksp.sh &` → poll `krpc.connect()` → run tests from
`service/SpaceCenter/test/` (`python -m unittest test_autopilot.<Class>.<test> -v`).

**Quick gate (between changes — the full suite is too slow for per-commit turnaround):**

- `TestAutoPilotAttitude*.test_orbital_directions` (attitude classes except
  `TestAutoPilotAttitudeSlow`, which takes too long for the quick gate)
- `TestAutoPilotLaunch*.test_launch`
- `TestAutoPilotLaunch*.test_smooth_turn`

This covers the basics: the autopilot can point the vessel in vacuum and atmosphere.

**Targeted oscillation tests — only at decision points, not per commit:**

- Phase 1 commit 3 (FF switchover): `feedforward_spikes` ≤ baseline from the side-by-side logs;
  Ariane5 no-wobble.
- Phase 2 shadow runs assert `shadow=0.0` (identity), so the quick gate suffices per commit;
  one Flexible + Ariane5 no-wobble run after commit 5, config/force tests after commit 6.
- Phase 3 accept/revert criteria: 3.1 Flexible hold envelope (0.28 Hz watch); 3.2 Flexible hold
  + Ariane pitch-over recovery; 3.3 Ariane pitch-over recovery.

The remaining calibrated suites/assertions may need retuning after the redesign — deferred to a
final recalibration pass. Metrics via `tools/krpctest/krpctest/diagnostics.py`
(`feedforward_spikes`, `control_oscillation_amplitude`, `control_reversal_rate`). After RPC
changes: rebuild + reinstall stubs. No CHANGES.txt updates until PR-merge time (project
convention).

### Files

- `service/SpaceCenter/src/AutoPilot/AttitudeController.cs` (all phases)
- `service/SpaceCenter/src/AutoPilot/OscillationDetectors.cs`, `OscillationMitigations.cs`,
  `MitigationPolicy.cs` (new, Phase 2); `OscillationFilters.cs` unchanged
- `service/SpaceCenter/src/Services/AutoPilot.cs`; `Services/OscillationControl.cs` → replaced
  by `RateFilterMode.cs`, `MitigationMode.cs` (Phase 2.6)
- `service/SpaceCenter/test/test_autopilot.py` (oscillation config/force tests; Chatter revival)
- `design/*` (docs); `tools/krpctest/krpctest/diagnostics.py` (only if new log fields need parsing)
