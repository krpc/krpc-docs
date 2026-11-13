# Clients: defects more than one client shares

Writing the client design docs turned up the first six, in the threaded clients.

* **Dropping the last handle leaves a stream running in C#, Java and Python.** The spec requires the removal, and each guide states it, under Streaming Data and Event Endings. `StreamManager` holds the `StreamImpl`, so the server keeps evaluating the stream and its callbacks keep running. These clients list `test_drop_last_handle` as an expected failure. C++ passes it.
* **A dropped, unclosed client stays connected in C#, Java and Python.** The threads reach the client, so it is never collected. It holds its socket and threads until process exit, and a loop opening connections leaks them. The spec has no ruling on this.
* **One held condition stalls the dispatcher thread.** Applying an update takes each changed stream's condition in turn, so all streams and callbacks of the connection wait for the holder. A wait on a second stream by that holder never wakes, and the dispatcher queue grows. This is `test_wait_holding_another`, marked `@skip` in all four clients.
* **The dispatcher queue is unbounded.** The reader queues every update without coalescing, so a slow callback delays all waiters and callbacks of the connection, and memory grows. In Python, with a 10 ms callback and 1 kHz updates, waiters were about 1700 values behind after 2 s. Java shows the same with a burst of 2000 updates. The spec has no ruling on a bound.
* **A close waits for a blocked callback.** `Session.join` joins the dispatcher thread with no timeout, so a callback that never returns hangs the close. A callback waiting on a lock the closing thread holds deadlocks it, as the skip in the join covers stream conditions only.
* **The guides misstate the callback thread.** Each Threading section says callbacks never run on the program's threads, apart from a first call. The spec has a remove or a close run end callbacks there. In C# and Java, read from code, an end or first call on another thread can overlap a callback on the dispatcher thread.

## From the parity audit and the client guide rewrite

Still open from the client API parity audit (2026-07-21) and the client guide rewrite (2026-10-29),
re-checked against `main` on 2026-11-09.

* **A short wire tuple decodes short in Python, Lua and C-nano** (`test_too_few_items[tuple]`).
  Structures check their field count.
* **A failed write of the connection request escapes the handshake unwrapped:** `OSError` in Python,
  `std::runtime_error` in C++, `IOException` in C# and Java. C-nano returns
  `KRPC_ERROR_ENCODING_FAILED`, and the fix returns the write's own error
  (`test_handshake_failed_write`).
* **C# and Java have no connection-wide update wait or callback,** which Python and C++ have
  (`test_wait_for_update`, `test_update_callback`). The guides leave them out until the API exists.
* **A callback slower than its stream can keep `addCallback` from returning, in C#, Java and C++.**
  The adding thread makes the callback's first call, then passes on every value the dispatcher
  queued meanwhile. One shared design. `test_callback_one_call_at_a_time` is marked `@timing`. Not
  re-checked since C4.
* **C++ and Java wait indefinitely only for a zero handshake or stall timeout,** which the spec makes
  an argument error (`test_handshake_timeout_values[zero]`). To decide: how each client spells an
  infinite timeout, then fix the code, the guides, the Java 0.8.0 changelog entry and the Javadoc
  on the timeouts in `Connection.java` together. The C++ guide tells readers to pass zero, and the
  Java guide suggests a long timeout such as `Duration.ofMinutes(5)`.
* **Mapped exceptions are thrown two ways.** Python and C++ throw a generated class derived from
  the native type, such as `InvalidOperationException(RuntimeError)`. C# throws the `System` type
  itself (`Connection.GetException`), and Java registers `exception.native` in place of the
  generated class (`java.tmpl`). So the C# and Java references document generated classes the
  clients never throw. Throw the derived class everywhere, which breaks no program, as a catch of
  the native type still matches:
  - C#: clientgen gives each mapped exception its `System` base, and `GetException` throws the
    registered types. None of the 11 is sealed.
  - Java: the generated class extends the native type and is registered. `TimeoutException` stays
    the exception, as Java has no unchecked native type for it.
  - `test_mapped_exceptions` then requires the client's own type, with the native type among its
    bases. It allows both forms today.
* **`doc/src/communication-protocols/messages.rst` does not mention `GetClientName`.**
