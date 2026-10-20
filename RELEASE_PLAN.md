# Release plan

Planned features per release, with pointers to design docs where they exist. Work status
lives on GitHub ([`krpc/krpc`](https://github.com/krpc/krpc) issues and PRs); this is the
roadmap; the icons give progress at a glance.

✅ done · 🚧 in progress or partly done · ⬜ not started

| | Release | Theme | Progress |
| --- | --- | --- | --- |
| 🚧 | 0.7 | Server-side functions, streams and events, protocol additions, service improvements | All features merged; pre-release fixes drafted in [issues/](issues/README.md#070); unreleased |
| ⬜ | 0.8 | Single connection, then client conformance testing and thread safety | 0 of 4 started |
| ⬜ | 1.0 | Remaining protocol improvements (#906) | 0 of 3 done; tick control has a 0.7 stopgap |

## 0.7 — server-side functions, streams and events, service improvements

Everything merged since v0.6.0 (PRs #1015 to #1130, milestone 0.7.0). The main features:

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
| ✅ | Game state and scene handling (no game loaded, scene checks) | #1041, #1119, #1121 | — |
| ✅ | Client optimization, benchmark suite | #1056, #1052 | [build-tools/benchmarks.md](design/build-tools/benchmarks.md) |
| ✅ | Cnano client TCP/IP | #1055 | — |

### Services

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Debug service | #1033 | [services/debug-service.md](design/services/debug-service.md) |
| ✅ | Editor scene API | #1038, #1059, #1064 | [services/editor-scene-api.md](design/services/editor-scene-api.md) |
| ✅ | UI: code-built controls, layout and widgets | #1040 | [services/ui-controls-and-layout.md](design/services/ui-controls-and-layout.md) |
| ✅ | Drawing: map view, editor, tracking station, primitives, navball markers | #1115, #1116, #1037 | — |
| ✅ | Orbits from state vectors, expanded orbit API | #1046, #1087 | [services/orbits-from-state-vectors.md](design/services/orbits-from-state-vectors.md) |
| ✅ | Buoyancy | #1103 | [services/buoyancy.md](design/services/buoyancy.md) |
| ✅ | Precision mode, RCS force and torque | #1082, #1080 | — |
| ✅ | RealFuels support | #1039 | — |
| ✅ | Plus many smaller SpaceCenter additions and fixes | — | — |

### Build and tools

| | Feature | PRs |
| --- | --- | --- |
| ✅ | Windows build and test in CI | #1058, #1060 |
| ✅ | KSP version compatibility code removed | #1048 |
| ✅ | Package metadata and release process cleanup | #1015 |

### Open on the 0.7.0 milestone

| | Issue | Notes |
| --- | --- | --- |
| ✅ | [#1117](https://github.com/krpc/krpc/issues/1117) Setting `KRPC.GameScene` to flight from the space center throws `NullReferenceException` | Fixed by #1131 |

## 0.8 — single connection, then client conformance and thread safety

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Single connection: RPC and stream servers merged | none yet | [protocol/single-connection.md](design/protocol/single-connection.md) |
| ⬜ | Request ids, with the single connection | none yet | [protocol/request-ids.md](design/protocol/request-ids.md) |
| ⬜ | Client conformance tests and runtime specification | [#1123](https://github.com/krpc/krpc/issues/1123) | [client-conformance.md](design/client-conformance.md) |
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

## 1.0 — remaining protocol improvements

The rest of meta-issue [#906](https://github.com/krpc/krpc/issues/906)
([protocol/improvements.md](design/protocol/improvements.md)), built on the 0.8 single connection
and covered by the conformance suite as it lands.

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Client → server streams | [#903](https://github.com/krpc/krpc/issues/903) | [protocol/reverse-streams.md](design/protocol/reverse-streams.md) |
| ⬜ | Batching / transactions, fire-and-forget | [#903](https://github.com/krpc/krpc/issues/903) | [protocol/reverse-streams.md](design/protocol/reverse-streams.md) |
| 🚧 | Tick control — one RPC/batch per physics update, replacing the tick hold stopgap | [#251](https://github.com/krpc/krpc/issues/251) | — (protocol design open) |

## Not scheduled

| | Feature | Notes |
| --- | --- | --- |
| 🚧 | Service versioning | Implemented on a branch, never merged — [services/service-versioning.md](design/services/service-versioning.md). |
| ⬜ | Server-side arbitrary expressions, and server-side function follow-ups | Proposals — see [server-side-functions/](design/server-side-functions/). |
| 🚧 | More communication protocols ([#899](https://github.com/krpc/krpc/issues/899)) | Local sockets landed in 0.7; anything further unplanned. |
| ⬜ | Inheritance support ([#905](https://github.com/krpc/krpc/issues/905)) | Just a nicety; skipping keeps the OOP model simple — clients translate their OOP to procedures. |
| ⬜ | Constructor calls ([#898](https://github.com/krpc/krpc/issues/898)) | Objects are wrappers of game objects, GC'd when unreferenced by the game; constructors add a new refcounted object kind. |
| ⬜ | Autopilot aero, incl. large planes ([#526](https://github.com/krpc/krpc/issues/526)) | Maybe ignore, defer to MechJeb integration — [autopilot/aero-extension.md](design/autopilot/aero-extension.md). #526 is milestoned 1.0.0 on GitHub. |
| ⬜ | SSL / encryption ([#11](https://github.com/krpc/krpc/issues/11)) | Likely out of scope; use a proxy / tunnel. |
| 🚧 | Mod integrations: Principia ([#767](https://github.com/krpc/krpc/issues/767)), MechJeb2 and Kerbal Engineer Redux ([#288](https://github.com/krpc/krpc/issues/288)), Raster Prop Monitor ([#375](https://github.com/krpc/krpc/issues/375), [#424](https://github.com/krpc/krpc/issues/424)), FAR static analysis ([#420](https://github.com/krpc/krpc/issues/420)) | Principia phase 1 shipped as a docs page; phases 2 and 3 wait on upstream — [services/principia-service.md](design/services/principia-service.md). |
| 🚧 | Mod fixes: DockingCam and LaserDist need forks ([#674](https://github.com/krpc/krpc/issues/674)), kOS name tag duplicated ([#829](https://github.com/krpc/krpc/issues/829)) | [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md); #829 has PR #965 open — [services/kos-nametag-shared-module.md](design/services/kos-nametag-shared-module.md). |
| ⬜ | SpaceCenter API requests: vessel state and staging prediction ([#311](https://github.com/krpc/krpc/issues/311)), landing ([#352](https://github.com/krpc/krpc/issues/352)) | Old requests; parts may already be covered by the stage API and per-part bounding boxes. |
| 🚧 | Docs, build and test: docs restructure ([#1050](https://github.com/krpc/krpc/issues/1050)), Python linting and type checking ([#660](https://github.com/krpc/krpc/issues/660)), service test improvements ([#259](https://github.com/krpc/krpc/issues/259)), Windows CI local socket hang ([#1078](https://github.com/krpc/krpc/issues/1078)) | Can land in any release. #259 has 4 of its 5 items ticked. |
