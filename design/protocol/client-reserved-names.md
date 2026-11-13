# Client reserved names

**Status:** implemented in every client, with no PR yet (2026-11-05). Keyword escaping predates it.
The [service and type escapes](#service-and-type-escapes-proposal) are a proposal,
[client name escapes](../../issues/client-name-escapes.md).

How each client keeps a name from a service definition clear of the names the client itself uses:
its language's keywords, the library and standard types it names, the members of its base classes,
and the locals of its generated code. Names from two parts of a service definition are kept apart by
[client naming](client-naming.md).

## Approach

Two techniques, chosen per name:

* **Qualify the client's names.** A library, standard or runtime type is written from a root no
  service name can shadow, e.g. C++ `::std::string`. This changes no name a user sees.
* **Escape the service's name.** A service, type, member or parameter whose converted name the
  client cannot qualify, such as a keyword, a base class method or a local, takes a trailing `_`,
  e.g. `class_`.
  No source name ends in `_`, so an escaped name never meets another
  ([identifiers](service-definition-rules.md#identifiers)).

The scanner keeps no list of client names, as a new client or client feature can always add one.
See [what the rules guarantee](service-definition-rules.md#what-the-rules-guarantee). A new client
name takes a leading `_` where it can, and otherwise the client escapes the definition's name. A clash
that neither covers is a documented limitation, as [platform macros](#platform-macros) are.

Qualifying is preferred, as escaping renames a member. Parameters escape against the locals and
helper parameters of a generated function, and members against the client's base classes. An escape
renames a member only where the name failed or misbehaved before, apart from Java, which escapes its
reserved names in every scope. No bundled service has any of them.

The docs name an escaped member as the code does, through the same `Language` method. Parameter
names in docgen are not escaped yet, so the docs show `from` where Python takes `from_`.

## Per client

### C++

| Name | Technique |
| --- | --- |
| Library and standard types | Written from the global namespace: `::krpc::Client`, `::krpc::Service`, `::krpc::Object`, `::krpc::encoder::`, `::std::string`, `::std::int32_t` |
| Another service's type, and the current one's | In full, `::krpc::services::SpaceCenter::Vessel`, so a nested class named after a service cannot shadow it |
| Keywords | Escaped |
| Parameters named `_args`, `_data`, `_result`, `_client`, `client` | Escaped. These are the locals of a generated function and the client a static method takes |
| A structure field named `other` | Compared through `this->`, so it does not read as the argument |

The docs keep the short spellings, `std::string`, through an unqualified `CppLanguage`. The generated
headers grow by 10 to 17%.

### C-nano

Every generated name starts `krpc_<Service>_` or `KRPC_<SERVICE>_`, so only a function's own names
are at risk.

| Name | Technique |
| --- | --- |
| Keywords of C and C++ | Escaped |
| Parameters named `_call`, `_arguments`, `_result`, `_stream`, `connection`, `instance`, `returnValue`, `returnValueIsNull`, `NULL`, `size_t`, `int32_t`, `int64_t`, `uint32_t`, `uint64_t` | Escaped. The locals and added parameters of a generated function, and the standard names it uses |
| Parameters starting `krpc_`, `KRPC_`, `pb_` or `PB_` | Escaped, as the library and nanopb names the function body calls |

### C#

| Name | Technique |
| --- | --- |
| Library and `System` types | `global::` throughout, and no `using` directives |
| The type specifications class | `_TypeSpecs`, a name no service type can take |
| Keywords | Escaped |
| Members named `Equals`, `GetHashCode`, `GetType`, `ToString`, `MemberwiseClone`, `Finalize`, `ReferenceEquals`, `CompareTo`, `GetObjectId`, `AddExceptionTypes` | Escaped, as members of `object`, `RemoteObject`, a structure or the service class |
| A member named as the type that holds it, e.g. a procedure `Service` | Escaped, as C# allows no such member |
| Parameters named `_args`, `_result`, `connection`, `nameof` | Escaped |
| Structure constructor parameters | The field name in lower camel case, escaped, so a field `Class` gives `class_` |
| Types named `Service`, `ExtensionMethods` | To escape, see [service and type escapes](#service-and-type-escapes-proposal) |

### Java

| Name | Technique |
| --- | --- |
| Library and `java.lang` types | In full: `krpc.client.Connection`, `com.google.protobuf.ByteString`, `java.lang.String`, `@java.lang.Override`. No imports |
| Keywords | Escaped |
| Members named `clone`, `compareTo`, `equals`, `finalize`, `getClass`, `getObjectId`, `hashCode`, `notify`, `notifyAll`, `toString`, `wait` | Escaped, as methods of `java.lang.Object` and the client's base classes |
| Any name `com`, `java`, `krpc`, `org` | Escaped. A variable of a package's name obscures the package in every qualified name |
| Parameters named `_args`, `_data`, `connection` | Escaped |
| Structure fields named `other`, `result` | Compared through `this.` |

### Python

The stubs and the client's run-time service objects use the same names.

| Name | Technique |
| --- | --- |
| Imported names: `List`, `Optional`, `NamedTuple`, `Event`, `DocEnum`, `ClassBase`, `Client` and the rest | Imported under private aliases, `_List`, `_Event` |
| Builtins evaluated in a class body: annotations, `property`, `float("nan")`, `set()`, exception bases | Through `_builtins`, e.g. `@_builtins.property`, `_builtins.RuntimeError` |
| `krpc.limits` in default arguments | Through the alias `_limits` |
| Keywords | Escaped |
| Parameters named `self`, `cls` | Escaped, in the stubs and in the functions the client builds at run time |
| The names a run-time function is evaluated with | `Invoke`, `ParamTypes`, `ReturnType`, `DefaultArgument`. A snake case parameter has no upper case letter |

Members are not escaped. `KRPC.Type.int()`, `float()`, `bool()` and `Expression.set()` are shipped
names, and qualifying the builtins keeps them working.

An enumeration value named `mro` is not handled yet: `Enum` rejects the name. The stubs and the
run-time client should escape it.

### Lua

| Name | Technique |
| --- | --- |
| Members named `is_a`, `class_of` | Escaped. The client checks argument types through these Penlight class methods |
| Parameters | Every parameter takes a trailing `_`, so none meets a name the generated function uses |

A member named `cast` or `catch` replaces those Penlight methods on its class. The client calls
neither, and `KRPC.Expression.cast` is a shipped name, so they are not escaped.

## Service and type escapes (proposal)

Names a client puts beside a service or a type, where the client's name is public and fixed. Today
these clashes break the client. Each escape gives the definition's name a trailing `_`.

| Client | Name | Clash | Escaped as |
| --- | --- | --- | --- |
| Python, Lua | A service named as a public client member: `Close`, `Stream`, `AddStream`, `AddEvent`, `Run`, `Compile`, `GetCall`, `StreamUpdateCondition`, `WaitForStreamUpdate`, `AddStreamUpdateCallback`, `RemoveStreamUpdateCallback` | The service replaces the member on the client object | `conn.close_` |
| Python | A type `<Service>Client` in its own service, e.g. `SpaceCenterClient` | The generated module's [client type](../python-declarations.md#client-types) | `SpaceCenterClient_` |
| C# | A service named `Dispose` | `IConnection.Dispose` wins over the extension method | `conn.Dispose_()` |
| C# | A type named `Service` or `ExtensionMethods` | The classes generated in each service's namespace | `Service_` |
| C-nano | A service named `Error`, `Callback`, `Return`, `Bytes`, `Size` or `Type` | An enumeration value constant `KRPC_<SERVICE>_<ENUM>_<VALUE>` matches a library name, e.g. `KRPC_ERROR_CONNECTION_FAILED` | `KRPC_ERROR__<ENUM>_<VALUE>` |
| C#, C++, Java | A member `Bind` or `Bound`, once [static method binding](../static-method-binding.md) lands | The bound form's static method and nested class | `Bind_`, `bind_` |

A client that adds a public name beside a service or type adds a row here.

## Platform macros

An object-like macro rewrites any C or C++ identifier, after every technique above. `windows.h`
defines `near`, `far` and `interface`, and Arduino defines `HIGH`, `LOW` and `PI`. A member named
after one fails to compile on that platform. Neither the scanner nor clientgen can know every
platform's macros, so this is left open.

## Tests

`tools/TestServer/src/TestServiceNames.cs` adds `TestService` classes named after the library types,
members named after the base class methods and builtins, and methods whose parameters are named
after every reserved local. Each client's build compiles the generated code, the conformance testees
included. A krpctools test runs the generated Python module, whose class bodies run on import. Each
client's change was checked against the old generator, which fails on the fixtures.
