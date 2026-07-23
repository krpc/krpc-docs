# Per-stream invalidation on exception (issue #877)

**Status:** proposal — design agreed, not yet implemented (2026-07-03).

## Context

[Issue #877](https://github.com/krpc/krpc/issues/877) asks for a way for clients to
detect that their streams have gone stale after a game-state change (quickload etc.),
proposing a global protocol-level "all streams invalidated" notification driven by a
server-side state generation counter.

We prefer a granular design: when an individual stream is no longer valid — detected by
its underlying RPC throwing an exception — the client is notified and the stream is
removed, per stream. A stream is not necessarily tied to a single game object, so
"object destroyed" is not the right trigger; "the underlying call threw" is.

**Key finding:** the server already does this for procedure-call streams.
`ProcedureCallStream.UpdateInternal` (`core/src/Service/ProcedureCallStream.cs:45-53`)
catches exceptions, converts them to an `Error` via `Services.Instance.HandleException`,
and sets `Changed`; `Core.StreamServerUpdate` (`core/src/Core.cs:550-551, 566-572`)
sends that error to the client exactly once, then removes the stream. Existing tests
cover it (`client/python/krpc/test/test_stream.py:201-237`). The quickload scenario
genuinely triggers this path: e.g. `Vessel.InternalVessel`
(`service/SpaceCenter/src/Services/Vessel.cs:67-69`) re-resolves by Guid on each access
and `FlightGlobalsExtensions.GetVesselById` throws when the vessel is gone.

The actual gaps this design fixes:

1. **`EventStream` has no exception handling** (`core/src/Service/EventStream.cs:35-40`):
   a throwing event predicate propagates out of `stream.Update()` (`Core.cs:537`, also
   unguarded) and aborts `StreamServerUpdate` for **all clients, every frame, forever** —
   no error sent, stream never removed.
2. **Clients don't treat an error result as invalidation**: the stream stays in their
   local manager map forever; `wait()` blocks forever after an error; C# and C++ have
   crash bugs when a callback is registered on an erroring stream (C# update thread dies
   from an InvalidCastException; C++ calls `std::terminate`).
3. **The "error result ⇒ stream removed" convention is undocumented** in the protocol
   docs.

Decisions:

- **Protocol: implicit convention** — no `.proto` change; document that a `StreamResult`
  carrying an error means the server has removed the stream. The server always removes
  on error, so this is unambiguous; `bool removed` can be added proto3-compatibly later
  if transient (non-fatal) stream errors are ever wanted.
- **Client scope: all four stream-capable clients** — Python, C#, Java, C++. (lua/cnano
  have no stream support; websockets/serialio are conformance-test packages.)
- **Typed `ObjectDestroyedException`: deferred** to a follow-up tied to issue #771.

## Phase 1 — Server fix (core/)

### 1.1 `core/src/Service/EventStream.cs` — catch exceptions in `UpdateInternal()`

Mirror `ProcedureCallStream.UpdateInternal`:

```csharp
public override void UpdateInternal() {
    if (continuation != null) {
        try {
            if (continuation())
                Trigger();
        } catch (System.Exception e) {
            var result = StreamResult.Result;
            result.Reset();
            result.Error = Services.Instance.HandleException(e);
            Changed = true;
            continuation = null;  // poison, like StreamContinuation does
        }
    }
    if (shouldRemove)
        Core.Instance.RemoveStream (Id);
}
```

Reuses `Services.Instance.HandleException` (`core/src/Service/Services.cs:367-387`) —
already maps `[KRPCException]` types and honors `VerboseErrors`. Core's existing
`HasError → removeStreams` logic then notifies + removes with no further changes.

### 1.2 `core/src/Service/EventStream.cs` — guard `Sent()`

`Sent()` (lines 51-56) unboxes `(bool)result.Value`; after the error path calls
`result.Reset()`, `Value` is null → NRE in Core's `Sent()` loop (`Core.cs:560-562`).
Change to:

```csharp
if (result.HasValue && (bool)result.Value)
    result.Value = false;
```

### 1.3 `core/src/Core.cs:535-541` — defense-in-depth around `stream.Update()`

Wrap `stream.Update()` in try/catch: on `System.Exception`, log and set an error
`ProcedureResult` on the stream (the `Stream.Result` setter in
`core/src/Service/Stream.cs` sets `Changed` when `HasError`). Guarantees no stream
implementation can ever abort the update loop for all clients.

## Phase 2 — Protocol documentation

`doc/src/communication-protocols/messages.rst` — in the Streams / `StreamResult`
section (~lines 179-226), document:

- When a stream's RPC throws, the `result` contains an `error`; the server sends it
  **exactly once** and then removes the stream.
- Clients must treat such a stream as invalid: no further updates will arrive for its
  id; calling `KRPC.RemoveStream` is unnecessary but harmless (server tolerates unknown
  ids).
- Note this is how clients detect streams invalidated by game-state changes
  (quickload/revert) — the #877 scenario.

## Phase 3 — Client changes (uniform semantics)

For each client, on receiving an error `StreamResult`:

1. Build/store the exception as the stream value (existing behavior — keep).
2. **Mark the StreamImpl removed** and **delete it from the manager map** (no leak;
   later updates for the id are already skipped; server ids are never reused).
3. Reading the value keeps raising the stored error forever — NOT "Stream does not
   exist".
4. `wait()` / `start(wait=True)` on an invalidated stream raises the stored error
   immediately instead of blocking forever.
5. `remove()` on an invalidated stream is an idempotent no-op that preserves the stored
   error (no RPC, no overwrite with "Stream does not exist").
6. Callbacks: deliver the exception where the callback type permits (Python/Java);
   where it can't (C# typed callbacks, C++ `std::function<void(std::string)>`), skip
   callbacks for the terminal error and document detection via `Get()`/`wait()` —
   fixing the current crashes.

### 3.1 Python (`client/python/krpc/`)

- `streammanager.py` `StreamImpl`: add `_removed` flag + `removed` property.
- `StreamManager.update()` (lines 160-180): in the `HasField("error")` branch, after
  `_update_stream(...)`, mark removed and `del self._streams[result.id]`.
- `StreamImpl.remove()` (lines 96-99): early-return if `_removed`; set `_removed` for
  user-initiated removal too.
- `stream.py` `Stream.wait()` / `start()`: if impl removed and stored value is an
  Exception, raise it before waiting.
- `event.py` `Event.wait()` (line 38): don't reset value to `False` when
  removed/errored — currently clobbers the stored error then blocks forever.

### 3.2 C# (`client/csharp/src/`)

- `StreamImpl.cs`: `Removed` property; idempotent, error-preserving `Remove()`.
- `StreamManager.cs` `Update()` (lines 90-109): on error, mark removed +
  `streams.Remove(id)`; wrap callback invocations in try/catch. Fix `Stream.cs`
  typed-callback wrapper (~line 137): skip when value `is Exception` (currently
  InvalidCastException kills the update thread).
- `Stream.cs` `Wait()` / `Start(wait)`: if removed, rethrow stored exception instead of
  `Monitor.Wait`.

### 3.3 Java (`client/java/src/krpc/client/`)

- `StreamImpl.java`: `removed` flag; idempotent `remove()`.
- `StreamManager.java` `update()` (lines 68-89): on `hasError()`, mark removed +
  `streams.remove(id)`; per-callback try/catch so a throwing callback can't kill the
  update thread.
- `Stream.java` `waitForUpdate*()` / `startAndWait()`: if removed, throw stored error
  immediately (reuse `get()`'s unwrap logic, lines 100-107).

### 3.4 C++ (`client/cpp/`)

- `stream_impl.hpp/.cpp`: `removed` flag + `has_error()` accessor.
- `stream_manager.cpp` `update()` (lines 70-90): on error, mark removed +
  `streams.erase(id)`; guard the callback dispatch with `if (!stream->has_error())` —
  currently `get_data()` rethrows inside the update thread → `std::terminate`.
- `stream.hpp` `wait()` / `start(true)`: if impl removed, call `impl->get_data()`
  (rethrows) instead of waiting.

## Phase 4 — Tests

### 4.1 TestServer (`tools/TestServer/src/TestService.cs`)

Add a throwing event next to `OnTimer` (~line 452), e.g.
`ThrowingEvent(uint updatesBeforeThrow = 0)` whose predicate throws
`InvalidOperationException` after N updates — covers both immediate and later variants.
Client bindings regenerate via the existing `clientgen` / `services-testservice`
targets in each client BUILD file.

### 4.2 Python tests (`client/python/krpc/test/test_stream.py`, `test_event.py`)

Extend the existing exception tests (lines 201-237):

- after the error raises, the id is gone from `conn._stream_manager._streams`;
- repeated reads keep raising the same error;
- `wait()` raises immediately (guard with timeout — must not hang);
- `add_callback` callback receives the exception object;
- `remove()` after invalidation is a no-op, error still raised;
- `test_event.py`: throwing event — `event.wait()` raises, doesn't hang.

### 4.3 C# / Java / C++ tests

Mirror the Python cases in `client/csharp/test/StreamTest.cs` + `EventTest.cs`,
`client/java/test/krpc/client/StreamTest.java` + `EventTest.java`,
`client/cpp/test/test_stream.cpp` + `test_event.cpp`. Critical regressions to cover:
error arriving while a callback is registered must not kill the update thread (C#) or
terminate the process (C++); wait-after-error must not block.

### 4.4 Core unit test

Small unit test for `EventStream.UpdateInternal` + `Sent` after a throwing continuation
under `core/test/Service/` (the exception path doesn't need `Core.Instance`).

## Verification

1. `bazel test //core:test`
2. `bazel test //client/python:test //client/csharp:test //client/java:test
   //client/cpp:test` — each spins up TestServer; new tests exercise the full path:
   server exception → error StreamUpdate → client invalidation.
3. Manual #877 scenario in KSP: stream on a vessel, quicksave, destroy vessel,
   quickload → client gets `ArgumentException("No such vessel ...")` raised once from
   the stream; `wait()` doesn't hang; server log shows "Removing stream as it returned
   an error"; no per-frame exception spam / frame-rate degradation.
4. Regression: existing event tests (`OnTimer`, `OnTimerUsingLambda`) still pass — they
   exercise the `shouldRemove` path through the modified `UpdateInternal`.

## Follow-ups (out of scope)

- **Typed `ObjectDestroyedException`** in SpaceCenter lookups
  (`FlightGlobalsExtensions.GetVesselById` etc.) so clients can distinguish "object
  gone — recreate streams" from bugs; tie to issue #771.
- **Error-less server-side removal**: `Event.remove()` (`EventStream.cs:47-49`) removes
  the stream with no client notification — the implicit convention doesn't cover it. A
  `bool removed` StreamResult field would; revisit if it becomes a problem.
- Respond on issue #877 explaining the granular approach vs. the proposed global
  generation counter.

## Notes / risks

- Python `StreamManager.update` holds `_update_lock` while invoking user callbacks;
  deleting from `_streams` under the same RLock is safe, and a re-entrant
  `stream.remove()` from a callback becomes a no-op via the membership check — add a
  test.
