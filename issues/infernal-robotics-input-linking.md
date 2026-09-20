# InfernalRobotics — input-linking / IK / tracking cluster

**Status:** proposal — designed, not implemented (2026-07-16). No GitHub issue yet. Follow-up to
the InfernalRobotics core-API expansion ([PR #985](https://github.com/krpc/krpc/pull/985)), which
surfaced IR-Next's core mechanical/state API and deliberately deferred this cluster.

## Motivation

IR-Next's `IServo` exposes a subsystem for driving servos from vessel control axes and sun-tracking,
separate from the core mechanical API. It is niche and harder to test (needs a servo configured in a
linked/tracking input mode), so it was split out of the initial expansion.

## Scope (all already on IR-Next `IServo`/`IServoGroup`; verify names against
`InfernalRoboticsNext.dll` with `ikdasm`)

- **`InputMode`** — new kRPC enum from IR's `InputModeType {manual=1, control=2, linked=3,
  tracking=4}`; plus `LinkInput()` method.
- **Control-axis linkage** (get/set floats): `PitchControl`, `RollControl`, `YawControl`,
  `ThrottleControl`, `XControl`, `YControl`, `ZControl`, and the matching per-axis speeds
  `PitchSpeed`, `RollSpeed`, `YawSpeed`, `ThrottleSpeed`, `XSpeed`, `YSpeed`, `ZSpeed`, plus
  `BaseSpeed`.
- **Sun tracking:** `TrackSun` (bool), `TrackAngle` (float).
- **Deflection:** `ControlDeflectionRange`, `ControlNeutralPosition`.

~18 members. Same wiring pattern as the core expansion (interface + `IRServo` reflected impl +
`doc/order.txt` + the `InputMode` enum rendered in `servo.tmpl`).

## Notes

- These are servo-level, so they work on non-active vessels automatically (real `IServo`).
- Testing meaningfully needs a craft servo configured with a linked/tracking input mode, or at least
  a round-trip of the settable floats; extend `InfernalRobotics.craft` if strict behavioral coverage
  is wanted (manual VAB edit).
- Follow the structure of the core expansion ([PR #985](https://github.com/krpc/krpc/pull/985)) and
  the `test_parts_robotic.py` test standard.
