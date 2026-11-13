# Flags enumerations in server side functions

Follows [krpc-enum-flags.md](krpc-enum-flags.md). A server side function can hold a constant
combination of flags, and `KRPC.Expression.And`, `Or` and `ExclusiveOr` combine two values of a
flags enumeration. A function cannot yet combine or test flags whose values are only known when it
runs, such as a stream of `SpaceCenter.MapFilter`:

* `KRPC.Expression.Not` fails for an enumeration operand, as .NET defines no `Not` for an enum type.
* The Python function compiler allows `&`, `|` and `^` only on integers and bools, and has no `~` or
  `in` for flags. A constant combination folds before it reaches the server, so it works.
* The C# function compiler builds `a | b` on an enum as casts around an integer `Or`, which may work
  but is untested. `HasFlag` is a method call it does not map.
* No conformance requirement covers a function that combines or tests flags.

Lua, Java, C++ and C-nano build functions through the `Expression` API, so they get `And`, `Or` and
`ExclusiveOr` already, and `Not` once the server has it.

Proposal:

## Server

`Expression.Not` of a flags enumeration value gives the declared values the operand does not hold:
the complement masked with the union of the declared values, as the C++ client's `~` does. `Not` of
an enumeration without `[Flags]` stays an error.

## Python function compiler

| Python | Expression |
| --- | --- |
| `a \| b`, `a & b`, `a ^ b` | `Or`, `And`, `ExclusiveOr`, for two values of one flags enumeration |
| `~a` | `Not` |
| `a in b`, `a not in b` | `Equal(And(b, a), a)`, and its negation |

An operand of another enumeration, or two enumerations that differ, is a compile error.

## C# function compiler

* Test `a | b`, `a & b`, `a ^ b` and `~a` on a flags enumeration, and fix what fails.
* Map `b.HasFlag (a)` to `Equal(And(b, a), a)`.

## Conformance tests

Each testee's `RunFunction` and `AddFunctionStream` accept the type `TestFlags`.

| Requirement | Profile |
| --- | --- |
| A function combines two flags values it is passed, with union, intersection and difference | `functions` |
| A function tests whether a flags value holds another | `functions` |
| A function stream of a combination follows its operands | `functions` |
| A function combining two enumerations that differ, or one without `[Flags]`, is refused | `functions` |

`core/test` covers `Not` of a flags value and of an enumeration without `[Flags]`. The client
guides' server side function sections show combining flags, where the client compiles functions.
