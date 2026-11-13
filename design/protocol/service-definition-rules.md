# Service definition rules

**Status:** partly done. The identifier, shape, duplicate and id rules are implemented. The member
key rule is a proposal, [#1237](https://github.com/krpc/krpc/issues/1237). The service and type name
rules are done, [PR #1324](https://github.com/krpc/krpc/pull/1324) and
[PR #1325](https://github.com/krpc/krpc/pull/1325). The rules for parameters
and enumeration values are a proposal with no PR yet
([issue](../../issues/clientgen-qualified-names.md)).

What the scanner accepts in a service definition, and why. Clients name things after these rules and
may assume them, see [client naming](client-naming.md). A definition that breaks a rule is left out
as [partial loading](../server/partial-loading.md) describes. The problem is reported as
[problem reporting](../server/problem-reporting.md) describes.

| Rule | State |
| --- | --- |
| [Identifiers](#identifiers) for services, types, members and fields | Implemented |
| [Shapes](#shapes): visibility, nesting, types | Implemented |
| [Exact duplicates](#exact-duplicates) within a kind | Implemented |
| [Ids](#ids), hashed or set by hand | Implemented, [PR #1265](https://github.com/krpc/krpc/pull/1265) |
| [Member keys](#member-keys): case-insensitive, with accessor keys | Proposal, #1237. The `ConfigNode` clashes are removed ([PR #1261](https://github.com/krpc/krpc/pull/1261), [PR #1273](https://github.com/krpc/krpc/pull/1273)) |
| [Helper keys](#helper-keys) for the C++ `_stream` and `_call` functions | Proposal |
| [Service and type names](#service-and-type-names) unique case-insensitively | Implemented. Type names with type ids, phase E0 of [client-errors.md](../client-errors.md#type-ids), [PR #1324](https://github.com/krpc/krpc/pull/1324). Service names, types named as their service, and one class per service, [PR #1325](https://github.com/krpc/krpc/pull/1325) |
| [Type ids](#ids), hashed or set by hand | Implemented, phase E0 of [client-errors.md](../client-errors.md#type-ids), [PR #1324](https://github.com/krpc/krpc/pull/1324) |
| [Parameters and enumeration values](#parameters-and-enumeration-values) | Proposal |

## What the rules guarantee

A clash between a service and a client can't be ruled out entirely. A new client, or a new feature
of an existing one, brings names that can't be predicted today. The rules therefore rule out one
kind of clash, and leave the other to the clients:

| Clash | Example | Kept apart by |
| --- | --- | --- |
| Two names of one definition merge under the [contract](client-naming.md#the-contract)'s conversions | `RCSEnabled` and `RcsEnabled`, `GetValues` and `Values` | These rules. The contract bounds what a generator may do, so the scanner can rule these out |
| A name of a definition meets a client's own name | A type `SpaceCenterClient`, a service `Close`, a member `Bind` | The client, as [client reserved names](client-reserved-names.md) describes. The scanner keeps no list of client names |

Client names use a form a definition can't produce, such as a leading `_`, or the client escapes the
definition's name. An escape depends on the client release alone, never on another member, unlike
the rejected [renaming on a clash](#rejected). A clash that neither covers is a documented limitation
of that client.

## Identifiers

A service, class, enumeration, structure, exception, procedure, property, method and structure field
name matches `^[A-Z][A-Za-z0-9]*$` (`TypeUtils.ValidateIdentifier`). Parameter names and enumeration
value names are not checked today.

**The rules below rest on this.** A name with no `_` keeps every case conversion reversible up to
case. Folding case is then enough to tell when two names convert to one client name. A procedure name
uses `_` to join its parts, e.g. `Vessel_get_Name`, so a part never contains one.

## Shapes

`TypeUtils` checks each kind on its own terms:

| Kind | Rule |
| --- | --- |
| Service | A public static class with `KRPCService`, not nested in another service. One class declares each service |
| Procedure, property | Public static, declared in a service |
| Class, exception | A public non-static class, nested in its service unless it names the service in its attribute |
| Enumeration | A public enum over `int`, placed as a class is |
| Structure | A public non-generic value type, placed as a class is, with at least one field. It does not contain itself |
| Method, class property | Public, declared in the class or a base of it |
| Extension member | A public static extension method of a kRPC class, see [extension members](extension-members.md) |
| Parameter, return value | A valid kRPC type. A stream or event only where [internal members](internal-members-and-handles.md) allow |

## Exact duplicates

Two procedures, classes, enumerations, structures or exceptions of one service with the same name
are an error. The check runs within each kind, so a class and an enumeration of one name pass it.
[Service and type names](#service-and-type-names) closes that gap.

## Ids

A service or procedure id that is 0, or shared by two of them, is a scanner error. Explicit service
ids 1 to 255 are reserved for the services that ship with kRPC. See
[procedure ids](procedure-ids.md#collisions).

The classes, enumerations, structures and exceptions of a service share a second id space, by the
same rule, with the same error. See [type ids](../client-errors.md#type-ids).

## Member keys

From #1237. Each member reserves keys, and two members of one scope that share a key clash:

* A method, static method, enumeration value or structure field reserves its name.
* A property `Foo` reserves `Foo`, `GetFoo` and `SetFoo`.
* Keys compare case-insensitively.

| Scope | Members |
| --- | --- |
| Service | Its procedures and properties |
| Class | Its methods, static methods and properties, together |
| Enumeration | Its values |
| Structure | Its fields |

This closes every case merge, e.g. `RCSEnabled` and `RcsEnabled` both becoming `rcs_enabled`, and
every accessor clash, e.g. a method `GetValues` beside a property `Values` both becoming Java's
`getValues`. The keys cover the accessors of the clients that ship. A future client with Java bean
boolean getters, `isFoo`, escapes a clash with a method `IsFoo`.

Types are outside this rule. A property `Camera` beside a class `Camera` is common, with 12 pairs in
the bundled services, and every client keeps types and members apart.

**`ConfigNode`.** The one clash in the bundled services was `GetValues(name)` and `GetNodes(name)`
beside the properties `Values` and `Nodes`. `FindValues` and `FindNodes` replace them
([PR #1261](https://github.com/krpc/krpc/pull/1261)), and the old methods are removed with no
deprecation cycle ([PR #1273](https://github.com/krpc/krpc/pull/1273)).

## Helper keys

C++ generates `foo_stream` and `foo_call` beside each member `foo`, and `set_foo_call` beside each
property setter. A member `FooStream` beside a member `Foo` therefore clashes. The member key rule
gains:

* A method, static method or property `Foo` also reserves `FooStream` and `FooCall`.
* A property `Foo` also reserves `SetFooCall`.

The rule is C++ specific, unlike the rest of the member keys. The alternative, a helper name no
member can take, renames the public `_stream` and `_call` functions.

Helper keys cover only the C++ helpers that ship. A later client name is kept apart by the client,
see [what the rules guarantee](#what-the-rules-guarantee). For example,
[static method binding](../static-method-binding.md) (#1195) plans a static method `Bind` and a nested
class `Bound` in some clients, and those clients escape a member of either name.

## Service and type names

* **Service names are unique, compared case-insensitively.** `Foo` and `FOO` would share the Python
  module `krpc.services.foo`, the C++ and C-nano header name, the C-nano `KRPC_FOO_` constants, and
  the Python and Lua attribute `conn.foo`.
* **One class declares each service.** Merging the classes that declared one name has failed since
  service ids became a hash of the name, as both classes take one id and the scan reports a clash.
  With different ids, the service took the id and game scene of the class scanned first.
* **The classes, enumerations, structures and exceptions of a service are unique together, compared
  case-insensitively.** Enumerations `Mode` and `MODE` would share the C-nano `KRPC_S_MODE_`
  constants, and a class and an enumeration of one name would share a C# namespace.
* **No type is named as its service.** C++ and Java reject a nested class named as the class that
  holds it, and Python replaces the type with the service class.

## Parameters and enumeration values

* **A parameter name matches `^[a-z][A-Za-z0-9]*$`.** The parameters of a procedure are unique,
  compared case-insensitively. `fooBar` and `FooBar` would both become C++, Python and Lua
  `foo_bar`, and Java `fooBar`. The instance parameter of a class member keeps the
  name `this`, which the scanner gives it.
* **An enumeration value name matches the identifier rule.** A value `Foo_` would become Java `FOO`
  beside a value `Foo`, as the Java client strips the `_` it adds to a keyword.

Every parameter and value in the bundled and test services already meets both.

## Checks

| Where | Check | Result |
| --- | --- | --- |
| Scanner (`core`) | Every rule, extension members included | Left out, see [partial loading](../server/partial-loading.md) |
| `tools/ServiceDefinitions` | Every rule, as the scanner with no error list | Build failure, naming both members |
| clientgen | The member and helper keys | Build failure, naming both members |
| clientgen test | `TestService` members named after the names the clients escape, and the clashes the rules allow, e.g. a property `Foo` beside a type `Foo` | Generates and compiles in every client |

**No deprecation exemption, and no warning period.** A clash is a bug that should never ship. A
third-party mod with one loses those members at once. A clash with a client's own name is the
client's to fix, in a client release. Every bundled and test service meets every
rule above, checked 2026-11-05 against the service definitions.

## Phases

Each phase merges on its own.

1. **`ConfigNode`.** Done, PR #1261 and PR #1273.
2. **Member keys** (#1237): the scanner check, the rule in `doc/src/extending/types.rst`, and the
   [client contract](client-naming.md#the-contract) in the client specification.
3. **Service and type names, parameters and enumeration values, helper keys.** Scanner checks and
   extending docs.
4. **Tool checks.** `ServiceDefinitions` and clientgen, and the test service.

The escapes for client names are client work, in
[client name escapes](../../issues/client-name-escapes.md).

## Rejected

| Option | Why not |
| --- | --- |
| Renaming per client, on a clash | Adding a member renames an existing one, e.g. a new property `Foo` renames Java's `getFoo()` |
| Reserving each name a client uses, in the scanner | No bound: each new client or client feature adds names, and each addition rejects a service that loaded before. Python's `<Service>Client`, `Bind` and `Bound`, and `IsFoo` were already queued |
| Per-language name overrides on the attributes | Services would carry knowledge of every client, and a new client would need edits to existing services |
| Types and members in one scope | Rejects 12 existing property and type pairs, for no client that needs it |
| A warning in 0.8, an error from 1.0, with deprecated members exempt | Each client needs a rule for the exempt pairs, for a bug that should never ship |
