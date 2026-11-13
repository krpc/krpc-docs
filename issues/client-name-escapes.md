# Clients: escape a service or type name that meets a client's own name

Some clients put public names of their own beside a service or a type. A definition with one of those names breaks the client today:

* **Python, Lua.** A service named as a client member, such as `Close` or `Stream`, replaces `conn.close` or `conn.stream`.
* **Python.** A type `SpaceCenterClient` in service `SpaceCenter` clashes with the generated module's client type.
* **C#.** A service `Dispose` loses to `IConnection.Dispose`. A type `Service` or `ExtensionMethods` clashes with the classes generated in each service's namespace.
* **C-nano.** A service `Error`, `Callback`, `Return`, `Bytes`, `Size` or `Type` gives enumeration value constants that match library names, e.g. `KRPC_ERROR_CONNECTION_FAILED`.

The scanner keeps no list of these names, as each new client or client feature can add more. Each client generator escapes the definition's name with a trailing `_` instead, as it already does for keywords: `conn.close_`, `SpaceCenterClient_`, `KRPC_ERROR__<ENUM>_<VALUE>`. The Python and Lua run-time clients escape a service attribute the same way.

Tests: `TestService` fixtures named after each name above, compiled by every client build, and a conformance test for the Python and Lua service attribute.

Design: [client-reserved-names.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/client-reserved-names.md)
