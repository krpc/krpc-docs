# Surfacing deprecated members in docs and clients (issue #904)

**Status:** done — merged as [PR #926](https://github.com/krpc/krpc/pull/926) (2026-07-11);
issue [#904](https://github.com/krpc/krpc/issues/904) closed. Historical design record.

Implementation notes (deviations/clarifications from the design below):
 - `TypeUtils.GetDeprecated`/`GetPropertyDeprecated` guard with `Reflection.HasAttribute`
   before `Reflection.GetAttribute` (the latter throws when the attribute is absent).
 - Generated C#/Java/C++ stubs reference their own deprecated members (exception-type
   registration, enum `fromValue`), which trips warnings-as-errors — suppressed file-wide
   in the generated code (`#pragma warning disable 612, 618` for C#, class-level
   `@SuppressWarnings("deprecation")` for Java). C++ `[[deprecated]]` is placed after the
   `class`/`enum struct` keyword and after the enumerator name (not leading).
 - The dynamic Python `DeprecationWarning` fires only for dynamically-created services;
   pre-generated stubs get the docstring notice only (they are static and warning-free),
   matching the design's split. The client uses pre-generated stubs by default, so the
   warning test connects with `use_pregenerated_stubs=False`.
 - Also prepended the `Deprecated.` docstring notice to dynamic classes/enums/enum
   values/exceptions/services (design only spelled out procedures/properties).
 - `game_scenes` wire-gap fix left out of scope (tracked separately).

## Context

[Issue #904](https://github.com/krpc/krpc/issues/904): marking a kRPC member
`[Obsolete("reason")]` has no visible effect — generated documentation shows nothing,
and generated client code carries no deprecation marker, so users only discover
deprecations from the changelog.

Findings from the codebase:

- **Deprecation is not modeled anywhere today.** `Obsolete` appears nowhere in
  `core/src` or `service/*/src`; the scanner neither reads nor skips it, and there is no
  corresponding field in the wire schema, the ServiceDefinitions JSON, docgen or
  clientgen. The full chain must be added: C# attribute → scanner signature → wire
  schema + JSON → krpctools (docgen/clientgen) → templates → dynamic clients.
- **`GameScene` is the exact model to copy** for threading per-member metadata:
  read from the attribute in `ServiceSignature.Add*` via `TypeUtils`
  (`core/src/Service/TypeUtils.cs:185-192`), stored on the signature
  (`Scanner/ProcedureSignature.cs:91-99`), conditionally emitted in `GetObjectData`
  (JSON) and copied into internal messages in `KRPC.GetServices`.
- **Known gap to avoid repeating**: `Procedure.game_scenes` is populated on the internal
  message (`core/src/Service/KRPC/KRPC.cs:87`) but never copied into the protobuf message
  — `MessageExtensions.ToProtobufMessage(Procedure)` has no `GameScenes` line, so game
  scenes reach the JSON but not the wire. The deprecation flag must be wired through
  **both** paths, since the dynamic Python/Lua clients read the protobuf `GetServices`
  response, not the JSON.
- All schema additions needed are plain `bool`/`string` fields — supported by every
  toolchain in the build including the Unity-pinned protobuf 3.10.1 and protobuf-lua
  (no repeat of the #843 proto3-`optional` problem).

## Decisions

- **Read the standard `System.ObsoleteAttribute`** — no new kRPC attribute. Service
  authors write `[KRPCProperty, Obsolete("use Foo instead")]` exactly as the issue does.
  `ObsoleteAttribute.Message` becomes the reason (empty string when omitted).
  `IsError = true` is treated the same as `false` for now (the member stays callable
  over RPC; see open questions).
- **Wire/JSON naming: `deprecated` + `deprecated_reason`** — language-neutral
  (matches Java/C++/Python idiom; "obsolete" is C#-specific).
- **Scope: all service-definition entities** — procedures (which covers properties,
  class methods/static methods and class properties), classes, enumerations,
  enumeration values, exceptions, and services. Deprecating a class/enum does **not**
  auto-deprecate its members on the wire; each entity carries its own flag (clients and
  docs mark the container itself; C#/Java/C++ compilers already warn on use of a member
  of a deprecated type where applicable).
- **Deprecated members remain fully functional** — the scanner never skips them; this
  feature is purely informational.
- **Dynamic Python client emits `DeprecationWarning` at call time** — the runtime
  analogue of a compiler warning, using the standard `warnings` machinery (so users
  control visibility the normal Python way). The dynamic Lua client is left unchanged
  (it doesn't even consume `documentation` today).
- **Docs rendering: a warning admonition, not `.. deprecated::`** — Sphinx's built-in
  `deprecated` directive takes a *version* argument, which we don't have (the attribute
  carries a reason, not a version), and support across the third-party domains
  (sphinx_csharp, javasphinx, luadomain) is inconsistent. Each docgen macro emits a
  domain-independent `.. warning:: Deprecated. <reason>` admonition instead, directly
  after the member's signature/doc text. Gray-out styling via CSS is a cosmetic
  follow-up (see open questions).

## Wire schema changes (`protobuf/krpc.proto`)

Add to each of `Service` (fields 7–8), `Procedure` (7–8), `Class` (3–4),
`Enumeration` (4–5), `EnumerationValue` (4–5), `Exception` (3–4):

```proto
  bool deprecated = N;
  string deprecated_reason = N + 1;   // may be empty; only meaningful when deprecated
```

Additive proto3 change; old clients ignore the fields, old servers never set them.
(`Parameter` is excluded — C# cannot apply `[Obsolete]` to a parameter.)

## Server changes (`core/`)

1. **Scanner** — in `ServiceSignature.Add*` (`core/src/Service/Scanner/ServiceSignature.cs`),
   read the attribute off the member being scanned, following the `GameScene`/`Nullable`
   pattern; a small helper in `TypeUtils` (e.g. `GetDeprecated(ICustomAttributeProvider)`
   returning `(bool, string)`) using `Reflection.GetAttribute<ObsoleteAttribute>`.
   For properties, read the attribute from the property itself (authors annotate the
   property, per the issue's example), falling back to the accessor method.
2. **Signatures** — add `Deprecated` / `DeprecatedReason` properties to
   `ProcedureSignature`, `ClassSignature`, `EnumerationSignature`,
   `EnumerationValueSignature`, `ExceptionSignature`, `ServiceSignature`
   (`core/src/Service/Scanner/*.cs`), set in the ctors.
3. **JSON** — in each signature's `GetObjectData`, conditionally emit
   (`if (Deprecated) { info.AddValue("deprecated", true); info.AddValue("deprecated_reason", ...); }`),
   mirroring the `game_scenes` conditional (`ProcedureSignature.cs:146-159`). This is
   the only producer-side change needed for the ServiceDefinitions JSON
   (`tools/ServiceDefinitions/src/Program.cs` serializes via `GetObjectData`).
4. **Internal messages** — add the two fields to
   `core/src/Service/Messages/{Procedure,Class,Enumeration,EnumerationValue,Exception,Service}.cs`.
5. **`KRPC.GetServices`** (`core/src/Service/KRPC/KRPC.cs:68-121`) — copy signature →
   internal message.
6. **`MessageExtensions.cs`** — copy internal message → protobuf in each
   `ToProtobufMessage`. **Do not** forget this step (the `game_scenes` gap above).
   Optionally fix the missing `GameScenes` copy in the same pass — small, related, and
   makes the wire response match the JSON (separate commit).
7. Where service code must keep *calling* a deprecated member internally, use
   `#pragma warning disable 618` locally rather than suppressing project-wide.

## docgen changes (`tools/krpctools/krpctools/docgen/`)

- `nodes.py` — accept `deprecated` / `deprecated_reason` from the JSON `**info` on
  `Service`, `Class`, `Procedure`, `Property`, `ClassMethod`, `ClassStaticMethod`,
  `ClassProperty`, `Enumeration`, `EnumerationValue`, `ExceptionNode` (default
  false/empty).
- Each language macro template (`python.tmpl`, `csharp.tmpl`, `java.tmpl`, `cpp.tmpl`,
  `cnano.tmpl`, `lua.tmpl`) — after the member directive and before/alongside
  `gendoc(x.documentation)`, emit:

  ```rst
  .. warning:: Deprecated. <reason>
  ```

  (reason omitted when empty). Same slot as the existing `remarks` → `.. note::`
  pattern (`python.tmpl:167-171`).
- All six per-language API doc targets in `doc/BUILD.bazel` regenerate automatically.

## clientgen changes (`tools/krpctools/krpctools/clientgen/`)

- `generator.py` — add `deprecated` / `deprecated_reason` to every member context dict
  (procedures ~L104-115, properties, class members, classes, enums, exceptions).
- Per-language templates:
  - **C#** (`csharp.tmpl`): emit `[global::System.Obsolete("<reason>")]` alongside
    `[RPCAttribute]` (procedure ~L92-95, properties ~L104, class methods ~L176-206);
    plain `[global::System.Obsolete]` when the reason is empty. Classes/enums/enum
    values get the attribute on their declarations.
  - **Java** (`java.tmpl` + `java.py`): emit `@Deprecated` alongside `@RPCInfo`
    (~L66-72), and append a `@deprecated <reason>` javadoc tag inside the generated
    `/** … */` block (`parse_documentation`, `java.py:72-77`).
  - **C++** (`cpp.tmpl`): emit `[[deprecated("<reason>")]]` on the declaration
    (methods ~L80-84, properties ~L86-90, class members ~L118-133); the build is
    already C++17. Also add `\deprecated <reason>` to the doxygen block
    (`cpp.py:25-30`).
  - **cnano** (`cnano.tmpl` + a runtime header): define a `KRPC_DEPRECATED(msg)` macro
    in `client/cnano/include/krpc_cnano/` (`__attribute__((deprecated(msg)))` for
    GCC/Clang, `__declspec(deprecated(msg))` for MSVC, empty otherwise) and emit it on
    generated declarations.
  - **Python stubs** (`python.tmpl` + `python.py`): prepend a `Deprecated: <reason>`
    line to the generated docstring. (A `@typing_extensions.deprecated` decorator would
    give static-checker support but adds a dependency — see open questions.)
- Regenerate golden fixtures `krpctools/test/clientgen-TestService-*.txt`.

## Dynamic clients

- **Python** (`client/python/krpc/service.py`): when building invokers
  (~L360-370) and properties, if the protobuf `Procedure.deprecated` is set, wrap the
  call to issue
  `warnings.warn("<Service>.<name> is deprecated: <reason>", DeprecationWarning, stacklevel=2)`
  (once per call site, standard `warnings` dedup applies). Also prepend
  `Deprecated: <reason>` to the constructed docstring (`_parse_documentation` output,
  L159-184).
- **Lua**: no change (out of scope; it ignores `documentation` today too).

## Tests

- **TestService** (`tools/TestServer/src/TestService.cs`): add an `[Obsolete("reason")]`
  procedure, property, class (with a member), enum value, and one `[Obsolete]` with no
  message — exercising every entity kind and the empty-reason case.
- **Core**: `ScannerTest.cs` + `MessageAssert.cs` assertions for the new signature
  fields and their JSON emission; a test that the protobuf `GetServices` response
  carries the flags (covering the `MessageExtensions` copy).
- **krpctools**: clientgen golden-fixture diffs per language; docgen output checked via
  the existing `check_documented_test` targets plus a fixture assertion that the
  warning admonition is emitted.
- **Python client**: `pytest.warns(DeprecationWarning)` on calling the deprecated
  TestService procedure; docstring content check.

## Implementation order

1. `protobuf/krpc.proto` + `doc/src/communication-protocols/messages.rst`
   (document the new fields).
2. Server: TypeUtils helper, signatures, JSON, internal messages, `GetServices`,
   `MessageExtensions` (+ optional `game_scenes` gap fix as its own commit); core tests.
3. TestService additions.
4. docgen: nodes + six macro templates.
5. clientgen: generator context + five language templates + cnano macro header;
   golden fixtures.
6. Python dynamic client runtime warnings + tests.
7. CHANGES.txt entries per component as the final commit before merging the PR.

## Open questions

1. **`ObsoleteAttribute.IsError = true`**: currently treated identically to a plain
   deprecation. An alternative is to exclude such members from the service definition
   entirely (a soft-removal mechanism). Deferred until there's a concrete need.
2. **Python static-checker support**: adopt `typing_extensions.deprecated` (PEP 702) in
   generated Python stubs? Gives IDE strikethrough at the cost of a new dependency for
   the generated services package. Deferred; docstring + runtime warning ship first.
3. **Docs styling**: the issue suggests graying out deprecated members. The warning
   admonition ships first; a `:class: deprecated`-based CSS treatment can be layered on
   later without touching the data flow.
