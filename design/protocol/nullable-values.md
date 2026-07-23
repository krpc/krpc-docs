# Nullable values and default-value presence (issue #843)

**Status:** proposal — design agreed, not yet implemented (revised 2026-07-23).

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
- **Inference applies to parameter defaults only — returns and properties stay explicit.**
  The rule above is a purely *static* read of the declared default: `= null` is visible in the
  signature. Whether a method ever *returns* null is a property of its body, not its signature,
  and is not statically decidable — so **return nullability is never inferred**. It must be
  declared (`Nullable = true` on the procedure), and a null return from a procedure not so
  marked throws (`CheckReturnValue`). Properties have **no declared default value** in the kRPC
  model (there is no `[KRPCProperty(Default = …)]`), so the null-default rule cannot apply to a
  property either:
  - A property **getter is a return** — it requires explicit `[KRPCProperty(Nullable = true)]`
    exactly like a procedure return, and a null read from a non-nullable property throws. A C#
    auto-property that happens to hold `null` does not make it nullable; that would be inferring
    from runtime state, which is exactly what returns disallow.
  - A property **setter**'s synthesized `value` parameter takes its nullability solely from the
    same property flag (item 6); it can carry neither `[KRPCNullable]` nor a default.

  So a property is nullable — for reads and for writes — iff `Nullable = true` is set on it;
  there is no implicit path. This keeps property nullability symmetric between getter and setter
  and consistent with the explicit-return rule.
- **All types nullable.** `is_null` is type-agnostic, so value types (`int`, `float`,
  `bool`, enums) are nullable when marked, not just reference/class types; generated client
  signatures reflect this per language (see Client changes).
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
     `IsAClassType` gate in `CheckReturnValue` (above) already lets a marked-nullable return
     of any reference type flow through the expression path. No `Expression.cs` change was
     needed. Value-type nullable returns through expressions remain Open question 2,
     unexercised in phase 2.
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
   the setter-nullability plumbing (item 6) and deriving `Nullable` from a null default in the
   `ProcedureParameter(ParameterInfo)` constructor (the null-default-implies-nullable rule
   above).
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
- Non-class nullable returns: generated stubs (`clientgen/cnano.tmpl:22-35`) for
  procedures with `return_is_nullable` take an extra `bool * returnValueIsNull`
  out-parameter (exact shape to settle at implementation; cnano templates currently
  ignore nullability entirely).

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

**Phase 1 — protobuf schema.** `protobuf/krpc.proto` (the `is_null`, `has_default_value` and
`default_value_is_null` fields) plus the matching protocol docs
(`doc/src/communication-protocols/messages.rst`, per the Documentation section). Fields are
additive and unused, so the schema regenerates at build time. (One cnano encoder golden test
does start failing here — cnano builds its `Argument` on an un-zeroed struct, so the new
`is_null` bool serializes uninitialized memory — but per the phasing that break is expected
and is fixed when cnano lands in phase 6c.)

**Phase 2 — core server + core tests.** All `core/` changes (Server changes items 1–9):
Encoder, `MessageExtensions`, `Services.cs` validation, property-setter nullability
(`ServiceSignature.cs` / `ClassMethodHandler.cs` / `ProcedureParameter.cs`), signature JSON.
Core tests (`ScannerTest`, `Services`, `MessageExtensions`, `Encode(null)` throws). At the end
the server speaks the new protocol and enforces explicit nullability — **every client is now
broken until its phase lands.**

> Implementation notes:
> - No `Expression.cs` change was needed (see item 5) — the expression path routes through
>   `CheckReturnValue`.
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
>   `X x = null` — omit → default null, or pass null explicitly), plus null-rejection tests for
>   the non-nullable counterparts. `EchoTestObject`'s param was marked `[KRPCNullable]` (it relied
>   on the dropped implicit class-nullability). `MessageAssert` gained `HasNullableParameter` and
>   `HasNullableParameterWithDefaultValue`; `HasParameter` now also asserts *not* nullable.
>   (There is no "static class property" form to cover — kRPC class properties must be non-static
>   and service properties must be static, so `NullableProperty` is the static-property case.)
> - The expected client-toolchain break lands here, not only in the clients: `clientgen`'s
>   `decode_default_value` faults on the JSON `null` default now emitted for existing
>   null-default params (TestService `OptionalArguments`, SpaceCenter `[KRPCNullable] … = null`),
>   breaking every client's codegen until the shared krpctools fix in phase 4.

**Phase 3 — TestService.** The new test procedures (Tests section): empty-collection
default, nullable string/list/value-type returns, nullable non-class and class parameters,
and the null-accepting vs null-rejecting property setters. No client exercises them yet.

**Phase 4 — Python client + shared krpctools path.** Python client decode/encode/default
rules; the shared krpctools JSON-`null`-default handling (`generator.py` / `utils.py`) and
`.pyi` value-type-nullable stubs. Tests: Python client suite plus the websockets/serialio
conformance suites (they read `results[0].value` directly). First end-to-end validation of
the protocol against the phase-2 server via `TestServer`.

**Phase 5 — services audit + revert workarounds** (`service/*`, Server changes items 10–11;
depends only on phase 2). Confirm every null-accepting parameter is nullable (Target*
covered by the property flag, existing `[KRPCNullable]` params); delete the ~58 redundant
manual null guards, keeping the load-bearing `Camera.Focussed*` two; revert the nullability
workarounds — the #824 `LaunchVessel.crew` empty-list hack and its `new List<string>()`
pass-throughs. In-game SpaceCenter tests (`target_vessel = None` clears, `focussed_vessel =
None` errors).

**Phase 6 — remaining clients, one sub-phase each.** Each sub-phase updates that client's
decode/encode/default handling together with its clientgen generator and golden fixtures,
and passes its comms suite against the phase-2 server:
  - 6a — C# (`T?` value-type nullables)
  - 6b — C++ (`std::optional`)
  - 6c — cnano (nullable-return out-parameter — Open question 1)
  - 6d — Java (boxed `Integer`/`Double`/… value-type nullables)
  - 6e — Lua

**Final commit — changelogs.** Per-component `CHANGELOG.md` entries (repo convention), as the
dedicated final commit before merging the PR.

## Open questions

1. **cnano nullable-return API shape**: extra out-parameter vs. a new error code — settle
   when implementing phase 6c.
2. **Nullable value-type returns in the expression API**: phase 2 confirmed reference-type
   nullable returns flow through the expression path (via `CheckReturnValue`), but no
   value-type nullable return exists in `core` yet to exercise. `Expression.Call` builds
   `LinqExpression.Convert(result.Value, returnType)`, which would fault converting a null
   `Value` to a value type — revisit when a nullable value-type return is first added
   (phase 3 TestService / phase 6).
