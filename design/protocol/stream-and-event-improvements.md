# Stream and Event Improvements and Fixes

**Status:** proposal (2026-10-10). Covers [#877](https://github.com/krpc/krpc/issues/877),
[#902](https://github.com/krpc/krpc/issues/902), [#198](https://github.com/krpc/krpc/issues/198) and
[#315](https://github.com/krpc/krpc/issues/315). Supersedes [stream-invalidation.md](stream-invalidation.md)
and [stream-refcounting.md](stream-refcounting.md), which were never implemented. Their decisions are
folded in here, and changed where noted. #902 is fixed by removing stream deduplication, in place of
the reference count. The design changes no wire format.

This work lands before server side functions ([server-side-functions.md](../server-side-functions/server-side-functions.md)),
which builds on it. SSF then adds only function streams and function events.

The doc has three parts:

1. **Design**: what streams and events mean, split into what the server does and what a client
   does. It builds up from a single stream to events.
2. **Current implementation**: an audit of `main`, and where it departs from the design.
3. **Phases**: the PRs that bring the implementation in line with the design.

# Part 1. Design

## Streams

### What a Stream Is

A stream is a procedure call that the server evaluates repeatedly and pushes to the client.

| Call | Effect |
|---|---|
| `KRPC.AddStream(call, start)` | creates a new stream and returns its id |
| `KRPC.StartStream(id)` | starts evaluating it |
| `KRPC.SetStreamRate(id, rate)` | limits its updates per second |
| `KRPC.RemoveStream(id)` | ends it |

Server:

* Ids come from one counter per server and are never reused.
* Each update, the server evaluates every started stream and sends a `StreamResult` for each one
  whose value changed. The results go in one `StreamUpdate` on the client's stream connection.

Client:

* A manager maps each id to one shared stream state: the latest value or error, the waiters, and the
  callbacks. A handle is the user's view of that state.
* An update thread reads the stream connection, applies each result to its shared state, wakes the
  waiters and calls the callbacks.

### States

A stream has one server-side state machine per client, and the client mirrors it.

| State | Entered by | Leaves to |
|---|---|---|
| added | `AddStream`, `AddFunctionStream`, `AddEvent`, a procedure returning an event | started, ended |
| started | `StartStream`, `start = true`, or creation for an event | ended |
| ended | `RemoveStream`, an error, the server removing it, disconnect | (terminal) |

After a stream ends, the server sends nothing more for its id.

### One Stream per Add

**Every add creates a new stream with a new id.** Two adds of an equal call are two independent
streams. Each has its own lifetime, started flag, rate and event firings.

Server:

* `AddStream`, `AddFunctionStream` and `AddEvent` never return an existing id.
* **Shared evaluation.** Within one update, the server evaluates the equal procedure call streams of
  one client once, and gives the outcome to each. Equal means the same procedure and equal decoded
  arguments, the existing `ProcedureCallStream.Equals`. A value, an error and a yield are all shared
  this way.
* Each stream still sends its own `StreamResult`, so an equal value is repeated in the
  `StreamUpdate`.
* Sharing is per client, as a procedure can depend on the calling client. A stream whose rate skips
  the update takes no part.
* Function streams and events are never shared. A function can hold state, and an event's firings
  are its own.

Client:

* The manager keeps one shared state per id. A handle owns its stream, and copies of a handle
  share it.
* `remove()` ends the stream for every copy. Removing it again through any copy does nothing.

### Removal and Management Calls

The client removes a stream with `RemoveStream`. The server sends no final result for it, as the
client already knows.

The id counter is a high-water mark, the rule the object store uses for object ids:

| Id | `RemoveStream` | `StartStream`, `SetStreamRate` |
|---|---|---|
| live | end the stream | act on the stream |
| below the mark, absent (ended) | no-op | no-op |
| at or above the mark (never issued) | `ArgumentException` | `ArgumentException` |

Ended-id calls are no-ops because they race with the final result already on its way to the client.
The final result says what happened.

### Endings and Errors

Every ending the client did not ask for is **announced exactly once**, with a final `StreamResult`
carrying an error.

| End reason | Final result | Client surfaces it as |
|---|---|---|
| Error in evaluation or encoding | the error | the typed exception |
| Server removed it, e.g. a service event that has finished | `KRPC.StreamRemovedException` | the typed exception |
| Removed by the client | none | `StreamError` "removed" |
| Connection closed, either side | none: the connection is gone | the client's closed-connection error |

**A `StreamResult` whose `ProcedureResult` has an `error` is final.** The server already removes a
stream after sending its error, the rule [#269](https://github.com/krpc/krpc/issues/269) settled, so
this documents current behavior. A client that wants to keep watching builds a new stream. A
server-side removal is one more error on that path:

```csharp
/// <summary>
/// A stream was removed by the server.
/// </summary>
[KRPCException (Service = "KRPC")]
public sealed class StreamRemovedException : System.Exception
```

Server:

* Sends the error once, in a final result, then removes the stream.
* **No stream can stop the update loop.** The server catches around each stream's update and turns
  the exception into an error result.
* Every stream kind encodes its value inside its own update, because the encode in the write covers
  every stream of a client. An encode failure then fails one stream.

Client:

* Any error ends the stream. The client needs no knowledge of `StreamRemovedException`, whose type
  only names the cause for the caller.
* On a final result the client stores the error, marks the state ended, wakes all waiters, calls the
  `on end` callbacks and drops the map entry.
* Every later read, `wait` and `start` on every handle raises the stored error. Re-raising does not
  grow the error's traceback.
* **The update thread never dies.** A decode failure for one result becomes that stream's error. A
  failure reading the connection ends the connection: every stream ends with the closed-connection
  error and every waiter wakes. A user callback that throws is reported and the thread continues,
  for both stream and update callbacks.

Old clients surface `StreamRemovedException` as they surface any stream error today. Python builds
it from the service definitions, and the C#, Java and C++ stubs fall back to their generic RPC
exception. A new `removed` field was the alternative. It would decode as `false` in an old client,
and an event waiter would hang.

### Waiting and Callbacks

| Situation | `wait()` | `wait(timeout)` |
|---|---|---|
| Update arrives | returns | returns `true` |
| Timeout elapses | n/a | returns `false` |
| Stream ended | raises the ending, per "Endings and Errors" | same |

* The timeout is a deadline. A wake before it with nothing new waits for the remaining time.
* Returning `bool` from the timed form changes the return type in place, in every client. The C#,
  Java and C++ forms return `void` today, and Python returns `None`. The change is source compatible,
  as a call used as a statement discards its result. It is a binary break in the C#, Java and C++
  libraries, which ship with each release, so callers recompile.
* Stream callbacks receive values only. Errors and endings are not passed, so typed callback
  signatures stay typed.
* Each handle can take an `on end` callback, which receives the ending exception. It is called once,
  after the final result is applied and outside the manager's locks, so it can call RPCs. Without it,
  a program driven only by callbacks never learns that its stream ended.

### Game State Changes

During a load, the game has not yet rebuilt objects that will exist again. An error raised for that
reason does not end a stream.

Server:

* Lookups that fail because the game is between states throw a distinct internal exception, the
  dormant case of `FlightGlobalsExtensions.NotResolvable` and its counterparts for parts and other
  objects. `Services.HandleException` reports it to a direct RPC as the same
  `InvalidOperationException` as now.
* Every stream kind treats it as a procedure stream treats a yield. The update is skipped and the
  stream keeps its last sent value.
* The hold lasts until `GameState.Settled`. Then a stream over a surviving object carries on, and
  one over an object that is gone gets `ObjectDestroyedException` and ends.

Settling covers every loaded game. Today `SweepObjectStore` settles a state only when the vessel or
editor part count is above zero and unchanged across two ticks, so an empty save never settles.

* A count of zero settles too, once it has held for a longer window than a nonzero count. A load
  fills the list from empty, so the longer window keeps an early empty list from settling. The
  window is sized in phase 5.
* An editor with no ship counts as zero parts.
* Open: in the main menu `HighLogic.CurrentGame` is null, the state never settles, and a held stream
  waits until a game is loaded. That outcome is defensible. The alternative is to classify everything
  as destroyed when no game is loaded.

A load is signaled by a property, which a client can stream:

```csharp
/// <summary>
/// The number of game states that have finished loading.
/// </summary>
[KRPCProperty]
public static uint GameStateLoads { get; }
```

* It counts when `GameState.Settled` goes from false to true, so a change arrives when the new state
  is usable.
* Sweeps that `RequestSweep` asks for after a part dies leave `Settled` true and do not count.
* The internal `GameState.Generation` counts at `GameState.Changed`, when a state starts to load.
  The two counters differ by design, hence the distinct name.
* Held streams resume in the same update as the sweep. Ordering within the update is not guaranteed,
  so a client reacting to the count can still see a value from a held stream in that update. The
  value is from the new state.

Client:

* A single "game loaded" callback comes from existing machinery: a stream of `GameStateLoads` with a
  callback, or `add_event` over `loads != n`. A helper can follow if the pattern proves common.

This is the answer to #877. The issue asks for a global "all streams invalid" message with a
generation counter. This design ends streams one at a time instead. A stream over a surviving object
stays correct across a load, and one over a dead object ends with a typed error.

## Events

An event is a stream of `bool` whose `true` results are firings. Everything under "Streams" applies.
This section adds what is specific to events.

### Sources

| Source | Fires when |
|---|---|
| `KRPC.AddEvent` | its condition is true in an update |
| A procedure returning a `Service.Event`, e.g. `OnTimer` | the service calls `Trigger` |

Every `AddEvent`, and every call of a procedure returning an event, creates a separate event.

### Start on Creation

Firings are latched from the moment the handle exists, which needs the server to be evaluating.

Server:

* Starts an event's stream when it creates it: in `KRPC.AddEvent`, and in the `Service.Event`
  constructor.

Client:

* A new handle's cursor starts at the state's current firing count.
* Old clients are unaffected. Their lazy `StartStream` in `wait` finds the stream started, and the
  start resends the current value.

The cost is evaluation between creation and the first wait, which is the window the user asked to
watch. The current lazy start in `wait` is what makes a firing before the first wait invisible.

### Firings Counted per Handle

Client:

* The shared state keeps `fired`, a counter incremented on every `true` result.
* Each handle keeps `seen`, the value of `fired` when a `wait` on it last returned.
* `wait()` reads `seen` on entry, returns once `fired` exceeds it, then sets `seen = fired`. The
  waiter never writes the stored value, so an error or an ending stays visible.

Consequences:

* A firing between two `wait` calls is not lost. The next `wait` returns immediately.
* Firings coalesce. Five firings before a `wait` make it return once.
* Two threads waiting on one handle both return on a firing.
* An `AddEvent` condition that stays true sends `true` every update, so a `wait` returns on the next
  update. This matches a condition polled in a loop.

### Server-Side Removal

A service event can end itself, e.g. when its timer has finished.

Server:

* `Service.Event.Remove` records a pending end. The event's update sets
  `KRPC.StreamRemovedException` as the error in the first update with no unsent firing. The error
  path then sends it and removes the stream. The description can carry the reason, e.g. "the event
  has finished".
* A firing is always delivered before the end. A firing and an error cannot share one result, as
  both reset the same `ProcedureResult`. An event that fires and removes itself in one update sends
  `true`, then the error in the next update.
* A pending end is acted on only when the stream updates. Events start on creation, so every event
  updates. A rate limit delays the end by up to one period.

### Wait

| Situation | `wait()` | `wait(timeout)` |
|---|---|---|
| Fired since `seen` | returns | returns `true` |
| Fires while waiting | returns | returns `true` |
| Timeout elapses | n/a | returns `false` |
| Stream ended by an error | raises the typed error | raises the typed error |
| Stream removed by the server | raises `KRPC.StreamRemovedException` | raises `KRPC.StreamRemovedException` |
| Removed by the client, through any copy of the handle | raises `StreamError` | raises `StreamError` |
| Connection closed | raises the closed-connection error | same |

* A firing not yet seen when the ending arrives wins. `wait` returns, and the next `wait` raises.
* An event callback is called once per firing.

## Function Streams and Events

Server side functions land after this work and add `KRPC.AddFunctionStream` and an `AddEvent` over a
function. They follow the model above. What they add:

* **One stream per add.** Every `AddFunctionStream`, and every `AddEvent` over a function, creates a
  new stream, and shared evaluation never applies to them. The SSF stack deduplicates them by
  `Expression` object today, and the rebase removes that.
* **`StateVariable` state** belongs to the function, and every evaluation advances it. Two streams of
  one function advance it twice per update. A separate state needs a separate build.
* **Errors.** An exception from a function, and a value that fails to encode, end only that stream.
  A function raising `KRPC.StreamRemovedException` itself ends its stream with that error, the same
  final result, so no reservation is needed.
* **A yield stays an error** (SSF, "A yield is an error, and nothing retries"). A yielding procedure
  continues through a continuation that a restart discards. Restarting re-runs it from scratch every
  update, so it never completes. A transient error clears once the game settles, so a restart
  succeeds.
* **Held evaluations are rolled back.** A held function stream or function event evaluates again
  from the start in the next update. The stream snapshots its function's `StateVariable` values
  before each evaluation and restores them when the evaluation is held, so a held update leaves the
  state as it found it. The snapshot is only taken for functions that declare state. Game writes
  made before the throw are not undone, and repeat on the re-run.

# Part 2. Current Implementation

The audit describes `main` with phase 0 applied. Phase 0 moves fixes already written in the SSF
stack, and changes no part of the model. Each defect names the phase that fixes it.

## Server

| Mechanism | Behavior | Where |
|---|---|---|
| Ids | One counter per server, never reused | `Core.AddStream` |
| Dedup, procedure streams | An equal `(procedure, decoded arguments)` from the same client returns the existing id | `ProcedureCallStream.Equals` |
| Dedup, `AddEvent` | Never: the v0.6.0 `AddEvent` on `main` creates a `Service.Event` per call | `KRPC.AddEvent` |
| Dedup, service events | Never: `new Service.Event` passes `requireNew` | `Service.Event` |
| Removal | `RemoveStream` marks the id. A mark from an RPC is flushed at the start of the next stream update. A mark made during the stream loop, by an error or `Service.Event.Remove`, is flushed at the end of the same update, after the write. No refcount, so one remove ends it for every handle | `Core.RemoveStream`, `Core.StreamServerUpdate` |
| Re-add of a stream marked for removal | Cancels the removal, returns the same id | `Core.AddStream` |
| Error | Sent once in the update, then the stream is removed | `Core.StreamServerUpdate` |
| Server-side removal of an event | `Service.Event.Remove` removes the stream with **no message to the client**. The removal is made in `UpdateInternal`, so an event never started is never removed, and a rate limit delays it | `EventStream.UpdateInternal` |
| Yield in a procedure stream | Update skipped, retried next update | `ProcedureCallStream.UpdateInternal` |
| Event value | `true` on a firing; `Sent` resets it to `false` without sending. An `AddEvent` condition that stays true sends `true` every update | `EventStream` |
| Firing before start | `Service.Event.Trigger` before `StartStream` is latched and sent on start. An `AddEvent` condition is only evaluated once started | `Stream.Start` |
| Disconnect | All the client's streams removed | `Core.StreamClientDisconnected` |

| Defect | Phase |
|---|---|
| **`stream.Update()` is unguarded in `Core.StreamServerUpdate`.** A stream class that throws stops the update for every client, every update. Phase 0 makes `EventStream` catch its condition's errors, but there is no catch around the call itself | 1 |
| **Procedure streams encode in `StreamStream.Write`.** An encode failure, such as a null in a list of objects, is a `ServiceException`. It escapes the update loop, with the same effect as above | 1 |
| **`StreamStream.protoResultCache` is never pruned.** It grows by one entry per stream id ever sent on the connection, so a `with conn.stream(...)` in a loop grows it without bound | 1 |
| **Unknown ids are handled three ways.** `RemoveStream` does nothing. `StartStream` throws `InvalidOperationException`. `SetStreamRate` throws a raw `KeyNotFoundException` | 1 |
| **`Service.Event.Trigger` is not thread safe.** TestServer's `OnTimer` calls it from a timer thread, racing with `Sent` on the update thread | 1 |
| **A stream over a procedure returning an event adds a stream per update.** Suspected, not reproduced. Each evaluation constructs a `Service.Event`, which calls `Core.AddStream` while `StreamServerUpdate` enumerates the client's streams. The enumeration then throws "collection was modified" outside `stream.Update()`, so a catch around that call does not cover it. Each update also leaks one event stream | 1 |
| **A server-side removal is silent**, and an event never started is never removed | 2 |
| **Events start lazily**, so a firing of an `AddEvent` condition before the first `wait` is never seen | 2 |
| **Equal adds share one stream.** One `RemoveStream` ends it for every handle (#902). A re-add of a stream marked for removal returns an id the client has dropped, which works only because `Stream.Start` resends the value | 4 |
| **The game being between states ends streams that would have survived.** During a quickload, `GetVesselById` throws `InvalidOperationException` ("the game is between states") for a vessel the game has not rebuilt yet. A stream is terminal on any error, so a stream over a vessel that exists in the loaded save is removed. This is the #877 symptom in its current form | 5 |
| **A failed write drops a final result.** An error result is marked for removal before `Stream.Write`. A caught `ServerException` loses the error but the stream is still removed. The connection is failing in that case, so the closed-connection ending covers it | none |

## Clients

Python, C#, Java and C++ share one structure. A manager maps a server id to one `StreamImpl`, and
every handle with that id shares it: value, condition, callbacks and removed flag. Phase 0 adds the
removed flag, stale-handle guards and wake on removal, and stops passing errors to callbacks. Error
types are reconstructed correctly in all four clients, typed by service and name.

| Defect | Py | C# | Java | C++ | Phase |
|---|---|---|---|---|---|
| An error result is not treated as the end of the stream: not marked removed, map entry kept | x | x | x | x | 3 |
| `wait()` after an error result blocks forever | x | x | x | x | 3 |
| `Event.wait` resets the shared value to `false`, overwriting a stored error, then blocks forever | x | x | x | x | 3 |
| `Event.wait` reset discards a firing that arrived before the wait, or one a second waiter was about to read | x | x | x | x | 3 |
| `Event.wait(timeout)` cannot tell a timeout from a firing, and returns early on any wake | x | x | x | x | 3 |
| Close does not wake waiters | `Event.wait` re-waits | x | x | x | 3 |
| Server-side disconnect wakes nobody | x | x | x | x | 3 |
| Update thread dies on a decode or parse error | x (#198) | process ends | x | `std::terminate` | 3 |
| Other | `Event.wait` resets the value without a removal guard | `Start(wait)` checks removed outside the lock; `Event.Wait` resets the value without a removal guard | `start()` skips the removed check | busy spin after server close; one `unique_lock` shared by all handles; `remove()` inside `acquire()` deadlocks | 3 |
| `remove()` on one handle ends the stream for all handles from equal adds (#902). Fixed by the server change alone | x | x | x | x | 4 |

# Part 3. Phases

Each phase can be merged on its own, and all of them land before server side functions. The SSF
stack is then rebased onto the phases, and its function streams and events adopt the model as
listed under "Function Streams and Events".

## Phase 0: Fixes Moved Out of SSF

The SSF stack fixed generic stream and event defects alongside its own code. Phase 0 moves them
onto `main` unchanged, so they ship before SSF and the later phases start from them. It is
extraction only, with no protocol change.

| Where | Fix |
|---|---|
| Server | `EventStream.UpdateInternal` turns an exception from its condition into an error result, so an event cannot stop the update loop. A firing resets the result, clearing an earlier error. `Services.HandleException` accepts an exception with no stack trace. Streaming `KRPC.AddEvent` is refused, as it would add an event per update |
| Clients | A removed stream throws on a wait, a read or a start through any handle, and a removal wakes its waiters. Removing it again through another handle does nothing. A stream callback is not called for an update that is an error, and reading the stream throws it. Java and C++ guard the `Event.wait` reset against a removal |

## Phases 1 to 5

| Phase | Scope | Notes |
|---|---|---|
| 1. Server hardening | catch around `stream.Update()`; encode procedure streams in `UpdateInternal`; prune `protoResultCache` on removal; the high-water rule for management calls; document `Service.Event.Trigger` as main thread only and fix `OnTimer`; reproduce the stream over a procedure returning an event, and if confirmed have `AddStream` reject such a procedure | no protocol change |
| 2. Final results | `KRPC.StreamRemovedException`; `Service.Event.Remove` records a pending end that is sent after any unsent firing, and `EventStream` no longer calls `Core.RemoveStream`; the server starts events on creation | protocol docs: states, an error result is final |
| 3. Client terminal states | in all four: an error result ends the shared state; close and disconnect end every stream; waiters always wake; `on end` callback; event cursors; timed waits of streams and events return `bool`; update threads survive decode errors and throwing callbacks; the per-client bugs in the audit | the bulk of the work. The C++ lock changes overlap [stream-freezing-removal.md](stream-freezing-removal.md) |
| 4. One stream per add (#902) | `AddStream` always creates a stream, and the re-add path in `Core.AddStream` goes; shared evaluation of equal procedure call streams per client and update; a benchmark of many equal streams before and after; the protocol docs, and the C#, Java and C++ guides on stream equality | clients need no code change. **Breaking:** repeated equal adds without a remove now accumulate streams |
| 5. Game state | dormant exception and skip; zero counts settle; `KRPC.GameStateLoads` | in-game tests: a stream over a surviving vessel across a quickload, one over a vessel removed by it, a held stream in an empty save |

## Tests

* TestServer: a service event that removes itself without firing; one that fires and removes itself
  in one update, sending `true` then the error; a procedure stream whose value fails to encode; a
  throwing event (from the superseded design); a stream over a procedure returning an event.
* Per client, against TestServer:
  * error then `wait`, for a stream and an event;
  * a firing before `wait`, and one before the first `wait` of a new event;
  * two threads waiting on one event handle both see a firing;
  * timed `wait` returning `false`, for a stream and an event;
  * a server-removed event;
  * close and server disconnect waking a stream `wait` and an event `wait`;
  * two equal adds giving two ids, and removing one leaving the other live;
  * remove then add of an equal stream receiving a value.
* Core: equal streams evaluated once per update with a result sent for each, high-water rule, update loop surviving a throwing stream, `GameStateLoads`
  ignoring a part-death sweep, a zero count settling.
* SSF, once rebased: a held function evaluation restoring its state variables.

## Decisions

Decided 2026-10-10:

* Timed waits of streams and events return `bool`, changed in place in every client. The binary
  break in the C#, Java and C++ libraries is accepted.
* A held function evaluation restores its `StateVariable` values (SSF, after rebasing).
* Holds are bounded by fixing the settle check for zero counts, not by a time limit.
* The load counter is `KRPC.GameStateLoads`.
* Stream deduplication is removed, and every add is a new stream. It was added to save results on
  the wire for streams such as altitude. Over events and function streams it needs reference counts,
  per-handle cursors and shared function state. Equal procedure call streams keep one evaluation per
  update, and their values are repeated in the update message.

To confirm:

1. A server-side removal is an error result, `KRPC.StreamRemovedException`, with no wire change. A
   `removed` field was the alternative. It would leave an old client's event waiter hanging.
2. The server starts events on creation. Starting them from the client was the alternative, at one
   RPC per event.
3. Transient errors are held, not sent. The alternative is to send them as non-final errors, which
   would need a wire field and leaves every client to decide what a non-final error means.
4. #877 is answered by per-stream endings plus `GameStateLoads`, not by a global invalidation.
