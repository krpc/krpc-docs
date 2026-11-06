# C++: defects found reviewing the client lifetime change

Reviewing the strong handles and `Client::close`, #1286, turned up this defect, read from code and not run.

* **A concurrent second `close()` returns before the close has finished.** The first caller claims the close, and any other caller returns at once. The first caller drains the socket before it ends the streams, which can take about 2 s. In that time a second thread's `conn.close(); stream();` can read an old value, although the guide says streams end. If a callback made the first call, a `close()` on another thread returns without joining the dispatcher thread, so the callback can still be running.

  Python runs the whole close on each caller, so it does not share this. No conformance test covers concurrent closes, and the spec has no ruling. Either a later caller waits, other than on the dispatcher thread or from a re-entrant call, or the guide states it.
