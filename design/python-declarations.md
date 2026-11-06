# Python: generated declarations and dynamic services

**Status:** proposal, for 0.8. Issue: [python-declarations.md](../issues/python-declarations.md), not yet filed.

The Python client has two implementations of every service: generated stubs and services built from `GetServices`. A stub that lacks a member has a third path, `merge_service`, which adds the member to a per-client subclass. This doc replaces them with one implementation, always built from the server's definitions, plus generated modules that carry the type information.

The client then always has the RPCs the server has, and type checkers still see the shipped services.

## History

The client was dynamic with `.pyi` files until #703 (v0.5.2) made the stubs full implementations, for the reasons in #659:

| Reason | Today |
|---|---|
| Types could not be imported at run time (#626) | Solved here by `.py` modules |
| The `.pyi` types were wrong and untested (#627, #658) | Generator bugs. `pyright` checks the doc examples, and a drift test is added below |
| Static code might perform better | Not borne out, see [Evidence](#evidence) |

`merge_service` came later, for [extension members](protocol/extension-members.md).

## Decisions

### One implementation

Every service is built from `GetServices` at connect. `use_pregenerated_stubs` is removed with no deprecation, as the stream connection options were.

Each use case then works with no choice to make:

| Use case | Result |
|---|---|
| Type hints | The generated modules, which assume the server matches |
| A mod with its own service | Built at connect. Type checkers do not know it |
| A mod adding members to a shipped class | The members exist at run time. Type checkers do not know them |
| A server of another version | The services match the server. Type checkers see the client's version |

### Generated modules

`clientgen` writes `krpc/services/<service>.py`, importable at run time. It has no `.pyi` beside it:

| Kind | In the module | At run time |
|---|---|---|
| Enumeration, structure, exception | Real class | Usable with no connection |
| Class, service | Declaration | Never instantiated |

A default argument needs no connection and no `TYPE_CHECKING` guard:

```python
from krpc.services.spacecenter import SASMode

def f(mode: SASMode = SASMode.prograde) -> None:
    ...
```

A declaration keeps its signatures, types and documentation. Each body raises:

```python
class ReferenceFrame(metaclass=DeclaredClass):
    @staticmethod
    def create_relative(reference_frame: ReferenceFrame, ...) -> ReferenceFrame:
        """..."""
        raise _declaration("SpaceCenter", "ReferenceFrame")
```

 * **A body raises, in place of `...`.** `basedpyright` treats the two the same, in a prototype of both. A `...` body returns `None` silently when called, and importing a class makes that call an easy mistake.
 * **The error is the one [static-method-binding.md](static-method-binding.md) decided.** It is a `TypeError` naming the fix: reach the class through a connection, as `conn.space_center.ReferenceFrame`.
 * **Built classes do not inherit from declarations.** A member the declaration has and the server lacks would otherwise appear to exist.
 * **`DeclaredClass` compares names.** `isinstance` and `issubclass` compare the service and class names of the built class and its bases, which also suits [inheritance](protocol/inheritance.md). Calling a declaration raises the same `TypeError`.
 * **`krpc/services/__init__.py` stays, reduced.** It declares the attributes of `Client` for type checkers, and lists the modules. At run time a client has an attribute only for each service the server has.

### One class per type where the definitions match

A built enumeration is a different class from the imported one, so `dyn.prograde == imported.prograde` is false and `coerce_to` raises `ValueError`. At connect, the client therefore looks up each enumeration, structure and exception in the generated module:

| Definitions | Class used | Effect |
|---|---|---|
| Match | The generated class, shared by every client | `==`, `is` and `isinstance` work |
| Differ | One built for this client | The server's values all work. `==` and `coerce_to` compare service, name and value. `is` is false |
| No module | One built for this client | As today for a mod's service |

 * An enumeration matches on its names and values, and a structure on its field names in order. Field types always come from the server's definition, as they do today.
 * These classes hold no client, so sharing them brings back none of the stub defects.
 * A generated class is never altered to fit a server. That would change a class every client shares, based on one connection.
 * A structure already accepts any tuple of the right length.

### Static methods

The rule in [static-method-binding.md](static-method-binding.md) is unchanged: a static method takes its connection from the service object the class is reached through. A call through an object runs on the object's connection. Built classes already do both, and `test_static_method_connection` and `test_static_method_through_an_object_connection` pass on them. This replaces phase 2 of that doc, which fixes `StaticMethod` on the shared stub classes.

## What Goes

| Item | Note |
|---|---|
| `merge_service`, `extended_stub_classes`, `_stub_is_missing`, `_client_class` | The partial path |
| `WrappedClass`, `_wrapped_subclasses`, `StaticMethod` | Binding a shared class to a client |
| `_stub_definitions` | Reduced to the lookup above |
| The implementations in `python.tmpl` | Bodies become declarations |
| `:conformance-base`, `:client-base`, `:python_base` | One way to run the client |

`krpc_base_lib` stays, as `clientgen` imports the client and generates the modules. The dynamic path stays too, as it is now the only one.

These defects in [client-python-defects.md](../issues/client-python-defects.md) go with the code:

 * `types._wrapped_subclasses` pins every client.
 * Static methods through an object bind to the first client.
 * Passing an object between a stub and a dynamic client.
 * An enumeration only the server declares breaks a merged member.
 * An `ImportError` in any stub downgrades silently.
 * Without stubs, a service the server lacks is `None`.

## What Stays Broken

**Some member names fail the whole connect.** A parameter named `cls`, or an enumeration value named `Mro`, raises at connect. A mod's service can already do this. Fix it in phase 2, as every service now takes this path.

## Evidence

Measured with the definitions of all 11 shipped services (2,419 procedures) and a fake client:

| Measure | Result |
|---|---|
| Building every service | About 130 ms at connect |
| `import krpc` | About 130 ms with stubs, about 145 ms without |
| A call, excluding the network | About 89 ns built, 136 ns stub |
| Conformance with no stubs in the runfiles | 588 passed, 3 failed. The failures are test setup, see [conformance-python-no-stubs.md](../issues/conformance-python-no-stubs.md) |

The in-game tests have not run on built services, and exceptions were not prototyped.

## Plan

Each phase merges on its own. Milestone `ksp-v0.8.0`.

### Phase 1: Evidence and conformance

 * [conformance-python-no-stubs.md](../issues/conformance-python-no-stubs.md): make `:conformance-base` run with no stubs.
 * Run a subset of the in-game tests with `use_pregenerated_stubs=False`, covering `SpaceCenter`, `UI` and `Drawing`. Failures here change the plan.

### Phase 2: Client and clientgen

 * Generate the modules, and the lookup and comparison above. Regenerate the goldens.
 * Fix the testee's `is_service`, and remove the `test_exposed_members[services]` line from `expected-failures.txt`.
 * Build every service from `GetServices`, and remove what is listed under [What Goes](#what-goes).
 * Fix the member names that fail a connect.
 * Remove `:conformance-base` and the other base targets.
 * Native tests in `client/python/krpc/test`:
   * The definitions of an enumeration and a structure differing from the module, as conformance runs only the matching case for `TestService` and the no-module case for `ConformanceService`.
   * Each declaration's signature against the service built from the same definitions, as the drift test.
 * Update service tests and tools that call a static method on an imported class.
 * Changelog `client/python`: "**Breaking:** Remove `use_pregenerated_stubs`, as services are always built from the server's definitions (#NNN)".

### Phase 3: Docs

 * `python.rst`: replace "Service Stubs" with type checking, importing types, and what a mismatch does.
 * `client-design/python.rst`: replace "Pre-Generated and Dynamic Services". `client-design.rst`: the "Service stubs" column.
 * `extending/extending-other-services.rst` and `extending/clientgen.rst`: a mod's members work at run time, and generating declarations is only for type checking.

## Alternatives Considered

| Alternative | Why not |
|---|---|
| Keep stubs and `merge_service` | Three paths, and the defects above |
| Stubs with no fallback, `use_pregenerated_stubs=False` otherwise | A mod's extension members need the flag, which loses every type hint. Roughly 100 lines saved, with `WrappedClass` and `StaticMethod` staying |
| `.pyi` files only | No run time import, so `def f(mode=SASMode.prograde)` has no equivalent. This is the design #703 moved away from |
| Add a server's extra enumeration values to the generated class | Changes a class shared by every client, based on one connection |
| Declarations as base classes of built classes | Members the server lacks appear to exist |

## Open Questions

 * **Strict mode.** An opt-in warning at connect when the server's definitions differ from the modules. The client cannot read types back from the modules cheaply, so it needs a hash per service from `clientgen`, compared with a hash of the server's definitions. Left for later, as the program still runs correctly and only static checking is out of date.
 * **Lua.** [#1201](https://github.com/krpc/krpc/issues/1201) proposes annotations, then runtime stubs "as the Python stubs do". The JavaScript client's [phase 3](javascript-client.md) is already declarations plus built services. This design suggests dropping the second step for Lua.
