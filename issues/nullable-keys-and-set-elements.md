# Allow nullable set elements and dictionary keys

**Status:** draft issue, not filed. Protocol change, deferred past 0.7.0 and likely dropped. Implemented on the `nullable-keys-and-set-elements` branch, which is not on origin. Labels: `enhancement`, `server`.

Design: [nullable-keys-and-set-elements.md](../design/protocol/nullable-keys-and-set-elements.md).

[PR #1091](https://github.com/krpc/krpc/pull/1091) made every nested type position nullable,
except a set element and a dictionary key. The server enforces the exception in
`TypeUtils.IsASetCollectionType`, `TypeUtils.IsAValidKeyType` and the `Encoder`. Server side
functions copy it as special cases: `Type.SetType`, `CreateSet`, `ToSet`, `GroupBy` and the Python
compiler's `plain_ptype`. A set built from nullable numbers has a different element type from the
list built from the same values, and it can throw where the list does not.

## Proposal

Types are uniform: any position may be nullable.

* A set may hold one null.
* A nullable key type is valid. Inserting a null key is a run-time error.
* Add `Position.Key`, so the attributes can name a key.
* Remove the special cases from server side functions and the Python compiler.

Each client needs its own decision on how to hold a null element or key. The design doc covers
every client and the phases.

## Changelog impact

Server and each client: an entry that set elements and dictionary keys may be nullable. Additive.
