# Client defects and decisions

What the client API parity audit (2026-07-21) and its Python sweep found, re-checked on the single
connection branch, with the parity and the rulings that followed. "Audit n" is the audit's bug
number.

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

C4 and C5 recorded their defects and fixed none, as client fixes follow the suite as their own work.

C3 found and fixed a C++ crash on decoding a tuple of the wrong length, and a C# nullable enum return, which threw `InvalidCastException` as the decoder
returned the enum's integer value.

Two lessons from the audit stand:

- **A reference client is not checked by comparison.** Python was the reference and had 26 defects
  the comparison could not find.
- **A shared design copies its bugs.** The lock order inversion (audit 7, 22, 50) and the
  overwritten removal marker (27, 51) were one design, ported to four clients.

## Open defects

The defects still open moved to the client defects issues on 2026-11-09, one per client, with
[client-design-shared-defects.md](../../issues/client-design-shared-defects.md) for those several
clients share. Each names the conformance test that catches it. Those fixed by then were dropped:
C++ close and exception registration, the C# removed-stream type, the dropped disconnect reason,
the unknown status crashes outside C-nano, and the Lua and C-nano malformed messages.

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
