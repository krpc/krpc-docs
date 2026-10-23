# Request ids and asynchronous RPCs

**Status:** in progress (2026-10-22): phase 1 implemented locally with the single connection, not yet
in a PR. Built together with the
[single connection](single-connection.md) for 0.8, as part of
[protocol version](protocol-version.md) 2. Phases 2 and 3 are later additions, each negotiated in
the handshake. Issue drafted in [issues/request-ids.md](../../issues/request-ids.md).

Related: [single-connection.md](single-connection.md) (its "Client reader" section specifies the
client side of phase 1), [improvements.md](improvements.md) (meta-issue
[#906](https://github.com/krpc/krpc/issues/906)), [reverse-streams.md](reverse-streams.md) (#903,
batching and `no_response`), [protocol-compatibility.md](../protocol-compatibility.md),
[client-conformance/defects.md](../client-conformance/defects.md) (Python bug 25 of the parity audit).

## Problem

A response is matched to its request by position only. The client sends one `Request` and reads one
`Response`. The server reads no second request from a client while one is in flight
(`pollRequestsCurrentClients` in `Core.PollRequests`). Three consequences:

- **No pipelining.** Every call costs a round trip. `repeated ProcedureCall calls` batches calls in
  one request, but no bundled client exposes it.
- **A yielding RPC stalls the connection.** `YieldException` requeues the continuation for the next
  update and the client stays in `pollRequestsCurrentClients`. `WarpTo` makes the connection
  unusable while it runs.
- **Desynchronization is silent and permanent.** An exception between the client's send and receive
  leaves the response unread, and every later call reads the previous call's result. This is Python
  bug 25 (`Client._invoke`). A Ctrl-C during a slow RPC triggers it.

It is also why the server needs a second connection for streams. See
[single-connection.md](single-connection.md).

## Wire format

```protobuf
message Request {
  uint64 id = 2;
  repeated ProcedureCall calls = 1;
}

message Response {
  uint64 id = 3;
  Error error = 1;
  repeated ProcedureResult results = 2;
}
```

- The id is client-allocated, scoped to the session and opaque to the server, which copies it. A
  reconnect starts a new session (see [single-connection.md](single-connection.md) "Reconnecting").
- Every version 2 client sets it, starting at 1. 0 is never sent.
- One id per `Request`, whatever its call count. A response answers a whole request, and calls
  within a request never complete independently.
- A client matches a response by id, never by position. This keeps phase 3 additive
  ([protocol-compatibility.md](../protocol-compatibility.md)).

## Ordering

**Execution stays strictly FIFO per client.** kRPC calls have side effects on shared game state.
`control.throttle = 1` followed by `control.activate_next_stage()` means something, and a client
that pipelines them must get that meaning. The protocol docs state this.

Given FIFO execution, responses are in order too, including for yielding calls: a yielded call
holds up the ones behind it, as today.

## Phases

| Phase | Release | Work | Negotiated |
| --- | --- | --- | --- |
| 1, ids | 0.8, with the single connection | The fields above. Server echoes the id. Clients match by id through the reader in [single-connection.md](single-connection.md). | No, part of version 2 |
| 2, pipelining | Later, additive | Per-client FIFO queue on the server, bounded by a negotiated depth. A client API to send now and collect later. | Yes |
| 3, out-of-order completion | Later, additive, may never be built | A per-call flag lets a yielding call step out of the head of the line. | Yes |

### Phase 1

Server, in the version 2 connection of [single-connection.md](single-connection.md):

- `ExecuteContinuation` and `SendErrorResponse` copy the request's id onto the response.
  `RequestDecodeException` carries the id for a request that parses but fails to decode.
- A message that does not parse, or a request that fails to read, ends the connection with a
  `disconnect`, since there is no id to answer with.
- No scheduling change. The one-in-flight guard in `PollRequests` stays.

Client: the "Calls" rules in [single-connection.md](single-connection.md). In short, a pending slot
per id, added before the write; a write lock per message; the reader fills slots by id; an
abandoned slot's response is discarded; an unknown id is a protocol error. Lua and cnano read until
the response with their id.

What phase 1 gives on its own:

- **Bug 25 is fixed.** An interrupted call abandons its slot, and its response is discarded on
  arrival.
- **Threads stop queuing on the client.** Several threads can write requests at once. The server
  still runs them one at a time, and TCP holds the rest. Python's `_rpc_connection_lock` goes, so a
  yielding call on one thread no longer blocks every thread's send.
- **Desync is detectable.** A response with an unexpected id closes the connection with an error.

### Phase 2

- Replace the one-in-flight guard in `PollRequests` with a per-client FIFO queue.
- The depth is a negotiated feature with a value: a field in `ConnectionRequest`, and the granted
  value in `ConnectionResponse`. Absent is a depth of 1, today's behavior. See "Additive changes" in
  [protocol-version.md](protocol-version.md).
- The granted depth is also the server's flood defense: the server stops reading from a client at
  the cap, and TCP backpressure does the rest.
- Clients gain a "send now, collect later" API on top of the reader.

### Phase 3

Only here do responses stop being ordered, and only for calls the client marks as overtakeable. A
marked call that yields leaves the head of the line, later calls proceed past it, and its response
arrives when it completes. This is the one place two calls' effects can interleave in an order the
client did not write.

Evaluate it against telling users to open a second connection for long-running calls, which costs
nothing and already works.

## Relationship to batching

Keep `repeated ProcedureCall calls`. All calls in one `Request` run in one `RequestContinuation`,
and so in the same update, which separate pipelined requests do not guarantee. That same-update
grouping is a real semantic, and composes with ids: one id per `Request`.

The `no_response` flag from [reverse-streams.md](reverse-streams.md) is complementary:
fire-and-forget for writes, ids for reads collected later. A `no_response` request produces no
response to correlate.

## Client APIs

The reader in [single-connection.md](single-connection.md) is the base for every higher-level API:

- synchronous call: submit, then wait on the slot at once (phase 1, what every client does);
- pipelined batch: submit N, then wait on all N (phase 2);
- asyncio: the slots are `asyncio.Future`s.

A Python `async` surface is a separate question: a parallel `krpc.aio` package with generated async
stubs, or an async-capable client that the sync API wraps. The protocol work does not depend on it.

## Open questions

All for phase 2 or later. Phase 1 has none.

- Does the round-robin scheduler with a global `MaxTimePerUpdate` give fair service when one client
  can queue many requests? Probably needs a per-client budget, or at least a check that a deep queue
  cannot starve other clients.
- What happens to queued but unexecuted requests on disconnect? Dropping them seems right. Confirm
  against [client-disconnect-cleanup.md](client-disconnect-cleanup.md).
- SerialIO has no flow control worth the name. Should its granted depth be fixed at 1?
