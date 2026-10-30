# Conformance: a race point for a value queued during a first call

`test_streams.py::test_queued_value_dropped_by_remove` checks that removing a stream drops a value
queued for its callback while a first call runs. It sleeps `SETTLE` twice:

1. After the new value is read, so the update thread has queued it for the adding thread.
2. After the remove starts, so the remove waits on the first call.

Neither step is observable, so each sleep is a guess, and the test can pass without forcing the
order it checks.

* Add race points at the two steps, in the clients with the `races` profile: the update thread
  with the value queued, and the removing thread waiting on the first call.
* Move the test to the `races` profile, and replace the sleeps with `AwaitPause` and `Resume`.

Related: [conformance-forced-races.md](conformance-forced-races.md), which adds race points to C#
and Python.
