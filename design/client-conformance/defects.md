# Client defects and decisions

What the client API parity audit (2026-07-21) and its Python sweep found that is still open,
re-checked on the single connection branch. Each defect names the requirement that catches it, so
it lands in an expected-failures file until fixed. "Audit n" is the audit's bug number.

## Fixed since the audit

Audit 1 to 10, 12 to 15 and 17 to 22, 49 to 51 in [PR #1002](https://github.com/krpc/krpc/pull/1002),
[#1003](https://github.com/krpc/krpc/pull/1003), [#1004](https://github.com/krpc/krpc/pull/1004),
[#1005](https://github.com/krpc/krpc/pull/1005), [#1007](https://github.com/krpc/krpc/pull/1007),
[#1008](https://github.com/krpc/krpc/pull/1008) and [#1065](https://github.com/krpc/krpc/pull/1065).
Audit 16, 27, 28, 30, 44, and the value half of 47, by the stream and event rework
([#1122](https://github.com/krpc/krpc/pull/1122)). Audit 23, 24 in #1008. Audit 25, 29, 31, 37
and 42 by the single connection. The event `wait` divergence (a timeout read from a value reset)
is gone in all four clients, which now count firings per handle. Client codegen G1
([client-codegen.md](../client-codegen.md), #1172) fixed audit 26 (Python exception classes), the C++
dropped stack trace, the C# trailing space and the Java exception table.

C3 found and fixed a C++ crash on decoding a tuple of the wrong length, and a C# nullable enum return, which threw `InvalidCastException` as the decoder
returned the enum's integer value.

Two lessons from the audit stand:

- **A reference client is not checked by comparison.** Python was the reference and had 26 defects
  the comparison could not find.
- **A shared design copies its bugs.** The lock order inversion (audit 7, 22, 50) and the
  overwritten removal marker (27, 51) were one design, ported to four clients.

## Open defects

| Id | Client | Defect | Audit | Requirement |
| --- | --- | --- | --- | --- |
| `python-static-method-binding` | Python | `StaticMethod.__get__` writes `_client` onto the shared stub class, so the first client to call a static method through an instance binds it for every client. | 32 | `objects-types-from-different-connections` |
| `python-subclass-leak` | Python | `_wrapped_subclasses` values strongly reference their weak keys, so every client graph leaks. | 33 | per-client test |
| `python-string-as-list` | Python | Any iterable coerces to a list, so a string becomes a list of characters. | 34 | `values-string-is-not-a-list` |
| `python-object-equality` | Python | Equality and hash use the id only, ignoring class and connection. | 35 | `objects-different-classes-are-not-equal` |
| `python-integer-range` | Python | Call encoding checks only for negatives. `2**32+1` to a `uint32` arrives as 1. `run()` range-checks, plain calls do not. | 36 | `values-integer-out-of-range` |
| `python-enum-member-names` | Python | Enum members keyed by snake case collapse names differing in case, and a member snake casing to `mro` fails `connect()`. | 38 | per-client test |
| `python-parameter-name-clash` | Python | A parameter named `cls`, or two differing only in case, fails `connect()` with a `SyntaxError`. | 39 | per-client test |
| `python-procedure-property-clash` | Python | A procedure and a property with one name: the procedure is lost. | 40 | per-client test |
| `python-unpruned-stubs` | Python | All 12 generated services are attached whether or not the server has them. | 41 | `objects-member-rosters` |
| `python-tuple-arity` | Python, Lua, cnano | A short wire tuple decodes short. Structs check their field count. Java has since been fixed, and C++ crashed on one until C3. | 43 | `codec-tuple-arity` |
| `python-unclosed-client` | Python | A dropped unclosed client keeps its threads and socket. The threads now exit when the server closes. | 45 | per-client test |
| `python-wait-in-callback` | Python, and by design every threaded client | A callback that waits on a stream deadlocks, as only the dispatcher wakes waiters. Documented, not guarded. | 46 | Spec states it ("Decisions") |
| `shared-event-handles` | Python | Two `Event` objects for one server event share a stream, so removing either ends both. | 47 | `streams-remove` (removal ends every copy, by design since #1122) |
| `python-error-reporting` | Python | An `ImportError` from a stub silently downgrades every service to dynamic. Ordering operators raise `NotImplementedError` in place of returning `NotImplemented`. Docstrings lost when a type is first built from another service is not re-checked. | 48 | per-client test |
| `cpp-client-destructor-doc` | C++ | The docs describe a `~Client()`. The connection closes when the last copy is released. | doc error | none, docs only |
| `csharp-argument-parameter-name` | C# | `ArgumentNull` and `ArgumentOutOfRange` get an empty parameter name (`Connection.cs` `new ArgumentNullException(string.Empty, message)`). | divergence | `errors-mapped-exceptions` |
| `codec-nan-vectors` | C#, Lua, core | The NaN vectors are the sign-set `...ff`, others `...7f`. Each is a NaN, so this is a vector drift, not a codec bug. | new | `codec-nan` |
| `lua-cnano-stall` | Lua, cnano | No stall timeout: a stalled message blocks a call. cnano POSIX and Windows have no read timeout at all. | divergence 6 | `connection-stall` (a SHOULD) |
| `csharp-call-after-dispose` | C# | A call after `Dispose` raises `ObjectDisposedException`, not the connection error. | C2 | `connection-calls-after-close-raise` |
| `java-wrapped-connection-error` | Java | A call after close raises `RPCException("Failed to invoke call")`, with the `ConnectionException` as its cause. | C2 | `connection-calls-after-close-raise` |
| `cpp-no-close` | C++ | A `Client` has no close. It closes when the last copy is destroyed, so no call can follow a close. | C2 | `connection-calls-after-close-raise` |
| `cpp-exception-registration` | C++ | The `KRPC` exception types are registered by constructing a `KRPC` service object. A program that never does gets `RPCError` and the `KRPC.Name: ` prefix. | C2 | `errors-mapped-exceptions`, `errors-message` |
| `lua-error-position` | Lua | RPC errors are raised with `error(msg)`, so the message starts with the client's source position (`client.lua:136: `). | C2 | `errors-mapped-exceptions`, `errors-message` |
| `lua-invalid-enum` | Lua | An enum type takes any number, so an out-of-range value is sent. | C3 | `values-invalid-enum` |
| `lua-integer-range` | Lua | The encoder does not check an integer against its parameter's type. | C3 | `values-integer-out-of-range` |
| `lua-extra-arguments` | Lua | Arguments past the last parameter are dropped, not rejected. | C3 | `calls-too-many-arguments` |
| `cnano-unknown-response-id` | cnano | A response with an unknown id is taken as the result of the waiting call. | C3 | `calls-unknown-response-id` |
| `lua-uint64-range` | Lua | A `uint64` above the `sint64` range decodes as a negative integer, as Lua integers are signed 64-bit. | C3 | `calls-special-defaults` |
| `lua-cnano-refusal-status` | Lua, cnano | A refused connection reports its status only inside the message. | C2 | `connection-refused` |
| `cnano-no-drain` | cnano | `krpc_disconnect` sends the `disconnect` and closes, with no half-close or drain. By design in the single connection, but the spec makes the drain a MUST. | C2 | `connection-close` |
| `cnano-error-message-length` | cnano | The error message is cut to `KRPC_ERROR_MESSAGE_LENGTH` (256), which cuts the stack trace. | C2 | `errors-message` |
| `messages-doc-client-name` | docs | `messages.rst` does not mention `GetClientName`. | doc error | none, docs only |

## Parity

Where the clients differ in what they offer, as of the single connection branch.

| | Python | C# | C++ | Java | Lua | cnano |
| --- | --- | --- | --- | --- | --- | --- |
| Close | `close`, context manager | `Dispose` | last copy released | `AutoCloseable` | `close` | `krpc_disconnect` |
| Connect timeout | yes | yes | yes | yes | no | no |
| Handshake timeout | yes | yes | yes | yes | yes | no |
| Stall timeout | yes | yes | yes | yes | no | Arduino only |
| Local socket | yes | yes | yes | yes | yes | transport hook |
| Streams, events, functions | yes | yes | yes | yes | no | no |
| Scoped stream removal | yes | no | no | no | - | - |
| Connection-wide update callback | yes | no | yes | no | - | - |
| Batching or async calls | no | no | no (`invoke` takes a batch, returns the first result) | no | no | no |
| Stream creation | bound method or `getattr` | lambda | `_stream` members | method name string | - | - |
| Service discovery | stubs, then dynamic | stubs | stubs | stubs | dynamic | stubs |

Concurrent calls from several threads pipeline over one socket in the four threaded clients, as
only the write is locked. No client exposes the handshake's client id, reconnection, or a per-call
deadline.

## Decisions

Ruled 2026-10-23. The native exception choices, Python's exception classes and the error message
format are ruled in [client-codegen.md](../client-codegen.md) "Decisions".

| Decision | Ruling | Requirement |
| --- | --- | --- |
| Lua streams | Out of 0.8. Lua's single thread is the blocker. Hide the inert `add_stream`/`add_event` on `conn.krpc`. | No `streams` profile for Lua |
| C++ dropped stream handle (audit 11) | Intended: removal is explicit since #1122, in every client. Dropping a handle leaves the stream, as `doc/src/cpp/client.rst` documents. | None. What a dropped handle does is left to each client |
| Waiting in a callback | Stays documented. Detecting it and raising can be a later SHOULD. | Spec states it |
| Java stream creation | The method name form stays. A typed form is API design, outside this work. | None |
