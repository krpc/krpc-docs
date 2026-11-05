# Fail a call with an argument position past the last parameter

The server silently drops an argument whose position is past the procedure's last parameter. The
call then runs without it, and a parameter with a default takes the default. For example, a client
with a stale signature that passes an argument at position 2 of a two-parameter procedure gets a
successful call, with no sign of the lost value.

`ProcedureCall.ToMessage` in `MessageExtensions.cs` skips these arguments, with the comment "Ignore
the argument if its position is not valid". The comment gives no reason. Server side functions
already reject the same mistake: `Expression.cs` throws `ArgumentException` with "Argument position
N out of range".

## Proposal

`ProcedureCall.ToMessage` throws `ArgumentException`, with the message `Expression.cs` uses. The call
fails with that error in its own result, and the other calls in the request still run.

This is a **Breaking:** change for a client that sends these arguments and gets a successful call
today.

Two arguments at one position are out of scope. `Services.SetArguments` takes the last.

## To check first

Whether any client relies on the drop. A generated client built against a newer service may send an
argument for a parameter that an older server lacks. If it always sends defaulted parameters, the
drop is what lets it call that server, and the error would break it. No documented rule says
parameters are only appended, unlike structure fields, so this may never have been reliable.

## Tests

* `core/test`: a position past the last parameter fails the call, and the other calls in the request
  run.
* `client/conformance`: a test that sends the position to the real server with `raw.request`.

`test_too_many_arguments` stays as it is. Its Lua expected failure also stays, as a generated Lua
function discards extra arguments before the client encodes the request.
