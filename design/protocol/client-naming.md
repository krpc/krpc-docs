# Client naming

**Status:** the mappings ship in every client. Naming another service's type in full in every client,
and the leading `_` on the C# and Python helpers, are implemented with no PR yet. The contract is a
proposal with the member key rule, [#1237](https://github.com/krpc/krpc/issues/1237).

How each client turns the names in a service definition into its own, and why two names the
[service definition rules](service-definition-rules.md) allow never become one. Clashes with a
client's own names, such as keywords and library types, are in
[client reserved names](client-reserved-names.md).

## Mappings

| Definition | C# | C++ | C-nano | Java | Python | Lua |
| --- | --- | --- | --- | --- | --- | --- |
| Service `SpaceCenter` | namespace `KRPC.Client.Services.SpaceCenter`, class `Service`, `conn.SpaceCenter()` | class `krpc::services::SpaceCenter`, header `space_center.hpp` | prefix `krpc_SpaceCenter_`, header `space_center.h` | class `krpc.client.services.SpaceCenter` | module `krpc.services.spacecenter`, `conn.space_center` | `conn.space_center` |
| Type `Vessel` | `Vessel` in the namespace | nested `Vessel` | `krpc_SpaceCenter_Vessel_t` | nested `Vessel` | `Vessel` in the module | `SpaceCenter.Vessel` |
| Procedure or method `WarpTo` | `WarpTo` | `warp_to` | `krpc_SpaceCenter_WarpTo`, `krpc_SpaceCenter_Vessel_WarpTo` | `warpTo` | `warp_to` | `warp_to` |
| Property `Name` | property `Name` | `name()`, `set_name()` | `..._Name`, `..._set_Name` | `getName()`, `setName()` | property `name` | property `name`, stored as `get_name`, `set_name` |
| Enumeration value `Docked` | `Docked` | `docked` | `KRPC_SPACECENTER_<ENUM>_DOCKED` | `DOCKED` | `docked` | `docked` |
| Structure field `Seconds` | property `Seconds` | `seconds` | member `seconds` | field `seconds`, `getSeconds()` | `seconds` | `seconds` |
| Parameter `referenceFrame` | `referenceFrame` | `reference_frame` | `referenceFrame` | `referenceFrame` | `reference_frame` | positional, `reference_frame_` |

Generated helpers beside the members:

| Client | Helper | Kept apart by |
| --- | --- | --- |
| C++ | `warp_to_stream`, `warp_to_call`, `set_name_call` | The [helper keys](service-definition-rules.md#helper-keys) |
| Python | `_build_call__warp_to`, `_return_type__warp_to`, `_build_call_set__name` | A leading `_`, which no member name has |
| C# | `_TypeSpecs`, internal | A leading `_` |
| Java | `_Types`, nested | A leading `_` |
| Python | `_Definitions`, `_type_Vessel` for type checkers | A leading `_` |

## The contract

From #1237. A generator may only:

* change case, and insert separators between words;
* prefix a property accessor with `get`, `set` or `is`, in any case;
* add a suffix containing `_` to a keyword or a name the client reserves, e.g. `in_`. Source names
  never contain `_`, so an escaped name cannot clash with another;
* add a helper name the [service definition rules](service-definition-rules.md) reserve, or one with
  a leading `_`.

It must also:

* **Keep types apart from members**, by case (Python `Camera` and `camera`), by suffix (C-nano
  `_t`) or by namespace (C# and Java).
* **Keep scopes apart.** A class member and a service member never share a client namespace. A
  client that flattens scopes into one namespace, such as C-nano, keeps the class name in the member
  name, with a separator the source names cannot contain.
* **Name another service's type in full**, so that a type of the current service cannot shadow it.
  C++ writes `::krpc::services::SpaceCenter::Vessel`, Java `krpc.client.services.SpaceCenter.Vessel`,
  C# `global::KRPC.Client.Services.SpaceCenter.Vessel`, and Python an aliased module
  `_service_spacecenter.Vessel`.

A client whose conventions do not fit builds its names from procedure names, which are unique by
construction.

## Why the names stay apart

| Merge | Example | Prevented by |
| --- | --- | --- |
| Case conversion | `RCSEnabled` and `RcsEnabled` become `rcs_enabled` | [Member keys](service-definition-rules.md#member-keys), and the type and parameter rules, compare case-insensitively |
| Property accessor | `GetValues` beside `Values` becomes `getValues` | Member keys: a property reserves `GetFoo`, `SetFoo`, `IsFoo` |
| C++ helper | `FooStream` beside `Foo` becomes `foo_stream` | [Helper keys](service-definition-rules.md#helper-keys) |
| Escape suffix | `Class` becomes `class_`. No source name ends in `_` | The identifier rule |
| Java enumeration constants | `Foo_` and `Foo` become `FOO` | The [enumeration value rule](service-definition-rules.md#parameters-and-enumeration-values) |
| File and module names | `SpaceCenter` and `Spacecenter` become `spacecenter` | Service names compare case-insensitively |
| Type and member | Class `Camera` beside property `Camera` | The contract: types and members kept apart |
| Type and service | Class `Foo` in service `Foo` | The [type name rule](service-definition-rules.md#service-and-type-names) |

## Client objects

Some clients put services on an object of their own, beside its members:

| Client | Service reached as | Clash |
| --- | --- | --- |
| Python | `conn.space_center`, an attribute of `Client` | A service named as a public `Client` member, e.g. `Stream` replaces `conn.stream` |
| Lua | `conn.space_center`, a field of the client | `Close` replaces `conn:close` |
| C# | `conn.SpaceCenter()`, an extension method of `IConnection` | `Dispose`: the instance method wins |
| C++, C-nano, Java | A constructor, function prefix or `newInstance` | None |

The [reserved names](service-definition-rules.md#reserved-names) keep services off these members.

The Python client does not check this itself. `Client._load_services` sets each service with
`setattr(self, snake_case(service.name), ...)`, so a server whose definitions break the rule, such
as a service named `Close` or `Stream`, replaces the `Client` method of that name.

## Tests

The `TestService` fixtures in `tools/TestServer/src/TestServiceNames.cs` hold names each client
reserves. Every client build compiles them, and a krpctools test runs the generated Python module.
The goldens in `tools/krpctools/krpctools/test` show each client's names for them.
