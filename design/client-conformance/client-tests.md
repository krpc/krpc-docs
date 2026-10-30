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

## Built after C6

The suite closed most of the gaps the C6 classification found (harness.md "Built after C6"), and
a second read-only pass per client deleted the tests it now covers, under the same rule.

| Client | Deleted | Covered by |
| --- | --- | --- |
| C# | 23 tests, 281 lines | Exact mapped types for all eleven, held-condition waits, first callback call, stream value types, tuple and nullable collection vectors |
| Java | 18 tests, 253 lines | As C#, and the callback that raises |
| C++ | 23 tests, 254 lines | Codec vectors, held-condition and update waits, close and connection failure waking a wait |
| Python | 33 tests, 350 lines | As C++, the mapped exceptions, and object and double function values |
| Lua | 17 tests, 161 lines | New calls and values cases, tuple and nullable collection vectors, malformed data |
| cnano | 22 tests, 393 lines | The calls and values tests, keeping the caller's buffer, null result and `krpc_free` tests |

Closed: errors of every mapped type and exactly the mapped native type, removal errors where the
client's own removal raises them, the first callback call (a `first-call-on-add` profile),
holding a condition across commands (one update per wait, a zero timeout, the connection-wide
wait), stream values of nulls, enums and collections holding nulls, object-typed class
properties, 1- and 3-tuples, a nullable collection or struct in a list, functions at double,
nullable, list and object types with double and object arguments, a missing local socket path
and an unknown host.

Gaps left, each keeping client tests alive:

| Gap | Keeps |
| --- | --- |
| A client's own error types (`RPCException`, `EncodingException`, `StreamError`, `ArgumentException`) are checked by kind only | The typed clients' tests of a client-side error type |
| Expected failures: C++ KRPC exception registration, Java `StreamException` endings, the C# removed-stream type, Lua's error position | The client tests of each, until fixed |
| No `GetStatus`: the testees' generated dispatch skips message-typed results ([#1197](https://github.com/krpc/krpc/issues/1197)) | `test_version` in every client |
| No empty set or dictionary through a call, no uint32 set or dictionary vectors | The collection call and vector tests |
| No consecutive callback values, no timed rate, no callback that waits on a condition, no forced races | `TestCallback`, `TestRate`, the first-call wait tests, the race tests |
| Functions not at string, struct, tuple or dictionary types, and function stream error types | Most function stream tests |
| The C++ testee drops the client on close | The C++ close tests |

Wording, NaN bytes, multi-entry set and dictionary order, idioms and internals stay client tests
by design.
