# Streams of calls and functions that return no value

`KRPC.AddStream` rejects a procedure with no return value, with "Cannot create a stream for a procedure that does not return a value". `KRPC.AddFunctionStream` rejects a server side function that evaluates to no value, with "The function does not evaluate to a value". The Python and C# clients reject both before calling the server.

A stream is also a way to run code on the server on every update, at the stream's rate. Having no value does not mean having no effect. A server side function built from `Block`, `Assign` and calls to setters is a control loop that runs in game each tick, with no client round trip. Examples are a throttle limiter or an attitude hold. A plain void call, such as a setter fed from an expression, is the same case. Today the workaround is to return a dummy value, which then gets encoded, compared and sent.

Proposal:

- `AddStream` and `AddFunctionStream` accept a call or function with no value. It runs on each stream update, at `SetStreamRate`'s rate, for its side effects.
- A stream with no value behaves like any other stream. Its first run sends a result with no value, encoded as a call to a procedure with no return value encodes its result. The value never changes, so no further update is sent unless there is an error, which ends the stream.
- `RemoveStream` stops it.
- Events are unchanged, and still need a boolean.
- The clients allow it. The stream's value is `None`, `null` or `void` in each language, and its callbacks still run on the first update and on an error.

The wire protocol needs no change, as a result with no value is already an empty value. The core tests that assert the rejection (`AProcedureWithNoReturnValueCannotBeStreamed` and `AddFunctionStreamWithNoValueIsRejected`) become tests of the new behavior, and the stream docs need updating.
