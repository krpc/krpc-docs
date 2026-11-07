# Fail a call with an invalid argument position

The server silently drops an argument whose position is past the procedure's last parameter. The
call then runs without it, and a parameter with a default takes the default. For example, a client
with a stale signature that passes an argument at position 2 of a two-parameter procedure gets a
successful call, with no sign of the lost value. Of two arguments at one position, the last replaces
the first.

`ProcedureCall.ToMessage` in `MessageExtensions.cs` skips these arguments, with the comment "Ignore
the argument if its position is not valid". The comment gives no reason. Server side functions
already reject the same mistake: `Expression.cs` throws `ArgumentException` with "Argument position
N out of range".

## Proposal

`ProcedureCall.ToMessage` throws `ArgumentException` for a position past the last parameter, with
the message `Expression.cs` uses, and for a duplicate position. The call fails with that error in
its own result, and the other calls in the request still run.

This is a **Breaking:** change for a client that sends these arguments and gets a successful call
today.

## Client and server mismatch

The C++, C#, C-nano and Java stubs always send every parameter. Against an older server that lacks
an appended parameter, every call to that RPC now fails, even with the default.

**Ruling:** a call with a changed signature should fail, as a signature change could also change
what the call means. A client and server mismatch is never guaranteed to work.

An old stub that leaves out a parameter appended with a default still succeeds with the default.
This case stays undetected: see the negative results in the [release plan](../RELEASE_PLAN.md).

## Tests

* `core/test`: a position past the last parameter or a duplicate position fails the call, and the
  other calls in the request run.
* `client/conformance`: tests that send these positions to the real server with `raw.request`.

`test_too_many_arguments` stays as it is. Its Lua expected failure also stays, as a generated Lua
function discards extra arguments before the client encodes the request.
