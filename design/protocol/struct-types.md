# Structure types (issue #866)

**Status:** proposal — design agreed, not yet implemented (2026-07-03).

## Context

[Issue #866](https://github.com/krpc/krpc/issues/866): compound data is today either a
`KRPCClass` (server-side handle, one RPC per field access) or a positional tuple (by
value, but unnamed fields). Read-heavy compound values pay badly:
`SpaceCenter.launch_sites` costs 1 + 3n RPCs; pitch/roll/yaw is 3 RPCs. The proposal: a
`[KRPCStruct]` value type — named fields, serialized inline, no server-side handle.

Exploration shows structs decompose into two machineries that every client already has,
just never joined:

- **Value encoding = the Tuple pattern.** Collection values are encoded as wrapper
  messages of `repeated bytes items` (`protobuf/krpc.proto` `Tuple`/`List`/`Set`), with
  fully recursive element encoding — class handles inside collections already work
  (server `Encoder.WriteTuple`, `core/src/Server/ProtocolBuffers/Encoder.cs:83`;
  e.g. Python `encoder.py`/`decoder.py` tuple branches, C# `WriteTuple`/`DecodeTuple`
  `Encoder.cs:97-111,216-230`, Java javatuples `Encoder.java:251,382`, C++ generated
  `std::tuple` overloads, cnano generated per-tuple C structs, Lua tuple branch).
- **Named per-service types = the Class/Enumeration pattern.** `Type` carries
  `code` + `service` + `name` for `CLASS`/`ENUMERATION`; definitions ride the `Service`
  message; the scanner registers them via attribute passes
  (`core/src/Service/Scanner/Scanner.cs`, `ServiceSignature.AddClass/AddEnum`); dynamic
  clients build native types at runtime (Python `types.py` `_create_class_type` /
  `_create_enum_type`; Lua equivalents); clientgen/docgen emit them per language.
  Notably, **cnano already generates named-field C structs for every tuple type**
  (`cnano.tmpl:66-72`, fields `e0, e1, …`) — structs are that machinery with real names.

Two gotchas found:

1. **Stream change detection**: `ValueUtils.Equal` (`core/src/Service/ValueUtils.cs`)
   deep-compares lists/sets/dicts but falls through to `x.Equals(y)` for everything
   else. A C# struct containing a collection field would compare by field-wise
   reference equality → a stream on a struct-returning procedure would send an update
   every frame. Needs an explicit struct branch.
2. **Old dynamic clients fail at connect time, not call time**: Python
   `types.py Types.as_type()` ends in `raise ValueError("Invalid type")` and is run for
   *every* procedure's types during service creation (Lua identical,
   `types.lua:129`). Adding one struct-returning procedure to SpaceCenter therefore
   breaks *all* existing Python/Lua dynamic clients at connection, wholesale. Static
   clients (C#, C++, cnano) are unaffected (compile-time dispatch; old stubs simply
   lack the new procedure); Java's runtime TypeCode switch throws only if the new
   procedure is somehow invoked.

## Decisions

- **Wire encoding: the Tuple wire format, positional.** A struct value is encoded
  exactly like a tuple of its field values in declaration order (`repeated bytes
  items`; clients may literally reuse their Tuple codec). Field *names* live only in
  the service definition, exactly as class/enum names do.
  **Rejected: tagged protobuf-field encoding** (field numbers + wire types). It would
  buy per-field presence (nullable fields) and skip-unknown evolution, but requires
  every client to hand-roll tagged wire-format codecs, where the positional format
  reuses codecs all seven client implementations already have. Revisit only if
  nullable fields become a hard requirement.
- **Field evolution: append-only.** Decoders must ignore extra trailing items (newer
  server) and should error on missing items (mismatched definitions). Reordering,
  removing, or retyping fields is a breaking change to that struct.
- **Struct fields are non-nullable in v1.** No `[KRPCNullable]` on struct fields; the
  server raises an encode-time error on a null field value. Nullability of the struct
  *value itself* (as a return/argument/default) composes with #843's `is_null`
  mechanism for free. (Per-field presence is the tagged-encoding feature deliberately
  deferred.)
- **Authoring**: `[KRPCStruct]` on a public, non-generic **C# `struct`** (value
  semantics; enforced by `AttributeUsage(AttributeTargets.Struct)`), with `Service`
  resolution like `KRPCClassAttribute`. Fields are the **`[KRPCProperty]`-marked public
  instance properties with get+set**, in declaration order (matches the issue's
  sketch; explicit marking permits unexposed helper members). `Nullable`/`GameScene`
  on struct-field properties is a scanner error. At least one field required.
- **Field types**: any valid kRPC type — values, enums, class handles (the
  `CelestialBody Body` case), collections, and **other structs** (composability), with
  a scanner-time cycle check (a struct may not contain itself directly or
  transitively).
- **TypeCode `STRUCT = 102`** (objects range, next to CLASS/ENUMERATION), carrying
  `service` + `name`.
- **Compatibility stance**: adding struct definitions to the schema is additive, but
  the first struct *adopted* in a shipped service breaks old dynamic clients (gotcha 2)
  — accepted as part of the 0.6.0 protocol-improvements break (consistent with #843's
  clean-break decision), documented in the changelog. As mitigation **going forward**,
  the new Python/Lua clients gain graceful degradation: an unknown TypeCode in a
  service definition skips that procedure/entity with a warning instead of aborting
  service creation, so the *next* type-system addition won't repeat this.
- **Usage guidance** (docs, from the issue): structs are for compound values whose
  fields are almost always wanted together; keep `KRPCClass` for lazily-fetched or
  mutable state. Migrating an existing class/tuple API to a struct is a breaking
  change reserved for already-awkward APIs; new struct APIs are additive alongside
  existing members.

## Schema changes (`protobuf/krpc.proto`)

```proto
// Type.TypeCode — objects range
STRUCT = 102;

message Struct {
  string name = 1;
  repeated StructField fields = 2;
  string documentation = 3;
}

message StructField {
  string name = 1;
  Type type = 2;
  string documentation = 3;
}

// Service message
repeated Struct structs = 7;   // next free field
```

All additions are plain proto3 messages/fields/enum values — fine for the Unity
protobuf 3.10.1 pin and protobuf-lua. **Field-number coordination**: the #904 design
also claims `Service` field 7 (for `deprecated`); whichever lands first takes 7, the
other renumbers. #904's `deprecated`/`deprecated_reason` pair should also be added to
`Struct`/`StructField` when both features exist.

## Server changes (`core/`)

Insertion points (verified during exploration):

1. **Attribute**: new `core/src/Service/Attributes/KRPCStructAttribute.cs`
   (mirror `KRPCClassAttribute` — `Service` property; no `GameScene`).
2. **TypeUtils** (`core/src/Service/TypeUtils.cs`): `IsAStructType` (attribute check),
   `GetStructServiceName`, `ValidateKRPCStruct` (public, C# struct, valid identifier,
   ≥1 `[KRPCProperty]` field, field types `IsAValidType`, cycle check); wire into
   `IsAValidType` (L32) and `SerializeType` (~L560, `code = "STRUCT"` + service+name).
3. **Encoding** (`core/src/Server/ProtocolBuffers/Encoder.cs`): `WriteStruct` in the
   `EncodeObject` dispatch chain (L59-74) — reflect the declared `[KRPCProperty]`
   fields in declaration order, encode each recursively into a `Schema.KRPC.Tuple`;
   null field value → `ServiceException`. `DecodeStruct` beside `DecodeTuple` (L200) —
   type-directed by the struct's field list, constructing the C# struct via its
   property setters. Cache the reflected field list per struct type (encode runs per
   stream update).
4. **Stream equality** (`core/src/Service/ValueUtils.cs`): add an `IsAStructType`
   branch doing per-field recursion through `Equal` (gotcha 1).
5. **Scanner**: `StructSignature` + `StructFieldSignature`
   (`core/src/Service/Scanner/`, modeled on `EnumerationSignature` /
   `EnumerationValueSignature`, with `GetObjectData` emitting `name`/`fields`/
   `documentation` for the ServiceDefinitions JSON); `ServiceSignature.AddStruct` +
   `structs` in its `GetObjectData`; a `GetTypesWith<KRPCStructAttribute>` pass in
   `Scanner.cs`.
6. **Runtime messages**: `core/src/Service/Messages/Struct.cs` + `StructField.cs`;
   `Service.Structs`; copy loop in `KRPC.GetServices`
   (`core/src/Service/KRPC/KRPC.cs:92-108`); `ToProtobufMessage` conversions in
   `MessageExtensions.cs` (including the `Type` STRUCT branch at L191-195 region).

## Client changes

The shared prerequisite is `client/python/krpc/types.py`, because krpctools routes
**all** clientgen and docgen type parsing through it (`krpctools/utils.py as_type()`):
add `StructType` (holding service, name, ordered field names + types), a
`struct_type()` factory, registration hooks, and `_create_struct_type()` building a
`collections.namedtuple` (named access, tuple-compatible, immutable — right value
semantics).

- **Python dynamic**: `Types.as_type()` STRUCT branch; encoder/decoder branches
  mirroring the tuple branches (encode positionally from the namedtuple; decode items
  then construct it); `service.py` `_add_service_struct` loop over `service.structs`
  (beside `_add_service_class`, L305). Plus the graceful-degradation change: catch
  unknown-code errors during service construction, skip + `warnings.warn`.
- **Python static stubs** (`clientgen/python.py` + `.tmpl`): `struct_type(...)` in
  `parse_python_type`; the struct's name in type hints; a generated
  `typing.NamedTuple` declaration per struct and a `_structs` registry mirroring
  `_classes`.
- **C#** (`client/csharp/`): generated `public struct` with properties + a
  `[KRPCStruct]`-style marker attribute carrying field order; `Encoder.cs` gains
  `IsAStructType` + `WriteStruct`/`DecodeStruct` (reflection over the ordered
  properties, cached per type), modeled on the tuple paths (L79, L216-230).
- **Java** (`client/java/`): generated immutable POJO (fields, ctor, getters,
  `equals`/`hashCode`); `Encoder.java` `STRUCT` cases in the encode/decode TypeCode
  switches (L85-103, L154), instantiating via a `Types.createStruct` registration like
  the existing `createClass` pattern (`java.tmpl` `_Types`, L157).
- **C++** (`client/cpp/`): generated plain `struct` with public members and
  `operator==`; generated `encode`/`decode` overloads per struct (same cog/template
  mechanism as the `std::tuple` arities in `encoder.hpp:46-58` /
  `decoder.hpp:47-56`), emitted into the service header by `cpp.tmpl`.
- **cnano** (`client/cnano/`): reuse the tuple machinery
  (`clientgen/cnano.py` `_collection_types` / `build_collection_types`, `cnano.tmpl`
  L66-100) keyed by the struct's declared name with **named** members instead of
  `e0/e1`, plus per-struct `krpc_encode_*`/`krpc_decode_*` helpers — the closest
  existing analogue in any client.
- **Lua dynamic** (`client/lua/krpc/`): `types.lua` StructType + a small named-field
  class factory; decoder branch beside the tuple branch; `service.lua`
  `_add_service_struct`; same graceful-degradation change as Python.

## docgen

`nodes.py`: `Struct` + `StructField` nodes parsed from the JSON (`self.structs` beside
`self.classes`, L62-68); a `struct(x)` macro in each of the six `docgen/*.tmpl` files
modeled on the `class`/`enumeration` macro pair, listing fields with their types and
docs.

## Documentation

- `doc/src/communication-protocols/messages.rst`: the `STRUCT` TypeCode, the
  `Struct`/`StructField` definition messages, the positional Tuple-format value
  encoding, append-only evolution rule, non-nullable fields, and the note for
  third-party client authors (the issue explicitly calls this out).
- A short "structs vs classes" guidance section in the service-author docs
  (extending `doc/src/internals` or the service documentation) covering the
  when-to-use rules above.

## Tests

- **TestService** (`tools/TestServer/src/TestService.cs`): a `TestStruct` with a
  value field, a string field, an enum field, a `TestClass` (handle) field, and a
  list field; procedures modeled on the existing compound-type tests —
  `EchoStruct` round-trip (cf. `IncrementTuple`, L266), struct argument, struct
  default value via `[KRPCDefaultValue]` (cf. `TupleDefault`, L293), a list-of-structs
  procedure, a nested-struct type, and a counter-in-a-struct procedure for stream
  change-detection tests.
- **Core**: scanner tests (registration, validation errors: no fields, bad field
  type, cycle, nullable-on-field); encoder round-trip incl. class-handle and
  collection fields; `ValueUtils.Equal` struct branch; null-field encode error.
- **Clients**: per-client round-trip/argument/default/list-of-structs tests plus a
  stream-on-struct test (no spurious updates when unchanged — pins the
  `ValueUtils.Equal` fix); Python/Lua graceful-skip test (hand-crafted definition with
  an unknown code → warning, other procedures usable).
- **krpctools**: clientgen golden fixtures regenerate for all five languages; docgen
  fixture for the struct macro.

## Implementation order

1. Schema + protocol docs.
2. Server: attribute, TypeUtils, scanner/signatures, messages, encoder/decoder,
   `ValueUtils.Equal`; core tests; TestService additions.
3. Python client (dynamic) + `types.py` (unblocks krpctools) + graceful degradation.
4. krpctools: clientgen python/C#/Java/C++/cnano + docgen.
5. Remaining clients' runtime codecs (C#, Java, C++, cnano, Lua) + tests.
6. CHANGES.txt entries (core, all clients, krpctools) as the final pre-merge commit,
   noting the old-dynamic-client compatibility consequence.

First-adoption candidates (separate follow-up work, per the issue): a
`LaunchSiteInfo` struct for `SpaceCenter.launch_sites`, and an additive
`Control.pitch_roll_yaw` alongside the existing per-axis properties.

## Open questions

1. **Mutable or immutable client types**: namedtuple (Python) and immutable POJOs
   (Java) are proposed; if structs later become common as *arguments*, builder-style
   or mutable variants may be friendlier. Defer until adoption shows the need.
2. **`coerce_to` behavior** (Python/Lua): whether a plain tuple/list of the right
   arity is accepted where a struct is expected (the dynamic clients already coerce
   tuple↔list). Proposed: yes, positional coercion — cheap and convenient; confirm
   during implementation.
