# Client codegen: generate more than stubs

**Status:** done, G3, G5 and G1 merged as [PR #1172](https://github.com/krpc/krpc/pull/1172) for
0.8, ahead of the [conformance suite](client-conformance/README.md). G4 and G2 dropped. Split out of
[#1123](https://github.com/krpc/krpc/issues/1123).

## Problem

Only the service stubs are generated. Each client hand-copies the rest of what it knows about the
protocol and the server, and the copies disagree:

- **Exception mapping.** Python and C# map 11 server exceptions to native types, Java maps 10 with
  different picks, C++ maps none. Python's stub declares its own exception classes, which the
  client never raises.
- **Error messages.** Six formats. C# adds a trailing space and C++ drops the stack trace.
- **Constants.** Port 50000 in the server (4 places) and 6 clients. The local socket path rule in 6
  libraries plus the cnano benchmark.
- **The service list.** 12 entries repeated in five client BUILD files, the csproj, and twice in
  Python's `services/__init__.py`.
- **The `KRPC` service.** Its generated stubs have no goldens, so nobody reviews them.

## Sources

The servicedefs JSON (`core/src/Service/Scanner/*Signature.cs`), `protobuf/krpc.proto` and
clientgen (`tools/krpctools/krpctools/clientgen/`). The cnano `encoder.c` cog blocks
(`tools/build/cog.bzl`) are prior art for in-source generation.

## Phases

Each phase merges on its own. G3 and G5 change no behavior. G1 does, as ruled under
[Decisions](#decisions).

| Phase | Change | Replaces |
| --- | --- | --- |
| G1 | Add `string mapped_type` to `KRPC.Exception` in `krpc.proto` (additive, protocol version 2) and emit `KRPCException.MappedException` into both `GetServices` and the servicedefs JSON (`ExceptionSignature.GetObjectData` writes only documentation and deprecation today). Generated stubs take the native type from a per-language table in `lang/*.py`. Python and Lua, which build types at runtime from `GetServices`, read the new field. | Python `types.py` `EXCEPTION_TYPES` and the reverse table in `functionstatements.py`, C# `Connection.cs`, Java `Connection.java`. C++ gains a mapping. Each client's message assembly moves to the ruled format. |
| G3 | Goldens for the `KRPC` service: a `KRPC.Core.json` fixture and `clientgen-KRPC-<lang>.txt`. | Only `Empty`, `Ordering` and `TestService` have goldens today. |
| G5 | One Starlark list of services driving every `clientgen_*` target and Python `services/__init__.py`. | The 12-entry list (11 services plus TestService) in five client BUILD files, the csproj and `services/__init__.py`. |

Suggested order: G3 first, as it gives G1 a golden to change. Then G5, then G1. G1 is checked by
each client's own tests, updated to the new behavior. The conformance suite later pins
them as `errors-mapped-exceptions` and `errors-message`
(tests in `krpc` `conformance/tests/test_errors.py`, [client-conformance](client-conformance/README.md)).

### Dropped: G4

G4 was to generate the type code tables, the numeric limits and the Java tuple arity switch. Each
table maps the protoc type codes to native types of one language, so there is no shared copy to
remove. krpctools already takes its limits from `krpc.limits`. `limits.lua` differs by design, for
Lua 5.1 integers. The Java switch follows the fixed javatuples classes.

### Dropped: G2

G2 was to generate the protocol constants from custom options in `krpc.proto`. `krpc.proto` sets
`optimize_for = LITE_RUNTIME` for the C++ client's `protobuf_lite`, and protoc refuses a lite file
that imports the non-lite `descriptor.proto`. A separate source would need build plumbing in six
clients and the server for about eight stable values. They stay hand-written, and the conformance
suite checks them. G1 unified the message format by hand.

### Progress

- G3: the fixture is `KRPC.Core.json` from `//core:ServiceDefinitions`, so it cannot go stale.
- G5: `tools/krpctools/services.bzl` lists the services, and `clientgen_services` declares each
  client's targets from it. Python's `services/__init__.py` is expanded from a template. The C#
  `.csproj` cannot be generated, and had drifted to 5 of 11 services. A test now checks it against
  the list.
- G1: `mapped_type` holds the .NET type's full name, e.g. `System.ArgumentException`. The tables
  in `lang/*.py` and Python's `types.NATIVE_EXCEPTIONS` key on it. Java registers the native
  class through `addExceptionType`. Diverged from the plan in two places:
  - C# keeps its table in `Connection.cs`. Registering a constructor would add a member to the
    public `IConnection`, and the .NET argument exceptions take their arguments in different
    orders.
  - Lua raises strings, so it has no types to read `mapped_type` into. Its message already
    matched the ruled format, as did cnano's.

## Exception tables

The server defines 16 `KRPC` exceptions. 11 have a mapped type: `InvalidOperation`, `Argument`,
`ArgumentNull`, `ArgumentOutOfRange`, `NullReference`, `KeyNotFound`, `IndexOutOfRange`,
`DivideByZero`, `NotSupported`, `Timeout` and `Overflow`. The other 5 (`Error`,
`ObjectDestroyed`, `ObjectNotLoaded`, `StreamRemoved`, `UnsupportedScene`) raise their generated
types.

| Client | Today |
| --- | --- |
| Python, C# | The 11. C# gives `ArgumentNull` and `ArgumentOutOfRange` an empty parameter name |
| Java | 10, no `Timeout`. `InvalidOperation` maps to `UnsupportedOperationException`, `ArgumentOutOfRange` to `IndexOutOfBoundsException`, `Overflow` and `DivideByZero` to `ArithmeticException` |
| C++ | None. All 16 are generated `RPCError` subclasses |
| Lua, cnano | Strings and one error code |

Python's generated stub declares `class ArgumentException(RuntimeError)` and serves it on the
service, while the client raises the builtin `ValueError`. So `except conn.krpc.ArgumentException`
never fires (parity audit bug 26, [client-conformance/defects.md](client-conformance/defects.md)).
G1 fixes it by having the client raise the stub's class, which subclasses the builtin. Code
catching the builtin is unaffected.

## Error message format

| Client | Format |
| --- | --- |
| Python | description, `\nServer stack trace:\n`, trace. `Service.Name:` prefix only for an unknown type |
| C# | description, newline, `Server stack trace: ` (trailing space), newline, trace |
| Java | description, `\nServer stack trace:\n`, trace |
| C++ | description only. The trace is dropped. `Service.Name:` prefix for an unknown type |
| Lua | `Service.Name: description\nServer stack trace:\n...` |
| cnano | `Service.Name: description\nServer stack trace:\n...`, behind `KRPC_ERROR_MESSAGES` |

## Decisions

Ruled 2026-10-22.

| Decision | Ruling |
| --- | --- |
| Mapping for runtime-built clients | A `mapped_type` field on `KRPC.Exception`, not a generated client-side table. `GetServices` and the servicedefs JSON carry the same data. |
| Python exception classes | The client raises the stub's class, which subclasses the builtin. `except ValueError` and `except conn.krpc.ArgumentException` both catch it, and `ArgumentNull` stays distinct from `Argument`. Fixes parity bug 26. |
| C++ | The generated classes stay, each deriving from its `std` type. Types with no `std` equivalent stay `RPCError` subclasses. |
| Java | Follow the C# hierarchy. `Timeout` stays unmapped, as `java.util.concurrent.TimeoutException` is checked. |
| Error message format | `description\nServer stack trace:\ntrace` in all six clients. A `Service.Name: ` prefix only when the client has no type for the error, which in Lua and cnano is every error. The trace line is omitted when the trace is empty. |
| G2 scope and source | Constants only, as custom options in `krpc.proto`. Superseded: G2 dropped, see [Dropped: G2](#dropped-g2). |

### Native types

| Server | Python base | C++ base | Java |
| --- | --- | --- | --- |
| `InvalidOperation` | `RuntimeError` | `std::logic_error` | `IllegalStateException` |
| `Argument` | `ValueError` | `std::invalid_argument` | `IllegalArgumentException` |
| `ArgumentNull` | `ValueError` | `std::invalid_argument` | `IllegalArgumentException` |
| `ArgumentOutOfRange` | `ValueError` | `std::out_of_range` | `IllegalArgumentException` |
| `NullReference` | `TypeError` | `RPCError` | `NullPointerException` |
| `KeyNotFound` | `KeyError` | `std::out_of_range` | `NoSuchElementException` |
| `IndexOutOfRange` | `IndexError` | `std::out_of_range` | `IndexOutOfBoundsException` |
| `DivideByZero` | `ZeroDivisionError` | `std::domain_error` | `ArithmeticException` |
| `NotSupported` | `NotImplementedError` | `RPCError` | `UnsupportedOperationException` |
| `Timeout` | `TimeoutError` | `RPCError` | generated `RPCException` subclass |
| `Overflow` | `OverflowError` | `std::overflow_error` | `ArithmeticException` |

C# keeps its current table. Python's bases are today's `EXCEPTION_TYPES`.

### Breaking changes

Each needs a `**Breaking:**` changelog entry.

- **C++.** `catch (krpc::RPCError&)` no longer catches the 8 exceptions with a `std` base. `RPCError`
  derives from `std::runtime_error`, so a class cannot take both without two `std::exception` bases.
- **Java.** `InvalidOperation` changes from `UnsupportedOperationException` to
  `IllegalStateException`, and `ArgumentOutOfRange` from `IndexOutOfBoundsException` to
  `IllegalArgumentException`.
- **Message text.** C# loses the trailing space and C++ gains the trace. Code matching on the
  message text sees the change.

## Lower priority

- Shared test vectors for snake case and name parsing (`attributes.py` against `attributes.lua`).
- Moving the doc parsing in `service.py` and `service.lua` onto `docparser.py`.
