# Deprecation signals for every member kind in every client

**Status:** in progress. Implemented in two local commits with no PR yet. See [Implementation](#implementation).

`[Obsolete]` can mark a service, procedure, property, class, method, enum, enum value, struct, field or exception. The scanner reads each one, and the protocol carries `deprecated` and `deprecated_reason` for each kind. Docgen renders a notice for every kind. The clients signal only some of them:

| Kind | C# | C++ | Java | Python | C-nano | Lua |
| --- | --- | --- | --- | --- | --- | --- |
| Service | none | none | none | docstring | none | none |
| Procedure, method, property | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | `DeprecationWarning` | `KRPC_DEPRECATED` | none |
| Class | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | none | none | none |
| Enum, enum value | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | none | none | none |
| Struct, field | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | none | none | none |
| Exception | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | none | none | none |

A deprecated service or class does not deprecate its members. The `LIDAR` service is an example. The service and the `Laser` class carry `[Obsolete]`, but `LIDAR.Laser` and `LIDAR.Available` do not. So `conn.lidar.laser(part)` in Python and `connection.LIDAR().Laser(part)` in C# run with no warning.

## Proposal

* **Members inherit the deprecation of their service or class.** A member with no reason of its own takes the container's reason. Apply this in clientgen's shared model and in the Python and Lua runtimes. The protocol and the docs stay as declared, so the reference keeps one notice per page.
* **Python:** warn on use of a deprecated class, enum value, struct field and exception. Mark the generated stubs with `warnings.deprecated` (PEP 702, `typing_extensions` before 3.13), so type checkers flag them too.
* **C-nano:** `KRPC_DEPRECATED` on enum values, struct typedefs, fields and exception codes, where the compiler supports the attribute.
* **Lua:** a warning on calling a deprecated procedure, method or property, at least once per member. Types follow if the runtime can hook their use cheaply.
* **C#, C++, Java:** only the inherited deprecation of the first bullet.

## Testing

Deprecation is shared client behavior, so it belongs in `client/conformance/`. `test_deprecated_warning` is a single `@untested` requirement, because the testee protocol has no channel for warnings. Add that channel to `testee.proto`, then split the requirement by kind. The compile-time attributes in C#, C++, Java and C-nano can be checked by compiling a use of each member with warnings as errors. `TestService` already has a deprecated procedure, property, class, method, enum, enum value, struct, field and exception. It needs a deprecated service, and a member of `DeprecatedClass` with no `[Obsolete]` of its own. A language that cannot signal a kind lists the test in its `unsupported.txt`.

## Implementation

The commits are "Signal the deprecation of every member kind in every client" and "Test deprecation signals in the conformance suite". All of the proposal landed, except the gaps below.

| Kind | C# | C++ | Java | Python | C-nano | Lua |
| --- | --- | --- | --- | --- | --- | --- |
| Service members | inherited | inherited | inherited | inherited | inherited | inherited |
| Procedure, method, property | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | `DeprecationWarning` | `KRPC_DEPRECATED` | stderr |
| Class | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | `DeprecationWarning` | `KRPC_DEPRECATED` | stderr |
| Enum, enum value | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | `DeprecationWarning` | `KRPC_DEPRECATED` | stderr |
| Struct | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | `DeprecationWarning` | `KRPC_DEPRECATED` | stderr |
| Struct field | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | `DeprecationWarning` on read | `KRPC_DEPRECATED` | none |
| Exception | `[Obsolete]` | `[[deprecated]]` | `@Deprecated` | `DeprecationWarning` | none | none |

Lua warns once per member on each connection. Python stubs also carry PEP 702 `@deprecated`.

### Divergences from the Proposal

| Proposal | Implementation | Reason |
| --- | --- | --- |
| C#, Java checked by compiling with warnings as errors | Reflection over the attribute | The attribute is what the compiler reads, and reflection needs no extra build step |
| C++, C-nano checked by compiling with warnings as errors | A build rule compiles a use of each member and records the compiler's warnings | The testee reports the warnings through the same channel as the other clients |
| C-nano marks exception codes | No signal | An exception has no C type |
| Testee channel for warnings | `DeprecationSignals`, one command for every client | Requirements are split by kind, with controls for members that are not deprecated |
| Fixtures in `TestService` | Also a new `DeprecatedService`, and partly deprecated enum and struct types | A service is deprecated as a whole, so it needs its own fixture |

### Additions to the Proposal

* **Header suppression:** generated C++ headers warned about their own deprecated types. C++ and C-nano headers now suppress the warning for their own code only, so a use in a program still warns.
* **Enum and struct members:** a deprecated enum or struct also deprecates its values or fields.

### Gaps

* **Lua:** no signal for struct fields, because a field is a plain table entry. No signal for exceptions, because the client has no exception types.
* **Python struct fields:** only reads warn. Constructing the struct stays silent, because the decoder uses the same constructor.
* **Java:** signals carry no reason, because `@Deprecated` has none.
* **MSVC in C:** no enumerator attribute, so a plain C program gets no warning for a deprecated enum value. The conformance probe compiles as C++ on that compiler.
* **Websockets testee:** the deprecation tests are expected failures, because it has no `DeprecationSignals` command.
* **`_call` and `_stream`:** the C++ `_call` and `_stream` functions carry no `[[deprecated]]`. Neither do the C-nano `_call` functions from #1267, once that lands. Each is a way to use a deprecated procedure with no warning.

### Verification

* **Passed on Linux:** every client's conformance suite and `//:test`, with `//doc:spelling` passing on a re-run after a one-word fix and `//client/cnano:communication-serialio` skipped. `bazel build //...` was clean before that fix.
* **Negative control:** with inheritance switched off, the inherited-member requirements failed in every client. The run exposed tests passing for the wrong reason. Those were tightened, and the control was not repeated afterward.
* **Type checker:** basedpyright flagged the deprecated members in a sample file and left the others alone.

### Open

* The MSVC path is unverified: `/Zs`, `/TP`, C4996 parsing and the enumerator attribute. The first Windows CI run exercises it, or a Windows session can check it first.
* The changelog fragment needs the PR number.
* Filing the issue, and the PR, remain to be done.
