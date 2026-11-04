# Deprecation signals for every member kind in every client

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
