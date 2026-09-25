# Nullable values inside structures and collections

**Status:** in progress (as of 2026-09-02). Follow-up to
[nullable-values.md](nullable-values.md), which made a parameter or a return value nullable but
left every nested position non-nullable. Unblocks open question 3 of
[struct-types.md](struct-types.md). No issue yet.

All three phases landed across the schema, the server, krpctools and every client, merged as
[PR #1091](https://github.com/krpc/krpc/pull/1091). Every client holds nullability the way
[The shape a client takes](#the-shape-a-client-takes) sets out. Outstanding: the service
adoptions of Phase 2 step 5.

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
The server keeps the mapping, and the decision below takes it out.

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
- **The object id 0 is not a null.** `ObjectStore` maps a null to the id 0 and back, which
  is how a null reached a class-typed slot before #1017. Nullability is declared on the type
  and carried beside the value, so the mapping goes: adding a null is an error, and the id 0
  names no object. A client that sends 0 for a class value gets an error rather than a null
  at a position that never declared one.
- **A nullable value carries a leading presence bool.** At a nested position, `Type.nullable`
  means the encoded value is a bool, followed by the value's ordinary encoding when the bool is
  true. This is in band, which the top-level design deliberately avoided. The reasons it gave do
  not apply here: the cost falls only on a position declared nullable, and a presence bool
  collides with nothing because it prefixes the value rather than standing in for it.
- **Nullable positions are the structure field, the list element, the tuple item and the
  dictionary value**, alongside the three top-level slots. A dictionary **key** and a **set**
  element may not be nullable. A null key carries no meaning and key types are already
  restricted to the six that hash cleanly. A set of nullable values admits at most one null,
  which is well defined and rarely wanted, and it costs `std::optional` hashing in C++ and a
  parallel flag array in cnano. Neither exclusion needs a rule of its own: a position is named
  rather than counted, and neither has a name.
- **Value types declare nullability structurally, reference types declare it by attribute.**
  `Nullable<T>` is a real runtime type, so `double? Temperature` and `IList<int?>` need no
  annotation. A reference type carries no nullability at runtime, so it is marked:
  `[KRPCProperty (Nullable = true)]` on a structure field, and a path of named positions on
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

A reference type takes a path of named positions on `[KRPCNullable]`, extending the existing
attribute rather than adding a sibling:

```csharp
public enum Position
{
    Element,                                          // the element of a list
    Value,                                            // the value of a dictionary
    Item1, Item2, Item3, Item4, Item5, Item6, Item7   // the items of a tuple
}

[AttributeUsage (AttributeTargets.Parameter | AttributeTargets.Method |
                 AttributeTargets.Property, AllowMultiple = true)]
public sealed class KRPCNullableAttribute : Attribute
{
    public KRPCNullableAttribute (params Position[] path) { Path = path; }
    public Position[] Path { get; }
}
```

An empty path is the meaning the attribute has today, so every existing use stands. Each step
of the path names a position of the type it is applied to, and the next step applies to the
type at that position:

```csharp
[KRPCNullable] IList<Vessel> vessels
[KRPCNullable (Element)] IList<Vessel> crew
[KRPCNullable (Value)] IDictionary<string, Vessel> byName
[KRPCNullable (Item2)] Tuple<string, Vessel> named
[KRPCNullable (Element, Element)] IList<IList<Vessel>> byStage
[KRPCNullable (Value, Item1)] IDictionary<string, Tuple<Vessel, double>> targets
```

The examples read with `using static KRPC.Service.Attributes.Position;`. Without it each
position is written `Position.Element`, as `GameScene` already is on `[KRPCProcedure]`.

Nesting repeats a position name once per level, outermost first. On `IList<IList<Vessel>>`,
`[KRPCNullable (Element)]` makes the inner **lists** nullable and
`[KRPCNullable (Element, Element)]` makes the **vessels** nullable. A type with both nullable
carries both attributes.

`AllowMultiple` covers a type with several nullable positions:

```csharp
[KRPCNullable]
[KRPCNullable (Element)]
IList<Vessel> maybeVessels                                    // the list, and its elements

[KRPCNullable (Value, Item1)]
[KRPCNullable (Value, Item2)]
IDictionary<string, Tuple<Vessel, Vessel>> pairs              // both items of every value
```

On a method the path applies to the return type, matching how `Nullable = true` already does.

### One validation rule

A path step is an error when the type at that step has no position by that name. That single
rule covers every case, with no exclusion written as a special case:

| Path | Applied to | Outcome |
| --- | --- | --- |
| `Value` | `IDictionary<string, Vessel>` | the values are nullable |
| `Value` | `IList<Vessel>` | error, a list has no value |
| `Item3` | `Tuple<string, Vessel>` | error, the tuple has two items |
| `Element` | `HashSet<Vessel>` | error, a set has no nameable position |
| `Key` | anything | does not compile, `Position` has no `Key` |

A dictionary key and a set element are excluded by having no name rather than by a rule that
rejects them. `Element` is defined as the element of a list, so a set has no position a path
can reach, and `Position` has no `Key` at all.

### Rejected alternative: integer index paths

`[KRPCNullable (1, 0)]` on `IDictionary<string, IList<Vessel>>`, indexing `Type.types` at each
step. It is the smallest attribute and it maps directly onto the wire. Rejected because the
reader has to know that a dictionary key is index 0 and its value is index 1, and because a
wrong index is usually another valid position rather than an error: `1` on a two-item tuple is
silently the second item, and on a dictionary silently the value. A named position is checked
against the container kind, and a dictionary key becomes unspellable rather than a scanner
error.

### Rejected alternative: marking by element type

`[KRPCNullable (typeof (Vessel))]`, meaning every `Vessel` in the declared type is nullable. It
needs no position vocabulary and no counting. Rejected because it cannot distinguish two
occurrences of one type: `Tuple<Vessel, Vessel>` with only the second item nullable is exactly
the structure-like tuple the phase is for.

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
    public System.Type Type;          // the unwrapped type
    public System.Type DeclaredType;  // the type as declared, which keeps Nullable<T>
    public bool Nullable;
    public TypeSpec[] Types;   // element specs, mirroring Type.types
}
```

The declared type is what the decoder builds a collection from, so a position that can hold a
null is able to hold one: an `IList<int?>` rather than an `IList<int>`.

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

The spec replaces the runtime-type dispatch rather than sitting beside it. The encoder reads
the type from the spec at every position, so a value is encoded as the type that declares it.
A procedure declaring `IList<T>` and returning an array encodes, where the runtime type gave
no serializable type at all.

A null at a position that does not allow one is an error at encode, naming the position and
the type holding it. There is none to catch at decode: no encoding decodes to a null once the
object store rejects the id 0.

## Client changes

Every client follows one rule: at a position whose type is nullable, read or write the presence
bool, then fall through to the codec it already has. What differs is where the client gets the
declared type and how the language spells a null.

| Client | Where the declared type comes from | Null value |
| --- | --- | --- |
| Python | `TypeBase` gains `nullable`, and the nullable form of a type is a copy sharing its python type | `None`, with `Optional[...]` in the generated stubs |
| Lua | the same type model as Python | `Types.none`, the sentinel that already keeps a null out of a table without leaving a hole |
| Java | `Encoder.encode` already threads the wire `Type` through its recursion, so the flag arrives with no plumbing | a boxed `Integer`, held as null |
| C++ | template overloads | `std::optional<T>`, a class type included, so one rule covers every type |
| C# | reflects the generated type, so a nullable reference position is invisible; clientgen emits an explicit `TypeSpec` | `int?`, and a plain reference type |
| cnano | generated per type | a companion `bool` |

Phase 1 is a read-site change in every client, from `Parameter.nullable` and
`return_is_nullable` to the `nullable` on the type each already holds, plus the cache fix
above. The reflection-based clients carry most of the remaining cost, and only in Phase 3.

**C#** derives its type information from the generated C# type, through `TypeInfo.For`. A
nullable structure field is visible there, because clientgen generates the structure class and
can give the field a nullable type. A nullable collection element is not: `IList<int?>` is self
describing and `IList<Vessel>` declared nullable by attribute is not. Clientgen emits a static
`TypeSpec` naming the nullable positions, which the generated stub passes to the encoder in
place of `typeof (...)`. Specs are interned per service, so a shape is built once.

A stream and a call built from an expression read no stub body: the C# type in the expression
is all they have. So the generated service also holds the spec of every procedure whose values
that type cannot describe, keyed by procedure name and reached through the `RPCAttribute` on
the stub. Java resolves its wire `Type` through `@RPCInfo` the same way.

**cnano** stores collection items by value, `krpc_list_int32_t { size_t size; int32_t * items; }`,
so there is no free null anywhere. A nullable position takes a companion `bool`: a member beside
a nullable structure field, and, in Phase 3, a parallel array beside nullable items. A nullable
element type is named as its own generated type, following the naming scheme the collection
types already use, so a list of nullable ints and a list of ints stay distinct declarations.

## The shape a client takes

Three rules, which fall out of the wire format. Hold a client against them when its step lands,
and rework it to them where it does not fit.

1. **The type at a position carries whether that position can hold null.** Nullability belongs
   to the position, and the type there is the one thing every part of a client already has. So a
   client holds no flag beside a type.
2. **A slot and a position are different operations.** A slot carries its null out of band and
   encodes as the value alone; a value inside another value carries a leading presence bool. The
   codec has an entry point for each, and the slot one ignores the nullability of the type it is
   given. This mirrors the server's `EncodeObject` against its `EncodeItem`.
3. **The nullable form of a type shares the language type of the non-nullable one.** A class has
   one generated class and a structure one generated structure, however the position holding it
   is declared, so identity and equality still hold across a nullable position.

What each part of a client looks like:

| Part | Shape |
| --- | --- |
| Type model | one type object per type and nullability; the nullable form is built from the non-nullable one and shares its language type |
| Slot codec | `encode (value, type)` and `decode (data, type)`, ignoring the type's nullability |
| Position codec | `encode_item (value, type)` and `decode_item (data, type)`, reading it |
| Collections | a collection holds the types of the positions inside it, and nullability arrives with them |
| Structure fields | fields are set as a name and a type; the field's type carries whether it can be null |
| Coercion | a null passes at a position whose type is nullable, and is rejected at one whose type is not |
| Generated stubs | name a nullable position by its type, `list_type (nullable (class_type ("S", "C")))` |
| Documentation | a nullable position is described from its type alone |

A language that spells nullability in the type itself satisfies rules 1 and 3 for free:
`std::optional<T>` in C++, a generated `krpc_nullable_object_t` in cnano. A language whose type
model is the wire `Type` satisfies them by setting `nullable` on it, as Java does.

### Where each client stands

| Client | Carries nullability in | Conforms |
| --- | --- | --- |
| Python | the type object, `TypeBase.nullable` | yes |
| C++ | the C++ type, `std::optional<T>` | yes |
| cnano | the generated C type, `krpc_nullable_object_t` | yes |
| Java | the wire `Type`, through `Types.nullable` | yes |
| Lua | the type object, `TypeBase.nullable` | yes |
| C# | the type object, `TypeSpec` | yes |

**C#** carried the same fact three ways at first: the CLR type, a `TypeSpec` and
`TypeInfo.ArgumentIsNullable`, with `EncodeItem (value, type, nullable, spec)` taking two of
them beside the type. `TypeSpec` is the one that can describe every position, since a
reference-typed one is invisible in the CLR type, so it became the client's type object. A stub
names a spec everywhere it once named a `typeof (T)`, and `TypeSpec.For` builds the one a CLR
type gives on its own. The stream and expression paths have only that, so they take the spec
the service declares for the procedure instead, as [Client changes](#client-changes) sets out.
The client's `TypeSpec` mirrors the server's.

### What it rules out

Each of these is a second place the same fact lives, and each was in the first Python
implementation:

- a parallel `value_nullable` or `field_nullable` list beside a collection's or a structure's
  types
- a `nullable` argument passed beside a type through a codec, a coercion or a generator
- a `has_nullable_fields` memo, or any flag derived once and stored beside what it came from
- a structure field registered as a name, a type and a nullability triple
- a second read of the service definition for a flag the type already carries
- a nullable type resolving to the non-nullable type object, which throws the flag away and
  forces all of the above

### Reworking one client

1. Give the type model the nullable form: one type per type and nullability, built from the
   non-nullable one, sharing its language type and whatever the type store binds after
   construction. Key the type cache on nullability too, so a list of nullable values and a list
   of values are distinct types.
2. Split the codec into the slot and position entry points, and delete the nullability argument
   from the position one.
3. Take the flag out of the collection and structure types, and out of coercion and structure
   field registration.
4. Point the client's krpctools backend at the type: the generated stubs name the nullable form,
   and the docs are rendered from the type alone.
5. Regenerate the golden fixtures. Only that client's should change.

The rework is one commit, amended into that client's step rather than added after it. The steps
of a phase are not green in turn, so judge the branch by its tip: `bazel test //:test`,
`bazel build //...`, then that client's own target and `//tools/krpctools:test`. A fixture that
moves for another language means a backend changed behavior rather than where it reads
nullability.

### Tests a client needs

Beyond the round trips already listed under [Tests](#tests), the cases that catch the failures
this shape is for:

- a nullable type of every kind resolves to a type sharing the language type of its
  non-nullable form
- a value at a nullable position holding a collection, and one holding a structure, at the byte
  level: the presence bool sits ahead of the whole encoding
- a structure field that is a collection with a nullable element
- a stream of a collection with a nullable element, which is the only path that reaches the
  presence bool through the stream decoder
- a null at a position that cannot hold one is rejected by coercion
- a nullable set element and a nullable dictionary key, which no service declares: a client that
  reads the type at every position handles them, and one that names the positions instead reads
  the presence byte as part of the value

## Documentation

- `doc/src/communication-protocols/messages.rst`: Phase 1 replaces the two slot flags with
  `Type.nullable`. Phase 2 adds the presence bool and the rule that separates it from
  `is_null`, and rewrites the Structures section, which states that a field is never null.
- `doc/src/extending.rst`: Phase 2 covers the serializable types list, the *Null Values* and
  *Nullable Value Types* sections, and the `KRPCStruct` criteria, which forbid a nullable
  field. Phase 3 documents `Position` and the path form of `KRPCNullable` beside the existing
  form.

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
  `IDictionary<string, IList<Vessel>>`, and a doubly nested case, `IList<IList<Vessel>>`.
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
5. The service adoptions Phase 2 is for: `SpaceCenter.CommNode` and `ActionGroupAction`.
   `CommLink` stays a class, since its `SignalStrength` is a live reading a client streams. See
   [struct-adoption-audit.md](../services/struct-adoption-audit.md). In progress, separately
   from steps 1 to 4.
6. Changelogs, as the final commit before merging.

### Phase 3: nullable collection elements

Follows the same order, on top of a merged Phase 2.

1. Core: `TypeSpec`, the four `Encoder.Encode` call sites, `Position` and the path form of
   `[KRPCNullable]`, and the scanner validation. Core tests.
2. TestService fixtures.
3. Python plus the shared krpctools path.
4. One step per remaining client: C#, C++, Java, Lua, cnano.
5. Changelogs.

Steps 1 to 5 are implemented.

## Open questions

None.

## Settled

- **Whether Phase 3 covers more than the dictionary value.** It does. A tuple and a dictionary
  value are both used the way a structure is, which is where the demand for a nullable field
  comes from, and a list falls out of the same mechanism with no corner case. A tuple standing
  in for a structure is still better declared as a `[KRPCStruct]`, which Phase 2 covers.
- **How a nullable position is named.** By name rather than by index, resolved above.
- **The C# client's descriptor shape.** A static `TypeSpec` per nullable shape, interned per
  service, rather than a `TypeInfo` built from the service definition. The reflection the client
  already does covers every position a CLR type can describe, and the spec covers the rest.
  Reading nullability from the spec alone is the rework above, not a change of shape.
- **How a client holds nullability.** On the type at the position, per
  [The shape a client takes](#the-shape-a-client-takes). Python, Lua and C# landed with the
  flag beside their types first, and were reworked. C++ landed with a nullable class at a
  slot spelled as the id-0 object, and was reworked to `std::optional` everywhere. The cnano
  client landed with nullability passed beside the type, and only some positions taking the
  nullable form. It was reworked to a slot and a position entry point, reading the type at
  each.
