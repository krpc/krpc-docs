# Server side functions: name types, exceptions and fields by id

Seven `KRPC` procedures of the server side function API take names as strings:

| Procedure | Names |
| --- | --- |
| `Type.ClassType`, `Type.EnumerationType`, `Type.StructType` | a service and a type |
| `Expression.ConstantEnum` | a service and an enumeration |
| `Expression.Throw`, `Expression.TryCatch` | a service and an exception |
| `Expression.GetField` | a structure field |

C-nano calls by id to keep names out of flash. A sketch that builds an expression over a
`SpaceCenter.Vessel` still puts `"SpaceCenter"` and `"Vessel"` in flash. Phase E0 of the client
errors work gives every type an id, reported in `GetServices`. Nothing in the function API accepts
those ids yet.

* **Add a variant of each procedure that takes ids.** A type or exception is named by its service
  id and its type id. A structure field is named by its index, its position in the structure's
  definition, which the wire encoding already fixes.
* **The string procedures stay.** The other clients have the names in their stubs, and keep using
  them.
* **C-nano defines a macro per class, enumeration and structure,** with the pair of ids, as E5
  does for exceptions. The variants take the pair.
* **Rewrite the C-nano server side function examples to use ids.** `CollectionEvent.c`,
  `NotLoadedEvent.c`, `StructureField.c` and `ThrowException.c` under
  `doc/src/scripts/user-guide/server-side-functions/` pass names today.

The variants are `Type.ClassTypeById`, `EnumerationTypeById` and `StructTypeById`,
`Expression.ConstantEnumById`, `ThrowById`, `TryCatchById` and `GetFieldByIndex`, as kRPC has no
overloads. Each id pair is two parameters, `serviceId` then the type's id, so one C-nano macro
fills both. The macros are `KRPC_CLASS_`, `KRPC_ENUMERATION_` and `KRPC_STRUCT_`, beside
`KRPC_EXCEPTION_`. Each structure field also has a `KRPC_FIELD_` macro holding its position, so
a program never writes the number, and a new client version can reorder fields safely.

`Expression.Parameter`, `Variable` and `StateVariable` take names the program chooses, which refer
to no definition. They need no ids.

Depends on phase E0 of
[client-errors.md](https://github.com/krpc/krpc-docs/blob/main/design/client-errors.md#type-ids),
and on E5 for the C-nano macros.
