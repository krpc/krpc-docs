# C++: client defects

Reviewing the strong handles and `Client::close`, #1286, turned up the first defect, read from code and not run. Known conformance failures are in `client/cpp/conformance/expected-failures.txt`.

* **A concurrent second `close()` returns before the close has finished.** The first caller claims the close, and any other caller returns at once. The first caller drains the socket before it ends the streams, which can take about 2 s. In that time a second thread's `conn.close(); stream();` can read an old value, although the guide says streams end. If a callback made the first call, a `close()` on another thread returns without joining the dispatcher thread, so the callback can still be running.

  Python runs the whole close on each caller, so it does not share this. No conformance test covers concurrent closes, and the spec has no ruling. Either a later caller waits, other than on the dispatcher thread or from a re-entrant call, or the guide states it.

## From the parity audit and the client guide rewrite

Still open from the client API parity audit (2026-07-21) and the client guide rewrite (2026-10-29), re-checked against `main` on 2026-11-09.

* **A stream value is decoded when it is read,** so a value that fails to decode raises on each read, and never ends the stream or calls its end callbacks (`test_undecodable_value`).
* **`run` and a function stream throw `std::runtime_error` for a null** without `std::optional`, not the encoding error (`test_null_for_non_nullable_type[double]`). The guide already describes the fixed behavior.
