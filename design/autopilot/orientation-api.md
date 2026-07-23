# AutoPilot — well-defined orientation API

**Status:** done — shipped in [PR #882 "Rework the Autopilot"](https://github.com/krpc/krpc/pull/882)
(merged 2026-07). The orientation-API integration tests pass in-game (`TestAutoPilotAttitude`).
Started from the fix for [#564](https://github.com/krpc/krpc/issues/564) (near-vertical `RollError`
singularity) and broadened into a redesign of the whole **pitch / heading / roll** orientation
surface. Breaks backwards compatibility deliberately. **No separate GitHub issue.**

## Motivation

#564 reported that `roll_error` returns "pointless big values" near vertical and that a scalar
`target_roll` cannot hold a rocket's orientation through a gravity turn. The immediate bug (the error
readout) is fixed, but it is one symptom of a structural problem: **every scalar pitch/heading/roll
value in the AutoPilot and Flight APIs routes through a single surface-frame Euler decomposition
(`PitchHeadingRoll`) that gimbal-locks at the vertical.** At pitch → ±90° heading and roll collapse
onto the same axis, so *heading and roll both become ill-defined* — and roll's implicit reference (the
vertical plane through the nose) vanishes exactly where rockets launch.

The goal of this document: make **orientation** the primary currency of the API — set and read as
rotations, or as direction + up-vector — and make every angle well-defined everywhere it can be. Roll
is re-anchored to a persistent, user-chosen reference so it stays well-defined; scalar pitch/heading
survive only as documented, heading-singular-near-vertical convenience.

## Core insight

The surface-frame Euler triple (pitch, heading, roll) is **not** a good primary representation of
orientation: it gimbal-locks. Three things are individually robust and should carry the API:

1. **A rotation (quaternion) is always well-defined** — no singularity anywhere. It is the canonical
   form for both setting and reading a target or attitude.
2. **Direction + up-vector is well-defined except at one user-controlled point.** Given a nose
   `direction` and a reference `up`, the roll is fixed by aligning the dorsal ("roof") axis to `up`.
   The only singularity is `up ∥ direction` (asking the roof to point where the nose already points —
   geometrically impossible, since roof ⊥ nose). The user picks `up`, so the singularity sits off the
   trajectory. This is the launch/gravity-turn workhorse #564 was missing.
3. **Every *error* is always well-defined** — an error compares two full orientations about a shared
   axis and needs no absolute frame. This is why the #564 `RollError` fix (nose-axis quaternion
   residual, `AttitudeController.RollErrorTo`) works, and it generalizes to pitch and yaw.

*Absolute* scalar pitch/heading cannot be made always-defined — heading is meaningless at the pole —
so they are demoted, not fixed. Roll, by contrast, *is* fixed: re-expressed against a persistent
reference vector (insight 2) rather than the vanishing vertical plane.

## Proposal

### 1. Three primary orientation knobs

Three ways to command orientation, differing in how the roll degree of freedom is handled — fully
pinned, held, or set against a reference:

```
AutoPilot.TargetRotation = rotation                  // full quaternion; roll fully pinned; never singular
AutoPilot.TargetDirection = direction                // nose→direction; roll held (suppressed)
AutoPilot.SetDirectionAndUp(direction, up, roll=0)   // nose→direction, roof→up (⊥nose), then roll° about nose
```

- **`TargetRotation` (get/set)** — set the complete target attitude directly, as a quaternion. Always
  well-defined; the canonical form for both setting and reading a target. Leaves the stored up
  reference (§2) unchanged.
- **`TargetDirection` (get/set)** — point the nose along `direction` and *hold roll* (suppress roll
  rotation — drive the roll rate to zero, no target angle). The "point here, don't care which way is
  up" knob. Well-defined (its `FromToRotation` implementation is already correct). Leaves the stored
  up reference (§2) unchanged.
- **`SetDirectionAndUp(Tuple3 direction, Tuple3 up, float roll = 0)`** — point the nose along
  `direction` and roll so the dorsal ("roof") axis aligns with `up` (its component ⊥ the nose), then
  apply an optional `roll` offset (degrees, default 0) about the nose. **Stores `up` as the persistent
  roll reference (§2).** Built on the existing `GeometryExtensions.LookRotation2(forward, up)`
  (`GeometryExtensions.cs:429`); no new geometry. Well-defined for every nose direction **except**
  `up ∥ direction`, where it falls back to direction-only (roll suppressed). `up` need not be
  normalized or perpendicular — it is projected (matching `LookRotation2` / `OrthoNormalize2`).

  Holding orientation through a gravity turn is now trivial and singularity-free: pass a fixed `up`
  (e.g. north). As the nose pitches vertical → downrange it never crosses north, so roll is defined
  the whole way — impossible today, where `target_roll`'s singularity sits on the launchpad.

**Continuity constraint.** `SetDirectionAndUp(direction, zenith, 0)` must reproduce today's
`roll = 0` (dorsal axis = body −z, roof in the vertical plane on the zenith side — see the
pitch-heading-roll tutorial). This grounds the new API in the existing convention and makes the
`roll` offset match the old scalar roll away from vertical. The `LookRotation2` (`forward → +z`,
`up → +y`) convention must be remapped onto kRPC's nose = body +y convention (the same remap
`QuaternionFromPitchHeadingRoll` encodes); the equivalence is an explicit unit test.

### 2. The persistent up reference — `TargetRoll` measured against it

The controller remembers an **up reference vector** (in the AutoPilot reference frame), defaulting to
the frame's "up" (zenith / radial-out). It is set by `SetDirectionAndUp`, or directly via the
`UpReference` get/set property (below); `TargetRotation`, `TargetDirection`, and the scalar
pitch/heading setters leave it untouched. It persists across direction changes — set it once and
every later roll is measured against the same reference, which is exactly what holding an attitude
through an ascent needs.

`TargetRoll` (get/set) is **kept and reinterpreted** as **roll about the nose relative to the up
reference** (roof aligned to the reference = roll 0), replacing the old pole-singular
"roll from the vertical plane". Consequences:

- With the default reference (zenith), `TargetRoll` reproduces today's values away from vertical, and
  is singular only when the nose is vertical (zenith ∥ nose) — the familiar case, now *movable*.
- After any `SetDirectionAndUp(dir, up, …)` with a `up` off the trajectory, `TargetRoll` is
  well-defined for the whole path. Setting `TargetRoll = r` re-rolls the current target to `r`
  relative to the stored reference (keeping the nose direction); reading it returns the current
  target's roll relative to the reference. `NaN` still means roll suppressed.
- `CurrentTargetRoll` (the slewed value) is measured the same way.

`SetDirectionAndUp(dir, up, roll)` is thus exactly sugar for "set the up reference to `up`, aim at
`dir`, and set `TargetRoll = roll`". The up reference is also a standalone get/set property,
`AutoPilot.UpReference`. Setting it re-anchors the reference — and hence how `TargetRoll` is measured —
**without moving the current target**: you can set the reference once, then command rolls against it
with `TargetRoll` while changing the nose direction freely.

### 3. Scalar pitch / heading → demoted convenience

`TargetPitch`, `TargetHeading` and `TargetPitchAndHeading` remain as ergonomic shortcuts for aiming
the nose by angle, documented as **heading-singular near vertical**. When roll is controlled they
preserve the current roll *relative to the up reference* (rebuilding via `SetDirectionAndUp`), so a
pitch/heading change no longer perturbs roll near vertical. (`TargetDirection` (set) is not demoted —
it is primary knob 1, §1.)

### 4. Singularity-free errors everywhere

Replace the Euler-subtraction errors with one residual decomposition of
`targetRotation × currentRotation⁻¹` into (pitch-axis, yaw-axis, roll-axis) components — the same
machinery `RollErrorTo` already uses. Expose as a single `AutoPilot.AttitudeError → (pitch, yaw,
roll)` with `PitchError` / `HeadingError` / `RollError` (and the `Current*` variants) as views.
`Error` / `CurrentError` (total angle) are already quaternion-based and unchanged.

### 5. Telemetry

`Flight.Pitch/Heading/Roll` are absolute angles and stay singular at the poles by definition:
document them as such and point users at `Flight.Rotation` (quaternion) / `Flight.Direction`. No
`Flight.RollRelativeTo(up)` RPC — the persistent up reference on the AutoPilot (§2) makes the
well-defined roll available through `TargetRoll` / `RollError` instead.

## Full API surface (current status → proposed disposition)

Complete `AutoPilot` RPC surface (59 members) plus the orientation-relevant `Flight` telemetry.
**Singular** = ill-conditioned at the vertical (pitch → ±90°). Disposition: **Keep** (unchanged),
**Add** (new), **Change** (behavior/semantics change — breaking), **Demote** (kept but documented as
singular / convenience-only).

### Orientation setters (inputs)

| Member | Singular today | Proposed | Notes |
|---|---|---|---|
| `TargetRotation` (set) | ✅ ok | Keep (primary) | knob 1 — full quaternion; roll fully pinned |
| `TargetDirection` (set) | ✅ ok | Keep (primary) | knob 2 — nose only, roll held (suppressed) |
| `SetDirectionAndUp(direction, up, roll=0)` | — | **Add** (primary) | knob 3 — nose→dir, roof→up⊥, +roll offset; only singular at `up ∥ direction` |
| `ReferenceFrame` (get/set) | — | Keep | frame the target is expressed in |
| `TargetPitch` (set) | ❌ heading/roll | Demote | convenience; rebuilds via PHR |
| `TargetHeading` (set) | ❌ heading/roll | Demote | convenience |
| `TargetPitchAndHeading(pitch, heading)` | ❌ near vertical | Demote | convenience |
| `TargetRoll` (set) | ❌ singular | **Change** | roll about nose relative to the up reference; well-defined except `up ∥ nose` |
| `UpReference` (get/set) | — | **Add** | the stored roll reference (§2); default zenith. Set re-anchors roll without moving the target |

### Target readouts

| Member | Singular today | Proposed | Notes |
|---|---|---|---|
| `TargetRotation` (get) | ✅ ok | Keep | canonical target readout (quaternion) |
| `TargetDirection` (get) | ✅ ok | Keep | `targetRotation * up` |
| `CurrentTargetRotation` / `CurrentTargetDirection` (get) | ✅ ok | Keep | effective (slewed) target |
| `TargetPitch` / `TargetHeading` (get) | ❌ heading | Demote | PHR-derived |
| `CurrentTargetPitch` / `CurrentTargetHeading` (get) | ❌ heading | Demote | PHR-derived |
| `TargetRoll` (get) | ❌ singular | **Change** | roll relative to the up reference; well-defined except `up ∥ nose` |
| `CurrentTargetRoll` (get) | ❌ singular | **Change** | slewed roll relative to the up reference |

### Errors

| Member | Singular today | Proposed | Notes |
|---|---|---|---|
| `Error` / `CurrentError` | ✅ ok | Keep | quaternion total angle |
| `RollError` / `CurrentRollError` | ✅ fixed (#564) | Keep | nose-axis residual `RollErrorTo` |
| `PitchError` / `HeadingError` | ❌ Euler subtraction | **Change** | from residual decomposition (`AttitudeError`) |
| `CurrentPitchError` / `CurrentHeadingError` | ❌ Euler subtraction | **Change** | as above, effective target |
| `AttitudeError` → (pitch, yaw, roll) | — | **Add** | unified residual; the scalar errors become views |

### Frame / blend / tuning config (no orientation singularity)

| Member(s) | Proposed | Notes |
|---|---|---|
| `RollStartAngle`, `RollEngageAngle` | Keep | roll blend zone |
| `RollAttenuationAngle`, `PitchYawAttenuationAngle` | Keep | pointing deadband |
| `MaxAngularVelocity`, `AutoTune`, `TimeToPeak`, `SoftStartTime`, `TargetSmoothingTime`, `Overshoot` | Keep | profile/slew tuning |
| `StoppingAngleThreshold`, `StoppingVelocityThreshold`, `Wait(timeout)` | Keep | settle thresholds + blocking wait |
| `PitchPIDGains`, `RollPIDGains`, `YawPIDGains`, `PitchYawRateFilterMode`, `RollRateFilterMode` | Keep | per-axis controller config |
| `PitchYawOscillationFrequency`, `RollOscillationFrequency`, `OscillationNotchQ`, `OscillationBandwidthFloor(Mode)`, `OscillationFeedforwardMode`, `OscillationOutputFilterMode` | Keep | oscillation mitigation config |
| `PitchYawControlOscillation`, `RollControlOscillation`, `OscillationLevel`, `PitchYawOscillationLatched`, `RollOscillationLatched`, `PitchYawOscillationDetectedFrequency`, `RollOscillationDetectedFrequency` | Keep | oscillation readouts |
| `SAS`, `SASMode`, `Engaged`, `ShowInfoUI`, `Reset()`, `DiagnosticLogging`, `DiagnosticLog` | Keep | session / control / diagnostics |

### Flight telemetry (orientation-relevant)

| Member | Singular today | Proposed | Notes |
|---|---|---|---|
| `Flight.Rotation` | ✅ ok | Keep | quaternion — always-defined attitude |
| `Flight.Direction` | ✅ ok | Keep | nose vector |
| `Flight.Pitch` | ❌ near vertical | Demote | absolute; document, point at `Rotation` |
| `Flight.Heading` | ❌ near vertical | Demote | absolute; undefined at the pole |
| `Flight.Roll` | ❌ singular | Demote | absolute; use AutoPilot `TargetRoll` / `RollError` for a well-defined roll |

## Tutorial update — `doc/src/tutorials/autopilot.rst`

The "Using the AutoPilot" section (`autopilot.rst:14`) currently teaches only reference frame +
`target_pitch_and_heading` + optional `target_roll` — i.e. the demoted, pole-singular path. Rework its
opening to teach the new model. Add a "Setting the target attitude" subsection under "Using the
AutoPilot" with three parts:

### Part 1 — the three primary ways to set attitude

Frame them as "how much of the roll do you want to pin?", in table/prose form:

1. **`target_rotation`** (quaternion) — pin the full attitude. Always well-defined; the canonical form.
   Best when you already have a rotation (e.g. copied from another vessel or a saved orientation).
2. **`target_direction`** (a vector) — point the nose; **roll is held** (the autopilot zeroes roll
   rotation but holds no specific angle). The "point here, don't care which way is up" knob.
3. **`set_direction_and_up(direction, up, roll=0)`** — point the nose along `direction` and roll so the
   vessel's roof aligns with the `up` vector (plus an optional `roll`). This is the way to **hold an
   orientation through a maneuver** — e.g. a gravity turn: pass a fixed `up` (say north) and the roll
   stays defined the whole way up, with no singularity at the vertical. Note the stored **up reference**
   (`up_reference`, default straight up) persists: set it once, then use `target_roll` (Part 2) to
   command rolls against it while changing direction freely.

Include the **roll sign convention** here: *positive roll rolls the vessel to the right (right wing
down) — i.e. clockwise when viewed from behind, looking along the nose* — matching standard aircraft
bank. So `set_direction_and_up(horizon_dir, up, +30)` banks 30° right of wings-level.

A short worked example: hold a fixed orientation from launch through the gravity turn using
`set_direction_and_up` with a constant `up`, contrasted with the old `target_roll` approach that breaks
at the vertical.

### Part 2 — the other (convenience) ways, with singularity warnings

* **`target_pitch` / `target_heading` / `target_pitch_and_heading`** — aim the nose by angle. Ergonomic,
  but add a `.. warning::` that **heading is ill-defined when the nose is near vertical** (pitch → ±90°),
  so prefer `target_direction` / `set_direction_and_up` near the vertical.
* **`target_roll`** — roll angle measured **relative to the up reference** (Part 1), not the old vertical
  plane. Well-defined unless the up reference is parallel to the nose. `NaN` (unset) holds roll.

### Part 3 — reading the state back

* **Attitude/target readouts:** `rotation` / `target_rotation` and `direction` / `target_direction` are
  always well-defined — recommend these.
* **Errors:** `error` (total), and the per-axis `pitch_error` / `heading_error` / `roll_error` (all
  singularity-free, from the attitude-error decomposition). These are the robust way to see "how far
  off am I", including in roll near vertical.
* **Demoted scalar readouts** (`target_pitch/heading/roll`, and `Flight.pitch/heading/roll`): mention
  with the same near-vertical `.. warning::`, pointing at `rotation` / the error readouts instead.

The existing "Tuning the AutoPilot", "Flexible craft", "Smoothing target changes" and "How it works"
subsections are unaffected.

## Implementation notes

The controller already stores its target as a `QuaternionD targetRotation` plus a `bool
rollControlled` (`AttitudeController.cs:36`), with `SetTarget` (PHR), `SetTargetDirection`
(roll-free) and `SetTargetRotation` (full). Add one field — `Vector3d upReference` (default the
frame's up / zenith) — and the setters map straight onto it:

```
// Persistent roll reference; only SetTargetDirectionAndUp writes it.
Vector3d upReference = <frame zenith>;

public void SetTargetRotation (QuaternionD rotation)          // backs TargetRotation (set); upReference untouched
{ targetRotation = rotation; rollControlled = true; BeginSlew (); }

// Build the target from (direction, up, roll) — the shared primitive.
QuaternionD RotationFromDirectionUpRoll (Vector3d direction, Vector3d up, double roll)
{
    direction = direction.normalized;
    var roof = up - Vector3d.Dot (up, direction) * direction;               // up ⊥ nose
    var q0 = GeometryExtensions.FromToRotation (Vector3d.up, direction);     // nose→dir (arbitrary roll)
    if (roof.magnitude < 1e-6) return q0;                                    // up ∥ dir → no roll anchor
    var roof0 = q0 * new Vector3d (0, 0, -1);                                // dorsal axis at that roll
    var align = SignedAngle (roof0, roof.normalized, direction);            // roll to bring roof0→roof
    return QuaternionAboutAxis (direction, align + roll) * q0;
}

public void SetTargetDirectionAndUp (Vector3d direction, Vector3d up, double roll)
{
    upReference = up;                                                        // <-- the only writer
    targetRotation = RotationFromDirectionUpRoll (direction, up, roll);
    rollControlled = true;
    BeginSlew ();
}
```

`TargetRoll` then reads/writes roll relative to `upReference`, keeping the current nose direction:

```
public double TargetRoll {
    get { return rollControlled ? RollRelativeTo (targetRotation, upReference) : double.NaN; }
    set {
        if (double.IsNaN (value)) { rollControlled = false; BeginSlew (); return; }
        targetRotation = RotationFromDirectionUpRoll (TargetDirection, upReference, value);
        rollControlled = true; BeginSlew ();
    }
}
```

`FromToRotation` (`GeometryExtensions.cs:311`) and the residual/angle-axis helpers already exist;
`SignedAngle`, a small axis-angle constructor, and `RollRelativeTo` (the residual-nose projection,
mirroring `RollErrorTo`) are the only new geometry. `TargetPitch/Heading` (set) route through
`RotationFromDirectionUpRoll (newDirection, upReference, currentRoll)` so a pitch/heading change
preserves roll relative to the reference. Everything downstream (slew, roll blend weight,
`RollErrorTo`, soft-start) already operates on `targetRotation`, so **no control-loop changes are
needed.** The unified `AttitudeError` reuses the residual decomposition written for `RollErrorTo`.

## Verification

- Unit: `SetDirectionAndUp(dir, zenith, 0)` ≡ `QuaternionFromPitchHeadingRoll(pitch, heading, 0)`
  (continuity, so `TargetRoll` with the default reference matches today away from vertical); the
  `roll` offset composes (`…, r)` ≡ `…, 0)` rolled by `r`); `up ∥ direction` suppresses roll rather
  than producing NaN; `AttitudeError` matches `Error` on pure single-axis offsets.
- Unit: after `SetDirectionAndUp(dir, north, r)`, reading `TargetRoll` returns `r`; changing pitch
  keeps `TargetRoll == r`; `TargetRotation`/`TargetDirection` leave `UpReference` unchanged.
- Integration (`service/SpaceCenter/test/test_autopilot.py`, in-game): a scripted gravity turn with a
  fixed `up` holds a constant physical orientation with bounded roll error through vertical — the #564
  scenario that is impossible today. Extend the near-vertical roll tests added in #564.

## Open questions

None outstanding.

Resolved: `UpReference` is a get/set property (settable directly; set re-anchors roll without moving
the target). No `Flight.RollRelativeTo` RPC — the persistent up reference covers it. The method-setter
/ `Target*`-readout naming asymmetry is fine (left as-is). `TargetDirection` (set) is retained as the
roll-hold (suppressed) primary knob. `TargetRoll` is kept and reinterpreted relative to the up
reference (not removed).

## Implementation plan (implemented in [PR #882](https://github.com/krpc/krpc/pull/882))

Three separate commits, in order. All implemented; the C# service DLL, the `ServiceDefinitions`
generation, the ruff/pyright gates on the test file, the doc-coverage gates and the full doc HTML
build all pass headlessly. **In-game integration-test run + merge still pending** (the `test_autopilot.py`
additions need the running game).

### Commit 1 — C# service changes (`service/SpaceCenter`) ✅

All the mod-DLL source changes; regenerates the client stubs.

- [x] `SetDirectionAndUp(direction, up, roll=0)` — the one new primary setter — plus the persistent
      `upReference` field and its get/set `UpReference` property (set just writes the field; the
      current target is not moved). (`TargetRotation` / `TargetDirection` already exist as get/set
      properties and are kept.) New geometry: `GeometryExtensions.AngleAxis` / `SignedAngle` back the
      shared `RotationFromDirectionUpRoll` primitive and its inverse `RollRelativeTo`. Roll sign is
      `align − roll` about the nose (positive banks right); validated for internal consistency
      (roundtrip, composition, up∥dir suppression) with a numpy quaternion harness.
- [x] Reinterpret `TargetRoll` (get/set) and `CurrentTargetRoll` (`EffectiveTargetRoll`) relative to
      `upReference`; route `TargetPitch/Heading` (set) through the shared primitive (`AimNose`) so they
      preserve roll. `upReference` defaults to `(1,0,0)` (the frame's up / zenith), reset in `Reset`.
- [x] Unified singularity-free `AttitudeError` / `CurrentAttitudeError` → (pitch, yaw, roll) from
      `AttitudeErrorTo` (**body-frame** pitch/yaw — body x = pitch axis, z = yaw axis — + nose-residual
      roll); `PitchError` / `HeadingError` are now magnitudes of its components (a breaking change from
      the Euler subtraction); `RollError` unchanged. (In-game testing corrected this from an initial
      roll-invariant-frame decomposition, whose axes carry the pointing rotation's twist and so
      mis-routed a pitch offset onto the yaw component.)
- [x] Demote the scalar Euler surface in the API-reference docstrings: near-vertical `<remarks>`
      warnings on `TargetPitch/Heading`, `TargetPitchAndHeading`, the scalar target readouts, and
      `Flight.Pitch/Heading/Roll`, steering to the primary knobs / error readouts.

### Commit 2 — integration tests ✅

- [x] Extend `service/SpaceCenter/test/test_autopilot.py`: the three primary setters; `up_reference`
      default/persistence and direct set; `target_roll` relative to the reference (preserved across
      pitch/heading changes); `up ∥ direction` fallback; roll defined through the exact vertical
      (target-space, plus a physics companion holding through vertical with bounded roll error); the
      continuity check (`set_direction_and_up(dir, zenith, r)` ≡ the Euler-built target) and the
      roll-sign convention; unified per-axis `attitude_error`.
- [x] `test_flight.py` roll telemetry unaffected (`Flight.Roll` semantics unchanged; only docstrings
      demoted), so no test change was needed there.

### Commit 3 — tutorial ✅

- [x] Rewrite the "Using the AutoPilot" opening of `doc/src/tutorials/autopilot.rst` (three primary
      setters, the convenience ways with singularity warnings, readouts, roll sign convention) — see
      the tutorial-update section above. New members added to `doc/order.txt`.

Ships in PR #882; no separate issue. (The `CHANGES.txt` entry, per repo convention, goes in the
dedicated final pre-merge commit — not one of the three above.)
