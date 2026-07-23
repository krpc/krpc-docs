# Batched calls, fire-and-forget, and reverse streams (issue #903)

**Status:** proposal — design agreed, not yet implemented (2026-07-03).

## Context

[Issue #903](https://github.com/krpc/krpc/issues/903): control writes are blocking
round-trips — `control.pitch = x; control.yaw = y` measured at ~40 ms — and there is no
non-blocking send path analogous to (receive) streams.

Why writes are slow: the server only processes RPCs inside `RPCServerUpdate`, once per
`FixedUpdate` (`core/src/Core.cs:403-496`), with an adaptive time budget
(`MaxTimePerUpdate` self-tuning 1–25 ms, `Core.cs:380-394`). A blocking client waits up
to a full game tick per call, and strictly sequential setters each pay that wait.

What exploration established:

- **Batching already exists everywhere except client APIs.** `Request` carries
  `repeated ProcedureCall calls`; `RequestContinuation` (`core/src/Service/RequestContinuation.cs:19-84`)
  executes multiple calls in order in one tick (yield-aware, completed calls not
  re-run), with **per-call error isolation** (`ProcedureCallContinuation.Run`,
  `ProcedureCallContinuation.cs:35-49`) and ordered results; the protocol docs already
  advertise it (`messages.rst:59-60`). Every client hard-codes one call per request and
  reads `results[0]` — but every client also already has standalone `ProcedureCall`
  builders (used by streams): Python `get_call`/`_build_call` (`client.py:150,229`),
  C# `GetCall` (`Connection.cs:169-296`), Java `buildCall`/`getCall`
  (`Connection.java:238,362`), C++ `build_call` (+ `invoke(Request)` already accepts
  multi-call, `client.cpp:53-120`), cnano generated call builders, Lua inline.
- **Responses are written at exactly one place** — `client.Stream.Write(response)` in
  `Core.ExecuteContinuation` (`Core.cs:762`) — the natural seam for a no-response flag.
  No `oneway`/`no_response` concept exists anywhere today.
- **Ordering model**: strict FIFO per client — the server will not read a client's next
  request while one of its continuations is queued or yielded (the
  `pollRequestsCurrentClients` guard, `Core.cs:683-734`); round-robin across clients.
  Pipelined requests wait in the socket/receive buffer and drain within a tick up to
  the time budget.
- **The RPC connection is the only viable channel for client→server pushes.** The
  stream connection is hard-wired one-way: inbound type `NoMessage`, all read paths
  throw (`core/src/Server/Message/StreamStream.cs:15-29`), and **SerialIO has no stream
  connection at all** (`SerialIO/StreamServer.cs:14-24`). All three transports (PB/TCP,
  WebSockets, SerialIO) fully decode `Request`, so **new fields on `Request` need zero
  transport changes**, while a new inbound message type would touch every transport.
- Prior art for latest-wins-per-tick evaluation is the forward stream loop
  (`Core.StreamServerUpdate`, `Core.cs:503-578`); prior art for server-side call
  storage is `Expression.Call` (`core/src/Service/KRPC/Expression.cs:105-138`).

## Decisions

Three rungs, phased; each ships independently and the later ones build on the earlier.

1. **Batching** — client-API work only; no protocol or server change.
2. **Fire-and-forget** — `bool no_response = 2` on `Request`; server skips the response
   write. Client use is **gated on server version** (see version skew below).
3. **Reverse streams** — register a call once, push latest-wins argument updates that
   the server applies **at most once per tick**; pushes ride `Request` on the RPC
   connection; errors invalidate the reverse stream and are delivered over the
   (forward) stream connection using the #877 error convention.

Cross-cutting: all schema additions are plain proto3 fields/messages — no toolchain
issues (Unity protobuf 3.10.1, protobuf-lua).

## Rung 1 — Batching (client APIs)

Semantics (already guaranteed by the server): calls execute in order in a single
request, normally within one tick; each call's error is isolated in its
`ProcedureResult` and raised only when that call's result is accessed; a call that
yields (multi-tick RPC) delays completion of the whole request — documented, with the
advice to keep long-running calls out of latency-sensitive batches.

Per-client API sketches (exact shapes finalised at implementation):

- **Python**: a context manager that intercepts `_invoke`:
  ```python
  with conn.batch() as batch:
      control.pitch = 0.1          # queued
      control.yaw = 0.2            # queued
      alt = vessel.flight().mean_altitude   # queued, returns a BatchResult
  print(alt.value)                 # available after the block exits
  ```
  Inside the block, stub invocations enqueue `(ProcedureCall, return_type)` pairs and
  return `BatchResult` handles; on exit, one multi-call `Request` is sent and results
  are decoded per handle. Accessing `.value` inside the block raises. Lua mirrors this.
- **C# / Java**: explicit batch objects reusing the existing call builders —
  `var b = conn.NewBatch(); var r = b.Add(() => vessel.Flight().MeanAltitude); b.Execute(); r.Value`.
  Property *setters* can't appear in C# expression lambdas, so the batch gains a
  `b.Set(() => control.Pitch, 0.1f)` form that derives the setter procedure from the
  getter expression (the `X_get_Y` → `X_set_Y` naming convention).
- **C++**: `Client::invoke(schema::Request)` already accepts multi-call; add a
  `krpc::Batch` helper wrapping `build_call` + indexed result decoding.
- **cnano**: raise the `calls`/`results` nanopb capacities in
  `client/cnano/src/krpc.options` and add `krpc_invoke_batch(conn, calls, results, n)`
  (`krpc.c:61-104` currently hard-codes `calls_count = 1` and rejects `results_count != 1`).

## Rung 2 — Fire-and-forget

**Schema**: `Request { repeated ProcedureCall calls = 1; bool no_response = 2; }`.
Request-level, not per-call — mixed batches would need partial responses.

**Server**: thread the flag through `Messages.Request` → `RequestContinuation`;
`ExecuteContinuation` skips `client.Stream.Write(response)` (`Core.cs:762`) when set.
Errors from no-response requests are logged at info level and otherwise dropped.
Execution is unchanged — same FIFO ordering, same tick budget; the one-in-flight guard
still applies (a burst of pipelined fire-and-forget requests drains within ticks).

**The fence idiom** (document): because the server won't read request N+1 until N
completes, a subsequent *normal* RPC's response confirms that all prior fire-and-forget
requests have executed — a free flush/barrier.

**Version skew — the one hazard**: an old server ignores the unknown field and writes a
`Response` the client never reads, desynchronizing the connection. Client libraries
therefore check the server version (`KRPC.GetStatus().version`) once, lazily, before
first use of `no_response` (or reverse streams), and raise a clear "server too old"
error otherwise. Old client + new server is trivially fine.

**Client APIs**: an option on the batch API (`with conn.batch(no_response=True):`,
`b.Execute(noResponse: true)`), which also covers the single-call case.

## Rung 3 — Reverse streams

**Schema**:

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
  as forward streams** (shared id space, so the stream-connection error channel is
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
  `StreamResult { id, result.error }` on the **stream connection exactly once** —
  reusing the [#877 invalidation convention](stream-invalidation.md) verbatim; client
  stream managers route errors for reverse ids to the reverse-stream wrapper.
  **SerialIO caveat**: no stream connection exists, so invalidation there is silent
  (subsequent pushes to the dead id are ignored); documented limitation.
- Client disconnect tears down its reverse streams (beside the forward-stream cleanup
  in `Core.RPCClientDisconnected`/`StreamClientDisconnected`).
- The one-in-flight guard is **kept**: pushes queued behind an in-flight multi-tick RPC
  stall until it completes. Documented, with the recommendation to keep high-rate push
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

`doc/src/communication-protocols/messages.rst`: `no_response` semantics + the fence
idiom; `ReverseStreamUpdate` + the new RPCs; latest-wins and once-per-tick execution;
the error/invalidation convention (cross-referencing the #877 section); SerialIO
limitation. Client docs: batch API, fire-and-forget option, reverse-stream API, and a
rewritten "fast control loops" guidance section (this is the issue's use case).

## Tests

- **Batching**: multi-call round trip with mixed success/error results (error isolated
  to its handle); ordering; extend `test_performance.py:11-21` with a batched variant
  demonstrating the latency win (assert batched < N× single, loosely — headless-KSP
  timing is noisy).
- **Fire-and-forget**: no-response setter observed applied via a subsequent read (the
  fence); ordering across a mix of no-response and normal requests; old-server gating
  (mock/skip).
- **Reverse streams**: register + push + read-back next tick; latest-wins (burst of
  pushes → final value only; TestService gains a counter that increments per *applied*
  set, proving superseded pushes never execute); invalidation via a TestService
  throwing setter → error arrives on the stream connection once, wrapper re-raises,
  removal idempotent; remove-then-push ignored; disconnect cleanup; per-tick
  application cadence (headless-KSP giant-timestep caveat: assert on counts, not
  wall-clock timing).
- **Core unit tests** for the registry (apply/dirty/latest-wins) where testable
  without `Core.Instance`.

## Implementation order

1. Batching client APIs (Python → C#/Java/C++/cnano/Lua) + perf test. No server work.
2. `no_response`: schema + server + client batch option + version gating + docs.
3. Reverse streams server: schema additions, RPCs, registry, executor, error channel
   (depends on #877's client/server invalidation work being in place).
4. Reverse streams client APIs, Python first; remaining clients.
5. CHANGES.txt entries per component as the final pre-merge commit.

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
2. Whether push-only requests should bypass the one-in-flight guard (out-of-order
   with in-flight RPCs, but lower push latency when mixing workloads) — deferred with
   the separate-connection workaround documented; revisit with real-usage data.
