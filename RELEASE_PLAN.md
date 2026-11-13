# Release plan

The authoritative list of planned work per release, with pointers to design docs. Each item is an
issue in [issues/](issues/), done as pull requests on [`krpc/krpc`](https://github.com/krpc/krpc).
The GitHub issue tracker is for public bug reports; the few items that started there keep their
GitHub issue.

✅ done · 🚧 in progress or partly done · ⬜ not started · ⛔ blocked

The **Issue** column says what tracks the item:

* A link into [issues/](issues/): the issue, done as one or more PRs, which the column then lists.
* `#N`: a GitHub issue, with the milestone given here.
* `#N`, then a **bold action**: a GitHub issue that needs that change.
* `PR #N`: no issue, the pull request tracks the work.
* **To write**: no issue yet.

The milestone goes on the PRs, and on a GitHub issue: 0.8 is `ksp-v0.8.0`, 1.0 is `ksp-v1.0.0`.
Finished items are collapsed under **Done** in each section.

| | Release | Theme | Progress |
| --- | --- | --- | --- |
| ✅ | [0.7](#07-server-side-functions-streams-and-events-service-improvements) | Server-side functions, streams and events, protocol additions, service improvements | Tagged 2026-10-21 |
| 🚧 | [0.8](#08-single-connection-client-codegen-then-client-conformance-and-thread-safety) | Single connection, client codegen, then client conformance testing and thread safety | 16 of 26 features done |
| ⬜ | [1.0](#10-remaining-protocol-improvements-server-side-function-follow-ups) | Remaining protocol improvements (#906), server side function follow-ups | 0 of 9 done; tick control has a 0.7 stopgap |

## 0.7: server-side functions, streams and events, service improvements

Everything merged since v0.6.0, PRs #1015 to #1163 on milestone 0.7.0. Tagged 2026-10-21.

<details>
<summary>Done (41)</summary>

### Protocol and server

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Protocol version 1 in the handshake, with version 0 served as 1 | #1162 | [protocol/protocol-version.md](design/protocol/protocol-version.md) |
| ✅ | Server-side functions | #1124 to #1130 | [server-side-functions/server-side-functions.md](design/server-side-functions/server-side-functions.md) |
| ✅ | Stream and event improvements: refcounting, invalidation | #1122, #1108, #1109 | [protocol/stream-and-event-improvements.md](design/protocol/stream-and-event-improvements.md), superseding [protocol/stream-refcounting.md](design/protocol/stream-refcounting.md) and [protocol/stream-invalidation.md](design/protocol/stream-invalidation.md) |
| ✅ | Stream freezing removed | #1118 | [protocol/stream-freezing-removal.md](design/protocol/stream-freezing-removal.md) |
| ✅ | Extension members | #1077 | [protocol/extension-members.md](design/protocol/extension-members.md) |
| ✅ | Structure types | #1066, #1067 | [protocol/struct-types.md](design/protocol/struct-types.md) |
| ✅ | Nullable values, incl. inside structures and collections | #1017, #1091 | [protocol/nullable-values.md](design/protocol/nullable-values.md), [protocol/nested-nullable-values.md](design/protocol/nested-nullable-values.md) |
| ✅ | Object lifetime and removal | #1051, #1072, #1120 | [object-lifetime.md](design/object-lifetime.md) |
| ✅ | Physics tick synchronization (tick hold, stopgap for #251), auto-pilot update timing | #1070 | [server/tick-hold.md](design/server/tick-hold.md), [autopilot/update-timing.md](design/autopilot/update-timing.md) |
| ✅ | Local socket transport | #1065 | [protocol/local-transports.md](design/protocol/local-transports.md) |
| ✅ | More communication protocols; local sockets landed in 0.7, gRPC moved to #1187 | [#899](https://github.com/krpc/krpc/issues/899) | [protocol/local-transports.md](design/protocol/local-transports.md) |
| ✅ | Definition ordering | #1044 | [protocol/definition-ordering.md](design/protocol/definition-ordering.md) |
| ✅ | RPCs deprecated in 0.6.0 removed | #1140 | — |
| ✅ | Game state and scene handling (no game loaded, scene checks, scene loads) | #1041, #1119, #1121, #1131 | — |
| ✅ | Client optimization, benchmark suite | #1056, #1052 | [build-tools/benchmarks.md](design/build-tools/benchmarks.md) |
| ✅ | Get object id helper in every client | #1160 | — |
| ✅ | Cnano client TCP/IP | #1055 | — |
| ✅ | Lua 5.1 to 5.4, lua-protobuf, `socket.unix` on Windows | #1142 | [build-tools/lua-5.4-and-lua-protobuf.md](design/build-tools/lua-5.4-and-lua-protobuf.md), [build-tools/lua-socket-unix-on-windows.md](design/build-tools/lua-socket-unix-on-windows.md) |

### Services

| | Feature | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Debug service, force RPCs, `SetFlight` teleport fix | #1033, #1146, #1158 | [services/debug-service.md](design/services/debug-service.md) |
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
| ✅ | Build tools and dependencies updated, sphinx-csharp 1.0.0 | #1139, #1159, #1163 | — |
| ✅ | Doc examples checked, client API docs match the stubs, link checker | #1141, #1151, #1156 | — |
| ✅ | Generated client files named after their service, C/C++ header includes | #1149, #1150 | — |
| ✅ | In-game test waits, buildifier as a test | #1147, #1152 | — |
| ✅ | Changelogs grouped by topic | #1157 | — |

</details>

## 0.8: single connection, client codegen, then client conformance and thread safety

One connection per client in place of separate RPC and stream connections, on protocol version 2,
with client behavior set by a runtime specification and checked by a conformance suite across every
client. A hard break: clients older than 0.8 cannot connect to a 0.8 server.

### Features

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| 🚧 | Client name collisions: a scanner rule banning clashing member names, a contract for client naming, the clashing `ConfigNode` methods removed (done: #1261, #1273) | [#1237](https://github.com/krpc/krpc/issues/1237) | [protocol/service-definition-rules.md](design/protocol/service-definition-rules.md), [protocol/client-naming.md](design/protocol/client-naming.md) |
| ⬜ | Inheritance for remote objects; additive, UI and Drawing first, then robotics and #900 modules | [#905](https://github.com/krpc/krpc/issues/905) | [protocol/inheritance.md](design/protocol/inheritance.md) |
| 🚧 | Flags enumerations, for `SpaceCenter.MapFilter`, with conformance tests; breaking for `MapFilterType.All`. Implemented for the server and every client, not yet submitted | [krpc-enum-flags.md](issues/krpc-enum-flags.md) | — |
| ⬜ | Flags enumerations in server side functions: `Expression.Not`, and the Python and C# compilers' operators; follows the flags enumerations PR | [krpc-enum-flags-functions.md](issues/krpc-enum-flags-functions.md) | — |
| 🚧 | Scanner errors disable only the broken members, a broken mod disables only its integration, listed in one popup | [#1227](https://github.com/krpc/krpc/issues/1227) | [server/partial-loading.md](design/server/partial-loading.md), [server/problem-reporting.md](design/server/problem-reporting.md) |
| ⬜ | `RequiresMod` attribute: the server checks that a service's mod is available before each RPC | [requires-mod-attribute.md](issues/requires-mod-attribute.md) | [server/partial-loading.md](design/server/partial-loading.md) |
| 🚧 | Python: build every service from the server's definitions, with generated declarations for type checking; removes `use_pregenerated_stubs` and replaces the Python part of #1195. Phases 1 to 2b merged, and two phase 3 follow-ups: typed function compiler, `definitions` and `declarations` conformance profiles. Open: pyright on generated modules, `<Service>Client` escaped, `--bundle`, a connect per game | [python-declarations.md](issues/python-declarations.md), PRs #1298, #1302, #1303, #1304, #1305, #1306 | [python-declarations.md](design/python-declarations.md) |
| 🚧 | JavaScript client for the browser, on WebSockets, in phases. Phases 1 to 3 implemented, not yet submitted | **To write** | [javascript-client.md](design/javascript-client.md) |
| 🚧 | Trajectories service; a PR from an outside contributor | PR #1253, **add milestone** | [services/trajectories-service.md](design/services/trajectories-service.md) |
| 🚧 | Kerbal Engineer Redux service | [#288](https://github.com/krpc/krpc/issues/288), **add milestone** | [services/kerbal-engineer-redux.md](design/services/kerbal-engineer-redux.md) |

<details>
<summary>Done (16)</summary>

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ✅ | Single connection: RPC and stream connections merged | [#1174](https://github.com/krpc/krpc/issues/1174), fixed by #1219 | [protocol/single-connection.md](design/protocol/single-connection.md) |
| ✅ | Protocol version 2, with the single connection | Part of the single connection issue, #1219 | [protocol/protocol-version.md](design/protocol/protocol-version.md) |
| ✅ | Procedure ids derived from names, with protocol version 2 | [#1196](https://github.com/krpc/krpc/issues/1196), fixed by #1265 | [protocol/procedure-ids.md](design/protocol/procedure-ids.md) |
| ✅ | Request ids (phase 1), on the single connection branch | [#1175](https://github.com/krpc/krpc/issues/1175), fixed by #1219 | [protocol/request-ids.md](design/protocol/request-ids.md) |
| ✅ | Client codegen: the exception mapping and the service list, generated | #1172 | [client-codegen.md](design/client-codegen.md) |
| ✅ | Client conformance tests and runtime specification | [#1123](https://github.com/krpc/krpc/issues/1123), fixed by #1220 | [client-conformance/](design/client-conformance/README.md) |
| ✅ | Client thread safety: define and document what is thread-safe | [#427](https://github.com/krpc/krpc/issues/427), fixed by #1225 | — |
| ✅ | C-nano: every transport compiled in, chosen at run time, so vcpkg ships them all; a custom transport is a table of functions | [#1176](https://github.com/krpc/krpc/issues/1176), fixed by #1275 | [cnano-transports.md](design/cnano-transports.md) |
| ✅ | Streams of calls and server side functions that return no value, run for their side effects | [#1198](https://github.com/krpc/krpc/issues/1198), fixed by #1272 | — |
| ✅ | Lua and C-nano: compile and run server side functions built with the expression API, which the internal `KRPC` procedures left them without | [#1267](https://github.com/krpc/krpc/issues/1267), fixed by #1297, C-nano in #1295 | — |
| ✅ | `GetStatus` returns a kRPC struct in place of the `KRPC.Status` protobuf message | [#1197](https://github.com/krpc/krpc/issues/1197), fixed by #1244 | — |
| ✅ | DockingCamera on the public Docking Camera (KURS) release; with the LIDAR deprecation, supersedes #674 | [#1232](https://github.com/krpc/krpc/issues/1232), fixed by #1264 | [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| ✅ | Deprecate LIDAR in favor of `SpaceCenter.RaycastDistance`, and raycasts ignore trigger colliders; makes #1181 moot | [#1233](https://github.com/krpc/krpc/issues/1233), fixed by #1263 | [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| ✅ | C#: target .NET Standard 2.0 in place of .NET Framework 4.7.2 | [#1230](https://github.com/krpc/krpc/issues/1230), fixed by #1274 | [csharp-client-targets.md](design/csharp-client-targets.md) |
| ✅ | C#: import the NuGet packages with rules_dotnet's `nuget_repo`, one target per package for every framework; straight after #1230 | [csharp-nuget-repo.md](issues/csharp-nuget-repo.md), done by PR [#1294](https://github.com/krpc/krpc/pull/1294) | [csharp-client-targets.md](design/csharp-client-targets.md) |
| ✅ | Java: publish the client to Maven Central | [#1231](https://github.com/krpc/krpc/issues/1231), fixed by #1276 | — |

</details>

### Merged

<details>
<summary>Done (30)</summary>

| | Item | PRs | Design doc |
| --- | --- | --- | --- |
| ✅ | Rails warp limit matches the game's in flight (fixes #1164) | #1167 | — |
| ✅ | Math and units rendered in the service docs | #1169 | [build-tools/doc-math.md](design/build-tools/doc-math.md) |
| ✅ | Docs restructured into User Guides, Clients and Developer Guide (fixes #1050) | #1170 | [build-tools/doc-structure.md](design/build-tools/doc-structure.md) |
| ✅ | Build and CI: krpctest changelog on release, vcpkg caches, `KRPC_TEST_` variables, CI version sha, nanopb download | #1165, #1166, #1168, #1171, #1173 | — |
| ✅ | Autopilot with large planes (fixes #526) | #1191 | [autopilot/aero-extension.md](design/autopilot/aero-extension.md) |
| ✅ | Client API docs: XML doc crefs to exceptions, checked docs in every client (fixes #1183) | #1185 | [build-tools/doc-crefs-to-exceptions.md](design/build-tools/doc-crefs-to-exceptions.md) |
| ✅ | Bazel sandbox in CI, in the processwrapper sandbox, and a slimmer build image | #1184 | — |
| ✅ | Refuse an enumeration default the enumeration does not declare | #1192 | — |
| ✅ | Compare stream values by their encoding | #1199 | — |
| ✅ | Client guides restructured, one guide per client; developer documentation brought up to date (fixes #427) | #1225 | — |
| ✅ | New logo, README refresh, license fixes | #1221 | — |
| ✅ | Build and CI: Python autodoc timeout, Lua lint in CI, doc serve staging, third-party C++ disk cache, vcpkg cache per runner image | #1208, #1218, #1224, #1226, #1229 | — |
| ✅ | Events from `AddEvent` are edge triggered | #1234 | — |
| ✅ | Quieter server logging, with the client named in log lines (fixes #1180) | #1235 | — |
| ✅ | Adaptive rate control keeps the configured max. time per update (fixes #1236) | #1250 | — |
| ✅ | Compiled delegates for reflected members | #1251 | — |
| ✅ | Internal procedures for the `KRPC` service's stream, event and function plumbing, hidden from stubs and docs | #1269 | — |
| ✅ | Conformance: the `threads` profile renamed `concurrency`, before the JavaScript client | #1270 | [javascript-client.md](design/javascript-client.md) |
| ✅ | Build and CI: changelog fragments and PR hints, merge queue, CI hardened against flaky downloads, docs build on Windows (fixes #1259), run-ksp follows the current log | #1239, #1240, #1242, #1254, #1260, #1268 | — |
| ✅ | Lua: `nil` for null values, and a `nil` argument no longer drops the ones after it | #1278 | — |
| ✅ | Python: `isinstance` and `issubclass` with a class reached through a connection | #1279 | [static-method-binding.md](design/static-method-binding.md) |
| ✅ | Build and CI: versions dropped from the Java guide's `javac` example, flaky Python client tests listed | #1238, #1246, #1248 | — |
| ✅ | C++ and C-nano clients and the Arduino library licensed under MIT | #1281 | — |
| ✅ | C#: each target built for the framework that runs it | #1283 | — |
| ✅ | Client design pages on the docs site; guides corrected on when a stream ends and a connection stays open | #1287 | — |
| ✅ | Conformance: `Rate` testee command renamed `GetRate`, `TestService2` and `ConformanceService` definitions shipped in krpctools, more flaky tests listed | #1282, #1284, #1288 | — |
| ✅ | Build and CI: service imports sorted in generated Python stubs, tool package tests started once the Python client is built | #1292, #1293 | — |
| ✅ | C# tools: System.CommandLine and System.Text.Json replace NDesk.Options and Newtonsoft.Json; `krpc-testserver` and `krpc-servicedefs` reject unknown options, service definitions written in a fixed order | #1296 | — |
| ✅ | Python: an `RPCError` for a server error naming a class that is not an exception, and a deprecated procedure keeps its signature | #1300, #1301 | — |
| ✅ | Conformance: run Python's `:conformance-base` with no stubs, as it loads them today; first phase of the Python declarations work | #1298 | [python-declarations.md](design/python-declarations.md) |

</details>

### Fixes and smaller items

| | Item | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Scanner rules for service, type, parameter and enumeration value names, and the C++ helper names | [clientgen-qualified-names.md](issues/clientgen-qualified-names.md) | [protocol/service-definition-rules.md](design/protocol/service-definition-rules.md) |
| ⬜ | Clients: escape a service or type name that meets a client's own name | [client-name-escapes.md](issues/client-name-escapes.md) | [protocol/client-reserved-names.md](design/protocol/client-reserved-names.md) |
| ⬜ | Clients: use `Connection` for the entry point in every client | [client-class-names.md](issues/client-class-names.md) | — |
| ⬜ | Deprecation signals for every member kind in every client | [deprecation-all-members.md](issues/deprecation-all-members.md) | — |
| 🚧 | Audit how each client binds static methods and streams to a connection; the Python part done by #1302 | [#1195](https://github.com/krpc/krpc/issues/1195) | [static-method-binding.md](design/static-method-binding.md) |
| ⬜ | Clients: calls that cannot go in a server side function | [calls-a-function-cannot-make.md](issues/calls-a-function-cannot-make.md) | — |
| ⬜ | Clients: check whether a per-element function needs a real instance | [call-with-arguments-template.md](issues/call-with-arguments-template.md) | [server-side-functions/server-side-functions.md](design/server-side-functions/server-side-functions.md) |
| ⬜ | Lua: `platform.sleep` busy-waits, to whole seconds | [lua-platform-sleep.md](issues/lua-platform-sleep.md) | — |
| ⬜ | In-game tests for websockets, serial IO and local sockets, for what `TestServer` and the unit tests do not reach | [ingame-protocol-tests.md](issues/ingame-protocol-tests.md) | — |
| 🚧 | Update the `krpc` and `krpc-cnano` vcpkg ports for 0.8.0: MIT licenses, copyright files, every C-nano transport (done in the repo: #1275, #1281; publishing waits on the release) | [vcpkg-ports-0-8.md](issues/vcpkg-ports-0-8.md) | — |
| ⬜ | SpaceCenter: setting the IVA camera mode fails silently straight after a launch, and leaves the IVA when already in it | [camera-iva-mode-setter.md](issues/camera-iva-mode-setter.md) | — |

<details>
<summary>Done (17)</summary>

| | Item | Issue | Design doc |
| --- | --- | --- | --- |
| ✅ | Close a WebSockets connection whose frame is too large | #1193 | — |
| ✅ | Codec and clientgen fixes: bytes default arguments in generated code, a C# nullable enum return, a C++ short tuple | #1194 | [client-conformance/](design/client-conformance/README.md) |
| ✅ | `RemoveStream` and `SetStreamRate` take a `Stream`; resolved the other way, streams and events encoded as bare stream ids | [#1178](https://github.com/krpc/krpc/issues/1178), fixed by #1266 | — |
| ✅ | `KerbalAlarmClock.Alarm.PlaySound` has no effect | [#1179](https://github.com/krpc/krpc/issues/1179), fixed by #1262 | [services/kac-remotetech-tests-and-api.md](design/services/kac-remotetech-tests-and-api.md) |
| ✅ | DockingCamera log spam | [#1180](https://github.com/krpc/krpc/issues/1180), fixed by #1235 | [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| ✅ | Fail a call with an invalid argument position: past the last parameter, or two arguments at one position; breaking | #1290 | — |
| ✅ | Strict argument decoding: fail a call with an argument the server cannot decode in full, each call failing on its own; breaking | #1280 | — |
| ✅ | Publish the bundled TestServer and ServiceDefinitions for every platform, so `krpc-conformance` and `servicedefs` run on Windows; the TestServer ships only in krpctools, as `krpc-testserver` | [#1228](https://github.com/krpc/krpc/issues/1228), fixed by #1271 | [ksa/build-and-test-tools.md](design/ksa/build-and-test-tools.md), "Service definitions" |
| ✅ | Run clang-format and clang-tidy over every C and C++ source | [#1177](https://github.com/krpc/krpc/issues/1177), fixed by #1277 | — |
| ✅ | C++: hold the client strongly, so objects never dangle, add `close()`, and take the client by reference in the public API; breaking | #1285, #1286 | — |
| ✅ | Clients: scope streams and events with each language's scoping construct, with a conformance test for events; removes Python's `Client.stream`, breaking | #1291 | — |
| ✅ | Documentation crefs use the C# service name | [#1188](https://github.com/krpc/krpc/issues/1188), fixed by #1243 | — |
| ✅ | Client disconnect during a yielding call stops the server on .NET | [#1189](https://github.com/krpc/krpc/issues/1189), fixed by #1249 | — |
| ✅ | Server window does not resize to fit its content | [#1186](https://github.com/krpc/krpc/issues/1186), fixed by #1247 | — |
| ✅ | Publish wheels for krpc and krpctools, in place of sdists | #1289 | — |
| ✅ | Lua API docs on sphinx-lua-ls, when luadomain breaks on a Sphinx bump | [#1202](https://github.com/krpc/krpc/issues/1202), fixed by #1252 | — |
| ✅ | Move krpctest into krpctools, as a game-agnostic in-game test runner | PR #1299 | [build-tools/krpctest-in-krpctools.md](design/build-tools/krpctest-in-krpctools.md), [ksa/build-and-test-tools.md](design/ksa/build-and-test-tools.md) |

</details>

## 1.0: remaining protocol improvements, server side function follow-ups

The rest of meta-issue #906 ([protocol/improvements.md](design/protocol/improvements.md)), built on
the 0.8 single connection and covered by the conformance suite as it lands. Each item is an
addition on protocol version 2, so 0.8 clients keep working: see
[protocol-compatibility.md](design/protocol-compatibility.md).

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Protocol improvements (meta issue) | [#906](https://github.com/krpc/krpc/issues/906) | [protocol/improvements.md](design/protocol/improvements.md) |
| 🚧 | Non-blocking calls and batching, fire-and-forget, client to server streams | [#903](https://github.com/krpc/krpc/issues/903), **add milestone** | [protocol/non-blocking-calls.md](design/protocol/non-blocking-calls.md), [protocol/fire-and-forget.md](design/protocol/fire-and-forget.md), [protocol/reverse-streams.md](design/protocol/reverse-streams.md); `KRPC.RunFunction` (#1124) already runs a batch in one tick |
| 🚧 | Tick control: one RPC or batch per physics update, replacing the tick hold stopgap | [#251](https://github.com/krpc/krpc/issues/251), **add milestone** | [server/tick-hold.md](design/server/tick-hold.md) is the stopgap; protocol design open |

### Server side function follow-ups

Follow-ups to server side functions, which merged in 0.7 (#1124 to #1130).

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Function release: a client releases the functions it no longer needs | [#1107](https://github.com/krpc/krpc/issues/1107), closed as premature, **reopen**, **add milestone** | [server-side-functions/function-release.md](design/server-side-functions/function-release.md) |
| ⬜ | Shared nodes compiled once, removing the `MaxNodes` bound | **To write** | [server-side-functions/shared-nodes.md](design/server-side-functions/shared-nodes.md) |
| ⬜ | Batched tree construction, gated on measuring real tree sizes | **To write** | [server-side-functions/batched-tree-construction.md](design/server-side-functions/batched-tree-construction.md) |
| ⬜ | C# functions with statements | **To write** | [server-side-functions/csharp-statement-functions.md](design/server-side-functions/csharp-statement-functions.md) |
| ⬜ | Yielding procedures: deferred calls and resumable functions | **To write** | [server-side-functions/yielding-procedures.md](design/server-side-functions/yielding-procedures.md) |
| ⬜ | Arbitrary expressions: opt-in calls to arbitrary CLR members | **To write** | [server-side-functions/server-side-arbitrary-expressions.md](design/server-side-functions/server-side-arbitrary-expressions.md) |

## Not scheduled

### Features

#### Protocol and server

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Events that carry a value: a core stream of the unsent firings as a list, no protocol change; waits for a service that needs it | [events-with-values.md](issues/events-with-values.md) | — |
| ⬜ | Streams and events over serial IO, after the single connection; needs flow control | [#1204](https://github.com/krpc/krpc/issues/1204) | [protocol/single-connection.md](design/protocol/single-connection.md) |
| ⬜ | Per-client receive patience | [recv-patience.md](issues/recv-patience.md) | [server/recv-timeout-cliff.md](design/server/recv-timeout-cliff.md) |
| ⬜ | gRPC support, possibly through an external bridge; the game's runtime cannot host it | [#1187](https://github.com/krpc/krpc/issues/1187) | [protocol/grpc-support.md](design/protocol/grpc-support.md) |

#### Clients

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Custom transports in every client, as C-nano has | [client-custom-transports.md](issues/client-custom-transports.md) | — |
| ⬜ | Python: asyncio conveniences over `submit`, after the single connection | [python-asyncio-client.md](issues/python-asyncio-client.md) | [protocol/request-ids.md](design/protocol/request-ids.md) |
| ⬜ | Lua: documentation for the dynamically built services | [#1182](https://github.com/krpc/krpc/issues/1182) | — |
| ⬜ | Lua: pre-generated type hints, LuaCATS annotations first, as the Python declarations | [lua-type-hints.md](issues/lua-type-hints.md) | [python-declarations.md](design/python-declarations.md) |
| ⬜ | MicroPython client, for boards such as the Raspberry Pi Pico; first check that generated stubs fit | [micropython-client.md](issues/micropython-client.md) | — |

#### Services and mod integrations

| | Feature | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Autopilot extensions: bank-to-turn, heterogeneous actuators, output filter knobs, sign convention refactor | — | [autopilot/bank-to-turn.md](design/autopilot/bank-to-turn.md), [autopilot/heterogeneous-actuators.md](design/autopilot/heterogeneous-actuators.md), [autopilot/output-filter-manual-knobs.md](design/autopilot/output-filter-manual-knobs.md), [autopilot/sign-convention-refactor.md](design/autopilot/sign-convention-refactor.md) |
| ⬜ | Index of mod integrations: existing work, plus SCANsat, Kerbalism, Near Future Solar and compatibility checks | [mod-integrations-index.md](issues/mod-integrations-index.md) | — |
| 🚧 | RemoteTech API bindings and KAC alarm actions | [remotetech-kac-api.md](issues/remotetech-kac-api.md) | [services/kac-remotetech-tests-and-api.md](design/services/kac-remotetech-tests-and-api.md) |
| ⬜ | InfernalRobotics input linking and sun tracking | [infernal-robotics-input-linking.md](issues/infernal-robotics-input-linking.md) | [services/infernal-robotics-input-linking.md](design/services/infernal-robotics-input-linking.md) |
| 🚧 | Principia support; phase 1 shipped as a docs page, phases 2 and 3 wait on upstream | [#767](https://github.com/krpc/krpc/issues/767) | [services/principia-service.md](design/services/principia-service.md) |
| ⬜ | MechJeb2 service, ported from Genhis' KRPC.MechJeb, then stage stats from MechJeb's fuel-flow simulation | [#288](https://github.com/krpc/krpc/issues/288), [#311](https://github.com/krpc/krpc/issues/311) | [services/mechjeb.md](design/services/mechjeb.md) |
| 🚧 | Raster Prop Monitor integration and camera views, all four phases on branch `raster-prop-monitor`, unpushed | [#375](https://github.com/krpc/krpc/issues/375), [#424](https://github.com/krpc/krpc/issues/424) | [services/raster-prop-monitor.md](design/services/raster-prop-monitor.md) |
| ⛔ | Per-thruster RCS control through IndividualRCS; a PR from an outside contributor | PR #1245 | — |

### Fixes, tests and tooling

#### Server and protocol

| | Item | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Raise the default receive timeout | [recv-timeout-default.md](issues/recv-timeout-default.md) | [server/recv-timeout-cliff.md](design/server/recv-timeout-cliff.md) |
| ⬜ | Reject a string argument holding invalid UTF-8 in the KSP mod; measure the cost first | [invalid-utf8-arguments.md](issues/invalid-utf8-arguments.md) | — |
| ⬜ | Find out what users see with a mismatched client, server or service, per client; document the symptoms in the docs | [client-server-mismatch.md](issues/client-server-mismatch.md) | [protocol-compatibility.md](design/protocol-compatibility.md) |
| ⬜ | Compiled delegates for the KSA control inputs; waits on a `KRPC.Core` release with `Accessor` | [ksa-control-inputs-delegates.md](issues/ksa-control-inputs-delegates.md) | — |

#### Client spec and conformance

| | Item | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Client spec: rule on the behavior clients differ on, starting with one callback thread per connection, and add the tests | [conformance-spec-rulings.md](issues/conformance-spec-rulings.md) | [client-conformance/spec.md](design/client-conformance/spec.md) |
| ⬜ | Conformance: coverage gaps, including skipped arguments in a call built for a server side function | [conformance-coverage-gaps.md](issues/conformance-coverage-gaps.md) | [client-conformance/](design/client-conformance/README.md) |
| ⬜ | Conformance: race points in C# and Python, then forced orders in place of guessed sleeps | [conformance-race-points.md](issues/conformance-race-points.md) | [client-conformance/harness.md](design/client-conformance/harness.md) |
| ⬜ | Conformance driver: notification waits, the serial link wait, a self-removing callback helper | [conformance-driver.md](issues/conformance-driver.md) | [client-conformance/harness.md](design/client-conformance/harness.md) |

#### Clients

| | Item | Issue | Design doc |
| --- | --- | --- | --- |
| ⬜ | Clients: defects more than one client shares | [client-design-shared-defects.md](issues/client-design-shared-defects.md) | — |
| ⬜ | Generate the client API references from the client sources | [client-api-reference-autodoc.md](issues/client-api-reference-autodoc.md) | — |
| ⬜ | C#: defects found writing the design doc | [client-csharp-defects.md](issues/client-csharp-defects.md) | — |
| ⬜ | C#: keep the `.csproj` package versions in step with the Bazel lock files; follows the `nuget_repo` import | [csproj-package-versions.md](issues/csproj-package-versions.md) | — |
| ⬜ | C++: client defects | [client-cpp-defects.md](issues/client-cpp-defects.md) | — |
| ⬜ | Clients: a manual ASan, UBSan and TSan run for C++ and C-nano | [sanitizer-testing.md](issues/sanitizer-testing.md) | — |
| ⬜ | Java: defects found writing the design doc | [client-java-defects.md](issues/client-java-defects.md) | — |
| ⬜ | Python: defects found writing the design doc | [client-python-defects.md](issues/client-python-defects.md) | — |
| ⬜ | Python: Ctrl-C during a call on Windows, with the single connection | [python-ctrl-c-windows.md](issues/python-ctrl-c-windows.md) | [protocol/single-connection.md](design/protocol/single-connection.md) |
| ⬜ | Python: trim client frames from server error tracebacks | [python-traceback-trim.md](issues/python-traceback-trim.md) | — |
| ⬜ | clientgen: a Python `--include` given as a file path makes a wrong import; take a module name only; follows the Python declarations | [clientgen-python-include-paths.md](issues/clientgen-python-include-paths.md) | [python-declarations.md](design/python-declarations.md) |
| ⬜ | Lua: defects found writing the design doc | [client-lua-defects.md](issues/client-lua-defects.md) | — |
| ⬜ | Lua 5.1: `math.huge` stands for the largest integer, so 2^63 - 1 reads as infinity | [lua-51-math-huge.md](issues/lua-51-math-huge.md) | — |
| ⛔ | luasocket release pin, blocked upstream on lunarmodules/luasocket#469 | [#1203](https://github.com/krpc/krpc/issues/1203) | [build-tools/lua-socket-unix-on-windows.md](design/build-tools/lua-socket-unix-on-windows.md) |
| ⬜ | C-nano: defects found writing the design doc | [client-cnano-defects.md](issues/client-cnano-defects.md) | — |
| ⬜ | C-nano: retry POSIX serial reads and writes interrupted by a signal, and loop short writes | [cnano-serial-eintr.md](issues/cnano-serial-eintr.md) | — |
| ⬜ | C-nano: follow-ups to server side functions: generated functions, heap use, header opt-out, examples, testee cleanups | [cnano-functions-follow-ups.md](issues/cnano-functions-follow-ups.md) | — |
| ⬜ | Websockets testee: defects found writing the design doc | [client-websockets-defects.md](issues/client-websockets-defects.md) | — |

#### Tests, build and CI

| | Item | Issue | Design doc |
| --- | --- | --- | --- |
| 🚧 | Autopilot test-plan gaps | [autopilot-test-gaps.md](issues/autopilot-test-gaps.md) | [autopilot/test-plan.md](design/autopilot/test-plan.md) |
| 🚧 | Mod compatibility tests | [mod-compat-tests.md](issues/mod-compat-tests.md) | [services/mod-compat-test-coverage.md](design/services/mod-compat-test-coverage.md), [services/dockingcam-lidar-tests.md](design/services/dockingcam-lidar-tests.md) |
| ⬜ | NUnit 5 | [nunit-5-migration.md](issues/nunit-5-migration.md) | [build-tools/nunit-5-migration.md](design/build-tools/nunit-5-migration.md) |
| ⬜ | Windows CI: C-nano serial transport tests, over a named pipe | [#1200](https://github.com/krpc/krpc/issues/1200) | — |
| ⬜ | Build `KRPC.IO.Ports` from source in the net472 `KRPC.Core`, in place of the prebuilt DLL | [core-serial-ports.md](issues/core-serial-ports.md) | — |

### Negative results

| Feature | Design doc |
| --- | --- |
| A general "should stage now" check ([#311](https://github.com/krpc/krpc/issues/311)): when to stage depends on the craft's design. Scripts build their own rule on `Engine.Flameout` and the `Stage` API, in one round trip as a server side function. The rest of #311 is in the MechJeb2 service | [services/mechjeb.md](design/services/mechjeb.md) |
| Service versioning | [services/service-versioning.md](design/services/service-versioning.md) |
| CI lite and merge queue | [build-tools/ci-lite-merge-queue.md](design/build-tools/ci-lite-merge-queue.md) |
| CI remote cache | [build-tools/ci-remote-cache.md](design/build-tools/ci-remote-cache.md) |
| Constructor calls ([#898](https://github.com/krpc/krpc/issues/898)), closed: static class methods cover it | [protocol/inheritance.md](design/protocol/inheritance.md#constructors) |
| Nullable set elements and dictionary keys: implemented, then dropped over open questions on key semantics | [protocol/nullable-keys-and-set-elements.md](design/protocol/nullable-keys-and-set-elements.md) |
| Clients calling by procedure id in place of name: measured in C++, C#, Java and Python, with no measurable round trip gain over TCP/IP or a local socket, for 36% fewer bytes on a one-argument call. C-nano keeps ids, for flash and slow serial links | [analysis/procedure-ids-vs-names.md](analysis/procedure-ids-vs-names.md) |
| Leaving an argument at its default out of a generated stub's call: 84 of 2198 procedures have a defaulted parameter, mostly setup calls, and 55 of them save 6 or 7 bytes a call. Omitting it would let a stub call an older server after a service appends a parameter, at the cost of a comparison per argument, and of an explicit value equal to the stub's default giving way to the server's | — |
| Detecting a stub older than a service, such as by a hash of the signature on each call. An old stub leaves out a parameter appended with a default, so the call runs with the default, and a server cannot tell it from a current client. A client and server mismatch is never guaranteed to work. This case stays undetected, and users keep their stubs matched to the server | — |
| Python: warning at connect when the server's definitions differ from the generated declarations, by a hash per service from `clientgen`. The calls are built from the server's definitions and run correctly, so only static type checking is out of date | [python-declarations.md](design/python-declarations.md) |
| SSL encryption and authentication ([#11](https://github.com/krpc/krpc/issues/11)), closed as not planned: use a proxy or tunnel | — |
| Streams and events of a function with parameters, the arguments fixed when added: wrap it in a function with no parameters that calls it with constants. Doing that in the clients was also rejected: no constant node for collections, tuples or structs, and the server keeps every constant for the life of the connection | [server-side-functions/server-side-functions.md](design/server-side-functions/server-side-functions.md#function-arguments) |
| A stream rate in force from the stream's first update, by a rate argument to `AddStream` or a stream added stopped. The first value is never rate limited, and the rate timer starts when the stream is added. Extra updates need `SetStreamRate` to land two or more ticks after `AddStream`. To rule them out, add the stream and set its rate inside a tick hold, or inside its successor from [#251](https://github.com/krpc/krpc/issues/251) | [server/tick-hold.md](design/server/tick-hold.md) |
| Generating client stubs in `order.txt` order: `clientgen` sorts members by name, and the docs website already takes its order from `order.txt` through `docgen`. The new order would reach only stub readers and IDE outline views, and would reorder every stub and most `clientgen` goldens. Worth revisiting if a client's documentation system reads its order from the stubs | — |

## Issues

Each file in [issues/](issues/) is one issue: the heading is the title, the rest is the body. An
issue refers to another by a link to its file. A PR that does the work describes it on its own, as
nothing public may reference this repo.
