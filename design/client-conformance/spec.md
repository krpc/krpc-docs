# Requirement inventory

The requirements the published spec states, and the test that checks each. Phase C0 turns this
into the spec pages in `krpc`, phrased as RFC 2119 MUST and SHOULD under the krpc writing rules.
This list is the plan for those pages. Once a page is published it is the source of truth, and
this list is not kept in step.

Sources: the client testing standard's rubric, the single connection's client reader rules
([single-connection.md](../protocol/single-connection.md)), the stream and event design
([stream-and-event-improvements.md](../protocol/stream-and-event-improvements.md)), the client
rules in [protocol-compatibility.md](../protocol-compatibility.md), and the open defects
([defects.md](defects.md)).

## Naming

| Item | Form | Example |
| --- | --- | --- |
| Requirement id | `<area>-<name>`, kebab case | `streams-wait-timeout-short` |
| RST label in the spec | `spec-<id>` | `spec-streams-wait-timeout-short` |
| Test | `conformance/tests/test_<area>.py::test_<name>` | `test_streams.py::test_wait_timeout_short` |
| Variant | A pytest parameter | `test_values.py::test_scalar_arguments[uint64]` |

- The area is one spec page and one test file. The name is a short phrase, a sentence for a
  behavior (`a_callback_is_not_passed_an_older_value`) and a noun for a feature (`rate`).
- An id is never reused or renamed once published. A dropped requirement leaves a gap.
- A test is marked `@spec("<id>")` and `@profile("<profile>")`. The coverage report reads the
  markers, so a test checking a second requirement adds a second marker.
- Names come from the existing tests: the Python stream, event and object tests, which the other
  clients mirror, and the client testing standard's catalog for calls and values.

## Profiles

A testee reports its profiles in `Hello`. A test outside them is skipped, not failed.

| Profile | Covers | Python | C# | C++ | Java | Lua | cnano |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: |
| `core` | Connection, calls, values, codec, errors, objects | yes | yes | yes | yes | yes | yes |
| `dynamic` | Rejecting wrong arguments, in a dynamically typed language | yes | no | no | no | yes | no |
| `defaults` | Omitting arguments that have defaults | yes | yes | yes | no | yes | no |
| `named-args` | Passing arguments by name, at run time | yes | no | no | no | no | no |
| `streams` | Streams | yes | yes | yes | yes | no | no |
| `events` | Events | yes | yes | yes | yes | no | no |
| `functions` | Server-side function streams, events and runs | yes | yes | yes | yes | no | no |
| `threads` | Concurrent calls, callbacks, close from other threads | yes | yes | yes | yes | no | no |

The `dynamic` profile holds the requirements a compiler enforces in a statically typed language:
wrong argument types, counts and ranges (C3 ruling). The server takes any enum number, as
`KRPC.GameScene` is a flags enum, so `values-invalid-enum` is a `dynamic` requirement too.

C# named arguments are compiler syntax over the stub's declared defaults, which `defaults` already
checks by leaving arguments off the end, so C# takes no `named-args` profile (C3 ruling).

C4 rulings: `streams-property-setters-are-invalid` is `dynamic`, as a compiler rejects such a
stream. `calls-request-ids` is `threads`, as it holds trivially with one call in flight. The
other C4 rewordings are listed in [harness.md](harness.md) "Built in C4".

Transports are reported separately: `tcpip` (all), `localsocket` (all but cnano, until cnano is built
with every transport at once), `serialio` (cnano). Lua has no streams in 0.8 ([defects.md](defects.md)
"Decisions").

Levels below: **M** is MUST, **S** is SHOULD. Profile is `core` unless given.

## Connection

`test_connection.py`. Most tests run against the scripted server ([harness.md](harness.md)).

| Id | Level | Requirement |
| --- | :-: | --- |
| `connection-connect` | M | Connects over TCP to an address and port, by default `127.0.0.1:50000`. |
| `connection-connect-localsocket` | M | Connects to a local socket path. Profile: `localsocket`. |
| `connection-default-socket-path` | M | The default path is `krpc.sock` in `XDG_RUNTIME_DIR` or `LOCALAPPDATA`, else `/tmp/krpc-<user>.sock`. Profile: `localsocket`. |
| `connection-client-name` | M | Sends the client name in the `connection_request`. `KRPC.GetClientName` returns it. |
| `connection-protocol-version` | M | Sends protocol version 2. |
| `connection-wrong-port` | M | Nothing listening raises the connection error. |
| `connection-refused` | M | A refusal raises the connection error with the status and message. `DENIED` is distinguishable. |
| `connection-unknown-status` | M | An unknown `ConnectionResponse` status is reported with its message. |
| `connection-disconnect-during-handshake` | M | A `disconnect` before the `connection_response` ends the attempt with its reason. |
| `connection-unexpected-handshake-message` | M | Any other case before the `connection_response` is a protocol error. |
| `connection-handshake-timeout` | S | Gives up after a handshake timeout, 5 s by default, settable, including to none. |
| `connection-reconnect-gets-a-new-client` | M | A new connection is a new server client, with a new id. |
| `connection-close` | M | Close sends a `CLOSED` `disconnect`, half-closes and drains for up to 1 s. |
| `connection-calls-after-close-raise` | M | A call after close raises the connection error at once. |
| `connection-ended-by-the-server` | M | A server `disconnect` fails the connection. The error carries its reason and message. |
| `connection-ended-without-a-disconnect` | M | End of stream with no `disconnect` fails the connection the same way. |
| `connection-pending-calls-fail-on-end` | M | Calls in flight when the connection fails raise its error. Profile: `threads`. |
| `connection-unknown-message-is-skipped` | M | A `Message` with no known case, once the session has started, is skipped. |
| `connection-wrong-direction-is-a-protocol-error` | M | A client-to-server case received is a protocol error, answered with a `PROTOCOL_ERROR` `disconnect`. |
| `connection-malformed-message` | M | A message that fails to parse ends the connection with `MALFORMED_MESSAGE`. |
| `connection-stall` | S | A message stalled partway for the stall timeout (30 s by default, settable) ends the connection with `TIMEOUT`. |
| `connection-serial-resume` | M | A resumed serial client follows the resume rules in single-connection.md "Reconnecting". Profile: `serialio`. |

## Calls

`test_calls.py`.

| Id | Level | Requirement |
| --- | :-: | --- |
| `calls-procedure` | M | Calls a service procedure. |
| `calls-service-property` | M | Gets and sets a service property, including get-only and set-only ones. |
| `calls-class-method` | M | Calls a class instance method. |
| `calls-class-static-method` | M | Calls a class static method, also through an instance where the language allows. |
| `calls-class-property` | M | Gets and sets a class property, including asymmetric accessors. |
| `calls-extension-members` | M | Calls members another service adds to a class, including one returning a class of a third service. |
| `calls-void-return` | M | A procedure returning nothing completes. |
| `calls-blocking-procedure` | M | A procedure that yields across updates returns its result. |
| `calls-request-ids` | M | Each request in flight has an id no other request in flight has. |
| `calls-request-id-sequence` | S | Ids start at 1 per session and increase by one. The server treats ids as opaque. |
| `calls-responses-matched-by-id` | M | A response is matched to its call by id, never by position. Profile: `threads`. |
| `calls-unknown-response-id` | M | A response id neither pending nor abandoned is a protocol error. |
| `calls-abandoned-response-is-discarded` | S | A call interrupted while waiting abandons its id, and the next call gets its own result. Profile: `threads`. |
| `calls-too-many-arguments` | M | Too many arguments raise the client's argument error, before sending. Profile: `dynamic`. |
| `calls-too-few-arguments` | M | Omitting an argument with no default raises the argument error. Profile: `dynamic`. |
| `calls-scalar-defaults` | M | An omitted scalar, string or bytes argument takes its default. Profile: `defaults`. |
| `calls-collection-defaults` | M | An omitted list, set, dictionary or tuple argument takes its default, including an empty one. Profile: `defaults`. |
| `calls-null-default` | M | An omitted argument whose default is null is sent as null. Profile: `defaults`. |
| `calls-enum-default` | M | An omitted enum argument takes its default. Profile: `defaults`. |
| `calls-struct-default` | M | An omitted struct argument takes its default. Profile: `defaults`. |
| `calls-special-defaults` | M | NaN, the infinities and the integer and floating point extremes arrive intact as defaults. Profile: `defaults`. |
| `calls-partial-arguments` | M | Trailing arguments omitted, on a procedure, an instance method and a static method. Profile: `defaults`. |
| `calls-named-arguments` | M | Arguments by name, omitting a non-trailing default, and the errors for a duplicate or unknown name. Profile: `named-args`. |
| `calls-deprecated-procedure-warns` | S | A client with a runtime warning mechanism warns on a deprecated call. |

## Values

`test_values.py`. Arguments go through an independent representation, a string, so a symmetric
codec bug cannot pass ([test-service.md](test-service.md) "Testing values").

| Id | Level | Requirement |
| --- | :-: | --- |
| `values-scalar-arguments` | M | Each scalar type as an argument. Variants: `double`, `float`, `sint32`, `sint64`, `uint32`, `uint64`, `bool`. |
| `values-scalar-returns` | M | Each scalar type as a return value. Same variants. |
| `values-integer-extremes` | M | The minimum and maximum of each integer type, both directions. |
| `values-string` | M | Strings, including non-ASCII text, both directions. |
| `values-line-endings` | M | CR and LF survive a string round trip. |
| `values-bytes` | M | Bytes, both directions. |
| `values-enums` | M | An enum value, both directions. |
| `values-invalid-enum` | M | An out-of-range enum argument raises an error. Profile: `dynamic`. |
| `values-collections` | M | Lists, sets, dictionaries and tuples of scalars, both directions. |
| `values-nested-collections` | M | A collection of collections, both directions. |
| `values-collections-of-objects` | M | Lists, sets, dictionaries and tuples of objects, both directions. |
| `values-structs` | M | Structs, nested structs and collections of structs, both directions. |
| `values-nullable-scalars` | M | A nullable scalar and enum, null and not, both directions. |
| `values-nullable-string` | M | A nullable string, both directions. |
| `values-nullable-collections` | M | A nullable list, set, dictionary and tuple, both directions. |
| `values-nullable-object` | M | A nullable object, through a procedure, an instance method and a static method. |
| `values-nullable-struct-fields` | M | Nullable struct fields, and a nullable struct. |
| `values-nullable-elements` | M | Null list elements, dictionary values and tuple items, also nested. |
| `values-incorrect-parameter-type` | M | A value of the wrong type raises the client's encoding or argument error. Profile: `dynamic`. |
| `values-integer-out-of-range` | S | An integer outside its parameter's type raises the encoding error. Applies to dynamically typed clients. |
| `values-string-is-not-a-list` | S | A string passed for a list of strings raises an error. Applies to dynamically typed clients. |

## Codec

`test_codec.py`. Driven by `Encode` and `Decode` commands, with no server.

| Id | Level | Requirement |
| --- | :-: | --- |
| `codec-scalars` | M | Each scalar type encodes to, and decodes from, the given bytes. |
| `codec-nan` | M | A NaN of either sign decodes as a NaN. A NaN encodes to some NaN. |
| `codec-string-and-bytes` | M | Strings and bytes, to and from the given bytes. |
| `codec-object` | M | An object handle, and the null handle. |
| `codec-collections` | M | Lists, sets, dictionaries, tuples and nested collections. |
| `codec-tuple-arity` | M | A tuple of the wrong arity fails to encode, and fails to decode. |
| `codec-struct` | M | A struct, with null and non-null fields. |
| `codec-nullable` | M | The null encoding of each nullable position. |
| `codec-message` | M | A protobuf message, and its length prefix. |

## Errors

`test_errors.py`.

| Id | Level | Requirement |
| --- | :-: | --- |
| `errors-mapped-exceptions` | M | Each server exception with a `mapped_type` raises the client's native type for it ([client-codegen.md](../client-codegen.md) "Native types"). A client with no exception types (Lua, cnano) reports the error with the `Service.Name: ` prefix. |
| `errors-custom-exception` | M | A service exception raises its generated type. |
| `errors-krpc-exceptions` | M | The `KRPC` exceptions with no mapped type (`ObjectDestroyedException`, `StreamRemovedException`, ...) raise their generated types. |
| `errors-raised-type-is-the-exposed-type` | M | The type raised for a server exception is the type the client exposes for it, so a handler written against the stub catches it. |
| `errors-unknown-exception-type` | M | An exception of an unknown service or type raises the generic error, carrying service, name and description. |
| `errors-message` | M | The message is the description, then the server stack trace when sent, in the format of [client-codegen.md](../client-codegen.md) "Decisions". |
| `errors-structured` | S | The error exposes the service and name of the server exception. |
| `errors-null-argument-rejected` | M | A null argument to a non-nullable parameter is sent, and the server's rejection raised. |
| `errors-null-return-rejected` | M | A null return from a non-nullable procedure raises an error. |
| `errors-guarded-nullable-property` | M | A property readable as null whose setter rejects null raises on a null set. |
| `errors-invalid-object-id` | M | A handle the server never issued raises the `ArgumentException` mapping, as a call target and as an argument. The next call succeeds. |

## Objects

`test_objects.py`.

| Id | Level | Requirement |
| --- | :-: | --- |
| `objects-equality` | M | Two handles to one object are equal. Handles to different objects are not. |
| `objects-hash` | M | Equal handles hash equal, where the language hashes. |
| `objects-sorting` | S | Handles order by id, where the language orders. |
| `objects-different-classes-are-not-equal` | S | Handles of different classes with one id are not equal. |
| `objects-get-object-id` | M | The object id helper returns the id, and raises on null. |
| `objects-types-from-different-connections` | M | Objects and types from two connections stay bound to their own connection. |
| `objects-member-rosters` | M | The client exposes exactly the members, classes and enum values the server defines. |

## Streams

`test_streams.py`. Profile `streams`. Names follow Python's `test_stream.py`, which the other
three clients mirror.

| Id | Level | Requirement |
| --- | :-: | --- |
| `streams-procedure` | M | Streams a procedure. |
| `streams-property` | M | Streams a service property getter. |
| `streams-class-method` | M | Streams an instance method. |
| `streams-class-static-method` | M | Streams a static method. |
| `streams-class-property` | M | Streams a class property getter. |
| `streams-extension-member` | M | Streams a member another service adds. |
| `streams-property-setters-are-invalid` | M | A setter or a void procedure cannot be streamed. |
| `streams-null-initial-value` | M | A stream delivers null. |
| `streams-struct-value` | M | A stream delivers a struct, and an unchanged struct sends one update. |
| `streams-read-straight-after-add` | M | A stream starts on add. A read blocks until the first value. |
| `streams-add-stream-twice` | M | Each add makes a new stream with its own id and lifetime. |
| `streams-interleaved` | M | Several streams update independently. |
| `streams-rate` | M | The rate can be set and read back. |
| `streams-wait` | M | `wait` returns on the next update. |
| `streams-wait-timeout-short` | M | `wait(timeout)` returns false when the timeout elapses first. |
| `streams-wait-timeout-long` | M | `wait(timeout)` returns true on an update. The timeout is a deadline. |
| `streams-callback` | M | A callback is called with each new value. |
| `streams-callback-added-after-the-first-value` | M | A callback added to a stream with a value is called once with it. |
| `streams-a-callback-is-not-passed-an-older-value` | M | A callback never receives a value older than its last. |
| `streams-a-callback-runs-on-one-thread-at-a-time` | M | One callback never runs on two threads at once. |
| `streams-callback-is-not-passed-an-error` | M | Callbacks receive values only. |
| `streams-remove-callback` | M | A removed callback is not called again. |
| `streams-callback-that-raises` | M | A throwing callback is reported, and other streams carry on. |
| `streams-error-ends-the-stream` | M | A final error result ends the stream. Later reads and waits raise it. |
| `streams-exception-immediately` | M | A call that throws on its first evaluation ends the stream with the typed error. |
| `streams-exception-later` | M | A call that throws after some updates ends the stream with the typed error. |
| `streams-yield-exception` | M | A yielding procedure cannot be streamed and ends with an error. |
| `streams-a-value-that-fails-to-decode-ends-only-its-stream` | M | A decode failure ends that stream and no other. |
| `streams-remove` | M | Removing through a handle ends the stream at once for every copy. Reads raise the removed-stream error. |
| `streams-remove-stream-twice` | M | Removing again, through any copy, does nothing. |
| `streams-remove-then-add-stream` | M | A stream added after a removal of an equal one is independent. |
| `streams-update-does-not-resurrect-a-removed-stream` | M | An update in flight for a removed stream is dropped. |
| `streams-result-for-an-unregistered-stream-is-dropped` | M | A result for an unknown id is dropped. |
| `streams-remove-wakes-a-waiting-thread` | M | A waiter wakes on remove and raises. Profile: `threads`. |
| `streams-close-wakes-a-waiting-thread` | M | A waiter wakes on close and raises the closed error. Profile: `threads`. |
| `streams-connection-failure-wakes-a-waiting-thread` | M | A waiter wakes on connection failure and raises its error. Profile: `threads`. |
| `streams-end-callback-on-remove` | M | An end callback is called once on remove. |
| `streams-end-callback-on-error` | M | An end callback is called once with the error. |
| `streams-end-callback-on-close` | M | An end callback is called once on close. |
| `streams-end-callback-added-after-the-end` | M | An end callback added after the end is called at once. |
| `streams-remove-end-callback` | M | A removed end callback is not called. |
| `streams-response-precedes-the-first-update` | M | The first update follows the response to the add. |
| `streams-no-update-after-a-remove-response` | M | No update for a stream follows the response to its removal. |
| `streams-calls-see-current-values` | M | After a call returns, stream values are at least as new as the server state before it. |
| `streams-update-callback` | S | A connection-wide update callback is called once per update. |
| `streams-scoped-removal` | S | The language's scope idiom removes the stream (Python `with`, C# `using`, Java try-with-resources). |

## Events

`test_events.py`. Profile `events`. Names follow Python's `test_event.py`.

| Id | Level | Requirement |
| --- | :-: | --- |
| `events-event` | M | An event from a procedure returning an event fires and `wait` returns. |
| `events-event-using-lambda` | M | An event built by the service from a lambda fires. |
| `events-custom-event` | M | An event from `AddEvent` over an expression fires. Profile: `functions`. |
| `events-procedure-returning-an-event` | M | A procedure returning an event can also be streamed as a stream of bool. |
| `events-firing-before-wait` | M | A firing before the first `wait` is kept. |
| `events-firings-coalesce` | M | Several firings before a `wait` make it return once. |
| `events-two-threads-wait-on-one-event` | M | Two threads waiting on one handle both return. Profile: `threads`. |
| `events-event-timeout-short` | M | `wait(timeout)` returns false on timeout. |
| `events-event-timeout-long` | M | `wait(timeout)` returns true on a firing. |
| `events-event-loop` | M | Repeated waits see each firing of a repeating event. |
| `events-event-callback` | M | A callback is called once per firing after it is added. |
| `events-event-remove-callback` | M | A removed callback is not called. |
| `events-callback-added-after-a-wait-is-not-called` | M | A late callback does not replay a firing a `wait` already saw. |
| `events-callback-added-after-an-unseen-firing-is-called` | M | A late callback replays a firing nothing has seen, once. |
| `events-two-late-callbacks-do-not-both-replay-a-firing` | M | Only one late callback replays a firing. |
| `events-a-firing-passed-to-a-value-callback-is-replayed` | M | A value callback on the event's stream takes no firing. |
| `events-a-removed-callback-does-not-take-a-firing` | M | A callback removed before its replay leaves the firing. |
| `events-server-removed-event` | M | A service event that ends raises `KRPC.StreamRemovedException`, after any unseen firing. |
| `events-event-that-ends-without-firing` | M | An event that ends without firing raises on `wait`. |
| `events-remove-wakes-an-event-wait` | M | A waiter wakes on remove. Profile: `threads`. |
| `events-close-wakes-an-event-wait` | M | A waiter wakes on close. Profile: `threads`. |
| `events-end-callback-on-close` | M | An end callback is called on close. |
| `events-end-callback-on-connection-failure` | M | An end callback is called on connection failure. |

## Threading

`test_threading.py`. Profile `threads`. This page answers
[#427](https://github.com/krpc/krpc/issues/427).

| Id | Level | Requirement |
| --- | :-: | --- |
| `threading-thread-safe-connection` | M | Calls from several threads on one connection all return their own results. |
| `threading-rpc-interleaving` | M | A slow call on one thread does not block a call on another past the server's own ordering. |
| `threading-streams-added-on-several-threads` | M | Streams added concurrently are each registered. |
| `threading-callbacks-run-off-the-caller` | M | Callbacks run on a callback thread, never on a thread making a call. |
| `threading-rpc-from-a-callback` | M | A callback may make calls. |
| `threading-rpc-while-holding-a-condition` | M | A call made while holding a stream's condition returns. |
| `threading-a-blocked-callback-stalls-only-callbacks` | M | Calls and stream values carry on while a callback blocks. |
| `threading-close-from-a-callback` | M | Close from a callback ends the connection without deadlock. |
| `threading-close-from-an-end-callback` | M | Close from an end callback ends the connection without deadlock. |
| `threading-close-while-holding-a-condition` | M | Close while holding a stream's condition ends the connection. |
| `threading-close-with-a-call-in-flight` | M | Close during another thread's call fails that call with the connection error. |

## Functions

`test_functions.py`. Profile `functions`. Trees are built through each client's `KRPC.Expression`
stubs. The builders (Python's compiler, C#'s LINQ) keep their own per-client tests.

| Id | Level | Requirement |
| --- | :-: | --- |
| `functions-function-stream` | M | A function stream delivers the function's value. |
| `functions-function-stream-error` | M | An error in the function ends only its stream. |
| `functions-function-streams-over-one-function` | M | Each add of one function is a separate stream: removing one leaves the other. |
| `functions-events-over-one-function` | M | Each event over one function is separate: removing one leaves the other. |
| `functions-run-function-with-arguments` | M | `KRPC.RunFunction` runs a function with arguments and returns its value. |
| `functions-run-function-with-a-null-argument` | M | A null argument reaches the function. |
| `functions-stream-of-a-function-with-parameters-rejected` | M | A function with parameters cannot be streamed. |

## Compatibility rules

The client rules from [protocol-compatibility.md](../protocol-compatibility.md), each with its
requirement:

| Rule | Requirement |
| --- | --- |
| Skip a `Message` with no known case once the session has started | `connection-unknown-message-is-skipped` |
| Match responses by request id, never by position | `calls-responses-matched-by-id` |
| Map an unknown server exception to the generic error | `errors-unknown-exception-type` |
| Report an unknown `ConnectionResponse` status with its message | `connection-unknown-status` |
| A negotiated feature absent from the handshake is unsupported | No test until the first negotiated feature |
| The release version from `GetStatus` never gates a feature | Stated in the spec, not testable |
