# Stream and Event Improvements and Fixes

**Status:** done (2026-10-12), merged in PR #1122. The Python client is the reference, see
"Client Reference". Divergences are under "Implementation".

Four parts shipped first as their own PRs, all merged:

| PR | Part |
|---|---|
| #1118 | C++ stream freezing removal |
| #1119 | `KRPC.UnsupportedSceneException` for the game scene check |
| #1120 | `KRPC.ObjectNotLoadedException` for dormant lookups |
| #1121 | game state settling with no vessels and across scene changes, and `KRPC.GameStateLoads` |

The stream and event PR builds on them. Its phase 6 holds streams over the two exceptions, sends an
event's firing before an error from the same update, and adds TestServer tests of an event that
ends without firing.

Covers [#877](https://github.com/krpc/krpc/issues/877),
[#902](https://github.com/krpc/krpc/issues/902), [#198](https://github.com/krpc/krpc/issues/198) and
[#315](https://github.com/krpc/krpc/issues/315). Supersedes [stream-invalidation.md](stream-invalidation.md)
and [stream-refcounting.md](stream-refcounting.md), which were never implemented. Their decisions are
folded in here, and changed where noted. #902 is fixed by removing stream deduplication, in place of
the reference count. The message formats are unchanged. The `KRPC` service drops `StartStream` and
the `start` flag of `AddStream`, which breaks old clients. The C++ client's stream freezing was
removed outright by #1118, in place of the deprecation plan in [stream-freezing-removal.md](stream-freezing-removal.md).

This work landed before server side functions ([server-side-functions.md](../server-side-functions/server-side-functions.md)),
merged in #1124 to #1130, which builds on it. SSF then adds only function streams and function events.

The doc has three parts:

1. **Design**: what streams and events mean, split into what the server does and what a client
   does. It builds up from a single stream to events.
2. **Current implementation**: an audit of `main`, and where it departs from the design.
3. **Phases**: the steps that bring the implementation in line with the design.

# Part 1. Design

## Streams

### What a Stream Is

A stream is a procedure call that the server evaluates repeatedly and pushes to the client.

| Call | Effect |
|---|---|
| `KRPC.AddStream(call)` | creates a new stream, starts evaluating it, and returns its id |
| `KRPC.SetStreamRate(id, rate)` | limits its updates per second |
| `KRPC.RemoveStream(id)` | ends it |

Server:

* Ids come from one counter per server and are never reused.
* Each update, the server evaluates every stream and sends a `StreamResult` for each one whose value
  changed. The results go in one `StreamUpdate` on the client's stream connection.

Client:

* A manager maps each id to one shared stream state: the latest value or error, the waiters, and the
  callbacks. A handle is the user's view of that state.
* An update thread reads the stream connection, applies each result to its shared state, wakes the
  waiters and calls the callbacks.

### States

A stream has one server-side state machine per client, and the client mirrors it.

| State | Entered by | Leaves to |
|---|---|---|
| live | `AddStream`, `AddFunctionStream`, `AddEvent`, a procedure returning an event | ended |
| ended | `RemoveStream`, an error, the server removing it, disconnect | (terminal) |

After a stream ends, the server sends nothing more for its id.

### Start on Add

**A stream is evaluated from the update after it is added.** There is no deferred start, and
reading a stream blocks until its first value arrives.

Server:

* The first evaluation of a stream always sends its value.

Client:

* **Results for unknown ids are kept.** The add reply arrives on the RPC connection and the first
  result on the stream connection, so the result can arrive first. The client notes each id from
  the add reply while it holds the RPC lock, in reply order. Several threads can add at once, so
  ids are noted in increasing order but registered in any order.
* For an id above the highest noted id, or noted but not registered yet, the client keeps the
  latest value and any ending. Registering the id applies them under the new stream's lock.
* A result for any other absent id belongs to an ended stream and is dropped.
* A callback added to a stream that has a value is called once with it, so it sees the first value
  however the add and the first result race. An event callback follows "Callbacks" under "Events".
* The buffer is a stopgap. A single connection ([single-connection.md](single-connection.md))
  orders the add reply before the first result, and removes it.

### One Stream per Add

**Every add creates a new stream with a new id.** Two adds of an equal call are two independent
streams. Each has its own lifetime, rate and event firings.

Server:

* `AddStream`, `AddFunctionStream` and `AddEvent` never return an existing id.
* **One evaluation per stream.** Each stream is evaluated once per update its rate allows, and the
  server never compares calls. Equal streams read equal values, as they are evaluated in the same
  update.
* Each stream sends its own `StreamResult`, so an equal value is repeated in the `StreamUpdate`.

Client:

* The manager keeps one shared state per id. A handle owns its stream, and copies of a handle
  share it.
* `remove()` ends the stream for every copy. Removing it again through any copy does nothing.
* To read one value from several places, such as several threads, pass one handle between them.
  Each add costs one more evaluation per update.

### Removal and Management Calls

The client removes a stream with `RemoveStream`. The server sends no final result for it, as the
client already knows.

The id counter is a high-water mark, the rule the object store uses for object ids:

| Id | `RemoveStream` | `SetStreamRate` |
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
| Removed by the client | none | the client's removed-stream error: `StreamError` in Python and C++, `InvalidOperationException` in C#, `StreamException` in Java |
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
* A procedure stream encodes its value inside its own update, because the encode in the write
  covers every stream of a client. An encode failure then fails one stream. An event's `bool`
  cannot fail to encode, and is encoded in the write.

Client:

* Any error ends the stream. The client needs no knowledge of `StreamRemovedException`, whose type
  only names the cause for the caller.
* On a final result the client stores the error, marks the state ended, wakes all waiters, calls the
  `on end` callbacks and drops the map entry.
* Every later read and `wait` on every handle raises the stored error. Re-raising does not
  grow the error's traceback.
* A value that fails to decode ends the stream, and the client sends `RemoveStream` for it from a
  thread other than the update thread. The C++ client decodes in the handle, see "Implementation".
* **The update thread never dies.** A decode failure for one result becomes that stream's error. A
  failure reading the connection ends the connection: every stream ends with the closed-connection
  error and every waiter wakes. A user callback that throws is reported and the thread continues,
  for both stream and update callbacks.

Old clients surface `StreamRemovedException` as they surface any stream error today. Python builds
it from the service definitions, and the C#, Java and C++ stubs fall back to their generic RPC
exception.

### Waiting and Callbacks

| Situation | `wait()` | `wait(timeout)` |
|---|---|---|
| Update arrives | returns | returns `true` |
| Timeout elapses | n/a | returns `false` |
| Stream ended | raises the ending, per "Endings and Errors" | same |

* The timeout is a deadline. A wake before it with nothing new waits for the remaining time.
* The timed form returns `bool`: `true` when a new value or firing arrived, `false` on timeout.
  Every client changes it in place, where it returns `void` or `None` today. Existing code compiles
  unchanged, as a call used as a statement discards the result. Programs built against the C# or
  Java library must be recompiled, as the return type is part of the compiled method reference there.
* Stream callbacks receive values only. Errors and endings are not passed, so typed callback
  signatures stay typed.
* No stream or manager lock is held while a callback runs. Each callback has its own lock, held
  while it runs, so one callback never runs on two threads at once. It records the version of the
  last value it was given, and an older value, or a value after the stream ended, is skipped.
* Each handle can take an `on end` callback, which receives the ending exception. It is called once,
  after the final result is applied and outside the manager's locks, so it can call RPCs. Without it,
  a program driven only by callbacks never learns that its stream ended.

### Game State Changes

A game object the game can build again is dormant (`GameObjectState.Dormant`). Examples are a
vessel during a load, a part of an unloaded vessel, a contract before the contract system has parsed
it, and the ship of an editor that has not opened it yet. A lookup of a dormant object throws its own exception, the counterpart of
`ObjectDestroyedException`:

```csharp
/// <summary>
/// The game object that a service object refers to exists, but is not loaded.
/// For example, the game is loading, or the vessel carrying the part is unloaded.
/// </summary>
[KRPCException (Service = "KRPC")]
public sealed class ObjectNotLoadedException : System.Exception
```

Server:

* The dormant case of `NotResolvable`, in `FlightGlobalsExtensions`, `PartId` and the other service
  objects, throws `ObjectNotLoadedException` in place of `InvalidOperationException`. A direct RPC
  receives it too.
* A procedure stream or a service event treats it as a yield. The update is skipped and the stream
  keeps its last sent value.
* The hold has no limit, and lasts while the object is dormant. A stream over a part of an unloaded
  vessel resumes when the vessel loads. After a load, a stream over a surviving object carries on,
  and one over an object that is gone gets `ObjectDestroyedException` and ends.
* A procedure called outside its game scenes throws `KRPC.UnsupportedSceneException`, in place of
  `RPCException`. A procedure stream or a service event holds on it as on `ObjectNotLoadedException`,
  from its first evaluation, so a stream of a flight-only property survives a visit to the space
  center. A stream added in the wrong scene waits for a scene where the procedure is available.
* A procedure stream held from its first evaluation sends nothing, so a read waits for the object to
  load. A held event still sends its first result, `false`.
* Function streams and function events are never held. They end on the error, as "Function Streams
  and Events" describes.

Client:

* A hold sends no result. A program that needs to know streams `GameStateLoads`, or the vessel's
  loaded state.

Settling covers every loaded game. A state settles once its vessel or editor part count is
unchanged across two ticks.

* A count of zero settles too, once it has held for 1 s and 10 updates. No load was measured to
  list zero vessels before its first one, so the window is a margin.
* An editor with no ship counts as zero parts.
* After a scene load request, nothing settles until the next scene starts, as the old scene can run
  more physics ticks first.
* The server stops in the main menu, so a held stream ends with the closed connection there.

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

### Firings From Creation

An event fires from the update after it is created, as every stream starts on add. A firing before
the first `wait` is kept.

* `Service.Event.Trigger` sets the value sent in the next update.
* A new handle's `seen` is 0, so a firing buffered before the add reply counts.

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
* A pending end is acted on only when the stream updates. Every stream starts on add, so every
  event updates. A rate limit delays the end by up to one period.

### Wait

| Situation | `wait()` | `wait(timeout)` |
|---|---|---|
| Fired since `seen` | returns | returns `true` |
| Fires while waiting | returns | returns `true` |
| Timeout elapses | n/a | returns `false` |
| Stream ended by an error | raises the typed error | raises the typed error |
| Stream removed by the server | raises `KRPC.StreamRemovedException` | raises `KRPC.StreamRemovedException` |
| Removed by the client, through any copy of the handle | raises the client's removed-stream error | same |
| Connection closed | raises the closed-connection error | same |

* A firing not yet seen when the ending arrives wins. `wait` returns, and the next `wait` raises.

### Callbacks

* An event callback is called once per firing that arrives after it is added.
* The server sends no `false` after a firing, so an event's latest value stays `true`. A callback
  added later is called straight away, once, only if the event has a firing not yet passed to a `wait` on
  that handle, or to any of the event's callbacks. A handle that never waited and had no callbacks
  therefore replays its last firing.

## Function Streams and Events

Server side functions land after this work and add `KRPC.AddFunctionStream` and an `AddEvent` over a
function. They follow the model above. What they add:

* **One stream per add.** Every `AddFunctionStream`, and every `AddEvent` over a function, creates a
  new stream.
* **`StateVariable` state** belongs to the function, and every evaluation advances it. Two streams of
  one function advance it twice per update. A separate state needs a separate build.
* **Errors.** An exception from a function, and a value that fails to encode, end only that stream.
  A function raising `KRPC.StreamRemovedException` itself ends its stream with that error, the same
  final result, so no reservation is needed.
* **A yield stays an error** (SSF, "A yield is an error, and nothing retries"). A yielding procedure
  continues through a continuation that a restart discards. Restarting re-runs it from scratch every
  update, so it never completes.
* **Never held.** An `ObjectNotLoadedException` ends a function stream or function event like any
  other error. A held re-run would repeat the state changes and game writes made before the throw.
  A function that should survive a load or an unloaded vessel catches the exception, and its
  handler chooses the result and the state:

  ```
  TryCatch(body, "KRPC", "ObjectNotLoadedException", message, handler)
  ```

  An event's handler returns `false`, so the event does not fire. A stream's handler can return a
  last good value kept in a `StateVariable`. Without a handler, the stream ends at the first load or
  vessel unload it meets, and the client sees the error. `KRPC.UnsupportedSceneException` is caught
  the same way, for a function that calls a procedure outside its game scenes.

# Part 2. Current Implementation

The audit dates from 2026-10-10, before the split into #1118 to #1121. It describes `main` with
phase 0 applied. Phase 0 moves fixes already written in the SSF stack, and changes no part of the
model. Each defect names the phase or PR that fixes it.

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
| **Events start lazily**, so a firing of an `AddEvent` condition before the first `wait` is never seen | 4 |
| **Equal adds share one stream.** One `RemoveStream` ends it for every handle (#902). A re-add of a stream marked for removal returns an id the client has dropped, which works only because `Stream.Start` resends the value | 5 |
| **A dormant object raises the same error as a failure.** A dormant lookup throws `InvalidOperationException`, the type of many real errors, so a stream, a function or client code cannot tell "not loaded" from a failure. A stream is terminal on any error. During a quickload, a stream over a vessel the game has not rebuilt yet is removed, though the vessel exists in the loaded save. This is the #877 symptom in its current form. A stream over a part also ends when its vessel unloads | #1120 gives the dormant lookup its own exception; phase 6 holds the stream on it in place of ending it |
| **An empty save never settles.** `SweepObjectStore` settles a state only when the vessel or editor part count is above zero. In a save with no vessels, a vessel that is gone is reported as between states, never as destroyed. Under the design, a stream over it would be held forever | #1121 |
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
| `Stream.wait(timeout)` returns nothing, so a timeout cannot be told from an update | x | x | x | x | 3 |
| Close does not wake waiters | `Event.wait` re-waits | x | x | x | 3 |
| Server-side disconnect wakes nobody | x | x | x | x | 3 |
| No ending reaches a callback. Phase 0 stops passing errors to callbacks, and there is no `on end` callback, so a program driven by callbacks never learns that its stream ended | x | x | x | x | 3 |
| Update thread dies on a decode or parse error | x (#198) | process ends | x | `std::terminate` | 3 |
| Other | `Event.wait` resets the value without a removal guard | `Start(wait)` checks removed outside the lock; `Event.Wait` resets the value without a removal guard | `start()` skips the removed check | busy spin after server close; one `unique_lock` shared by all handles; `remove()` inside `acquire()` deadlocks | 3 |
| `remove()` on one handle ends the stream for all handles from equal adds (#902). Fixed by the server change alone | x | x | x | x | 5 |
| A callback added to a stream that has a value is not called until the value changes | x | x | x | x | 4 |
| A result for an unknown id is dropped. Clients avoid losing the first value by adding with `start = false` and then calling `StartStream`, one extra RPC per stream | x | x | x | x | 4 |

# Part 3. Phases

The phases land together as one PR, before server side functions. Each phase is a self-contained
step within it, built and tested in order. The SSF stack is then rebased onto the phases, and its function streams and events adopt the model as
listed under "Function Streams and Events".

## Phase 0: Fixes Moved Out of SSF

The SSF stack fixed generic stream and event defects alongside its own code. Phase 0 moves them
onto `main` unchanged, so they ship before SSF and the later phases start from them. It is
extraction only, with no protocol change.

| Where | Fix |
|---|---|
| Server | `EventStream.UpdateInternal` turns an exception from its condition into an error result, so an event cannot stop the update loop. A firing resets the result, clearing an earlier error. `Services.HandleException` accepts an exception with no stack trace. Streaming `KRPC.AddEvent` is refused, as it would add an event per update |
| Clients | A removed stream throws on a wait, a read or a start through any handle, and a removal wakes its waiters. Removing it again through another handle does nothing. A stream callback is not called for an update that is an error, and reading the stream throws it. Java and C++ guard the `Event.wait` reset against a removal |

## Phases 1 to 6

| Phase | Scope | Notes |
|---|---|---|
| 1. Server hardening | catch around `stream.Update()`; encode procedure streams in `UpdateInternal`; prune `protoResultCache` on removal; the high-water rule for management calls; document `Service.Event.Trigger` as main thread only and fix `OnTimer`; reproduce the stream over a procedure returning an event, and if confirmed have `AddStream` reject such a procedure | no protocol change |
| 2. Final results | `KRPC.StreamRemovedException`; `Service.Event.Remove` records a pending end that is sent after any unsent firing, and `EventStream` no longer calls `Core.RemoveStream` | protocol docs: states, an error result is final |
| 3. Client terminal states | in all four: an error result ends the shared state; close and disconnect end every stream; waiters always wake; `on end` callback; event cursors; timed waits of streams and events return `bool`; update threads survive decode errors and throwing callbacks; the per-client bugs in the audit | the bulk of the work. Builds on the C++ freezing removal in #1118 |
| 4. Start on add | server: `AddStream(call)` starts the stream, `StartStream` and the `start` flag go, and a first evaluation always sends; clients: results for unknown ids buffered, `start()` and the `start` argument go, a callback added to a stream with a value is called with it; the protocol docs and client guides | depends on 3. **Breaking:** an old client's `AddStream(call, false)` succeeds, as the server drops the extra argument, and starts the stream. The client then fails on `StartStream` at its first read, wait or start, and leaves a server stream it never registered |
| 5. One stream per add (#902) | `AddStream` always creates a stream; the re-add path in `Core.AddStream` and the server's comparison of calls go; the protocol docs, and the C#, Java and C++ guides on stream equality | clients need no code change. **Breaking:** repeated equal adds without a remove now accumulate streams |
| 6. Game state | procedure streams and service events hold on `KRPC.ObjectNotLoadedException` and `KRPC.UnsupportedSceneException`; an event's firing is sent before an error from the same update; TestServer tests of an event that ends without firing. The exceptions, zero count settling and `KRPC.GameStateLoads` shipped in #1119, #1120 and #1121 | in-game tests: a stream over a surviving vessel across a quickload, one over a vessel removed by it, a stream in an empty save, a stream over a part held while its vessel is unloaded, a flight-only stream across a visit to the editor |

## Tests

* TestServer: a service event that removes itself without firing; one that fires and removes itself
  in one update, sending `true` then the error; a procedure stream whose value fails to encode; a
  throwing event (from the superseded design); a stream over a procedure returning an event.
* Per client, against TestServer:
  * error then `wait`, for a stream and an event;
  * a firing before `wait`, and one before the first `wait` of a new event;
  * a constant-valued stream read straight after its add, and a callback added after its first
    value, both receiving that value;
  * two threads waiting on one event handle both see a firing;
  * timed `wait` returning `false`, for a stream and an event;
  * a server-removed event;
  * close and server disconnect waking a stream `wait` and an event `wait`;
  * two equal adds giving two ids, and removing one leaving the other live;
  * remove then add of an equal stream receiving a value.
* Core: two equal streams each evaluated and each sent a result, the high-water rule,
  the update loop surviving a throwing stream, a rate set before the first update, a stream held on
  the game scene check. `GameStateLoads` ignoring a part-death sweep, and the zero count settling,
  shipped with #1121. A contract across a load is partly covered by #1120.
* SSF, once rebased: a function stream that catches `ObjectNotLoadedException` surviving a
  quickload, and one that does not ending with it.

## Decisions

Decided 2026-10-10:

* Timed waits of streams and events return `bool`, changed in place in every client. The binary
  break in the C# and Java libraries is accepted.
* A dormant lookup throws `KRPC.ObjectNotLoadedException`, for direct RPCs and streams alike.
* Function streams and function events are never held. The function catches
  `ObjectNotLoadedException` to survive a load. A held re-run would need a deep copy of
  collection state, and would still repeat game writes.
* A hold has no time limit. Fixing the settle check for zero counts makes every load settle.
* The load counter is `KRPC.GameStateLoads`.
* Stream deduplication is removed, and every add is a new stream. It was added to save results on
  the wire for streams such as altitude. Over events and function streams it needs reference counts,
  per-handle cursors and shared function state. Values of equal streams are repeated in the update
  message.
* Equal streams are evaluated separately, once each per update. A procedure with side effects then
  runs once per stream, and the server never compares calls. Equal adds in one client are rare, as
  telemetry, control loops and dashboards add each stream once. A client reading one value in
  several places shares one handle. If a measurement calls for it, property getters alone could be
  shared later, where sharing is not observable.
* Streams start on add. `StartStream` and the `start` flag are removed, which breaks old clients.
  Until the single connection lands, clients buffer results for unknown ids.
* A server-side removal is an error result, `KRPC.StreamRemovedException`, with no wire change.
* A procedure stream or service event over a dormant object is held for as long as the object is
  dormant, e.g. a part until its vessel loads. Sending a non-final error was rejected, as it needs
  a wire field and leaves every client to decide what a non-final error means.
* #877 is answered by per-stream endings plus `GameStateLoads`, not by a global invalidation.
* The phases land as one PR.

Decided 2026-10-11, after a review of the implementation:

* C++ stream freezing is removed, with no deprecation release. The stream changes
  broke it further: the server sends a final result and a first value once, and freezing kept only
  the last skipped message. Holding the tick (`KRPC.HoldTick`) and expression streams, both in
  0.7.0, give values from one physics tick. The removal shipped first, as #1118.
* A client keeps at most the latest value and an ending for an id not registered yet. A new stream
  has no callbacks, and an event's firings coalesce per handle, so nothing else is observable. A
  noted id that is never wrapped, e.g. a raw `KRPC.AddStream` call, then costs one entry.
* The kept results are stored under the new stream's lock, so a later update lands after them.
* A value that fails to decode ends the client stream and sends `RemoveStream` for it. The C++
  client is the exception, see "Implementation".
* No lock is held while a callback runs. Each callback records the version of the last value it
  was given, and a delivery of an older value is skipped. This covers the first call that
  `add_callback` makes with the current value.
* Closing a connection never waits on a lock its caller holds. The closing thread ends every
  stream before it joins the update thread, and the update thread gives up on a held stream lock
  once a close is requested.
* An expression cannot call a procedure that returns an event, as `AddStream` cannot stream one.

Decided 2026-10-11, after a second review:

* `AddStream` and expressions refuse a procedure returning a stream as well as an event. A stream
  over `KRPC.AddStream` added a stream per update while the update loop enumerated them.
* A late event callback is called only for a firing not yet passed to a `wait` on its handle or to a
  callback. The server still sends no `false` after a firing.
* A procedure outside its game scenes throws `KRPC.UnsupportedSceneException`, and streams hold on
  it from the start. Functions can catch it.
* Deliveries to one callback are serialized by a lock of its own, and recheck the version and the
  ending under it.
* Ending every stream on close or disconnect takes stream locks in repeated non-blocking passes, so
  a thread holding one stream's lock while it waits on another is woken. Close does not join the
  update thread while the closing thread holds a stream lock.
* An error from an event's update waits for an unsent firing, as a server-side removal does.

Fixed 2026-10-12, after a third review:

* Python: `close()` hung while its caller held `stream_update_condition`.
* C#: `Dispose` from a callback's first call deadlocked with the update thread.
* C++: a late event callback replayed a firing after the end, and its replay was lost to a
  concurrent `false`. Event callbacks are now gated on the firing count. The first call of a late
  callback blocked on the callback lock, and `remove()` after `get_condition_lock().lock()`
  deadlocked.
* All clients: an id noted but never registered is dropped on `RemoveStream`.
* C#: old stubs note ids from a `GetServices` listing, as Java does.

Fixed 2026-10-12, after a fourth review:

* Python and Java: a callback's first call deadlocked with the update thread, which waited for the
  callback's lock. The update thread now queues its values for the adding thread, as C# did.
* C#: a close could replace a server ending with the closed error. All clients now keep it in
  `to_end`.
* Late event callbacks: C# and Java counted value callbacks on the event's stream. All clients now
  count only event callbacks, when they are called.
* All clients: a removed callback could be called once more, and take a firing. Update callbacks
  ran after close. C# and Java kept results after close.
* Python: a `KeyboardInterrupt` during a first call or an end callback on a user thread was
  swallowed.
* C++: `close()` hung after a raw `get_condition_lock().lock()`. The hold counts are replaced by
  a re-entrant mutex that knows its owner.

# Client Reference

Decided 2026-10-12, after a fourth review found the clients diverging again: the Python client is
the reference implementation. C#, Java and C++ follow its structure and names, and differ only where
the language forces it. A behavior change lands in Python first, then is ported.

## State

| Object | State | Guarded by |
|---|---|---|
| Manager | registry `id -> stream`; `issued` (highest id noted); `unregistered` ids; kept results per id (latest value, then an ending); `to_end` (streams out of the registry and not yet ended, with each ending); `closed`; `close_requested` | update lock (re-entrant), except `close_requested`, a flag |
| Stream | value, `updated`, `version` (values received), `fired` (true values received), `callbacks_fired` (highest firing passed to an event callback), `replaying` (the firing a replay in flight will pass), ending, callbacks, end callbacks | its condition, then the update lock |
| Callback | function, kind (value or event), `version` passed, `adding`, `missed` queue | its own re-entrant lock, held while it runs; `adding` and `missed` under the update lock |
| Event handle | `seen`, the firing count when a `wait` on it last returned | the stream's condition |

## Locks

* Order: a stream condition, then the update lock. The RPC lock, then the update lock. A callback
  lock, then the update lock. No thread waits on another thread while it holds the update lock.
* Stream conditions and callback locks are re-entrant, and can say whether the current thread holds
  them. C++ wraps its mutex to provide this.
* The update thread never blocks on a lock a user thread can hold. It takes a stream condition in
  50 ms timed tries, and gives up once `close_requested` is set. It takes a callback lock in 10 ms
  timed tries, and gives up when `close_requested` or the callback's `adding` is set.

## Thread Roles

| Thread | Does |
|---|---|
| RPC caller | notes ids from replies in reply order (`note_issued`), and removals on success only (`note_removed`), under the RPC lock |
| Update thread | decodes results under the update lock; then per stream, under its condition, stores the value or ends it and notifies; then calls the callbacks with no lock held; then the update callbacks, unless `closed` |
| Adding thread | registers a callback, then makes its first call after a non-blocking try of the callback lock. While the first call runs, `adding` is set and the update thread queues its values in `missed`. The adding thread passes them on, and clears `adding` in the same update-lock hold that finds `missed` empty |
| Closing thread | sets `close_requested`; moves every registered stream to `to_end` with the closed error; ends `to_end` in passes of 10 ms tries until it is empty; joins the update thread unless it is that thread or holds a stream condition or the update condition |

## Rules

* A final result moves its stream from the registry to `to_end` as it is decoded. The update thread
  or the closing thread then ends it with that result, so a close never replaces a server ending.
* A callback is passed a version only if it is still added, the version is newer than its last, and
  the stream has not ended. A value queued in `missed` before the end is still passed.
* An event callback that is passed a firing raises `callbacks_fired`. A late event callback replays
  only if `fired > max(seen, callbacks_fired, replaying)`. Value callbacks on the event's stream do
  not count. A replay reserves its firing in `replaying`, and clears it if the callback is not called.
* A remove of a stream in `to_end` ends it with that ending, and sends no `RemoveStream`.
* An exception from a callback is reported on the update thread. On another thread, Python lets a
  `BaseException` that is not an `Exception` propagate, and Java an `Error`. One from a first call
  removes the callback first, so a failed add adds nothing. One from an end callback during a close
  or a remove is raised once every stream has ended and the `RemoveStream` call is sent.
* A result for an id above `issued`, or in `unregistered`, is kept, unless `closed`.

## Conformance Tests

Each client has a test of each behavior, named after it in the client's style. With the per-client
list under "Tests", these make the conformance set.

| Behavior | Test |
|---|---|
| Values during a first call reach the callback on the adding thread, and the update thread does not wait | values during a first call are queued |
| A first call can wait for later values of its stream | the first call of a callback waits for updates |
| The update thread gives up on a callback lock once close is requested | close while an update waits for a first call |
| Close from a first call, and from a callback on the update thread | close from the first call of a callback; close from a callback |
| A removed callback is not called, and takes no firing | a removed callback is not called; a removed callback does not take a firing |
| A firing passed to a value callback is still replayed to a late event callback | a firing passed to a value callback is replayed |
| Update callbacks stop once closed | update callbacks are not called once closed |
| A closing thread holding a stream's condition ends it with its server ending | a closer holding the condition keeps a server ending |
| End callbacks | end callback on remove, on error, on close, on connection failure, added after the end; remove end callback |
| A fatal exception from a first call propagates (Python, Java) | a first call propagates keyboard interrupt / an error |
| A value queued as a first call ends is passed | a value queued as a first call ends is passed |
| A replay that does not call its callback leaves the firing | a callback removed before its replay takes no firing |
| A remove after a decoded final result keeps the server ending | remove keeps a server ending |
| A fatal exception from an end callback does not stop a close or a remove (Python, Java) | close / remove with an end callback that exits (or throws an error) |

# Implementation

All phases are built as one change, with in-game tests for phase 6. Where it departs from the
design:

| Area | Divergence |
|---|---|
| Buffering | The C# and C++ stubs mark the calls that return a stream or event id. Java finds them from the stubs' return types |
| C# API | `IConnection.Invoke` gains an overload taking the return type. A class implementing `IConnection` must add it |
| C++ | Each stream has one `krpc::RecursiveMutex` and `krpc::Condition`, shared by its handles, which give the re-entrancy and owner query of Python's `Condition` over an `RLock`. Each handle has its own `std::unique_lock` over the mutex. Values are decoded by the handle, so a value that fails to decode is thrown to the reader and does not end the stream. A callback is skipped for such a value, and the failure is logged once per stream |
| Java | A closed connection ends streams with `StreamException`, caused by `ConnectionException`, as `get` and the waits cannot throw an `IOException`. The untimed waits stay `void` |
| Close | Java's close never joins the update thread. `getCondition()` is public API used with `synchronized`, which rules out a timed lock. Close and disconnect move every stream to `to_end`, end them under the update lock, and notify their conditions from short-lived threads. Storing a value still waits on a condition another thread holds |
| Waits across streams | A thread holding one stream's lock while it waits for another stream's next value stalls the update thread when the first stream updates, in every client. Only close and disconnect are fixed for this pattern |
| Late callbacks | An event that has ended replays no firing to a late callback, though `wait` still returns for it |
| Close join | Python, C# and C++ skip the join when the closing thread holds a stream condition or the update condition |
| Update callbacks | Only Python and C++ have connection-wide update callbacks |
| C++ | The stream manager owns a copy of the client, so streams outlive the copy that added them. The registry holds weak pointers, and drops an expired one when a result arrives for it |
| Java, C# | A stub lookup that fails falls back to the server's `GetServices`, fetched once, so a stream id is still noted with old or missing stubs |

Parts of the design shipped in the earlier PRs, which made these choices:

| PR | Choice |
|---|---|
| #1120 | A contract, a waypoint or an alarm missing while the game is between states is dormant. A contract or waypoint is also dormant until `ContractSystem.loaded`, as the contract system parses its contracts a frame after the scene loads it. An Infernal Robotics servo group of an unloaded vessel is dormant, as groups are found from the vessel's parts |
| #1121 | Vessels are known only in a scene with a planetarium, as an editor lists none. A scene load request starts a change of state, as the game fills in the next scene while it loads. Measured in quickloads, scene changes and editor visits, a load's vessel list goes from absent straight to a nonzero count, so the zero-count window is a margin |

## SSF Rebase

* `EventStream` holds on every held error and has no option to not hold. SSF function events must
  never be held (see "Function Streams and Events" and [server-side-functions.md](../server-side-functions/server-side-functions.md)),
  so the rebase adds the option back.
* The v0.6.0 LINQ `KRPC.AddEvent` is built on `Service.Event`, so it is held like a service event
  until SSF replaces it.

