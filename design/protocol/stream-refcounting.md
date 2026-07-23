# Reference-counted streams (issue #902)

**Status:** proposal — design agreed, not yet implemented (2026-07-03).

## Context

[Issue #902](https://github.com/krpc/krpc/issues/902): two identical `AddStream`
requests from one client return the same stream id (deliberate dedup to minimize
traffic), but a single `RemoveStream` destroys the stream for both consumers —
independent parts of a client program can silently break each other.

How it works today:

- **Server dedup**: `Core.AddStream` (`core/src/Core.cs:580-608`) linearly scans the
  client's streams for an equal stream — `ProcedureCallStream.Equals`
  (`core/src/Service/ProcedureCallStream.cs:24-33`) compares the procedure and all
  decoded arguments — and returns the existing id (the `AddStream` RPC passes
  `requireNew: false`, `core/src/Service/KRPC/KRPC.cs:198-210`). Ids come from a
  monotonic counter (`nextStreamId`), never reused. On a dedup hit it also un-marks a
  pending removal (`removeStreams.Remove(entry.Key)`) to guard the remove-then-re-add
  race.
- **Server removal**: `Core.RemoveStream` (`Core.cs:639-652`) marks the id in
  `removeStreams`; the deferred removal happens in `StreamServerUpdate`
  (`Core.cs:513-519, 566-572`). No count anywhere — one remove kills the shared stream.
- **The bug exists client-side too**: all four bundled clients dedup locally by the
  *returned id* and share one `StreamImpl` between wrappers
  (Python `streammanager.py:110-117`, C# `StreamManager.cs:58-67`,
  Java `StreamManager.java:40-48`, C++ `stream_manager.cpp:39-49`). `remove()` on one
  wrapper unconditionally issues the `RemoveStream` RPC, deletes the map entry, and
  poisons the *shared* impl with "Stream does not exist" — so the sibling wrapper breaks
  locally even if the server kept the stream.
- **Event streams are immune**: `EventStream.Equals` is reference equality and
  `Service.Event` adds with `requireNew: true` (`core/src/Service/Event.cs:27-52`),
  so every `AddEvent` gets a fresh id; refcounts there are structurally always 1.
- There is no core-level unit test of `Core.AddStream`/`RemoveStream` dedup; the
  behavior is pinned only by protocol-level client tests
  (`client/python/krpc/test/test_stream.py:160-183` `test_add_stream_twice`, which
  asserts the shared id).

## Decisions

- **Server-side reference count per (client, stream)**, as the issue proposes. The
  count lives on `Service.Stream` (each instance belongs to exactly one client's map,
  so no cross-client bookkeeping is needed). No wire change.
- **The unit of reference is one successful `AddStream` RPC.** Copies of a client-side
  wrapper share its single reference (removing via any copy consumes it) — unchanged
  from today's handle semantics.
- **Forced removals bypass the count**: error invalidation
  (`Core.cs:550-551`, the #877 path — see
  [stream-invalidation.md](stream-invalidation.md)), `EventStream` self-removal
  (`EventStream.cs:35-40`), and client disconnect (`Core.StreamClientDisconnected`,
  `Core.cs:103-112`) tear the stream down outright regardless of count.
- **Bundled clients get wrapper-level removal**: `remove()` detaches only the wrapper
  it is called on; the shared `StreamImpl` and other wrappers keep working until the
  last wrapper is removed.
- Pre-existing shared-stream quirks are unchanged and documented: `SetStreamRate` and
  `StartStream` act on the shared stream (last caller wins).

## Server changes (`core/`)

1. `Service.Stream` (`core/src/Service/Stream.cs`) — add
   `internal int ReferenceCount { get; set; }`, managed only by `Core`.
2. `Core.AddStream` (`Core.cs:580-608`):
   - dedup hit: if the stream was marked for removal, un-mark it (existing race guard)
     and reset the count to 1; otherwise increment. Return the existing id as now.
   - new stream: count starts at 1.
3. `Core.RemoveStream(IClient, ulong)` (`Core.cs:639-652`) — decrement; only when the
   count reaches 0, mark `removeStreams[streamId] = streamClient`. A remove on an
   unknown id, or on a stream already at 0 (marked but not yet processed), stays an
   idempotent no-op.
4. Forced-removal paths (`Core.cs:550-551` error path; the all-clients
   `RemoveStream(ulong)` overload at `Core.cs:654-665` used by `EventStream`;
   `StreamClientDisconnected`) — remove/mark directly without decrementing, as today.
   `RemoveStreamInternal` is unchanged.

## Client changes

Uniform rule: each `add_stream()` call issues its own `AddStream` RPC (as today — the
server increments), and each wrapper's `remove()` issues one `RemoveStream` RPC (the
server decrements). The client mirrors the count on the shared `StreamImpl` so it knows
when to drop its local map entry:

- `StreamImpl` gains a reference count: incremented in the manager's `add_stream` both
  on creation and on the existing-id hit.
- The wrapper (`Stream`) gains a `removed` flag: `remove()` is idempotent per wrapper —
  first call issues the `RemoveStream` RPC, decrements the impl count, and marks the
  wrapper; at count 0 the manager deletes the map entry and poisons the impl
  ("Stream does not exist"), exactly the current end-state.
- Reads/`wait()` on a removed *wrapper* raise "Stream does not exist" for that wrapper
  only; sibling wrappers are unaffected.
- Error invalidation (#877) stays impl-level: the error poisons the shared impl and all
  wrappers observe it, and the manager map entry is dropped without any `RemoveStream`
  RPCs (the server already removed it; subsequent wrapper `remove()` calls are no-ops
  per the #877 design).

Per client, the touch points are the add/remove paths already identified:
Python `stream.py:91-93` + `streammanager.py:96-99,110-131`; C# `Stream.cs:151-154` +
`StreamImpl.cs:92-97` + `StreamManager.cs:58-88`; Java `Stream.java:169-171` +
`StreamImpl.java:98-101` + `StreamManager.java:40-66`; C++ `stream.hpp:159-163` +
`stream_impl.cpp:95-97` + `stream_manager.cpp:39-68` (the count is explicit on
`StreamImpl`, not inferred from `shared_ptr::use_count`, so copied `Stream<T>` handles
keep today's shared-reference semantics).

Events wrap a stream by id (e.g. Python `event.py:11-19`) and flow through the same
manager paths; since event ids never collide, their count is always 1 and behavior is
unchanged.

## Compatibility

- No schema change. New client + old server: each wrapper's `RemoveStream` beyond the
  first hits the old server's idempotent unknown-id path — the stream dies on the first
  remove (old behavior), and remaining local wrappers read stale values until removed;
  acceptable skew.
- Old client + new server: a client that issued N identical `AddStream`s but relies on
  one `RemoveStream` killing the stream now leaves it alive (count N−1). The bundled
  old clients delete their local map entry on the first remove, so subsequent updates
  for the id are skipped (already the pattern for unknown ids) — a harmless server-side
  leak until disconnect. Document in the changelog.

## Documentation

`doc/src/communication-protocols/messages.rst` — in the streams section, document that
identical `AddStream` calls return the same id and that streams are reference counted
per client: each `AddStream` acquires a reference, each `RemoveStream` releases one,
and the stream is destroyed at zero (or immediately on error — cross-reference the
#877 invalidation convention).

## Tests

- **Rewrite `test_add_stream_twice`** (Python `test_stream.py:160-183`, C#
  `StreamTest.cs:172-197`, Java `StreamTest.java:255-279`, C++ equivalent): keep the
  shared-id assertion, then add the new core assertion — `s1.remove()` leaves `s0`
  live and updating; `s0.remove()` then fully removes it (a third identical
  `add_stream` yields a **new** id, observable via the impl's stream id since ids are
  never reused).
- Per-wrapper `remove()` idempotence; reads on the removed wrapper raise while the
  sibling still works.
- Existing `test_remove_then_add_stream` / `test_restart_stream` (race-guard paths)
  must still pass with the count-reset-to-1 behavior.
- Optional: a first core-level unit test for `Core.AddStream`/`RemoveStream` counting,
  if `Core.Instance` can be stood up in `core/test` without a full server (currently
  no such test exists — flagged during exploration).

## Implementation order

1. Server (`Core.cs`, `Stream.cs`) + protocol docs.
2. Python client + tests (fastest protocol-level verification).
3. C#, Java, C++ clients + tests.
4. CHANGES.txt entries (core + each client) as the final pre-merge commit.

## Interactions

- **#877 invalidation** ([stream-invalidation.md](stream-invalidation.md)): error ⇒
  forced teardown regardless of count; client-side error poisoning is impl-level and
  intentionally overrides wrapper-level removal state.
- **#901 freezing** ([stream-freezing-removal.md](stream-freezing-removal.md)): no longer an
  interaction. Freezing was to be ported to all clients with per-stream pending buffers, which
  would have needed reconciling with refcounted removal; instead the C++ feature is being removed
  in favor of server-side function streams, so refcounting is unaffected by it.
