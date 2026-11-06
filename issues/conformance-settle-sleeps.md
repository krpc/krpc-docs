# Conformance: replace guessed sleeps with forced orders

Several conformance tests sleep `SETTLE` and assume the client has reached a state by then. That
state is not observable, so each sleep is a guess. On a slow run, a test can pass without forcing the
order it checks.

| Test | Sleep | On a slow run |
|---|---|---|
| `test_concurrency.py::test_close_with_a_call_in_flight` | After the call starts, before the close | The close lands before the call is sent, and the test passes on the error of a closed connection |
| `test_streams.py::test_queued_value_dropped_by_remove` | After the new value is read, so the update thread has queued it for the adding thread | The remove can run before the value is queued |
| `test_streams.py::test_queued_value_dropped_by_remove` | After the remove starts, so the remove waits on the first call | The first call can end before the remove waits on it |

## Proposal

Add these race points, in the clients with the `races` profile:

| Race point | Where the thread pauses |
|---|---|
| `CALL_SENT` | The calling thread, with its request written, before it waits for the response |
| To be named | The update thread, with a value queued for the adding thread |
| To be named | The removing thread, waiting on a first call |

Then change the tests:

* Move `test_queued_value_dropped_by_remove` to the `races` profile, and replace its sleeps with
  `AwaitPause` and `Resume`.
* Add a test in the `races` profile that forces a close at `CALL_SENT`. The call raises the connection
  error.
* Replace the sleep in `test_close_with_a_call_in_flight`, which stays in the `concurrency` profile for
  every client. `test_response_after_close` shows the form: a scripted server sets an event when it
  receives the call, and the test waits for that event before the close.

The two close tests fix both orders that can be forced: the close after the server has the call, and
the close before the caller waits. A thread blocked inside its wait cannot report that it got there,
so neither form proves that state. After the server has the call it is the likely state, and the test
no longer passes with no call in flight.

## Other Sleeps

The conformance tests have about 30 other `SETTLE` sleeps, such as in
`test_concurrency.py::test_interrupted_wait` and `test_close_while_callback_waits`. Some give a wrong
wake time to happen, and cannot be replaced by an event. Go through the rest and convert those that
guess an order.

Related: [conformance-forced-races.md](conformance-forced-races.md), which adds race points to C#
and Python.
