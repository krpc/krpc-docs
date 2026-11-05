# Support flags enumerations

`SpaceCenter.MapFilter` holds a combination of `MapFilterType` values, as the game's
`MapViewFiltering.VesselTypeFilter` is a `[Flags]` enum. kRPC has no concept of a flags enumeration:

* `MapFilterType` lacks `[Flags]`, and the definitions sent to clients cannot mark one.
* Reading `MapFilter` in Python raises `ValueError` for a combination, as `Enum(value)` does. Java
  returns null. C#, C++, C-nano and Lua hold the number.
* A Python or Java script has no way to build a combination to set.
* Strict argument decoding fails a call that passes a combination.
* A default parameter value or an `Expression` enumeration constant that combines values is an
  error.
* `MapFilter` has no in-game tests.

Proposal:

## Definition

A `KRPCEnum` with `[Flags]` is a flags enumeration. The scanner checks its values:

* Each value is 0, a single bit, or a union of single bits the enumeration declares.
* No value is negative.

A value is valid when it holds no bit outside the union of the declared values. The server and the
clients all apply this rule. Other enumerations keep accepting declared values only.

`KRPC.Enumeration` gains `bool flags = 6`, and `servicedefs` carries it to clientgen. The value stays
a `sint32` on the wire. The new field is additive, so the protocol version does not change.

## Server

`Encoder`, `ParameterSignature.CheckEnumerationValues` and `Expression` share one validity check. A
server-side function can use a combination as a constant. Whether `Expression.And` and `Or` accept
enumeration operands is still to check.

## `MapFilterType`

`MapFilterType` gains `[Flags]`, and `All` changes from the game's -1 to 32767, the union of its bits.

* A negative member breaks Python's flag arithmetic. With `All = -1`, `T.all & ~T.debris` gives the
  wrong bits on Python 3.14.
* The getter masks the game's state with `All`, so the game's -1 reads as `All`.
* The setter passes the game's `All` when every bit is set.

This is a **Breaking:** change for a client that compares or sends the number -1.

## Clients

| Client | Type | Combine | Test |
| --- | --- | --- | --- |
| Python | A `DocFlag` base over `enum.Flag` | `a \| b` | `a in b` |
| C# | `[Flags] enum` | `a \| b` | `b.HasFlag (a)` |
| C++ | `enum struct` with generated `\|`, `&`, `^` and `~` | `a \| b` | `(b & a) == a` |
| C-nano | `typedef enum` | `a \| b` | `(b & a) == a` |
| Java | A generated final class of constants, implementing `RemoteEnum` | `a.or (b)` | `b.contains (a)` |
| Lua | `Types.Enum` with methods, as Lua 5.1 has no bitwise metamethods | `a:union (b)` | `b:contains (a)` |

* **Java.** A Java `enum` cannot hold a combination. A class keeps one type name in every signature
  and leaves the `fromValue` path in `Encoder` unchanged. The alternative, `EnumSet`, needs a
  separate encoding path and a different signature for these members.
* **Python.** `enum.Flag` raises `ValueError` for an undeclared bit, and `~` stays within the declared
  bits (checked on 3.12 and 3.14, not yet on 3.10). `enum.IntFlag` keeps undeclared bits. A negative
  number decodes as a complement, so the decoder checks for it.
* **Undeclared results.** C#, C++, C-nano, Java and Lua list `test_undeclared_enum_result` as an
  expected failure. The undeclared bit result test joins that list where the client does not check.

## Conformance tests

`TestService` gains a flags enumeration with a zero value, three bits and a union, and procedures that
echo it, return its number and take it as a default. It appears in the clientgen and docgen goldens.

A new testee command combines two values and another tests for one, in every testee.

| Requirement | Profile |
| --- | --- |
| A combination arrives intact in both directions, also in a list, a nullable and a structure | all |
| The zero value and a declared union decode as their declared values | all |
| A combination built by the client equals the same combination from the server | all |
| A client tests whether a combination holds a value, and removes a value from it | all |
| A default parameter value holding a combination applies when the argument is left off | all |
| A stream of a flags enumeration delivers a combination | all |
| A result holding an undeclared bit raises the encoding error, and the next call succeeds | all |
| An argument holding an undeclared bit is refused before it is sent | `dynamic` |
| The definitions mark a flags enumeration, and leave other enumerations unmarked | all |
| A combination of an enumeration without `[Flags]` stays an error | `dynamic` |

`core/test` covers the scanner rules and the decoding of valid and undeclared bits. In-game tests in
`service/SpaceCenter/test` cover `MapFilter`: reading a combination, setting one, and setting and
reading `All` and `None`.

## Docs

* `doc/src/extending/attributes.rst` adds the `[Flags]` rules to the `KRPCEnum` criteria.
* `doc/src/communication-protocols/messages.rst` covers `flags` and the validity rule.
* Each client guide shows how to combine and test values.
* The API reference marks a flags enumeration.
* `MapFilterType` says again that its values may be combined. Strict argument decoding removed that
  line, when the combination stopped working.
