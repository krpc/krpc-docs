# Python: build every service from the server's definitions, with generated declarations for type checking

The Python client has two implementations of every service, generated stubs and services built from `GetServices`, and a third path that adds members a stub lacks. They differ in behavior, and several defects exist only on the stub paths.

Replace them with one implementation:

 * **Every service is built from `GetServices` at connect.** The client always has the RPCs the server has, including members a mod adds to a shipped class. `use_pregenerated_stubs` is removed.
 * **`clientgen` writes importable `.py` modules for type checking.** Enumerations, structures and exceptions are real classes, so `def f(mode=SASMode.prograde)` needs no connection. Classes and services are declarations whose bodies raise a `TypeError` naming the fix.
 * **Types match by definition.** Where the server's definition matches the module, the client uses the generated class, so `==`, `is` and `isinstance` work on imported types. Otherwise it builds its own, and a generated enumeration value converts to it by number. A client and server of different releases are not supported.
 * **`krpc.connect()` connects with `krpc.ksp.KSPClient`**, so a script with no client type type checks against the KSP services. `krpc.connect[T]()` connects with another client type.

Follow-up: `krpc.connect()` defaulting to `KSPClient` suits KSP only. A KSA program gets the KSP types, and after the planned package split the base package's `connect()` would need `krpc-ksp`. A connect per game, such as `krpc.ksp.connect()`, is one fix, to settle before the KSA client types.

This is a breaking change for 0.8. The conformance prerequisite is #1298. It also replaces the Python part of #1195.

Design: `design/python-declarations.md` in the planning repo.
