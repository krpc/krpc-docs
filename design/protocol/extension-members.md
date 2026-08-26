# Extension members for other services' classes (issues #305 + #900)

**Status:** in progress — built on a branch, not yet opened as a PR. Written 2026-07-03,
revised 2026-08-22 against `krpc` at version 0.7.0.

Everything below landed as designed, with four differences:

- **The scanner pass covers every `[KRPCMethod]`/`[KRPCProperty]` method in a public
  static class, not only extension methods.** A member that forgets `this` is then a
  scanner error rather than silently ignored, which is the more useful outcome for the
  mistake most likely to be made. Classes annotated `[KRPCService]` are skipped, as the
  service pass already reports a class member declared in one.
- **The clientgen and docgen fixtures do not change.** The TestServer extension members
  are built into the server but not into the assembly the service definitions come from,
  so the bundled stubs lack them — which is what makes the Python stub merge testable.
  Nothing in clientgen or docgen can tell an extension member from a native one, so there
  is nothing there to cover separately.
- **The Python merge covers class members only.** Service-level procedures and properties
  are not merged; service-level extension procedures are out of scope anyway.
- **`KRPC.SpaceCenter.ModuleRef` is now public.** The #900 pattern has a third-party class
  standing for a part module, so it has to find that module again on every access. Everything
  else the proxy conventions ask for was already public; the resolver was not. This supersedes
  the rejected alternative in [object-lifetime.md](../object-lifetime.md), which weighed only
  whether the bundled services needed it.

## Context

[Issue #305](https://github.com/krpc/krpc/issues/305): a third-party kRPC service wants
to add members to another service's classes — e.g. a TestFlight service adding
`vessel.parts.with_failure("blah")` and `parts.failed` onto SpaceCenter's `Parts`.
[Issue #900](https://github.com/krpc/krpc/issues/900): mods want to expose their
`PartModule`s as first-class typed classes instead of the stringly-typed
`Module.HasField`/`GetField` API.

What exploration established:

- **Cross-service *type references* already work end-to-end.** There is no
  same-service validation (`ProcedureSignature` checks only `TypeUtils.IsAValidType`);
  the wire `Type` message carries the owning service per class; and the bundled
  RemoteTech/KerbalAlarmClock/LiDAR/Drawing/UI services reference
  `SpaceCenter.Vessel`/`Part`/`CelestialBody` heavily (e.g.
  `service/RemoteTech/src/Comms.cs:15,46,103`). All clients render foreign class types
  service-qualified, and the Python stub generator even emits cross-service imports
  (`clientgen/python.py:194-242`).
- **Class-level redirection already exists**: `[KRPCClass(Service = "X")]` lets a class
  declared in any assembly join service X's namespace
  (`TypeUtils.ValidateKRPCClass`, `core/src/Service/TypeUtils.cs:449-473`; documented in
  `doc/src/extending.rst:180-238`). What's missing is the member-level equivalent.
- **Class members are just procedures with naming conventions** in the owning
  service's definition: `Parts_WithFailure`, `Parts_get_Failed`,
  `Parts_static_X` (`ServiceSignature.AddClassMethod` / `AddClassProperty`,
  `core/src/Service/Scanner/ServiceSignature.cs:252-311`). Every consumer — Python/Lua
  dynamic clients, clientgen, docgen — resolves the bare class-name prefix **within the
  procedure's own service** (`client/python/krpc/service.py:429-479`,
  `client/lua/krpc/service.lua:302-330`, `clientgen/generator.py:245-320`,
  `docgen/nodes.py:68-70`). `ProcedureSignature` re-parses the same convention
  (`ProcedureSignature.cs:134-161`) but nothing reads the result, so it is not a
  consumer to keep in step.
- **Member binding is by declaring type only**: `TypeUtils.ValidateKRPCMethod`
  (`TypeUtils.cs:626-641`) requires the method to be declared in the class (or a base);
  `[KRPCMethod]` has no redirection property; C# extension methods
  (`ExtensionAttribute`) are nowhere handled. A `[KRPCMethod]` on a plain static class
  is silently ignored today, because the scanner only looks for it on `[KRPCClass]` and
  `[KRPCService]` types.
- **Service discovery is AppDomain-wide reflection** (`Reflection.AllTypes`,
  `core/src/Utils/Reflection.cs:10-26`): any mod DLL in GameData is scanned — the
  distribution story for third-party extensions already exists.
- **Python client stub short-circuit**: a service whose stubs were generated ahead of
  time has its types registered from the stubs and never goes through `create_service`
  (`client/python/krpc/client.py:129-150`), so the live definition's procedures are
  ignored — runtime-added members on SpaceCenter would be invisible to stub users.

## Decisions

- **Extension members are grafted into the *target class's service definition* on the
  server; the wire protocol and schema are unchanged and clients need (almost) no
  changes.** A TestFlight extension method on `Parts` becomes an ordinary
  `Parts_WithFailure` procedure in *SpaceCenter's* service definition, executing
  TestFlight's static method. Every client, clientgen, and docgen then attaches it
  exactly like a native member — `vessel.parts.with_failure(...)` in all six client
  languages for free.
  **Rejected: extension procedures living in the extending service's definition** with
  service-qualified class targeting. That needs a schema extension (the bare-name
  prefix can't carry a service) plus new attachment logic in every dynamic client,
  clientgen restructuring, and docgen changes — and Java/C++ cannot even express
  instance members added from another generated file (no extension methods; nested /
  closed classes). The chosen design turns a six-client problem into a
  server-scanner problem.
- **Authoring syntax: C# extension methods.** `[KRPCMethod]` on a public static
  extension method (compiler-emitted `ExtensionAttribute`) in any public static class
  — no service attribute needed on the containing class; the target service is
  resolved from the `this` parameter's class:

  ```csharp
  public static class TestFlightExtensions {
      /// <summary>Parts that have the named failure.</summary>
      [KRPCMethod]
      public static IList<Part> WithFailure (this Parts parts, string failure) { ... }

      [KRPCProperty (Nullable = true)]
      public static FailureModule GetFailureModule (this Part part) { ... }
  }
  ```
- **Extension properties** (C# has none natively): `KRPCPropertyAttribute` gains
  `AttributeUsage(AttributeTargets.Method)` for extension methods named `GetX` /
  `SetX` — getter = `this` only, non-void; setter = `this` + one parameter, void;
  emitted as `Class_get_X` / `Class_set_X`. Mismatched name/shape is a scanner error.
- **Classes only.** Extension members target `[KRPCClass]` types. `[KRPCStruct]` types
  are serialized by value and have only fields, so there is nothing to attach a member
  to; a struct as the `this` parameter is a scanner error. Structs are valid parameter
  and return types of an extension member, through `IsAValidType`, like any other type.
- **Nullability and deprecation compose as for native members.** `Nullable` on
  `[KRPCMethod]`/`[KRPCProperty]` and `[KRPCNullable]` on parameters carry through
  unchanged; an extension property setter's value parameter is its second parameter and
  is marked nullable directly, rather than through the synthesized-parameter route
  `AddClassPropertyMethod` needs. `[Obsolete]` on an extension member must reach the
  signature the same way `TypeUtils.GetDeprecated` /
  `TypeUtils.GetPropertyDeprecated` do for native members.
- **#900 is a documented pattern on top of #305, not a new mechanism.** A mod defines
  `[KRPCClass(Service = "TestFlight")] FailureModule` wrapping its `PartModule`, plus a
  nullable extension property `Part.failure_module` (built via
  `part.InternalPart.Modules` — the same public-accessor route the bundled services
  use). The wrapper implements `IGameObjectState`, as `SpaceCenter.Module` does, so the
  object store drops it once the game destroys what it stands for. Nullability of "this
  part has no such module" composes with the null-value support from
  [#843](https://github.com/krpc/krpc/issues/843).
  **Rejected: the issue's `ISupportsKRPC` / `Module.GetRepresentation()` bridge** — with
  inheritance (#905) explicitly out of scope, a generic `GetRepresentation` has no
  expressible static return type in the kRPC type system. Revisit only if #905 lands.
- **GameScene**: an extension member's `GameScene.Inherit` resolves against the
  *target class's* effective scene (which may itself inherit from the target service) —
  the member runs in the target's context. Explicit scenes on the member override, as
  for native members.
- **Collisions are scanner errors**: an extension member whose procedure name collides
  with a native member or another extension fails the scan with a message naming both
  declaring types.

## Server changes (`core/`)

1. **Scanner pass** (`core/src/Service/Scanner/Scanner.cs`): a new pass, after all
   services and classes are registered, over public static classes' methods carrying
   `[KRPCMethod]` or `[KRPCProperty]` + `ExtensionAttribute` (today silently ignored —
   no behavior change for existing code that would suddenly get picked up, but audit
   for accidental matches). For each: validate, resolve the target class from the
   first parameter (`TypeUtils.IsAClassType` + `GetClassServiceName`), and add to the
   *target's* `ServiceSignature` via new `AddClassExtensionMethod` /
   `AddClassExtensionProperty` methods emitting the standard
   `Class_Member` / `Class_get_X` / `Class_set_X` names. The pass follows the
   conventions the other passes now use: set `Scanner.CurrentAssembly` so a
   `ServiceException` is attributed to the mod that caused it, and report failures
   through `HandleError` so one bad extension is collected for the server window
   rather than aborting the whole scan.
2. **Validation** (`TypeUtils.cs`): `ValidateKRPCExtensionMethod` — public static,
   `ExtensionAttribute` present, first parameter a `[KRPCClass]` type, remaining
   parameter/return types `IsAValidType`, target service exists (`ServiceException`
   otherwise), property shape rules above.
3. **Handler**: reuse `ClassStaticMethodHandler`
   (`core/src/Service/ClassStaticMethodHandler.cs`), which already compiles a plain
   static invoker and takes its parameters straight off the `MethodInfo` — an
   extension member is a static call whose first argument is the instance. It needs
   only the first parameter renamed to `"this"`, matching the synthetic parameter
   `ClassMethodHandler.cs:23` inserts, so client-side positional binding is identical.
   `HasInstance` stays **false**: parameter 0 then remains in the argument array,
   which is what a static call wants, and `Services.SetArguments`
   (`Services.cs:252`) and `KRPC.Expression.Call` (`Expression.cs:118`) — the only two
   readers of the flag — split off an instance only when it is true. Nothing keys
   instance-ness off `HasInstance` or off the parameter name: the clients use the
   `Class_Member` naming convention and drop parameter 0 by position
   (`clientgen/generator.py:249`).
4. **GameScene resolution** for extension members per the decision above. No new API is
   needed: `TypeUtils.GetClassGameScene`, `GetMethodGameScene` and
   `GetClassPropertyGameScene` already take the class type, so passing the *target*
   class gives the intended semantics.
5. Documentation flows unchanged: XML doc comments on the extension method are picked
   up by `DocumentationExtensions.GetDocumentation` from the mod's own doc XML, and
   cref resolution already handles cross-assembly kRPC names.

No schema, wire, or ServiceDefinitions-JSON format changes — extension members are
indistinguishable from native members downstream.

## Client changes

- **None for correctness** in Lua (fully dynamic), C#, Java, C++, cnano (static stubs:
  third parties regenerate stubs from their server's definitions, the documented
  clientgen workflow in `extending.rst`; bundled stubs are unaffected because bundled
  definitions contain no third-party extensions).
- **Python: stub/definition merge** (the one real client work item). A service with
  pre-generated stubs contributes only `_stub_definitions` and is never passed to
  `create_service`, so the live definition's procedures are dropped
  (`client/python/krpc/client.py:129-150`). After `register_all` has registered every
  service's types, diff the live definition's procedures against the stub service and
  attach any that are missing, reusing the `_add_service_class_method` /
  `_add_service_class_static_method` / `_add_service_class_property` machinery that
  `create_service` uses — the stub's classes are ordinary Python classes and the
  dynamic path already attaches via `setattr`. Run each attachment through
  `_skipping_unknown_types` (`service.py:352`), so a member naming a type the client
  does not know is skipped with a warning rather than failing the connection; that is
  the same treatment the dynamic path gives it, and the struct field-count warning in
  `_stub_definitions` is the existing precedent for tolerating skew this way. This also
  fixes the general version-skew gap where a newer server's added members are invisible
  to older stubs; until it lands, `Client(use_pregenerated_stubs=False)` is the
  workaround. Foreign return types (e.g. `TestFlight.FailureModule`) resolve through
  `types.py` `class_type(service, name)`, which creates types on demand and is keyed
  globally by (service, name) — no ordering hazard.

## Documentation

`doc/src/extending.rst`:
- A new "Extending other services" section: extension methods and properties, the
  `this`-parameter rule, GameScene semantics, collision behavior.
- A worked #900 example: wrapping a mod `PartModule` as a `[KRPCClass]` +
  nullable extension property on `SpaceCenter.Part`, with the
  `InternalPart` access pattern and `IGameObjectState` on the wrapper.

## Tests

- **TestServer** (`tools/TestServer/src/`): a `TestServiceExtensions` static class
  adding an extension method, a read-only extension property, and a read/write
  extension property pair onto `TestClass`, plus an extension returning a class from
  a second service (cross-service return) — appearing in TestService's definition.
  TestServer declares only one service today, so the cross-service case needs a second
  one added there; `core/test/Service/TestService2.cs` and `TestService3.cs` are the
  precedent on the scanner side.
- **Core scanner tests** (`core/test/Service/ScannerTest.cs`): registration under the
  standard names; validation errors (first param not a KRPCClass, first param a
  KRPCStruct, non-static, missing `this`, bad property shape, name collision with a
  native member, target service missing); GameScene inheritance from the target class;
  deprecation and nullability carried through.
- **Handler test**: extension member invocation with the instance as parameter 0
  (beside `ClassMethodHandlerTest.cs`).
- **Client tests**: Python/Lua dynamic — extension members callable and
  indistinguishable from native ones; Python stub-merge — a stub lacking a member
  present in the live definition gains it at connect. TestService's Python stubs are
  bundled (`services-testservice` in `client/python/BUILD.bazel`), so this is tested by
  adding the extension only to the live TestServer.
- **krpctools**: clientgen golden fixtures regenerate (extension members appear as
  ordinary members in all five generated languages); docgen fixture showing the member
  on the target class's page.

## Implementation order

1. Server: validation + scanner pass + handler; core tests.
2. TestServer extensions + protocol-level client-test verification (no client changes
   needed to pass).
3. Python stub/definition merge + tests.
4. `extending.rst` sections + the #900 worked example.
5. `CHANGELOG.md` entries (core, python client, docs) as the final pre-merge commit.

## Follow-ups (out of scope)

- **Service-level extension procedures** (`[KRPCProcedure(Service = "X")]` adding
  top-level procedures/properties to another service) — the symmetric companion to
  `[KRPCClass(Service=...)]`; nothing in this design precludes it, and the scanner
  pass structure would accommodate it naturally. Add if a concrete need appears.
- **Typed module discovery** (`Part.modules_of_type(...)`-style helpers) and any
  polymorphic `Module.representation` bridge — blocked on inheritance (#905).
