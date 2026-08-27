# Nullable values inside collections and structures

**Status:** proposal (2026-08-27). Follow-up to
[nullable-values.md](nullable-values.md), which made a parameter or a return value nullable but
left every nested position non-nullable. Unblocks open question 3 of
[struct-types.md](struct-types.md). No issue yet.

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
| `IList<int?>`, `IDictionary<string,int?>`, `Tuple<int?,string>`, `HashSet<int?>` | `TypeUtils.IsAValidType` (`core/src/Service/TypeUtils.cs:32`), which does not recognize `Nullable<T>`, so every collection predicate rejects the element type |
| `[KRPCStruct]` with a nullable field | `TypeUtils.ValidateStructFields` (`TypeUtils.cs:586`), plus the null guards in `Encoder.WriteStruct` and `Encoder.DecodeStruct` |

`Nullable<T>` is unwrapped in exactly two places, both of them top level:
`ProcedureParameter`'s constructor and `Scanner/ProcedureSignature`. Neither recurses into a
generic argument, and `ValidateStructFields` reads `property.PropertyType` raw.

Two structure adoptions are blocked on this, per
[struct-adoption-audit.md](../services/struct-adoption-audit.md):
`SpaceCenter.ActionGroupAction`, whose `Module` is nullable, and `SpaceCenter.CommNode`, whose
`Vessel` only a ground station lacks. The second also gates `CommLink` and `Comms`.

## Decisions

- **Nullability moves onto `Type`, for nested positions only.** A `bool nullable` on the `Type`
  message is what [nullable-values.md](nullable-values.md) named as the right schema once kRPC
  wants genuine nullable collection elements. Its objection was that nothing could produce one.
  This design supplies the producer, so the field is added. `Parameter.nullable` and
  `Procedure.return_is_nullable` keep their meaning and are not deprecated, so the top level is
  untouched.
- **A nullable value carries a leading presence bool.** `Type.nullable` means the encoded value
  is a bool, followed by the value's ordinary encoding when the bool is true. This is in band,
  which the top-level design deliberately avoided, and the reasons it gave do not apply here:
  the cost falls only on a slot declared nullable, and a presence bool collides with nothing
  because it prefixes the value rather than standing in for it. The alternative is a set of
  parallel flag fields on the collection messages, rejected below.
- **Nullable positions are the list element, the set element, the tuple element, the dictionary
  value and the structure field.** A dictionary **key** may not be nullable. Key types are
  already restricted to the six that hash cleanly, and a null key carries no meaning. Declaring
  one is a scanner error.
- **Value types declare nullability structurally, reference types declare it by attribute.**
  `Nullable<T>` is a real runtime type, so `IList<int?>` needs no annotation. A reference type
  carries no nullability at runtime, so it takes an index path on `[KRPCNullable]`.
- **A structure field may be nullable.** `[KRPCProperty (Nullable = true)]` on a field, which
  `ValidateStructFields` rejects today, marks the field itself. This is what the two blocked
  adoptions need, and it composes with the field types that are already allowed.
- **The change is additive to the wire.** A `false` bool serializes to nothing, so a definition
  that declares nothing nullable is byte for byte what it is today, and so is every value.
  An old client reading a new definition ignores `Type.nullable` and then mis-decodes a value
  that uses it. That is the same compatibility stance structure types took: a client breaks
  only against a service that adopts the feature, and none does yet.

## Wire protocol changes

```diff
 message Type {
   TypeCode code = 1;
   string service = 2;
   string name = 3;
   repeated Type types = 4;
+  bool nullable = 5;
 }
```

`StructField` already holds a `Type`, and a collection's element types are already
`Type.types`, so one field covers every nested position. Field number 5 is unused.

### Value encoding

A `Type` with `nullable` set encodes as a bool, followed by the value's ordinary encoding when
that bool is true. The bool is written exactly as a `BOOL` value is, so it is one byte.

```
IList<int?> holding [1, null, 3]

  List.items[0] = 01 02      present, then sint32 1
  List.items[1] = 00         null
  List.items[2] = 01 06      present, then sint32 3

IList<int> holding [1, 2, 3]

  List.items[0] = 02         unchanged
```

The prefix applies wherever `Type.nullable` is set and nowhere else, so a non-nullable element
is unchanged and a nullable element costs one byte when it holds a value. A null costs one byte
in place of the value.

`Type.nullable` is never set on a parameter's own type or on a return type. Those slots keep
`Parameter.nullable` and `Procedure.return_is_nullable`, and their nulls keep riding `is_null`.
The rule a client follows is therefore unambiguous: `is_null` at the call boundary, a presence
bool inside a value.

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

### Value types and enumerations

`Nullable<T>` at any nested position, with no annotation:

```csharp
IList<int?>
IDictionary<string, double?>
Tuple<int?, string>
HashSet<TestEnum?>

[KRPCStruct]
public struct Reading
{
    [KRPCProperty]
    public double? Temperature { get; set; }
}
```

This is the rule [nullable-values.md](nullable-values.md) set for a parameter or a return
value, applied recursively. Boxing erases `Nullable<>`, so a boxed value is either a boxed `T`
or null and the encoder needs no `Nullable<T>` case of its own.

### Reference types

A reference type carries no nullability at runtime, so nullability is declared. Extend the
existing attribute with an index path rather than adding a sibling:

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
a dictionary key are all scanner errors.

### Structure fields

`[KRPCProperty (Nullable = true)]` marks the field itself. `[KRPCNullable (...)]` on the same
property marks a position inside the field's type.

```csharp
[KRPCStruct]
public struct CommNode
{
    [KRPCProperty (Nullable = true)]
    public Vessel Vessel { get; set; }
}
```

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

### The declared type has to reach the encoder

`Encoder.EncodeObject` dispatches on `value.GetType ()`
(`core/src/Server/ProtocolBuffers/Encoder.cs:25`), so the encode path has no declared type.
A `Nullable<T>` element is recoverable from the container's runtime type, but a reference-typed
element declared nullable by attribute is not: `IList<Vessel>` looks the same either way.

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

`Encoder.Decode` already receives a declared `System.Type` and takes the spec in its place.

### The rest

- **`TypeUtils`**: accept `Nullable<T>` of a value type or an enumeration as a valid nested
  type, so the collection predicates admit it. Leave `IsAValidKeyType` alone, which is what
  makes a nullable dictionary key an error. Look through `Nullable<T>` in `StructTypesIn`, so
  the recursion check still finds a structure inside `IList<Reading?>`. Drop the nullable-field
  rejection in `ValidateStructFields`, keeping the game-scene one.
- **`Encoder`**: write and read the presence bool at a nullable position, in `WriteList`,
  `WriteSet`, `WriteTuple`, `WriteDictionary` and `WriteStruct` and their decode counterparts.
  Drop the null-field guards in `WriteStruct` and `DecodeStruct`. `EncodeObject` still rejects
  a bare null, since a null now belongs to the slot around a value rather than to the value.
- **Scanner**: read the paths off `[KRPCNullable]`, validate them against the type, and fold
  them together with the `Nullable<T>` positions into the `TypeSpec`.
- **Validation**: a null in a non-nullable position is an error at encode and decode alike,
  reported with the position rather than the type, so a service author can find it.
- **`ValueUtils.Equal`** needs no change. It compares a null operand at the top of the function,
  before it dispatches on type, so a null element already compares correctly.

## Client changes

Every client follows one rule: at a position whose type is nullable, read or write the presence
bool, then fall through to the codec it already has. What differs is where the client gets the
declared type and how the language spells a null element.

| Client | Where the declared type comes from | Null element |
| --- | --- | --- |
| Python | `TypeBase` gains `nullable`. `Types.as_type` caches on the serialized `Type`, so a nullable node is already a distinct object | `None`, with `Optional[...]` at nested positions in the generated stubs |
| Lua | the same type model as Python | `Types.none`, the sentinel that already keeps a null out of a table without leaving a hole |
| Java | `Encoder.encode` already threads the wire `Type` through its recursion, so the flag arrives with no plumbing | a boxed `Integer`, held as null in a `List` |
| C++ | template overloads | `std::optional<T>` inside the container, which needs container-level `encode` and `decode` overloads |
| C# | reflects the generated type, so a nullable reference element is invisible; clientgen emits an explicit `TypeInfo` at a nullable position | `int?`, and a plain reference type |
| cnano | generated per type | a companion `bool` |

Two clients carry most of the cost.

**C#** derives its type information from the generated C# type, through `TypeInfo.For`. That
works for `IList<int?>`, which is self describing, and not for `IList<Vessel>` declared nullable
by attribute. `BuildEncoder` also rejects a null item outright today. Clientgen emits a static
`TypeInfo` describing the nullable positions, which the generated stub passes to the encoder in
place of `typeof (...)`.

**cnano** stores collection items by value, `krpc_list_int32_t { size_t size; int32_t * items; }`,
so there is no free null anywhere. A nullable position takes a companion `bool`: a member beside
a nullable structure field, and a parallel array beside nullable items. A nullable element type
is named as its own generated type, following the naming scheme the collection types already
use, so a list of nullable ints and a list of ints stay distinct declarations.

## Documentation

- `doc/src/communication-protocols/messages.rst`: the `Type.nullable` field, the presence bool,
  and the rule that separates it from `is_null`. The Structures section states that a field is
  never null, which this replaces.
- `doc/src/extending.rst`: the serializable types list, the *Null Values* and *Nullable Value
  Types* sections, and the `KRPCStruct` criteria, which forbid a nullable field. Document the
  index path on `KRPCNullable` beside the existing form.

## Tests

- **TestService** (`tools/TestServer/src/TestService.cs`): a nullable element in each of a list,
  a set, a dictionary value and a tuple, declared once by `Nullable<T>` and once by attribute; a
  structure with a `Nullable<T>` field and one with a class-typed nullable field; a nested case
  such as `IDictionary<string, IList<Vessel>>`; and the rejection cases, a nullable dictionary
  key and a null in a non-nullable element.
- **Core**: scanner tests for each declaration form and each error, encoder round trips for
  every nullable position, and a check that a non-nullable collection still encodes byte for
  byte as it did.
- **Clients**: the round-trip, argument and stream tests each client already has for the top
  level, repeated for a nested position.
- **krpctools**: regenerate `clientgen-TestService-*` and `docgen-TestService-*`.

## Implementation phases

The shape [nullable-values.md](nullable-values.md) used, which is the closest precedent for a
change crossing the schema and every client. Full CI is not green between phases.

1. Schema: `Type.nullable`, and the protocol documentation for it.
2. Core: `TypeSpec`, the scanner, `TypeUtils`, the encoder, and the authoring documentation.
   Core tests. Every client is broken from here until its phase lands.
3. TestService fixtures.
4. Python plus the shared krpctools path, which unblocks every generator.
5. One phase per remaining client, each carrying that client's generator backend, its runtime
   codec, its golden fixtures and its tests: C#, C++, Java, Lua, cnano.
6. Changelogs, as the final commit before merging.

## Open questions

1. **Whether the top level should move onto `Type.nullable` as well.** Doing so folds two flags
   into one and makes the rule uniform, at the cost of a second protocol break for every client
   so soon after the first. Kept as is here, which leaves two mechanisms to document.
2. **The C# client's `TypeInfo` shape.** Emitting a static descriptor per nullable position is
   the cheapest change, and it splits the client's type handling between reflection and
   generated data. Building every `TypeInfo` from the service definition instead is tidier and
   is a larger change to a client that currently reflects.
3. **Whether a nullable element belongs in a set.** A set of nullable values admits at most one
   null, which is well defined but rarely wanted. Allowed here for uniformity, since excluding
   it is a special case in every client.
