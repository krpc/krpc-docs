# Add a public object id accessor to each client

Milestone: 0.8.0 · Labels: enhancement, client

`Expression.ConstantObject (ulong value)` takes an object by its id, so a script reads the id off a remote object. Python and Lua expose it only as `_object_id`, C++ as `_id`, and C# as a lower case `id` property. The server side functions tutorial calls the Python name "the internal attribute".

Add a public, documented, read-only accessor in each client, in that language's style, and keep the old names working: Python `object_id`, Lua `object_id`, C++ `id ()`, and C# `Id` with `id` marked `[Obsolete]`. Java's `id` field and cnano's `krpc_object_t` already serve. Check the generated stubs for a clashing `ObjectId` or `Id` member before settling the names, then update the tutorial and its example scripts.
