# Nullable values inside structures and collections

**Status:** proposal (2026-08-28). Follow-up to
[nullable-values.md](nullable-values.md), which made a parameter or a return value nullable but
left every nested position non-nullable. Unblocks open question 3 of
[struct-types.md](struct-types.md). No issue yet.

Split into three phases, each mergeable on its own. **Phase 1** moves nullability onto the
`Type` message, a wire format change with no change in behavior. **Phase 2** makes a structure
field nullable, which is what the blocked service work needs. **Phase 3** extends the same
mechanism to a collection element, which is where the cost is.

## Context

[PR #1017](https://github.com/krpc/krpc/pull/1017) made a value nullable at the call boundary.
Nullability is a property of the **slot**: `Parameter.nullable` and
`Procedure.return_is_nullable` declare it, and `Argument.is_null` and `ProcedureResult.is_null`
carry the null itself. Both flags sit beside the encoded bytes rather than inside them.

A nested value has no such channel. `Tuple`, `List` and `Set` are `repeated bytes items`, and
`DictionaryEntry` is two `bytes` fields, so an item is one opaque blob with nowhere to put a
flag. A structure value is encoded as a tuple of its fields, so a field is an item too.

Two declarations are therefore rejected today:

| Declaration | Rejected by |
| --- | --- |
| `[KRPCStruct]` with a nullable field | `TypeUtils.ValidateStructFields` (`core/src/Service/TypeUtils.cs:586`), plus the null guards in `Encoder.WriteStruct` and `Encoder.DecodeStruct` |
| `IList<int?>`, `IDictionary<string,int?>`, `Tuple<int?,string>` | `TypeUtils.IsAValidType` (`TypeUtils.cs:32`), which does not recognize `Nullable<T>`, so every collection predicate rejects the element type |

`Nullable<T>` is unwrapped in exactly two places, both of them top level:
`ProcedureParameter`'s constructor and `Scanner/ProcedureSignature`. Neither recurses into a
generic argument, and `ValidateStructFields` reads `property.PropertyType` raw.

Two structure adoptions are blocked on the first row, per
[struct-adoption-audit.md](../services/struct-adoption-audit.md):
`SpaceCenter.ActionGroupAction`, whose `Module` is nullable, and `SpaceCenter.CommNode`, whose
`Vessel` only a ground station lacks. The second also gates `CommLink` and `Comms`.

### Two facts that shape the design

**The nullable protocol break has not shipped.** #1017 and structure types
([PR #1066](https://github.com/krpc/krpc/pull/1066)) are both in the unreleased 0.7.0 cycle. A
client that depends on `Parameter.nullable` or on the structure encoding does not exist outside
this repository, so reshaping either is one break in one release rather than two.

**The id-0 null sentinel is gone.** Open question 3 of [struct-types.md](struct-types.md) says
a class-typed field needs no wire change, because `ObjectStore.AddInstance (null)` returns the
reserved id 0. #1017 retired that on the client side: Python builds an object handle from
whatever id arrives (`client/python/krpc/decoder.py:91`), so id 0 now yields a live handle
rather than a null. A class-typed field needs the mechanism below like every other field.

### Nullability was on `Type` once

[Issue #395](https://github.com/krpc/krpc/issues/395) asked for nullability in the service
definition JSON, so a client in a language without a null could generate correct code. It
proposed the flag on the type, as `"optional": true` inside `return_type`. That is what June
2017 implemented, as `Type.nullable = 5`. September 2017 moved it to
`Procedure.return_is_nullable`, three months and 99 commits later, still before v0.4.0 shipped.

The commit message records no reason. The diff shows one. `Type.nullable` was populated in a
single branch of `TypeUtils.SerializeType`, for a class type and only as a return value. Every
recursive call passed the flags off:

```csharp
result["types"] = type.GetGenericArguments ().Select (t => SerializeType (t, false, false)).ToList ();
```

So `SerializeType` carried `bool isReturnType, bool nullable` through its whole recursion to
serve one branch at depth zero, with two wrapper functions supplying them. The move deleted 60
lines against 39 added. Nullability was a property of the slot threaded through a structural
descriptor that never read it, which is the objection
[nullable-values.md](nullable-values.md) restated in 2026.

Two things follow. `Type.nullable = 5` was added and removed inside one development cycle, so
no release carries it and field 5 is free. Phase 3's `TypeSpec` is that same descriptor threaded
through that same recursion, which is what to weigh before Phase 3 starts.

## Decisions

- **`Type.nullable` is the single declaration, at every position.** A `bool nullable` on the
  `Type` message declares a nullable parameter, return value, structure field and collection
  element alike. `Parameter.nullable` and `Procedure.return_is_nullable` are removed. One rule
  answers "is this slot nullable" everywhere, and the recursion in `Type.types` covers every
  nested position with no further schema change. This puts nullability back where
  [issue #395](https://github.com/krpc/krpc/issues/395) first asked for it, and the objection
  that moved it off `Type` in 2017 is answered by having positions that set it.
- **Carriage stays split by position.** `Argument.is_null`, `ProcedureResult.is_null` and
  `Parameter.default_value_is_null` keep carrying the null at the call boundary, where a proto3
  `false` costs nothing. A value nested inside another value has no such field, so it carries a
  leading presence bool instead. Declaration is uniform; carriage follows what the position can
  afford.
- **A nullable value carries a leading presence bool.** At a nested position, `Type.nullable`
  means the encoded value is a bool, followed by the value's ordinary encoding when the bool is
  true. This is in band, which the top-level design deliberately avoided. The reasons it gave do
  not apply here: the cost falls only on a position declared nullable, and a presence bool
  collides with nothing because it prefixes the value rather than standing in for it.
- **Nullable positions are the structure field, the list element, the tuple element and the
  dictionary value**, alongside the three top-level slots. A dictionary **key** and a **set**
  element may not be nullable. A null key carries no meaning and key types are already
  restricted to the six that hash cleanly. A set of nullable values admits at most one null,
  which is well defined and rarely wanted, and it costs `std::optional` hashing in C++ and a
  parallel flag array in cnano. Both exclusions are a scanner error, so no service produces one
  and no client decodes one.
- **Value types declare nullability structurally, reference types declare it by attribute.**
  `Nullable<T>` is a real runtime type, so `double? Temperature` and `IList<int?>` need no
  annotation. A reference type carries no nullability at runtime, so it is marked:
  `[KRPCProperty (Nullable = true)]` on a structure field, and an index path on
  `[KRPCNullable]` for a collection element.
- **A structure knows its own fields; a collection does not know its elements.** This is what
  splits the phases. `WriteStruct` and `DecodeStruct` already hold the `PropertyInfo` for each
  field, so a nullable field is readable at the point of encoding. `Encoder.EncodeObject`
  dispatches on `value.GetType ()`, and `IList<Vessel>` looks the same whether or not its
  element is nullable, so a nullable element needs the declared type threaded into the encoder.
  Phase 2 pays none of that cost; Phase 3 pays all of it.
- **Nullability must not fragment the client type caches.** Every dynamic client caches a
  `Type` by its serialized bytes, and registers the generated class for a class type under that
  key (`client/python/krpc/types.py:143`). Adding `nullable` to the message makes a nullable
  `Vessel` a different key, which would miss the registration and mint a second, unrelated
  Python class. A nullable type therefore resolves to its non-nullable type first and shares
  that type's `python_type`, so `isinstance` still holds. Lua caches the same way and takes the
  same treatment. A nullable class-typed parameter and return value exist today, so this lands
  in Phase 1.

## Wire protocol changes

```diff
 message Procedure {
   string name = 1;
   repeated Parameter parameters = 2;
   Type return_type = 3;
-  bool return_is_nullable = 4;
   ...
 }

 message Parameter {
   string name = 1;
   Type type = 2;
-  bool nullable = 4;
   bool has_default_value = 5;
   bytes default_value = 3;
   bool default_value_is_null = 6;
 }

 message Type {
   TypeCode code = 1;
   string service = 2;
   string name = 3;
   repeated Type types = 4;
+  bool nullable = 5;
 }
```

`StructField` already holds a `Type`, and a collection's element types are already
`Type.types`, so one field covers every position. Field number 5 on `Type` is unused, and held
this same flag before v0.4.0 without ever reaching a release.

The two numbers vacated are freed rather than reserved. Both shipped, `Procedure` field 4 in
v0.4.0 and `Parameter` field 4 in v0.5.2, so a released client does read them. Reusing either
would need a peer that speaks 0.7.0's schema alongside an older one, and #1017 already rules
that out. A clean schema is worth more here than a guard on a combination the protocol break
has removed.

Phase 1 makes the whole of this change. Phase 2 and Phase 3 set `Type.nullable` at positions
Phase 1 leaves it clear of, and add the encoding below.

### Value encoding

The presence bool belongs to the nested positions. A parameter, a return value and a default
value each have their own null flag, so `Type.nullable` on one of them declares nullability
without changing the encoding. Everywhere else, a `Type` with `nullable` set encodes as a bool,
followed by the value's ordinary encoding when that bool is true. The bool is written exactly as
a `BOOL` value is, so it is one byte.

```
A structure whose second field is a nullable Vessel

  Tuple.items[0] = ...        the first field, unchanged
  Tuple.items[1] = 01 07      present, then object id 7
  Tuple.items[1] = 00         null

IList<int?> holding [1, null, 3]

  List.items[0] = 01 02       present, then sint32 1
  List.items[1] = 00          null
  List.items[2] = 01 06       present, then sint32 3

IList<int> holding [1, 2, 3]

  List.items[0] = 02          unchanged
```

A non-nullable position is byte for byte what it is today. A nullable position costs one byte
when it holds a value, and one byte in place of the value when it holds a null.

### Rejected alternative: parallel flags on the collection messages

```
message List { repeated bytes items = 1; repeated bool items_are_null = 2; }
message DictionaryEntry { bytes key = 1; bytes value = 2; bool value_is_null = 3; }
```

This mirrors `Argument.is_null` and costs nothing when a nullable collection happens to hold no
nulls. It is rejected on two counts. It changes four messages rather than one, and it leaves an
invariant a decoder must police, that the flag array is empty or exactly as long as the items.
It also costs real work in cnano: nanopb decodes fields in wire order through per-field
callbacks, so two repeated fields that may arrive in either order have to be buffered and
correlated, where a prefix byte is read by the callback that already runs per item.

### Rejected alternative: an empty item means null

An item of zero length could mean null, with no prefix on a present value. An empty collection,
tuple or structure encodes to zero bytes, so the meaning collides for exactly the element types
that are already the awkward ones.

## Declaring nullability in C#

### Structure fields (Phase 2)

`[KRPCProperty (Nullable = true)]` marks a field nullable, which `ValidateStructFields` rejects
today. A `Nullable<T>` field needs no annotation.

```csharp
[KRPCStruct]
public struct CommNode
{
    [KRPCProperty (Nullable = true)]
    public Vessel Vessel { get; set; }

    [KRPCProperty]
    public double? SignalStrength { get; set; }
}
```

`Nullable = true` on a `Nullable<T>` field is redundant and accepted. The two spellings mean the
same thing, and which one is available depends on whether the field type is a value type.

### Collection elements (Phase 3)

`Nullable<T>` at any nested position, with no annotation:

```csharp
IList<int?>
IDictionary<string, double?>
Tuple<int?, string>
```

A reference type takes an index path on `[KRPCNullable]`, extending the existing attribute
rather than adding a sibling:

```csharp
[AttributeUsage (AttributeTargets.Parameter | AttributeTargets.Method |
                 AttributeTargets.Property, AllowMultiple = true)]
public sealed class KRPCNullableAttribute : Attribute
{
    public KRPCNullableAttribute (params int[] path) { Path = path; }
    public int[] Path { get; }
}
```

An empty path is the meaning the attribute has today, so every existing use stands. A path
indexes `Type.types` at each step, which is the order the wire already uses:

```csharp
[KRPCNullable (0)] IList<Vessel> vessels
[KRPCNullable (1, 0)] IDictionary<string, IList<Vessel>> byName
[KRPCNullable] [KRPCNullable (0)] IList<Vessel> maybeVessels
```

On a method the path applies to the return type, matching how `Nullable = true` already does.
An out of range index, a path into a type that has no element at that position, and a path onto
a dictionary key or a set element are all scanner errors. The readability of the path is
[open question 2](#open-questions).

### Rejected alternative: C# nullable reference type annotations

`IList<Vessel?>` is the best syntax available, and it reads the same as `IList<int?>`. Setting
`<Nullable>annotations</Nullable>` on the kRPC assemblies emits the metadata without the CS8632
error that [nullable-values.md](nullable-values.md) cited against it. Rejected on two grounds:

- **The metadata has to be walked by hand.** `NullabilityInfoContext` arrives in .NET 6, and
  the plugin targets net472 under Mono. What is left is the flattened `NullableAttribute` byte
  array plus the `NullableContextAttribute` compression, read by attribute name because the
  types are compiler generated per assembly.
- **A third-party service assembly is oblivious.** A mod that adds its own service compiles
  under its own settings, so whether `?` means anything depends on someone else's csproj. An
  attribute means the same thing in every assembly.

### Rejected alternative: a public `Optional<T>` wrapper

`IList<Optional<Vessel>>`, with implicit conversions both ways, makes nested nullability
structural for reference types the way `Nullable<T>` does for value types. Everything that
reflects over the type then sees it, and the server needs no declared-type plumbing at all.
Rejected because it puts a wrapper into the service-authoring surface at every point a
collection is built or read, and gives nullability two spellings that differ by whether the
element happens to be a value type.

## Server changes

### Phase 1

Set `nullable` on the `Type` built for a parameter and for a return value, where
`ProcedureParameter.Nullable` and `ReturnIsNullable` put it today. Those two stay as the
internal model that `Services.cs` reads, and stop being message fields. `MessageExtensions`
and `TypeUtils.SerializeType` carry the flag into the protobuf message and into the service
definition JSON. Nothing else moves: the same procedures are nullable, and every encoded value
is unchanged.

### Phase 2

- **Scanner and messages**: set `nullable` on the `Type` built for a structure field.
- **`TypeUtils`**: accept `Nullable<T>` of a value type or an enumeration as a structure field
  type. Drop the nullable-field rejection in `ValidateStructFields`, keeping the game-scene one.
  Look through `Nullable<T>` in `StructTypesIn`, so the recursion check still sees a structure
  inside `Reading?`.
- **`Encoder`**: write and read the presence bool per field in `WriteStruct` and `DecodeStruct`,
  reading `Nullable = true` and `Nullable<T>` off the `PropertyInfo` that both already hold.
  Drop their null-field guards. `EncodeObject` still rejects a bare null, since a null belongs
  to the position around a value rather than to the value.
- **Validation**: a null in a non-nullable field is an error at encode and decode alike,
  reported with the field name.

### Phase 3

`Encoder.EncodeObject` dispatches on `value.GetType ()`
(`core/src/Server/ProtocolBuffers/Encoder.cs:25`), so the encode path has no declared type. A
`Nullable<T>` element is recoverable from the container's runtime type, and a reference-typed
element declared nullable by attribute is not.

Build a descriptor once, in the scanner:

```csharp
sealed class TypeSpec {
    public System.Type Type;   // the unwrapped type
    public bool Nullable;
    public TypeSpec[] Types;   // element specs, mirroring Type.types
}
```

`ParameterSignature` and `ProcedureSignature` hold it. It subsumes three walks of the C# type
that are separate today: `MessageExtensions.ToProtobufMessage (this Type)`,
`TypeUtils.SerializeType` for the service definition JSON, and the encoder's own recursion.

Threading it is contained. `Encoder.Encode` has four call sites:

| Call site | Source of the spec |
| --- | --- |
| `MessageExtensions.cs:41`, a procedure result | `Messages.ProcedureResult`, set in `Services.ExecuteCall` where the `ProcedureSignature` is in hand |
| `StreamStream.cs:76`, the stream write path | the same field on the result |
| `MessageExtensions.cs:143`, a parameter default | `Messages.Parameter` |
| `ParameterSignature.cs:66`, the definition JSON | the signature itself |

`Encoder.Decode` already receives a declared `System.Type` and takes the spec in its place. The
rest is the scanner reading the paths off `[KRPCNullable]`, validating them against the type,
and folding them together with the `Nullable<T>` positions into the spec. `ValueUtils.Equal`
needs no change, since it compares a null operand before it dispatches on type.

## Client changes

Every client follows one rule: at a position whose type is nullable, read or write the presence
bool, then fall through to the codec it already has. What differs is where the client gets the
declared type and how the language spells a null.

| Client | Where the declared type comes from | Null value |
| --- | --- | --- |
| Python | `TypeBase` gains `nullable`, resolved through the non-nullable type so the generated class is shared | `None`, with `Optional[...]` in the generated stubs |
| Lua | the same type model as Python | `Types.none`, the sentinel that already keeps a null out of a table without leaving a hole |
| Java | `Encoder.encode` already threads the wire `Type` through its recursion, so the flag arrives with no plumbing | a boxed `Integer`, held as null |
| C++ | template overloads | `std::optional<T>`, except a class type, where an `Object<T>` with id 0 is already the null representation (`client/cpp/include/krpc/object.hpp:35`) |
| C# | reflects the generated type, so a nullable reference position is invisible; clientgen emits an explicit `TypeInfo` | `int?`, and a plain reference type |
| cnano | generated per type | a companion `bool` |

Phase 1 is a read-site change in every client, from `Parameter.nullable` and
`return_is_nullable` to the `nullable` on the type each already holds, plus the cache fix
above. The reflection-based clients carry most of the remaining cost, and only in Phase 3.

**C#** derives its type information from the generated C# type, through `TypeInfo.For`. A
nullable structure field is visible there, because clientgen generates the structure class and
can give the field a nullable type. A nullable collection element is not: `IList<int?>` is self
describing and `IList<Vessel>` declared nullable by attribute is not. Clientgen emits a static
`TypeInfo` describing the nullable positions, which the generated stub passes to the encoder in
place of `typeof (...)`.

**cnano** stores collection items by value, `krpc_list_int32_t { size_t size; int32_t * items; }`,
so there is no free null anywhere. A nullable position takes a companion `bool`: a member beside
a nullable structure field, and, in Phase 3, a parallel array beside nullable items. A nullable
element type is named as its own generated type, following the naming scheme the collection
types already use, so a list of nullable ints and a list of ints stay distinct declarations.

## Documentation

- `doc/src/communication-protocols/messages.rst`: Phase 1 replaces the two slot flags with
  `Type.nullable`. Phase 2 adds the presence bool and the rule that separates it from
  `is_null`, and rewrites the Structures section, which states that a field is never null.
- `doc/src/extending.rst`: Phase 2 covers the serializable types list, the *Null Values* and
  *Nullable Value Types* sections, and the `KRPCStruct` criteria, which forbid a nullable
  field. Phase 3 documents the index path on `KRPCNullable` beside the existing form.

## Tests

- **Phase 1** adds no fixture. The nullable tests every client and
  `core/test/Service/ServicesTest.cs` already have pass unchanged, which is the point of the
  phase, and `MessageAssert` moves to reading the flag off the type. One test is new per
  dynamic client: a nullable class-typed value decodes to the same generated class as a
  non-nullable one, which is the cache hazard above.
- **TestService** (`tools/TestServer/src/TestService.cs`): Phase 2 adds a structure with a
  `Nullable<T>` field and one with a class-typed nullable field, plus the rejection case, a
  null in a non-nullable field. Phase 3 adds a nullable element in each of a list, a dictionary
  value and a tuple, declared once by `Nullable<T>` and once by attribute, a nested case such as
  `IDictionary<string, IList<Vessel>>`, and the rejection cases, a nullable dictionary key and a
  nullable set element.
- **Core**: scanner tests for each declaration form and each error, encoder round trips for
  every nullable position, and a check that a non-nullable value still encodes byte for byte as
  it did.
- **Clients**: the round-trip, argument and stream tests each client already has for the top
  level, repeated for a nested position.
- **krpctools**: regenerate `clientgen-TestService-*` and `docgen-TestService-*`.

## Implementation phases

Three phases, each mergeable on its own. The steps within a phase follow the shape
[nullable-values.md](nullable-values.md) used, which is the closest precedent for a change
crossing the schema and every client. Full CI is not green between the steps of a phase.

### Phase 1: nullability on `Type`

A wire format change with no change in behavior. The same procedures are nullable, every
encoded value is identical, and the client API is untouched. One step, since the schema, the
server and all six clients read the same fields and have to move together:

1. `Type.nullable` added; `Parameter.nullable` and `Procedure.return_is_nullable` removed,
   their numbers freed. The server sets the flag on the parameter and return types. Every
   client reads it there, and resolves a nullable type through its non-nullable one so the
   generated class stays shared. Golden fixtures and service definitions regenerated. Protocol
   documentation.

The phase is worth landing on its own even if Phase 2 stalls. It is free while 0.7.0 is
unreleased, and it gets more expensive with every release that ships the two slot flags.

### Phase 2: nullable structure fields

1. Core: the scanner, `TypeUtils`, `WriteStruct` and `DecodeStruct`, and the authoring
   documentation. Core tests. Every client is broken from here until its step lands.
2. TestService fixtures.
3. Python plus the shared krpctools path, which unblocks every generator.
4. One step per remaining client, each carrying that client's generator backend, its runtime
   codec, its golden fixtures and its tests: C#, C++, Java, Lua, cnano.
5. The service adoptions Phase 2 is for: `SpaceCenter.CommNode`, `ActionGroupAction`, and
   `CommLink` and `Comms` behind them. See
   [struct-adoption-audit.md](../services/struct-adoption-audit.md).
6. Changelogs, as the final commit before merging.

### Phase 3: nullable collection elements

Follows the same order, on top of a merged Phase 2.

1. Core: `TypeSpec`, the four `Encoder.Encode` call sites, the `[KRPCNullable]` index path, and
   the scanner validation. Core tests.
2. TestService fixtures.
3. Python plus the shared krpctools path.
4. One step per remaining client: C#, C++, Java, Lua, cnano.
5. Changelogs.

## Open questions

1. **Whether Phase 3 has a caller.** No service wants a nullable collection element today. The
   same objection sank `Type.nullable` in [nullable-values.md](nullable-values.md), and sank the
   2017 version before it, and it now applies to Phase 3 alone. Phase 3 may sit as a design
   until a service needs it.
2. **The readability of the `[KRPCNullable]` index path.** `[KRPCNullable (1, 0)]` on
   `IDictionary<string, IList<Vessel>>` asks the reader to know that a dictionary key is index 0
   and its value is index 1. Restricting Phase 3 to depth one covers every service anyone has
   proposed and makes the attribute read plainly. Revisit when Phase 3 starts.
3. **The C# client's `TypeInfo` shape.** Emitting a static descriptor per nullable position is
   the cheapest change, and it splits the client's type handling between reflection and
   generated data. Building every `TypeInfo` from the service definition instead is tidier and
   is a larger change to a client that currently reflects.
