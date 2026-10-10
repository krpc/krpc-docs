# Stream and event lifetime

**Status:** proposal (2026-10-10). Covers [#877](https://github.com/krpc/krpc/issues/877),
[#902](https://github.com/krpc/krpc/issues/902), [#198](https://github.com/krpc/krpc/issues/198) and
[#315](https://github.com/krpc/krpc/issues/315). Supersedes [stream-invalidation.md](stream-invalidation.md)
and [stream-refcounting.md](stream-refcounting.md), which were never implemented. Their decisions are
folded in here, and changed where noted. The design changes no wire format.

This doc audits the stream and event machinery as of the server side functions stack (the SSF PRs,
not yet opened) and defines one model for three questions:

1. What deduplication means: what two handles to one stream share, and what they do not.
2. What a waiting event does when its stream goes away.
3. How errors and endings reach the client.

## Audit

### Server

| Mechanism | Behavior | Where |
|---|---|---|
| Ids | One counter per server, never reused | `Core.AddStream` |
| Dedup, procedure streams | An equal `(procedure, decoded arguments)` from the same client returns the existing id | `ProcedureCallStream.Equals` |
| Dedup, function streams | Same `Expression` object returns the existing id | `FunctionStream.Equals` (SSF) |
| Dedup, `AddEvent` | Same `Expression` object returns the existing id | `EventStream.Equals` (SSF, new; on `main` every event was new) |
| Dedup, service events | Never: `new Service.Event` passes `requireNew` | `Service.Event` |
| Removal | `RemoveStream` marks the id; the next update removes it. No refcount, so one remove ends it for every handle | `Core.RemoveStream` |
| Re-add of a stream marked for removal | Cancels the removal, returns the same id | `Core.AddStream` |
| Error | Sent once in the update, then the stream is removed | `Core.StreamServerUpdate` |
| Server-side removal of an event | `Service.Event.Remove` removes the stream with **no message to the client** | `EventStream.UpdateInternal` |
| Yield in a procedure stream | Update skipped, retried next update | `ProcedureCallStream.UpdateInternal` |
| Yield in a function stream or event | Error, stream removed | SSF design, "A yield is an error" |
| Event value | `true` on a firing; `Sent` resets it to `false` without sending. An `AddEvent` condition that stays true sends `true` every update | `EventStream` |
| Firing before start | `Service.Event.Trigger` before `StartStream` is latched and sent on start. An `AddEvent` condition is only evaluated once started | `Stream.Start` |
| Disconnect | All the client's streams removed | `Core.StreamClientDisconnected` |

Server defects:

* **`stream.Update()` is unguarded in `Core.StreamServerUpdate`.** A stream class that throws stops
  the update for every client, every update. The SSF stack fixes `EventStream` and `FunctionStream`,
  but there is no catch around the call itself.
* **Procedure streams encode in `StreamStream.Write`.** An encode failure, such as a null in a list of
  objects, is a `ServiceException`. It escapes the update loop, with the same effect as above.
  `FunctionStream` already encodes in `UpdateInternal`.
* **`StreamStream.protoResultCache` is never pruned.** It grows by one entry per stream id ever sent
  on the connection, so a `with conn.stream(...)` in a loop grows it without bound.
* **Unknown ids are handled three ways.** `RemoveStream` does nothing. `StartStream` throws
  `InvalidOperationException`. `SetStreamRate` throws a raw `KeyNotFoundException`.
* **The game being between states ends streams that would have survived.** During a quickload,
  `GetVesselById` throws `InvalidOperationException` ("the game is between states") for a vessel the
  game has not rebuilt yet. A stream is terminal on any error, so a stream over a vessel that exists
  in the loaded save is removed. This is the #877 symptom in its current form.
* **`Service.Event.Trigger` is not thread safe.** TestServer's `OnTimer` calls it from a timer thread,
  racing with `Sent` on the update thread.

### Clients

Python, C#, Java and C++ share one structure. A manager maps a server id to one `StreamImpl`, and
every handle with that id shares it: value, condition, callbacks and removed flag. The SSF stack added
a removed flag, stale-handle guards and wake on removal, and stopped passing errors to callbacks. It
introduced no regressions. What remains:

| Defect | Py | C# | Java | C++ |
|---|---|---|---|---|
| An error result is not treated as the end of the stream: not marked removed, map entry kept | x | x | x | x |
| `wait()` after an error result blocks forever | x | x | x | x |
| `Event.wait` resets the shared value to `false`, overwriting a stored error, then blocks forever | x | x | x | x |
| `Event.wait` reset discards a firing that arrived before the wait, or one a second waiter was about to read | x | x | x | x |
| `Event.wait(timeout)` cannot tell a timeout from a firing, and returns early on any wake | x | x | x | x |
| `remove()` on one handle ends the stream for all of them (#902) | x | x | x | x |
| Close does not wake waiters | `Event.wait` re-waits | x | x | x |
| Server-side disconnect wakes nobody | x | x | x | x |
| Update thread dies on a decode or parse error | x (#198) | process ends | x | `std::terminate` |
| Other | | `Start(wait)` checks removed outside the lock | `start()` skips the removed check | busy spin after server close; one `unique_lock` shared by all handles; `remove()` inside `acquire()` deadlocks |

Error types are reconstructed correctly in all four clients, typed by service and name.

## Model

### States

A stream has one server-side state machine per client, and the client mirrors it.

| State | Entered by | Leaves to |
|---|---|---|
| added | `AddStream`, `AddFunctionStream`, `AddEvent`, a procedure returning an event | started, ended |
| started | `StartStream`, or `start = true` | ended |
| ended | the last reference released, an error, the server removing it, disconnect | (terminal) |

Every transition to ended that the client did not ask for is **announced exactly once** with a
final `StreamResult` carrying an error. After that the server sends nothing more for the id and
never reuses it.

| End reason | Final result | Client surfaces it as |
|---|---|---|
| Error in evaluation or encoding | the error | the typed exception |
| Server removed it, e.g. a service event that has finished | `KRPC.StreamRemovedException` | the typed exception |
| Last reference released by the client | none: the client already knows | `StreamError` "removed" on that handle |
| Connection closed, either side | none: the connection is gone | `ConnectionError` / the client's closed-connection error |

### Final results

**No wire format change.** The rule is: a `StreamResult` whose `ProcedureResult` has an `error` is
final. The server already removes a stream after sending its error, so the rule documents current
behavior. A server-side removal becomes one more error on that path.

```csharp
/// <summary>
/// A stream was removed by the server.
/// </summary>
[KRPCException (Service = "KRPC")]
public sealed class StreamRemovedException : System.Exception
```

* `Service.Event.Remove` sends `KRPC.StreamRemovedException` instead of removing silently. Its
  description can carry the reason, e.g. "the event has finished".
* Clients need no knowledge of the type to end the stream: any error ends it. The type only names
  the cause for the caller.
* Old clients surface it as they surface any stream error today: Python builds it from the service
  definitions, and the C#, Java and C++ stubs fall back to their generic RPC exception. A new
  `removed` flag would decode as `false` in an old client, and an event waiter would hang.
* A firing is always delivered before the end. A service event that fires and removes itself in one
  update sends `true`, then the error in the next update, because `RemoveStream` takes effect in the
  next update.
* A function that raises `KRPC.StreamRemovedException` itself, if the SSF stack can express it, ends
  its stream with that error. The outcome is the same final result, so no reservation is needed.

### Management calls on ended streams

The id counter is a high-water mark, the rule the object store uses for object ids:

| Id | `RemoveStream` | `StartStream`, `SetStreamRate` |
|---|---|---|
| live | release one reference | act on the stream |
| below the mark, absent (ended) | no-op | no-op |
| at or above the mark (never issued) | `ArgumentException` | `ArgumentException` |

Ended-id calls are no-ops because they race with the final result already on its way to the client.
The final result says what happened.

## Deduplication

**Deduplication is invisible except for the id.** Two handles from equal adds behave as two
independent streams that happen to share an evaluation.

| Aspect | Shared or per handle |
|---|---|
| Evaluation and value | Shared. One evaluation per update, one result on the wire |
| Lifetime | Per handle. The server counts references per client; each successful add is one, each `RemoveStream` releases one, and the stream ends at zero. Forced endings (error, server removal, disconnect) ignore the count |
| Started | Monotonic. Started once any handle starts it. `start = false` on a hit leaves a started stream started |
| Rate | Shared, last `SetStreamRate` wins. Documented. A per-handle rate would need a per-reference id on the wire, which the rate does not justify |
| Event firings | Per handle, through a cursor (below) |
| `StateVariable` state | Shared: one evaluation advances it once per update, as the SSF design states |
| Error | Shared. Every handle sees the same error |

What is equal:

* A procedure stream: same procedure and equal decoded arguments, as now.
* A function stream or a function event: the same `Expression` object, as the SSF stack does. Two
  builds of the same tree are two streams.
* A service event (`new Service.Event`): never equal to another. Each call to a procedure returning an
  event is a separate source of firings, such as two `OnTimer` calls.

The server refcount is #902's design unchanged. One fix: a re-add that finds the stream marked for
removal un-marks it and sets the count to 1.

Clients mirror the count on the shared `StreamImpl`. `remove()` detaches only the handle it is called
on, and is idempotent per handle. The impl is dropped from the manager map when its count reaches
zero or the stream ends. Copies of one handle share its single reference. The C++ client counts
explicitly rather than through `shared_ptr::use_count`, so copied `Stream<T>` objects keep today's
semantics.

## Events

### Firings are counted per handle

The client-side reset of a shared value is the root of three event defects: lost firings, waiter
interference, and an error overwritten then waited on forever. Replace it with a sequence number.

* `StreamImpl` keeps `fired`, a counter incremented on every `true` result.
* Each `Event` handle keeps `seen`, the value of `fired` when it last returned from `wait`.
* `wait()` returns once `fired > seen`, then sets `seen = fired`. The stored value is never written by
  the waiter, so an error or an ending stays visible.

Consequences:

* A firing between two `wait` calls is not lost. The next `wait` returns immediately.
* Firings coalesce. Five firings before a `wait` make it return once.
* Two handles to a deduplicated event each see every firing. Deduplicating `AddEvent` becomes safe.
* An `AddEvent` condition that stays true still sends `true` every update, so a `wait` returns on
  the next update. This matches the current behavior of a condition polled in a loop.

### Events start when they are created

Firings are latched from the moment the handle exists, which needs the server to be evaluating.
Clients start an event's stream on creation: `AddEvent` and procedures returning events are followed
by `StartStream`, and a new handle's `seen` is the impl's `fired` at that point.

The cost is evaluation between creation and the first wait, which is the window the user asked to
watch. The current lazy start in `wait` is what makes a firing before the first wait invisible.

### Wait returns or raises, never hangs

| Situation | `wait()` | `wait(timeout)` |
|---|---|---|
| Fired since `seen` | returns | returns `true` |
| Fires while waiting | returns | returns `true` |
| Timeout elapses | n/a | returns `false` |
| Stream ended by an error | raises the typed error | raises the typed error |
| Stream removed by the server | raises `KRPC.StreamRemovedException` | raises `KRPC.StreamRemovedException` |
| This handle removed | raises `StreamError` | raises `StreamError` |
| Another handle removed | waits normally, the stream is still referenced | waits normally |
| Connection closed | raises the closed-connection error | same |

* A firing and an ending in one result, or a firing not yet seen when the ending arrives: the
  firing wins. `wait` returns, and the next `wait` raises.
* The timeout is a deadline. A wake before it with nothing new waits for the remaining time.
* Returning `bool` from the timed form is an API change in every client. The C#, Java and C++ forms
  return `void` today, and Python returns `None`. Python and C++ can change the return type without
  breaking callers. C# and Java need a new overload or a deprecation, settled per client in phase 3.

### Callbacks

* Stream callbacks receive values only. Errors and endings are not passed, so typed callback
  signatures stay typed (the SSF behavior).
* Each handle gets a per-stream `on end` callback taking the ending exception. It is called once,
  after the final result is applied and outside the manager's locks, so it can call RPCs. Without it,
  a program driven only by callbacks never learns that its stream ended.
* An event callback fires once per firing.

## Errors

* **Delivery.** The server sends the error once, in a final result, then removes the stream. The
  client stores it on the impl, marks the impl ended, wakes all waiters, calls the `on end` callbacks,
  and drops the map entry.
* **Reads after the end.** Every read, `wait` and `start` on every handle raises the stored error.
  Python raises a copy, or re-raises with the traceback reset, so the traceback does not grow on
  each read.
* **No stream can stop the update loop.** The server catches around each `stream.Update()` and turns
  the exception into an error result. Every stream kind encodes its value inside `UpdateInternal`, so
  an encode failure fails one stream.
* **No client update thread can die.** A decode failure for one result becomes that stream's error.
  A failure reading the connection ends the connection: every stream ends with the closed-connection
  error and every waiter wakes. User callbacks that throw are reported and the thread continues, in
  all four clients and for both stream and update callbacks.

### Transient errors: the game between states

During a load, the game has not yet rebuilt objects that will exist again. An error raised for that
reason must not end a stream.

* Lookups that fail because the game is between states throw a distinct internal exception, the
  dormant case of `FlightGlobalsExtensions.NotResolvable` and its counterparts for parts and other
  objects. `Services.HandleException` reports it to a direct RPC as the same `InvalidOperationException`
  as now.
* Every stream kind treats it as a procedure stream treats a yield: the update is skipped and the
  stream keeps its last sent value. A function that catches it inside a `TryCatchAll` handles it
  itself.
* Once the game settles, a stream over a vessel that survived carries on. A stream over an object that
  is gone gets `ObjectDestroyedException` and ends.

Open: in the main menu `HighLogic.CurrentGame` is null, the state never settles, and a held stream
waits until a game is loaded. That outcome is defensible. The alternative is to classify everything
as destroyed when no game is loaded.

## Game state changes (#877)

The issue asks for a global "all streams invalid" message with a generation counter. This design
does not invalidate streams globally. A stream over a surviving object stays correct across a
load, and a stream over a dead object ends with a typed error, per stream. What the issue needs in
addition is a signal that a load happened, which can be a stream:

```csharp
/// <summary>
/// The number of times the game has loaded a new state, counted once the state has finished loading.
/// </summary>
[KRPCProperty]
public static uint GameStateGeneration { get; }
```

* It counts at `GameState.Sweep` rather than at `GameState.Changed`, so a change arrives when the new
  state is usable. This is step 1 of the issue's sequence.
* Streams held while the game was between states resume in the same update as the sweep. Ordering
  within the update is not guaranteed, so a client reacting to the generation can still see a value
  from a held stream in that update. The value is from the new state.
* A client gets the issue's single callback with existing machinery: a stream of the property and a
  callback, or `add_event` over `generation != g`.
* No wire change, and no new client API beyond the generated property. A client helper can follow if
  the pattern proves common.

## Phases

Each phase can be merged on its own. None changes the SSF stack, which can land first. Until phase 3,
SSF's event deduplication makes the shared-reset defect reachable through two `add_event` handles of
one function. The SSF tests already pin that sharing.

| Phase | Scope | Notes |
|---|---|---|
| 1. Server hardening | catch around `stream.Update()`; encode procedure streams in `UpdateInternal`; prune `protoResultCache` on removal; high-water rule for `StartStream`, `SetStreamRate`, `RemoveStream`; document `Service.Event.Trigger` as main thread only and fix `OnTimer` | no protocol change |
| 2. Final results | `KRPC.StreamRemovedException`; `Service.Event.Remove` sends it | protocol docs: states, an error result is final, dedup rules |
| 3. Client terminal states | in all four: an error result ends the impl; close and disconnect end every impl; waiters always wake; `on end` callback; event cursors and start on creation; timed waits return `bool`; update threads survive decode errors; the per-client bugs in the audit table | the bulk of the work |
| 4. Refcounting (#902) | server count; per-handle `remove` in clients | depends on 3 for per-handle state |
| 5. Game state | dormant exception and skip; `KRPC.GameStateGeneration` | in-game tests: a stream over a surviving vessel across a quickload, one over a vessel removed by it |

## Tests

* TestServer: a service event that removes itself without firing; one that fires and removes itself
  in one update; a procedure stream whose value fails to encode; a throwing event (from the superseded
  design).
* Per client, against TestServer:
  * error then `wait`, for a stream and an event;
  * a firing before `wait`;
  * two handles to one deduplicated event both see a firing;
  * timed `wait` returning `false`;
  * a server-removed event;
  * close and server disconnect waking a stream `wait` and an event `wait`;
  * remove on one handle leaving the other live.
* Core: refcount, high-water rule, update loop surviving a throwing stream.

## Decisions to confirm

1. A server-side removal is an error result, `KRPC.StreamRemovedException`, with no wire change. A
   `removed` field was the alternative. It would leave an old client's event waiter hanging.
2. Events start on creation.
3. Timed waits return `bool`, with a deprecation path in C# and Java.
4. Transient errors are held, not sent. The alternative is to send them as non-final errors, which
   would need a wire field and leaves every client to decide what a non-final error means.
5. #877 is answered by per-stream endings plus `GameStateGeneration`, not by a global invalidation.
