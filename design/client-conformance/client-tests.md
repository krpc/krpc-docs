# Client tests

What each client's own suite keeps once the conformance suite runs, and what C6 deletes.

## Layers

| Layer | Where | Fate |
| --- | --- | --- |
| Comms tests against TestServer | `test_client`, `ConnectionTest`, `test_stream`, `StreamTest`, ... | Replaced by the suite, except the idiom tests below |
| Stand-in server tests | Python `test_session.py`, C# and Java `ConnectionTestCase` with `StandInServer` | Replaced by the scripted server |
| Codec vectors | `test_encodedecode`, `EncoderTest`, `test_encode_decode`, ... | Replaced by `test_codec.py`. Core's `EncoderTest.cs` stays, as it tests the server |
| Transport and framing | `connectiontest.py`, `connection_test.hpp`, cnano `test_communication_*` | Kept: they test the client's socket layer below the testee |
| Type system and coercion | `test_types`, `test_limits` | Kept: language specific |
| Name parsing and conversion | `test_attributes`, `test_snake_case` | Kept. Shared vectors are a lower priority ([client-codegen.md](../client-codegen.md)) |
| Function builders | `test_functioncompiler`, `FunctionCompilerTest`, `test_expressiontree`, `ExpressionTreeTest` | Kept: each builder is its own idiom |
| Golden fixtures | `tools/krpctools/krpctools/test/clientgen-*`, `docgen-*` | Kept: they pin generated code, defaults' spellings and deprecation markers |

## Idiom tests

Tests of language features the suite cannot express. Each stays in its client.

| Client | Tests |
| --- | --- |
| Python | Context manager on a connection and a stream, `KeyboardInterrupt` and `BaseException` from callbacks, traceback growth on re-raise, the dynamic service path without stubs (`client-base`), `DeprecationWarning` |
| C# | LINQ stream and function forms (`MultiplyByOne`, `NarrowingConversionIsComputed`), `IDisposable` |
| C++ | Handle copy and assignment (`test_default_constructable`, `test_assignable`, `test_acquire_through_two_handles`), destroying a handle while another thread holds its lock, `shared_ptr` and container use |
| Java | Stream lookup by method name (`GetCallWithNonInternedMethodName`, `GetCallWithWrongArgumentType`), registration without stubs, close from an interrupted thread |
| Lua | Coercion does not leak a global |
| cnano | Allocation (`string_malloc_and_free`), the Arduino read backend, the POSIX and Windows serial backends |

## Coverage gaps closed by the suite

Behavior a client exposes today but does not test. Each becomes a pass or an expected failure.

| Requirement | Tested today in |
| --- | --- |
| `errors-null-return-rejected` | Python only |
| `errors-invalid-object-id` | Python only |
| `calls-special-defaults` | Python only (fixtures and compiles pin the spelling elsewhere) |
| `calls-partial-arguments` on methods, `calls-named-arguments` | Python only |
| `connection-refused`, `connection-ended-by-the-server` | Python, C# and Java, each against its own stand-in |
| `connection-wrong-port` | All but cnano |
| Stream and event behavior | Each of Python, C#, C++ and Java tests a different subset |

## Built in C6

A client test is deleted only when one conformance test checks the same behavior through the same
client API at least as strictly. A read-only pass per client classified every test, and each
deletion names its conformance test there. The rest stays: idioms, tests of a client's internals,
and tests that pin more than the suite does.

| Client | Deleted | Kept, in the main |
| --- | --- | --- |
| C# | 83 tests, 1,044 lines | `MappedExceptions`, the forced stream manager races, the exact exception types, `Wait(0)`, the stand-in server cases |
| Java | 73 tests and 8 codec vector files, 1,285 lines | The double, float, set and dictionary vector files, the forced races, the exact exception types |
| C++ | 73 tests, 873 lines | Handle copies and locks, the stream manager tests, the KRPC exception types (expected failures in the suite) |
| Python | 107 tests and `test_threading.py`, 1,551 lines | The compiler tests, `__cause__`, `KeyboardInterrupt`, the forced races, the exact exception types |
| cnano | 12 codec tests, 110 lines | `test_client.cpp` whole, the direct encoded size and NaN byte checks |
| Lua | 41 tests, 550 lines | The error message texts, the NaN bytes, the encoding order of sets and dictionaries, the uint64 values, `GetStatus`, coercion |

Decisions made while deleting:

- **Python runs the suite without stubs too.** `//client/python:conformance-base` runs a testee on the
  base library, which builds its services from the server's definitions, as `client-base` does. So
  the deleted Python tests keep their coverage of runtime services.
- **Lua's tests went before a Windows run.** The line framing (harness.md "Built after C6") turns its
  Windows conformance target back on. No client's suite has run on Windows yet, so Lua's covered
  tests went on the same footing, and a Windows failure is fixed when CI shows one.
- **cnano keeps `test_client.cpp`.** cnano has no local socket conformance target, and the file is
  the only test of a caller's buffer for a string, a null result pointer and `krpc_free`.
- **The local socket runs only the connection page** (README "Open questions"), so the per-client
  `client-localsocket` targets now run fewer calls over a local socket. That was the plan.
- **No stand-in server file goes.** Each still holds a case the suite lacks, such as a malformed
  handshake response or a response after the disconnect.

Gaps in the suite the classification found, each keeping client tests alive. Closing one lets more
tests go:

| Gap | Keeps |
| --- | --- |
| Errors are checked by kind: `raised` accepts any error, and `is_removed_error` a stream or RPC error | Every exact exception type test, in all four typed clients |
| `errors-mapped-exceptions` covers 4 of the 11 mapped types | `MappedExceptions` in each client |
| The C++ testee drops the client on close, so a call after close never reaches the client | The C++ close tests |
| A first callback call may run on the adding thread, so the suite cannot ask for it | The synchronous first call tests |
| No exact one update per wait with the condition held, no zero timeout | `test_wait` and its variants |
| No `GetStatus`, object-typed class property, null int or string stream value, 1- or 3-tuple, nullable collection in a list | The tests of each |
| Functions only at sint32, bool and string, with no object argument | Most function stream tests |
| `connection-wrong-port` never opens a missing local socket path | The localsocket connect tests |
