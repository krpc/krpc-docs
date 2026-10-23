# Release plan

The authoritative list of planned work per release, with pointers to design docs. GitHub issues on
[`krpc/krpc`](https://github.com/krpc/krpc) are updated to match this file, and track work status.

✅ done · 🚧 in progress or partly done · ⬜ not started

The **GitHub** column says how the issue on GitHub stands against this plan:

* `#N`: filed, with the milestone and labels given here.
* `#N`, then a **bold action**: filed, but GitHub needs that change.
* **To file**: not on GitHub yet. The link is the draft in [issues/](issues/), see
  [Filing a draft](#filing-a-draft).
* **To draft**: not on GitHub, and no draft yet.

| | Release | Theme | Progress |
| --- | --- | --- | --- |
| 🚧 | 0.7 | Server-side functions, streams and events, protocol additions, service improvements | Protocol version to add, then tag |
| ⬜ | 0.8 | Single connection, then client conformance testing and thread safety | 0 of 6 started |
| ⬜ | 1.0 | Remaining protocol improvements (#906), server side function follow-ups | 0 of 9 done; tick control has a 0.7 stopgap |

## 0.7: server-side functions, streams and events, service improvements

Everything merged since v0.6.0 (PRs #1015 to #1157, milestone 0.7.0), plus the protocol version,
which is left to do before the tag. **Close the milestone on GitHub once 0.7.0 is tagged.**

### Protocol and server

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ⬜ | Protocol version 1 in the handshake, with version 0 served as 1 | **To file**: [protocol-version.md](issues/protocol-version.md); labels enhancement, protocol, server, client | [protocol/protocol-version.md](design/protocol/protocol-version.md) |
| ✅ | Server-side functions | #1124 to #1130 | [server-side-functions/server-side-functions.md](design/server-side-functions/server-side-functions.md) |
| ✅ | Stream and event improvements: refcounting, invalidation | #1122, #1108, #1109 | [protocol/stream-and-event-improvements.md](design/protocol/stream-and-event-improvements.md), superseding [protocol/stream-refcounting.md](design/protocol/stream-refcounting.md) and [protocol/stream-invalidation.md](design/protocol/stream-invalidation.md) |
| ✅ | Stream freezing removed | #1118 | [protocol/stream-freezing-removal.md](design/protocol/stream-freezing-removal.md) |
| ✅ | Extension members | #1077 | [protocol/extension-members.md](design/protocol/extension-members.md) |
| ✅ | Structure types | #1066, #1067 | [protocol/struct-types.md](design/protocol/struct-types.md) |
| ✅ | Nullable values, incl. inside structures and collections | #1017, #1091 | [protocol/nullable-values.md](design/protocol/nullable-values.md), [protocol/nested-nullable-values.md](design/protocol/nested-nullable-values.md) |
| ✅ | Object lifetime and removal | #1051, #1072, #1120 | [object-lifetime.md](design/object-lifetime.md) |
| ✅ | Physics tick synchronization (tick hold, stopgap for #251), auto-pilot update timing | #1070 | [server/tick-hold.md](design/server/tick-hold.md), [autopilot/update-timing.md](design/autopilot/update-timing.md) |
| ✅ | Local socket transport | #1065 | [protocol/local-transports.md](design/protocol/local-transports.md) |
| ✅ | Definition ordering | #1044 | [protocol/definition-ordering.md](design/protocol/definition-ordering.md) |
| ✅ | RPCs deprecated in 0.6.0 removed | #1140 | — |
| ✅ | Game state and scene handling (no game loaded, scene checks, scene loads) | #1041, #1119, #1121, #1131 | — |
| ✅ | Client optimization, benchmark suite | #1056, #1052 | [build-tools/benchmarks.md](design/build-tools/benchmarks.md) |
| ✅ | Cnano client TCP/IP | #1055 | — |
| ✅ | Lua 5.1 to 5.4, lua-protobuf, `socket.unix` on Windows | #1142 | [build-tools/lua-5.4-and-lua-protobuf.md](design/build-tools/lua-5.4-and-lua-protobuf.md), [build-tools/lua-socket-unix-on-windows.md](design/build-tools/lua-socket-unix-on-windows.md) |

### Services

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Debug service, force RPCs | #1033, #1146 | [services/debug-service.md](design/services/debug-service.md) |
| ✅ | Editor scene API, matched to `Vessel` and `Flight` | #1038, #1059, #1064, #1153 | [services/editor-scene-api.md](design/services/editor-scene-api.md), [services/editor-vessel-center-of-mass.md](design/services/editor-vessel-center-of-mass.md) |
| ✅ | Value classes and tuples returned as structures | #1132, #1148 | [services/struct-adoption-audit.md](design/services/struct-adoption-audit.md) |
| ✅ | UI: code-built controls, layout and widgets | #1040 | [services/ui-controls-and-layout.md](design/services/ui-controls-and-layout.md), [services/ui-widget-gap-audit.md](design/services/ui-widget-gap-audit.md) |
| ✅ | Drawing: map view, editor, tracking station, primitives, navball markers | #1115, #1116, #1037 | — |
| ✅ | Orbits from state vectors, expanded orbit API | #1046, #1087 | [services/orbits-from-state-vectors.md](design/services/orbits-from-state-vectors.md), [services/orbit-position-and-velocity.md](design/services/orbit-position-and-velocity.md) |
| ✅ | Buoyancy | #1103 | [services/buoyancy.md](design/services/buoyancy.md) |
| ✅ | Precision mode, RCS force and torque | #1082, #1080 | — |
| ✅ | Time warp in the space center and tracking station | #1145 | — |
| ✅ | Name tags from KSPCommunityPartModules or kOS (#829) | #1155 | [services/kos-nametag-shared-module.md](design/services/kos-nametag-shared-module.md) |
| ✅ | Infernal Robotics servo deduplication | #1154 | — |
| ✅ | RealFuels support | #1039 | — |
| ✅ | Plus many smaller SpaceCenter additions and fixes | — | — |

### Build and tools

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Windows build and test in CI | #1058, #1060 | — |
| ✅ | KSP version compatibility code removed | #1048 | — |
| ✅ | Package metadata and release process cleanup | #1015 | — |
| ✅ | Culture analyzers | #1133 | [build-tools/culture-analyzers.md](design/build-tools/culture-analyzers.md) |
| ✅ | ruff and pyright replace pylint, black and mypy | #1134, #1135 | — |
| ✅ | Build tools and dependencies updated | #1139 | — |
| ✅ | Doc examples checked, client API docs match the stubs, link checker | #1141, #1151, #1156 | — |
| ✅ | Generated client files named after their service, C/C++ header includes | #1149, #1150 | — |
| ✅ | In-game test waits, buildifier as a test | #1147, #1152 | — |
| ✅ | Changelogs grouped by topic | #1157 | — |

## 0.8: single connection, then client conformance and thread safety

### Features

| | Feature | GitHub | Labels | Design doc |
| --- | --- | --- | --- | --- |
| ⬜ | Single connection: RPC and stream connections merged | **To file**: [single-connection.md](issues/single-connection.md) | enhancement, protocol, server, client | [protocol/single-connection.md](design/protocol/single-connection.md) |
| ⬜ | Protocol version 2, with the single connection | Part of the single connection issue | — | [protocol/protocol-version.md](design/protocol/protocol-version.md) |
| ⬜ | Request ids (phase 1), on the single connection branch | **To file**: [request-ids.md](issues/request-ids.md) | enhancement, protocol, server, client | [protocol/request-ids.md](design/protocol/request-ids.md) |
| ⬜ | Client conformance tests and runtime specification | [#1123](https://github.com/krpc/krpc/issues/1123), **move from 1.0.0**, **post the [comment](#comment-on-1123)** | enhancement, client | [client-conformance/](design/client-conformance/README.md) |
| ⬜ | Client thread safety: define and document what is thread-safe | [#427](https://github.com/krpc/krpc/issues/427) | docs | — |

* **Single connection first.** It changes connection setup and threading in every client, so the
  conformance suite is written against it rather than rewritten after it.
* **The protocol version goes to 2 with it.** A 0.7 client and a 0.8 server then fail at the
  handshake with a clear error, in either direction.
* **Request ids go with it, on the same branch.** The single connection's client reader matches
  responses by id, so phase 1 of request ids is part of it. Pipelining and out-of-order completion
  are later additions.
* **Thread safety goes with conformance.** The single connection changes client threading, and
  the conformance suite's threading tests are where the guarantees get pinned and checked across
  clients.
* **A hard break.** The 0.8 server speaks only the single connection, with no transition period.
  Clients older than 0.8 cannot connect to it.

### Fixes and smaller items

Everything but the `RemoveStream` change and the Ctrl-C fix can ship in a 0.7.x release if 0.8 is far off. The
`RemoveStream` change breaks the `KRPC` service, and the Ctrl-C fix depends on the single connection.

| | Item | GitHub | Labels | Design doc |
| --- | --- | --- | --- | --- |
| ⬜ | `RemoveStream` and `SetStreamRate` take a `Stream` | **To file**: [remove-stream-takes-stream.md](issues/remove-stream-takes-stream.md) | enhancement, protocol, server | — |
| ⬜ | `KerbalAlarmClock.Alarm.PlaySound` has no effect | **To file**: [kac-alarm-play-sound.md](issues/kac-alarm-play-sound.md) | bug, service:kerbal-alarm-clock | [services/kac-remotetech-tests-and-api.md](design/services/kac-remotetech-tests-and-api.md) |
| ⬜ | DockingCamera log spam, LIDAR docstrings | **To file**: [dockingcam-lidar-cleanups.md](issues/dockingcam-lidar-cleanups.md) | bug, service | [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| ⬜ | Raise the default receive timeout | **To file**: [recv-timeout-default.md](issues/recv-timeout-default.md) | enhancement, server | [server/recv-timeout-cliff.md](design/server/recv-timeout-cliff.md) |
| ⬜ | Python: Ctrl-C during a call on Windows, with the single connection | **To file**: [python-ctrl-c-windows.md](issues/python-ctrl-c-windows.md) | bug, client:python | [protocol/single-connection.md](design/protocol/single-connection.md) |
| ⬜ | Python: trim client frames from server error tracebacks | **To file**: [python-traceback-trim.md](issues/python-traceback-trim.md) | enhancement, client:python | — |

## 1.0: remaining protocol improvements, server side function follow-ups

The rest of meta-issue #906 ([protocol/improvements.md](design/protocol/improvements.md)), built on
the 0.8 single connection and covered by the conformance suite as it lands. Each item is an
addition on protocol version 2, so 0.8 clients keep working: see
[protocol-compatibility.md](design/protocol-compatibility.md).

| | Feature | GitHub | Labels | Design doc |
| --- | --- | --- | --- | --- |
| ⬜ | Protocol improvements (meta issue) | [#906](https://github.com/krpc/krpc/issues/906) | enhancement, protocol | [protocol/improvements.md](design/protocol/improvements.md) |
| 🚧 | Batching and transactions, fire-and-forget, client to server streams | [#903](https://github.com/krpc/krpc/issues/903), **add milestone** | enhancement, protocol | [protocol/reverse-streams.md](design/protocol/reverse-streams.md); `KRPC.RunFunction` (#1124) already runs a batch in one tick |
| 🚧 | Tick control: one RPC or batch per physics update, replacing the tick hold stopgap | [#251](https://github.com/krpc/krpc/issues/251), **add milestone** | enhancement, server:api | [server/tick-hold.md](design/server/tick-hold.md) is the stopgap; protocol design open |

### Server side function follow-ups

Follow-ups to server side functions, which merged in 0.7 (#1124 to #1130).

| | Feature | GitHub | Labels | Design doc |
| --- | --- | --- | --- | --- |
| ⬜ | Function release: a client releases the functions it no longer needs | [#1107](https://github.com/krpc/krpc/issues/1107), closed as premature, **reopen**, **add milestone** | enhancement, server:api | [server-side-functions/function-release.md](design/server-side-functions/function-release.md) |
| ⬜ | Shared nodes compiled once, removing the `MaxNodes` bound | **To draft** | enhancement, server:api | [server-side-functions/shared-nodes.md](design/server-side-functions/shared-nodes.md) |
| ⬜ | Batched tree construction, gated on measuring real tree sizes | **To draft** | enhancement, client | [server-side-functions/batched-tree-construction.md](design/server-side-functions/batched-tree-construction.md) |
| ⬜ | C# functions with statements | **To draft** | enhancement, client:csharp | [server-side-functions/csharp-statement-functions.md](design/server-side-functions/csharp-statement-functions.md) |
| ⬜ | Yielding procedures: deferred calls and resumable functions | **To draft** | enhancement, server:api | [server-side-functions/yielding-procedures.md](design/server-side-functions/yielding-procedures.md) |
| ⬜ | Arbitrary expressions: opt-in calls to arbitrary CLR members | **To draft** | enhancement, server:api | [server-side-functions/server-side-arbitrary-expressions.md](design/server-side-functions/server-side-arbitrary-expressions.md) |

## Not scheduled

### Features

| | Feature | GitHub | Labels | Design doc |
| --- | --- | --- | --- | --- |
| ⬜ | Per-client receive patience | **To file**: [recv-patience.md](issues/recv-patience.md) | enhancement, server | [server/recv-timeout-cliff.md](design/server/recv-timeout-cliff.md) |
| 🚧 | RemoteTech API bindings and KAC alarm actions | **To file**: [remotetech-kac-api.md](issues/remotetech-kac-api.md) | enhancement, service:remote-tech, service:kerbal-alarm-clock | [services/kac-remotetech-tests-and-api.md](design/services/kac-remotetech-tests-and-api.md) |
| ⬜ | InfernalRobotics input linking and sun tracking | **To file**: [infernal-robotics-input-linking.md](issues/infernal-robotics-input-linking.md) | enhancement, service:infernal-robotics | [services/infernal-robotics-input-linking.md](design/services/infernal-robotics-input-linking.md) |
| ⬜ | Autopilot with large planes | [#526](https://github.com/krpc/krpc/issues/526), **decide**: on 1.0.0, maybe deferred to a MechJeb integration | bug, service:space-center | [autopilot/aero-extension.md](design/autopilot/aero-extension.md) |
| ⬜ | Autopilot extensions: bank-to-turn, heterogeneous actuators, output filter knobs, sign convention refactor | — | — | [autopilot/bank-to-turn.md](design/autopilot/bank-to-turn.md), [autopilot/heterogeneous-actuators.md](design/autopilot/heterogeneous-actuators.md), [autopilot/output-filter-manual-knobs.md](design/autopilot/output-filter-manual-knobs.md), [autopilot/sign-convention-refactor.md](design/autopilot/sign-convention-refactor.md) |
| ⬜ | Trajectories service | — | — | [services/trajectories-service.md](design/services/trajectories-service.md) |
| ⬜ | Nullable set elements and dictionary keys, parked and likely dropped | — | — | [protocol/nullable-keys-and-set-elements.md](design/protocol/nullable-keys-and-set-elements.md) |
| ⬜ | Python: an asyncio client, after the single connection | **To file**: [python-asyncio-client.md](issues/python-asyncio-client.md) | enhancement, client:python | [protocol/request-ids.md](design/protocol/request-ids.md) |
| ⬜ | Streams and events over serial IO, after the single connection; needs flow control | **To file**: [serialio-streams.md](issues/serialio-streams.md) | enhancement, protocol, server, client:cnano | [protocol/single-connection.md](design/protocol/single-connection.md) |
| 🚧 | More communication protocols; local sockets landed in 0.7, nothing further planned | [#899](https://github.com/krpc/krpc/issues/899) | enhancement, protocol | [protocol/local-transports.md](design/protocol/local-transports.md) |
| ⬜ | Inheritance for remote objects; a nicety, clients translate their OOP to procedures | [#905](https://github.com/krpc/krpc/issues/905) | enhancement, protocol | — |
| ⬜ | Constructor calls; would add a new refcounted object kind | [#898](https://github.com/krpc/krpc/issues/898) | enhancement, protocol | — |
| ⬜ | SSL encryption and authentication; likely out of scope, use a proxy or tunnel | [#11](https://github.com/krpc/krpc/issues/11) | enhancement, protocol | — |
| 🚧 | Principia support; phase 1 shipped as a docs page, phases 2 and 3 wait on upstream | [#767](https://github.com/krpc/krpc/issues/767) | enhancement, service:space-center | [services/principia-service.md](design/services/principia-service.md) |
| ⬜ | MechJeb2 and Kerbal Engineer Redux services | [#288](https://github.com/krpc/krpc/issues/288) | enhancement | — |
| ⬜ | Raster Prop Monitor integration and camera views | [#375](https://github.com/krpc/krpc/issues/375), [#424](https://github.com/krpc/krpc/issues/424) | mod-compatibility; enhancement | — |
| ⬜ | DockingCamera and LaserDist integration; needs forks | [#674](https://github.com/krpc/krpc/issues/674) | enhancement | [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| ⬜ | Vessel state and staging prediction; parts may be covered by the stage API | [#311](https://github.com/krpc/krpc/issues/311) | enhancement, service:space-center | — |
| 🚧 | Docs restructure, any release | [#1050](https://github.com/krpc/krpc/issues/1050) | docs | — |

### Fixes, tests and tooling

| | Item | GitHub | Labels | Design doc |
| --- | --- | --- | --- | --- |
| ⬜ | Windows CI: C++ local socket test hangs, any release | [#1078](https://github.com/krpc/krpc/issues/1078) | bug, client:cpp | — |
| ⬜ | Windows CI: Python stream test flake, any release | [#1138](https://github.com/krpc/krpc/issues/1138) | bug, client:python | — |
| 🚧 | Autopilot test-plan gaps | **To file**: [autopilot-test-gaps.md](issues/autopilot-test-gaps.md) | tools, service:space-center | [autopilot/test-plan.md](design/autopilot/test-plan.md) |
| 🚧 | Mod compatibility tests | **To file**: [mod-compat-tests.md](issues/mod-compat-tests.md) | tools, mod-compatibility | [services/mod-compat-test-coverage.md](design/services/mod-compat-test-coverage.md), [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| ⬜ | XML doc crefs to exceptions | **To file**: [doc-crefs-to-exceptions.md](issues/doc-crefs-to-exceptions.md) | enhancement, tools, docs | [build-tools/doc-crefs-to-exceptions.md](design/build-tools/doc-crefs-to-exceptions.md) |
| ⬜ | NUnit 5 | **To file**: [nunit-5-migration.md](issues/nunit-5-migration.md) | enhancement, tools | [build-tools/nunit-5-migration.md](design/build-tools/nunit-5-migration.md) |
| ⬜ | Bazel sandbox in CI | **To file**: [buildenv-linux-sandbox.md](issues/buildenv-linux-sandbox.md) | enhancement, build-scripts | — |
| ⬜ | Lua API docs on sphinx-lua-ls, when luadomain breaks on a Sphinx bump | **To file**: [lua-sphinx-domain.md](issues/lua-sphinx-domain.md) | docs, tools, client:lua | — |
| ⬜ | luasocket release pin, blocked upstream | **To file**: [luasocket-release-pin.md](issues/luasocket-release-pin.md) | tools, client:lua, dependencies | [build-tools/lua-socket-unix-on-windows.md](design/build-tools/lua-socket-unix-on-windows.md) |

### Negative results

| Feature | Design doc |
| --- | --- |
| Service versioning | [services/service-versioning.md](design/services/service-versioning.md) |
| CI lite and merge queue | [build-tools/ci-lite-merge-queue.md](design/build-tools/ci-lite-merge-queue.md) |
| CI remote cache | [build-tools/ci-remote-cache.md](design/build-tools/ci-remote-cache.md) |

## Updating GitHub

### Filing a draft

Each file in [issues/](issues/) is one issue: the heading is the title, the rest is the body. Take
the milestone and labels from its row above. After filing, replace **To file** with the issue
number, link the number from the design doc that names the draft, and delete the draft.

A placeholder such as `#<single-connection>` names another draft. Replace it with that draft's
issue number when filing.

### Comment on #1123

Decisions for the conformance work, left open by the client audits:

```markdown
Client decisions to settle as part of this work:

* Whether the Lua client gets streams.
* C++: dropping a `Stream` handle never removes the server stream (parity audit bug 11). Rule it intended under the explicit removal model of #1122, or fix it.
* `TestService`: rename `EnumDefaultArg` and `AddMultipleValues`, and add `UInt32ToString`, `HexStringToBytes` and `StaticOptionalArguments`.
* The open Python client bugs from the parity audit's Python sweep.

Background: [client-conformance/defects.md](https://github.com/krpc/krpc-docs/blob/main/design/client-conformance/defects.md), [client-conformance/test-service.md](https://github.com/krpc/krpc-docs/blob/main/design/client-conformance/test-service.md)
```
