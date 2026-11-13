# Java: defects found writing the design doc

Writing the client's design doc turned up these defects. Paths are relative to `client/java/`, and known conformance failures are in `conformance/expected-failures.txt`.

* `doc/src/java.rst` disagrees with the code. It says a handshake or stall timeout of zero throws `IllegalArgumentException`, and `Connection.checkTimeouts` accepts zero. It says `getObjectId(null)` throws `IllegalArgumentException`, and the code throws `NullPointerException`. It says objects order as unsigned, and `RemoteObject.compareTo` compares signed.
* `doc/src/java.rst` says `StreamException` is thrown when a stream cannot be created, and no code path does that.
* `MessageReader.read` and `Connection.handshake`: a `Duration` past about 292 years overflows `toNanos`. A handshake timeout throws `ArithmeticException` from `newInstance`. A stall timeout fails the connection on its first call. Confirmed by running.
* `Session.call`: an interrupted call throws `RPCException` caused by `ConnectionException` on a healthy connection, the same shape as a dead connection. Confirmed by running.
* `Session.writeRequest` has no check for a close in progress. A request that races the close's half-close fails, and `end` closes the channel, which cuts the close's drain short. Read from code.
* `RemoteObject` is `Serializable` with a transient `connection`. A deserialized object equals the original, and its calls throw `NullPointerException`. Confirmed by running.
* `Stream.hashCode` and `Event.hashCode` hash the `StreamImpl` identity, while `equals` and `compareTo` compare ids. Streams with one id on connections to two servers are equal with different hashes, and collapse in a `TreeMap`. Confirmed by running against a stand-in server.
* `Encoder` uses `Class.forName(String)`, which resolves through the client jar's class loader, and `Connection.stubsLoader` is package-private and used only for return types. Stubs in a child class loader fail to decode objects, enumerations and structures. Read from code.
* Generated `fromValue` returns `null` for an undeclared value, so `Encoder.decode` gives `null` in a position that cannot hold one. The reason given for `test_undeclared_enum_result`, "holds any number", does not match. Confirmed by running.
* `StreamManager.registered` is weak on `StreamImpl`. A thread that keeps only the condition of a removed stream, whose handle is collected, deadlocks in `close()` if a callback waits for that condition. Read from code.
* `StreamManager` names its waker threads `kRPC stream waker`. Python and C# name theirs `krpc-waker`, and the other Java threads are `krpc-reader` and `krpc-dispatcher`. Rename it to `krpc-waker`, and update `doc/src/client-design/java.rst`. Read from code.

## From the parity audit and the client guide rewrite

Still open from the client API parity audit (2026-07-21) and the client guide rewrite (2026-10-29), re-checked against `main` on 2026-11-09.

* **The connection error is wrapped or replaced.** The fix needs an exception design first: calls declare only the checked `RPCException`, and `ConnectionException` is an `IOException`. The guide says nothing about the connection closing until then.
  - A call after a close, an unknown response id or a malformed size raises `RPCException`, with the `ConnectionException` as its cause (`test_call_after_end[close]`, `test_unknown_id`, `test_malformed_size`).
  - A stream or event ended by a close or a connection failure ends with `StreamException("Connection closed")`, without the reason (`test_end_callback[connection-failure]`, `test_wake_waiter[close]`).
* **A server that closes the socket during the handshake makes `newInstance` throw a bare `EOFException`**, not `ConnectionException` (`test_handshake_lost`). `handshake` catches only timeouts and parse errors.
* **A stream added before any call through its service raises an untyped `RPCException`** for the service's exception, as the types are registered when a service object is made (`test_procedure_exception[first-CustomException]`).
