# Single connection review: open findings

**Status:** open. The findings of the 2026-10-30 review of the
[single connection](single-connection.md) PR (#1219, predicted) and the client conformance stack
above it. The conformance suite at the stack tip served as the spec. Paths are as of the single
connection PR unless noted, and line numbers may drift.

## Done

These are folded, or to be folded, into the commits that introduced the code. The single
connection changelog entries are renumbered to #1219.

- **The reader thread stops reading once a close starts** (C#, Java, C++), as in Python.
- **A close after a failure ends the streams with the failure's cause and reason** (Python, C#,
  Java, C++). Tested by `test_close_after_failure`.
- **C++ lifetime fixes.** A removed callback is destroyed after the update lock is released. The
  dispatch moves its callbacks, and work dispatched after the queue stops is kept until the
  session is destroyed.
- **C-nano.** The size prefix is read into 32 bits, which keeps a 16-bit `size_t` safe. A
  receive failure during a call ends the session.
- **A size prefix over 32 bits fails the connection** (C-nano, Python, C++, Lua). Tested by
  `test_size_over_32_bits`. This is an expected failure in Java, which raises an RPC error.
- **Lua.** A message that fails to decode is `MALFORMED_MESSAGE`. A failed client setup sends the
  disconnect.
- **Java.** An interrupted stream wait keeps the interrupt flag. The protocol error disconnect
  waits at most the close timeout for the write lock.
- **Server.**
  - The per-update debug line is built only when debug logging is on.
  - M19: the "Sent stream update" line also logged an update that `Connection.Write` dropped.
    The "Sent" lines move from `Core.cs` into `Connection.Write`, built only when debug logging
    is on and logged once `TryWrite` succeeds. The dead "Failed to send" catches in `Core.cs` are
    removed, as `Connection.TryWrite` catches and logs a failed write.
  - The `Core` fields that need it get label comments.
- **Docs and changelogs.**
  - The missing numbers are added.
  - The C# stubs entry is verb-first.
  - The Python timeout entry is marked Breaking.
  - `PROTOCOL_ERROR` names abandoned ids.
  - The text on closing and on request ids matches the server.
  - M22: `getting-started.rst` reads "A connection fails after the client's handshake timeout,
    5 seconds by default, so connect with no handshake timeout to leave time to answer."
  - M23: the server settings entry is "**Breaking:** Reset each existing server's settings to
    their defaults, so a TCP/IP and a WebSockets server both use port 50000 until one is changed".
    The key rename goes in the PR text.
  - M24: the core changelog gains "Accept the stream RPCs over serial IO, which returned an error,
    with no flow control for their updates".
  - M25: the C-nano changelog splits protocol version 2 from the removal of
    `KRPC_SINGLE_CONNECTION`, with the Breaking entries first.
  - M26: the client guides say "The connection fails after 5 seconds by default". The
    `messages.rst` and `serialio.rst` phrases are gone at the stack tip.
  - M27: the `TIMEOUT` row of the handshake table is one sentence at the stack tip.
  - M28: the guide notes, `client-spec/calls.rst` and `cnano/client.rst` are reflowed. The long
    `messages.rst` and `localsocket.rst` lines are gone at the stack tip.
- **C++ testee.** Each command holds its client, so a close with a call in flight waits for the
  call. `test_close_with_a_call_in_flight` and `test_response_after_close` are expected failures
  for C++.
- **C-nano testee.** It closes after a failed connect only over a serial port.
- **D1 test.** `test_wait_holding_another` covers D1, and is listed with the new `@skip` flag in
  C++, C#, Java and Python, where it hangs. The fix itself is still open (D1 below).
- **D2 test.** `test_held_stream_ending_before_value` covers D2, and is an expected failure in
  C++, C#, Java and Python. The fix itself is still open (D2 below).

## Design questions

### D1. A held stream condition blocks the dispatcher queue

Clients: Python, C#, and by the same design Java and C++.

**Status.** The conformance test is added and skipped. The fix is open. A trial fix in Python
passed the whole suite: the dispatcher tries the condition without blocking, and a waker thread
announces the latest value once the holder lets go.

The dispatcher announces each value with the stream's condition held. When another thread holds
that condition, it spins until it gets it, and gives up only once a close is requested:

- C#: `StreamManager.cs:248-255` (`EnterCondition`) and `:392` (`Apply`), which runs
  `while (!Monitor.TryEnter (condition, 50)) { if (closeRequested) return false; }`
- Python: `_apply` and `_lock` in `streammanager.py`

One held condition stalls the whole queue. Every stream's updates and every callback wait.

**Failure.** Thread T holds A's condition and waits on stream B. That is
`lock (a.Condition) { lock (b.Condition) { b.Wait (); } }`, or `b.Get ()` before B's first value
while holding A. An update for A is queued ahead of B's update, so the dispatcher spins on A for
good. B is never announced, and T hangs or times out.

**Spec.** `test_wake_waiter_holding_another` treats waiting on one stream while holding another's
condition as supported. It checks only the close and failure cases. The `NotifyClosed` remark
names the same pattern.

**Option.** When the condition is held, hand that stream's announce to a waker, as `NotifyClosed`
does, or requeue it, so the queue keeps moving. Per-stream ordering must survive this.

### D2. `get()` on a held condition before the first value raises the wrong error

Clients: Python, C#, Java, C++.

**Status.** The conformance test is added as an expected failure. Each of the four clients raises
"Stream has no value". The fix is open.

The wait loop exits on the stored ending, but `ThrowIfEnded` and `raise_if_ended` raise only an
announced ending for the holder.

- Python: `stream.py:68-70`. `while not stream.updated and not stream.ended:` then
  `return stream.value`.
- C#: `Stream.cs` `Get`, with `StreamImpl.cs:95-103` and `:112-116`.

**Failure.** T holds S's condition, and S has no value yet. The server ends S, so the reader
stores the ending, but the dispatcher cannot announce it while T holds the condition. T calls
`get()` and gets "Stream has no value" (`InvalidOperationException` in C#), not the server's
error.

**Spec.** `test_held_stream_ending` says the error "reaches it as a value does", so `get()` should
block until the ending is announced and then raise it. No test covers it without an earlier
value.

**Option.** When the condition is held, loop on the announced ending:
`!Updated && !(holder ? EndingAnnounced : Ended)`. This interacts with D1: with the dispatcher
spinning on the held condition, the ending is never announced.

### D3. WebSockets: the server reads no disconnect or close frame while a call is in flight

Files: `core/src/Core.cs:872`, `core/src/Server/Message/Connection.cs:384-397`.

`PollRequests` skips a client that has a continuation. `ReadAhead` buffers the bytes but decodes
none of them.

**Failure.** A WebSockets client starts a yielding call, then closes from another thread. It
sends a `disconnect` and a close frame, then waits for the server's close frame. The TCP peer
stays open, so the server sees nothing and its continuation keeps running. The client gives up
after 1 s and drops TCP, and only then does the server notice.

Over TCP/IP the half-close gives EOF, and `Disconnected()` finds the buffered disconnect. The
`ReadAhead` comment covers only that case.

**Spec.** `test_websockets_close` and `test_close_wait_limit` with
`test_close_with_a_call_in_flight`. The server's close then arrives a second late. No test covers
it directly.

**Option.** During a session, have `ReadAhead` scan the buffer for a `disconnect` or a close frame,
as `BufferedDisconnect` does.

### D4. WebSockets framing errors end the session with no `disconnect`

File: `core/src/Server/WebSockets/Connection.cs:188-272` (`throw Fail (...)`).

These end a session with only the close frame:

- a text frame;
- RSV bits;
- out-of-order fragments;
- invalid UTF-8;
- an over-large message.

The client receives no `disconnect` with `MALFORMED_MESSAGE` or `PROTOCOL_ERROR`. During the
handshake there is no `connection_response` with status `MALFORMED_MESSAGE` either.

`Fail` writes the close frame first and sets `closeSent`, so a later `Write` drops the message.

**Spec.** In `messages.rst`, "either side ends a connection by sending a `disconnect`" and the
`MALFORMED_MESSAGE` row. No test covers it.

**Option.** Have `Fail` record the reason, and have `Connection` write the `disconnect` or the
`connection_response` before the close frame.

### D5. Java and C++: a zero handshake or stall timeout means wait forever

This was raised in an earlier round and left as an expected failure. It is listed here because it
is a behavior to settle before 0.8 ships. The other clients reject zero.

## Minor findings

These are narrow races, latency effects, edge cases and nits. Each has a one-line fix unless
noted.

### Python

- **M1. A write that fails during `close()` cuts the drain short.**
  - Where: `session.py:300-306` and `:343`.
  - A caller that blocks on the write lock before the close writes after the half-close. It gets
    EPIPE and calls `_end(None)`, which sets `_ended`. The close then skips its drain and can turn
    unread data into an RST.
  - Fix: when `_failure` returns None (closing), leave the slot failed and do not call `_end`.
    Java has the same shape (M5).
- **M2. `stream.remove()` during a close or failure re-ends the stream as removed, and raises.**
  - Where: `streammanager.py:556-572`.
  - Later reads raise the removed error, not the connection error. This goes against
    `test_read_after_close`.
  - Fix: return early when a close is requested or the session has failed. Or swallow the
    `ConnectionError` from `RemoveStream`.
- **M3. Dead code.** These have no use outside native tests that a later branch deletes:
  - the `_run_inline` default for `StreamManager(dispatch=...)`;
  - the `Session.reader` and `.dispatcher` properties.

  `Connection.receive` and `partial_receive` are removed at the stack tip.

### C#

- **M4. Only `ThreadInterruptedException` abandons a call's slot.**
  - Where: `Session.cs:224-232`.
  - Another exception from `WriteRequest` leaves the slot pending, such as one from
    `CalculateSize`/`WriteTo`, or `OutOfMemory`. A partial write also corrupts the framing.
  - Fix: catch every exception, as Python does.
- **M5. A failed TCP connect leaks the socket.**
  - Where: `Connection.cs:123-137`. This predates the branch.
  - Only the timeout path closes the socket. `ConnectToPath` was fixed on this branch, but the TCP
    path was not.
  - Fix: `try { ... } catch { socket.Close (); throw; }`.
- **M6. Dead code.** The test-only `StreamManager.Update (ulong, ProcedureResult)` at `:376-382` has
  no callers once the native tests go.

### Java

- **M7. A request written after the close's disconnect cuts the drain short.**
  - Where: `Session.java:170-191`, `344-363` and `553-574`.
  - Same shape as M1. The caller gets `ClosedChannelException` and calls `end`, which closes the
    channel before the server does.
  - Fix: skip the write when `closing` or `error != null`, under the write lock.
- **M8. The reader thread can take the role after a caller has consumed the data.**
  - Where: `Session.java:598-621`.
  - `readable` is computed before the role is taken. The reader thread then blocks in `receive()`
    holding the role, and the next call pays a thread hand-off. Latency only.
  - Fix: after taking the role, read only if `reader.hasBuffered()` or `selectNow()` > 0, as C#
    and Python do.
- **M9. The idle stall wait is capped at 1 s, not at the stall time left.**
  - Where: `Session.java:600-601` and `:617`.
  - A partial message times out up to about 1 s late. `test_stall_while_idle` passes regardless.
  - Fix: when buffered, select for `min(1000, stall remaining)`.
- **M10. An interrupted call raises an exception whose cause is a `ConnectionException`, on a
  healthy connection.**
  - Where: `Session.java:197-203`, `Connection.java:589-590`.
  - Fix: use a plain `InterruptedIOException`.
- **M11. A huge `Duration` overflows `toNanos()`.**
  - Where: `MessageReader.java:58` and `:86`, `Connection.java:407-414`.
  - `ChronoUnit.FOREVER.getDuration()` as a stall timeout fails the first call with
    `ArithmeticException`. As a handshake timeout it escapes `newInstance` unwrapped.
  - Fix: treat 292 years or more as no timeout.
- **M12. `holdsCondition` scans a weak set of `StreamImpl`s.**
  - Where: `StreamManager.java:38-39` and `:67-76`.
  - This is contrived. A thread keeps only the condition object, the `StreamImpl` is
    garbage-collected, and the thread then closes inside `synchronized (c)` while a callback waits
    for `c`. That deadlocks on the join.
  - Fix: keep the conditions themselves in the weak set.

### C++

- **M13. `Client::wait_for_stream_update` has undefined behavior on some timeouts.**
  - Where: `client.cpp:331`. This predates the branch.
  - `static_cast<int>(timeout * 1000)` is undefined for NaN, infinity or more than about
    2.1e6 s.
  - Fix: validate and clamp the timeout, as `StreamImpl::wait` does.
- **M14. Dead code and a misleading comment.**
  - `StreamManager::update_and_wait` and `is_registered` are used only by native tests.
  - The `drop_stream` comment at `stream_manager.cpp:168` says a live entry is another stream
    given the same id. The server never reuses an id. The live-entry case is an id decoded again.

### C-nano

- **M15. Resumable connect returns the "retry" error for permanent failures.**
  - Where: `krpc.c:133-136` and `:168-172`.
  - A receive IO or EOF error, and an undefined status, both return `CONNECTION_FAILED` "...,
    retry". A program following the header loops forever on an unplugged adapter.
  - Spec: `test_serialio_no_answer` names only a disconnect, `MALFORMED_MESSAGE` and `TIMEOUT`
    as no answer.
  - Fix: return the transport's error, refuse an unknown status, and keep "retry" for the
    no-answer cases.
- **M16. An EOF partway through a message reports "failed to parse".**
  - Where: `krpc.c` `read_callback`.
  - `pb_decode` turns a transport error into `DECODING_FAILED`. A `MALFORMED_MESSAGE` disconnect
    is then sent on a dead line.
  - Fix: record transport errors apart from parse failures.

### Lua and C-nano

- **M17. A `stream_update` fails the session as a protocol error.**
  - Where: `client.lua:116-119`, and the `default:` arm in `krpc_invoke`.
  - Neither client has streams, but both expose `KRPC.AddStream`. Before this branch, a stream RPC
    with no stream connection raised `InvalidOperationException`. Now the call succeeds and the
    first update ends the session.
  - Fix: skip `stream_update` in these clients, or document `AddStream` as unsupported there.

### Server

- **M18. A stall is only detected once an in-flight call finishes.**
  - Where: `Connection.cs:572` and `Core.cs:872`.
  - A request that stalls partway while another call yields gets its `TIMEOUT` only once the
    yielding call completes. The timeout then fires at once.
  - Fix: run the stall check in `ReadAhead` during a session.
- **M29. WebSockets: a dropped frame counts as written.**
  - Where: `WebSockets/Connection.cs:80`, the `!upgraded || closeSent` return.
  - `Write` drops a frame before the upgrade and after a close frame is sent, and returns
    normally. `TryWrite` then reports the message as written, so a "Sent" debug line would log
    it.
  - No session is current at either point, so `Connection.Write` returns false first. Follow
    up: make `Write (IMessage)` report a dropped frame, so the result holds for every protocol.

### Harnesses and testees

- **M20. Serial harness: request ids restart at 1 in every test on one shared session.**
  - Where: `client/serialio/krpcserialio/test_serialio.py:56` and `:139`.
  - `self.next_id += 1` creates an attribute on each test instance, so the resets in
    `test_reconnect`, `test_queued_handshake_retries` and `resume()` do nothing. The tests pass
    only because the server does not check ids. The WebSockets harness has the same pattern.
  - Fix: `type(self).next_id`, or reconnect per test.
- **M21. WebSockets testee: an empty binary frame reads as the server closing.**
  - Where: `client/websockets/conformance/testee.py:251`, added with the conformance infrastructure.
  - `if not data: return None` comes before the `str` check. websocket-client returns `''` for a
    close frame but `b''` for an empty binary frame. So `test_handshake_unexpected_message[empty]`
    passes for the wrong reason.
  - Fix: return None only for `data == ""`.
