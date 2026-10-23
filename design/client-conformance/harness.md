# Harness

How the suite runs a test against a client. C1 built the driver, the scripted server, the Bazel
macro and the Python testee. C2 built the other five testees and the dispatch generators (local
branch, before its PR). `ConformanceService` does not exist yet.

### Built in C1

| Item | As built |
| --- | --- |
| Layout | `conformance/testee.proto`, `conformance/driver/` (plugin, testee process, scripted server, raw client, values, native tables), `conformance/tests/`, `conformance/expected-failures/<client>.txt`. The Python testee is `client/python/conformance/testee.py`. |
| Commands | Version 1 has only what the first set uses: `Connect`, `Close`, `Invoke`, `AddStream`, `Get`, `Wait`, `AddCallback`, `Compare`. The rest are added with their tests. |
| Values | Scalars, string, bytes, null and `Object{handle, id}`. Each returned object gets a new handle, so two handles can name one object. Composites come with C3. The driver compares integers and floats by value, as Python cannot tell their wire types. |
| Errors | `native_types` is a list: every native type the error is an instance of. `status` and `reason` carry a refusal or a disconnect. |
| Native tables | `conformance/driver/natives.py`, keyed by the `Hello` client name. Kept apart from the clients, so a client's table change fails the suite. |
| Naming check | The plugin fails collection when a test's name does not match its first `spec` id. A stale expected-failures line also fails it. |
| TestServer launch | Factored out of `run_client_test.py` into `tools/build/serverprocess.py`. `tools/benchmarks/testserver.py` still has its own copy. |
| Bazel | `conformance_test(name, testee, expected_failures, transports)` in `tools/build/conformance.bzl`, one target per transport (`//client/python:conformance-tcpip`), in `//:test`. |
| Not built | The coverage report. The spec pages stay orphans until a page's tests run. |

### Built in C2

| Item | As built |
| --- | --- |
| Dispatch generators | `csharp-dispatch`, `java-dispatch`, `cpp-dispatch` and `cnano-dispatch` clientgen languages (`clientgen/dispatch.py`), left out of the `--help` list. `clientgen_dispatch` in `clientgen.bzl` declares them for `KRPC` and `TestService`. `TestService2` and the extension members are left out of the bundled definitions, so only the Python and Lua testees reach them. The fix is drafted as [test-service-full-definitions.md](../../issues/test-service-full-definitions.md). |
| Coverage | Members whose parameters and result are scalars, strings, bytes or objects. A nullable scalar, a collection, an enum, a struct or a message leaves the member out until C3 extends `Value`. cnano also leaves out bytes and nullable strings. |
| Testees | `client/<lang>/conformance/`. C# and Java are hand-written beside the generated half, C++ and cnano are C++ with a generated header per service, and Lua dispatches through its runtime service objects like Python. cnano's testee is C++ calling the C API, and links the full C++ protobuf for the testee protocol. |
| Profiles | Lua reports `core` and `defaults`, cnano `core`, so the stream tests skip. cnano builds for TCP/IP only. |
| Lua on Windows | The Lua target is off on Windows: Lua reads standard input in text mode there. |
| `errors-mapped-exceptions` | C# and Java raise the native type itself, with no service or name, so the test checks service and name only when the testee reports them. |
| Expected failures | 1 C#, 1 Java, 6 C++, 6 cnano, 9 Lua, each citing a new row in [defects.md](defects.md). |
| Lint | The C++ and cnano testees are clang-formatted but not clang-tidied, like the client tests. Filed as [#1177](https://github.com/krpc/krpc/issues/1177). |
| Java static streams | Broken and untested. The Java stub of a static method takes the connection first, so `addStream(<class>.class, name, connection, args...)` repeats it. The generated dispatch leaves it out, so streaming a static method raises "Method not found". The fix is in `JavaDispatchGenerator.stream`, with a test that streams a static method. No first set test does. |

```
pytest driver --stdin/stdout, testee.proto--> testee (one per client)
   |   |                                          |
   |   +-- control connection (Python client) --> TestServer <--+  client under test
   |                                                            |
   +-- scripted server <----------------------------------------+  (connection tests)
```

## Driver

A pytest plugin in `conformance/driver/`.

| Fixture | Does |
| --- | --- |
| `server` | Launches TestServer and scrapes its address. |
| `scripted_server` | A raw listener that plays a scripted exchange of `Message`s, for the handshake, disconnect and compatibility tests. |
| `testee` | Spawns the client's testee and reads its `Hello`. |
| `control` | A Python client connection that sets and observes server state through `ConformanceService`. |

- **TestServer launch** is factored out of `tools/build/run_client_test.py` (start, wait for
  `Server started successfully`, scrape `tcpip_port = N` or `localsocket_path = P`) and
  `tools/benchmarks/testserver.py` (the same scrape, and `socket_directory()` duplicated) into one
  module both use.
- **The scripted server** grows out of Python's `ScriptedServer` in `krpc/test/test_session.py`.
  The C# and Java `StandInServer`s cover the same cases (refused, malformed handshake response,
  ended by the server) and are deleted in C6.
- **Testee lifetime.** The `testee` fixture is session scoped: one process per session, a fresh
  `Connect` per test. The driver restarts a testee that crashes or misses a reply deadline, and
  fails the test it was running.
- **Timeouts.** A test that waits on the handshake or stall timeout sets it short through
  `Connect`.

## Testee protocol

`conformance/testee.proto`, versioned. Varint length-delimited framing, which every client already
implements.

**Hello** reports the client name, the testee protocol version, the profiles and the transports
([spec.md](spec.md) "Profiles").

**Commands** each carry an `id` and an optional `thread` name. The testee runs each command on the
named worker thread and replies asynchronously, keyed by `id`. A test can then say "wait on thread
A, remove on thread B", the shape of the deadlocks found in Python and Java. A testee without the
`threads` profile (Lua, cnano) gets no `thread`, and runs each command to completion in order.

| Command | Does |
| --- | --- |
| `Connect{transport, address, settings}`, `Close` | Connection, with the handshake and stall timeouts as settings |
| `Invoke{target?, member, args}` | A call through the generated stub. `member` is the wire procedure name |
| `Interrupt{thread}` | Interrupts a call in flight, where the language allows |
| `AddStream{invoke}`, `SetRate`, `Rate`, `Get`, `Wait{timeout?}`, `Remove` | Streams. `Wait` returns whether the stream updated |
| `AddCallback`, `RemoveCallback`, `AddEndCallback`, `RemoveEndCallback` | Callbacks, reported as notifications |
| `AddEvent{invoke or expression}`, `WaitEvent{timeout?}` | Events, with the stream commands for the rest |
| `AddFunctionStream{expression}`, `RunFunction{expression, args}` | Server-side functions |
| `Compare{a, b}`, `Hash{a}`, `ObjectId{a}` | Object identity |
| `Encode{type, value}`, `Decode{type, bytes}` | The codec, with no connection |
| `Members{service, class?}` | The member roster the client exposes |

**Notifications** carry callback firings: `Notification{callback, value or ending}`. A callback
command can ask the callback to block, raise, make a call or close the connection, so the
threading tests are expressible.

**Values** cross as a `Value` message of plain protobuf fields: one per scalar type, string,
bytes, null, an object id, an enum number, and repeated items, map entries and struct fields for
the composites. The testee converts a `Value` to and from native values without its kRPC codec.
Wire bytes would pass through the testee's decoder and then its encoder, so a symmetric codec bug
would cancel out. Only `Encode` and `Decode` carry kRPC wire bytes, checked against fixed vectors.

**Errors** cross as `{kind, service, name, message}`, where `kind` is `rpc`, `stream`,
`connection`, `encoding`, `argument` or `timeout`, plus the name of the native type raised. The
driver checks that name against the client's native types. Lua and cnano raise no types, and send
none.

**Dispatch is generated.** A new clientgen backend, built in C2, generates each testee's `Invoke`
and `AddStream` dispatch from the service definitions. It covers `KRPC`, `TestService`,
`TestService2` and `ConformanceService` only.

- Testees call the real generated stubs and the idiomatic stream API: C# lambdas, Java's method
  name form, C++ `_stream` members.
- Lua, and Python without stubs, dispatch through their runtime service objects.
- Expressions arrive as a neutral tree, and the testee builds it through the `KRPC.Expression`
  stubs.

## Tests, profiles and expected failures

- Tests live in `conformance/tests/test_<area>.py`, named as in [spec.md](spec.md) "Naming".
- Each test is marked with its spec ids and profile, and skipped when the testee lacks the profile.
- **Expected failures** live in `conformance/expected-failures/<client>.txt`, one test id per line,
  enforced strictly as in protobuf. A listed test that passes fails the run, so every gap is fixed
  or recorded. Each line cites the defect or issue, e.g. `# defects.md python-tuple-arity`.
- **Timing tests** race the clock, e.g. the wait timeouts, the stall and the threading tests. Each
  is marked `@timing`, and a listed `@timing` test that passes does not fail the run. Tests order
  events through `ConformanceService` where they can, and take no `@timing` mark.

## Bazel

- `conformance_test(name, testee, client, transports)` in `tools/build/`, modeled on
  `tools/build/client_test.bzl`. Each client BUILD instantiates it, and the targets join `//:test`.
- The testees live with their clients (`client/<lang>/conformance/`), as they build against the
  client.
- **A coverage report** lists spec id against client, built from the test results and markers.
  It is published with the spec in C7.

## TestServer

`ConformanceService` and the `TestService` changes are in [test-service.md](test-service.md).
TestServer serves `TestService` (id 9999), `TestService2` (id 9997, one class used by the
extension members), the extension members on `TestClass`, and the Benchmark service. Its server
types are `protobuf`, `websockets`, `websockets-echo`, `serialio` and `localsocket`. The suite uses
`protobuf`, `localsocket` and `serialio`.
