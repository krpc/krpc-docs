# Nullable values and default-value presence (issue #843)

**Status:** proposal — design agreed, not yet implemented (2026-07-03).

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
- **Uniform null rule: `is_null = true` ⇒ the value is null, for every type; the value
  bytes are unset and must be ignored.** The legacy id-0/`0x00` sentinel is retired on the
  encode side: the server and clients stop *emitting* it for null. This is a
  **protocol-breaking change** for already-released clients calling nullable-class RPCs
  (they throw on the missing value bytes); all bundled clients are updated in lockstep and
  the change is documented for third-party client authors.
- **Decode-side leniency is kept**: clients continue to *accept* object-id 0 (class types)
  and `b"\x00"` (collection types) as null, so new clients still work against 0.5.x/0.6.0
  servers.
- **Scope: full.** (a) default-value presence fix (revert the #824 workaround);
  (b) null returns and null defaults for all types; (c) null **arguments** for nullable
  parameters (presence on `Argument` too); (d) nullable API surface in the C++ and cnano
  clients.
- **Nullable semantics on parameters**: a null argument is legal iff the parameter is
  marked nullable **or** is a class type (the latter preserved for compatibility — the
  server has never enforced `Nullable` on class-typed arguments,
  `core/src/Service/Services.cs:274-277,329-333`). Null returns are legal iff the
  procedure is marked nullable, for any type — `CheckReturnValue`
  (`Services.cs:343-362`) currently rejects null for non-class types *before* consulting
  `ReturnIsNullable`; that ordering is fixed.

## Wire protocol changes (`protobuf/krpc.proto`)

```diff
 message Argument {
   uint32 position = 1;
   bytes value = 2;
+  // When true, the argument value is null; value must be unset and is ignored.
+  bool is_null = 3;
 }

 message ProcedureResult {
   Error error = 1;
   bytes value = 2;
+  // When true, the procedure returned null; value must be unset and is ignored.
+  bool is_null = 3;
 }

 message Parameter {
   string name = 1;
   Type type = 2;
   bytes default_value = 3;
   bool nullable = 4;
+  // When true, the parameter is optional. default_value holds the encoded default
+  // (which may legitimately be zero-length, e.g. an empty list), unless
+  // default_value_is_null is set.
+  bool has_default_value = 5;
+  // When true, the parameter's default value is null; default_value must be unset.
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

Version-skew behavior: old peers ignore the new bool fields. The remaining skew cases —
new client sending a null class argument to an old server, old client receiving a null
class result from a new server — fail with a decode error and are documented as requiring
matched versions for null-class traffic.

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
5. **`Services.cs` null validation**:
   - `CheckReturnValue` (L343-362): reorder so `returnValue == null && ReturnIsNullable`
     is accepted for any type; null with `!ReturnIsNullable` throws as today.
   - `GetArguments` (L329-333) / `SetArguments` (L274-277): accept null when the
     parameter is nullable **or** class-typed; reject otherwise.
6. **`KRPCNullableAttribute`** (`core/src/Service/Attributes/KRPCNullableAttribute.cs`)
   is already type-agnostic and `ProcedureParameter.cs:44-53` already supports null
   defaults (`DBNull.Value` marks *no* default, so `null` is a valid default) — no
   scanner changes expected beyond tests.
7. **Serialized signature / ServiceDefinitions JSON**
   (`core/src/Service/Scanner/ParameterSignature.cs:62-63`, `GetObjectData`): emit
   `default_value` as JSON `null` when the default is null (today it round-trips the
   `0x00` sentinel through `Encoder.Encode(null)`); keep omitting the key when there is
   no default. This is what krpctools/clientgen consumes.
8. **`KRPC.GetServices`** (`core/src/Service/KRPC/KRPC.cs:80-85`) — carries the internal
   `Messages.Parameter`; change is entirely in `ToProtobufMessage` (item 3).

Note the C# server's protobuf runtime stays at 3.10.1; plain bool fields serialize fine.

## Client changes

The rule for every client: **decode** — if `is_null` (or, from old servers, the legacy
id-0/`b"\x00"` sentinel) → null; otherwise decode `value` bytes as today (zero-length
bytes are a valid encoding of empty collections). **encode** — null argument → set
`is_null`, leave `value` unset. **defaults** — use `has_default_value` /
`default_value_is_null`; fall back to byte-truthiness of `default_value` when
`has_default_value` is false, for compatibility with old servers.

### Python (`client/python/krpc/`)

- `service.py:318-335` — `param_required = [not (p.has_default_value or p.default_value) ...]`;
  default extraction: `None` if `default_value_is_null`, else decode when
  `has_default_value` (or legacy truthiness).
- `client.py:221-227` — check `response.results[0].is_null` before decoding.
- `streammanager.py:173-176` — same check on `result.result.is_null`.
- `encoder.py:42-52` / argument building in `client.py` — `None` argument → `is_null`
  on the `Argument`; drop the class-only `object_id = 0` special case for None
  (keep decoding id 0 → None in `decoder.py:63-66` and the `b"\x00"` collection
  sentinel at `decoder.py:69-91` for old servers).
- Type stubs / `Optional[...]` handling already exists for nullable params.

### Lua (`client/lua/krpc/`)

- `service.lua:77,80` — switch from `HasField('default_value')` to the
  `has_default_value` / `default_value_is_null` fields (with the same legacy fallback).
- `client.lua:51-59` — check `result.is_null` before `decoder.decode`.
- `encoder.lua` / `decoder.lua` — same encode/decode rules as Python.

### C# (`client/csharp/`)

- `Connection.cs:146-166` (`Invoke`) and `StreamManager.cs:90-98` return the raw
  `ByteString` today; thread the `is_null` flag through (e.g. return the
  `ProcedureResult` or a (bytes, isNull) pair) and have `Encoder.Decode` produce null.
- `Encoder.cs:186-192` — keep id-0 → null decode for old servers; encode side: null
  argument → `is_null` instead of `WriteUInt64(0)`.
- Nullable non-class returns are reference types in the generated API (`string`,
  `IList<T>`, …) so `null` flows naturally; no signature changes required.

### Java (`client/java/`)

- `Connection.java:199-235`, `StreamManager.java:74-76`, `Encoder.java:111-158,340-347` —
  same shape as C#. Reference types throughout; no signature changes.

### C++ (`client/cpp/`)

- `client.cpp:53-70` — surface `is_null` from the invoke path;
  `decoder.hpp` gains an overload for nullable decode.
- **Class types**: keep the existing client-side null representation — an `Object<T>`
  with `_id == 0` (`include/krpc/object.hpp:21-22`); no API change for the many existing
  nullable-class procedures.
- **Non-class nullable returns**: generated signatures become `std::optional<T>`
  (clientgen `cpp.py` / `cpp.tmpl:9-13`). `std::optional` is not currently used anywhere
  in the client, but both build paths are already C++17 (`.bazelrc:1`,
  `client/cpp/CMakeLists.txt.tmpl:4-5`), so it is available.
- Null arguments: nullable parameters take `std::optional<T>` (non-class) or the id-0
  `Object<T>` (class, as today).

### cnano (`client/cnano/`)

- `krpc_result_t` (`include/krpc_cnano/decoder.h:17-21`) gains an `is_null` flag,
  populated when decoding `ProcedureResult` (`src/decoder.c:18-35` — note nanopb only
  invokes the value callback when the field is present, so absent-value handling is
  natural here).
- Class types: null ⇒ `krpc_object_t` 0 (`types.h:26`), as today.
- Non-class nullable returns: generated stubs (`clientgen/cnano.tmpl:22-35`) for
  procedures with `return_is_nullable` take an extra `bool * returnValueIsNull`
  out-parameter (exact shape to settle at implementation; cnano templates currently
  ignore nullability entirely).

### clientgen / krpctools (`tools/krpctools/`)

- `generator.py:52-55` — the JSON path keys on `"default_value" in parameter`, which is
  already presence-correct (the JSON producer keys on `HasDefaultValue`); extend to treat
  JSON `null` as a null default (`utils.py:59-66` `decode_default_value`).
- Emit nullable surface: Python already emits `Optional[...]`
  (`clientgen/python.py:72-102,236-278`); add C++ `std::optional` per above; C#/Java
  generators need no signature changes (optionally add `@Nullable`/`?` annotations —
  out of scope).
- Regenerate golden fixtures `krpctools/test/clientgen-TestService-*.txt`.

## Documentation

`doc/src/communication-protocols/messages.rst`:
- `ProcedureResult` (L103-123), `Parameter` (L391-413) and `Argument` field docs — add
  the three new fields and the null/presence semantics table.
- Protobuf-encoding section (L156-168) and Proxy Objects section (L603-611): document
  that null is signaled by `is_null`, that object id 0 / `0x00` is the **legacy**
  encoding still accepted by clients, and that servers no longer emit it.

## Tests

- **TestService** (`tools/TestServer/src/TestService.cs`) additions:
  - a procedure with an **empty-collection default** (`[KRPCDefaultValue]` empty list) —
    regression test for the core #824 bug; no such case exists today.
  - nullable **string** and **list** returns (e.g. `EchoNullableString(string)` with
    `Nullable = true`), and a nullable non-class **parameter** accepting null.
- **Core tests**: `ScannerTest.cs` / `MessageAssert.cs` (`HasParameterWithDefaultValue`,
  L30-37) extended for the new message fields; `Services` tests for the relaxed
  null-validation ordering; encoder test that `Encode(null)` throws.
- **Client suites**: each client gets null-return/null-argument/empty-collection-default
  tests mirroring the existing `EchoTestObject`/`OptionalArguments` patterns
  (`client/python/krpc/test/test_client.py:110-128,302-327`, C#
  `ConnectionTest.cs:105,145-159`, Java `ConnectionTest.java:149`, cnano
  `test_client.cpp:100,162-171`, plus stream variants).
- **Conformance suites**: re-run `client/websockets/.../test_websockets.py` and
  `client/serialio/.../test_serialio.py` (they read `results[0].value` directly and
  need `is_null`-aware assertions for the new test procedures).
- **Revert the #824 workaround**: restore optional `crew` on `LaunchVessel`
  (`service/SpaceCenter/src/Services/SpaceCenter.cs`) with an empty-list default, and
  remove the explicit `new List<string>()` pass-throughs in
  `LaunchVesselFromVAB`/`LaunchVesselFromSPH`.

## Implementation order

1. `protobuf/krpc.proto` + `messages.rst` (schema regenerates at build time; no
   generated code is checked in).
2. Server core (`core/`): MessageExtensions, Encoder, Services validation, signature
   JSON; core tests.
3. TestService additions.
4. Python client + krpctools shared decode path; Python/websockets/serialio suites.
5. Lua client.
6. C# and Java clients.
7. C++ client (std::optional) and cnano.
8. Clientgen golden fixtures; #824 revert.
9. CHANGES.txt entries for each component as the final commit before merging the PR.

## Open questions

1. **cnano nullable-return API shape**: extra out-parameter vs. a new error code — settle
   when implementing phase 7.
2. **Transition shim (currently rejected)**: with the flag mechanism the server *could*
   also emit the legacy `0x00` sentinel alongside `is_null = true` for class types at
   negligible cost, keeping all released clients working for one release cycle. The
   agreed design omits this (clean break, lockstep client update); flagging it here in
   case the compatibility calculus changes before release.
