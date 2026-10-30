# Conformance: wake waits on the testee's notifications

`wait_until` in `client/conformance/driver/testee.py` polls its condition every 10 ms until it
holds or `REPLY_TIMEOUT` elapses. About 50 calls use it, in `test_streams.py`, `test_threading.py`,
`test_functions.py`, `test_events.py`, `test_calls.py` and the driver's `update_barrier`.

Nearly every condition reads state that changes only when a testee notification arrives, such as a
callback's `calls` or a stream's value.

* Signal a condition variable in the `Client` each time it handles a notification.
* Have `wait_until` wait on it, with the same deadline, and check the condition on each wake.
* Keep the poll for a condition that reads the control connection, which sends no notification.
