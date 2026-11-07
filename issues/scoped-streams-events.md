# Clients: scope streams and events with the language's scoping construct

The spec's `test_scoped_removal` asks that a stream can be scoped to a block, and it fails on C#, Java and C++. Python has it for streams only, through a separate method. No client has it for events, and the spec has no test for them.

A scoped stream or event is removed at the end of the block. In Python, C# and Java this applies to every handle to it. In C++ the block must hold the last copy. Dropping a handle with no block is a separate requirement, `test_drop_last_handle`.

## Work

| Client | Change |
|---|---|
| Python | `Stream` and `Event` are context managers, with `__exit__` calling `remove`, so `with conn.add_stream(...)` and `with conn.add_event(...)` work. Remove `Client.stream`. Breaking |
| C# | `Stream` and `Event` implement `IDisposable`, with `Dispose` calling `Remove` and no finalizer |
| Java | `Stream` and `Event` implement `AutoCloseable`, with `close` calling `remove` |
| C++ | No client change. A stream or event going out of scope in a block is removed, as the conformance tests now confirm. Only the testee reported `Unsupported` |

Lua and C-nano have no streams or events.

 * Add a scoped test for events to the spec, alongside `test_scoped_removal`.
 * Update each testee's `scoped` branch, and remove the `test_scoped_removal` lines from `expected-failures.txt`.
 * Update the guides, the design pages and the Python uses of `Client.stream`: the doc scripts and the tests in `client/python` and `service/SpaceCenter`.

## Notes for Reviewers

**Decisions**

 * **`test_scoped_removal` no longer reads a handle after the block.** A C++ handle kept past the block would keep the stream alive, so the old test could not pass honestly on C++. The test now checks that the server stops evaluating the stream, and a scoped `AddStream` replies with no handle.
 * **C++ differs from the other clients on purpose.** A copy kept outside the block keeps the stream or event running. This matches the destructor semantics `test_drop_last_handle` requires, and is recorded on the C++ design page.
 * **`ScopeEvent` takes a handle the testee already holds.** Events come from the result of an ordinary call, so the shared `Fixture` can make one. The C++ testee copies the event into the block and drops its handle, so the copy in the block is the last one. The other testees keep a dead handle, which no later command uses.
 * **`Client.stream` goes with no deprecation period**, as this draft specified. It shipped in v0.7.0, so this is a breaking change for scripts using it.
 * **C# uses a plain `Dispose`**, with no `Dispose(bool)` and no `GC.SuppressFinalize`, as there is no finalizer. The analyzers in the gates report nothing for it.

**Worth checking**

 * **Removal is an RPC, so leaving a block can raise.** If `remove` fails during the exit, for example on a connection failure in flight, the error surfaces from the block. It can replace an exception from the block's body in C#, chain to it in Python, and be suppressed onto it in Java. A stream or event that has already ended is a no-op on the Python path, and the C# design page says the same for `Remove`. I read this from the code and did not test it.
 * **Java's `close()` declares `RPCException`,** so try-with-resources has to handle it, like every other call in that client.
 * **`with event.stream` removes the event,** as the stream shares its implementation. This is consistent with `test_remove[...stream]`, but has no test of its own.
 * **The stream test uses `wait_until`,** so it does not require removal to have finished when the block ends. A client that removes shortly afterward would pass. The event test has no such tolerance.

**Verification**

 * `//:test`, `bazel build //...` and every client's conformance suite pass, on Linux only. Windows was not run.
 * Only `service/SpaceCenter/test/test_stream_game_state.py` was run in game (7 passed). The other renamed in-game tests were not run. Their only change is `conn.stream` to `conn.add_stream`.
 * There was no separate negative control for the new tests. The removal checks are shared with `test_drop_last_handle`, which is an expected failure on Python, C# and Java because those streams stay on the server. That shows the checks detect a stream or event that was not removed.
