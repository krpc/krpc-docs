# Codebase-wide TODO / FIXME sweep

**Status:** done — all clusters merged to `main` 2026-07-19 as the nine-PR train #972
(protobuf-serialization), #973 (websockets), #974 (cpp-client-fixes), #975 (spacecenter-fixes),
#976 (server-ui), #977 (spacecenter-new-api), #978 (build-tooling), #979 (client-fixes) and #980
(spacecenter-test-improvements), with §3d merged earlier as PR #970. No umbrella GitHub issue was
filed — the PRs are the record. The deferred follow-ups each have their own
design doc: object lifetime → [#771](https://github.com/krpc/krpc/issues/771) / [PR #894](https://github.com/krpc/krpc/pull/894),
`RemoveStream` → #906, time-warp scene gating
([`time-warp-outside-flight.md`](../issues/time-warp-outside-flight.md)), and the deferred-state RPC
audit ([`deferred-state-rpc-audit.md`](services/deferred-state-rpc-audit.md)). This doc is the
historical record of the sweep.

This was a catalog of every `TODO`/`FIXME` comment in the source tree (90 of them, as of
2026-07-17), grouped by area with a disposition for each — a backlog to burn down, not a single
change; several clusters mapped onto work already tracked elsewhere (cross-references noted inline).
The work was consolidated, then split into the nine per-area PRs above
(trees verified byte-identical to the consolidated tree) and merged one at a time, each with its
own changelog commit where user-visible.

 * **Core server — protocol & networking (§1): done.** Five of
   the six items fixed (the two protobuf read paths reworked to be zero-copy, the websocket handshake
   made resilient to truncated/split requests, and both connection-URL query parsers made robust);
   the sixth (`RemoveStream` signature) is deliberately deferred to the #906 protocol work as a
   breaking change.
 * **Build & tooling (§7): done.** Three
   fixed (the Python cref snake_case bug, the packaging exclude matcher, and re-enabling `-W` on the
   spelling build) and three resolved as documented workarounds (the spelling dictionary copy, the
   serial-test startup delay, and Lua reference shortening).
 * **Client libraries — source (§5): done.** Two fixed (the Java encoder
   `unsafeWrap` and the C++ `CopyFrom`) and seven documented as
   correct-but-flagged code or constraints. The `WrappedClass` multi-client bug was fixed as well
   (per-client subclass + regression test). One item
   remains: the Python exception stack-trace rewrite, left as a deferred enhancement.
 * **SpaceCenter correctness/precision (§3b): done** (consolidated
   together with the §1/§7/§5 chain). Verified in-game. Two real fixes (the
   RCS `shieldedCanThrust` gate and wiring up `Wheel.SteeringAngleAuto` with a new test) and two
   negative results documented in place of their markers: the geometry double-precision "fix" was
   reverted — attempting it revealed that KSP's `QuaternionD.Euler`/`.eulerAngles` throw at runtime
   (their native `Internal_*EulerRad` binding is stripped), so the single-precision `Quaternion`
   round-trip is a necessary workaround, not an oversight — and the Experiment `gatherData`
   reflection is likewise necessary: disassembly of KSP 1.12 shows no public method runs an
   experiment without popping the results dialog (`DeployExperiment`/`DeployAction`/
   `DeployExperimentExternal` all hardcode `gatherData(showDialog: true)`; the only dialog-free
   caller, `OnActive`, is gated on staging configuration), so the FIXME was replaced with that
   rationale.
 * **SpaceCenter performance (§3c): done.** All four fixed: CommNode's two
   vessel-scan lookups replaced by an O(1) transform-based lookup, `Vessel.AngularVelocity`'s
   per-call `GetComponent<Rigidbody>()` replaced by the root part's cached rigidbody (applied to
   all nine sites of that idiom, including the attitude controller's per-tick reads), and
   `Flight.ReferenceArea`'s vessel-wrapper construction replaced by a shared `WetMass` extension.
   Verified in-game (81 tests: comms/flight/vessel + the autopilot quick gate).
 * **Server plugin UI (§2): done.** Two real fixes — the combo-box position now
   computed exactly with `GUIUtility.GUIToScreenPoint` (the old mouse-delta trick was verified
   in-game to be environment-dependent), and the option-dialog close path uses Unity's lifetime
   check instead of catching an NRE — plus rationale comments for the addon's static state and
   the scaled title-bar spacer.
 * **Client library tests (§6): done.** Both C++ re-enables uncovered real client
   bugs fixed along the way — lost stream-update notifications (notify without the condition mutex)
   and `freeze_streams` blocking forever when no stream produces updates. The Lua "enable tests"
   note became four new member-introspection tests. The remaining four markers were reworded or
   resolved (the C# Mono-workaround comment was obsolete; the Dispose it apologized for is ordinary
   cleanup and stays). Client-side fixes → changelog entries needed for `client/cpp`.
 * **SpaceCenter test quality/accuracy (§8c): done.** All ten questions answered:
   three tolerances explained (precision limits, model error, inter-RPC time skew), two part
   mysteries resolved (stageable docking ports; the intake's IntakeAir mass), and five assertions
   genuinely strengthened (sign-aware identity quaternion, no-axial-tilt rotation check,
   direction/rotation round-trips, rotational-velocity inclusion). Verified in-game.
 * **SpaceCenter missing/stubbed tests (§8b): done.** Five tests implemented
   (launchable vessels, IVA camera with a distance/pointing base split, SAS+speed target modes,
   node-removal assertions) and three gaps documented as untestable (stock-part and scene-gating
   constraints). The node-removal test exposed a real server defect — stale `Node` objects
   silently wrote to detached maneuver nodes — fixed with a flight-plan membership guard
   (changelog entry needed). Verified in-game.
 * **SpaceCenter cleanup/minor (§3e): done.** Two cleanups (the `InvokeEvent`
   PartModule extension; the maneuver-frame offset correction re-anchored to the node's own
   vessel), one documented constraint (warp is flight-scene-only because the API is defined in
   terms of the active vessel), two features implemented (`Parachute.SafeState` + enum; the four
   contract date properties) and one stale marker deleted (contract parameters already exposed).
   Verified in-game. The two new API surfaces need changelog entries pre-merge.
 * **SpaceCenter decouple/undock hack (§3d): done, merged** as PR #970.
   Verified in-game. Factored the duplicated ten-frame settle-wait into a shared
   `PartSeparation.NewVessel` helper that documents why the wait exists and why ten frames.

The sweep covered `*.cs`, `*.py`, `*.java`, `*.cpp`, `*.hpp`, `*.h`, `*.lua`, `*.bzl`, `*.rst`,
`*.proto`, excluding the Bazel output trees. Regenerate the raw list with:

```
grep -rniE '\b(TODO|FIXME)\b' --include='*.cs' --include='*.py' --include='*.java' \
  --include='*.cpp' --include='*.hpp' --include='*.h' --include='*.lua' --include='*.bzl' \
  --include='*.rst' --include='*.proto' . | grep -vE 'bazel-'
```

## How to read this

Each item is tagged with a rough disposition:

* **bug** — a comment marking behavior that is (or may be) wrong; worth verifying against the live
  game.
* **cleanup** — an acknowledged hack or inefficiency with no user-visible defect.
* **perf** — a known inefficiency called out for later optimization.
* **api** — a signature/shape the author already flagged as wanting to change (a breaking change, so
  release-gated).
* **feature** — unimplemented functionality behind a stub.
* **test** — a gap, skip, or workaround in a test suite.
* **tracked** — already covered by an existing design doc / planned-work item; listed here only for
  completeness, action lives there.

---

## 1. Core server — protocol & networking

**Done, except the deferred API change.**

| File:line | Disposition | Status | Note |
| --- | --- | --- | --- |
| `core/src/Server/ProtocolBuffers/Utils.cs:97` | **bug** | ✅ done | Turned out to be a protobuf API-semantics misunderstanding, not a bug (`ParseFrom` reads to the end of its input). Reworked the byte-buffer read path to decode the varint prefix directly and parse the bounded body via the public span-based `ParseFrom(byte[],offset,length)` — zero copy, zero stream allocation, and correct across multiple buffered messages. |
| `core/src/Server/ProtocolBuffers/Utils.cs:57` | cleanup | ✅ done | Replaced with a named `ReadChunkSize` constant. Also reworked the sibling stream/handshake read path to read straight into the `DynamicBuffer` (new `Reserve`) and parse the bounded body with `MergeFrom(byte[],offset,length)` — no per-call buffer or stream allocation. |
| `core/src/Server/WebSockets/ConnectionRequest.cs:36` | cleanup | ✅ done | Now accumulates the handshake across reads until the `\r\n\r\n` header terminator arrives (leaving the attempt pending), with a timeout, mirroring the protobuf server's partial-request handling. |
| `core/src/Server/WebSockets/RPCServer.cs:74` | cleanup | ✅ done | Replaced with a shared `Request.QueryParameter` helper that finds the parameter in any position and percent-decodes it. |
| `core/src/Server/WebSockets/StreamServer.cs:66` | cleanup | ✅ done | Same helper, used for the stream-server client-id. |
| `core/src/Service/KRPC/KRPC.cs:248` | **api** | deferred | `RemoveStream(ulong id)` should take a `Stream` object, not a raw `ulong`. Breaking wire/API change — fold into the Protocol Improvements work (issue #906) rather than doing standalone. |

## 2. Server plugin — UI

**Done.** Two real fixes and two documented rationales.

| File:line | Disposition | Status | Note |
| --- | --- | --- | --- |
| `server/src/Addon.cs:15` | cleanup | ✅ documented | The statics are deliberate: a new addon instance is created on every scene change (`KSPAddon.AllGameScenes`, `once: false`), so the config, server core and button textures must be static to survive the switch. TODO replaced with that rationale. |
| `server/src/UI/GUILayoutExtensions.cs:181` | cleanup | ✅ fixed | The GUI-space→screen conversion differenced `Input.mousePosition` against the event's mouse position — only correct when the two agree (true when a real mouse is over the button, which is why it worked in practice). Replaced with `GUIUtility.GUIToScreenPoint`, which converts exactly via the GUI clip stack. Verified in-game by instrumentation: the new form returned exactly window-origin + button offset while the old formula was off by 960 px in the headless environment (mouse-position mismatch). |
| `server/src/UI/OptionDialog.cs:59` | cleanup | ✅ fixed | The NRE catch replaced with Unity's lifetime check (`popup != null` reports a destroyed object as null), skipping the Destroy for a dialog already removed by other UI logic. |
| `server/src/UI/Window.cs:114` | cleanup | ✅ documented | The spacer is a necessary layout compensation: the title font scales with `UI_SCALE` (see `OnGUI`) but the skin's window style reserves a fixed-height title area. FIXME replaced with that rationale; a metric-derived height would need visual verification to tune and the constant is behaviorally established. |

## 3. SpaceCenter service — source

### 3a. Object lifetime / memory management (cluster → issue #771)

These all say "delete the object" / "need memory management" and are exactly the leak the
ObjectStore-GC work ([issue #771](https://github.com/krpc/krpc/issues/771), [PR #894](https://github.com/krpc/krpc/pull/894)) is meant to
solve. **Do not fix piecemeal** — they resolve as a set once weak-ref + event-sweep GC lands.

| File:line | Note |
| --- | --- |
| `service/SpaceCenter/src/Services/Node.cs:14` | "need to perform memory management for node objects". |
| `service/SpaceCenter/src/Services/Node.cs:239` | "delete this Node object". |
| `service/SpaceCenter/src/Services/Control.cs:808` | "delete the Node objects". |
| `service/SpaceCenter/src/Services/Parts/Force.cs:65` | "delete the object". |
| `service/KerbalAlarmClock/src/Alarm.cs:175` | "delete this object" (same class of leak, KAC service). |

### 3b. Correctness / precision

**Done.** Verified in-game.

| File:line | Disposition | Status | Note |
| --- | --- | --- | --- |
| `service/SpaceCenter/src/ExtensionMethods/GeometryExtensions.cs:245` | **bug** | ✅ documented | Not fixable the obvious way: switching to KSP's double-precision `QuaternionD.eulerAngles` throws at runtime (its native `Internal_ToEulerRad` binding is stripped from the game — built clean headless, blew up in-game). The single-precision `Quaternion` round-trip is a necessary workaround; the FIXME was replaced with that explanation. A true double-precision fix would mean hand-rolling Unity's ZXY euler math with singularity handling, for a sub-degree gain on values returned to clients as float — not worth the autopilot risk. |
| `service/SpaceCenter/src/ExtensionMethods/GeometryExtensions.cs:281` | **bug** | ✅ documented | Same, `QuaternionFromEuler` via `QuaternionD.Euler` / `Internal_FromEulerRad`. |
| `service/SpaceCenter/src/Services/Parts/Wheel.cs:355` | **bug** | ✅ fixed | The "isn't working" was an unfinished, non-compiling stub (a stray `steering.steer` line). The field is read live in KSP's `GetSteeringResponseScale`, so wired it up as a plain get/set bool `SteeringAngleAuto` matching the sibling `SteeringEnabled`/`SteeringInverted`, registered in `doc/order.txt`, and added a round-trip test to `test_parts_wheel`. |
| `service/SpaceCenter/src/Services/Parts/Experiment.cs:86` | cleanup | ✅ documented | "Don't use private API!!!" — the reflection is necessary. Disassembling KSP 1.12's `ModuleScienceExperiment` shows every public entry point (`DeployExperiment`, `DeployAction`, `DeployExperimentExternal`) hardcodes `gatherData(showDialog: true)` — popping the results dialog and reporting failures as screen messages instead of exceptions — and the only `gatherData(false)` caller, `OnActive`, is gated on `useStaging && stagingEnabled` so it silently no-ops for most experiments. Reflecting the private `gatherData(false)` coroutine mirrors KSP's own staging path; the FIXME was replaced with that rationale. |
| `service/SpaceCenter/src/Services/Parts/RCS.cs:70` | **bug** | ✅ fixed | `Active` used `!ShieldedFromAirstream`, ignoring `rcs.shieldedCanThrust`. KSP's own `FixedUpdate` and `GetPotentialTorque` allow a shielded thruster to fire when `shieldedCanThrust` is set, so the gate is now `(!ShieldedFromAirstream \|\| rcs.shieldedCanThrust)`; this also corrects the RCS torque/force/acceleration availability that gates on `Active`. No regression in-game; the positive branch is not stock-testable (no stock RCS sets `shieldedCanThrust`) — verified against KSP's identical IL gate. |

### 3c. Performance

**Done.** Verified in-game: test_comms + test_flight + test_vessel + the
autopilot quick gate, 81 passed / 0 failed.

| File:line | Status | Note |
| --- | --- | --- |
| `service/SpaceCenter/src/Services/Vessel.cs:1064` | ✅ fixed | `AngularVelocity` did a `GetComponent<Rigidbody>()` per call. The vessel behavior is attached to the root part's game object (confirmed by disassembly: `AddComponent<Vessel>` on `part.gameObject`), so the vessel's rigidbody is the root part's cached `Part.rb` field. New `VesselExtensions.WorldAngularVelocity` reads it there; also applied to the eight other `GetComponent<Rigidbody>()` sites (ReferenceFrame ×4, AutoPilot, AttitudeController's per-tick reads ×2) — the hot paths benefit most. |
| `service/SpaceCenter/src/Services/Flight.cs:171` | ✅ fixed | `ReferenceArea` constructed a `SpaceCenter.Vessel` wrapper just to read `Mass`. The mass sum now lives in a `WetMass` vessel extension used by both `Vessel.Mass` and the reference-area calculation. |
| `service/SpaceCenter/src/Services/CommNode.cs:74` | ✅ fixed | `IsVessel` scanned every vessel in the game comparing `Connection.Comm`. A vessel's `CommNode` is constructed with the vessel's transform (confirmed by disassembly: `CommNetVessel` passes its own transform to the node ctor), so the vessel is read in O(1) via `node.transform.GetComponent<Vessel>()`, with the `Connection.Comm` identity check retained so stale nodes from a rebuilt network behave as before. |
| `service/SpaceCenter/src/Services/CommNode.cs:91` | ✅ fixed | Same, `Vessel` — both now share one lookup helper. |

### 3d. The multi-frame active-vessel hack (decouple / undock)

**Done.** Verified in-game.

| File:line | Status | Note |
| --- | --- | --- |
| `service/SpaceCenter/src/Services/Parts/Decoupler.cs:85` | ✅ done | Waited 10 frames after decoupling because KSP changes its mind about the active vessel. |
| `service/SpaceCenter/src/Services/Parts/DockingPort.cs:147` | ✅ done | Same 10-frame wait after undocking. |

Both were the same underlying KSP quirk and the same duplicated code. Factored into a shared
`PartSeparation.NewVessel` helper (`service/SpaceCenter/src/Services/Parts/PartSeparation.cs`) that
documents why the wait exists (KSP doesn't finalize the split on the event frame; the new vessel and
the active-vessel assignment settle over a few frames) and why ten frames; each caller supplies only
its own "separated" predicate. The decoupler path was unified from `.First()` to `.Single()` (a single
separation yields exactly one new vessel), confirmed by the in-game decouple tests. Staging's
`Control.PostActivateStage` looked similar but is a genuinely different pattern (waits on
`StageManager.CanSeparate`, returns many vessels) and was deliberately left alone.

### 3e. Cleanup / minor

**Done.** Verified in-game: test_parts_parachute + test_contracts +
test_node + test_parts_docking_port all pass; docs build green. The two new API surfaces
(`Parachute.SafeState`, the contract dates) need changelog entries in the pre-merge changelog
commit.

| File:line | Disposition | Status | Note |
| --- | --- | --- | --- |
| `service/SpaceCenter/src/Services/Parts/DockingPort.cs:373` | cleanup | ✅ fixed | `InvokeEvent` moved to a new `PartModuleExtensions` class, as the marker asked. |
| `service/SpaceCenter/src/Services/ReferenceFrame.cs:410` | cleanup | ✅ fixed | The "better way": the orbit-space→world-space offset correction is deliberate and stays (confirmed via disassembly that `getPositionAtUT` anchors on the body's current position, so the two spaces genuinely differ by a residual), but it now measures the offset on the **node's own vessel** (which the frame already tracks) instead of `FlightGlobals.ActiveVessel`, which gave a wrong correction for maneuver frames on non-active vessels. |
| `service/SpaceCenter/src/Services/SpaceCenter.cs:660` | feature | ✅ documented | The warp API is defined in terms of the active vessel (rails altitude limits, physics-warp fallback, `CanRailsWarpAt`), so it cannot simply be opened to the space-center/tracking-station scenes where KSP can also warp; that would need a vessel-independent API surface. TODO replaced with that rationale; widening is now a tracked proposal (see [`time-warp-outside-flight.md`](../issues/time-warp-outside-flight.md), needs issue). |
| `service/SpaceCenter/src/Services/Parts/Parachute.cs:185` | feature | ✅ implemented | New `Parachute.SafeState` + `ParachuteSafeState` enum (Safe/Risky/Unsafe/None) read from `ModuleParachute.deploymentSafeState`. Verified via disassembly that KSP updates the field every `FixedUpdate` regardless of the PAW (headless-safe, unlike #883/#889), computing the real state only in atmosphere while stowed/armed; also that KSP reports Unsafe for the first second after unpacking (`timeUnpacked` guard) — documented in the property docs and waited out in the test. Stock-only (`CheckStock`). |
| `service/SpaceCenter/src/Services/Contract.cs:260` | feature | ✅ implemented | `DateAccepted`/`DateDeadline`/`DateExpire`/`DateFinished` as UT seconds. Disassembly-confirmed semantics: accepted set on `Accept()`, expiry on `Offer()`, deadline at offer or accept depending on deadline type, zero defaults. Note the krpctest career save's auto-completed progression contract has no recorded finish time, so `DateFinished` is documented as zero when KSP didn't record it. |
| `service/SpaceCenter/src/Services/Contract.cs:261` | feature | ✅ stale, removed | Contract parameters have long been exposed (the `Parameters` property); the TODO was vestigial and was deleted. |

## 4. KerbalAlarmClock service

| File:line | Disposition | Note |
| --- | --- | --- |
| `service/KerbalAlarmClock/src/AlarmAction.cs:21` | cleanup | Uncertainty over the `KillWarp` vs `KillWarpOnly` distinction. Resolvable from the disassembled KAC DLL — fold into the KAC test/API completion work (tracked). |
| `service/KerbalAlarmClock/test/test_kerbalalarmclock.py:4` | **tracked** | "expand the KAC tests" — already the headline of the KAC & RemoteTech planned item. |

## 5. Client libraries — source

**Done, except one
deferred enhancement.** Lower-yield than the other clusters: most items were "is there a better way?"
musings on already-correct code, so it is two real fixes plus documentation.

| File:line | Disposition | Status | Note |
| --- | --- | --- | --- |
| `client/java/src/krpc/client/Encoder.java:31` | perf | ✅ fixed | Every encode method copied a freshly-built array into a `ByteString` via `copyFrom`; the arrays are never reused, so all 14 sites now use `UnsafeByteOperations.unsafeWrap`, removing a copy per encoded value. |
| `client/cpp/src/client.cpp:71` | perf | ✅ fixed | The `ProcedureCall` overload copied the call field by field (dropping any new field). The `const&` input makes a copy unavoidable, so it uses `CopyFrom` — correct and future-proof. |
| `client/python/krpc/streammanager.py:206` | cleanup | ✅ documented | The bare-except is the intended clean-exit-on-close path for the stream update thread; FIXME replaced with that rationale. |
| `client/csharp/src/StreamManager.cs:149` | cleanup | ✅ documented | Same clean-exit-on-close idiom (connection-closed exceptions end the thread). |
| `client/csharp/src/StreamManager.cs:152` | cleanup | ✅ documented | Second site of the same. |
| `client/java/src/krpc/client/StreamManager.java:111` | cleanup | ✅ documented | Same clean-exit-on-close idiom. |
| `client/cpp/include/krpc/object.hpp:21` | cleanup | ✅ documented | The public fields are a permanent constraint (encoder/decoder need them; `friend` would create a circular dependency), not a to-do. |
| `client/lua/krpc/init.lua:25` | cleanup | ✅ documented | **Not a bug** (the original "bug" call was wrong): the `and` guard is correct — OK is the protobuf default, so status reads as nil and the guard makes only a present, non-OK status an error. FIXME replaced with that explanation. |
| `client/python/krpc/types.py:623` | **bug** | ✅ fixed | `WrappedClass` injected the client onto the wrapped class for static-method calls. With pre-generated stubs the class object is shared across clients, so the last client to touch a given class won the `_client` slot — a genuine multi-client bug that routed static calls to the wrong connection. Fixed so that each client now gets its own subclass of the wrapped class carrying its own `_client`, cached weakly per client, so nothing is written onto the shared class; a regression test (`TestWrappedClass`) fails if the client is shared. Covers the `service.Foo.static_method()` path; the rarer `instance.static_method()` path (the `StaticMethod` descriptor) is a separate mechanism left as-is. |
| `client/python/krpc/client.py:262` | enhancement | ✅ implemented | Server error tracebacks now end at the call site. Spec that resolved the "debatable value" concern: only exceptions built from server error responses are trimmed (marked by `_build_error`, checked by `krpc.error.is_server_error`) — for those the client frames are pure noise since the real trace is the server stack trace in the message; client-side failures keep full tracebacks. CPython appends every frame an exception unwinds through, so the trim lives at the outermost stub frame: the clientgen template stubs, `_construct_func` dynamic stubs (now named `def`s compiled with a `<krpc:Service.Procedure>` filename instead of anonymous `<string>` lambdas), and the deprecation wrapper each catch and re-raise marked exceptions `with_traceback(None)`, leaving the caller's frame plus one stub frame. Stream accessors re-raise stored server errors from a clean traceback, which also stops repeated stream accesses accumulating the previous raise's frames. Regression tests in `test_traceback.py` cover both stub paths (the `client_base` target runs the suite dynamically), the untrimmed client-side path, and the stream case. |

## 6. Client libraries — tests (mostly disabled/limitations)

**Done.** The two C++ re-enables each uncovered a real client bug; the Lua
one was implemented as new tests; the rest were reworded or resolved.

| File:line | Disposition | Status | Note |
| --- | --- | --- | --- |
| `client/cpp/test/test_stream.cpp:275` | test | ✅ fixed | The three `wait_for_stream_update` tests were disabled in 2018 over unfixable flakiness. Root cause was a real client bug: the update thread called `notify_all` without holding the condition mutex, so notifications could be lost (an abandoned earlier attempt was circling this). Fixed to match the Python client's discipline, and the tests re-enabled in the shape of Python's enabled equivalents (start the stream while holding the condition, synchronize on an update boundary before reading the baseline). Full suite passes repeated runs. |
| `client/cpp/test/test_stream.cpp:470` | test | ✅ fixed | `test_stream_stop_while_frozen` also hid a real client bug: `freeze_streams` was only acknowledged when the next stream update message arrived, so it blocked forever with no started stream (the test predates deferred stream start, which turned its stream into one that never produces updates — matching the 2018 disable date). The update thread now acknowledges freezes from the receive loop's timeout path; test re-enabled verbatim. |
| `client/lua/krpc/test/test_client.lua:247` | test | ✅ implemented | The "disabled tests" were Python code pasted as a porting note, a decade stale. Ported the four missing member-introspection tests to Lua (KRPC service, TestService, TestClass, TestEnum + values) with a helper that enumerates public members through the penlight class structure. Expected sets follow Lua conventions (get_/set_ properties, no exception classes). One pre-existing enabled `test_client_members` was left as-is. |
| `client/lua/krpc/test/test_client.lua:141` | test | ✅ reworded | Language limitation (Lua discards excess arguments); FIXME reworded to a plain comment and the dead commented asserts removed. |
| `client/java/test/krpc/client/StreamTest.java:71` | test | ✅ reworded | Language limitation (no default parameters); FIXME reworded. |
| `client/csharp/test/ServerTestCase.cs:19` | cleanup | ✅ resolved | The `Connection.Dispose` in teardown is ordinary per-test resource cleanup, not a Mono workaround — the obsolete apologetic comment was simply removed, keeping the call. |
| `core/test/Server/TestClient.cs:6` | cleanup | ✅ reworded | Hand-rolled fake is the standard answer to mocks lacking equality; TODO reworded to state that rationale. |
| `core/test/Utils/ReflectionTest.cs:10` | test | ✅ reworded | The fixture coupling is deliberate (the tests count types across the test assembly); TODO reworded to say so. |

## 7. Build & tooling

**Done.**

| File:line | Disposition | Status | Note |
| --- | --- | --- | --- |
| `tools/krpctools/krpctools/clientgen/python.py:401` | **bug** | ✅ fixed | Genuine bug: the `<see cref="M:..."/>` member translation used lowerCamelCase (copied from the Java generator) instead of the Python client's snake_case. Fixed to `snake_case`, matching the C++ generator and `parse_plain_cref_member`. |
| `tools/build/pkg.bzl:22` | **bug** | ✅ fixed | The exclude matcher silently never matched a trailing-`*` pattern and early-returned on an exact pattern before checking the rest. Rewrote it to handle exact / `*suffix` / `prefix*` / `*mid*` and test every pattern. (The `**/*.lib.cs` exclude that looked broken actually uses Bazel's native glob, not this function.) |
| `tools/build/sphinx.bzl:105` | cleanup | ✅ fixed | Re-added `-W` (warnings as errors). It failed because `spelling_ignore_contributor_names` made sphinxcontrib-spelling scan git history, which only warns in the repo-less sandbox and added nothing; disabled it (names go in `dictionary.txt`). Added `set -o pipefail` so `-W`'s exit code survives the pipe to `tee`, which also makes any misspelling fail the build. Verified both directions. |
| `tools/build/sphinx.bzl:98` | cleanup | ✅ documented | The dictionary is copied because sphinxcontrib-spelling needs a writable regular file and Bazel stages read-only symlinks — a necessary workaround; the FIXME was replaced with that rationale. |
| `tools/build/client_test.bzl:52` | cleanup | ✅ documented | The `sleep 1` covers the socat/PTY serial link not being ready the instant the server reports started; there is no readily observable readiness signal, so the FIXME was replaced with that rationale. |
| `tools/krpctools/krpctools/docgen/lua.py:75` | cleanup | ✅ documented | Reference shortening is a deliberate no-op because sphinx-lua cannot resolve the shortened form the other domains use; the FIXME was replaced with that rationale. |

## 8. SpaceCenter integration tests — gaps & workarounds

The largest cluster. Most are "improve this test" / "why is this wait needed" / "implement this
test" markers. They don't block anything but represent real coverage and hygiene debt. Suggested
grouping into a single "SpaceCenter test hardening" pass, **except** the autopilot ones which belong
to the aero-extension effort.

### 8a. Autopilot (→ aero-extension, already tracked)

| File:line | Note |
| --- | --- |
| `test_autopilot.py:1678` | "the autopilot does not yet model aerodynamic control". |
| `test_autopilot.py:1736` | Residual from the `disable_control_surfaces` TODO above. |
| `test_autopilot.py:1780` | Small oscillation after a 5° pitch — likely aero-surface related. |
| `test_autopilot.py:1805` | Large continuous slews still flaky in the floored regime. |

These are covered by the AutoPilot aero-extension / asymmetric-actuator planned work; no separate
action.

### 8b. Missing or stubbed tests

**Done.** Verified in-game. Five implemented, three resolved as documented
limitations — and one uncovered a server defect, fixed along the way.

| File:line | Status | Note |
| --- | --- | --- |
| `test_spacecenter.py:42` | ✅ implemented | `launchable_vessels`: staged VAB craft present, stock SPH craft present (the save includes KSP's stock craft — e.g. Aeris 4A), unknown directory yields `[]` not an error. |
| `test_camera.py:93` | ✅ implemented | `TestCameraIVA` enabled: the camera test base was split so distance tests only apply to modes that have a camera distance (the IVA camera throws server-side); pitch/heading sweeps run within the IVA limits. Placed before the deliberately-last camera-switch class. |
| `test_contracts.py:188` | ✅ documented | Failing a contract needs a deadline to expire in flight (no RPC fails one directly; time warp is flight-scene only). The vessel-independent-warp planned item would make this cheap; until then the test checks the list reads back empty. |
| `test_control.py:175` | ✅ implemented | `test_sas_mode_with_target` on the active vessel (target/anti-target with the Mun targeted). Mixin comment explains why the non-active class can't have it: targets are per-vessel and only the active vessel's is settable. |
| `test_control.py:191` | ✅ implemented | `test_speed_mode_with_target`, same shape. |
| `test_node.py:66` | ✅ implemented + **server fix** | Enabling the skipped assertion exposed a real defect: after `Control.RemoveNodes` (or manual UI deletion, or removal via another wrapper), stale `Node` objects silently read/wrote the detached maneuver node — only `Node.Remove()`-then-access threw. All `Node` members now validate the node is still in the vessel's flight plan (`SafeNode` guard) and raise a typed `InvalidOperationException`; the store-lifetime half stays with #771. Behavioral change → changelog entry needed. |
| `test_parts_wheel.py:175` | ✅ documented | Verified against GameData: every stock wheel has a suspension module, so `has_suspension`'s negative path is untestable with stock parts. |
| `test_parts_control_surface.py:158` | ✅ documented | `GetPotentialTorque` is zero without airspeed, so the authority-limiter scaling needs a vessel in atmospheric flight; belongs with the aero-extension work if ever automated. |

### 8c. Test quality / accuracy questions

**Done.** Verified in-game (72 tests over body/spacecenter/parts, 0 fail).
Every question turned out to have a discoverable answer; three items became genuinely stronger
tests.

| File:line | Status | Note |
| --- | --- | --- |
| `test_body.py:228` | ✅ explained | The 100 m delta is ~1e-9 relative at the largest orbital radii — the transform chain subtracts near-equal double-precision world positions, which limits achievable precision. |
| `test_body.py:260` | ✅ explained | The comparison models the moon's motion as circular and equatorial; the 500 m/s delta covers the test's own model error for eccentric/inclined moons, not transform error. |
| `test_body.py:269` | ✅ improved | Identity check now covers the scalar component too, allowing for quaternion sign ambiguity (q ≡ −q). |
| `test_body.py:272` | ✅ improved | New check: a body's rotation relative to its non-rotating frame is a pure y-axis rotation, since stock bodies have no axial tilt. |
| `test_spacecenter.py:203` | ✅ explained | The "sometimes large difference" is inter-RPC time skew: each transform evaluates on its own physics tick and Kerbin moves at ~9.3 km/s in the Sun's frame, so the two positions embed slightly different times. |
| `test_spacecenter.py:206` | ✅ improved | New round-trip test with norm preservation. |
| `test_spacecenter.py:237` | ✅ improved | New rotation round-trip test (unit norm, sign-normalized). |
| `test_spacecenter.py:245` | ✅ improved | The specific test the TODO asked for: a point at rest on Kerbin's equator moves at ω·R in the non-rotating frame, proving rotational velocity is included. |
| `test_parts_part.py:256` | ✅ answered | Docking ports are stageable — they carry a staging icon and activating their stage decouples them (`Part.Stage` keys on `hasStagingIcon`), so a stage number is correct. |
| `test_parts_part.py:392` | ✅ answered | The 10 kg above dry mass is the intake's IntakeAir resource (2 units × 5 kg, confirmed in the part config); now also asserted via `part.resources.names`. |

### 8d. Mysterious / vestigial waits (relates to the deferred-state audit)

| File:line | Note |
| --- | --- |
| `test_spacecenter.py:463` | `wait(1)` — "why is this wait needed?" |
| `test_spacecenter.py:482` | `wait(1)` — "why is this wait needed?" |
| `test_spacecenter.py:496` | `wait(1)` — "why is this wait needed?" |
| `test_parts_part.py:15` | Wait needed to allow dynamic data to settle. |
| `test_parts_control_surface.py:14` | Wait needed for available-torque calculations to settle. |
| `test_parts_engine.py:265` | Must activate the engine for the assertion to hold. |
| `test_vessel.py:306` | Must run the engines to update their has-fuel status. |
| `test_parts_launch_clamp.py:15` | "improve this test". |

The unexplained-`wait()` items are exactly the vestigial-wait cleanup called out in the deferred-state
RPC audit ([`services/deferred-state-rpc-audit.md`](services/deferred-state-rpc-audit.md)); fold them into that follow-up.

### 8e. Duplicated test helpers

**Done.** Verified in-game (both files, 21 passed). The duplicated
`assert_resources_equivalent` now lives in a shared `resources_equivalence.py` module in the test
directory — deliberately **not** hoisted into `krpctest` (a separately-versioned published package
is the wrong home for SpaceCenter-specific test logic). Import mechanics: the test directories are
namespace packages, so the helper is imported by its fully-qualified name
(`service.SpaceCenter.test.resources_equivalence`), made resolvable by adding `pythonpath = .` to
`pytest.ini`; fully-qualified imports avoid the cross-service basename collisions that forced
importlib mode in the first place. The helper's headless self-test stays in `test_resources.py`
(pytest only collects `test_*` files) and imports the shared copy. This establishes the pattern for
any future shared test helpers.
