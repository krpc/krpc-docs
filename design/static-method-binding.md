# Static method binding

**Status:** proposal. Issue [#1195](https://github.com/krpc/krpc/issues/1195).

A static class method has no object to carry the connection. This doc audits how each client binds
one to a connection, for a call, a stream and a call builder, and plans one rule for all of them.

## Where static methods are used

About 160 RPCs, so the binding shows up in real programs, mostly in server side functions.

| Service | Class | Static methods |
| --- | --- | --- |
| KRPC | `Expression` | 125 |
| KRPC | `Type` | 17 |
| SpaceCenter | `AlarmManager` (7), `Orbit` (4), `ReferenceFrame` (2), `Resources` (2), `ResourceTransfer` (1) | 16 |
| Drawing | `Text`, `NavballMarker` | 2 |

Several create objects that belong to the calling connection (`ReferenceFrame.CreateRelative`,
`ResourceTransfer.Start`, the `AlarmManager` adds). The server removes them when that connection
ends ([proxy-object-conventions.md](proxy-object-conventions.md)), so the connection a static
method runs on matters beyond routing.

## Audit

### Service procedures, for comparison

Every object-oriented client reaches a service procedure through a service object bound to the
connection. cnano passes the connection to every function.

| Client | Service object | Call | Stream |
| --- | --- | --- | --- |
| Python | `conn.space_center` | `sc.warp_to(ut)` | `conn.add_stream(getattr, sc, "ut")` |
| Lua | `conn.space_center` | `sc.warp_to(ut)` | none |
| JS (branch) | `conn.spaceCenter` | `await sc.warpTo(ut)` | not yet (phase 4) |
| C# | `connection.SpaceCenter()` | `sc.WarpTo(ut)` | `connection.AddStream(() => sc.UT)` |
| Java | `SpaceCenter.newInstance(connection)` | `sc.warpTo(ut)` | `connection.addStream(SpaceCenter.class, "getUT")` |
| C++ | `SpaceCenter sc(&client)` | `sc.warp_to(ut)` | `sc.ut_stream()` |
| cnano | none | `krpc_SpaceCenter_WarpTo(conn, ut)` | none |

### Static methods

| Client | Call | Through an object | Stream | Call builder |
| --- | --- | --- | --- | --- |
| Python | `conn.test_service.TestClass.static_method(a, b)` | `obj.static_method(a, b)` | `conn.add_stream(conn.test_service.TestClass.static_method, a, b)` | `get_call(...)`, same shape |
| Lua | `conn.test_service.TestClass.static_method(a, b)` | `obj.static_method(a, b)` | none | none |
| JS (branch) | `conn.testService.TestClass.staticMethod(a, b)` | unsupported | not yet | not yet |
| C# | `TestClass.StaticMethod(connection, a, b)` | not in C# | `connection.AddStream(() => TestClass.StaticMethod(connection, a, b))` | `Connection.GetCall(() => ...)`, same shape |
| Java | `TestClass.staticMethod(connection, a, b)` | not used in Java | `connection.addStream(TestClass.class, "staticMethod", connection, a, b)` | `connection.getCall(...)`, same shape |
| C++ | `TestClass::static_method(client, a, b)` | not used in C++ | `TestClass::static_method_stream(client, a, b)` | `TestClass::static_method_call(client, a, b)` |
| cnano | `krpc_TestService_TestClass_StaticMethod(conn, &result, a, b)` | n/a | none | none |

Two models are in use, and they split by whether the language's classes are values:

* **Classes are values** (Python, Lua, JS). Each connection has its own class, reached through
  the service object. A static method takes the connection from there, as a service procedure
  does.
* **Classes are types** (C#, Java, C++), and cnano's functions. The connection is the static
  method's first argument.

Both models pass the connection once for a call. The defects are in the wrappers and in one
Python path.

### Findings

| # | Client | Finding | Severity |
| --- | --- | --- | --- |
| 1 | Java | `addStream(Class, name, args...)` and `getCall(Class, name, args...)` take the connection again as the first of `args`. Both drop it unchecked, so `null` or another connection works there. A service procedure through the same overload takes no connection. | API wart, the one #1195 names |
| 2 | Python | `StaticMethod.__get__` writes `_client` onto the shared stub class when called through an object. The first client to do this binds the class for every client. A later client's static call through an object runs on the first connection, and fails once that connection closes. Objects it creates belong to the wrong connection. | Bug, shipped in v0.7.0 ([defects.md](client-conformance/defects.md) `python-static-method-binding`) |
| 3 | Python | The conformance suite misses finding 2. `ConformanceService` and `TestService` have no pre-generated stubs, so the testee takes the dynamic path, whose classes are per client. `test_static_method_through_an_object_connection` passes. | Test gap |
| 4 | Python | A stub class imported directly (`from krpc.services.spacecenter import ReferenceFrame`) has no client. Its static methods fail with an `AttributeError` on `_client`, or work after some earlier call through an object bound it (finding 2). | Confusing error |
| 5 | C# | In a stream or `GetCall` lambda, the static method's connection argument is skipped and never evaluated. The stream runs on the connection `AddStream` is called on. This matches a service object or an object in the lambda, which also carry a connection the stream does not use. | Consistent, no change |
| 6 | C++ | Consistent: the connection once, for the call, the stream and the call builder. | None |
| 7 | Lua, cnano | Consistent. No streams. | None |
| 8 | JS | Matches Python. A static method through an object is unsupported, which suits JavaScript (a static method lives on the constructor). | None |
| 9 | Docs | Only the Java guide (`java.rst`) describes a static method, and it documents the doubled connection. The other client guides do not show how to call or stream one. | Docs gap |

## Decision

**A static method takes its connection from one place, the one its language gives a class:**

* where classes are values, the service object the class is reached through, as for a service
  procedure;
* where classes are types, the method's first argument, the one place that names it.

A wrapper that turns a call into a stream, event or call message never takes the connection a
second time. Where the wrapper is a method of the connection (`addStream`, `getCall`), the
connection it is called on is the connection, and the wrapped call names none.

Each form is the ordinary static method syntax of its language: `Class.method(...)` on a
connection's service in Python, Lua and JS, `Class.Method(connection, ...)` in C#, Java and C++.
Calling through an object stays where the language allows it (Python, Lua), and runs on the
object's connection.

### Applied per client

| Client | Change |
| --- | --- |
| Java | `connection.addStream(TestClass.class, "staticMethod", a, b)` and `connection.getCall(...)` likewise, matching a service procedure. |
| Python | Through an object, bind to that object's client without touching the shared class. An unbound stub class raises an error naming the fix. |
| C#, C++, Lua, cnano, JS | No change. |
| Docs | Each client guide shows a static method call and, where the client has them, its stream. |

## Plan

Each phase merges on its own. Milestone `ksp-v0.8.0` (clients release with KSP).

### Phase 1: Java streams and calls

* `addStream(Class, name, args...)` and `getCall(Class, name, args...)`: for a static method,
  `args` are the method's arguments. The lookup matches a static method whose parameters are
  `Connection` followed by `args`.
* The old form, with a leading `Connection`, is accepted and deprecated. It throws if that
  connection is not the one the method is called on. Removed in a later release.
* `java.rst` and the Java testee's stream and call commands switch to the new form. The existing
  `test_streams.py::test_members[static-method]` and `test_functions.py::test_call_member_kinds`
  cover it.
* Changelog `client/java`: "**Deprecated:** Passing the connection to `addStream` and `getCall`
  for a static method, which now take only its arguments (#1195)".

### Phase 2: Python binding

* `StaticMethod.__get__` through an object binds to `_wrapped_subclass(obj._client, type(obj))`
  and never writes `_client` onto the shared class.
* Called on an unbound stub class, a static method raises a `TypeError`: reach the class through a
  connection, as `conn.space_center.ReferenceFrame`.
* A native test in `client/python/krpc/test`: two connections through the pre-generated `KRPC`
  stub, static calls through objects from each, then one connection closed. This covers the
  internals that the conformance suite cannot reach (finding 3).
* Changelog `client/python`: "Fix static methods called through an object running on another
  connection (#1195)".

### Phase 3: Docs and spec

* A short "Static Methods" section in each client guide (Python, Lua, C#, Java, C++, C, C-nano),
  with a call and, where supported, a stream. Examples in `doc/src/scripts/`, using
  `ReferenceFrame.CreateRelative`.
* The spec text of `test_static_method_connection` states the rule above: the connection comes
  from the service object or the connection argument.
* Close #1195. Mark `python-static-method-binding` fixed in [defects.md](client-conformance/defects.md).

### Phase 4: Bound classes in C#, Java and C++

Building an `Expression` tree passes the connection at every node, 34 times across the C# doc
examples alone:

```cpp
auto total = Expr::variable(conn, "total", KType::int_(conn));
Expr::for_each(conn, x, values, Expr::assign(conn, total, Expr::add(conn, total, x)));
```

clientgen adds a `bind` factory to each class with static methods. It returns a small `Bound`
object that holds the connection and has each static method, minus the connection parameter:

```cpp
auto e = Expr::bind(conn);
auto t = KType::bind(conn);
auto total = e.variable("total", t.int_());
e.for_each(x, values, e.assign(total, e.add(total, x)));
```

| Client | Factory | Bound call |
| --- | --- | --- |
| C# | `var e = Expression.Bind(connection);` | `e.Not(e.Call(engines))` |
| Java | `Expression.Bound e = Expression.bind(connection);` | `e.not(e.call(engines))` |
| C++ | `auto e = Expression::bind(client);` | `e.not_(e.call(engines))` |

This is the typed-language counterpart of Python's `E = conn.krpc.Expression`. The bound object is
the one place that names the connection, as a service object is, so the rule above holds.

* **Opt-in.** `Class.Method(connection, ...)` stays the primary form, so nothing is deprecated.
* **Generated, for every class with static methods.** One loop per template, forwarding to the
  static method. It is generic rather than `Expression` only, so there is one rule. It adds a
  forwarder per static method, about 160.
* **Streams and call builders.** In C# and Java, the bound methods carry the static method's RPC
  attribute. C#'s `GetCall` already treats an object that is not a `RemoteObject` like a service
  object, so `connection.AddStream(() => e.Not(x))` works unchanged. Java's
  `addStream(Expression.Bound.class, "not", x)` works the same way. C++ gets calls only, as
  streaming an expression builder has no use, and its `_stream` forms stay on the static method.
* **Name clashes.** No class has a static method named `Bind` or a member named `Bound`. clientgen
  fails if one ever does.
* **Docs.** The server side functions guide uses the bound form in its C#, Java and C++ examples.
  Each client guide's "Static Methods" section (phase 3) shows it in one sentence and one example.
  The API reference comes from the service definitions, so it does not list `Bound` classes.
* **Tests.** A native test per client checks one bound call, and C# and Java a stream of one. The
  doc examples compile in the build. Bound classes are client API, so they get no conformance test.
* Changelog `client/csharp`, `client/java`, `client/cpp`: "Add `Bind` to classes with static
  methods, for calling them without passing the connection (#1195)", in each client's casing.

## Alternatives considered

| Alternative | Why not |
| --- | --- |
| Reach static methods through the service object in C#, Java and C++ too (`sc.ReferenceFrame.CreateRelative(...)`) | One form across all clients. Phase 4 gets the same ergonomics as an opt-in. But in C++ a member cannot share its name with the nested class, in Java a public field named like a class is unusual, and in C# it hides the ordinary `ReferenceFrame.CreateRelative` call. About 160 methods, and every server side function example in three languages, would go through a deprecation cycle. |
| A bound statics object from the connection (`connection.Statics<ReferenceFrame>()`) | Not the ordinary static method syntax of any of the languages. |
| A default connection for static methods | Implicit global state, and wrong for programs with two connections. |
| Check, in C#, that a static method's connection argument in a stream lambda is the stream's connection | A service object or an object in the lambda carries a connection the stream does not use either. Checking one of the three is inconsistent, and checking objects contradicts `objects-from-another-connection`. |
| A hand-written `Expression` builder per client | About 140 methods by hand in three languages, drifting from the server. |
| Operator overloads on `Expression` (`a + b`) | Covers arithmetic and comparison only. A larger design, and C# already has `connection.Compile`. |

## Out of scope

* Operator overloads for `Expression` in C# and C++.
