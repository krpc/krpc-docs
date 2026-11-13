# Conformance: race points in every threaded client, and forced orders in place of sleeps

The conformance suite forces the stream and event races through race points: places in a client where
the testee can pause a thread. The `Pause`, `AwaitPause` and `Resume` testee commands drive them, and
the tests are in the optional `races` profile.

| Client | Race points |
|---|---|
| C++ | Compiled in for its testee only (`KRPC_RACE_POINTS`) |
| Java | A package-private hook the testee sets by reflection. No `UPDATE_CALLBACKS`, as Java has no update callbacks: its testee replies UNSUPPORTED to a `Pause` there |
| C#, Python | None. They claim the profile, their testees reply to `Pause` with an error, and each lists 11 race tests as expected failures, "The client has no race points" |

## 1. C# and Python

For each client:

* Add the race points below, enabled only for the testee.
* Implement `Pause`, `AwaitPause` and `Resume` in the testee.
* Remove the expected failures.

A testee must remove a callback whose add is paused, when the driver asks. The Python testee has the
function before the add. The C++ and Java race points pass the tag of the callback being added.

| Race point | Where the thread pauses | Tests |
|---|---|---|
| `STREAM_CALLBACKS` | The update thread, with a value and a copy of the stream's callbacks, before it calls them | `test_streams.py::test_a_callback_is_not_called_once_its_stream_is_removed`, `test_streams.py::test_a_callback_removed_during_an_update_is_not_called`, `test_events.py::test_a_callback_removed_during_an_update_does_not_take_a_firing` |
| `UPDATE_CALLBACKS` | The update thread, before it calls the update callbacks | `test_concurrency.py::test_update_callbacks_are_not_called_once_closed` |
| `FIRST_CALL` | The adding thread, with the stream's value, before the first call | `test_streams.py::test_a_first_call_is_not_passed_an_older_value` |
| `FIRST_CALL_STARTED` | The adding thread, once the first call keeps the update thread out, before the callback runs | `test_concurrency.py::test_close_while_an_update_waits_for_a_first_call` |
| `STREAM_ENDING` | The update thread, with the ending of a stream stored, before it wakes the stream's waiters and calls its end callbacks | `test_streams.py::test_a_remove_during_an_ending_by_the_server_keeps_its_error` |
| `STREAM_VALUE` | The update thread, with a value of a stream stored, before it wakes the stream's waiters | `test_concurrency.py::test_a_wait_does_not_return_for_a_value_read_before_its_wake` |
| `FIRST_CALL_ENDED` | The adding thread, with the first call made and the values queued during it passed, before it lets the update thread call the callback | `test_streams.py::test_a_value_that_arrives_as_a_first_call_ends_is_passed` |
| `REPLAY` | The thread adding an event callback, with an unseen firing, before the call | `test_events.py::test_a_callback_added_during_a_replay_does_not_replay_the_firing`, `test_events.py::test_a_callback_removed_during_its_add_does_not_take_a_firing` |

## 2. Forced orders in place of guessed sleeps

Several tests sleep `SETTLE` and assume the client has reached a state by then. That state is not
observable, so each sleep is a guess, and on a slow run a test can pass without forcing the order it
checks.

| Test | Sleep | On a slow run |
|---|---|---|
| `test_concurrency.py::test_close_with_a_call_in_flight` | After the call starts, before the close | The close lands before the call is sent, and the test passes on the error of a closed connection |
| `test_streams.py::test_queued_value_dropped_by_remove` | After the new value is read, so the update thread has queued it for the adding thread | The remove can run before the value is queued |
| `test_streams.py::test_queued_value_dropped_by_remove` | After the remove starts, so the remove waits on the first call | The first call can end before the remove waits on it |

Add these race points to C++, Java, C# and Python:

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

## 3. The other sleeps

The tests have about 30 other `SETTLE` sleeps, such as in `test_concurrency.py::test_interrupted_wait`
and `test_close_while_callback_waits`. Some give a wrong wake time to happen, and cannot be replaced by
an event. Go through the rest and convert those that guess an order.
