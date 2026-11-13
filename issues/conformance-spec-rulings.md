# Client spec: rule on the behavior clients differ on

The client design docs turned up behavior the spec does not settle. For each question:

* Record the ruling as requirement text, in a conformance test's docstring.
* Add the test. A client that fails it lists the test in its `expected-failures.txt`.

## Ruled, needs the test

**One callback thread per connection.** The spec says only that callbacks run "on a thread of the
client", never on a thread that makes calls (`concurrency-callbacks-run-off-the-caller`). It does not
say how many such threads there are. The guides need to say, as a blocking callback holds up the other
callbacks on its thread.

* The callbacks of one connection run on its callback thread, one at a time.
* A callback that blocks holds up only the callbacks of its own connection.

Python, C#, Java and C++ already meet it, each with the `krpc-dispatcher` thread its session starts.
Lua and C-nano have no `concurrency` profile.

* Add the requirement under *Callback Threads* in `test_concurrency.py`, in the `connections`,
  `callbacks` and `concurrency` profiles.
* Test it with two connections: a callback on the first blocks, and a callback on the second is
  still called for a new value.
* State it in each client guide's callbacks and threading sections.

## To rule

| Question | Clients today |
|---|---|
| What happens to a client dropped with no close? | C++ closes on the last release. C#, Java and Python stay connected until exit. Lua's socket finalizer closes with no `disconnect` |
| Is a closed, dropped client collected? | Python pins it through `types._wrapped_subclasses` when it has stubs |
| Does a close wait for a callback that never returns? | C++, C#, Java and Python block on the join |
| Does a second, concurrent close wait for the first to finish? | Python runs the whole close on each caller. C++ returns at once ([client-cpp-defects.md](client-cpp-defects.md)) |
| Is a backlog behind a slow callback bounded? | The queue is unbounded in C++, C#, Java and Python, and waits fall behind it |
| Is a callback passed every value, or the latest? | `test_streams.py::test_callback` says no value is skipped. `test_concurrency.py::test_blocked_callback` and `test_callbacks_run_off_the_caller` say the latest, and `test_blocked_callback` cannot tell the two apart |
| What does a client with no streams do with a `stream_update`? | C-nano and Lua treat it as a protocol error, so a public procedure returning an `Event` ends a Lua connection |
| Does writing a read-only property raise an error? | Lua stores the value locally and sends nothing |

The client behavior comes from the client design pages, `doc/src/client-design*`, and the client
defects issues, such as [client-design-shared-defects.md](client-design-shared-defects.md).
