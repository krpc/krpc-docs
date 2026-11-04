# Client name collisions

**Status:** proposal (2026-10-31). Issue: [#1237](https://github.com/krpc/krpc/issues/1237).

## Problem

Each client maps a service's member names to its own conventions. Two members with distinct
procedure names can map to one client name:

| Client | Property `Foo` | Method `Foo` | Clashes with property `Foo` |
| --- | --- | --- | --- |
| Python, Lua | `foo` | `foo` | method `Foo` |
| C# | `Foo` | `Foo` | method `Foo` |
| C++ | `foo()`, `set_foo(v)` | `foo` | methods `Foo`, `SetFoo` |
| Java | `getFoo()`, `setFoo(v)` | `foo` | methods `GetFoo`, `SetFoo` |
| C-nano | `..._Foo`, `..._set_Foo` | `..._Foo` | method `Foo` |
| gRPC style (hypothetical) | `GetFoo`, `SetFoo` | `Foo` | methods `GetFoo`, `SetFoo` |

Snake case adds another merge: `RCSEnabled` and `RcsEnabled` both become `rcs_enabled`.

The scanner only rejects duplicate procedure names. A method `Foo` beside a property `Foo` cannot
come from one C# class. An [extension member](extension-members.md) can still add one.

**One collision exists today.** Every bundled service was checked against every client's mapping.
The only clashes are in `SpaceCenter.ConfigNode`, released in 0.6.0:

| Method | Property | Java names |
| --- | --- | --- |
| `GetValues(name)` | `Values` | `getValues(String)`, `getValues()` |
| `GetNodes(name)` | `Nodes` | `getNodes(String)`, `getNodes()` |

Java compiles these as overloads. A clashing method with no parameters would not compile, and a
client without overloading cannot generate these at all.

**Renaming per client breaks stability.** A generator could rename the second member of a clashing
pair. The renamed member then depends on what else is in the scope. Adding a property `Foo` would
rename an existing `GetFoo()` in Java, which breaks existing code. A new client must also never force
a service rename that breaks the other clients.

## Design

A fixed, language-neutral rule on service definitions, checked by the scanner. Client generators
only use mappings that the rule keeps unique.

### The rule

* **Each member reserves keys.** A method, static method, enumeration value or struct field
  reserves its name. A property reserves `Foo`, `GetFoo`, `SetFoo` and `IsFoo`.
* **Keys compare case-insensitively.** kRPC names contain no `_`, which separates the parts of a
  procedure name. Folding case therefore also covers every snake case and camel case merge.
* **Two members of one scope sharing a key clash.**

| Scope | Members |
| --- | --- |
| Service | Its procedures and properties |
| Class | Its methods, static methods and properties, together |
| Enumeration | Its values |
| Struct | Its fields |

`IsFoo` is reserved now, for a future client with Java bean style boolean getters. Reserving it
later would be the retroactive break this design avoids. No current member uses it.

Types are outside the rule. A property `Camera` beside a class `Camera` is common, with 12 pairs in
the bundled services. Clients keep types and members apart, as below.

### The client contract

A generator may only:

* change case, and insert separators between words;
* prefix a property accessor with `get`, `set` or `is`, in any case;
* escape a keyword with a suffix containing `_`, e.g. `in_`. Source names never contain `_`, so an
  escaped name cannot clash.

It must also:

* **Keep types apart from members**, e.g. by case (Python `Camera` vs `camera`), by suffix (C-nano
  `_t`) or by namespace (C# and Java).
* **Keep scopes apart.** A class member and a service member never share a client namespace. A
  client that flattens scopes into one namespace (one gRPC service, C-nano functions) keeps the
  class name in the member name, and a separator the source names cannot contain. The KSA gRPC
  prototype's `Vehicle_get_Name` is the form, from the procedure name.

A client whose conventions do not fit this contract builds its names from procedure names, which
are unique by construction.

Every current client fits the contract.

### Checks

| Where | Check | Result |
| --- | --- | --- |
| Scanner (`core`) | The rule, per scope, including extension members | Warning in 0.8, error from 1.0 |
| clientgen | The generated names, per scope, are unique | Build failure |
| clientgen test | A test service with the clashes the rule allows to pass, e.g. a property `Foo` beside a type `Foo` | Generates and compiles in every client |

**A warning, then an error.** Under [service and mod errors](../server/service-and-mod-errors.md) an
error disables both members, in every client. A third-party mod that loads today would lose members
for a problem in one client. Version 1.0 makes it an error, as a breaking release.

**A clash with a deprecated member is exempt.** It gives an author a migration path: deprecate the
clashing member, add a renamed one, and the warning goes. clientgen omits the deprecated member of
an exempt pair only where the generated names collide. An existing client keeps generating both,
as its names do not collide, so its users see no change.

**Extension members.** The extension clash check uses the same keys. The class keeps its own member,
as for duplicate names in [service and mod errors](../server/service-and-mod-errors.md).

### `ConfigNode`

`GetValues` and `GetNodes` are deprecated, replaced by `FindValues(name)` and `FindNodes(name)`.
The deprecated pair is exempt, and is removed with the other 1.0 removals.

## Phases

Each phase merges on its own.

1. **Rule and contract.** The scanner check as a warning, extension members included. The rule in
   `doc/src/extending/types.rst` for service authors. The client contract in the client
   specification.
2. **`ConfigNode`.** `FindValues` and `FindNodes`, with the old methods deprecated.
3. **clientgen check.** The per-scope uniqueness check and the test service.
4. **1.0.** The warning becomes an error, and the deprecated `ConfigNode` methods are removed.

## Rejected

| Option | Why not |
| --- | --- |
| Renaming per client, on a clash | Adding a member renames an existing one, as above |
| Per-language name overrides on the attributes | Services would carry knowledge of every client, and a new client would need edits to existing services |
| Types and members in one scope | Rejects 12 existing property and type pairs, for no client that needs it |
| An error from 0.8 | Disables members of mods that load today |
