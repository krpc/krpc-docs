# Make `KRPC.RemoveStream` and `SetStreamRate` take a `Stream`

`KRPC.AddStream` returns a `Stream` message, but `KRPC.RemoveStream` and `KRPC.SetStreamRate` take the bare `ulong` id. A FIXME on `RemoveStream` in `core/src/Service/KRPC/KRPC.cs` asks for the parameter to be a `Stream`.

The change breaks every client's encoding of these calls, including the C++ and Python code that tracks removals. Users do not see it, since each client wraps the call as `stream.remove ()`. It changes the `KRPC` service, so it ships in a release that already breaks the protocol, such as 0.8.
