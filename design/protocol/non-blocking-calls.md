# Non-blocking calls and batching (issue #903)

**Status:** proposal (2026-10-25). Planned for 1.0. Client APIs only, with no protocol or server
change. Needs the request-ids reader from 0.8. Split out of [reverse-streams.md](reverse-streams.md),
where it was rung 1. It replaces that doc's earlier `with conn.batch():` context manager.

One of three designs under [issue #903](https://github.com/krpc/krpc/issues/903), which is tracked
as one issue: **non-blocking calls and batching**, [fire-and-forget](fire-and-forget.md), [reverse
streams](reverse-streams.md). Each ships on its own, in that order.

## Context

Control writes are blocking round trips. `control.pitch = x; control.yaw = y` measured about 40 ms.

* **Why writes are slow.** The server processes RPCs only inside `RPCServerUpdate`, once per
  `FixedUpdate`, within an adaptive time budget (`MaxTimePerUpdate`, 1 to 25 ms). A blocking client
  waits up to a tick per call, and sequential setters each pay that wait.
* **Batching exists everywhere except the client APIs.** `Request` carries
  `repeated ProcedureCall calls`. `RequestContinuation` runs them in order in one tick, with
  per-call error isolation and ordered results. Every client hard-codes one call per request.
* **Every client can already build a call as data**, for streams: Python `get_call`, C# `GetCall`,
  Java `getCall`, C++ generated `*_call()` methods, cnano generated builders.
* `KRPC.RunFunction` (#1124) already runs several calls, setters included, in one request and one
  tick.

The old context manager is replaced for three reasons:

* The block is a hidden mode, which the #903 thread rejected as hard to debug.
* Inside it, `vessel.flight().mean_altitude` is typed `float` but returns a handle.
* Chaining breaks, as `vessel.flight()` returns a handle with no `mean_altitude`.

## `submit`

A non-blocking call takes the function and its arguments, as `add_stream` does, and returns a
future:

```python
f = conn.submit(getattr, flight, "mean_altitude")
conn.submit(setattr, control, "pitch", 0.1)       # result not needed
conn.submit(control.activate_next_stage)
f2 = conn.submit(vessel.position, ref)
alt = f.result()
```

* **No duplicated API.** The generated stubs are unchanged. `get_call` already builds the
  `ProcedureCall` through the `_build_call_<name>` builders. Setters gain a builder
  (`_build_call_set_<name>`, in `service.py` beside the getter's), and `get_call` accepts
  `setattr`.
* **Chains run on the server.** A lambda or a `KRPC.Expression` is compiled as `add_stream` does,
  and run with `KRPC.RunFunction` (#1124):
  `conn.submit(lambda: vessel.flight().mean_altitude)`.
* **Typed.** `submit(func: Callable[..., T], *args) -> Future[T]` types the method and lambda
  forms. The `getattr` and `setattr` forms are `Future[Any]`.
* **Ordered.** `submit` writes its request before returning, so calls run in the order they were
  submitted, interleaved with blocking calls. A blocking call is a fence: its result means every
  earlier submitted call has run.
* **Errors** are set on the future as the same exception the blocking call raises. A failed future
  never retrieved is logged when discarded, as asyncio does.
* **Blocking calls wrap `submit`.** `_invoke` becomes a submit followed by `result()`. This is the
  "one core, the sync API wraps it" answer to the open question in [request-ids.md](request-ids.md).

## Reader rules

These extend "Client reader" in [single-connection.md](single-connection.md).

| Rule | Reason |
| --- | --- |
| A submitted slot is pending work: the reader thread reads while streams are open **or** submitted slots are pending, and no caller waits | Otherwise a future with no caller in `result()` never completes |
| `result()` on a submitted slot waits on the future, without taking the reader role | The hand-off costs microseconds, which a non-blocking caller does not notice |
| The dispatcher decodes the result and completes the future | `Future.set_result` runs done callbacks, which are user code, and the reader runs none |
| An unread response is decoded and dropped | Fire-and-forget works without `no_response`, at the cost of the response bytes |

Requests already in the socket buffer should run back to back in one update, as
`Core.RPCServerUpdate` keeps polling until its time budget is spent. Measure this before relying on
it. Overlapping execution with reading is phase 2 of [request-ids.md](request-ids.md), and needs no
client API change.

## Batches

A batch puts several calls in one `Request`, so they run in one update. It uses the same signature:

```python
batch = conn.batch()
f = batch.submit(getattr, flight, "mean_altitude")
batch.submit(setattr, control, "pitch", 0.1)
batch.send()                                      # one request, futures complete together

with conn.batch() as batch:                       # sends on exit
    batch.submit(setattr, control, "yaw", 0.2)
```

* `batch.submit` sends nothing. Its future completes after `send()`.
* A batch is single use. A repeated group of calls is a server side function or a stream.
* Server semantics are unchanged: calls run in order, each call's error is isolated in its
  `ProcedureResult`, and a yielding call delays the whole request. Keep long-running calls out of
  latency-sensitive batches.

## asyncio

No generated `krpc.aio` package. An awaitable property setter is not valid Python, and awaitable
getters break the sync API, so async service classes would duplicate every member. Instead:

```python
alt = await asyncio.wrap_future(conn.submit(getattr, flight, "mean_altitude"))
```

A thin `conn.submit_async` returning an `asyncio.Future` can follow. See
[python-asyncio-client.md](../../issues/python-asyncio-client.md).

## Other clients

Each has a stream form that takes a call as data, and maps `submit` onto its native future.

| Client | Existing form | `submit` | Batch |
| --- | --- | --- | --- |
| C# | `AddStream(() => flight.MeanAltitude)`, `GetCall` | `Submit(() => flight.MeanAltitude)` returns `Task<T>`. Setters: `Submit(() => control.Pitch, 0.1f)`, deriving `X_set_Y` from `X_get_Y`. Continuations run asynchronously | `conn.NewBatch()` with the same `Submit` overloads, then `Send()` |
| Java | `addStream(flight, "getMeanAltitude")`, `getCall` | `submit(...)` returns `CompletableFuture<T>`, completed on the dispatcher | `conn.newBatch()` |
| C++ | Generated `mean_altitude_call()`, `set_mean_altitude_call(v)` | `client.submit<T>(call)` returns `std::future<T>` | `krpc::Batch` over `build_call`. `Client::invoke(schema::Request)` already takes several calls |
| Lua | Dynamic | `conn:submit(...)` returns a handle with `:result()`, which reads until its id | `conn:batch()` |
| cnano | Generated call builders | None. The client is single threaded | `krpc_invoke_batch(conn, calls, results, n)`. Raise the `calls` and `results` capacities in `client/cnano/src/krpc.options`; `krpc.c` hard-codes one call |

## Documentation

Client docs: `submit`, the batch API, and the asyncio route. A "fast control loops" section in
the client guides, which is the issue's use case, covering `submit`, batches and later
[reverse streams](reverse-streams.md).

## Tests

- **`submit`**: a future completes with no caller waiting on it; ordering against blocking
  calls; an error lands on its future only; a done callback runs off the reader; the setter and
  lambda forms; `asyncio.wrap_future` round trip.
- **Batching**: multi-call round trip with mixed success/error results (error isolated
  to its handle); ordering; extend `test_performance.py:11-21` with a batched variant
  demonstrating the latency win (assert batched < N× single, loosely — headless-KSP
  timing is noisy).

## Implementation order

1. Python `submit`, the setter builders and the reader rules, with tests.
2. Python batches, and a batched variant of `test_performance.py`.
3. `submit` and batches in C#, Java, C++ and Lua, then cnano batches.
4. `CHANGELOG.md` entries per component as the final pre-merge commit.
