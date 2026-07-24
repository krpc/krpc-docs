# Nullable values and default-value presence (issue #843)

**Status:** in progress (as of 2026-07-24). Phases 1–6 implemented — protocol schema, core server
+ enforcement, TestService fixtures, the Python client and shared krpctools path, the SpaceCenter
services audit + workaround revert, and every client (C#, C++, Java, Lua, cnano). Only the final
changelog commit remains pending. Tracked by
[issue #843](https://github.com/krpc/krpc/issues/843); each phase's implementation notes are
inline under [Implementation phases](#implementation-phases).

## Context

[Issue #843](https://github.com/krpc/krpc/issues/843): `Parameter.default_value` and
`ProcedureResult.value` are plain proto3 `bytes` fields, so "absent" and "explicitly
empty" are indistinguishable on the wire. The issue proposed marking both fields proto3
`optional`. Investigation of the codebase changed the design in three important ways.

**Finding 1 — the bug is narrower than the issue states.** The server encodes values
via `Encoder.EncodeObject` (`core/src/Server/ProtocolBuffers/Encoder.cs:20-81`), and
null encodes as `WriteUInt64(0)` → a single non-empty `0x00` byte (`Encoder.cs:28-29`).
Zero scalars are also non-empty (`int 0` → `0x00`, `""` → length-prefix `0x00`,
`false` → `0x00`). The only encodings that produce **zero-length** bytes — and therefore
vanish from the wire — are empty protobuf messages: empty list/set/dict/tuple defaults.
That is exactly the #824 `LaunchVessel.crew` case. So the concrete bug is "empty-collection
defaults look like no-default to dynamic clients"; zero scalar defaults work today.

**Finding 2 — there is already a type-agnostic null sentinel, and clients depend on it.**
The server emits `0x00` for null regardless of type; clients decode it as object-id 0 → null
for class types (all six clients) and as a `b"\x00"` sentinel → `None` for collection types
(Python `decoder.py:69-91`, Lua `decoder.lua`). The sentinel collides with legal values for
strings (`""`) and scalars (`0`), which is why nullability is effectively class-only today.
All four static clients (C#, Java, C++, cnano) decode a null class result by reading a
varint from the `0x00` byte; on an absent/empty value field they throw
(`client/cpp/src/decoder.cpp:71-76`, cnano `decoder.c:128-132`; C#/Java throw inside
protobuf varint reads).

**Finding 3 — proto3 `optional` is blocked by two toolchains.** The KSP/Unity server
plugin is pinned to protoc + Google.Protobuf **3.10.1** (`MODULE.bazel:121-129` — KSP's
Unity lacks `ReadOnlySpan`, required by Google.Protobuf > 3.10.1). protoc 3.10.1 rejects
`optional` in proto3 outright, and the 3.10.1 runtime cannot represent field presence.
The Lua codegen plugin (protobuf-lua 1.1.2, `MODULE.bazel:90-103`) predates proto3
optional and does not advertise `FEATURE_PROTO3_OPTIONAL`, so protoc 35.1 would refuse
to run it. All other toolchains (protoc 35.1, C# client 3.35.1, Java 4.35.1, C++ 35.1,
Python 7.35.1, nanopb 0.4.9.1) support `optional`.

## Decisions

- **Mechanism: additive `bool` fields, not proto3 `optional`.** Explicit presence/null
  flags are added to `Parameter`, `ProcedureResult` and `Argument`. Plain bool fields are
  handled by every toolchain in the build, including Unity protoc/runtime 3.10.1 and
  protobuf-lua 1.1.2. Proto3 `optional` is **rejected** for this feature: it would require
  upgrading the in-game plugin's protobuf stack (bundling System.Memory into GameData,
  untested under KSP) and a protobuf-lua plugin release. The bool fields can be marked
  deprecated in favor of `optional` if those toolchains are ever unblocked.
- **Flat presence/null bools, not a shared `Value` submessage.** A
  `message Value { bytes value = 1; bool is_null = 2; }` reused across `Argument`,
  `ProcedureResult` and `Parameter.default_value` would be tidier, and its message-presence
  would subsume `has_default_value`. Rejected: wrapping every value in a submessage adds
  ~2 framing bytes to *every* value on the wire, whereas a proto3 `false` bool serializes
  to nothing — the flat fields cost zero when unset. The hot path (stream updates and
  calls, including slow serial links) must not grow, so the flat bools are used.
- **Uniform null rule: `is_null = true` ⇒ the value is null, for every type; the value
  bytes are unset and must be ignored.** The legacy id-0/`0x00` null sentinel is retired
  completely — servers and clients stop both *emitting* and *accepting* it. There is no
  compatibility path: this is a **protocol-breaking change**, all bundled clients are
  updated in lockstep, and matched server/client versions are required for any RPC that
  returns or accepts null. The break is documented for third-party client authors.
- **Scope: full.** (a) default-value presence fix (revert the #824 workaround);
  (b) null returns and null defaults for all types; (c) null **arguments** for nullable
  parameters (presence on `Argument` too); (d) nullable API surface for **all** types in
  every client — value-type nullables (`int?` / `Integer` / `std::optional<int>`), not
  just reference and class types.
- **Nullable semantics — uniform, no type-based special cases.** A null argument is legal
  **iff the parameter is marked nullable** (`[KRPCNullable]`, or the property `Nullable`
  flag for a setter argument — see below); a null return is legal
  **iff the procedure is marked nullable** (`Nullable = true` on
  `[KRPCProcedure]`/`[KRPCMethod]`/`[KRPCProperty]`) — for *every* type, class types
  included. This removes the current behavior where class-typed **arguments** are
  implicitly nullable regardless of `[KRPCNullable]` (`GetArguments`/`SetArguments` gate
  only on `IsAClassType`, `core/src/Service/Services.cs:301-304,356-361`); returns already
  require explicit marking (`CheckReturnValue`, `Services.cs:384`). Consequences:
  - `CheckReturnValue` rejects a null non-class return (`Services.cs:378`) *before*
    consulting `ReturnIsNullable`; that gate is removed so a marked-nullable return of any
    type is accepted.
  - Parameters that legitimately accept null must be nullable — previously implicit for
    class types. The population is small and known (see Server changes): the null-clearing
    property setters `SpaceCenter.Target*` (handled by the property flag, below) and the
    existing `[KRPCNullable]` method parameters. **Breaking** for any script that passed
    null to a parameter now treated as non-null.
- **A null default implies nullable.** A parameter whose default value is `null` (`X x = null`
  or `[KRPCDefaultValue(null)]`) is nullable whether or not it also carries `[KRPCNullable]`:
  `ProcedureParameter.Nullable = HasAttribute<KRPCNullable> || (HasDefaultValue && DefaultValue
  == null)`. A null default is itself a declaration that null is a valid value, so the two are
  not independent — without this rule such a parameter could be null by omission yet reject an
  explicit null, which is incoherent, and its generated client type (`Optional[T] = None`) would
  contradict a non-nullable declaration. This also *shrinks* the breaking surface above: the
  many existing `X x = null` optional parameters stay nullable with no annotation, so only
  null-accepting parameters that have **no** default need marking.
- **Nullability is inferred from static signature facts, never from body behavior.** Two
  signature-level declarations imply nullable without an explicit marker: a **null default**
  (`= null`, params only) and a **`Nullable<T>` value type** (`int?`, both params and returns).
  Both are visible in the signature. What *cannot* be inferred is whether a method's *body*
  ever returns null — that is not statically decidable — and C# reference types (`string`,
  class types) carry no nullability in the type. So:
  - A **`Nullable<T>` parameter or return** (`int?`, `TestEnum?`, …) is nullable implicitly; no
    `[KRPCNullable]` / `Nullable = true` needed (see the `Nullable<T>` handling below).
  - A **reference-type return** (`string`, class) must be declared `Nullable = true`; a null
    return from a procedure not so marked throws (`CheckReturnValue`).
  - Properties have **no declared default** in the kRPC model (there is no
    `[KRPCProperty(Default = …)]`), so only the `Nullable<T>` / explicit-flag paths apply. A
    property **getter is a return** — a reference-typed getter needs explicit
    `[KRPCProperty(Nullable = true)]`, and a null read from a non-nullable property throws (a C#
    auto-property that merely holds `null` is runtime state, not a signature fact). A property
    **setter**'s synthesized `value` parameter takes its nullability from the same property flag
    (item 6) or from a `Nullable<T>` value type; it can carry neither `[KRPCNullable]` nor a
    default.
- **`Nullable<T>` value types.** A parameter or return declared `Nullable<T>` (e.g. `int?`,
  `float?`, `bool?`, `TestEnum?`) is unwrapped at the scanner: it appears on the wire as its
  underlying type `T` with `nullable = true` / `return_is_nullable = true`. This is done in
  `ProcedureParameter(ParameterInfo)` (params) and `ProcedureSignature` (returns) via
  `System.Nullable.GetUnderlyingType`. Because everything downstream sees `T`, and a boxed
  `Nullable<T>` is either a boxed `T` or `null` (boxing erases `Nullable<>`), the encoder,
  decoder, wire-type mapping and value validation need **no** `Nullable<T>`-specific handling —
  they operate on `T` as usual, and null is carried by `is_null`. The compiled method invoker
  converts the decoded `T`/`null` back to `Nullable<T>` for the call. The expression API
  (`Expression.Call`) evaluates a nullable value-type return as `Nullable<T>` so the null is
  representable (resolving Open question 2). Nested element nullability (`List<int?>`) is out of
  scope — only top-level parameter/return `Nullable<T>` is unwrapped.

  Only *value* types can be `Nullable<T>`. The **collection** types (`List`, `Set`,
  `Dictionary`, and `System.Tuple<>`) are all **reference** types, so `List<int>?` / `Tuple<…>?`
  are not `Nullable<>` — the `?` is a C# nullable-reference *annotation*, erased at runtime and
  not read by the reflection scanner (a bare `List<int>?` would be treated as a non-nullable
  `List<int>`). A nullable collection — like a nullable `string` or class — is therefore declared
  **explicitly** with `[KRPCNullable]` / `Nullable = true`; null then flows through the same
  reference-type `is_null` path, and the collection encoding runs only for non-null values.

  Why the split is principled, and why the scanner does not try to catch `List<int>?`:
  `Nullable<T>` is a genuine runtime type (`System.Nullable<T>`), present regardless of the
  `<Nullable>` compiler setting — reliably detectable, so it is honored. A reference-type `?`
  lives only in `NullableAttribute` metadata, which is unreliable: kRPC compiles in a
  **nullable-disabled** context (writing `List<int>?` yields compiler warning **CS8632**, an
  error under CI's `-warnaserror`), where the annotation is oblivious and not dependably emitted.
  So `List<int>?` cannot be distinguished from `List<int>` at scan time the way a genuinely
  unsupported type can. **Decision: document, don't detect** — rely on CS8632 plus the explicit
  markers rather than parsing fragile, compiler-context-dependent NRT metadata. (Contrast: a type
  kRPC cannot serialize at all — e.g. `Vector3d` — *is* caught, via `IsAValidType` →
  `ServiceException` at scan time. `List<int>` is a valid type; only its intended nullability is
  lost, and the compiler warning is the guard.)
- **All types nullable.** `is_null` is type-agnostic, so value types (`int`, `float`,
  `bool`, enums) are nullable when marked (`[KRPCNullable]`, `Nullable = true`, or a
  `Nullable<T>` declaration), not just reference/class types; generated client signatures
  reflect this per language (see Client changes).
- **Property nullability spans getter and setter.** A `[KRPCProperty(Nullable = true)]`
  makes both the getter's return *and* the setter's argument nullable — the setter's
  synthesized `value` parameter cannot carry `[KRPCNullable]`, so the property flag is its
  only source of nullability. This preserves null-clearing setters like
  `SpaceCenter.TargetVessel = null` (`SpaceCenter.cs:194,206,218`, all `Nullable = true`).
  A property that is nullable for reads but must reject a null write
  (`Camera.FocussedVessel`/`FocussedBody`, `Camera.cs:543,563`) keeps a manual
  `ArgumentNullException` guard in the setter: the flag lets the null through, and the
  guard rejects it. These are the only manual null guards that remain (see Server changes).

## Wire protocol changes (`protobuf/krpc.proto`)

```diff
 message Argument {
   uint32 position = 1;
   bytes value = 2;
+  bool is_null = 3;
 }

 message ProcedureResult {
   Error error = 1;
   bytes value = 2;
+  bool is_null = 3;
 }

 message Parameter {
   string name = 1;
   Type type = 2;
   bool nullable = 4;
+  bool has_default_value = 5;
   bytes default_value = 3;
+  bool default_value_is_null = 6;
 }
```

Semantics:

| State | `has_default_value` | `default_value_is_null` | `default_value` |
|---|---|---|---|
| no default (required param) | false | false | unset |
| default is a value (incl. empty collection) | true | false | encoded bytes (may be empty) |
| default is null | true | true | unset |

`StreamResult` wraps a `ProcedureResult` (`krpc.proto:76-79`), so streams inherit the
`is_null` semantics with no further schema change. `Response.results` likewise.
Field numbers 3 (Argument, ProcedureResult) and 5–6 (Parameter) are unused today.

Version-skew behavior: old peers ignore the new bool fields, so calls carrying only
non-null values stay byte-compatible across versions. Null traffic is not compatible in
either direction — a new client no longer accepts an old server's id-0/`0x00` null, and an
old client cannot interpret a new server's `is_null`. Any RPC that returns or accepts null
therefore requires matched server/client versions, documented as such.

### Wire-size impact

Proto3 never serializes a scalar field holding its default value, in every runtime in the
build (including Unity's Google.Protobuf 3.10.1), so a `false` bool contributes **zero
bytes**. Consequences:

- Calls with all required, non-null arguments — the common case — produce byte-for-byte
  identical `Argument`/`ProcedureResult` messages to today. Per-call traffic never grows
  for non-null values.
- A null argument or result costs 2 bytes (`is_null` tag + varint) versus 3 bytes for the
  legacy `0x00` sentinel (value-field tag + length + `0x00`), so null traffic *shrinks*.
- `has_default_value`/`default_value_is_null` appear only in `GetServices` metadata, and
  only add 2 bytes per parameter that actually has a default (plus 2 if that default is
  null). Required-only parameters serialize exactly as today.

**Rejected alternative — in-band encoding (no new fields).** Considered: require every
value encoding to be non-empty, treat zero-length `value`/`default_value` bytes as
"absent", and encode null as a non-empty sentinel such as `0x00`. Rejected for two
reasons:

1. *"Empty = absent" requires all real values to encode non-empty*, but empty collections
   legitimately encode as zero-length protobuf messages (Finding 1). Making them non-empty
   means a marker field inside `List`/`Set`/`Dictionary`/`Tuple` or a prefix byte on every
   collection value — changing the value encoding that every released client decodes, a
   far more invasive break than additive fields old peers ignore. (Proto3 without
   `optional` also cannot distinguish "field unset" from "field set to empty bytes" — they
   serialize identically — so empty-means-absent is forced regardless; the design already
   relies on clients decoding an absent value field as an empty collection when the
   declared type is a collection.)
2. *A `0x00` null sentinel is exactly today's protocol*, and its collisions are the root
   cause of the limitation: `0x00` is also the valid encoding of `int 0`, `uint 0`,
   `false` and `""` (Finding 2), which is why nullability is effectively class-only now.
   Since the scope includes nullable non-class types, an in-band sentinel would require
   escaping every value (growing the common case), whereas the out-of-band flag costs
   nothing when unset.

**Considered alternative — nullability on `Type`, not the slot.** `Parameter.nullable`
(and `Procedure.return_is_nullable`) could instead be a `bool nullable` on the `Type`
message. `Type` is recursive (`repeated Type types` for collection/tuple elements), so this
would additionally allow element-level nullability (`List<Vessel?>` vs `List<Vessel>?`) and
fold the parameter/return nullability split into one field. Kept slot-level instead:

- **The recursive capability has no producer.** `[KRPCNullable]` is
  `AttributeTargets.Parameter`; there is no way to annotate the `T` in `List<T>`, so the
  scanner would only ever set `nullable` at the top level — exactly what `Parameter.nullable`
  already expresses — while adding a never-populated `nullable` to every nested element
  `Type`.
- **Nullability is a property of the slot, not the structural type.** `Vessel` is not
  inherently nullable; a given parameter/return of type `Vessel` is. Keeping `nullable` on
  `Parameter`/`Procedure` matches that and leaves `Type` a clean structural descriptor.
- **Consistency:** the field would have to move for returns too (`return_type.nullable`),
  a wider protocol and client change for a purely conceptual tidy — the internal server
  model (`ProcedureParameter.Nullable`, handler `ReturnIsNullable`) is unaffected either way.

`Type.nullable` becomes the right schema only if kRPC later wants genuine nullable
collection elements, which needs a new source-level annotation and is out of #843's scope.

## Server changes (`core/`)

1. **`Encoder.cs:28-29`** — remove the null branch (`WriteUInt64(0)`); `Encode(null)`
   becomes an internal error (`ArgumentNullException`). Null never reaches the encoder.
2. **`MessageExtensions.cs:33-41`** (`ProcedureResult.ToProtobufMessage`) — when
   `procedureResult.HasValue && procedureResult.Value == null`, set `IsNull = true`
   instead of calling `Encoder.Encode`. The internal message layer already models null
   correctly (`core/src/Service/Messages/ProcedureResult.cs:8-14` sets `HasValue` on any
   assignment, including null), so no change upstream of this point. Streams flow through
   the same method (`MessageExtensions.cs:61-67`), so no stream-specific work — and the
   existing stream change-detection already handles null transitions
   (`ProcedureCallStream.cs:56-65`).
3. **`MessageExtensions.cs:100-109`** (`Parameter.ToProtobufMessage`) — set
   `HasDefaultValue` from `parameter.HasDefaultValue`; when the default is null set
   `DefaultValueIsNull = true`; otherwise set `DefaultValue = Encoder.Encode(...)` as now.
4. **Argument decoding** — where `Argument` messages are converted for execution
   (`core/src/Server/ProtocolBuffers/MessageExtensions.cs`, ProcedureCall path): map
   `is_null = true` → null argument value, skipping `Decoder.Decode`.
5. **`Services.cs` null validation** — null acceptance depends only on the nullable flag:
   - `CheckReturnValue` (L370-389): remove the `!IsAClassType` gate (L378) that rejects a
     null non-class return before the nullability check, so `returnValue == null` is
     accepted for any type when `ReturnIsNullable` and rejected otherwise.
   - `GetArguments` (L342-363) / `SetArguments` (L290-313): replace the
     `value == null && !IsAClassType(type)` check with `value == null && !parameter.Nullable`
     — null accepted iff the parameter is nullable, for every type; the class special case
     is dropped.
   - Expression API: the design expected a separate `nullAllowed = ReturnIsNullable &&
     IsAClassType` gate in `Expression.cs`, but no such gate exists — `Expression.Call`
     executes the RPC through `ExecuteCall` → `CheckReturnValue`, so removing the
     `IsAClassType` gate in `CheckReturnValue` (above) already lets a marked-nullable
     *reference-type* return flow through the expression path. The one `Expression.cs` change
     is for nullable *value-type* returns: `Expression.Call` converts the result to
     `Nullable<T>` so a null value is representable rather than faulting (Open question 2).
6. **Property setter nullability** (`core/src/Service/Scanner/ServiceSignature.cs`): the
   setter's synthesized `value` parameter is registered non-nullable. Derive its nullability
   from the property's `Nullable` flag instead (the getter already uses `GetNullable(property)`),
   so a `[KRPCProperty(Nullable = true)]` setter accepts null and a plain one rejects it. This
   is the only way to mark a setter argument nullable — the `value` parameter is synthesized
   and cannot carry `[KRPCNullable]`. **This spans both kinds of property**, each with its own
   handler and scan path: **class** properties (`AddClassProperty` → `ClassMethodHandler`) and
   **service-level** properties (`AddProperty` → `ProcedureHandler`). Both handlers gained a
   `SetValueParameterNullable()` that the setter path calls when the property is nullable.

   > The original design named only `AddClassProperty`, assuming the null-clearing
   > `SpaceCenter.Target*` setters were class properties. They are **service-level** static
   > properties (`SpaceCenter` is the service class), so they scan through `AddProperty` /
   > `ProcedureHandler`; without the service-property fix the server would reject
   > `TargetVessel = null` (their setters' `value` parameter would stay non-nullable). Both
   > paths are fixed in phase 2.
7. **`KRPCNullableAttribute`** (`core/src/Service/Attributes/KRPCNullableAttribute.cs`)
   is already type-agnostic and `ProcedureParameter.cs` already supports null defaults
   (`DBNull.Value` marks *no* default, so `null` is a valid default). The scanner changes are:
   the setter-nullability plumbing (item 6); deriving `Nullable` from a null default in the
   `ProcedureParameter(ParameterInfo)` constructor (the null-default-implies-nullable rule
   above); and unwrapping `Nullable<T>` value-type parameters/returns to their underlying `T`
   with `nullable`/`return_is_nullable` set, in `ProcedureParameter` and `ProcedureSignature`
   (the `Nullable<T>` rule above).
8. **Serialized signature / ServiceDefinitions JSON**
   (`core/src/Service/Scanner/ParameterSignature.cs:62-63`, `GetObjectData`): emit
   `default_value` as JSON `null` when the default is null (today it round-trips the
   `0x00` sentinel through `Encoder.Encode(null)`); keep omitting the key when there is
   no default. This is what krpctools/clientgen consumes.
9. **`KRPC.GetServices`** (`core/src/Service/KRPC/KRPC.cs:80-85`) — carries the internal
   `Messages.Parameter`; change is entirely in `ToProtobufMessage` (item 3).

Note the C# server's protobuf runtime stays at 3.10.1; plain bool fields serialize fine.

**Service-side changes (`service/*`, outside `core/`):**

10. **Mark null-accepting parameters.** Every parameter that legitimately accepts null must
    be nullable — previously implicit for class types. The population is small and known:
    the null-clearing property setters `SpaceCenter.TargetBody`/`TargetVessel`/
    `TargetDockingPort` (already `Nullable = true`, so covered once item 6 lands) and the
    existing `[KRPCNullable] … = null` method parameters. Sweep the services to confirm none
    is missed; a missing marker turns a previously-valid null argument into an
    `RPCException`. `**Breaking:**` for any affected RPC.
11. **Remove redundant manual null guards.** ~58 handwritten
    `if (ReferenceEquals(value, null)) throw new ArgumentNullException(...)` checks on
    non-nullable class parameters (all in SpaceCenter — `ReferenceFrame`, `Orbit`, `Vessel`,
    `CelestialBody`, `Part`, … method args and non-nullable setters) become unreachable once
    the server rejects null centrally; delete them. **Keep** the two guards on properties
    that are nullable for reads but must reject a null write (`Camera.FocussedVessel`/
    `FocussedBody`) — item 6 makes their setter accept null, so the guard is the
    enforcement. Removed cases change the client-visible error from `ArgumentNullException`
    to the central `RPCException`.

## Client changes

The rule for every client: **decode** — if `is_null` → null; otherwise decode `value`
bytes as today (zero-length bytes are a valid encoding of empty collections). **encode** —
null argument → set `is_null`, leave `value` unset. **defaults** — use `has_default_value`
/ `default_value_is_null`. The legacy id-0/`b"\x00"` sentinel is neither emitted nor
accepted; a null value is signaled purely by `is_null` on the wire. Clients keep their own
in-memory null representation for class objects (a null object handle), but never read or
write it as a wire sentinel.

### Python (`client/python/krpc/`)

- `service.py:318-335` — `param_required = [not p.has_default_value ...]`; default
  extraction: `None` if `default_value_is_null`, else decode when `has_default_value`.
- `client.py:221-227` — check `response.results[0].is_null` before decoding.
- `streammanager.py:173-176` — same check on `result.result.is_null`.
- `encoder.py:42-52` / argument building in `client.py` — `None` argument → `is_null`
  on the `Argument`; remove the class-only `object_id = 0` encode special case for None,
  and remove the id-0 → None (`decoder.py:63-66`) and `b"\x00"` collection sentinel
  (`decoder.py:69-91`) decode paths.
- Type stubs / `Optional[...]` handling already exists for nullable params, including
  value-type nullables (`Optional[int]`).

### Lua (`client/lua/krpc/`)

- `service.lua:77,80` — switch from `HasField('default_value')` to the
  `has_default_value` / `default_value_is_null` fields.
- `client.lua:51-59` — check `result.is_null` before `decoder.decode`.
- `encoder.lua` / `decoder.lua` — same encode/decode rules as Python, including removing
  the id-0 / `b"\x00"` null decode paths.

### C# (`client/csharp/`)

- `Connection.cs:146-166` (`Invoke`) and `StreamManager.cs:90-98` return the raw
  `ByteString` today; thread the `is_null` flag through (e.g. return the
  `ProcedureResult` or a (bytes, isNull) pair) and have `Encoder.Decode` produce null.
- `Encoder.cs:186-192` — remove the id-0 → null decode path; encode side: null argument →
  `is_null` instead of `WriteUInt64(0)`.
- Nullable **reference-type** returns/params (`string`, `IList<T>`, class types) carry
  `null` naturally, no signature change. Nullable **value-type** returns/params (`int`,
  `float`, `bool`, enums) need the nullable form `T?` (`Nullable<T>`) in the generated
  signature — a clientgen change (below).

### Java (`client/java/`)

- `Connection.java:199-235`, `StreamManager.java:74-76`, `Encoder.java:111-158,340-347` —
  same shape as C#, including removing the id-0 → null decode path. Reference-type
  nullables carry `null` naturally; nullable **value-type** returns/params take the boxed
  type (`Integer`, `Double`, `Boolean`) instead of the primitive — a clientgen change.

### C++ (`client/cpp/`)

- `client.cpp:53-70` — surface `is_null` from the invoke path;
  `decoder.hpp` gains an overload for nullable decode.
- **Class types**: a null class object is signaled by `is_null` on the wire and
  represented in-memory as an `Object<T>` with `_id == 0` (`include/krpc/object.hpp:21-22`)
  — an internal representation, not a wire sentinel; no API change for the many existing
  nullable-class procedures.
- **Non-class nullable returns/params** (value and collection types): generated signatures
  become `std::optional<T>` (clientgen `cpp.py` / `cpp.tmpl:9-13`). `std::optional` is not
  currently used anywhere in the client, but both build paths are already C++17
  (`.bazelrc:1`, `client/cpp/CMakeLists.txt.tmpl:4-5`), so it is available.
- Null arguments: nullable parameters take `std::optional<T>` (non-class) or an id-0
  `Object<T>` (class).

### cnano (`client/cnano/`)

- `krpc_result_t` (`include/krpc_cnano/decoder.h:17-21`) gains an `is_null` flag,
  populated when decoding `ProcedureResult` (`src/decoder.c:18-35` — note nanopb only
  invokes the value callback when the field is present, so absent-value handling is
  natural here).
- Class types: null is signaled by `is_null` on the wire and represented as
  `krpc_object_t` 0 (`types.h:26`) in-memory.
- Non-class nullable returns (value, string, collection): generated stubs for procedures
  with `return_is_nullable` take an extra `bool * returnValueIsNull` out-parameter, inserted
  immediately after `returnValue`. It is set `true` when the result is null and `*returnValue`
  is then left untouched; like `returnValue` it may be passed `NULL` if the caller does not
  need it. A uniform flag (rather than a per-type in-band sentinel) is used so a null return
  is distinguishable from an empty collection or an empty string. **Class** nullable returns
  keep the existing `krpc_object_t` out-parameter and signal null as `KRPC_NULL` (0) — no
  extra parameter, no change to existing nullable-class procedures. (Resolves Open question 1;
  the new-error-code alternative was rejected because a null result is a valid value, not an
  error, and would trip `KRPC_CHECK`.)
- Nullable **arguments**: every non-class nullable argument is a pointer, where `NULL` means
  null. String and collection arguments are already pointers (`const char *`,
  `const krpc_..._t *`), so they need no signature change; a nullable **value-type** argument
  (`int?`, `float?`, `bool?`, enum) changes from by-value to `const T *`. A null argument is
  encoded as `is_null` with the value unset. **Class** nullable arguments pass `KRPC_NULL` (0),
  also encoded as `is_null`.

### clientgen / krpctools (`tools/krpctools/`)

- `generator.py:52-55` — the JSON path keys on `"default_value" in parameter`, which is
  already presence-correct (the JSON producer keys on `HasDefaultValue`); extend to treat
  JSON `null` as a null default (`utils.py:59-66` `decode_default_value`).
- Emit nullable surface for **all** types, driven by the `nullable` / `return_is_nullable`
  flags: Python already emits `Optional[...]` (`clientgen/python.py:72-102,236-278`); add
  C++ `std::optional` per above; C# emits `T?` and Java the boxed type (`Integer`, …) for
  nullable **value-type** returns/params (reference-type nullables need no signature
  change); cnano per its section.
- Regenerate golden fixtures `krpctools/test/clientgen-TestService-*.txt`.

## Documentation

`doc/src/communication-protocols/messages.rst`:
- `ProcedureResult` (L103-123), `Parameter` (L391-413) and `Argument` field docs — add
  the three new fields and the null/presence semantics table.
- Protobuf-encoding section (L156-168) and Proxy Objects section (L603-611): document that
  null is signaled by `is_null`; remove any description of object id 0 / `0x00` as a null
  encoding — it is neither emitted nor accepted.

## Tests

- **TestService** (`tools/TestServer/src/TestService.cs`) additions:
  - a procedure with an **empty-collection default** (`[KRPCDefaultValue]` empty list) —
    regression test for the core #824 bug; no such case exists today.
  - nullable **string**, **list** and **value-type** returns (e.g.
    `EchoNullableString(string)` and `EchoNullableInt(int)` with `Nullable = true`), and
    nullable non-class **parameters** (a value type and a collection) accepting null.
  - a nullable **class parameter** marked `[KRPCNullable]` plus a non-nullable class
    parameter, to confirm null is now *rejected* without the marker.
  - a **nullable property** whose setter accepts null and a property whose setter rejects
    null (mirroring `SpaceCenter.TargetVessel` vs `Camera.FocussedVessel`), covering the
    property-setter nullability change (item 6).
- **Core tests**: `ScannerTest.cs` / `MessageAssert.cs` (`HasParameterWithDefaultValue`,
  L30-37) extended for the new message fields; `Services` tests for the null-validation
  changes — a nullable non-class return accepted, a null argument to an unmarked class
  parameter now *rejected*, null accepted only when `Nullable`; encoder test that
  `Encode(null)` throws.
- **Client suites**: each client gets null-return/null-argument/empty-collection-default
  tests mirroring the existing `EchoTestObject`/`OptionalArguments` patterns
  (`client/python/krpc/test/test_client.py:110-128,302-327`, C#
  `ConnectionTest.cs:105,145-159`, Java `ConnectionTest.java:149`, cnano
  `test_client.cpp:100,162-171`, plus stream variants).
- **Conformance suites**: re-run `client/websockets/.../test_websockets.py` and
  `client/serialio/.../test_serialio.py` (they read `results[0].value` directly and
  need `is_null`-aware assertions for the new test procedures).
- **In-game (`service/SpaceCenter/test/`)**: regression that `target_vessel = None` (and
  `target_body` / `target_docking_port`) still clears the target, and that
  `focussed_vessel = None` / `focussed_body = None` still error — the null-accepting vs
  null-rejecting setter split.
- **Revert the #824 workaround**: restore optional `crew` on `LaunchVessel`
  (`service/SpaceCenter/src/Services/SpaceCenter.cs`) with an empty-list default, and
  remove the explicit `new List<string>()` pass-throughs in
  `LaunchVesselFromVAB`/`LaunchVesselFromSPH`.

## Implementation phases

Distinct, independently-committable phases. **Full CI need not be green between phases** —
the tree is intentionally broken for clients from the moment the protocol changes in phase 2
until each client's phase lands. Each phase carries its own tests, which should pass at the
end of that phase.

**Phase 1 — protobuf schema.** ✅ *Done.* `protobuf/krpc.proto` (the `is_null`, `has_default_value` and
`default_value_is_null` fields) plus the matching protocol docs
(`doc/src/communication-protocols/messages.rst`, per the Documentation section). Fields are
additive and unused, so the schema regenerates at build time. (One cnano encoder golden test
does start failing here — cnano builds its `Argument` on an un-zeroed struct, so the new
`is_null` bool serializes uninitialized memory — but per the phasing that break is expected
and is fixed when cnano lands in phase 6c.)

**Phase 2 — core server + core tests.** ✅ *Done.* All `core/` changes (Server changes items 1–9):
Encoder, `MessageExtensions`, `Services.cs` validation, property-setter nullability
(`ServiceSignature.cs` / `ClassMethodHandler.cs` / `ProcedureParameter.cs`), signature JSON.
Core tests (`ScannerTest`, `Services`, `MessageExtensions`, `Encode(null)` throws). At the end
the server speaks the new protocol and enforces explicit nullability — **every client is now
broken until its phase lands.**

> Implementation notes:
> - The expression path routes reference-type null returns through `CheckReturnValue` (no gate
>   change needed), and the one `Expression.cs` change makes a nullable value-type return
>   evaluate as `Nullable<T>` (see item 5, resolves Open question 2).
> - Property-setter nullability was plumbed by making `ProcedureParameter.Nullable` settable
>   within the assembly and adding `SetValueParameterNullable()` to **both** handlers —
>   `ClassMethodHandler` (class properties) and `ProcedureHandler` (service-level properties) —
>   called from the setter path in `AddClassPropertyMethod` / `AddPropertyProcedure`. The
>   service-property path is the design correction noted in item 6 (covers `SpaceCenter.Target*`).
> - Core-test coverage exercises the nullability change across every member kind and combination:
>   nullable service procedure param+return (`EchoNullableString`, `EchoTestObject`), nullable
>   class **instance** method (`EchoNullableObject`), nullable class **static** method
>   (`StaticNullableMethod`), nullable **service-level** (static) property (`NullableProperty`,
>   getter return + setter accepting null), nullable **class** property setter (`ObjectProperty`),
>   and a parameter made nullable **implicitly by a null default** (`ProcedureOptionalNullArg`,
>   `X x = null` — omit → default null, or pass null explicitly), and **`Nullable<T>` value-type**
>   params+returns implicitly nullable with no marker (`EchoNullableInt` for `int?`,
>   `EchoNullableEnum` for `TestEnum?` — covering both encoder branches, numeric and enum), and
>   an explicitly-marked **nullable collection** (`EchoNullableList`, `[KRPCNullable] IList<string>`
>   — collections are reference types, so nullable via marker not `Nullable<T>`), plus
>   null-rejection tests for the non-nullable counterparts. `EchoTestObject`'s param was marked `[KRPCNullable]` (it relied
>   on the dropped implicit class-nullability). `MessageAssert` gained `HasNullableParameter` and
>   `HasNullableParameterWithDefaultValue`; `HasParameter` now also asserts *not* nullable.
>   (There is no "static class property" form to cover — kRPC class properties must be non-static
>   and service properties must be static, so `NullableProperty` is the static-property case.)
> - The expected client-toolchain break lands here, not only in the clients: `clientgen`'s
>   `decode_default_value` faults on the JSON `null` default now emitted for existing
>   null-default params (TestService `OptionalArguments`, SpaceCenter `[KRPCNullable] … = null`),
>   breaking every client's codegen until the shared krpctools fix in phase 4.

**Phase 3 — TestService.** ✅ *Done.* The new test procedures (Tests section): empty-collection
default, nullable string/list/value-type returns, nullable non-class and class parameters,
and the null-accepting vs null-rejecting property setters. No client exercises them yet.

> Implemented in `tools/TestServer/src/TestService.cs`, covering nullability across the whole
> member-kind matrix (service procedure, service property, class instance method, class static
> method, class property), each with a nullable and a non-nullable case:
>
> | Member kind | nullable | non-nullable / rejects null |
> |---|---|---|
> | Service procedure | `EchoNullableString`, `EchoNullableList` (`IList<int>`), `EchoNullableInt` (`int?`), `EchoTestObject` | `NotNullableObject`, `ReturnNullWhenNotAllowed` |
> | Service property | `ObjectProperty` (setter accepts null), `NullableObject` (setter guards null) | `StringProperty` |
> | Class instance method | `EchoNullableObject`, `ObjectToString` (nullable param) | `FloatToString` |
> | Class static method | `StaticNullableObject` | `StaticMethod` |
> | Class property | `TestClass.ObjectProperty` | `TestClass.IntProperty`, `StringPropertyPrivate*` |
>
> Plus `EmptyListDefault` (`[KRPCDefaultValue]` empty list — the #824 regression; serializes
> with the `default_value` key present and empty, i.e. `has_default_value` set on the wire) and
> `OptionalArguments` (class parameter nullable via a null default). `EchoNullableInt` serializes
> as `SINT32` with `nullable`/`return_is_nullable` set, confirming the `Nullable<T>` unwrapping
> end-to-end. `NullableObject` mirrors `Camera.FocussedVessel` (nullable for reads, setter
> rejects null); `ObjectProperty` mirrors `SpaceCenter.TargetVessel` (setter accepts null).
> Verified by building TestServer and inspecting the generated service definition; the client
> suites that exercise these land in phases 4 and 6.

**Phase 4 — Python client + shared krpctools path.** ✅ *Done.* Python client decode/encode/default
rules; the shared krpctools JSON-`null`-default handling (`generator.py` / `utils.py`) and
`.pyi` value-type-nullable stubs. Tests: Python client suite plus the websockets/serialio
conformance suites (they read `results[0].value` directly). First end-to-end validation of
the protocol against the phase-2 server via `TestServer`.

> Implementation notes:
> - **Shared krpctools:** `decode_default_value` (`utils.py`) returns `None` for a JSON `null`
>   default; the Python default-value formatter checks `None` before the string case. This
>   unblocks `clientgen` for *every* language (they all faulted on the null default since phase
>   2). The other languages' `parse_default_value` already tolerate `None` (C#/C++ emit their
>   null literal, Java uses overloads, cnano has no defaults), so their golden fixtures could be
>   regenerated even though their value-type-nullable *signatures* wait for phase 6.
> - **Python client:** null is signaled purely by `is_null` — `client._invoke` and
>   `streammanager.update` yield `None` when it is set; `_build_call` sets `is_null` for a `None`
>   argument. The id-0 class sentinel and the `b"\x00"` collection sentinels are removed from the
>   decoder, and the `None → id 0` case from the encoder. `service._parse_procedure` keys required
>   and default on `has_default_value` / `default_value_is_null`.
> - **A phase-2 gap surfaced here:** the stream write path (`StreamStream.cs`) hand-builds its
>   `ProcedureResult` for speed and bypasses `ToProtobufMessage`, so it still called
>   `Encoder.Encode` on a null stream value and crashed the stream server. Fixed to set `is_null`
>   (committed to `core`). The `test_nullable_stream` case caught it.
> - **Behavioral change made visible:** passing `None` to a non-nullable parameter (e.g. a
>   non-nullable collection) now sends `is_null` and is rejected by the server (`RPCError`) rather
>   than failing a client-side coercion (`TypeError`) — uniform server enforcement. The guarded
>   nullable setter (`NullableObject`) surfaces the service's `ArgumentNullException` as
>   `ValueError`. Tests updated; the obsolete id-0 sentinel unit tests were removed.
> - Golden `clientgen-*`/`docgen-*` fixtures regenerated for all languages.

**Phase 5 — services audit + revert workarounds** ✅ *Done.* (`service/*`, Server changes items 10–11;
depends only on phase 2). Confirm every null-accepting parameter is nullable (Target*
covered by the property flag, existing `[KRPCNullable]` params); delete the ~58 redundant
manual null guards, keeping the load-bearing `Camera.Focussed*` two; revert the nullability
workarounds — the #824 `LaunchVessel.crew` empty-list hack and its `new List<string>()`
pass-throughs. In-game SpaceCenter tests (`target_vessel = None` clears, `focussed_vessel =
None` errors).

> Implementation notes:
> - **77 guards removed** (the ~58 estimate was low), all on non-nullable class parameters of
>   `[KRPCMethod]`/`[KRPCProcedure]` methods and non-nullable `[KRPCProperty]` setters — the bulk
>   being `referenceFrame`/`target`/`vessel`/`body` coordinate-transform and lookup args. **Kept**
>   guards in constructors, `GetHashCode`/`Equals`, extension methods and private helpers; on the
>   nullable-property setters `Camera.FocussedBody`/`FocussedVessel` (the enforcement) and
>   `SpaceCenter.ActiveVessel`; and on tuple-typed (not class) setters. Two files
>   (`AlarmManager.cs`, `WaypointManager.cs`) kept their `using System;` — still used elsewhere.
> - **The #824 revert is `[KRPCNullable] IList<string> crew = null`, not an empty-list default.**
>   The actual workaround (commit "Make LaunchVessel crew … non-optional") had turned a
>   *null-default nullable* param into a required one; the true revert restores that. Finding 1's
>   "empty-collection default" label for #824 was imprecise — but phase 2 fixed both null and
>   empty-collection defaults, and the empty-collection case is separately exercised by phase 3's
>   `EmptyListDefault`.
> - **Audit result: no missed markers.** The only candidate found — `ReferenceFrame.CreateHybrid`'s
>   `rotation`/`velocity`/`angularVelocity` (`= null`) — is already nullable via the
>   null-default-implies-nullable rule, so it needs no `[KRPCNullable]`. All other null-accepting
>   params are marked or have null defaults.
> - Verified in-game: `test_clear_target`, `test_target_body`, `test_target_vessel` (nullable
>   setters clear the target) and a new `test_focussed_rejects_null` all pass against a live game.

**Phase 6 — remaining clients, one sub-phase each.** ⏳ *Pending.* Each sub-phase updates that client's
decode/encode/default handling together with its clientgen generator and golden fixtures,
and passes its comms suite against the phase-2 server. (The phase-4 golden regeneration already
added the new procedures to every language's fixtures; each sub-phase below is the value-type
nullable *signature* work plus that client's runtime encode/decode changes.)
  - 6a — C# (`T?` value-type nullables) ✅ *Done.*
  - 6b — C++ (`std::optional`) ✅ *Done.*
  - 6c — cnano (nullable-return out-parameter — Open question 1) ✅ *Done.*
  - 6d — Java (boxed `Integer`/`Double`/… value-type nullables) ✅ *Done.*
  - 6e — Lua ✅ *Done.*

> Phase 6a (C#) implementation notes:
> - **Out-of-band null.** `Connection.Invoke` now returns the `ProcedureResult` (not the raw
>   `ByteString`), so generated stubs read `is_null` before decoding; `StreamManager` does the
>   same for stream updates. Argument building sets `Argument.is_null` when the encoder yields a
>   null `ByteString`. The legacy id-0 sentinel is gone from both the encoder (`null` argument →
>   `is_null`, not `WriteUInt64(0)`) and decoder (a class value is always instantiated; null is
>   never carried in the value bytes).
> - **`Nullable<T>` handling is localized.** `Encoder.Encode`/`Decode` unwrap `Nullable<T>` to `T`
>   (`Nullable.GetUnderlyingType`), so the generated signature can be `int?` while `typeof(int?)`
>   still encodes/decodes as `int`; the generated `return` emits an `if (_result.IsNull) return
>   null;` guard for any nullable return (value or reference type). Only genuine value types and
>   enums gain the `?`; `string`, `byte[]`, classes and collections stay as-is and carry null
>   naturally.
> - **Clientgen** (`csharp.py`/`csharp.tmpl`): value-type nullable params/returns get the `?`
>   suffix, `return_is_nullable` is threaded per member (procedures, class/static methods,
>   property getters), and the golden `clientgen-TestService-csharp.txt` was regenerated.
> - **Tests:** the C# comms suite (`ConnectionTest`/`StreamTest`) gained nullable
>   value/string/list/class returns and arguments, null-rejection on non-nullable params and
>   properties, the null-accepting vs null-guarding property setters, the empty-collection
>   default and a nullable stream; `EncoderTest`'s retired id-0 sentinel tests were dropped and a
>   `Nullable<T>` round-trip added. Passes against the phase-2 `TestServer`.

> Phase 6b (C++) implementation notes:
> - **Out-of-band null.** `Client::invoke` now returns the `ProcedureResult` rather than the raw
>   value bytes, so a generated call reads `is_null` before decoding. Argument encoding gained a
>   `krpc::encoder::Value` (encoded bytes + `is_null`); `build_call`/`build_request` take a
>   `std::vector<encoder::Value>` and set `is_null` on the wire. `StreamImpl` carries an `is_null`
>   flag (set by `StreamManager` from the update), and `Stream<T>::operator()` / callbacks skip
>   decoding when it is set.
> - **`std::optional<T>` for non-class nullables.** Nullable value, string, collection and enum
>   parameters/returns are generated as `std::optional<T>`; a `decode(std::optional<T>&)` overload
>   decodes the present value and `encode_nullable(const std::optional<T>&)` maps an empty optional
>   to `is_null`. **Nullable class** parameters/returns keep their class type: null is the id-0
>   `Object<T>`, `encode_nullable(const Object<T>&)` maps id 0 to `is_null`, and a null return
>   leaves the default (id-0) object. The generated `_result` is value-initialized so a null return
>   is the correct default without an uninitialized read.
> - **Clientgen** (`cpp.py`/`cpp.tmpl`): the `args` macro emits `encode_nullable` for nullable
>   parameters; `cpp.py` wraps non-class nullable param/return types in `std::optional` (procedures,
>   class/static methods, property getters) and the golden `clientgen-TestService-cpp.txt` was
>   regenerated.
> - **Tests:** the C++ comms suite gained nullable value/string/list/class returns and arguments,
>   null rejection on a non-nullable class parameter (an id-0 object the server decodes to null),
>   the null-accepting vs null-guarding property setters, the empty-collection default and a
>   nullable stream. (A non-nullable property cannot be passed null in statically-typed C++, so
>   that case has no C++ test.) Passes against the phase-2 `TestServer`.

> Phase 6d (Java) implementation notes:
> - **Out-of-band null.** `Connection.invoke` now returns the `ProcedureResult`, so calls read
>   `is_null` before decoding; `StreamManager` does the same for stream updates. `buildCall` sets
>   `is_null` on an argument whose encoded value is null. `Encoder.encode(null, …)` returns a null
>   `ByteString` for any type (the class id-0 encode branch is gone), and `decodeObject` no longer
>   maps id 0 to null (null is signaled by `is_null`, so decode only ever runs for a present value).
> - **Boxed value-type nullables.** Nullable value-type parameters and return values are generated
>   as the boxed type (`Integer`, `Double`, `Boolean`, …) so they can hold null; the generated
>   `return` emits an `if (_data.getIsNull()) return null;` guard for any nullable return. Reference
>   types (`String`, `byte[]`, classes, enums, collections) carry null naturally and are unchanged.
> - **Clientgen** (`java.py`/`java.tmpl`): value-type nullable params/returns use `type_map_classes`,
>   `return_is_nullable` is threaded into the return-type descriptor, and the golden
>   `clientgen-TestService-java.txt` was regenerated.
> - **Tests:** the Java comms suite gained nullable value/string/list returns and arguments, null
>   rejection on a non-nullable class parameter, the nullable class instance/static methods, the
>   null-accepting vs null-guarding property setters, and a nullable stream; `EncoderTest`'s retired
>   id-0 sentinel tests were dropped for a null-encode assertion. The Java client has no default-arg
>   support (all arguments are required), so the empty-collection default has no Java client test.
>   Passes against the phase-2 `TestServer`.

> Phase 6e (Lua) implementation notes:
> - **Out-of-band null.** Lua is dynamically typed with no generated stubs, so this is a
>   runtime-only change. `client._invoke` returns `Types.none` when the result's `is_null` is set;
>   `client._build_request` sends `is_null` for a `Types.none` argument (checked before the usual
>   type validation/coercion, which would otherwise reject it). `service._parse_procedure` reads
>   `has_default_value` / `default_value_is_null` instead of the `default_value` field's presence,
>   so a null default becomes `Types.none` and an empty-collection default is distinguished from no
>   default.
> - **Null representation.** `Types.none` is the uniform null value for every type (Lua `nil`
>   cannot be stored in argument lists). The decoder no longer maps object id 0 to `Types.none` or
>   an empty collection to `nil`, and the encoder no longer emits id 0 for a null class — null is
>   carried only by `is_null`. Lua has no stream support, so there is no stream change.
> - **Tests:** the Lua comms suite gained nullable value/string/list returns and arguments, null
>   rejection on a non-nullable class parameter, the nullable class instance/static methods, the
>   null-accepting vs null-guarding property setters and the empty-collection default; the retired
>   id-0 sentinel unit tests were dropped and the service/class member-list assertions updated for
>   the new procedures. Passes against the phase-2 `TestServer`.

> Phase 6c (cnano) implementation notes:
> - **Out-of-band null.** The result's `is_null` is read from the decoded `ProcedureResult`
>   (`krpc_result_t.message.is_null`); the value callback fires only when the value field is
>   present, so a null result leaves the buffer empty and is never decoded. `krpc_add_argument`
>   now sets `is_null = false` explicitly (the argument array is caller-allocated and was
>   previously left uninitialized — the phase-1 encoder golden-test break), and a new
>   `krpc_add_null_argument` sets `is_null = true` with the value callback left unset.
> - **Return shape** (resolved Open question 1). Non-class nullable returns take an extra
>   `bool * returnValueIsNull` out-parameter after `returnValue`, set from `is_null`; it may be
>   `NULL` if unwanted, and the value is decoded only when not null. Class nullable returns are
>   unchanged — null is `KRPC_NULL` (0) in the `krpc_object_t` out-parameter.
> - **Argument shape.** Each non-class nullable argument is a pointer where `NULL` means null:
>   string and collection arguments are already pointers (unchanged), and a nullable value-type
>   argument changes from by-value to `const T *`. Class nullable arguments pass `KRPC_NULL`.
>   The generated stub adds a null argument when the pointer is `NULL` (or the object is
>   `KRPC_NULL`), otherwise encodes the value as before.
> - **Clientgen** (`cnano.py`/`cnano.tmpl`): `generate_context_parameters` marks nullable
>   parameters (null-check expression, and the pointer type for value-type/enum args); return
>   types are annotated with `nullable`/`is_class`; the `return` and `parameters` macros emit the
>   `returnValueIsNull` out-parameter and the `KRPC_NULL` vs flag handling. The golden
>   `clientgen-TestService-cnano.txt` was regenerated. The object-id encode/decode primitives are
>   unchanged (id 0 ↔ `KRPC_NULL`), so their unit tests stand.
> - **Tests:** the cnano comms suite gained nullable value/string/list returns and arguments,
>   null rejection on a non-nullable class parameter, the nullable class instance/static methods,
>   and the null-accepting vs null-guarding property setters. The C client has no default-argument
>   support, so the empty-collection default has no cnano client test. Passes against the phase-2
>   `TestServer`; the previously-failing encoder golden test now passes.

**Final commit — changelogs.** ⏳ *Pending.* Per-component `CHANGELOG.md` entries (repo convention), as the
dedicated final commit before merging the PR.

## Open questions

1. **cnano nullable-return API shape** — *resolved (2026-07-24)*. Non-class nullable returns
   take an extra `bool * returnValueIsNull` out-parameter (set true on null); the new-error-code
   alternative was rejected because null is a valid value, not an error, and would trip
   `KRPC_CHECK`. Nullable value-type **arguments** become `const T *` (NULL = null), matching the
   string/collection arguments that are already pointers; class nulls use `KRPC_NULL` (0). See the
   [cnano client changes](#cnano-clientcnano).
2. **Nullable value-type returns in the expression API** — *resolved (phase 2)*.
   `Expression.Call` builds `LinqExpression.Convert(result.Value, returnType)`, which would
   fault converting a null `Value` to a value type; it now converts to `Nullable<T>` when the
   return is a nullable value type, so the null is representable. Exercised by `EchoNullableInt`
   / `EchoNullableEnum`.
