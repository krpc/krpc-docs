# Python: generated declarations and dynamic services

**Status:** in progress, for 0.8. Phase 1 in #1298, phase 2 in #1302, phase 2b in #1303 and #1304, and two phase 3 follow-ups in #1305 and #1306; the other follow-ups are open. Issue: [python-declarations.md](../issues/python-declarations.md), not yet filed.

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
| A mod with its own service | Built at connect. Type checkers know it through the mod's client type, as in [Client types](#client-types) |
| A mod adding members to a shipped class | The members exist at run time. Type checkers do not know them |
| A server of another version | Not supported. The services match the server, and type checkers see the client's version |

### Generated modules

`clientgen` writes one module per service, importable at run time. It has no `.pyi` beside it. Where the shipped modules live is under [Packages](#packages):

| Kind | In the module | At run time |
|---|---|---|
| Enumeration, structure, exception | Real class | Usable with no connection |
| Class, service | Declaration | Never instantiated |

A default argument needs no connection and no `TYPE_CHECKING` guard:

```python
from krpc.ksp.spacecenter import SASMode

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
 * **A module declares a client type, `<Service>Client`,** which is `krpc.Client` plus the one service. See [Client types](#client-types).
 * At run time a client has an attribute only for each service the server has.

### One class per type where the definitions match

A built enumeration is a different class from the imported one, so `dyn.prograde == imported.prograde` is false and `coerce_to` raises `ValueError`. At connect, the client therefore looks up each enumeration, structure and exception in the registry of generated classes:

| Definitions | Class used | Effect |
|---|---|---|
| Match | The generated class, shared by every client | `==`, `is` and `isinstance` work |
| Differ | One built for this client | The server's values all work. A generated value converts to the client's by its number. `==` and `is` are false |
| Not registered | One built for this client | As for a mod with no module |

 * **The client type picks the modules.** `connect[T]` looks first in the modules of the `<Service>Client` types in `T`'s MRO. The client type and the run time then use the same declarations, and a module generated for a newer server applies only to the connections typed with it.
 * **Imported modules are the fallback.** A generated module registers its classes on import, by service and name, and a later registration replaces an earlier one. A service outside the client type uses the registered classes. `import krpc` imports no generated module.
 * **Values go by number.** A generated enumeration value converts to the client's built value by its number, as the other clients send their compiled numbers. A client and a server of different releases are not supported, so a renumbered value may stand for another one. A structure converts from any tuple of the right length.
 * **`except` needs the shared class.** Python compares exception classes by identity, ignoring `__subclasscheck__`, so `except` with an imported exception class needs that module's class to be the client's.
 * An enumeration matches on its names and values, and a structure on its field names in order. Field types always come from the server's definition, as they do today.
 * An exception matches on its name and the builtin its mapped type derives from. A server error then raises the generated class, so `except` works with an imported exception.
 * These classes hold no client, so sharing them brings back none of the stub defects.
 * A generated class is never altered to fit a server. That would change a class every client shares, based on one connection.
 * A structure already accepts any tuple of the right length.

### Access

Every service the server defines is built at connect, and is the attribute `conn.<snake_case name>`. A service the server lacks is no attribute, so accessing it raises `AttributeError` naming the service. Members always follow the server, including those another mod adds to a shipped class. A generated module changes no member, only the types type checkers see and the classes of [shared types](#one-class-per-type-where-the-definitions-match).

The same holds for every service, whether its module ships with the client, comes from another package, replaces a shipped one, or does not exist.

### Client types

Python has no declaration merging, so a module cannot add its service to `krpc.Client`. A client type is therefore a combination of per-service client types:

| Name | Declares |
|---|---|
| `krpc.Client` | The client's methods. Any service is `Any` to type checkers |
| `<Service>Client`, one in each generated module | `krpc.Client` plus the one service |
| `krpc.ksp.KSPClient`, and later `krpc.ksa.KSAClient` | The core services and every service shipped for one game, combined as a user would combine them |
| `krpc.connect[T](...)`, `krpc.connect_local[T](...)` | A client created as `T` |
| `krpc.connect(...)` | A `krpc.ksp.KSPClient`. `krpc.connect[krpc.Client]()` gives the plain client |

Code with no client type, which most users write, is typed for KSP, as `krpc.connect()` connects with `KSPClient`:

```python
import krpc

conn = krpc.connect(name="Launch")
vessel = conn.space_center.active_vessel    # Vessel | None
```

Code for a mod names the services it uses:

```python
import krpc
from krpc.ksp import KSPClient
from mymod_krpc import MyModClient

class Conn(KSPClient, MyModClient):
    pass

conn = krpc.connect[Conn](name="Launch")
conn.space_center.active_vessel    # Vessel | None
conn.my_mod.get_mode()             # int

with krpc.connect[KSPClient]() as conn:    # __enter__ keeps the type
    ...
```

A function can ask for only the services it uses, as each `<Service>Client` acts as a capability:

```python
from krpc.ksp.spacecenter import SpaceCenterClient

def stage(conn: SpaceCenterClient) -> None:
    vessel = conn.space_center.active_vessel
    assert vessel is not None
    vessel.control.activate_next_stage()

stage(conn)    # any client type including SpaceCenter
```

 * **`krpc.Client.__getattr__` returns `Any`, for type checkers only.** A typed client inherits it, so a misspelled service on a typed client is not reported. Typing is secondary, and the alternative forces `connect[...]` on every user who runs a type checker.
 * **`krpc.Client` declares no service, not even `KRPC`.** After the [split](#packages) the base package cannot know the game's services. The core services, `KRPC` and `StdLib`, take client types like the others, so a module generated for a newer server replaces them the same way. A `krpc` declared on `Client` would make a newer `KRPCClient` an incompatible override.
 * **The client's own calls to `KRPC` go through `Client._krpc`**, a property typed with the shipped declaration.
 * **`connect()` with no client type connects with `KSPClient`.** It imports `krpc.ksp` on the first connect, so `import krpc` imports no generated module. A script, and every doc example, then type checks with no client type. With `Any` services, the doc examples' pyright check found no misspelled member.
 * **Follow-up: the default is KSP's.** A KSA program calling `krpc.connect()` gets the KSP types, and after the split the base package's `connect()` needs `krpc-ksp` installed. One option is a connect per game, such as `krpc.ksp.connect()` and `krpc.ksa.connect()`, with `krpc.connect()` returning a `krpc.Client`. See [Phase 3](#phase-3-follow-ups).
 * **Several modules take one class**, as Python has no intersection type, so `connect[MyModClient, OtherClient]` cannot be typed.
 * **A client type holds only annotations.** The attributes come from `GetServices` at connect.
 * Lua and TypeScript can extend `Client` from the mod's file, by a repeated `---@class` and by module augmentation. There, `conn.myMod` type checks with no user code.

### Third-party services

A mod's author generates its module and publishes it as an ordinary package, or a user generates it into a project:

```
krpc-clientgen python MyMod MyMod.json -o mymod_krpc/mymod.py
```

The module is used exactly as a shipped one. A module whose service uses another service's types imports that service's module. `--include SERVICE=MODULE` names its module path, and the shipped services have defaults:

```
krpc-clientgen python MyMod MyMod.json SpaceCenter.json --include Other=other_krpc.other -o mymod.py
```

### Replacing a shipped module

For a server newer than the client, generate the module of the changed service, and use its client type in place of the shipped one:

```python
from krpc.ksp.spacecenter import SpaceCenterClient
from krpc.ksp.drawing import DrawingClient
from my_project.ui import UIClient, MessagePosition    # generated for the newer server

class Conn(UIClient, SpaceCenterClient, DrawingClient):
    pass

conn = krpc.connect[Conn]()
conn.ui.message("Hello", position=MessagePosition.top_center)
```

 * **This is the third-party case**, with no rule of its own.
 * **A replacement cannot combine with `KSPClient`.** `class Conn(UIClient, KSPClient)` is a type error, as both bases declare `ui`. The user lists the services they use.
 * **The replacement's classes apply to its connections only**, as the client type picks the modules.

### Packages

The client is planned to split into a base package and a stub package per game. The paths are fixed now, so the split moves files between distributions and changes no import:

| Path | Now | After the split |
|---|---|---|
| `krpc`, `krpc.connect`, `krpc.Client` | `krpc` | `krpc` |
| `krpc.services.krpc`, `krpc.services.stdlib` | `krpc` | `krpc` |
| `krpc.ksp.spacecenter`, `krpc.ksp.ui`, `krpc.ksp.drawing`, and the other KSP services | `krpc` | `krpc-ksp` |
| `krpc.ksp.KSPClient` | `krpc` | `krpc-ksp` |
| `krpc.ksa.*`, `krpc.ksa.KSAClient` | none | `krpc-ksa` |

 * **The game's services move to `krpc.ksp`**, matching the planned package name. `krpc.services` keeps the services of the core, which every server has.
 * **`krpc.services` no longer declares a `Client`.** A file cannot come from two distributions, and the base package cannot know a game's services.
 * **`import krpc` imports no game module**, as the base package will not have one. The client type picks the modules, and `connect()` imports `krpc.ksp` on its first call.
 * `krpc.services.testservice` stays in the base package, for the client's tests.

### Corner cases

| Case | Behavior |
|---|---|
| The client type declares a service the server lacks | `AttributeError` on access, naming the service |
| The server's definition differs from the module | Members follow the server, types the module. The enumeration or structure is built, and a generated enumeration value converts by its number |
| Two bases of a client type declare one service | A type error. At run time the first in the MRO picks the module |
| Two connections typed differently | Each uses its own type's modules |
| A module imported after connecting | Its enumeration values convert by number. `==`, `is`, and `except` with its exception classes, do not hold |
| A service named as a `Client` member, such as `Close` or `Stream` | The [reserved names](protocol/service-definition-rules.md#reserved-names) keep services off them |
| A class named `<Service>Client` in its own service | Clashes with the client type. To reserve in the service definition rules, as a follow-up |

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
| In-game tests on built services | 686 passed, 0 failed: 17 `SpaceCenter` files, all of `UI` and `Drawing` |

Exceptions were not prototyped.

## Plan

Each phase merges on its own. Milestone `ksp-v0.8.0`.

### Phase 1: Evidence and conformance

 * Done: [#1298](https://github.com/krpc/krpc/pull/1298) makes `:conformance-base` run with no stubs.
 * Done: a subset of the in-game tests with `use_pregenerated_stubs=False`, covering `SpaceCenter`, `UI` and `Drawing`. All passed, so the plan stands.

### Phase 2: Client and clientgen

One pull request, with a commit per item. The stubs are the modules being replaced, so the items do not ship apart. The docs are in it too, as a change updates the pages it makes false.

 * Generate the modules, with their registration and client type, and the lookup and comparison above. Regenerate the goldens.
 * `connect[T]` on each connect function.
 * Fix the testee's `is_service`, and remove the `test_exposed_members[services]` line from `expected-failures.txt`.
 * Build every service from `GetServices`, and remove what is listed under [What Goes](#what-goes).
 * Remove `:conformance-base` and the other base targets.
 * Native tests in `client/python/krpc/test`:
   * The definitions of an enumeration and a structure differing from the module, as conformance runs only the matching case for `TestService` and the no-module case for `ConformanceService`.
   * Each declaration's signature against the service built from the same definitions, as the drift test.
 * Update service tests and tools that call a static method on an imported class.
 * Changelog `client/python`:
   * "**Breaking:** Remove `use_pregenerated_stubs`, as services are always built from the server's definitions (#NNN)"
   * "**Breaking:** Calling a static method on a class imported from `krpc.services` raises a `TypeError` (#NNN)"
   * "Add `connect[T]` and `connect_local[T]`, which connect with a client type a generated module declares, such as `krpc.connect[MyModClient]()` for a mod's service (#NNN)"

Docs:

 * `python.rst`: replace "Service Stubs" with type checking, importing types, and what a mismatch does.
 * `client-design/python.rst`: replace "Pre-Generated and Dynamic Services". `client-design.rst`: the "Service stubs" column.
 * `extending/extending-other-services.rst` and `extending/clientgen.rst`: a mod's members work at run time, and a mod's generated module gives type hints and shared types when imported before connecting. `python.rst` shows `connect[T]`.

### Phase 2b: Client types and packages

On the same pull request as phase 2, from its review, as phase 2 made `krpc.Client` declare every shipped service. A module generated for a newer shipped service then could not redeclare its attribute.

 * `krpc.Client` with only a `TYPE_CHECKING` `__getattr__` returning `Any`, and `KRPCClient` and `StdLibClient` among the bases of `KSPClient`. Remove `krpc/services/__init__.py`'s `Client`, and the eager import of the modules.
 * The KSP services' modules move to `krpc.ksp`, with `KSPClient` in `krpc/ksp/__init__.py`.
 * `connect[T]` picks the modules from `T`, then the registry.
 * `--include SERVICE=MODULE` for Python, with defaults for the shipped services. This also fixes a module's import of another mod's service.
 * `krpctest`'s connection type and the in-game tests import from `krpc.ksp`.
 * Docs: `getting-started.rst` and every example keep `krpc.connect()`, typed through `KSPClient`. `python.rst` gets one section on typing. `extending/clientgen.rst` covers `--include` for Python.
 * Changelog `client/python`:
   * "**Breaking:** Move the KSP services' modules from `krpc.services` to `krpc.ksp` (#NNN)"
   * No entry for `krpc.connect()`, which stays typed with the KSP services through `KSPClient`
 * From the branch's review: enumeration values convert by number in place of by name, and `krpc.connect()` connects with `KSPClient` in place of a `krpc.Client` with `Any` services.
 * From the third review: `krpc.Client` declares no `krpc`, so the core services are treated as the others.

### Phase 3: Follow-ups

Each a pull request stacked on phase 2, merged in turn.

 * Done: [#1306](https://github.com/krpc/krpc/pull/1306). Type the function compiler's expressions. The `KRPC.Expression` declaration is typed, unlike the stub's `StaticMethod`, which shows the places where a value was looser than the call it reached.
 * Run pyright on the generated modules, which no check covers, so that a module a user generates type checks.
 * Reserve `<Service>Client` as a type name in the service definition rules.
 * `krpc-clientgen python --bundle`, to generate a combined client type with a set of modules, as for a whole newer server.
 * A connect per game, or another fix for `krpc.connect()` defaulting to `KSPClient`, before the KSA client types and the package split. See [Client types](#client-types).
 * Done: [#1305](https://github.com/krpc/krpc/pull/1305). Conformance: split a `definitions` profile out of `dynamic`, for building the services at connect, and add a `declarations` profile for the generated types. Python has both, and Lua takes `declarations` with [lua-type-hints.md](../issues/lua-type-hints.md).

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
| `Client.__getattr__` returning `Any` as the only typing for a mod | `conn.my_mod` type checks, with no hints for its members. Kept as the fallback for an undeclared service |
| `krpc.Client` declaring every shipped service | The base package cannot know them after the split, and a newer module for a shipped service then cannot redeclare its attribute |
| A `type: ignore` on the generated client type's attribute | Moves the error into the user's class as soon as it combines two client types |
| `.pyi` overrides in a stub path, to replace a shipped module | Type checkers see the newer types, while the run time imports the older classes |
| Global import order to pick the modules | A replacement module applies to every connection, and the result depends on what was imported first |
| Entry points, `krpc.services`, for a mod's module | A mod must ship a package in place of one file. The client type picking the modules makes order matter little |
| Enumeration values that compare, hash and convert by name | Serves a client and a server of different releases, which are not supported. A value inside a collection still went by number, so a full version converts every element |
| `krpc.connect()` returning a `krpc.Client` with `Any` services | Scripts and the doc examples lose type checking, which then catches no misspelled member |
| A warning at connect when the server's definitions differ from the modules, by a hash per service from `clientgen` | The program runs correctly, and only static checking is out of date |
