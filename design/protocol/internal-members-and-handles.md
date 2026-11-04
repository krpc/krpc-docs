# Internal members, protocol messages, stream and event handles

**Status:** in progress. Stream and event ids are issue
[#1178](https://github.com/krpc/krpc/issues/1178). Internal procedures, the scanner check and the
call conformance tests have no issue or PR yet.

What a user of a client sees of the protocol's plumbing: which procedures are hidden, where a
protocol message appears in an RPC, and where a stream or an event is a raw id or a handle.

## Rules

| # | Rule |
| --- | --- |
| 1 | A stream reaches a user through the client's add-stream API, which returns a handle wrapping the stream's id. |
| 2 | No RPC returns a stream, other than the internal `KRPC.AddStream` and `KRPC.AddFunctionStream`. |
| 3 | An event reaches a user through the client's add-event API, or an RPC returning a custom event. |
| 4 | An event from an RPC is wrapped the same way the add-event API wraps one. |

## Wire form

* A stream or an event is encoded as the `uint64` id of its stream. The `Stream` and `Event`
  messages are removed (#1178). Object references are bare ids too, so every handle is one form.
* The `STREAM` and `EVENT` type codes stay. A client needs them to register a stream before its
  first update, and to wrap an event.
* A handle is never extended with fields. Information about a stream is a getter RPC taking the id.

## Internal members

A procedure is **internal** when a direct call bypasses state the client library keeps. A direct
`AddStream` makes a server stream the stream manager never registered, so its docs already called
direct use undefined behavior.

| Procedure | Called by the client to |
| --- | --- |
| `KRPC.AddStream` | add a stream of a call |
| `KRPC.SetStreamRate` | set a stream handle's rate |
| `KRPC.RemoveStream` | remove a stream handle |
| `KRPC.AddFunctionStream` | add a stream of a server side function |
| `KRPC.CompileFunction` | compile a server side function |
| `KRPC.RunFunction` | run a server side function |
| `KRPC.AddEvent` | add an event |

Mechanism:

* `[KRPCProcedure (Internal = true)]` sets `Procedure.internal` (field 9) in `GetServices`, and
  `internal` in the service definitions JSON. It travels the same way as `deprecated`.
* Generated stubs, the dispatch of the conformance testees, the services Python and Lua build at
  run time, and the API docs all leave an internal procedure out.
* Each client library calls the internal procedures through its own helper: `InternalProcedures`
  in C#, Java and C++, and `Client._invoke_krpc` in Python. Lua and C-nano have no streams and call
  none.
* Java's invoke looked up whether a call adds a stream in the generated stubs. With no stub to look
  up, the helper passes that flag to `Connection.invokeKrpc` explicitly.

Alternatives considered:

| Option | Rejected because |
| --- | --- |
| Flag in the service definitions only | Python and Lua build services from `GetServices` at run time and would not see it |
| Hide per language (`_add_stream`, C# `internal`, C++ friends) | Java's services live in `krpc.client.services`, the client in `krpc.client`, so no access modifier hides a member from users but not from the client. Lua and C-nano have no mechanism |
| Hide by documentation only, as before | Users find the stubs and call them |

### Side effect: KRPC exception types

C++ and Java registered the KRPC exception types (`InvalidOperationException` and the rest) only as a
side effect of constructing a KRPC service object, which their stream code did. With the stream code
calling the helper instead, a mapped exception arrived as a plain RPC error. Both now register the
types on connect, as C# already did. This fixed 42 C++ conformance expected failures.

### Not internal

`GetServices`, `Expression.Call` and `Expression.CallWithArguments` stay public. None of them
touches client state, and each has users outside the client libraries. See the next section.

## Protocol messages in RPCs

| Member | Message | Where | Status | Why |
| --- | --- | --- | --- | --- |
| `KRPC.GetServices` | `Services` | return | public | The only service listing in C#, C++ and Java, e.g. to check a mod's service is installed. The format is documented on the protocol page |
| `Expression.Call` | `ProcedureCall` | parameter | public | The only way to put an RPC in a server side function in C++ and Java, which have no lambda compiler |
| `Expression.CallWithArguments` | `ProcedureCall` | parameter | public | As `Call`, with some arguments computed by functions |
| `KRPC.AddStream` | `ProcedureCall` | parameter | internal | Bypasses the stream manager |

* A `ProcedureCall` acts as a sealed handle. A user gets one from a client helper (Python
  `get_call`, C# `GetCall`, Java `getCall`, the generated C++ `*_call()` methods) and passes it
  back. A user never reads or sets its fields.
* The cost is cosmetic: the protobuf type in the signature, and the generated schema package on the
  user's path. A client type such as `krpc.Call` wrapping it would be a breaking change in every
  client for little gain. Revisit only if users ask.
* `Services` is the one place a user reads a message's fields. Client-native wrapper types would be a
  large surface for an introspection API few use.

Internal and "has a message in its signature" are separate questions. Internal is about client
state. A message type in a signature is a matter of presentation.

## Streams: raw ids and handles

| Client | Add-stream API returns | An RPC returning `STREAM` decodes as |
| --- | --- | --- |
| Python | `Stream` (`conn.add_stream`) | `int` |
| C# | `Stream<T>` (`AddStream`) | `ulong` |
| C++ | `Stream<T>` (`add_stream<T>`) | `uint64_t` |
| Java | `Stream<T>` (`addStream`) | `long` |
| Lua | no streams | `number` |
| C-nano | no streams | `uint64_t` |

* Only the internal `AddStream` and `AddFunctionStream` return a stream, so the raw-id column only
  shows through the client libraries' own internal calls.
* The service scanner enforces rule 2. It rejects a `Messages.Stream` in a parameter, a struct field,
  nested in a return value, or as the return value of a procedure that is not internal.
* A nullable stream id is `ulong?` in C#, and `Long` in Java and inside collections.

## Events: raw ids and handles

| Client | Add-event API returns | An RPC returning `EVENT` decodes as |
| --- | --- | --- |
| Python | `Event` (`conn.add_event`) | `krpc.event.Event`, at any position |
| C# | `Event` (`AddEvent`) | `KRPC.Client.Event`, at any position |
| C++ | `krpc::Event` (`krpc::add_event`) | `krpc::Event`, at any position |
| Java | `Event` (`addEvent`) | `krpc.client.Event`, at any position |
| Lua | no add-event API | `number`, a bare id |
| C-nano | no add-event API | `uint64_t`, a bare id |

* Python, C#, C++ and Java follow rules 3 and 4. Each add-event API calls `KRPC.AddEvent`, and the
  decoder wraps that result the same way as any other event.
* Python wrapped only an event returned at the top level, until a review fix made the decoder wrap
  events inside collections and structs too.
* Lua and C-nano deviate. Without a stream manager an event cannot be waited on. The options are
  event support in those clients, or leaving event-returning members out of their stubs. Open.

## Conformance coverage

| Test | Requirement |
| --- | --- |
| `test_calls.py::test_internal_procedure` | A client leaves out a procedure the server marks internal |
| `test_calls.py::test_exposed_members` | The exposed members exclude internal procedures |
| `test_functions.py::test_run_a_call` | A call the client builds runs through `Expression.Call` |
| `test_functions.py::test_call_member_kinds` | The client builds a call for a procedure, a property, a class method, a class property and a static method |
| `test_functions.py::test_call_with_arguments` | A built call passes to `Expression.CallWithArguments`; a position with a function takes its value, one without keeps the encoded argument |
| `test_functions.py::test_call_with_a_call_argument` | A function over one built call computes an argument of another, here a class method's instance |

`CallWithArguments` needs a testee command of its own, as the generic invoke cannot pass a
`ProcedureCall` argument. Python, C#, C++ and Java implement it. Lua and C-nano lack the functions
profile.

## Phases

| Phase | Content | State |
| --- | --- | --- |
| 1 | Streams and events as bare stream ids (#1178) | implemented, unmerged |
| 2 | `Procedure.internal`, the seven KRPC procedures marked, clients omit them | implemented, unmerged |
| 3 | Scanner allows a stream only as the return value of an internal procedure | implemented, unmerged |
| 4 | Conformance tests for calls the client builds | implemented, unmerged |

## Open items

* The stream/event split in the client APIs carries no information now that both are a `uint64`:
  C++ `Client::Returns { value, stream, event }`, the generator's return kind, and the return type
  code taken by C# `IConnection.Invoke`. Collapsing it to "adds a stream" changes the client API and
  the generated stubs.
* Events in Lua and C-nano, above.
* A sealed client type for `ProcedureCall`, only if users ask.
