# Harness

How the suite runs a test against a client. C1 built the driver, the scripted server, the Bazel
macro and the Python testee. C2 built the other five testees and the dispatch generators, C3
the calls, values, codec, errors and objects, and C4 the streams, events, threads and connection
tests with `ConformanceService` (local branch, before its PR).

### Built in C1

| Item | As built |
| --- | --- |
| Layout | `conformance/testee.proto`, `conformance/driver/` (plugin, testee process, scripted server, raw client, values, native tables), `conformance/tests/`, `conformance/expected-failures/<client>.txt`. The Python testee is `client/python/conformance/testee.py`. |
| Commands | Version 1 has only what the first set uses: `Connect`, `Close`, `Invoke`, `AddStream`, `Get`, `Wait`, `AddCallback`, `Compare`. The rest are added with their tests. |
| Values | Scalars, string, bytes, null and `Object{handle, id}`. Each returned object gets a new handle, so two handles can name one object. Composites came with C3. The driver compares integers and floats by value, as Python cannot tell their wire types. |
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
| Coverage | Members whose parameters and result are scalars, strings, bytes or objects. Extended in C3. |
| Testees | `client/<lang>/conformance/`. C# and Java are hand-written beside the generated half, C++ and cnano are C++ with a generated header per service, and Lua dispatches through its runtime service objects like Python. cnano's testee is C++ calling the C API, and links the full C++ protobuf for the testee protocol. |
| Profiles | Lua reports `core` and `defaults`, cnano `core`, so the stream tests skip. cnano builds for TCP/IP only. |
| Lua on Windows | The Lua target was off on Windows, as Lua reads standard input in text mode there. Fixed after C6 by the line framing. |
| `errors-mapped-exceptions` | C# and Java raise the native type itself, with no service or name, so the test checks service and name only when the testee reports them. |
| Expected failures | 1 C#, 1 Java, 6 C++, 6 cnano, 9 Lua, each citing a new row in [defects.md](defects.md). |
| Lint | The C++ and cnano testees are clang-formatted but not clang-tidied, like the client tests. Filed as [#1177](https://github.com/krpc/krpc/issues/1177). |
| Java static streams | The Java stub of a static method takes the connection first, so `addStream(<class>.class, name, connection, args...)` passes it. `test_streams.py::test_class_static_method` checks it. |

### Built in C3

| Item | As built |
| --- | --- |
| Composite values | `Value` carries `Enum`, `list`, `set`, `tuple` (as `Items`), `dictionary` (as `Entries`) and `Struct`. An enum and a struct name their service and type, which the Python and Lua testees need to build one. The driver compares enums by number and structs by their fields, as a typed testee may leave the names unset. The protocol stays at version 1, as it has not shipped. |
| Tuples | Lua has no tuple type and returns a list, so the tests compare a tuple result as a sequence. |
| Conversions | C# and Java compose small converter functions (`Arg.List (Arg.Sint32)`). C++ and cnano compose tag types (`List<Sint32>`), each with an `arg` and a `result`. Each generates a converter per struct, and cnano one per tuple, as their C types name the fields. cnano reuses the C-nano generator's C types, which differ inside a collection (`krpc_enum_t`, `krpc_nullable_*_t`). |
| Arguments | `Invoke` gains `named_arguments`, by the server's parameter name. Arguments left off the end take their defaults: the C# and C++ dispatch has a call per argument count, so the stub fills them in. Java and cnano stubs declare no defaults. Java had reported `defaults` and `named-args`, and now reports neither. |
| Bytes in Lua | Lua strings carry bytes, so the Lua testee sends a string that is not UTF-8 as bytes, and the tests read a bytes result through `values.as_bytes`. |
| Bytes defaults | `BytesDefault` found that C#, C++ and Lua spelled a bytes default as a Python literal. Fixed in clientgen. |
| Calls | `calls-request-ids` is left to C4: with one call in flight it holds trivially, so its test needs the `threads` profile. `calls-deprecated-procedure-warns` (a SHOULD) is not built, as the protocol has no channel for warnings. The scripted server answers `GetServices` with the real `KRPC` definitions, which Lua builds its services from. |
| Extension members | Only the Python and Lua testees reach `TestServiceExtensions` and `TestService2`. The typed testees list `calls-extension-members` as an expected failure until [test-service-full-definitions.md](../../issues/test-service-full-definitions.md) lands. |
| Errors | `test_custom_exception` also checks `errors-raised-type-is-the-exposed-type`: a testee reports an error's service and name only when the error is an instance of the type the client exposes for it (Python checks `isinstance` against the service object, the C++ dispatch has a generated `dynamic_cast` per exception type, C# and Java read them off the generated type). `ObjectDestroyedException` comes from a new `TestService.RemoveTestObject`. The scripted server sends the unknown exception type. |
| Objects | `Object` gains `service` and `name`: a handle of 0 asks the testee to make an object of that class with the given id, which reaches an id the server never issued. New commands `Hash` (null where objects have no hash: Lua, cnano) and `ObjectId`. |
| Member rosters | A `Members` command lists a client's services, and the members of a service, class or enum. The driver computes the expected names from the server's definitions in each dynamic client's style (`ROSTER_STYLES`: Lua names properties by their `get_`/`set_` accessors and has no exception types). The typed testees reply null and skip: their stubs are compiled from the same definitions the clientgen goldens check. |
| Codec | `Encode` and `Decode` commands take a codec type name from a fixed vocabulary (`test_codec.py`), which each testee maps to its client's type: Python and Lua parse it, C# and Java hold a table of type specs, C++ a table of tag types, cnano a table over the generated C codec functions. The vocabulary uses only collection types `TestService` already carries, as cnano generates a codec only for those. A null object is carried apart from the value in a slot, so the null handle is tested inside a list. Dictionaries and sets of several entries are only decoded, as the encoder picks the order. `codec-message` is not built: a protobuf message is encoded by the protobuf library. |
| C++ hash | C++ objects hash with `krpc::hash_value`, so the C++ testee reports it. |
| Moved to C4 | `objects-types-from-different-connections` needs a testee with two connections, which comes with the threads work and the connection binding audit ([connection-binding-audit.md](../../issues/connection-binding-audit.md)). The SHOULDs `objects-sorting` and `objects-different-classes-are-not-equal` are not built. |
| Published | The spec index is linked from the communication protocols page, with the calls, values, codec, errors and objects pages. The connection and streams pages stay orphans until C4 builds the rest of their tests. |
| Coverage | Every member of `KRPC` and `TestService` whose types are scalars, strings, bytes, objects, enums, structs of the service and collections of these. A protobuf message (`GetStatus`, `GetServices`) is still left out. cnano now takes bytes and nullable strings too. The cnano testee leaks what it allocates. |

### Built in C4

| Item | As built |
| --- | --- |
| `ConformanceService` | Id 9996, in the `TestService` assembly with its own definitions, in `CONFORMANCE_SERVICES` (`tools/krpctools/services.bzl`). `clientgen_dispatch` declares its stubs beside the typed testees only, so the shipped clients do not change. The as-built surface is in [test-service.md](test-service.md). The Python and Lua clients' own roster tests list it. |
| Stream commands | `SetRate`, `Rate`, `Remove`, `CopyStream`, `RemoveCallback`, `AddEndCallback`, `RemoveEndCallback`, `AddUpdateCallback`, `RemoveUpdateCallback`, and `AddStream.scoped`. A `Notification` carries a value, an `Ending` with the error an end callback was passed, or neither. Callback ids last as long as the testee. |
| `UNSUPPORTED` | An error kind a testee replies with for a feature its client lacks (update callback in C# and Java, scoped removal outside Python, `Interrupt` in Python and C++). The driver skips the test. |
| Events | A call that returns an event replies with a `Value.event` handle. `WaitEvent`, `AddEventCallback` and `EventStream` take it, and `AddEndCallback` and `Remove` take an event or a stream. The dispatch generators convert a `KRPC.Event` result, and do not stream a procedure that returns one. cnano has no events. |
| Threads | `Command.condition` holds a stream's or event's condition around a command. A reply and a notification name their thread. A callback `Behavior` sleeps, reports its return, and blocks until `Release`, fails, invokes or closes. `Interrupt` interrupts a worker (C#, Java). The driver's `Client.start` sends a command without waiting, and returns a `Pending`. |
| Connections | `Command.connection` names a connection beside the default one. Connecting the default closes the others and drops every handle. Only the threaded testees take a name, so `objects-types-from-different-connections` (core in the spec) runs in Python, C#, Java and C++ only. `ConformanceService.Probe` reports the connection each call came over. |
| Scripted server | Answers `AddStream` and `RemoveStream`, records each call once answered, sends stream updates and raw frames from the test thread, listens on a local socket path, and closes once its script returns. C-nano names a procedure by its id, which the scripts allow for. |
| Local socket | Every client but cnano has a `conformance-localsocket` target, which runs `test_connection.py` only. The testee's `XDG_RUNTIME_DIR` and `LOCALAPPDATA` are a scratch directory, so `connection-default-socket-path` listens on `krpc.sock` there. |
| Sharding | `conformance_test` runs four shards, each with its own server and testee. The six clients' twelve targets take 44 s together, most of it Lua and cnano waiting out the reply deadline on expected failures that hang. |
| Rewordings | Matched to the server and the clients: a stream of a yielding procedure delivers its result; a call sees the updates written before its response (single-connection guarantee 3); streaming a setter is `dynamic`; an event's stream is a stream of bool, true on each firing (Python refuses to stream a procedure returning an event); a refused port may raise the platform's error, as every typed client does; a callback's first call may run on the adding thread; `calls-request-ids` is `threads`. |
| Test shapes | `threading-rpc-interleaving` runs on a scripted server, as the server answers one client's requests in order. `threading-a-blocked-callback-stalls-only-callbacks` reads the other stream's first value before blocking, as waiters are woken through the callback thread in all four clients. The close tests check only that a later call fails, as `connection-calls-after-close-raise` checks the error. `events-a-removed-callback-does-not-take-a-firing` removes the callback before the firing; the replay race stays in Python's own tests. `connection-stall` sets a 1 s stall timeout, which the four clients that have one take since a single-connection addition. |
| Not built | `connection-serial-resume` and `events-custom-event`, built in C5. |
| Published | The connection, streams, events and threading pages, so every page is linked from the spec index. |
| Testee builds | The C++ and cnano testees build without warnings. |

### Built after C6

| Item | As built |
| --- | --- |
| JSON lines | The testee protocol frames each message as its proto3 JSON form on a line (user request, 2026-10-26), replacing varint prefixes. Base64 lines came first, and JSON replaced them for readability. Python and the driver use `json_format`, C# `JsonFormatter`/`JsonParser`, Java `JsonFormat` (`protobuf-java-util`, newly pinned), and one header shared by the C++ and cnano testees (`conformance/cpp/framing.hpp`) `util::MessageToJsonString`. The C testees drop `_setmode`. A testee that writes a line that is not a message fails at once, with the line in the error (negative control: a base64-writing Python testee). Python and Lua testees were fed hand-written lines against a TestServer. |
| Lua converter | lua-protobuf has no JSON mapping, so `client/lua/conformance/protojson.lua` converts between its tables and JSON, driven by `pb.fields`, with a small JSON reader and writer. It lasts until lua-protobuf is replaced. |
| Python float parsing | Python's `json_format` rejects `3.4028235e+38`, the shortest form of the largest float that C++ and C# print, as too large: it compares the double before rounding to single precision. The same bug was fixed in C# (protocolbuffers/protobuf#10509). The driver rounds such a value to the largest float before parsing. |
| Lua on Windows | The Lua target runs on Windows again. Only CI can prove it, after a push. |
| cnano local socket | Waits for the cnano build with every transport at once, which removes the compile-time transport choice (user, 2026-10-26). |
| Holding a condition | `HoldCondition{stream}` holds a stream's or event's condition, or the connection's update condition for handle 0, while the thread runs its later commands, until `ReleaseCondition`. Python, C# and C++ take the lock in one command and let go in another on the same thread. Java's monitor needs a block, so its worker runs the later commands inside `synchronized`. `WaitForUpdate{timeout}` is the connection-wide wait (Python and C++; C# and Java reply UNSUPPORTED). |
| `first-call-on-add` profile | A MAY: a client claiming it makes the first call of a callback before the add returns, so the notification comes before the reply. Python, C#, C++ and Java claim it. |
| Unsupported values | A codec type a fixed-table testee has no type for, and a null its type cannot hold (a C++ string or vector, a C-nano string or collection), reply UNSUPPORTED, so the test skips. C-nano's dispatch wraps a non-nullable string parameter in `NotNull<String>` for this. |
| Function types | `AddFunctionStream` and `RunFunction` also take `double`, `nullable sint32`, `list(sint32)` and `TestClass`, and runs take double and object arguments. |
| `ThrowMappedException` | One TestService procedure throws the seven mapped exceptions that had none, by name, so `errors-mapped-exceptions` covers all eleven. |

### Built in C5

| Item | As built |
| --- | --- |
| Building functions | The driver builds a function with `Invoke`s of the `KRPC.Expression` and `KRPC.Type` static methods (`driver/functions.py`), so a function is an object handle, with no neutral tree format. `Call{invoke}` builds `Expression.Call` over the `ProcedureCall` the client builds for a stream of the member: the dispatch generators emit it per streamed member (C# `Connection.GetCall`, Java `getCall`, C++ `_call`), and Python uses `get_call`. |
| Function commands | `AddFunctionStream{function, type}`, `AddFunctionEvent{function}` (replies with an event handle) and `RunFunction{function, type, arguments}`. The type is `sint32`, `bool` or `string`, which C# (`AddStream<T>`, `Run<T>`) and C++ (templates over `std::optional<T>`) need, and Python and Java ignore, as they read the type from the server. Arguments are sint32, bool, string or null Values. C++ visits up to two over a `std::variant`. Lua and cnano have no `functions` profile. |
| Function tests | All seven `functions-*` requirements and `events-custom-event` (in `test_events.py`, profiles `events` and `functions`) pass in Python, C#, Java and C++, with no new defect. The run test subtracts, so a client that swapped arguments fails (negative control). |
| Function rewordings | `functions-function-streams-over-one-function` and `functions-events-over-one-function`: each add is separate, and removing one leaves the other. The state advancing once per evaluation is not observable without racing the clock. |
| Python testee | Escapes a member named after a keyword (`Expression.lambda_`), which the C4 dispatch never met. |
| Serial transport | cnano has a `conformance-serialio` target, Linux only, running `test_connection.py`. The library picks its transport at compile time, so `conformance_test` takes `transport_testees`, and cnano builds `conformance-testee-serialio` on `krpc_cnano_serialio`. TestServer's `--type` takes a comma list: the target runs `serialio,protobuf`, so the control connection and `raw` calls go over TCP/IP while the testee is on a socat pseudo-terminal pair. |
| Serial scripted server | `ScriptedServer` runs on its own socat pair on the serialio target (`SerialLine`), as the testee has no other transport. A serial server sees no close: socat stays up when the client closes its end. So `connection-close` skips (no half-close), and a test whose connect fails stops socat to wake its script. `connection-wrong-port` opens a missing device path. |
| Serial skips | `connection-disconnect-during-handshake`, `connection-unexpected-handshake-message` and `connection-refused` for `MALFORMED_MESSAGE` and `TIMEOUT` skip over serial, as the resume rules override them. An expected-failure line holds for every transport of a client, so a test whose outcome differs by transport skips on one. |
| `connection-serial-resume` | Parametrized: a leftover `response`, `stream_update` or `disconnect` before the `connection_response`; a second `connection_response` before the first `response`; `MALFORMED_MESSAGE` and `TIMEOUT` as no answer, then a retry after a 3.5 s handshake timeout; and a refusal not retried, for which the script waits 5 s. cnano fails the two no-answer cases (`cnano-no-silent-retry`). A cnano that fails on a leftover fails three cases (negative control). |

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

`conformance/testee.proto`, versioned. Each message is its proto3 JSON form on a line of its own,
and a reader ignores a carriage return before the newline and rejects an unknown field. Text mode on
Windows cannot corrupt it, so a testee needs no binary mode switch, and a person can read a trace or
feed a testee commands by hand (changed after C6, from varint length-delimited framing).

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
| `Call{invoke}`, `AddFunctionStream{function, type}`, `AddFunctionEvent{function}`, `RunFunction{function, type, args}` | Server-side functions, built by `Invoke`s of the `KRPC.Expression` stubs (C5) |
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
  or recorded. Each line gives the reason as a comment. The files ship in `krpc`, so they name no
  `krpc-docs` file; [defects.md](defects.md) maps each defect to its requirement.
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
