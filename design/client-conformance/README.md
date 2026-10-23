# Client conformance

**Status:** proposal (2026-10-22), planned for 0.8 as
[#1123](https://github.com/krpc/krpc/issues/1123). The single connection and request ids phase 1
are built, which this work waited for. Facts below were surveyed on the single connection branch
(before its PR). Re-check them when a phase starts.

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
| [generation.md](generation.md) | Part 1: generating exception tables, constants, type tables and the service list |
| [defects.md](defects.md) | Open client defects from the audits, each with the requirement that catches it |

## Problem

Every client hand-writes its runtime: connection, codec, streams, events, errors and threading.
Only the service stubs are generated. Each feature costs one port per client, and the ports drift.

- **The stream and event tests are ported by hand.** Python, Java, C# and C++ each have 1,300 to
  1,500 lines of stream tests (67 to 83 tests) and 400 to 560 lines of event tests. The names drift
  (Java `testInerleaved`, C# mixing `TestWait` with sentence names), and each client has tests the
  others lack.
- **Codec vectors are copied and disagree.** The NaN vectors are `...7f` in Python, Java, C++ and
  cnano, and `...ff` in C#, Lua and core. The Lua copy carries the comment "should be ...7f ??".
- **Exception mapping disagrees.** Python and C# map 11 server exceptions to native types, Java
  maps 10 with different picks, C++ maps none.
- **Error messages differ.** C# adds a trailing space, C++ drops the stack trace, and Lua and cnano
  prefix `Service.Name:`.
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
| Python is not the reference | The spec is. Where clients disagree, the spec picks, and the losing clients get expected failures until fixed. |
| Thread safety ([#427](https://github.com/krpc/krpc/issues/427)) | Answered by the spec's threading page, and pinned by the `threads` profile. |
| `TestService` | Renames and removals wait until the per-client comms tests are deleted (phase C5), so each moves once. Additions land with the tests that need them. |

## Sequencing

| Step | Work |
| --- | --- |
| 1 | Land the single connection and request ids. |
| 2 | Part 1 phases G1, G3, G4 and G5, in any order. G2 was blocked on the single connection removing `stream_port` and the paired socket paths, and is now free. |
| 3 | Conformance phases C0 to C6. |
| 4 | 1.0 additions ([#903](https://github.com/krpc/krpc/issues/903), [#251](https://github.com/krpc/krpc/issues/251), [#905](https://github.com/krpc/krpc/issues/905), [#898](https://github.com/krpc/krpc/issues/898)), each with conformance tests. The suite pins the client tolerance rules that keep them additive ([protocol-compatibility.md](../protocol-compatibility.md)). |

Part 1 and Part 2 can overlap. G1 must precede the error tests in C3, and G2 the message format
test.

## Phases

| Phase | Scope |
| --- | --- |
| C0 | Spec skeleton in `krpc` (`doc/src/communication-protocols/client-spec/`), with the requirement labels from [spec.md](spec.md). Draft the streams and connection pages from current behavior. |
| C1 | Harness: `testee.proto`, the driver and its fixtures, the scripted server, the Bazel macro, the Python testee. Port the connection tests and about ten stream tests. |
| C2 | Java testee, the `threads` profile, and the first expected-failures file. |
| C3 | C# and C++ testees. Then calls, values, errors and objects, the codec vectors, events and server-side functions. `ConformanceService` and the `TestService` additions land here. |
| C4 | Lua and cnano testees, without the stream, event, function or thread profiles. cnano adds the `serialio` transport. |
| C5 | Delete the per-client tests the suite replaces ([client-tests.md](client-tests.md)), then the `TestService` renames and removals. |
| C6 | Document the testee protocol, and ship the driver with the TestServer archive for third-party clients. |

Each phase merges on its own. A spec page is published only once its tests run.

## Open questions

- **Python codec in the driver.** The driver decodes testee values with the Python codec. The
  codec vectors pin that codec, so this looks safe. Confirm when C1 lands.
- **Testee lifetime.** One process per test isolates failures, one per session is faster. The
  scripted-server tests need a fresh connection each, not a fresh process.
- **Transports per target.** Every testee over TCP. The local socket only for the connection page,
  as the transport sits below everything else.
- **Short timeouts.** The stall timeout is 30 s and the handshake timeout 5 s. The tests need a
  testee knob for both, or they run for minutes. The spec should say clients make both settable.
- **Server-side function tests.** Each client builds functions in its own idiom: Python compiles
  source, C# compiles LINQ, C++ and Java build `KRPC.Expression` calls by hand. The proposal: the
  suite sends neutral expression trees, built through each client's `Expression` stubs, and the
  builders keep their own per-client tests.
- **Decisions the audits left open**, listed in [defects.md](defects.md) "Decisions": Lua streams,
  C++ dropped stream handles, the Python exception classes, Java's exception picks, and C++ native
  exceptions.
