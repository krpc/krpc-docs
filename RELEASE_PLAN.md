# Release plan

Planned features per release, with pointers to design docs where they exist. Work status
lives on GitHub ([`krpc/krpc`](https://github.com/krpc/krpc) issues and PRs); this is the
roadmap; the icons give progress at a glance.

✅ done · 🚧 in progress or partly done · ⬜ not started

| | Release | Theme | Progress |
| --- | --- | --- | --- |
| 🚧 | 0.7 | Server-side functions, streams and events, protocol additions, service improvements | All merged, milestone closed; to be tagged |
| ⬜ | 0.8 | Single connection, then client conformance testing and thread safety | 0 of 5 started; issues drafted in [issues/](issues/README.md#080) |
| ⬜ | 1.0 | Remaining protocol improvements (#906) | 0 of 3 done; tick control has a 0.7 stopgap |

## 0.7 — server-side functions, streams and events, service improvements

Everything merged since v0.6.0 (PRs #1015 to #1157, milestone 0.7.0). The main features:

### Protocol and server

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Server-side functions | #1124 to #1130 | [server-side-functions/server-side-functions.md](design/server-side-functions/server-side-functions.md) |
| ✅ | Stream and event improvements: refcounting, invalidation | #1122, #1108, #1109 | [protocol/stream-and-event-improvements.md](design/protocol/stream-and-event-improvements.md) |
| ✅ | Stream freezing removed | #1118 | [protocol/stream-freezing-removal.md](design/protocol/stream-freezing-removal.md) |
| ✅ | Extension members | #1077 | [protocol/extension-members.md](design/protocol/extension-members.md) |
| ✅ | Structure types | #1066, #1067 | [protocol/struct-types.md](design/protocol/struct-types.md) |
| ✅ | Nullable values, incl. inside structures and collections | #1017, #1091 | [protocol/nullable-values.md](design/protocol/nullable-values.md), [protocol/nested-nullable-values.md](design/protocol/nested-nullable-values.md) |
| ✅ | Object lifetime and removal | #1051, #1072, #1120 | [object-lifetime.md](design/object-lifetime.md) |
| ✅ | Physics tick synchronization (tick hold, stopgap for #251) | #1070 | [server/tick-hold.md](design/server/tick-hold.md) |
| ✅ | Local socket transport | #1065 | [protocol/local-transports.md](design/protocol/local-transports.md) |
| ✅ | Definition ordering | #1044 | [protocol/definition-ordering.md](design/protocol/definition-ordering.md) |
| ✅ | RPCs deprecated in 0.6.0 removed | #1140 | — |
| ✅ | Game state and scene handling (no game loaded, scene checks, scene loads) | #1041, #1119, #1121, #1131 | — |
| ✅ | Client optimization, benchmark suite | #1056, #1052 | [build-tools/benchmarks.md](design/build-tools/benchmarks.md) |
| ✅ | Cnano client TCP/IP | #1055 | — |
| ✅ | Lua 5.1 to 5.4, lua-protobuf | #1142 | [build-tools/lua-5.4-and-lua-protobuf.md](design/build-tools/lua-5.4-and-lua-protobuf.md) |

### Services

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Debug service, force RPCs | #1033, #1146 | [services/debug-service.md](design/services/debug-service.md) |
| ✅ | Editor scene API, matched to `Vessel` and `Flight` | #1038, #1059, #1064, #1153 | [services/editor-scene-api.md](design/services/editor-scene-api.md), [services/editor-vessel-center-of-mass.md](design/services/editor-vessel-center-of-mass.md) |
| ✅ | Value classes and tuples returned as structures | #1132, #1148 | [services/struct-adoption-audit.md](design/services/struct-adoption-audit.md) |
| ✅ | UI: code-built controls, layout and widgets | #1040 | [services/ui-controls-and-layout.md](design/services/ui-controls-and-layout.md) |
| ✅ | Drawing: map view, editor, tracking station, primitives, navball markers | #1115, #1116, #1037 | — |
| ✅ | Orbits from state vectors, expanded orbit API | #1046, #1087 | [services/orbits-from-state-vectors.md](design/services/orbits-from-state-vectors.md) |
| ✅ | Buoyancy | #1103 | [services/buoyancy.md](design/services/buoyancy.md) |
| ✅ | Precision mode, RCS force and torque | #1082, #1080 | — |
| ✅ | Time warp in the space center and tracking station | #1145 | — |
| ✅ | Name tags from KSPCommunityPartModules or kOS (#829) | #1155 | [services/kos-nametag-shared-module.md](design/services/kos-nametag-shared-module.md) |
| ✅ | Infernal Robotics servo deduplication | #1154 | — |
| ✅ | RealFuels support | #1039 | — |
| ✅ | Plus many smaller SpaceCenter additions and fixes | — | — |

### Build and tools

| | Feature | PRs |
| --- | --- | --- |
| ✅ | Windows build and test in CI | #1058, #1060 |
| ✅ | KSP version compatibility code removed | #1048 |
| ✅ | Package metadata and release process cleanup | #1015 |
| ✅ | Culture analyzers | #1133 |
| ✅ | ruff and pyright replace pylint, black and mypy | #1134, #1135 |
| ✅ | Build tools and dependencies updated | #1139 |
| ✅ | Doc examples checked, client API docs match the stubs, link checker | #1141, #1151, #1156 |
| ✅ | Generated client files named after their service, C/C++ header includes | #1149, #1150 |
| ✅ | In-game test waits, buildifier as a test | #1147, #1152 |
| ✅ | Changelogs grouped by topic | #1157 |

The 0.7.0 milestone has no open issues.

## 0.8 — single connection, then client conformance and thread safety

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Single connection: RPC and stream servers merged | [drafted](issues/single-connection.md) | [protocol/single-connection.md](design/protocol/single-connection.md) |
| ⬜ | Request ids, with the single connection | [drafted](issues/request-ids.md) | [protocol/request-ids.md](design/protocol/request-ids.md) |
| ⬜ | `RemoveStream` and `SetStreamRate` take a `Stream`, with the single connection | [drafted](issues/remove-stream-takes-stream.md) | — |
| ⬜ | Client conformance tests and runtime specification | [#1123](https://github.com/krpc/krpc/issues/1123) (milestone to move from 1.0.0) | [client-conformance.md](design/client-conformance.md) |
| ⬜ | Client thread safety: define and document what is thread-safe | [#427](https://github.com/krpc/krpc/issues/427) | — |

* **Single connection first.** It changes connection setup and threading in every client, so the
  conformance suite is written against it rather than rewritten after it.
* **Request ids go with it.** Both need the same demultiplexing reader in each client; doing them
  separately writes it twice (see "Sequencing against #906" in
  [client-conformance.md](design/client-conformance.md)). Move to 1.0 if 0.8 needs to shrink.
* **Thread safety goes with conformance.** The single connection changes client threading, and
  the conformance suite's threading tests are where the guarantees get pinned and checked across
  clients.
* **Open question** from [single-connection.md](design/protocol/single-connection.md): whether the
  server speaks both connection formats during the transition, or 0.8 is a hard break.

### Smaller items

Fixes and additions that do not depend on the protocol work. They can ship in a 0.7.x release
if 0.8 is far off.

| | Item | Issue |
| --- | --- | --- |
| ⬜ | `KerbalAlarmClock.Alarm.PlaySound` has no effect | [drafted](issues/kac-alarm-play-sound.md) |
| ⬜ | DockingCamera log spam, LIDAR docstrings | [drafted](issues/dockingcam-lidar-cleanups.md) |
| ⬜ | Raise the default receive timeout | [drafted](issues/recv-timeout-default.md) |
| ⬜ | Python: trim client frames from server error tracebacks | [drafted](issues/python-traceback-trim.md) |

## 1.0 — remaining protocol improvements

The rest of meta-issue [#906](https://github.com/krpc/krpc/issues/906)
([protocol/improvements.md](design/protocol/improvements.md)), built on the 0.8 single connection
and covered by the conformance suite as it lands.

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Client → server streams | [#903](https://github.com/krpc/krpc/issues/903) (milestone to add) | [protocol/reverse-streams.md](design/protocol/reverse-streams.md) |
| 🚧 | Batching / transactions, fire-and-forget | [#903](https://github.com/krpc/krpc/issues/903) | [protocol/reverse-streams.md](design/protocol/reverse-streams.md); `KRPC.RunFunction` (#1124) already runs a batch in one tick |
| 🚧 | Tick control — one RPC/batch per physics update, replacing the tick hold stopgap | [#251](https://github.com/krpc/krpc/issues/251) (milestone to add) | [server/tick-hold.md](design/server/tick-hold.md) is the stopgap; protocol design open |

## Not scheduled

Milestone changes for existing issues are listed in [issues/github-changes.md](issues/github-changes.md).

### Issues to file, no milestone

| | Item | Draft | Design doc |
| --- | --- | --- | --- |
| ⬜ | Per-client receive patience | [recv-patience.md](issues/recv-patience.md) | [server/recv-timeout-cliff.md](design/server/recv-timeout-cliff.md) |
| 🚧 | RemoteTech API bindings and KAC alarm actions | [remotetech-kac-api.md](issues/remotetech-kac-api.md) | [services/kac-remotetech-tests-and-api.md](design/services/kac-remotetech-tests-and-api.md) |
| ⬜ | InfernalRobotics input linking and sun tracking | [infernal-robotics-input-linking.md](issues/infernal-robotics-input-linking.md) | [services/infernal-robotics-input-linking.md](design/services/infernal-robotics-input-linking.md) |
| 🚧 | Mod compatibility tests | [mod-compat-tests.md](issues/mod-compat-tests.md) | [services/mod-compat-test-coverage.md](design/services/mod-compat-test-coverage.md), [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| 🚧 | Autopilot test-plan gaps | [autopilot-test-gaps.md](issues/autopilot-test-gaps.md) | [autopilot/test-plan.md](design/autopilot/test-plan.md) |
| ⬜ | XML doc crefs to exceptions | [doc-crefs-to-exceptions.md](issues/doc-crefs-to-exceptions.md) | [build-tools/doc-crefs-to-exceptions.md](design/build-tools/doc-crefs-to-exceptions.md) |
| ⬜ | NUnit 5 | [nunit-5-migration.md](issues/nunit-5-migration.md) | [build-tools/nunit-5-migration.md](design/build-tools/nunit-5-migration.md) |
| ⬜ | Bazel sandbox in CI | [buildenv-linux-sandbox.md](issues/buildenv-linux-sandbox.md) | — |
| ⬜ | Lua API docs on sphinx-lua-ls | [lua-sphinx-domain.md](issues/lua-sphinx-domain.md) | — |
| ⬜ | luasocket release pin, blocked upstream | [luasocket-release-pin.md](issues/luasocket-release-pin.md) | [build-tools/lua-socket-unix-on-windows.md](design/build-tools/lua-socket-unix-on-windows.md) |

### Proposals and existing issues

| | Feature | Notes |
| --- | --- | --- |
| ⬜ | Server side function follow-ups: function release, shared nodes, batched tree construction, C# statement functions, yielding procedures, arbitrary expressions | Proposals in [server-side-functions/](design/server-side-functions/). Function release reopens #1107 when started. |
| ⬜ | Autopilot extensions: aero and large planes ([#526](https://github.com/krpc/krpc/issues/526)), bank-to-turn, heterogeneous actuators, output filter knobs, sign convention refactor | Proposals in [autopilot/](design/autopilot/README.md). Aero maybe deferred to a MechJeb integration. #526 is milestoned 1.0.0 on GitHub. |
| ⬜ | Trajectories service | Proposal, [services/trajectories-service.md](design/services/trajectories-service.md). |
| ⬜ | Nullable set elements and dictionary keys | Parked, likely dropped, [protocol/nullable-keys-and-set-elements.md](design/protocol/nullable-keys-and-set-elements.md). |
| 🚧 | More communication protocols ([#899](https://github.com/krpc/krpc/issues/899)) | Local sockets landed in 0.7; anything further unplanned. |
| ⬜ | Inheritance support ([#905](https://github.com/krpc/krpc/issues/905)) | Just a nicety; skipping keeps the OOP model simple — clients translate their OOP to procedures. |
| ⬜ | Constructor calls ([#898](https://github.com/krpc/krpc/issues/898)) | Objects are wrappers of game objects, GC'd when unreferenced by the game; constructors add a new refcounted object kind. |
| ⬜ | SSL / encryption ([#11](https://github.com/krpc/krpc/issues/11)) | Likely out of scope; use a proxy / tunnel. |
| 🚧 | Mod integrations: Principia ([#767](https://github.com/krpc/krpc/issues/767)), MechJeb2 and Kerbal Engineer Redux ([#288](https://github.com/krpc/krpc/issues/288)), Raster Prop Monitor ([#375](https://github.com/krpc/krpc/issues/375), [#424](https://github.com/krpc/krpc/issues/424)) | Principia phase 1 shipped as a docs page; phases 2 and 3 wait on upstream — [services/principia-service.md](design/services/principia-service.md). |
| ⬜ | DockingCam and LaserDist need forks ([#674](https://github.com/krpc/krpc/issues/674)) | [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md). |
| ⬜ | Vessel state and staging prediction ([#311](https://github.com/krpc/krpc/issues/311)) | Old request; parts may already be covered by the stage API. |
| 🚧 | Docs restructure ([#1050](https://github.com/krpc/krpc/issues/1050)) | Can land in any release. |
| ⬜ | Windows CI flakes: local socket hang ([#1078](https://github.com/krpc/krpc/issues/1078)), Python stream test ([#1138](https://github.com/krpc/krpc/issues/1138)) | Can land in any release. |

### Negative results

| Feature | Design doc |
| --- | --- |
| Service versioning | [services/service-versioning.md](design/services/service-versioning.md) |
| CI lite and merge queue | [build-tools/ci-lite-merge-queue.md](design/build-tools/ci-lite-merge-queue.md) |
| CI remote cache | [build-tools/ci-remote-cache.md](design/build-tools/ci-remote-cache.md) |
