# Part 1: generate more than stubs

Replace the hand-written copies in each client with code generated from the servicedefs JSON
(`core/src/Service/Scanner/*Signature.cs`), `protobuf/krpc.proto` and clientgen
(`tools/krpctools/krpctools/clientgen/`). The cnano `encoder.c` cog blocks (`tools/build/cog.bzl`)
are prior art for in-source generation. None of it is started.

| Phase | Change | Replaces |
| --- | --- | --- |
| G1 | Emit `KRPCException.MappedException` into the servicedefs JSON (`ExceptionSignature.GetObjectData` writes only documentation and deprecation). Generated `KRPC` stubs register the native type from a per-language table in `lang/*.py`. | Python `types.py` `EXCEPTION_TYPES` and the reverse table in `functionstatements.py`, C# `Connection.cs`, Java `Connection.java`. C++ has none. |
| G2 | One protocol constants file: the default address and port, the local socket path rule, the error message format. Generate a constants module per client and for the server. | Port 50000 in the server (4 places) and 6 clients, the socket path rule in 6 libraries plus the cnano benchmark, and 6 message formats. |
| G3 | Goldens for the `KRPC` service: a `KRPC.Core.json` fixture and `clientgen-KRPC-<lang>.txt`. | Core stub output nobody reviews. Only `Empty`, `Ordering` and `TestService` have goldens today. |
| G4 | Type code tables and numeric limits from `krpc.proto` `TypeCode` plus a small map. | Python and Lua `VALUE_TYPES`/`MESSAGE_TYPES`, `limits.lua`, the Java tuple arity switch in `Encoder.java`. |
| G5 | One Starlark list of services driving every `clientgen_*` target and Python `services/__init__.py`. | The 12-entry list (11 services plus TestService) in five client BUILD files, the csproj, and twice in `services/__init__.py`. |

## Exception tables

The server defines 16 `KRPC` exceptions. 11 have a mapped type: `InvalidOperation`, `Argument`,
`ArgumentNull`, `ArgumentOutOfRange`, `NullReference`, `KeyNotFound`, `IndexOutOfRange`,
`DivideByZero`, `NotSupported`, `Timeout` and `Overflow`. The other 5 (`Error`,
`ObjectDestroyed`, `ObjectNotLoaded`, `StreamRemoved`, `UnsupportedScene`) raise their generated
types.

| Client | Today |
| --- | --- |
| Python, C# | The 11 |
| Java | 10, no `Timeout`. `InvalidOperation` maps to `UnsupportedOperationException`, `ArgumentOutOfRange` to `IndexOutOfBoundsException`, `Overflow` and `DivideByZero` to `ArithmeticException` |
| C++ | None. All 16 are generated `RPCError` subclasses |
| Lua, cnano | Strings and one error code |

G1 makes each table data. Which native types each language uses is a spec decision
([defects.md](defects.md) "Decisions").

## Error message format

| Client | Format |
| --- | --- |
| Python | description, `\nServer stack trace:\n`, trace. `Service.Name:` prefix only for an unknown type |
| C# | description, newline, `Server stack trace: ` (trailing space), newline, trace |
| Java | description, `\nServer stack trace:\n`, trace |
| C++ | description only. The trace is dropped. `Service.Name:` prefix for an unknown type |
| Lua | `Service.Name: description\nServer stack trace:\n...` |
| cnano | `Service.Name: description\nServer stack trace:\n...`, behind `KRPC_ERROR_MESSAGES` |

G2 changes behavior in C#, C++ and Lua. The spec's `errors-message` picks the format first.

## Lower priority

- Shared test vectors for snake case and name parsing (`attributes.py` against `attributes.lua`).
- Moving the doc parsing in `service.py` and `service.lua` onto `docparser.py`.
