# Conformance: wait for the serial link instead of a fixed second

Before a serial IO test connects, the driver sleeps `SERIAL_SETTLE_TIME`, one second, after the
TestServer starts (`client/conformance/driver/plugin.py`). The sleep makes the serial tests pass.
Which step the link waits on is unverified: socat creating the pty pair, the server opening its
end, or the server reading from it.

* Find the step, and wait on its signal: a server log line, or the pty accepting a probe.
* Remove `SERIAL_SETTLE_TIME`.
* Each serial target then starts a second sooner per server.
