# Protocol compatibility from 0.8 to 1.0

**Status:** reference (2026-10-21). A check of the planned 1.0 protocol work against the 0.8 break,
and the rules that keep 1.0 additive. Re-check it when a 1.0 item gets its detailed design.

0.8 is a hard break: the [single connection](protocol/single-connection.md),
[request ids](protocol/request-ids.md), as [protocol version 2](protocol/protocol-version.md). 1.0
adds the rest of [#906](https://github.com/krpc/krpc/issues/906) and the server side function
follow-ups. The aim is that 1.0 stays on protocol version 2, so a 0.8 client works against a 1.0
server without the new features.

## Verdict

Every 1.0 item can land as an addition, given the rules below. Tick control
([#251](https://github.com/krpc/krpc/issues/251)) is the exception that cannot be judged yet, since
its protocol design is open.

## Rules 0.8 must fix

These are written into [protocol-version.md](protocol/protocol-version.md) under "Additive changes".
In short:

| Rule | Why |
| --- | --- |
| A feature that changes how a request is read is negotiated in the handshake, and absent means unsupported | An older server ignores an unknown field without an error |
| The server sends a new message kind only to a client granted it | A 0.8 client cannot handle what it does not know |
| A client skips a `Message` with no known case set, once a session has started | Proto3 parses a newer message kind as nothing set, including in a `oneof` |
| A client matches responses by request id, never by position | Out-of-order completion is then additive |
| A client maps an unknown server exception to its generic error | New features raise new `KRPC` exceptions |
| A client reports an unknown `ConnectionResponse` status with its message | New features may refuse a connection |
| The release version from `GetStatus` never gates a feature | Release versions of the server and clients will move apart |

Each client-side rule is pinned by the [conformance suite](client-conformance/README.md).

What an older server does with each request-level field it does not know:

| Field | Older server | Without negotiation |
| --- | --- | --- |
| `Request.no_response` | Sends a response | A response the client does not expect |
| Reverse stream pushes | Drops them | Control writes silently lost |
| Per-call out-of-order flag | Runs the call in order | Calls behind a slow one wait, the flag has no effect |
| Intra-request result references (rejected in [batched-tree-construction.md](server-side-functions/batched-tree-construction.md)) | Decodes an empty argument | The call runs with the wrong argument |

## The 1.0 items

| Item | Design | Wire change | 0.8 clients |
| --- | --- | --- | --- |
| Batching | [reverse-streams.md](protocol/reverse-streams.md) rung 1 | None, multi-call `Request` exists | Unaffected |
| Fire-and-forget | [reverse-streams.md](protocol/reverse-streams.md) rung 2 | `Request.no_response`, negotiated | Unaffected, never set it |
| Reverse streams | [reverse-streams.md](protocol/reverse-streams.md) rung 3 | A push field and new `KRPC` RPCs, negotiated. Errors use the existing `StreamResult` | Unaffected, never register one |
| Out-of-order completion | [request-ids.md](protocol/request-ids.md) phase 3 | A per-call flag, negotiated | Unaffected, never set it |
| Tick control | [tick-hold.md](server/tick-hold.md) is the stopgap, design open | Unknown | See below |
| Function release | [function-release.md](server-side-functions/function-release.md) | `KRPC.RemoveFunction` | See below |
| Shared nodes | [shared-nodes.md](server-side-functions/shared-nodes.md) | None, server internal. Removes `MaxNodes` | Unaffected, a bound is lifted |
| Batched tree construction | [batched-tree-construction.md](server-side-functions/batched-tree-construction.md) | None, client side | Unaffected |
| C# functions with statements | [csharp-statement-functions.md](server-side-functions/csharp-statement-functions.md) | None, client side | Unaffected |
| Deferred calls | [yielding-procedures.md](server-side-functions/yielding-procedures.md) | New `Expression` factories | Unaffected |
| Resumable functions | [yielding-procedures.md](server-side-functions/yielding-procedures.md) | None. `RunFunction` keeps its signature | A function that errored now spans ticks, as a yielding RPC does |
| Arbitrary expressions | [server-side-arbitrary-expressions.md](server-side-functions/server-side-arbitrary-expressions.md) | New factories and a setting. `TypeCode.Foreign` never reaches the wire | Unaffected |

## Breaks at the service level

The protocol version does not cover services, which are not versioned. A 1.0 server can still break
a 0.8 client by removing a procedure or changing what one means. Two items are at risk:

* **Tick control.** It must be opted into per connection, and must leave the default scheduling
  (polling, `OneRPCPerUpdate`) alone for a client that does not ask. `HoldTick`, `ReleaseTick` and
  `NextTick` are deprecated in 1.0, not removed.
* **Function release.** If a function stream or event owns its function and releases it on removal
  (its open question 1), a 0.8 client that removes a function stream and runs the same function
  again gets an invalid object. Removing a stream must leave its function alone. Phase 1 also
  changes one behavior: a node stops resolving once the client that built it disconnects. That case
  needs a node passed between clients, so it is accepted.

## Related

* [protocol/improvements.md](protocol/improvements.md), the overview of #906.
* [client-conformance/README.md](client-conformance/README.md), "Sequencing".
