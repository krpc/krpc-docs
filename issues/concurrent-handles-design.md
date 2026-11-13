# Conformance Tests for Concurrent Use of Shared Handles

## Problem

The conformance suite checks a client called from several program threads in the following
cases:

 * Calls spread over several threads (`test_concurrent_calls`), responses out of order
   (`test_interleaved_calls`), and pending calls on failure or close.
 * Streams of different calls added concurrently (`test_concurrent_stream_adds`).
 * Several threads waiting on one stream or event, woken by an update, a remove, a close or a
   failure on another thread.
 * One thread holding a stream's condition while others read, wait or remove.
 * One program thread racing the update thread, through the race points in `testee.proto`.

The suite never has two program threads change the same stream or event at once. It also never
mixes request types on several threads. A client can pass every test with an unguarded stream
table or callback list. The threaded clients' design in `doc/src/client-design.rst` has program
threads share one connection, so this is a gap in the spec.

## Scope

The tests go in `client/conformance/tests/test_concurrency.py`. Each carries the `concurrency`
profile, plus `streams`, `events` or `callbacks` as it uses them. A test that forces an
interleaving with a race point also carries `races`. The C++, C#, Java and Python clients run
these profiles. Each new test is a requirement in the generated client spec.

The tests use the existing testee commands: `Command.task` for the thread, `AddStream`, `Remove`,
`Get`, `Wait`, `AddCallback`, `RemoveCallback`, `Close` and `Pause`. No new command goes in
`testee.proto`.

## Requirements

### Same Call Added on Two Threads

Two threads add a stream of the same call at once:

```python
adds = [connected.start("adder%d" % i, add_stream=pb.AddStream(invoke=value(x)))
        for i in range(2)]
first, second = (Stream(connected, add.reply().stream) for add in adds)
```

Each add makes its own stream with its own lifetime, as `test_add_twice` requires for one
thread. Removing one leaves the other updating. Repeating the add over several pairs makes a
lost table entry likely to show.

### Concurrent Removes

Two threads remove the same stream, one through the handle and one through a copy. Both removes
return, and a read of either handle raises the removed error. A second case races a remove
against a `Get` on another thread. The `Get` returns the last value or raises the removed error,
and never a different error.

A stream added afterwards runs on, as `test_remove_twice` checks for one thread.

### Callbacks Changed on Several Threads

Several threads add and remove callbacks on one stream while the server updates it. Each callback
still attached at the end is called with the latest value. A callback removed before an update
is never called for that update.

The `STREAM_CALLBACKS` race point holds the update thread with its callback list while the other
threads change the list. This turns a likely race into a certain one. The same test runs for an
event with the `REPLAY` point.

### Mixed Requests

Several threads send invokes, stream adds and stream removes at once. Each invoke returns its own
result, each add a working stream, and each remove succeeds. This extends `test_unique_ids` and
`test_match_by_id` from invokes to every request a client sends.

### Close With an Add in Flight

A close returns while a stream add waits for its reply, as `test_close_with_a_call_in_flight`
requires for an invoke. The add raises the connection error. It never leaves a stream that
updates or holds a callback after the close. The scripted server holds the `AddStream` reply to
force the order.

### Load

Several threads read, wait on and add callbacks to several streams while the server updates
them. Every read returns a value the stream had, and every wait returns. The test runs for a
fixed time and carries `races`, since it finds data races by chance. A client with a race
detector, such as the C++ client under ThreadSanitizer, gets the most from it.

## Order of Work

1. Same call added on two threads, concurrent removes and mixed requests. These need only
   `start` and the existing commands, and cover the most likely bugs.
2. Callbacks changed on several threads, using the existing race points.
3. Close with an add in flight, on the scripted server.
4. The load test, last, as it is the slowest and the one most likely to need `@flaky`.

A client that fails a test lists it in its `expected-failures.txt` with the reason, and a
follow-up fixes the client.

## Docs

The spec pages come from the tests' docstrings. The threads section of
`doc/src/client-design.rst` is checked against the new requirements. A client that departs from
them records that on its design page.
