# Extension members for other services' classes (issues #305 + #900)

**Status:** proposal — design agreed, not yet implemented (2026-07-03).

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
  (`clientgen/python.py:160-209`).
- **Class-level redirection already exists**: `[KRPCClass(Service = "X")]` lets a class
  declared in any assembly join service X's namespace
  (`TypeUtils.ValidateKRPCClass`, `TypeUtils.cs:362-386`; documented in
  `doc/src/extending.rst:175-234`). What's missing is the member-level equivalent.
- **Class members are just procedures with naming conventions** in the owning
  service's definition: `Parts_WithFailure`, `Parts_get_Failed`,
  `Parts_static_X` (`ServiceSignature.AddClassMethod`,
  `core/src/Service/Scanner/ServiceSignature.cs:186-232`; re-parsed by
  `ProcedureSignature.cs:116-143`). Every consumer — Python/Lua dynamic clients,
  clientgen, docgen — resolves the bare class-name prefix **within the procedure's own
  service** (`client/python/krpc/service.py:432-439`, `service.lua:136-160`,
  `clientgen/generator.py:152-156`, `docgen/nodes.py:55-65`).
- **Member binding is by declaring type only**: `TypeUtils.ValidateKRPCMethod`
  (`TypeUtils.cs:433-448`) requires the method to be declared in the class (or a base);
  `[KRPCMethod]` has no redirection property; C# extension methods
  (`ExtensionAttribute`) are nowhere handled. A `[KRPCMethod]` on a plain static class
  is silently ignored today.
- **Service discovery is AppDomain-wide reflection** (`Reflection.AllTypes`,
  `core/src/Utils/Reflection.cs:10-26`): any mod DLL in GameData is scanned — the
  distribution story for third-party extensions already exists.
- **Python client stub short-circuit**: when a pre-generated stub exists for a service,
  `client.py:53-63` uses it wholesale and ignores the live definition's procedures —
  so runtime-added members on SpaceCenter would be invisible to stub users.

## Decisions

- **Extension members are grafted into the *target class's service definition* on the
  server; the wire protocol and schema are unchanged and clients need (almost) no
  changes.** A TestFlight extension method on `Parts` becomes an ordinary
  `Parts_WithFailure` procedure in *SpaceCenter's* service definition, executing
  TestFlight's static method. Every client, clientgen, and docgen then attaches it
  exactly like a native member — `vessel.parts.with_failure(...)` in all seven client
  languages for free.
  **Rejected: extension procedures living in the extending service's definition** with
  service-qualified class targeting. That needs a schema extension (the bare-name
  prefix can't carry a service) plus new attachment logic in every dynamic client,
  clientgen restructuring, and docgen changes — and Java/C++ cannot even express
  instance members added from another generated file (no extension methods; nested /
  closed classes). The chosen design turns a seven-client problem into a
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
- **#900 is a documented pattern on top of #305, not a new mechanism.** A mod defines
  `[KRPCClass(Service = "TestFlight")] FailureModule` wrapping its `PartModule`, plus a
  nullable extension property `Part.failure_module` (built via
  `part.InternalPart.Modules` — the same public-accessor route the bundled services
  use). Nullability of "this part has no such module" composes with #843's `is_null`.
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
   services/classes are registered, over public static classes' methods carrying
   `[KRPCMethod]` or `[KRPCProperty]` + `ExtensionAttribute` (today silently ignored —
   no behavior change for existing code that would suddenly get picked up, but audit
   for accidental matches). For each: validate, resolve the target class from the
   first parameter (`TypeUtils.IsAClassType` + `GetClassServiceName`), and add to the
   *target's* `ServiceSignature` via new `AddClassExtensionMethod` /
   `AddClassExtensionProperty` methods emitting the standard
   `Class_Member` / `Class_get_X` / `Class_set_X` names.
2. **Validation** (`TypeUtils.cs`): `ValidateKRPCExtensionMethod` — public static,
   `ExtensionAttribute` present, first parameter a `[KRPCClass]` type, remaining
   parameter/return types `IsAValidType`, target service exists (`ServiceException`
   otherwise), property shape rules above.
3. **Handler**: new `ClassExtensionMethodHandler`
   (beside `core/src/Service/ClassMethodHandler.cs`) — parameters are the method's own
   parameters with the first renamed to `"this"` (matching the synthetic parameter
   `ClassMethodHandler.cs:23` inserts, so client-side positional binding is
   identical); invocation is a plain static call, no instance cast needed. Reuses the
   existing continuation/one-tick machinery via `ProcedureHandler`-style invoker
   compilation.
4. **GameScene resolution** for extension members per the decision above (extend the
   `TypeUtils.Get*GameScene` family with a target-class-relative variant).
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
- **Python: stub/definition merge** (the one real client work item). After
  registering a pre-generated stub's types (`client.py:53-63`), diff the live
  definition's procedures against the stub and dynamically attach any missing ones —
  reusing the existing `_add_service_class_method` / `_add_service_class_property` /
  procedure machinery pointed at the stub's classes (they are ordinary Python classes;
  the dynamic path already attaches via `setattr`). This also fixes the general
  version-skew gap where a newer server's added members are invisible to older stubs.
  Foreign return types (e.g. `TestFlight.FailureModule`) resolve through
  `types.py` `class_type(service, name)`, which creates types on demand and is keyed
  globally by (service, name) — no ordering hazard.

## Documentation

`doc/src/extending.rst`:
- A new "Extending other services" section: extension methods and properties, the
  `this`-parameter rule, GameScene semantics, collision behavior.
- A worked #900 example: wrapping a mod `PartModule` as a `[KRPCClass]` +
  nullable extension property on `SpaceCenter.Part`, with the
  `InternalPart` access pattern and a pointer from the `Module` class docs to this
  pattern for mod authors.

## Tests

- **TestServer** (`tools/TestServer/src/`): a `TestServiceExtensions` static class
  adding an extension method, a read-only extension property, and a read/write
  extension property pair onto `TestClass`, plus an extension returning a class from
  a second service (cross-service return) — appearing in TestService's definition.
- **Core scanner tests** (`core/test/Service/ScannerTest.cs`): registration under the
  standard names; validation errors (first param not a KRPCClass, non-static,
  missing `this`, bad property shape, name collision with a native member, target
  service missing); GameScene inheritance from the target class.
- **Handler test**: `ClassExtensionMethodHandler` invocation with the instance as
  parameter 0 (beside `ClassMethodHandlerTest.cs`).
- **Client tests**: Python/Lua dynamic — extension members callable and
  indistinguishable from native ones; Python stub-merge — a stub lacking a member
  present in the live definition gains it at connect (can be tested against
  TestService's stub by adding the extension only to the live TestServer).
- **krpctools**: clientgen golden fixtures regenerate (extension members appear as
  ordinary members in all five languages); docgen fixture showing the member on the
  target class's page.

## Implementation order

1. Server: validation + scanner pass + handler; core tests.
2. TestServer extensions + protocol-level client-test verification (no client changes
   needed to pass).
3. Python stub/definition merge + tests.
4. `extending.rst` sections + the #900 worked example.
5. CHANGES.txt entries (core, python client, docs) as the final pre-merge commit.

## Follow-ups (out of scope)

- **Service-level extension procedures** (`[KRPCProcedure(Service = "X")]` adding
  top-level procedures/properties to another service) — the symmetric companion to
  `[KRPCClass(Service=...)]`; nothing in this design precludes it, and the scanner
  pass structure would accommodate it naturally. Add if a concrete need appears.
- **Typed module discovery** (`Part.modules_of_type(...)`-style helpers) and any
  polymorphic `Module.representation` bridge — blocked on inheritance (#905).
