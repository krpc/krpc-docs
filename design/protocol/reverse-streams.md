# Reverse streams (issue #903)

**Status:** proposal — design agreed, not yet implemented (2026-07-03). Planned for 1.0. Revised
2026-10-21 for the 0.8 single connection, request ids and protocol version. The code references
are from before 0.8. On 2026-10-25 non-blocking calls and fire-and-forget moved to their own docs.

One of three designs under [issue #903](https://github.com/krpc/krpc/issues/903), which is tracked
as one issue: [non-blocking calls and batching](non-blocking-calls.md),
[fire-and-forget](fire-and-forget.md), **reverse streams**. Each ships on its own, in that order.

Register a call once, then push latest-wins argument updates that the server applies **at most
once per tick**. Errors invalidate the reverse stream and arrive as a `StreamUpdate` using the
#877 error convention. Use is gated on a feature granted in the handshake, as for
[fire-and-forget](fire-and-forget.md). Schema additions are plain proto3 fields and messages
(Unity protobuf 3.10.1, protobuf-lua).

## Context

* **Execution is FIFO per client**, round-robin across clients. Phase 2 of
  [request ids](request-ids.md) replaces the server's one-in-flight guard with a per-client FIFO
  queue.
* **One connection carries both directions.** From 0.8 each client has a single connection
  ([single-connection.md](single-connection.md)), framed as `Message` in both directions on every
  transport, SerialIO included. Pushes travel client to server on it, and invalidation errors come
  back on it as a `StreamUpdate`.
* **Prior art.** Latest-wins-per-tick evaluation is the forward stream loop
  (`Core.StreamServerUpdate`). Server-side call storage is `Expression.Call`.
* **Why not [fire-and-forget](fire-and-forget.md) alone.** A burst of writes each executes.
  Latest-wins makes a high-rate control loop backpressure-proof.

## Design

**Schema** (where the pushes go is open question 3):

```proto
message Request {
  repeated ProcedureCall calls = 1;
  bool no_response = 2;
  repeated ReverseStreamUpdate reverse_updates = 3;
}

message ReverseStreamUpdate {
  uint64 id = 1;
  repeated Argument arguments = 2;   // full replacement argument list
}
```

**New KRPC-service RPCs** (`core/src/Service/KRPC/KRPC.cs`):

- `AddReverseStream(ProcedureCall call) → Stream` — validates the procedure and initial
  arguments, registers, returns an id **allocated from the same `nextStreamId` counter
  as forward streams** (shared id space, so the `StreamUpdate` error channel is
  unambiguous). No dedup or refcounting: each add is a fresh id (unlike forward
  streams there is no bandwidth reason to share, and #902-style sharing surprises are
  avoided by construction).
- `RemoveReverseStream(uint64 id)` — idempotent.

**Server registry + executor** (`core/src/Core.cs`):

- Per RPC client: `Dictionary<ulong, ReverseStream>` where `ReverseStream` holds the
  procedure signature, the latest decoded argument list, and a dirty flag.
- `PollRequests` applies `reverse_updates` immediately on read (argument decode +
  latest-wins replacement + dirty mark; unknown id is silently ignored — it races with
  removal, matching `RemoveStream` idempotence). A request with only pushes creates no
  continuation; clients always send pushes with `no_response = true` (a push with
  `no_response = false` gets an empty `Response` as a synchronous flush).
- Each `RPCServerUpdate`, after the poll block and before regular continuations:
  execute every dirty reverse stream once with its latest arguments, clear dirty,
  counted against the same time budget. **Latest-wins**: superseded pushes cost only
  parsing, never execution — this is what makes high-rate control loops
  backpressure-proof, the property fire-and-forget alone lacks.
- **Errors invalidate**: an exception from the stored call (via
  `Services.HandleException`), or a `YieldException` (reverse-stream calls must not
  yield — control setters never do), removes the reverse stream and sends a
  `StreamResult { id, result.error }` in a **`StreamUpdate` exactly once** —
  reusing the [#877 invalidation convention](stream-invalidation.md) verbatim; client
  stream managers route errors for reverse ids to the reverse-stream wrapper. A client
  that never registers a reverse stream never receives one of these errors.
- Client disconnect tears down its reverse streams, beside the forward-stream cleanup.
- Whether a push behind an in-flight multi-tick RPC applies at once or waits for it is
  open question 2. Until settled, document the recommendation to keep high-rate push
  loops on their own connection (a second `Connection` is already supported).

**Client APIs** (Python first, others mirror):

```python
rs = conn.add_reverse_stream(vessel.control, "pitch")   # property-setter form
rs.push(0.5)                                            # non-blocking, latest-wins
rs.remove()
```

plus a generic form for arbitrary procedures,
`conn.add_reverse_stream_call(func, *initial_args)` with `rs.push(*args)` replacing the
full argument list (instance handle included — a few bytes). Static clients: a
`ReverseStream<T>` built from a getter expression (deriving `X_set_Y` from `X_get_Y`,
as in the batch `Set` helper) with `.Set(value)`, plus a raw-`ProcedureCall` escape
hatch. Wrappers hold the id, mark themselves invalid on an error routed from the
stream manager, and re-raise the stored error on subsequent `push` — mirroring #877
wrapper semantics.

**GetStatus**: add a `reverse_streams` count beside the existing stream stats
(optional, cheap, aids debugging).

## Documentation

`doc/src/communication-protocols/messages.rst`: `ReverseStreamUpdate` and the new RPCs,
latest-wins and once-per-tick execution, the error and invalidation convention (cross-referencing
the #877 section), and the handshake feature. Client docs: the reverse-stream API, added to the
"fast control loops" section.

## Tests

- **Reverse streams**: register + push + read-back next tick; latest-wins (burst of
  pushes → final value only; TestService gains a counter that increments per *applied*
  set, proving superseded pushes never execute); invalidation via a TestService
  throwing setter → error arrives in one `StreamUpdate`, wrapper re-raises,
  removal idempotent; remove-then-push ignored; disconnect cleanup; per-tick
  application cadence (headless-KSP giant-timestep caveat: assert on counts, not
  wall-clock timing).
- **Core unit tests** for the registry (apply/dirty/latest-wins) where testable
  without `Core.Instance`.

## Implementation order

1. Server: schema additions, RPCs, registry, executor, error channel. Depends on #877's
   invalidation work.
2. Client APIs, Python first, then the remaining clients.
3. `CHANGELOG.md` entries per component as the final pre-merge commit.

## Interactions

- **#877 invalidation**: the reverse-stream error channel *is* the #877 convention;
  implement #877 first.
- **#902 refcounting**: deliberately not applied to reverse streams (each add is a
  fresh id); the shared id counter is unaffected.
- **#843 nullable**: pushes carry `Argument` messages and inherit `is_null` semantics
  for nullable parameters unchanged.
- **#901 freezing**: orthogonal — freezing gates the client's *inbound* value
  application; pushes are outbound.

## Open questions

1. Whether `AddReverseStream` should accept an initial `rate` (Hz cap on application,
   like forward-stream rates) — deferred; once-per-tick is the natural cap and control
   loops want every tick.
2. Whether pushes bypass the per-client FIFO queue (out of order with in-flight RPCs,
   but lower push latency when mixing workloads) — deferred with the
   separate-connection workaround documented; revisit with real-usage data.
3. Where pushes travel. On `Request`, as above, a push shares a message with calls and
   with `no_response`. As a new `Message` case holding `ReverseStreamUpdate`s, a push
   needs no `Request` and no response to suppress. `stream_update` is server to client
   only, and cannot carry arguments. Either is additive on protocol version 2.
