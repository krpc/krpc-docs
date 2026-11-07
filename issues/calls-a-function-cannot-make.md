# Clients: calls that cannot go in a server side function

`KRPC.Expression.Call` and `CallWithArguments` reject three kinds of procedure when a function is built:

* A procedure of the `KRPC` service.
* A procedure that returns a stream or an event.
* A procedure that returns a protocol buffer message.

Every client still lets a program build a `ProcedureCall` for these, and the program finds out from a server error at run time.

| Client | How a program gets the call | Other use of the call |
| --- | --- | --- |
| C++ | A generated `_call` for each procedure, 163 of them for `KRPC` | None known, as `_stream` builds its own call |
| C-nano | A generated `_call` for each procedure, 163 of them for `KRPC` once #1267 lands, 150 of those on `Expression` and `Type` | None, as the client has no streams |
| Python, C#, Java | `get_call` or `GetCall` at run time | `add_stream` takes the same call, and `KRPC.AddStream` has no such rejection |
| Lua | `get_call` at run time, once #1267 lands | None, as the client has no streams |

The generated functions cost the most where they can never succeed. `krpc_KRPC_Expression_Add_call` reads as a supported way to embed a call, and its comment says it fills in a call to pass to `krpc_KRPC_Expression_Call`. The `_call` functions add about 2,200 lines to the C-nano `KRPC` header.

Only the Python guide says that the procedures of the `KRPC` service cannot be called, and only for compiled functions. `test_functions.py` does not test any of the three rejections. `core/test/Service/KRPC/ExpressionTest.cs` tests the rejection of `KRPC` procedures and events, which does not show what a client does with them.

## Proposal

* **Generated clients leave out what cannot be used.** C-nano generates no `_call` for the three kinds. C++ does the same, once it is confirmed that nothing else uses those functions. The C++ and C-nano conformance dispatch then has no call to build for them, so a test that needs one builds it by hand or lists the client in `unsupported.txt`.
* **Run-time clients keep building the call**, as `add_stream` needs it. The server's error remains the check, raised when the function is built.
* **Add a requirement to the client spec.** Embedding each of the three kinds in a function raises the server's error when the function is built. Lua and the threaded clients run it directly.
* **Document the limit once**, in The Expression API section of the server side functions guide, and link to it from the client guides.

## Questions

* Should a run-time client's `get_call` be split from the call `add_stream` uses, so that it can raise on the client? The server's error already names the procedure and the reason, so this proposal leaves it as is.
* Does dropping the C++ functions count as a breaking change? They compile today, and only ever produce a call the server rejects in a function.
