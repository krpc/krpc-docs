# Race points for the C# and Python clients

The conformance suite forces the stream and event races through race points: places in a client where
the testee can pause a thread. The `Pause`, `AwaitPause` and `Resume` testee commands drive them, and
the tests are in the optional `races` profile.

The C++ and Java clients have the race points. C++ compiles them in only for its testee
(`KRPC_RACE_POINTS`), and the Java testee sets a package-private hook by reflection. C# and Python claim
the profile, but their testees reply to `Pause` with an error. Each lists the race tests as expected
failures, "The client has no race points".

| Race point | Where the thread pauses | Tests |
|---|---|---|
| `STREAM_CALLBACKS` | The update thread, with a value and a copy of the stream's callbacks, before it calls them | `test_streams.py::test_a_callback_is_not_called_once_its_stream_is_removed`, `test_streams.py::test_a_callback_removed_during_an_update_is_not_called`, `test_events.py::test_a_callback_removed_during_an_update_does_not_take_a_firing` |
| `UPDATE_CALLBACKS` | The update thread, before it calls the update callbacks | `test_threading.py::test_update_callbacks_are_not_called_once_closed` |
| `FIRST_CALL` | The adding thread, with the stream's value, before the first call | `test_streams.py::test_a_first_call_is_not_passed_an_older_value` |
| `FIRST_CALL_STARTED` | The adding thread, once the first call keeps the update thread out, before the callback runs | `test_threading.py::test_close_while_an_update_waits_for_a_first_call` |
| `STREAM_ENDING` | The update thread, with the ending of a stream stored, before it wakes the stream's waiters and calls its end callbacks | `test_streams.py::test_a_remove_during_an_ending_by_the_server_keeps_its_error` |
| `STREAM_VALUE` | The update thread, with a value of a stream stored, before it wakes the stream's waiters | `test_threading.py::test_a_wait_does_not_return_for_a_value_read_before_its_wake` |
| `FIRST_CALL_ENDED` | The adding thread, with the first call made and the values queued during it passed, before it lets the update thread call the callback | `test_streams.py::test_a_value_that_arrives_as_a_first_call_ends_is_passed` |
| `REPLAY` | The thread adding an event callback, with an unseen firing, before the call | `test_events.py::test_a_callback_added_during_a_replay_does_not_replay_the_firing`, `test_events.py::test_a_callback_removed_during_its_add_does_not_take_a_firing` |

## Proposal

For each of C# and Python:

- Add the race points, enabled only for the testee.
- Implement the three commands in the testee.
- Remove the expected failures.

A testee must remove a callback whose add is paused, when the driver asks. The Python testee has the
function before the add. The C++ and Java race points pass the tag of the callback being added.

Java has no update callbacks, so it has no `UPDATE_CALLBACKS` point. Its testee replies UNSUPPORTED to
a `Pause` there.
