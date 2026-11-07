# Clients: check whether a per-element function needs a real instance

To call an RPC on each element of a collection, a program with the expression API passes the instance twice. This is the Python example from the server side functions guide:

```python
has_fuel = conn.get_call(getattr, vessel.parts.engines[0], "has_fuel")
out_of_fuel = expression.lambda_(
    [engine],
    expression.not_(expression.call_with_arguments(has_fuel, {0: engine})),
)
```

`engines[0]` plays no part in the function, as the `{0: engine}` expression takes priority over the argument encoded in the call. The C++, C# and Java examples have the same shape. The [design](../design/server-side-functions/server-side-functions.md#calls) chose this on purpose: a client builds the template call from "any convenient instance", as it already builds a call that way for a stream.

This issue decides whether that choice is a problem worth fixing.

## Possible Costs

These come from reading the code. None has been reproduced in a test.

| Cost | Detail |
| --- | --- |
| A program needs an instance before it can build the function | A function asking whether any engine is out of fuel should return false on a vessel with no engines. Building it fails first: `engines[0]` raises an exception in Python, C# and Java, and is undefined behavior in C++ |
| The instance is still decoded | `ProcedureCall.ToMessage` decodes every argument before `BuildCall` runs. A template instance that was destroyed fails the whole function with `ObjectDestroyedException`, although the function never uses it |
| Round trips | The example makes two RPCs, `parts` and `engines`, only to get an unused object |
| Reading the code | `engines[0]` reads as though the function concerns the first engine |
| A mistake goes unnoticed | A value passed in the call and also in `args` is ignored with no error, whether or not the program meant to override it |

## What Already Avoids It

The server needs no instance in the call. The Python and C# function compilers build a `ProcedureCall` with only the service and procedure, and supply each argument as an expression. A program using the expression API has no such call to hand:

| Client | How a program gets the call |
| --- | --- |
| Python, C#, Java | `get_call` or `GetCall`, which takes an instance |
| C++ | A generated `_call` member of an instance |
| C-nano | A generated `_call` function for each procedure, once #1267 lands |
| Lua | `get_call`, once #1267 lands |

A program can build the message by hand with the internal procedure name, such as `Engine_get_HasFuel`. No guide describes this.

## Options

1. **Keep it, and document it.** The guide says the template's arguments are placeholders, and that the instance must exist.
2. **Add a way to build a call with no arguments.** Each client gets a form that names the procedure from the class, and the guide examples switch to it. Requires a design per client, as C++ and C-nano generate these calls per member.
3. **Also reject the overlap on the server.** A position in both the call and `args` fails. This is breaking, and `test_call_with_arguments` and `test_call_with_a_call_argument` rely on the overlap. It only becomes possible after option 2.

Option 1 is the default if the checks below find little real cost.

## Checks

* Reproduce the two failures in the table: a collection with no elements, and a destroyed template instance.
* Find out whether a null or default-constructed instance works as a placeholder in each client. The server does not check an overridden argument for null, so it may work already, but no client documents it.
* Find out how often real programs hit this. Programs on Python and C# can use the compilers in place of the expression API.
