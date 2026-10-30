# Client spec: one callback thread per connection

The spec says only that callbacks run "on a thread of the client", never on a thread that makes
calls (`threading-callbacks-run-off-the-caller`). It does not say how many such threads a client
has, or how connections share them. The client guides need to tell the reader, as a callback that
blocks holds up the other callbacks on its thread.

Guarantee that each connection has its own callback thread, in every client with the `callbacks`
and `threads` profiles:

* The callbacks of one connection run on its callback thread, one at a time.
* A callback that blocks holds up the callbacks of its own connection only. The callbacks of
  another connection carry on.

Current state:

| Client | Callback threads |
|---|---|
| Python, C#, Java, C++ | One per connection, the `krpc-dispatcher` thread each session starts |
| Lua, C-nano | No `threads` profile |

The four threaded clients already meet the guarantee, so the work is a requirement and a test:

* Add a requirement under *Callback Threads* in `test_threading.py`, in the `connections`,
  `callbacks` and `threads` profiles.
* Test it with two connections: a callback on the first blocks, and a callback on the second is
  still called for a new value.
* State it in each client guide's callbacks and threading sections.
