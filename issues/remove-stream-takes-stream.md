# Make `KRPC.RemoveStream` and `SetStreamRate` take a `Stream`

Milestone: 0.8.0 · Labels: enhancement, protocol, server

`KRPC.AddStream` returns a `Stream` message, but `KRPC.RemoveStream` and `KRPC.SetStreamRate` take the bare `ulong` id. A FIXME on `RemoveStream` in `core/src/Service/KRPC/KRPC.cs` asks for the parameter to be a `Stream`.

The change breaks every client's encoding of these calls, including the C++ and Python code that tracks removals. Users do not see it, since each client wraps the call as `stream.remove ()`. Do it with the single connection (#<single-connection>), which already changes every client's connection layer. If that slips, delete the FIXME instead.
