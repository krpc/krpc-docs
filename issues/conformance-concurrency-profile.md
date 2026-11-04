# Conformance: rename the `threads` profile to `concurrency`

The `threads` profile covers "concurrent calls, and callbacks and closes from other threads". Most
of its 40 tests check overlapping operations, and threads are one way to get them:

* Request ids, and responses matched in any order.
* A close while a call waits, and a response after the disconnect.
* Two waiters on one stream, and callbacks added or removed during delivery.

A client built on async tasks raises each case with no second thread: the planned JavaScript client
and Python's asyncio layer. Name the profile and its tests for what they test.

* Rename the profile to `concurrency`, described as "Concurrent calls, waits and callbacks, on
  threads or async tasks". Update the test markers, the `profiles` of the cpp, csharp, java and
  python `conformance_test` targets, and the profile table in `doc/src/client-spec.rst`.
* Rename `test_threading.py` to `test_concurrency.py`, and the spec page `threading.rst` to
  `concurrency.rst`. The requirement ids change from `threading-` to `concurrency-`, so update the
  references to them in the docs and the client guides.
* Rename the testee protocol's `thread` field to `task`, in `Command`, `Reply`, `Notification` and
  `Interrupt`. A task is a thread in a threaded testee and an async task chain in an async one.
  Update the driver (`testee.py`, `scripted.py`) and the cpp, csharp, java and python testees.
* A test that needs a real thread stays in the profile, and an async client lists it in
  `unsupported.txt`: `test_close_interrupted`, `test_blocked_callback`,
  `test_callbacks_run_off_the_caller`.
