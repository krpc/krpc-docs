# Harness

How the suite runs a test against a client. Nothing here exists yet. There is no `conformance/`
directory, testee or `ConformanceService` in `krpc`.

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
  ended by the server) and are deleted in C5.
- **Timeouts.** A test that waits on the handshake or stall timeout sets it short through
  `Connect` (README "Open questions").

## Testee protocol

`conformance/testee.proto`, versioned. Varint length-delimited framing, which every client already
implements.

**Hello** reports the client name, the testee protocol version, the profiles and the transports
([spec.md](spec.md) "Profiles").

**Commands** each carry an `id` and an optional `thread` name. The testee runs each command on the
named worker thread and replies asynchronously, keyed by `id`. A test can then say "wait on thread
A, remove on thread B", the shape of the deadlocks found in Python and Java.

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

**Values** cross as kRPC wire bytes plus a `krpc.Type`. The driver decodes them with the Python
codec, which the codec vectors pin.

**Errors** cross as `{kind, service, name, message}`, where `kind` is `rpc`, `stream`,
`connection`, `encoding`, `argument` or `timeout`, plus the name of the native type raised. The
driver checks that name against the generated exception table.

**Dispatch is generated.** A new clientgen backend generates each testee's `Invoke` and `AddStream`
dispatch from the service definitions.

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
  or recorded. Each line cites the defect or issue, e.g. `# defects.md cpp-error-stack-trace`.

## Bazel

- `conformance_test(name, testee, client, transports)` in `tools/build/`, modeled on
  `tools/build/client_test.bzl`. Each client BUILD instantiates it, and the targets join `//:test`.
- The testees live with their clients (`client/<lang>/conformance/`), as they build against the
  client.
- **A coverage report** lists spec id against client, built from the test results and markers.
  It is published with the spec in C6.

## TestServer

`ConformanceService` and the `TestService` changes are in [test-service.md](test-service.md).
TestServer serves `TestService` (id 9999), `TestService2` (id 9997, one class used by the
extension members), the extension members on `TestClass`, and the Benchmark service. Its server
types are `protobuf`, `websockets`, `websockets-echo`, `serialio` and `localsocket`. The suite uses
`protobuf`, `localsocket` and `serialio`.
