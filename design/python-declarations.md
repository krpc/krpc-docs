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
| A mod with its own service | Built at connect. Type checkers know it through the mod's client type, as [below](#a-mods-service) |
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
 * **`krpc/services/__init__.py` stays, reduced.** It declares the attributes of `Client` for type checkers, and imports the modules so they register. At run time a client has an attribute only for each service the server has.

### One class per type where the definitions match

A built enumeration is a different class from the imported one, so `dyn.prograde == imported.prograde` is false and `coerce_to` raises `ValueError`. At connect, the client therefore looks up each enumeration, structure and exception in the registry of generated classes:

| Definitions | Class used | Effect |
|---|---|---|
| Match | The generated class, shared by every client | `==`, `is` and `isinstance` work |
| Differ | One built for this client | The server's values all work. `==` and `coerce_to` compare service, name and value. `is` is false |
| Not registered | One built for this client | As for a mod with no module |

 * **Generated modules register their classes on import.** A module adds its enumerations, structures and exceptions to a registry in `krpc`, by service and name. A mod's module therefore works the same way as a shipped one. Import it before connecting, as a client looks only at classes registered by then.
 * **A later registration replaces an earlier one.** `import krpc` registers the shipped modules first, so a module a user generates for a newer server takes their place. A client keeps the classes it found at connect.
 * An enumeration matches on its names and values, and a structure on its field names in order. Field types always come from the server's definition, as they do today.
 * An exception matches on its name, as its definition holds nothing else. A server error then raises the generated class, so `except` works with an imported exception.
 * These classes hold no client, so sharing them brings back none of the stub defects.
 * A generated class is never altered to fit a server. That would change a class every client shares, based on one connection.
 * A structure already accepts any tuple of the right length.

### A mod's service

A mod's service is an attribute of the client, as a shipped one is. With no type checker, nothing more is needed:

```python
conn = krpc.connect()
conn.my_mod.get_mode()
```

Python has no declaration merging, so a mod's module cannot add `my_mod` to `krpc.Client`. Its module therefore declares a client type, and `connect` takes one:

```python
# mymod_services.py, generated by clientgen
class MyModClient(krpc.Client):
    my_mod: MyMod
```

```python
from mymod_services import MyModClient

conn = krpc.connect[MyModClient]()
conn.my_mod.get_mode()   # int
conn.space_center        # SpaceCenter
```

 * **`connect[T]` returns a client created as `T`.** `connect` and `connect_local` become objects whose `__getitem__` takes a subclass of `Client`. A plain call is unchanged and returns `Client`.
 * **Several mods take one class:** `class Conn(MyModClient, OtherClient): ...`, then `krpc.connect[Conn]()`. Python has no intersection type, so `connect[MyModClient, OtherClient]` cannot be typed.
 * **The client type holds only annotations.** The attributes come from `GetServices` at connect, as for every service.
 * Lua and TypeScript can extend `Client` from the mod's file, by a repeated `---@class` and by module augmentation. There, `conn.myMod` type checks with no user code.

### Static methods

The rule in [static-method-binding.md](static-method-binding.md) is unchanged: a static method takes its connection from the service object the class is reached through. A call through an object runs on the object's connection. Built classes already do both, and `test_static_method_connection` and `test_static_method_through_an_object_connection` pass on them. This replaces phase 2 of that doc, which fixes `StaticMethod` on the shared stub classes.

### Other clients

Lua and JavaScript take the same approach. Each builds its services at connect. Its generated modules hold real enumerations, structures and exceptions, where the language has them, and declare the classes and services.

 * **Lua**: annotations, then the importable types, in [lua-type-hints.md](../issues/lua-type-hints.md). Lua gets no runtime stubs.
 * **JavaScript**: [phase 3b](javascript-client.md#phase-3b-importable-types), on top of its declarations.

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

## Evidence

Measured with the definitions of all 11 shipped services (2,419 procedures) and a fake client:

| Measure | Result |
|---|---|
| Building every service | About 130 ms at connect |
| `import krpc` | About 130 ms with stubs, about 145 ms without |
| A call, excluding the network | About 89 ns built, 136 ns stub |
| Conformance with no stubs in the runfiles | 588 passed, 3 failed. The failures were test setup, fixed by [#1298](https://github.com/krpc/krpc/pull/1298), which gives 591 passed |

The in-game tests have not run on built services, and exceptions were not prototyped.

## Plan

Each phase merges on its own. Milestone `ksp-v0.8.0`.

### Phase 1: Evidence and conformance

 * [#1298](https://github.com/krpc/krpc/pull/1298), in review: make `:conformance-base` run with no stubs.
 * Run a subset of the in-game tests with `use_pregenerated_stubs=False`, covering `SpaceCenter`, `UI` and `Drawing`. Failures here change the plan.

### Phase 2: Client and clientgen

 * Generate the modules, with their registration and client type, and the lookup and comparison above.
 * `connect[T]` on each connect function. Regenerate the goldens.
 * Fix the testee's `is_service`, and remove the `test_exposed_members[services]` line from `expected-failures.txt`.
 * Build every service from `GetServices`, and remove what is listed under [What Goes](#what-goes).
 * Remove `:conformance-base` and the other base targets.
 * Native tests in `client/python/krpc/test`:
   * The definitions of an enumeration and a structure differing from the module, as conformance runs only the matching case for `TestService` and the no-module case for `ConformanceService`.
   * Each declaration's signature against the service built from the same definitions, as the drift test.
 * Update service tests and tools that call a static method on an imported class.
 * Changelog `client/python`: "**Breaking:** Remove `use_pregenerated_stubs`, as services are always built from the server's definitions (#NNN)".

### Phase 3: Docs

 * `python.rst`: replace "Service Stubs" with type checking, importing types, and what a mismatch does.
 * `client-design/python.rst`: replace "Pre-Generated and Dynamic Services". `client-design.rst`: the "Service stubs" column.
 * `extending/extending-other-services.rst` and `extending/clientgen.rst`: a mod's members work at run time, and a mod's generated module gives type hints and shared types when imported before connecting. `python.rst` shows `connect[T]`.

## Alternatives Considered

| Alternative | Why not |
|---|---|
| Keep stubs and `merge_service` | Three paths, and the defects above |
| Stubs with no fallback, `use_pregenerated_stubs=False` otherwise | A mod's extension members need the flag, which loses every type hint. Roughly 100 lines saved, with `WrappedClass` and `StaticMethod` staying |
| `.pyi` files only | No run time import, so `def f(mode=SASMode.prograde)` has no equivalent. This is the design #703 moved away from |
| Add a server's extra enumeration values to the generated class | Changes a class shared by every client, based on one connection |
| Declarations as base classes of built classes | Members the server lacks appear to exist |
| A list of the shipped modules for the lookup | A mod's module is never found, so its types differ from the client's |
| A typed accessor per service, `my_mod(conn)` | Two forms for a service, unless `conn.space_center` becomes `space_center(conn)` and breaks every script |
| `Client.__getattr__` returning `Any` | `conn.my_mod` type checks, with no hints for its members |
| Entry points, `krpc.services`, for a mod's module | Order no longer matters, but a mod must ship a package in place of one file |
| A warning at connect when the server's definitions differ from the modules, by a hash per service from `clientgen` | The program runs correctly, and only static checking is out of date |
