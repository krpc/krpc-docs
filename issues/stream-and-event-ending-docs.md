# Document how streams and events end, in each client guide

The client spec now settles what a stream or event delivers around its end. The client guides say
only what error an ended stream raises. Each guide should state the rules below in its own terms.

The rules split by who ends the stream or event:

| Ending | Value or firing the program has not seen | Later reads and waits |
|---|---|---|
| The server ends it, with an error or a `StreamRemovedException` | Delivered first: a wait returns for it, and a callback added later is called for an unseen firing | Raise the error that ended it |
| The client removes it | Discarded | Raise the error for a removed stream, at once |
| The client closes the connection | Discarded | Raise the connection error, at once |

Three related rules:

- **Holding the condition.** A thread holding a stream's condition sees an ending the same way it
  sees a new value. It reads the old value until it waits. The wait returns, and later reads and
  waits raise the error.
- **An ending outlives a close.** A stream that ended with an error before the connection closed
  keeps raising that error, not the connection error.
- **Callbacks.** When the server ends a stream, each callback is called with every value sent
  before the ending, in order, and the end callbacks are called after the last of them. Once the
  client removes the stream or closes the connection, no value callback is called.

The conformance tests that specify these:

- `test_events.py`: `test_ended_by_the_server`, `test_remove`,
  `test_callback_added_after_an_unseen_firing_is_called[ended]`
- `test_threading.py`: `test_remove_while_holding_the_condition`,
  `test_remove_event_while_holding_the_condition`, `test_a_held_stream_ends_on_a_wait`
- `test_streams.py`: `test_read_after_close`,
  `test_a_callback_is_not_called_once_its_stream_is_removed`,
  `test_a_value_queued_during_a_first_call_is_passed_before_a_server_ending`,
  `test_a_value_queued_during_a_first_call_is_dropped_by_a_remove`

Current state of the guides (`doc/src/<client>/client.rst`):

| Guide | State |
|---|---|
| Python, C++, C#, Java | A "Stream Endings" section lists the errors. It needs the table above, and the Events section needs the unseen firing rules. |
| Lua, C-nano | No section on endings. |

Several clients do not follow these rules yet, and list the tests above as expected failures. The
docs should describe the specified behavior, so this lands with or after the client fixes.
