# Client spec: rule on the behavior clients differ on

Writing a design doc for each client turned up behavior the spec does not settle, where clients differ.
Each question needs a ruling before a conformance test can require an answer.

| Question | Clients today |
|---|---|
| What happens to a client dropped with no close? | C++ closes on the last release. C#, Java and Python stay connected until exit. Lua's socket finalizer closes with no `disconnect` |
| Is a closed, dropped client collected? | Python pins it through `types._wrapped_subclasses` when it has stubs |
| Does a close wait for a callback that never returns? | C++, C#, Java and Python block on the join |
| Is a backlog behind a slow callback bounded? | The queue is unbounded in C++, C#, Java and Python, and waits fall behind it |
| What does a client with no streams do with a `stream_update`? | C-nano and Lua treat it as a protocol error, so a public procedure returning an `Event` ends a Lua connection |
| Does writing a read-only property raise an error? | Lua stores the value locally and sends nothing |

For each question:

* Record the ruling as requirement text in the spec, through a conformance test's docstring.
* Add the test. A client that fails it lists the test in its `expected-failures.txt`.

The client behavior above comes from the client design pages, `doc/src/client-design*`, and the client defects issues.

Related: [conformance-coverage-gaps.md](conformance-coverage-gaps.md), and
[spec-callback-thread-per-connection.md](spec-callback-thread-per-connection.md), which settles a
related question about callback threads.
