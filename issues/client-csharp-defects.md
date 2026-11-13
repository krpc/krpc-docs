# C#: defects found writing the design doc

Writing the client's design doc turned up these defects. Paths are relative to `client/csharp/`, and known conformance failures are in `conformance/expected-failures.txt`.

* `doc/src/csharp.rst` says a call after a close throws `ConnectionException`. `Connection.CheckDisposed` throws `ObjectDisposedException`, while `Stream.Get` on the same closed connection throws `ConnectionException`. See `test_call_after_end[close]`.
* `Stream.WaitForFirstUpdate` waits with no timeout, and only the dispatcher thread pulses it. A callback that adds a stream and calls `Get` hangs until another thread calls `Dispose`. After a connection failure it hangs for good, as `NotifyClosed` queues behind the callback. The guide warns against waiting in a callback, but does not name `Get`.
* Only a `Service` constructor registers exception types. On a connection with no service object, `Connection.GetException` turns a service's exception into a plain `RPCException`. Read from code: a generated static method and a stream of another connection's object both reach this case. Suggested fix, not prototyped: replace the per-connection registry with a lookup of `KRPC.Client.Services.<service>.<name>` in the loaded assemblies, cached per process, and fall back to `RPCException` when the type is not found. This removes `AddExceptionType` from the public `IConnection`, a breaking change. The table of `System` exceptions in `GetException` stays.
* `Encoder` decodes an event by casting its `IConnection` to `Connection`. On any other implementation of the public interface, a procedure returning an event throws `InvalidCastException`. `Connection` is the only implementation in the repo, and an `Event` needs its stream manager, so this is low priority. Read from code.

## From the parity audit and the client guide rewrite

Still open from the client API parity audit (2026-07-21) and the client guide rewrite (2026-10-29), re-checked against `main` on 2026-11-09.

* **`GetException` gives `ArgumentNullException` and `ArgumentOutOfRangeException` an empty parameter name** (`new ArgumentNullException (string.Empty, message)` in `Connection.cs`).
* **An interrupt does not reach a call reading the socket for its own response** (`test_abandoned_id`).
* **A type mismatch or a null raises `InvalidOperationException`, not the argument or encoding error.** `Run` and `AddStream` with a `TResult` that cannot hold the value (`test_mismatched_type[...]`), and a stream of a null for a value type (`test_stream_null_for_non_nullable_type[double]`). The guide already describes the fixed behavior.
* **The address is an `IPAddress`,** so the program resolves a host name itself (`test_unknown_host`). The guide leaves host names out until the API exists.

## From the client errors review

Found reviewing the `client-errors` branch (2026-11-11). It predates the branch.

* **The testee reports any other exception as a server error.** `ToError` in `conformance/Testee.cs` falls through to `Server` for an exception that is not one of the client's error types, an `ArgumentException` or a `ThreadInterruptedException`. A leaked `NullReferenceException` or `InvalidOperationException`, or a `CompilationException`, would pass a test that expects a server error.
