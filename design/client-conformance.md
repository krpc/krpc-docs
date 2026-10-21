# Client conformance: design sketch

**Status:** deferred sketch (2026-10-12), planned for 0.8 as
[#1123](https://github.com/krpc/krpc/issues/1123). It starts after 0.7.0 is released and the
single connection and request ids have landed; see "Sequencing against #906". The facts below were
surveyed on main at #1121, with #1122 (stream and event improvements) and the server-side
functions stack checked on top. Re-check them before detailing this plan.

## Problem

Every kRPC client hand-writes its runtime: connection, codec, streams, events, errors and
threading. Only the service stubs are generated. Each new feature costs one port per client, and
the clients' semantics drift apart:

- **Stream tests are ported by hand.** Python `test_stream.py`, Java `StreamTest.java`, C#
  `StreamTest.cs` and C++ `test_stream.cpp` are the same scenarios. They grow from about 600
  lines each on main to 1,400-1,500 lines each with #1122. The names have drifted (Java uses
  `testNoServerOnRpcEndpoint` and `ArgumentOutOfBounds`).
- **Codec hex vectors are copied** into six clients and core. They have already drifted: the
  float NaN vector is missing from C# and core.
- **Exception mapping lives in four hand-written tables that disagree.** Server-side functions
  raise the server's `KRPC` exceptions from 7 to 16, and the Java and Python tables grow to match
  by hand.
- **Error messages are formatted differently.** C# adds a trailing space, and C++ drops the
  server stack trace.
- **Python was the reference, and that hid bugs.**
  [client-api-parity-audit.md](client-api-parity-audit.md) found that treating
  Python as the reference had left it the least examined client.

## Prior art

| Project | Mechanism |
|---|---|
| protobuf | One conformance runner sends commands over stdin/stdout to a small testee per language. Each language keeps a checked-in failure list. Python, Ruby and PHP share the upb C core. |
| gRPC | A shared C core under most languages. Named interop cases are specified in prose, and every client runs against every server. |
| MongoDB drivers | One server and many drivers. A spec repo holds numbered requirements plus YAML tests in a unified format, and each driver writes one runner. |
| Smithy / AWS SDKs | Clients and protocol tests are generated from one model. |

A reference implementation alone makes the spec "whatever the reference does", including its
accidents. kRPC takes three ideas from the table: a written spec, shared tests run against every
client, and more generated code.

## Decisions

- **The suite is driven from Python, not from YAML.** YAML suits MongoDB because each driver runs
  its test data in-process. A Python driver keeps assertions, timing and sequencing in one place.
  It also fits the existing pytest and Bazel tooling. The cost is a process boundary: callbacks
  and threads become commands and notifications.
- **The spec is published in `krpc`**, in the protocol docs. `krpc-docs` is scratch space, and
  the spec is the ground truth.
- **Third-party clients can run the suite later.** The testee protocol is therefore designed to be
  stable and versioned from the start.
- **Generation (Part 1) lands before the suite (Part 2).**
- **Single connection and request ids land before the suite.** See "Sequencing against #906".

## Sequencing against #906

The suite pins the runtime behavior that clients expose. Each open item in meta-issue #906 either
changes that behavior or adds to it. Only the changing items need to land before the suite.

**Why most tests survive a protocol change.** Testees drive the public client API, so a test
never sees the wire. Moving to a single connection forces rewrites in two places only:

- **Connection tests**, and the `Connect` command's settings.
- **Threading tests.** The current threading behavior changes on purpose. For example, a yielding
  RPC holds Python's `_rpc_connection_lock` and blocks every other thread.

| Item | Changes existing semantics? | Before the suite? |
|---|---|---|
| Single connection ([single-connection.md](protocol/single-connection.md), no issue) | Yes: the connection setup, and a demultiplexing reader in every client that has streams | **Yes** |
| Request ids ([request-ids.md](protocol/request-ids.md), no issue, not listed on #906) | Yes: pipelining, async call APIs, a yielding RPC no longer blocks the connection, desync detection | **Yes, together with single connection** |
| #902 stream removal, #877 stream invalidation | Yes | Already in 0.7 |
| #903 batching, fire-and-forget, reverse streams | No, it adds API. Reverse streams need the single-connection envelope. | No |
| #251 tick control and transactions | Mostly additive. `HoldTick` is the stopgap, and the protocol design is still open. | No, unless it joins a single v1.0 wire break |
| #905 inheritance, #898 constructors | No. They change the generated stub surface. | No |
| #899 more communication protocols | No. Transports sit below the testee. | No |

**Single connection and request ids land as one piece of work.** Both need the same
demultiplexing reader, so doing them separately writes it twice, in four clients.

**v1.0 is split.** The wire break is 0.8 alone, so only the reader rework precedes the suite. #903
and #251 then land in 1.0 as additions, with tests. The suite pins the client tolerance rules that
keep them additive ([protocol-compatibility.md](protocol-compatibility.md)).

**Part 1 is mostly independent of #906.** The exception is G2: its constants include
`stream_port`, `stream_path` and the paired socket paths, which the single connection removes.

### Order

1. Release 0.7 with the stream and event improvements and server side functions.
2. Part 1 phases G1, G3, G4 and G5.
3. Single connection and request ids.
4. G2, then the conformance suite (Part 2, phases C0-C6).
5. #903, #251, #905 and #898 as additions, each with conformance tests.

**Alternative order:** build the suite before step 3, so that the six-client reader rework runs
against it. That rework is the lockstep change most likely to drift between clients. The cost is
rewriting the connection and threading tests afterwards. The rest of the suite survives.

## Part 1: generate more than stubs

The inputs are the servicedefs JSON (`core/src/Service/Scanner/*Signature.cs`),
`protobuf/krpc.proto` and clientgen (`tools/krpctools/krpctools/clientgen/`, `lang/*.py`). The
cnano `encoder.c` cog blocks (`tools/build/cog.bzl`) are prior art for in-source generation.

| Phase | Change | Replaces |
|---|---|---|
| G1 | Emit `KRPCException.MappedException` into the servicedefs JSON (`ExceptionSignature`). Generated KRPC stubs register the native exception from a per-language table in `lang/*.py`. | Python `types.py` `EXCEPTION_TYPES`, C# `Connection.cs`, Java `Connection.java`. C++ gets a mapping. |
| G2 | One protocol-constants data file holding the default address and ports, the local-socket path rule, and the error-message format. Generate a constants module for each client and for the server. | Seven copies of the local-socket path rule, the port literals, and the C# and C++ format drift. |
| G3 | Goldens for the KRPC service: a `KRPC.Core.json` fixture and `clientgen-KRPC-<lang>.txt`. | Core stub output that nobody reviews today. |
| G4 | Type-code tables and numeric limits, generated from `krpc.proto` `TypeCode` plus a small map. This covers Python and Lua `VALUE_TYPES`/`MESSAGE_TYPES`, `limits.lua` and the Java tuple-arity switch. | Hand-copied tables in `types.py`, `types.lua` and `Encoder.java`. |
| G5 | One Starlark list of services, driving every `clientgen_*` target and Python `services/__init__.py`. | The 11-service list repeated in each client BUILD and in the csproj. |

Notes:

- **G2 changes behavior.** The C# and C++ error-message formats change. The Part 2 spec decides
  which format is correct.
- **Standalone bug, out of scope:** `server/src/UI/EditServer.cs` defaults `stream_port` to 50000.
  This needs its own PR.
- **Lower priority:**
  - shared test vectors for snake_case and name parsing (`attributes.py` vs `attributes.lua`)
  - moving the doc parsing in `service.py` and `service.lua` onto `docparser.py`

## Part 2: conformance suite and spec

### Architecture

```
pytest driver (Python) --stdin/stdout, length-delimited protobuf--> testee (one per client)
       |                                                                 |
       +-- control connection (Python client) --> TestServer <-----------+  (client under test)
```

- **The driver** is a pytest plugin in `conformance/driver/`. It has three fixtures:
  - `server` launches TestServer. Factor the launch and address scraping out of
    `tools/build/run_client_test.py` and `tools/benchmarks/testserver.py` into one module.
  - `testee` spawns the client's testee binary.
  - `control` is a Python client connection that sets and observes server state.
- **The testee** is a thin command interpreter. It runs each command through its client's public
  API and reports the outcome. It does no checking.

### Testee protocol

The protocol is `conformance/testee.proto`, versioned. It uses kRPC-style varint
length-delimited framing, which every client already implements.

- **Hello** reports the client name, the protocol version, the profiles (`core`, `streams`,
  `events`, `expressions`, `threads`, `named-args`) and the supported transports.
- **Commands** each carry an `id` and an optional `thread` name. The testee runs each command on
  the named worker thread and replies asynchronously, keyed by `id`.
  - This lets a test say "wait on thread A, remove on thread B".
  - That is the shape of the recent Python and Java first-call deadlocks.
- **The command set:**
  - `Connect`, `Close`
  - `Invoke{target?, member, args}`, where `member` is the wire procedure name
  - `AddStream{invoke}`, `SetRate`, `Get`, `Wait{timeout}` (returns whether the stream updated),
    `AddCallback`, `AddEndCallback`, `RemoveCallback`, `Remove`. A stream starts when added
    (#1122).
  - `AddEvent{invoke | expression}` and the event lifecycle, including end callbacks
  - `Compare{a, b}` for object equality and hashing
  - `Encode{type, value}` and `Decode{type, bytes}`, which replace the copied hex vectors
- **Notifications** carry callback firings: `Notification{callback, value}`.
- **Values** cross the boundary as kRPC wire bytes plus a `krpc.Type`, and the driver decodes them
  with the Python codec. The codec vectors pin that codec too.
- **Errors** cross as `{kind: rpc|stream|connection|encoding|timeout, service, name, message}`,
  plus the name of the native type the client raised. The driver checks that name against the G1
  table.
- **Dispatch is generated.** A new clientgen backend generates each testee's `Invoke` and
  `AddStream` dispatch from the service definitions.
  - Testees call the real generated stubs and the idiomatic stream API: C# LINQ expressions, the
    Java reflection form, and so on.
  - Lua, and Python without stubs, dispatch through their runtime service objects.

### Spec

- **Location:** published under `doc/src/communication-protocols/client-spec/`, in the
  `communication-protocols.rst` toctree.
- **Pages:** connection, calls and errors, values, objects, streams, events, threading, and
  server-side functions.
- **Scope:** the wire format stays in `messages.rst`. The spec covers client-library behavior.
- **Requirement IDs:** each requirement is an RST-labeled item with a stable ID, e.g.
  `spec-stream-wait-wakes-on-remove`.
- **Requirement wording:** RFC 2119 MUST and SHOULD, under the krpc `CLAUDE.md` writing rules.
  Each requirement belongs to a profile.
- **Seed material:**
  - the A-J rubric in [client-testing.md](client-testing.md)
  - the parity audit's "Where the clients already agree" section
  - the stream and event ending rules from #1122: a final error result ends a stream, later
    reads and waits throw it, and event firings are counted per event object

### Suite layout and build

- **Tests** live in `conformance/tests/test_<feature>.py`. Each test is marked with its spec IDs
  and profile, and is skipped when the testee lacks that profile.
- **Expected failures** live in `conformance/expected-failures/<client>.txt`, enforced strictly as
  in protobuf. A listed test that passes fails the run, so every gap is either fixed or recorded.
- **The Bazel macro** is `conformance_test(name, testee, client, transports)`, modeled on
  `tools/build/client_test.bzl`. Each client BUILD instantiates it, and the targets join
  `//:test`.
- **A new `ConformanceService`** goes in TestServer, with its own servicedefs JSON so that testees
  get stubs for it. It fills the control gaps TestServer has today:
  - triggering an event on demand
  - settable watched values
  - timed blocking calls
  - forced disconnects

  `TestService` stays unchanged.
- **A coverage report** lists spec ID against client, built from the test results.

### Phases

| Phase | Scope |
|---|---|
| C0 | Spec skeleton, and the streams page drafted from current behavior. |
| C1 | Harness: `testee.proto`, the driver, the fixtures, the Bazel macro and the Python testee. Port about ten stream scenarios. |
| C2 | Java testee and the `threads` profile, with the first expected-failures file. |
| C3 | C# and C++ testees. Then events, server-side functions, calls and errors (rubric A-F and J), and codec vectors. |
| C4 | Lua and cnano testees, `core` profile only. |
| C5 | Delete the per-client tests the suite now covers. Keep idiom tests: C++ templates, Python `nonlocal`, LINQ. |
| C6 | Document the testee protocol, and ship the driver with the TestServer archive for third-party clients. |

### Open questions

- Driver-side decoding relies on the Python codec. Is that acceptable, given that the vectors pin
  the codec?
- Should each test get its own testee process, or should one process serve a session? The choice
  trades isolation against speed.
- Which transports should each conformance target run: TCP only, or the local socket too?
- How does a test describe a server-side function? Each client builds functions in its own idiom
  (Python lambdas, C# LINQ). A neutral expression tree is simple to send, but skips the client's
  builder, which is the part most likely to diverge.
