# Nullable set elements and dictionary keys

**Status:** proposal. No issue yet. Follow-up to
[nested-nullable-values.md](nested-nullable-values.md) ([PR #1091](https://github.com/krpc/krpc/pull/1091)),
which made every nested position nullable except a set element and a dictionary key.

## Problem

The exclusion is a protocol rule, and the server enforces it in three places:

| Site | Rule |
| --- | --- |
| `TypeUtils.IsASetCollectionType` | rejects `HashSet<T?>` |
| `TypeUtils.IsAValidKeyType` | allows only `int`, `long`, `uint`, `ulong`, `bool` and `string`, none of them nullable |
| `Encoder.WriteSet`, `Encoder.WriteDictionary` | refuse a null element or key |

The attribute vocabulary has no name for either position. `Position.Element` is a list element,
and there is no `Position.Key`.

[Server side functions](../server-side-functions/server-side-functions.md) have to produce valid kRPC
types, so they copy the rule as special cases:

- `Type.SetType`, `Type.DictionaryType`, `CreateEmptySet` and `CreateEmptyDictionary` reject a
  nullable element or key type.
- `CreateSet`, `CreateDictionary`, `ToSet`, `GroupBy` and `BuildDictionary` unwrap a nullable
  number to its value type, and check for a null when the function runs.
- The Python compiler strips nullability from set and key types (`plain_ptype`), and rejects a
  `None` in a set literal.

A set built from a nullable number has a different element type from the list built from the
same values. It can also throw where the list would not.

## Decision

Types are uniform. Any position may be nullable, a set element and a dictionary key included.

- **A set may hold one null.** .NET `HashSet`, Python `set`, Java `HashSet` and C++
  `std::set<std::optional<T>>` all hold one.
- **A null key is a run-time error.** A nullable key type is valid, and a dictionary of that type
  with only non-null keys encodes and decodes. Inserting a null key fails. A .NET `Dictionary`
  throws on one, on the server and in the C# client, so the container enforces it. The error
  keeps the message "a dictionary key cannot be null".
- **`Position.Key` names a key, and `Position.Element` names a set element too.** A
  reference-typed key or element, such as a string, can then be declared nullable with
  `[KRPCNullable]`, as a value-typed one already is through `Nullable<T>`.

The original reasons for the exclusion were that a null key carries no meaning, and that a
nullable set element costs `std::optional` hashing in C++ and a flag array in cnano. Both
clients already pay that cost: their generators emit `std::optional` and `nullable_X` wrappers
at these positions today. The exclusion now costs more than it saves, in special cases.

## Clients

No client rejects either position, and krpctools has no rule about them. Every generator names
key and element types through its at-position helper, which honors `nullable`.

| Client | Presence bool at element and key | Change needed |
| --- | --- | --- |
| Python | read and written | `encoder.py` sorts dictionary keys, and `None` among them raises `TypeError`. Sort with the null first. |
| C# | read and written | A null key decoded into a `Dictionary` throws `ArgumentNullException`. Raise the server's error. |
| C++ | **skipped**: `decoder.hpp` and `encoder.hpp` call `decode`/`encode` for set elements and map keys | Use `decode_item`/`encode_item`. Generated code already declares `std::optional` there, so today a nullable position misdecodes, and encoding one does not compile. |
| Java | read and written | none |
| Lua | read and written, a null is the `Types.none` sentinel | `encoder.lua` sorts keys, and `Types.none` among them fails. Sort with the null first. |
| cnano | generated `nullable_X` wrappers | none |

## Phases

1. **Protocol**, on its own branch from main:
   - `TypeUtils` accepts both positions, and `IsAValidKeyType` accepts the nullable value key types.
   - The encoder writes, and the decoder reads, the presence bool at both positions.
   - `Position.Key` is added, with scanner support.
   - The client fixes in the table above.
   - TestService procedures echo a `HashSet<int?>`, a set of nullable strings and an
     `IDictionary<int?, string>`. Each client round-trips a set holding a null and a nullable key
     type, and gets the error for a null key.
   - Docs: `messages.rst` (the presence bool applies at every position), `extending.rst`
     (`Position.Key`, `Element` on a set), and changelogs.
2. **Server side functions**, rebased onto phase 1, drop their special cases:
   - `CreateSet`, `CreateDictionary` and the collection operations join types as `CreateList`
     does.
   - The checks in `Type` and the empty-collection factories go.
   - The Python compiler keeps nullability at both positions.
   - A null key throws when the function runs, from the dictionary itself.

## Rejected alternatives

- **Making a null key work.** It needs a dictionary type that admits a null key on the server
  and in the C# client, which no service or client wants.
- **Relaxing sets only.** It keeps every special case for dictionary keys, so the code stays
  split by position.
