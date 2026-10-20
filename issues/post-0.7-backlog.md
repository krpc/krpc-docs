# Backlog after 0.7.0

**Status:** summary, not an issue. Untracked work found in the `design/` docs, for after the 0.7.0
release. Each row becomes its own GitHub issue when it is picked up. The items with their own
draft are in [README.md](README.md).

| # | Item | Size | Fits with | Source |
| --- | --- | --- | --- | --- |
| 1 | `KRPC.RemoveStream` and `SetStreamRate` take a `Stream` in place of an id | S, breaking | 0.8, or drop | [todo-fixme-sweep.md](../design/todo-fixme-sweep.md) §1 |
| 2 | Trim client-internal frames from server error tracebacks in Python | S | 0.8 | [todo-fixme-sweep.md](../design/todo-fixme-sweep.md) |
| 3 | Client decisions left to the conformance suite | M | 0.8, [#1123](https://github.com/krpc/krpc/issues/1123) | [client-api-parity-audit.md](../design/client-api-parity-audit.md), [client-testing.md](../design/client-testing.md) |
| 4 | Per-client receive patience | M | 0.8 or 1.0 | [recv-timeout-cliff.md](../design/server/recv-timeout-cliff.md) |
| 5 | Server side function follow-ups | M to L each | Not scheduled | [server-side-functions/](../design/server-side-functions/) |
| 6 | RemoteTech API bindings and the KAC alarm-action model | M | Any | [kac-remotetech-tests-and-api.md](../design/services/kac-remotetech-tests-and-api.md) |
| 7 | InfernalRobotics input linking | M | Any | [infernal-robotics-input-linking.md](infernal-robotics-input-linking.md) |
| 8 | Trajectories service | L | Any | [trajectories-service.md](../design/services/trajectories-service.md) |
| 9 | Mod compatibility tests | M | Any | [mod-compat-test-coverage.md](../design/services/mod-compat-test-coverage.md), [dockingcam-lidar-tests.md](../design/services/dockingcam-lidar-tests.md) |
| 10 | Autopilot extensions and fixes | L | With [#526](https://github.com/krpc/krpc/issues/526) | [autopilot/](../design/autopilot/README.md) |
| 11 | Autopilot test-plan gaps | M | With 10 | [autopilot/test-plan.md](../design/autopilot/test-plan.md) |
| 12 | CI lite and merge queue | M | Any | [ci-lite-merge-queue.md](../design/build-tools/ci-lite-merge-queue.md) |

## 1. `RemoveStream` takes a `Stream`

`KRPC.AddStream` returns a `Stream` message, which holds only the id. `KRPC.RemoveStream (ulong id)`
and `KRPC.SetStreamRate (ulong id, float rate)` take the bare id. A `FIXME` on `RemoveStream` in
`core/src/Service/KRPC/KRPC.cs` asks for the parameter to be a `Stream`. The TODO/FIXME sweep
deferred it to the #906 protocol work, because it is breaking.

The wire encoding changes from a varint to an embedded `Stream` message. That breaks:

* Every bundled client, both where it calls `RemoveStream` and where it decodes a `RemoveStream`
  argument to track removals (`Client::note_removed_streams` in C++, the `note_removed` path in
  Python's `client.py`).
* Every third-party client.

Users do not see the change. Each client wraps the call as `stream.remove ()`. The gain is a
consistent schema: a stream goes out as a `Stream` and comes back as one.

**Recommendation:** do it in 0.8, for `SetStreamRate` as well, since the single connection
already changes every client's connection layer. Otherwise, delete the `FIXME` and close the item.
Breaking every client for a typed parameter alone is not worth it.

## 2. Python error tracebacks

A server error raised in Python shows the client's own frames before the user's code. The `TODO`
is in `client/python/krpc/client.py`. The fix is on the local branch `python-traceback-trim`, one
commit from July 2026, which has not been rebased since.

## 3. Client decisions for the conformance suite

* Whether the Lua client gets streams.
* C++: a dropped `Stream` handle never removes the server stream (parity audit bug 11). Rule it
  intended under the explicit removal model of [PR #1122](https://github.com/krpc/krpc/pull/1122),
  or fix it.
* `TestService`: rename `EnumDefaultArg` and `AddMultipleValues`, and add `UInt32ToString`,
  `HexStringToBytes` and `StaticOptionalArguments`.
* The Python sweep bugs from the parity audit.

## 4. Per-client receive patience

A `KRPC` procedure that sets how long the server waits for this client's next call. A client that
does 2 ms of work per call can ask to be waited for. Other clients pay nothing. `CallContext`
identifies the caller, so this needs no protocol change. Batching, the other fix for the same
problem, is [#903](https://github.com/krpc/krpc/issues/903) in the 1.0 plan.

## 5. Server side function follow-ups

The release plan lists these as one line. Each one is its own issue:

* **Function release:** a client releases the expressions it built. Today they stay until the
  server stops. Probably the first to file.
* **Shared nodes:** compile a shared node once, and lift the `MaxNodes` bound.
* **Batched tree construction:** client side only. Measure real tree sizes first.
* **C# statement functions:** a sketch.
* **Yielding procedures:** deferred calls and resumable functions.
* **Arbitrary expressions:** call arbitrary CLR members.

## 6. RemoteTech and KAC

* RemoteTech: bind the API methods the service leaves unbound, about 17: `ControlPath`,
  `HasDirectGroundStation`, `RadioBlackout`, `PowerDown`, ground station management and `Enabled`.
* KAC: the phase 3 alarm-action model, with `WarpAction`, `MessageAction` and `DeleteWhenDone`.
  Its binding is the same as the `PlaySound` fix in [kac-alarm-play-sound.md](kac-alarm-play-sound.md).

## 7. InfernalRobotics input linking

About 18 servo members for control axis linking and sun tracking. The draft is
[infernal-robotics-input-linking.md](infernal-robotics-input-linking.md).

## 8. Trajectories service

A new service wrapping the Trajectories mod's impact prediction. Nothing is built yet.

## 9. Mod compatibility tests

In-game tests for Procedural Fairings, the Firespitter and WBI thrust reversers, and the stock
TF1/TF2 reversers. Also no-mod tests and `//:test` and `//:lint` wiring for DockingCamera and LiDAR,
which have no `test/` directory.

## 10. Autopilot extensions and fixes

* Proposals: [bank-to-turn](../design/autopilot/bank-to-turn.md),
  [heterogeneous actuators](../design/autopilot/heterogeneous-actuators.md) (phase 1 stands alone;
  phases 2 and 3 need the aero extension), and the
  [output filter knobs](../design/autopilot/output-filter-manual-knobs.md).
* The [sign convention refactor](../design/autopilot/sign-convention-refactor.md).
* The "still open" items in [inner-loop.md](../design/autopilot/inner-loop.md): the controller
  uses only the positive torque authority, target writes from other threads can tear, and the
  anti-windup is partial.

## 11. Autopilot test-plan gaps

In [test-plan.md](../design/autopilot/test-plan.md):

* §11.1: `attenuation_angle`, the `auto_tune=False` response and the radial nudge.
* §11.3: the dynamic roll axis, a moving target, the `decel_lag_correction` A/B and the first
  tick transient.
* §11.5: assert overshoot in `test_set_pitch` and `test_set_heading`.
* §11.6: clearing the integral at PRELAUNCH.
* From [oscillation.md](../design/autopilot/oscillation.md): more RCS on the `AutoPilotChatter`
  craft, and `recover_timeout` for `test_orbital_directions` on the flexible craft.

## 12. CI lite and merge queue

Run a reduced CI on pull requests, and the full suite in a merge queue or behind a `full-ci`
label. Nothing is implemented: `ci.yml` has no `merge_group` trigger or path filters.
