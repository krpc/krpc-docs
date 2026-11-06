# Clients: scope streams and events with the language's scoping construct

The spec's `test_scoped_removal` asks that a stream can be scoped to a block, and it fails on C#, Java and C++. Python has it for streams only, through a separate method. No client has it for events, and the spec has no test for them.

A scoped stream or event is removed at the end of the block, for every handle to it. Dropping a handle with no block is a separate requirement, `test_drop_last_handle`.

## Work

| Client | Change |
|---|---|
| Python | `Stream` and `Event` are context managers, with `__exit__` calling `remove`, so `with conn.add_stream(...)` and `with conn.add_event(...)` work. Remove `Client.stream`. Breaking |
| C# | `Stream` and `Event` implement `IDisposable`, with `Dispose` calling `Remove` and no finalizer |
| Java | `Stream` and `Event` implement `AutoCloseable`, with `close` calling `remove` |
| C++ | Confirm that a stream or event going out of scope in a block is removed. `test_drop_last_handle` passes, so it probably is, and only the testee reports `Unsupported`. Not tried |

Lua and C-nano have no streams or events.

 * Add a scoped test for events to the spec, alongside `test_scoped_removal`.
 * Update each testee's `scoped` branch, and remove the `test_scoped_removal` lines from `expected-failures.txt`.
 * Update the guides, the design pages and the Python uses of `Client.stream`: the doc scripts and the tests in `client/python` and `service/SpaceCenter`.
