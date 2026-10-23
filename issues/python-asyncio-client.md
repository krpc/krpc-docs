# Python: an asyncio client

Every bundled client is thread based: callers block on a call, and streams are read and dispatched on background threads. Add a Python client built on `asyncio`, where a call is awaited, many calls run concurrently from one event loop, and kRPC fits into async programs such as web dashboards and bots without a thread per connection.

The single connection (#1174) and request ids (#1175) make this a natural fit. One reader task reads the socket and resolves each pending call's `asyncio.Future` by id. Stream updates set stored values and wake awaiting tasks. Callbacks may be coroutines.

To decide:

- A parallel `krpc.aio` package with async service classes and type stubs, or one async core that the sync client wraps.
- The stream API: `await stream.wait()`, async iteration over updates, or both.
- Whether it waits for pipelining (request ids phase 2), which lets concurrent calls overlap on the server instead of queuing behind TCP.

Design: [request-ids.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/request-ids.md), "Client APIs"
