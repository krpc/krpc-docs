# Websockets testee: defects found writing the design doc

Writing the client's design doc turned up these defects. Paths are relative to `client/websockets/`, and known conformance failures are in `conformance/expected-failures.txt`.

* The docstring of `conformance/testee.py` says an `UNSUPPORTED` reply skips the test. The driver fails such a test unless the client lists it in `unsupported.txt`, as in `client/conformance/driver/testee.py`. This target has no such file, and lists these tests as expected failures.
* `Connection.__init__` shuts the socket down when the handshake fails. An RPC error from the `GetServices` call after the handshake leaves the socket open, and the testee keeps the previous closed `Connection`.
* `test_null_result_with_a_value` fails because `Connection.invoke` reads a result with `is_null` set as null before it looks at the value. This expected failure is a behavior of the testee, where the other entries are gaps in its scope.
