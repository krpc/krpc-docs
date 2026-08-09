# Structure types (issue #866)

**Status:** proposal, design agreed, not yet implemented. Written 2026-07-03, revised
2026-08-09 against `main` after the v0.6.0 release and
[PR #1017](https://github.com/krpc/krpc/pull/1017) (nullable values). Issue
[#866](https://github.com/krpc/krpc/issues/866) is milestoned 0.7.0.

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
  (server `Encoder.WriteTuple` in `core/src/Server/ProtocolBuffers/Encoder.cs`;
  e.g. Python `encoder.py`/`decoder.py` tuple branches, C# `WriteTuple`/`DecodeTuple`,
  Java javatuples, C++ variadic `std::tuple` overloads, cnano generated per-tuple C
  structs, Lua tuple branch).
- **Named per-service types = the Class/Enumeration pattern.** `Type` carries
  `code` + `service` + `name` for `CLASS`/`ENUMERATION`; definitions ride the `Service`
  message; the scanner registers them via attribute passes
  (`core/src/Service/Scanner/Scanner.cs`, `ServiceSignature.AddClass/AddEnum`); dynamic
  clients build native types at runtime (Python `types.py` `_create_class_type` /
  `_create_enum_type`; Lua equivalents); clientgen/docgen emit them per language.
  Notably, **cnano already generates named-field C structs for every tuple type**
  (`cnano.tmpl`, fields `e0, e1, …`) — structs are that machinery with real names.

Four gotchas found:

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
3. **A struct type has to be built in two phases.** A `Type` message with code `STRUCT`
   carries only `service` + `name`; the field list lives in `Service.structs`, read
   separately. This is the shape `EnumerationType` already has (constructed from
   `as_type()` with `typ=None`, populated later by `set_values`), but the stakes are
   higher: for an enum the deferred data is cosmetic, since the wire value is an sint32
   either way, whereas for a struct the deferred field list *is* the decoder. Eager
   construction cannot work, because a procedure signature naming a struct may be parsed
   before, or in a different service from, the definition that describes it.
4. **A struct-typed default value forces struct definitions to be registered before
   procedures.** Decoding a default needs the field types, and unlike the enum case
   there is no way around it: `krpctools/utils.py decode_default_value` sidesteps
   `EnumerationType` by decoding it as sint32, which works only because the wire value
   is an sint32 whatever the enum turns out to be. Three places currently register
   definitions in an order that would not serve a struct default:
   - `docgen/nodes.py Service.__init__` builds its procedures, and with them the
     `Parameter` objects that decode their own defaults, **before** `self.classes` and
     `self.enumerations`.
   - `clientgen/generator.py generate_context` builds classes, enumerations and
     exceptions before procedures, so structs slot in ahead of the procedure loop
     without reordering anything, but `clientgen/__init__.py` loads every service's
     definitions and then hands the generator only `defs[args.service]`, so a struct
     defined in another service is not visible at all.
   - The dynamic clients create services one at a time (`client.py`, `client.lua`), so
     a struct belonging to a service created later is unregistered when an earlier
     service's procedure defaults are decoded. The Python client already solves exactly
     this for pre-generated stubs, registering their class and enum types in a first
     pass over every service before creating any dynamic one, with a comment saying so.

   The same latent ordering constraint exists today for a cross-service *enum* default;
   it has simply never been hit.

## Decisions

- **Wire encoding: the Tuple wire format, positional.** A struct value is encoded
  exactly like a tuple of its field values in declaration order (`repeated bytes
  items`; clients may literally reuse their Tuple codec). Field *names* live only in
  the service definition, exactly as class/enum names do.
  **Rejected: tagged protobuf-field encoding** (field numbers + wire types). It would
  buy per-field presence (nullable fields) and skip-unknown evolution, but requires
  every client to hand-roll tagged wire-format codecs, where the positional format
  reuses codecs all six client implementations already have. Revisit only if
  nullable fields become a hard requirement.
- **Field evolution: append-only.** Decoders must ignore extra trailing items (newer
  server) and should error on missing items (mismatched definitions). Reordering,
  removing, or retyping fields is a breaking change to that struct.
- **Struct fields are non-nullable in v1.** No `[KRPCNullable]` on struct fields; the
  server raises an encode-time error on a null field value. Nullability of the struct
  *value itself* (as a return/argument/default) composes for free with the `is_null`
  mechanism from [#843](https://github.com/krpc/krpc/issues/843), which landed in
  [PR #1017](https://github.com/krpc/krpc/pull/1017). (Per-field presence is the
  tagged-encoding feature deliberately deferred.)
- **Struct-typed default values are supported**, on the same footing as tuple and
  collection defaults. C# cannot express a non-constant default, so
  `[KRPCDefaultValue(typeof(Factory))]` names a static class with a static `Create()`
  returning the value; that is how `Tuple`, `IList`, `ISet` and `IDictionary` defaults
  are already written, and a struct needs nothing new. Server-side the value is
  encoded by the same `Encoder.Encode` path as any other struct value, so the whole
  cost lands on the client tooling as the registration ordering of gotcha 4. Worth
  paying: the ordering is a latent constraint for cross-service enum defaults already,
  and fixing it once retires the entire class of bug.
- **Authoring**: `[KRPCStruct]` on a public, non-generic **C# `struct`** (value
  semantics; enforced by `AttributeUsage(AttributeTargets.Struct)`), with `Service`
  resolution like `KRPCClassAttribute`. Fields are the **`[KRPCProperty]`-marked public
  instance properties with get+set**, in declaration order (matches the issue's
  sketch; explicit marking permits unexposed helper members). `Nullable`/`GameScene`
  on struct-field properties is a scanner error. At least one field required.
- **Field types**: any valid kRPC type — values, enums, class handles (the
  `CelestialBody Body` case), collections, and **other structs** (composability), with
  a scanner-time cycle check (a struct may not contain itself directly or
  transitively). A class-handle field is added to the object store on encode, exactly
  as one inside a tuple is, so "no server-side handle" describes the struct value
  itself and not its fields. The RPC saving is unaffected; the object-lifetime cost is
  the same as the tuple encoding it replaces.
- **TypeCode `STRUCT = 102`** (objects range, next to CLASS/ENUMERATION), carrying
  `service` + `name`.
- **Compatibility stance**: adding struct definitions to the schema is additive, but
  the first struct *adopted* in a shipped service breaks old dynamic clients (gotcha 2).
  Accepted as part of the 0.7.0 protocol break: that cycle already carries a breaking
  wire change from [PR #1017](https://github.com/krpc/krpc/pull/1017), where `is_null`
  replaced the object-id-0 null sentinel, so this rides an existing break rather than
  creating one. Documented in the changelog. As mitigation **going forward**,
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
  bool deprecated = 4;
  string deprecated_reason = 5;
}

message StructField {
  string name = 1;
  Type type = 2;
  string documentation = 3;
  bool deprecated = 4;
  string deprecated_reason = 5;
}

// Service message
repeated Struct structs = 9;   // next free field
```

All additions are plain proto3 messages/fields/enum values — fine for the Unity
protobuf 3.10.1 pin and protobuf-lua.

The `deprecated`/`deprecated_reason` pair from
[#904](https://github.com/krpc/krpc/issues/904) is no longer conditional: it shipped in
v0.6.0 and every other definition entity (`Service`, `Procedure`, `Class`,
`Enumeration`, `EnumerationValue`, `Exception`) carries it, with docgen and every
clientgen backend expecting it. `Struct` and `StructField` take it from the start,
read from `[Obsolete]` the same way. That work also took `Service` fields 7 and 8, so
`structs` is field 9.

## Server changes (`core/`)

Insertion points, re-verified against `main` on 2026-08-09:

1. **Attribute**: new `core/src/Service/Attributes/KRPCStructAttribute.cs`
   (mirror `KRPCClassAttribute` — `Service` property; no `GameScene`).
2. **TypeUtils** (`core/src/Service/TypeUtils.cs`): `IsAStructType` (attribute check),
   `GetStructServiceName`, `ValidateKRPCStruct` (public, C# struct, valid identifier,
   ≥1 `[KRPCProperty]` field, field types `IsAValidType`, cycle check); wire into
   `IsAValidType` and `SerializeType` (`code = "STRUCT"` + service+name, beside the
   `IsAClassType`/`IsAnEnumType` branches).
3. **Encoding** (`core/src/Server/ProtocolBuffers/Encoder.cs`): `WriteStruct` in the
   `EncodeObject` dispatch chain — reflect the declared `[KRPCProperty]`
   fields in declaration order, encode each recursively into a `Schema.KRPC.Tuple`;
   null field value → `ServiceException`. `DecodeStruct` beside `DecodeTuple` —
   type-directed by the struct's field list, constructing the C# struct via its
   property setters. Cache the reflected field list per struct type (encode runs per
   stream update).
4. **Stream equality** (`core/src/Service/ValueUtils.cs`): add an `IsAStructType`
   branch doing per-field recursion through `Equal` (gotcha 1). The fall-through to
   `x.Equals(y)` is still there, and C#'s default struct equality compares a
   collection-typed field by reference, so the spurious-update bug is real.
5. **Scanner**: `StructSignature` + `StructFieldSignature`
   (`core/src/Service/Scanner/`, modeled on `EnumerationSignature` /
   `EnumerationValueSignature`, with `GetObjectData` emitting `name`/`fields`/
   `documentation`/`deprecated`/`deprecated_reason` for the ServiceDefinitions JSON);
   `ServiceSignature.AddStruct` + `structs` in its `GetObjectData`; a
   `GetTypesWith<KRPCStructAttribute>` pass in `Scanner.cs`.

   `Scanner.cs` runs its passes in order: procedures, then classes, then enumerations,
   then exceptions. A struct pass appended to that list is fine, because
   `IsAValidType` is a pure attribute check and needs no registry, but it means field
   validation and the cycle check are reported at struct-registration time rather than
   when a procedure mentioning the struct is scanned. The pass must therefore validate
   every `[KRPCStruct]` type it finds, including ones no procedure references.
6. **Runtime messages**: `core/src/Service/Messages/Struct.cs` + `StructField.cs`;
   `Service.Structs`; copy loop in `KRPC.GetServices`
   (`core/src/Service/KRPC/KRPC.cs`, beside the `Classes`/`Enumerations` loops, which
   also copy the deprecation pair); `ToProtobufMessage` conversions in
   `MessageExtensions.cs`, including the `Type` STRUCT branch.

## Client changes

The shared prerequisite is `client/python/krpc/types.py`, because krpctools routes
**all** clientgen and docgen type parsing through it (`krpctools/utils.py as_type()`):
add `StructType`, a `struct_type()` factory, registration hooks, and
`_create_struct_type()` building a `collections.namedtuple` (named access,
tuple-compatible, immutable — right value semantics).

`StructType` is built in two phases, following `EnumerationType` (gotcha 3):
`as_type()` constructs it from `service` + `name` alone with no python type, and a
later `set_fields(fields)` supplies the ordered field names and types and creates the
namedtuple. Two consequences:

- Decoding a struct value is only possible once `set_fields` has run, so
  `_add_service_struct` must run during service construction beside
  `_add_service_class` and `_add_service_enumeration`, ahead of the procedures.
- A struct in one service referenced by a procedure in another must work whatever order
  the services are created in, which the lazy construction gives for free. Nothing may
  read a `StructType`'s fields at service-construction time.

The Python client is fully type-annotated and checked by basedpyright, so the new type
objects and the dynamically built namedtuple need annotations that pass; the existing
`ClassType`/`EnumerationType` handling of dynamically created types is the model.

- **Python dynamic**: `Types.as_type()` STRUCT branch; encoder/decoder branches
  mirroring the tuple branches (encode positionally from the namedtuple; decode items
  then construct it); `service.py` `_add_service_struct` loop over `service.structs`.
  Plus the graceful-degradation change: catch unknown-code errors during service
  construction, skip + `warnings.warn`.
- **Python static stubs** (`clientgen/python.py` + `.tmpl`): `struct_type(...)` in
  `parse_python_type`; the struct's name in type hints; a generated
  `typing.NamedTuple` declaration per struct and a `_structs` registry mirroring
  `_classes`.
- **C#** (`client/csharp/`): generated `public struct` with properties + a
  `[KRPCStruct]`-style marker attribute carrying field order; `Encoder.cs` gains
  `IsAStructType` + `WriteStruct`/`DecodeStruct` (reflection over the ordered
  properties, cached per type), modeled on the tuple paths.
- **Java** (`client/java/`): generated immutable POJO (fields, ctor, getters,
  `equals`/`hashCode`); `Encoder.java` `STRUCT` cases in the encode/decode TypeCode
  switches, instantiating via a `Types.createStruct` registration like the existing
  `createClass` pattern in `java.tmpl`'s `_Types`.
- **C++** (`client/cpp/`): generated plain `struct` with public members and
  `operator==`, plus an `encode`/`decode` overload per struct emitted into the service
  header by `cpp.tmpl`. Tuples are no longer cog-generated per arity: `encoder.hpp` and
  `decoder.hpp` now handle `std::tuple<Ts...>` with a single variadic template using
  `std::apply` and a fold expression. That makes the struct case simpler than
  originally planned, since each generated overload just names its own members in
  order, and no cog step is involved.
- **cnano** (`client/cnano/`): reuse the tuple machinery
  (`clientgen/cnano.py` `_collection_types` / `build_collection_types`, `cnano.tmpl`)
  keyed by the struct's declared name with **named** members instead of
  `e0/e1`, plus per-struct `krpc_encode_*`/`krpc_decode_*` helpers — the closest
  existing analogue in any client. cnano's cog-generated sources are covered by a test
  that they are up to date, which the struct work has to keep green.
- **Lua dynamic** (`client/lua/krpc/`): `types.lua` StructType + a small named-field
  class factory; decoder branch beside the tuple branch; `service.lua`
  `_add_service_struct`; same graceful-degradation change as Python.

### Default values

Rendering a decoded struct default into source is a direct copy of the tuple case.
Each `krpctools/lang/*.py` has a `parse_default_value` with a `TupleType` branch that
recurses over `typ.value_types` and wraps the results in the language's construction
syntax; the `StructType` branch recurses over the ordered fields instead and emits the
same construction the generated type declares — aggregate initialization in C++,
`new Foo(...)` in C# and Java, `Foo(...)` for the Python namedtuple. cnano needs
nothing: its `parse_default_value` returns `None`, because C has no default arguments.

Making the field types available at that point is the ordering work from gotcha 4:

- `clientgen/generator.py`: a `structs` loop in `generate_context` ahead of the
  procedure loop, calling `set_fields` on each. `Generator.types` is a class-level
  `Types()` shared by every generator in a run, so the registrations persist.
- `clientgen/__init__.py`: register the struct definitions of **every** service in the
  loaded definitions, not just the one being generated, so a struct default whose type
  belongs to another service resolves. A struct that is genuinely absent from the input
  should raise a clear error naming it, rather than failing inside the decoder.
- `docgen/nodes.py`: build `self.structs` before the procedures loop in
  `Service.__init__`, since `Parameter.__init__` decodes its own default value.
- Dynamic clients: register every service's structs in a first pass before creating any
  service, extending the pass `client.py` already runs to register the class and enum
  types of pre-generated stubs. `client.lua` needs the same.

## docgen

`nodes.py`: `Struct` + `StructField` nodes parsed from the JSON, held as `self.structs`
beside `self.classes`; a `struct(x)` macro in each of the six `docgen/*.tmpl` files
modeled on the `class`/`enumeration` macro pair, listing fields with their types and
docs.

`Service.__init__` in `nodes.py` takes `classes`, `enumerations` and `exceptions` as
positional parameters with the deprecation pair as keywords, and `Service.remove`
enumerates the same three dictionaries; both change, and `self.structs` has to be built
before the procedures loop for the reason in gotcha 4.

`docgen/csharp.py` and `docgen/cpp.py` override `default_value` with their own
tuple/list/set/dictionary recursion for rendering defaults in the docs, rather than
delegating to `lang/*.py` like `docgen/domain.py` does. Both need the `StructType`
branch too.

`//doc:check-documented` has six per-language targets and should be extended to cover
structs and their fields, so an undocumented field fails the build like an undocumented
RPC does.

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
  `EchoStruct` round-trip (cf. `IncrementTuple`), a struct argument, a nullable struct
  return, a `StructDefault` procedure with a `CreateStructDefault` factory (cf.
  `TupleDefault`/`CreateTupleDefault`), a list-of-structs procedure, a nested-struct
  type, and a counter-in-a-struct procedure for stream change-detection tests.
- **Core**: scanner tests (registration, validation errors: no fields, bad field
  type, cycle, nullable-on-field); encoder round-trip incl. class-handle and collection
  fields; `ValueUtils.Equal` struct branch; null-field encode error.
- **Clients**: per-client round-trip/argument/default/list-of-structs tests plus a
  stream-on-struct test (no spurious updates when unchanged — pins the
  `ValueUtils.Equal` fix); Python/Lua graceful-skip test (hand-crafted definition with
  an unknown code → warning, other procedures usable).
- **krpctools**: clientgen golden fixtures regenerate for all five languages; docgen
  fixture for the struct macro. Two ordering fixtures pin gotcha 4: a struct default
  whose type is declared in a service other than the one being generated, which fails
  without the cross-service registration pass, and one whose type is declared after the
  procedure that defaults to it.

## Implementation order

Following the shape [PR #1017](https://github.com/krpc/krpc/pull/1017) landed in, which
is the closest precedent for a change that crosses the schema and every client:

1. Schema: the `STRUCT` code, the `Struct`/`StructField` messages, `Service.structs`.
2. Server: attribute, TypeUtils, scanner/signatures, messages, encoder/decoder,
   `ValueUtils.Equal`; core tests.
3. Protocol documentation.
4. TestService struct types and procedures.
5. Python client (dynamic) + `types.py`, which unblocks krpctools, plus the
   first-pass struct registration in `client.py` and graceful degradation.
6. krpctools: the language-independent definition handling, being the `structs` loop in
   `generate_context` and the cross-service registration in `clientgen/__init__.py`.
   Landing this before the per-language backends keeps the ordering work reviewable on
   its own rather than buried in whichever client happens to come first.
7. Regenerate the clientgen golden fixtures.
8. One commit per remaining client, each carrying that client's clientgen backend and
   template, its runtime codec, its `lang/*.py` default-value branch and its tests
   together: C#, C++, Java, Lua, cnano. Keeping clientgen and the runtime codec in one
   commit per client is what #1017 did, and it keeps each client's change reviewable on
   its own.
9. docgen structs support, including the `nodes.py` ordering fix and the `default_value`
   overrides in `docgen/csharp.py` and `docgen/cpp.py`.
9. `CHANGELOG.md` entries (core, all clients, krpctools) as the final pre-merge commit,
   noting the old-dynamic-client compatibility consequence. Per-component
   `CHANGELOG.md` replaced the old `CHANGES.txt` files.

First-adoption candidates (separate follow-up work, per the issue): a
`LaunchSiteInfo` struct for `SpaceCenter.launch_sites`, and an additive
`Control.pitch_roll_yaw` alongside the existing per-axis properties.
`SpaceCenter.LaunchSite` is still the `KRPCClass` the issue describes, with `Name`,
`Body` and `EditorFacility` properties and no mutable state, so the 1 + 3n cost and the
worked example both still hold.

## Open questions

1. **Mutable or immutable client types**: namedtuple (Python) and immutable POJOs
   (Java) are proposed; if structs later become common as *arguments*, builder-style
   or mutable variants may be friendlier. Defer until adoption shows the need.
2. **`coerce_to` behavior** (Python/Lua): whether a plain tuple/list of the right
   arity is accepted where a struct is expected (the dynamic clients already coerce
   tuple↔list). Proposed: yes, positional coercion — cheap and convenient; confirm
   during implementation.
