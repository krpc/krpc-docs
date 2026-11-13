# Scanner rules for service, type, parameter and enumeration value names

The scanner checks service, type, member and field names against `^[A-Z][A-Za-z0-9]*$`, and #1237
adds case-insensitive member keys. Some clashes in the generated client code are still possible.
The scanner gains these checks, each leaving out the names that break it and the members that
depend on them:

* **Service names** are unique, compared case-insensitively. `Foo` and `FOO` share the Python module
  `krpc.services.foo` and the C-nano `KRPC_FOO_` constants.
* **Type names** of a service are unique together, compared case-insensitively, and none is named as
  its service.
* **Parameter names** match `^[a-z][A-Za-z0-9]*$`, and are unique within a procedure compared
  case-insensitively. `fooBar` and `FooBar` both become C++ and Python `foo_bar`.
* **Enumeration value names** match `^[A-Z][A-Za-z0-9]*$`.
* **Helper keys.** A member `Foo` also reserves `FooStream` and `FooCall`, and a property `Foo` also
  reserves `SetFooCall`, as C++ generates `foo_stream`, `foo_call` and `set_foo_call`.

Every bundled and test service already meets these rules.

Design: [service-definition-rules.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/service-definition-rules.md)
