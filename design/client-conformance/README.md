# Client conformance

**Status:** in progress, planned for 0.8 as [#1123](https://github.com/krpc/krpc/issues/1123).
Proposed 2026-10-22 and reviewed 2026-10-23. C0 to C6 are built on a local branch, before their PR
([harness.md](harness.md) "Built in C1" to "Built in C5", [client-tests.md](client-tests.md) "Built in
C6"), and C7 is next. Client defects the
suite finds are recorded as expected failures, and fixed later as their own work. The single connection and request ids phase 1
are built, which this work waited for. Facts below were surveyed on the single connection and
client codegen branches (before their PRs). Re-check them when a phase starts.

This folder replaces three earlier docs: the conformance sketch (`client-conformance.md`), the
client testing standard (`client-testing.md`) and the client API parity audit
(`client-api-parity-audit.md`). Their history is in git. What they still decide is carried here.

| Doc | Covers |
| --- | --- |
| [README.md](README.md) | Problem, decisions, sequencing, phases, open questions |
| [spec.md](spec.md) | The requirement inventory: ids, levels, profiles, and the test that checks each |
| [harness.md](harness.md) | The driver, the testee protocol, the scripted server, Bazel, expected failures |
| [test-service.md](test-service.md) | `TestService` as it stands, the changes, and the new `ConformanceService` |
| [client-tests.md](client-tests.md) | What stays in each client's own suite, and what the suite replaces |
| [defects.md](defects.md) | Open client defects from the audits, each with the requirement that catches it |

Generating the exception mapping and the service list is a separate piece of work that lands
first: [client-codegen.md](../client-codegen.md). Its G1, G3 and G5 merged in
[#1172](https://github.com/krpc/krpc/pull/1172). G2 and G4 were dropped.

## Problem

Every client hand-writes its runtime: connection, codec, streams, events, errors and threading.
Only the service stubs are generated. Each feature costs one port per client, and the ports drift.

- **The stream and event tests are ported by hand.** Python, Java, C# and C++ each have 1,300 to
  1,500 lines of stream tests (67 to 83 tests) and 400 to 560 lines of event tests. The names drift
  (Java `testInerleaved`, C# mixing `TestWait` with sentence names), and each client has tests the
  others lack.
- **Codec vectors are copied and disagree.** The NaN vectors are `...7f` in Python, Java, C++ and
  cnano, and `...ff` in C#, Lua and core. The Lua copy carries the comment "should be ...7f ??".
- **Exception mapping and error messages disagreed** across the clients until client codegen G1.
  Nothing pins the fix, so the clients can drift apart again.
- **Coverage is uneven.** A null return from a non-nullable procedure, an unknown object id,
  special numeric defaults and named arguments are tested in Python only.
- **Python as the reference hid its own bugs.** The audit asked of every client "does this match
  Python?", which cannot find a Python bug. A later sweep of Python found 26. Two practices the
  audit had recorded as house style were shared defects, copied across clients.

## Prior art

| Project | Mechanism |
| --- | --- |
| protobuf | One runner sends commands over stdin/stdout to a small testee per language. Each language keeps a checked-in failure list. |
| gRPC | Named interop cases specified in prose. Every client runs against every server. |
| MongoDB drivers | A spec repo of numbered requirements plus YAML tests. Each driver writes one runner. |
| Smithy / AWS SDKs | Clients and protocol tests generated from one model. |

kRPC takes three ideas: a written spec, shared tests run against every client, and more
generated code. A reference implementation alone makes the spec whatever the reference does.

## Decisions

Settled earlier, and kept:

- **The suite is driven from Python.** A Python driver keeps assertions, timing and sequencing in
  one place, and fits pytest and Bazel. Callbacks and threads become commands and notifications.
- **The spec is published in `krpc`**, with the protocol docs. `krpc-docs` holds only this plan.
- **Third-party clients can run the suite later**, so the testee protocol is versioned from the
  start.
- **The single connection and request ids land first.** Done on its branch. The suite pins 0.8
  behavior, and only additive 1.0 work follows it.

New in this revision:

| Decision | Outcome |
| --- | --- |
| Requirement ids | `<area>-<name>`, where the name is the test's name. `streams-wait-timeout-short` is checked by `test_streams.py::test_wait_timeout_short`. See [spec.md](spec.md) "Naming". |
| Test names | Taken from the existing tests where one exists: the Python stream and event tests, which the other clients already mirror, and the client testing standard's catalog for the rest. |
| One requirement, one test | Variants (each scalar type, each member kind) are pytest parameters of that test. |
| Scripted server | The driver also hosts a scripted server, so the handshake, disconnect and compatibility rules are tested. Python's `ScriptedServer` and the C# and Java `StandInServer`s are the prior art. |
| Codec vectors | Move into the suite as `Encode`/`Decode` commands. A NaN must decode from either sign and encode to some NaN, which ends the vector drift. |
| Testee values | Cross as a `testee.proto` `Value` of plain protobuf fields, never as kRPC wire bytes. A codec bug that is symmetric in one client would otherwise cancel out in the testee. See [harness.md](harness.md) "Values". |
| Python is not the reference | The spec is. Where clients disagree, the spec picks, and the losing clients get expected failures until fixed. |
| Thread safety ([#427](https://github.com/krpc/krpc/issues/427)) | Answered by the spec's threading page, and pinned by the `threads` profile. |
| Testee lifetime | One process per test session, with a fresh `Connect` per test. The driver restarts a testee that crashes or times out. `Counter` counts per client, so a fresh connection starts from clean state. |
| Timeouts | The handshake and stall timeouts are `Connect` settings. The spec says clients SHOULD make both settable. |
| Timing | Tests order events through `ConformanceService` (`SetValue`, `Block`, `TriggerEvent`) in place of wall-clock sleeps where they can. Tests that still race the clock are marked `@timing` ([harness.md](harness.md)). |
| `TestService` | Renames and removals wait until the per-client comms tests are deleted (phase C6), so each moves once. Additions land with the tests that need them. |
| Defect rulings | Lua streams, the C++ dropped stream handle, waiting in a callback and Java stream creation are ruled in [defects.md](defects.md) "Decisions". |

## Sequencing

| Step | Work |
| --- | --- |
| 1 | Land the single connection and request ids. |
| 2 | Done in #1172. Client codegen G1, G3 and G5 ([client-codegen.md](../client-codegen.md)). Its exception tables and message format settle two client disagreements before the suite pins them. |
| 3 | Conformance phases C0 to C7. |
| 4 | 1.0 additions ([#903](https://github.com/krpc/krpc/issues/903), [#251](https://github.com/krpc/krpc/issues/251), [#905](https://github.com/krpc/krpc/issues/905)), each with conformance tests. The suite pins the client tolerance rules that keep them additive ([protocol-compatibility.md](../protocol-compatibility.md)). |

C0 to C2 can overlap with codegen. G1 must land before the first set's error tests, or they start
as expected failures in most clients.

## Phases

The harness and every testee come first, on a small first set of tests. Each area then grows on a
harness that already runs all six clients.

| Phase | Scope |
| --- | --- |
| C0 | Spec skeleton in `krpc` (`doc/src/communication-protocols/client-spec/`), with the requirement labels from [spec.md](spec.md). Draft the connection, calls and streams pages from current behavior. |
| C1 | Harness: `testee.proto`, the driver and its fixtures, the scripted server, the Bazel macro and the Python testee. The first set below passes for Python. |
| C2 | The Java, C#, C++, Lua and cnano testees on the first set, with the clientgen dispatch backend and the expected-failures files. Java proves the `threads` notifications, Lua and cnano the profile skips. |
| C3 | Calls, values, codec, errors and objects in full, with the `TestService` additions. |
| C4 | Streams and events in full, with `ConformanceService` and the `threads` profile. Also `calls-request-ids` and `objects-types-from-different-connections`, moved from C3, and the connection page's remaining tests. `events-custom-event` moves to C5 with the functions. |
| C5 | Server-side functions, and the `serialio` transport for cnano. |
| C6 | Delete the per-client tests the suite replaces ([client-tests.md](client-tests.md)), then the `TestService` renames and removals. |
| C7 | Document the testee protocol, and ship the driver with the TestServer archive for third-party clients. |

Each phase merges on its own. A spec page is published only once its tests run.

### First set

Fifteen tests, chosen to use each harness mechanism once: `Hello` and profile skips, `Connect`,
the scripted server, `Invoke`, `Value` conversion, errors, `AddStream`, `Wait` and callback
notifications. All use members `TestService` has today.

| Area | Tests |
| --- | --- |
| Connection | `connection-connect`, `connection-client-name`, `connection-close`, `connection-calls-after-close-raise`, `connection-refused` (scripted server) |
| Calls | `calls-procedure`, `calls-class-method` |
| Values | `values-scalar-arguments` (the five existing `...ToString` types), `values-string` |
| Errors | `errors-mapped-exceptions`, `errors-message` |
| Objects | `objects-equality` |
| Streams | `streams-procedure`, `streams-wait`, `streams-callback` (profile `streams`, skipped in Lua and cnano) |

## Open questions

- **Transports per target.** Every testee over TCP. The local socket only for the connection page,
  as the transport sits below everything else.
- **Server-side function tests.** Settled in C5: the driver builds functions with `Invoke`s of each
  client's `KRPC.Expression` stubs, with no tree format of its own. The builders (Python's
  compiler, C#'s LINQ) keep their own per-client tests.
