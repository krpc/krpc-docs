# A public object identifier in every client

**Status:** draft issue, not filed. Small, after 0.7.0. Labels: `enhancement`, `client:python`,
`client:lua`, `client:cpp`, `client:csharp`.

Two `KRPC` procedures take an object by its identifier, not as a class-typed parameter:

* `Expression.ConstantObject (ulong value)`
* `KRPC.GetObjectState (ulong id)`, added in 0.7.0

A class-typed parameter does not work for `GetObjectState`. Decoding the argument raises
`ObjectDestroyedException` for an object already dropped from the object store, before the
procedure runs.

To call either one, a client script has to read the identifier off the object. Some clients
give it only a private name:

| Client | Identifier | Visibility |
| --- | --- | --- |
| Python | `obj._object_id` | private by name |
| Lua | `obj._object_id` | private by name |
| C++ | `obj._id` | public member, private by name. A comment says it is public only for the encoder and decoder |
| C# | `obj.id` | public property, but lower case, which is not C# style |
| Java | `obj.id` | public final field, documented for `Expression.constantObject` |
| C-nano | `krpc_object_t` | the object is the identifier |

The docs already use the private names:

* `doc/src/scripts/tutorials/server-side-functions/TargetEvent.py` (`_object_id`) and
  `TargetEvent.cpp` (`_id`)
* `doc/src/tutorials/server-side-functions.rst`, which says "In Python it is the internal
  attribute `_object_id`"
* `doc/src/scripts/tutorials/object-lifetime/ObjectState.py` (`_object_id`), which comes with
  `GetObjectState`

## Proposal

Add a public, documented, read-only accessor in each client, named in that language's style. Keep
the old names working.

| Client | Add |
| --- | --- |
| Python | `obj.object_id` property. Keep `_object_id` as the backing attribute |
| Lua | `obj.object_id` field or `obj:object_id ()`, whichever matches the Lua client's conventions |
| C++ | `uint64_t id () const`. `_id` stays public for the encoder and decoder |
| C# | `Id` property. Mark `id` `[Obsolete]` |
| Java | nothing, `id` is already public |
| C-nano | nothing |

* The name must not clash with a generated member. A service class with an `ObjectId` or `Id`
  property would shadow the accessor, or be shadowed by it. Check the clientgen output for every
  service before choosing names. If there is a clash, use a name no service can generate, such
  as Python's `object_id` against a `snake_case` property.
* Change the docs listed above to use the public names, and drop the "internal attribute"
  sentence.
* Add a test to each client's suite that reads the accessor and passes it to
  `KRPC.GetObjectState`.

## Decide

* The names, after the clash check.
* Whether to keep only the accessor, or also have `GetObjectState` and `ConstantObject` accept an
  object directly through client-side sugar. The accessor is the smaller change, and covers both.

## Changelog impact

One entry per client that gains an accessor. For C#, `**Deprecated:**` on `id`.
