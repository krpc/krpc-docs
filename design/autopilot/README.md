# AutoPilot design docs

Design record for kRPC's attitude-control autopilot (`service/SpaceCenter/src/AutoPilot/`,
exposed through `service/SpaceCenter/src/Services/AutoPilot.cs`). The controller was rebuilt in
[PR #882 "Rework the Autopilot"](https://github.com/krpc/krpc/pull/882); the docs below are the
historical design record of that rework, plus proposals for extensions not yet built.

These are design records, not current-behavior documentation — the kRPC docs and PR history are the
source of truth for the code as it stands.

## The shipped controller, by layer

The controller is a cascade: an orientation command becomes a target attitude, the outer loop turns
attitude error into a target angular velocity, the inner loop turns that into torque, and the
oscillation layer damps structural modes the inner loop would otherwise excite.

| Layer | Doc | What it covers |
| --- | --- | --- |
| Orientation API | [orientation-api.md](orientation-api.md) | The pitch / heading / roll orientation API and reference-frame handling — what a script commands. |
| Outer loop | [outer-loop.md](outer-loop.md) | The 2D pitch/yaw pointing law and the PI-lag speed cone that shapes the target-velocity profile. |
| Inner loop | [inner-loop.md](inner-loop.md) | PID plus analytic acceleration feedforward, and the restructured mitigation gating — includes the pre-rework design critique. |
| Oscillation mitigation | [oscillation.md](oscillation.md) | Notch / low-pass structural-mode suppression, its in-game calibration, MechJeb comparison and detection limits, the superseded flexible-craft latch fix, and one negative result (adaptive TimeToPeak). |
| Special maneuvers | [antipodal-flip.md](antipodal-flip.md) | Deterministic 180° flip handling and the out-of-plane-instability fix. |
| Testing | [test-plan.md](test-plan.md) | The KSP-in-the-loop test craft matrix, metrics, and corner-case catalog. *(In progress.)* |

## Proposed extensions (not built)

Each is an independently-buildable future change, kept as its own doc.

| Doc | Status | What it proposes |
| --- | --- | --- |
| [aero-extension.md](aero-extension.md) | proposal | Extending the controller to aerodynamic flight. |
| [bank-to-turn.md](bank-to-turn.md) | proposal | Bank-to-turn control for asymmetric-authority craft. |
| [heterogeneous-actuators.md](heterogeneous-actuators.md) | proposal | Fast/slow actuator allocation across mixed effectors. |
| [sign-convention-refactor.md](sign-convention-refactor.md) | proposal | Move the inner loop to a right-handed sign convention. |
| [output-filter-manual-knobs.md](output-filter-manual-knobs.md) | proposal | Expose oscillation-mitigation internals as manual knobs. |
