# Conformance driver: wait on signals, not timers

Three changes to the driver in `client/conformance/driver/`, each mergeable on its own.

## Wake waits on the testee's notifications

`wait_until` in `testee.py` polls its condition every 10 ms until it holds or `REPLY_TIMEOUT` elapses.
About 50 calls use it, in `test_streams.py`, `test_concurrency.py`, `test_functions.py`,
`test_events.py`, `test_calls.py` and the driver's `update_barrier`. Nearly every condition reads
state that changes only when a testee notification arrives, such as a callback's `calls` or a stream's
value.

* Signal a condition variable in the `Client` each time it handles a notification.
* Have `wait_until` wait on it, with the same deadline, and check the condition on each wake.
* Keep the poll for a condition that reads the control connection, which sends no notification.

## Wait for the serial link instead of a fixed second

Before a serial IO test connects, `plugin.py` sleeps `SERIAL_SETTLE_TIME`, one second, after the
TestServer starts. The sleep makes the serial tests pass. Which step the link waits on is unverified:
socat creating the pty pair, the server opening its end, or the server reading from it.

* Find the step, and wait on its signal: a server log line, or the pty accepting a probe.
* Remove `SERIAL_SETTLE_TIME`. Each serial target then starts a second sooner per server.

The serial in-game protocol tests may need the same wait
([ingame-protocol-tests.md](ingame-protocol-tests.md)).

## A callback that runs a command on itself

`test_concurrency.py::test_remove_callback_from_itself` builds its `Callback` by hand and sends
`AddCallback` itself. The callback's behavior is a command naming the callback's own id, and
`Stream.add_callback` assigns the id only as it sends the add.

* Let `Stream.add_callback` take the behavior as a function of the new callback's id.
* Use it in the test, and drop the hand-built `Callback`.
