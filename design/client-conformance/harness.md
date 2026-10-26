# Harness

How the suite runs a test against a client. C1 built the driver, the scripted server, the Bazel
macro and the Python testee. C2 built the other five testees and the dispatch generators (local
branch, before its PR). `ConformanceService` does not exist yet.

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
| Lua on Windows | The Lua target is off on Windows: Lua reads standard input in text mode there. |
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
