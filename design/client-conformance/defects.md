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
is gone in all four clients, which now count firings per handle.

Two lessons from the audit stand:

- **A reference client is not checked by comparison.** Python was the reference and had 26 defects
  the comparison could not find.
- **A shared design copies its bugs.** The lock order inversion (audit 7, 22, 50) and the
  overwritten removal marker (27, 51) were one design, ported to four clients.

## Open defects

| Id | Client | Defect | Audit | Requirement |
| --- | --- | --- | --- | --- |
| `python-exception-classes` | Python | The stub declares its own `ArgumentException(RuntimeError)`, but the client raises the builtin `ValueError`, so `except conn.krpc.ArgumentException` never fires. Only the dynamic path agrees with itself. | 26 | `errors-raised-type-is-the-exposed-type` |
| `python-static-method-binding` | Python | `StaticMethod.__get__` writes `_client` onto the shared stub class, so the first client to call a static method through an instance binds it for every client. | 32 | `objects-types-from-different-connections` |
| `python-subclass-leak` | Python | `_wrapped_subclasses` values strongly reference their weak keys, so every client graph leaks. | 33 | per-client test |
| `python-string-as-list` | Python | Any iterable coerces to a list, so a string becomes a list of characters. | 34 | `values-string-is-not-a-list` |
| `python-object-equality` | Python | Equality and hash use the id only, ignoring class and connection. | 35 | `objects-different-classes-are-not-equal` |
| `python-integer-range` | Python | Call encoding checks only for negatives. `2**32+1` to a `uint32` arrives as 1. `run()` range-checks, plain calls do not. | 36 | `values-integer-out-of-range` |
| `python-enum-member-names` | Python | Enum members keyed by snake case collapse names differing in case, and a member snake casing to `mro` fails `connect()`. | 38 | per-client test |
| `python-parameter-name-clash` | Python | A parameter named `cls`, or two differing only in case, fails `connect()` with a `SyntaxError`. | 39 | per-client test |
| `python-procedure-property-clash` | Python | A procedure and a property with one name: the procedure is lost. | 40 | per-client test |
| `python-unpruned-stubs` | Python | All 12 generated services are attached whether or not the server has them. | 41 | `objects-member-rosters` |
| `python-tuple-arity` | Python, Java | A short wire tuple decodes short. Structs check their field count. | 43 | `codec-tuple-arity` |
| `python-unclosed-client` | Python | A dropped unclosed client keeps its threads and socket. The threads now exit when the server closes. | 45 | per-client test |
| `python-wait-in-callback` | Python, and by design every threaded client | A callback that waits on a stream deadlocks, as only the dispatcher wakes waiters. Documented, not guarded. | 46 | Spec states it. Raising in place of hanging is a SHOULD to decide |
| `shared-event-handles` | Python | Two `Event` objects for one server event share a stream, so removing either ends both. | 47 | `streams-remove` (removal ends every copy, by design since #1122) |
| `python-error-reporting` | Python | An `ImportError` from a stub silently downgrades every service to dynamic. Ordering operators raise `NotImplementedError` in place of returning `NotImplemented`. Docstrings lost when a type is first built from another service is not re-checked. | 48 | per-client test |
| `cpp-dropped-stream-handle` | C++ | Dropping the last handle never sends `RemoveStream`. The server stream runs for the connection's life. Documented in `doc/src/cpp/client.rst`. | 11 | `streams-dropped-handle` |
| `cpp-error-stack-trace` | C++ | The server stack trace is dropped. | divergence 4 | `errors-message` |
| `cpp-client-destructor-doc` | C++ | The docs describe a `~Client()`. The connection closes when the last copy is released. | doc error | none, docs only |
| `csharp-error-format` | C# | `Server stack trace: ` has a trailing space. `ArgumentNull` and `ArgumentOutOfRange` get an empty parameter name. | divergence | `errors-message`, `errors-mapped-exceptions` |
| `java-exception-table` | Java | No `Timeout` mapping, and different native picks from Python and C#. | new | `errors-mapped-exceptions` |
| `codec-nan-vectors` | C#, Lua, core | The NaN vectors are the sign-set `...ff`, others `...7f`. Each is a NaN, so this is a vector drift, not a codec bug. | new | `codec-nan` |
| `lua-cnano-stall` | Lua, cnano | No stall timeout: a stalled message blocks a call. cnano POSIX and Windows have no read timeout at all. | divergence 6 | `connection-stall` (a SHOULD) |
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

Open, to settle as part of this work. Each changes a requirement. The native exception choices,
Python's exception classes and the error message format are settled in
[client-codegen.md](../client-codegen.md) "Decisions".

| Decision | Options | Requirement |
| --- | --- | --- |
| Lua streams | Add them, or rule them out and hide the inert `add_stream`/`add_event` on `conn.krpc`. The blocker is Lua's single thread. | `streams` profile for Lua |
| C++ dropped stream handle | Rule it intended under explicit removal (#1122), or remove the stream with the last handle. | `streams-dropped-handle` |
| Waiting in a callback | Leave as documented, or detect and raise. | `python-wait-in-callback` |
| Java stream creation | Keep the method name form, or move toward a typed form. Only Java's form is not compile-time checked. | none, API design |
