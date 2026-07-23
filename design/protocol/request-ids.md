# Request ids and asynchronous RPCs

**Status:** proposal — sketch (2026-07-21), no issue filed yet; every section below needs
a real design pass before implementation.

Related: [improvements.md](improvements.md) (meta-issue
[#906](https://github.com/krpc/krpc/issues/906)),
[reverse-streams.md](reverse-streams.md) (#903 — batching, `no_response`),
[client-api-parity-audit.md](../client-api-parity-audit.md) (Python bug 25).

## Problem

The RPC protocol has no way to associate a response with the request that produced it. The
correlation is purely positional: the client sends one `Request`, then reads exactly one
`Response`, and the server never reads a second request from a client while one is still in
flight (`core/src/Core.cs:697`, guarded by `pollRequestsCurrentClients`). Three consequences:

- **No pipelining.** Every call costs a full round-trip. A client that wants to issue fifty
  calls pays fifty round-trips, even though the server would happily execute them all in one
  frame. The wire protocol's `repeated ProcedureCall calls` field exists for this, but no
  bundled client exposes it.
- **A yielding RPC stalls the whole connection.** `YieldException` re-queues the continuation
  for the next `FixedUpdate` and the client stays in `pollRequestsCurrentClients`, so nothing
  else that client sends is even read until the yield resolves. `WarpTo` and friends make the
  connection unusable for their duration.
- **Desynchronization is silent and permanent.** If a client is interrupted between
  `send_message` and `receive_message`, the buffered response is never consumed and every
  later call reads the *previous* call's result, forever. This is Python bug 25
  (`client/python/krpc/client.py:207-211`); a Ctrl-C during a slow RPC is enough to trigger
  it. With no id on the wire, neither side can detect it.

## Sketch

Add an id to `Request` and echo it on `Response`:

```protobuf
message Request {
  repeated ProcedureCall calls = 1;
  uint64 id = 2;
}

message Response {
  Error error = 1;
  repeated ProcedureResult results = 2;
  uint64 id = 3;
}
```

Additive and backwards compatible in both directions: proto3 ignores unknown fields, and `0`
(the default) means "no id", which is what an old client sends and what an old server echoes
back as absent. The id is client-allocated, opaque to the server, and scoped to the
connection — the server only copies it.

**Echoing is unconditional.** Even with no other change, a client that sets an id and checks
it on receipt turns bug 25 from silent permanent corruption into a detectable, recoverable
error. That is worth landing on its own, before any concurrency work.

### Negotiating concurrency

Echoing an id is safe for everyone. *Allowing more than one request in flight* is not — it
changes the server's per-client scheduling and its exposure to a client that floods it. So
gate that behind a per-connection opt-in, and default it off:

- Add a field to `ConnectionRequest` (e.g. `uint32 max_requests_in_flight`, `0`/absent =
  today's behavior of 1), and have `ConnectionResponse` report what the server actually
  granted, so an old server (which ignores the field and reports nothing) is indistinguishable
  from one that refused. The client then knows whether it may pipeline.
- The granted value is also the server's flood defense: it caps the per-client queue depth,
  and the server stops reading from that socket at the cap. TCP backpressure does the rest.

The alternative — a `KRPC.SetAsyncEnabled` RPC after connecting — avoids touching
`ConnectionRequest` but has an awkward window where the client doesn't yet know the answer.
Prefer the connection-time field.

## Ordering

The central question, and the one to get right before anything else.

**Execution order must stay strictly FIFO per client.** kRPC calls have side effects on a
shared mutable game state; `control.throttle = 1` followed by `control.activate_next_stage()`
means something, and a client that pipelines them must get that meaning. Reordering execution
would make pipelining unusable for anything except pure reads, which is most of the value
gone. This is non-negotiable and should be stated in the protocol docs, not left implicit.

**Given FIFO execution, responses are naturally in order too**, including for yielding calls —
a yielded call simply holds up the ones behind it, exactly as today, except that the client
may keep *sending*. That is already a large win (N calls, one round-trip) and it is the
version to build first, because it requires no new semantics anywhere: the client's existing
mental model still holds.

So the phasing is:

**Phase 1 — ids only.** Echo, validate on the client, detect desync. Fixes bug 25. No
scheduling change, no negotiation needed.

**Phase 2 — pipelining, in-order.** Per-client FIFO queue in `Core.RPCServerUpdate`, bounded
by the negotiated depth, replacing the one-in-flight guard at `core/src/Core.cs:697`.
Responses stay ordered. Clients gain a "send now, collect later" API.

**Phase 3 — out-of-order completion, opt-in per call.** Only here do responses stop being
ordered, and only for calls the client explicitly marks as overtakeable (a flag on
`ProcedureCall`, or a server-declared property of procedures known to yield, such as
`WarpTo`). A marked call that yields moves out of the head-of-line position and later calls
proceed past it; its response arrives whenever it completes. This is the piece that genuinely
needs the id, and the piece that needs the most vetting — it is the only place where two
calls' effects can interleave in an order the client did not write.

Phase 3 may well not be worth it. Evaluate it against the alternative of just telling users to
open a second connection for long-running calls, which costs nothing and is already possible.

## Relationship to batching

Keep `repeated ProcedureCall calls`. Pipelining does not subsume it: all calls in one
`Request` are executed within a single `RequestContinuation`
(`core/src/Service/RequestContinuation.cs:52-84`) and therefore in the same frame, which
pipelined separate requests do not guarantee. That same-frame grouping is a real semantic —
it is the "read `ut` and position coherently" property that stream freezing was trying to
provide — and it composes with ids rather than competing with them (one id per `Request`,
whatever its call count). The field also costs nothing to keep.

The `no_response` flag from [reverse-streams.md](reverse-streams.md) is
orthogonal and complementary: fire-and-forget for writes, ids for reads you will collect
later. A `no_response` request simply produces no response to correlate.

## Client APIs

The natural shape, once the server allows it, is a **demultiplexing reader**: one thread (or
task) owns the RPC socket, reads responses, matches each id to a pending future, and resolves
it. Every higher-level API is then a thin layer on that:

- synchronous call = submit, await the future immediately (what all clients do today);
- pipelined batch = submit N, await all N;
- asyncio = the futures are `asyncio.Future`s and the reader is a protocol/transport.

This also removes the Python client's whole-process `_rpc_connection_lock`
(`client/python/krpc/client.py:40`), under which a yielding RPC currently blocks every thread
in the client, not just the caller.

For Python specifically, an `async` surface is a bigger question than the protocol work: it
means either a parallel `krpc.aio` package with generated async stubs (clientgen work,
doubling the generated surface) or an async-capable client that the existing sync API wraps.
Decide that separately — the protocol change does not depend on it, and phases 1 and 2 are
useful to the sync clients on their own.

## Open questions

- Does the round-robin scheduler plus a global (not per-client) `MaxTimePerUpdate`
  (`core/src/Core.cs:420`) still give fair service when one client can queue many requests?
  Probably needs a per-client execution budget, or at least a check that a deep queue cannot
  starve other clients.
- What does the connection-close path do with queued-but-unexecuted requests? Silently drop
  seems right; confirm against [`client-disconnect-cleanup.md`](client-disconnect-cleanup.md).
- SerialIO has no flow control worth the name — should the negotiated depth be forced to 1
  there?
- Should the id be per `Request` or per `ProcedureCall`? Per `Request` is simpler and matches
  the response shape; per-call only matters if phase 3 lets calls *within* a request complete
  independently, which it should not.
- Interaction with stream invalidation (#877) and refcounting (#902): none expected, since
  streams use a separate connection, but confirm the stream connection's own request path
  (`AddStream`/`RemoveStream` are ordinary RPCs on the RPC connection).
