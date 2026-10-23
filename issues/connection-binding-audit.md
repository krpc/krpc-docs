# Audit how each client binds calls that have no instance to a connection

A static class method, and a stream of one, has no object to carry the connection. The clients bind it to a connection in different ways:

| Client | Call | Stream |
| --- | --- | --- |
| Python | `conn.test_service.TestClass.static_method(a, b)`, the class reached through the connection | `conn.add_stream(conn.test_service.TestClass.static_method, a, b)` |
| Lua | Through the connection's service object, as in Python | No streams |
| C# | `TestClass.StaticMethod(connection, a, b)` | `connection.AddStream(() => TestClass.StaticMethod(connection, a, b))` |
| Java | `TestClass.staticMethod(connection, a, b)` | `connection.addStream(TestClass.class, "staticMethod", connection, a, b)`, the connection passed twice |
| C++ | `TestClass::static_method(client, a, b)` | `TestClass::static_method_stream(client, a, b)` |
| cnano | `krpc_TestService_TestClass_StaticMethod(connection, &result, a, b)` | No streams |

Two of these are defects:

- **Java** needs the connection twice to stream a static method. Its own tests never stream one, and the conformance dispatch got it wrong.
- **Python** binds a static method by writing the client onto the shared stub class, so the first client to call it through an instance binds it for every client (`python-static-method-binding` in the conformance defects).

Audit every place a client binds a call to a connection: static methods, service objects (`TestService.newInstance(connection)`, `connection.TestService()`), streams, events, and the `KRPC.Expression` builders. Decide one rule for the conformance spec, and list the API changes each client needs. A change to the Java `addStream` form is breaking.

Related to #1123.

Design: [defects.md](https://github.com/krpc/krpc-docs/blob/main/design/client-conformance/defects.md)
