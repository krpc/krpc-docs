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
