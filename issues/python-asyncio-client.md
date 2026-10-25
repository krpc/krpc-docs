# Python: asyncio support

Every bundled client is thread based: callers block on a call, and streams are read and dispatched on background threads. Make the Python client usable from `asyncio`, so a call is awaited, many calls run concurrently from one event loop, and kRPC fits into async programs such as web dashboards and bots.

The single connection (#1174) and request ids (#1175) make this a natural fit. A non-blocking `conn.submit(func, *args)` is planned under #903, returning a `concurrent.futures.Future`. With it, `await asyncio.wrap_future(conn.submit(getattr, flight, "mean_altitude"))` works with no further changes. This issue adds the async conveniences on top, with no generated async copy of the service classes.

To decide:

- A `conn.submit_async` returning an `asyncio.Future`, or documenting `wrap_future` only.
- The stream API: `await stream.wait()`, async iteration over updates, or both.
- Whether callbacks may be coroutines, run on a given event loop.

Design: [non-blocking-calls.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/non-blocking-calls.md), "asyncio"; [request-ids.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/request-ids.md), "Client APIs"
