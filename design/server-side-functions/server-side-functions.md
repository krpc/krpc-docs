# Server-side functions

**Status:** done in [PR #1069](https://github.com/krpc/krpc/pull/1069), open for review, which
closes umbrella issue [#679](https://github.com/krpc/krpc/issues/679). Resumable functions are not
built; their design moved to [`resumable-functions.md`](resumable-functions.md).

Linked issues: [#517](https://github.com/krpc/krpc/issues/517) (per-element calls in predicates),
[#503](https://github.com/krpc/krpc/issues/503) (object constants),
[#521](https://github.com/krpc/krpc/issues/521) (multiplication/mixed-type arithmetic),
[#608](https://github.com/krpc/krpc/issues/608) (documentation).

## Goals

Server-side functions let a client do *almost* anything on the server that it can do locally:

1. Run a complex computation over multiple RPC results on the server, triggered and evaluated in a
   single physics tick, without network round trips (custom events and computed streams).
2. Stream the result of a computation out of the server (efficient telemetry), not just the result
   of a single RPC.
3. Run a whole function on the server once, within a single physics tick, for its result and its
   side effects. Events and streams cannot serve this, because they re-evaluate on every update.
4. Let clients write all of this in their own language rather than by hand-assembling trees.

This means: calling RPCs (including per-element inside collection operations), passing object
references around, arithmetic, comparisons and logic over mixed numeric types, collection
processing, statements and control flow, and returning any serializable kRPC value to the client.

## Vocabulary

Two things are named, and keeping them distinct is what the API names follow:

* an **expression** is a node of the algebra: `Add`, `Not`, `ConstantInt`, `While`, `Block`,
  `Break`. Control flow included, this is an expression algebra, and every node is one.
* a **function** is the whole program a client assembles out of them, and the only thing it ever
  runs, streams or compiles.

So the algebra keeps the name `Expression` and everything a user invokes is named for the function:
`KRPC.RunFunction`, `KRPC.AddFunctionStream`, `Client.compile_function`,
`Connection.CompileFunction`, `krpc/function_stream.hpp`. The class itself is not renamed: naming it
`Function` would make every value node read as a function (`Function.ConstantInt(1)`), and
`System.Linq.Expressions`, which the implementation compiles to directly, keeps the name
`Expression` for a factory class that contains `Block`, `Loop`, `Goto` and `TryCatch` too. A user
builds a function out of expressions, which is how every language describes itself.

The split is a naming rule, not a type distinction. A function is the root expression of a tree, so
`KRPC.RunFunction`, `KRPC.AddFunctionStream` and `KRPC.AddEvent` all take an `Expression`. Each
names its parameter `function`, which is what tells a reader that the whole tree is wanted rather
than a node of one. `KRPC.AddEvent` was renamed from `expression` for this, which is the one
user-visible break the rule costs.

The lambda node is `Expression.Lambda(parameters, body)`, after the LINQ node it maps to. It is
`Invoke`d or handed to `Select`/`Where`; it is not the whole function, and a block can be handed
straight to `RunFunction` with no lambda around it. A function that uses `Return` is the exception:
it is a parameterless lambda, invoked, since `Return` binds to a lambda (see "Statements, control
flow and side effects").

Prose, error messages and XML doc summaries follow the same split: a node is an expression, the
whole is a function. The tutorial's two properties are properties of a function, the yield message
reports that a function is evaluated within a single tick, and the client guides introduce the
feature as a server side function. The API reference page keeps the title `Expressions`, which
names what it documents, and links the tutorial for the rest.

Whether a client should reach the factories through a builder object (`conn.Expression.Not(...)`)
rather than through the class is an open question, unaffected by this split.

## Approach

`KRPC.Expression` and `KRPC.Type` are ordinary kRPC remote classes whose static factory RPCs build a
`System.Linq.Expressions` tree server-side, which is compiled with `.Compile()` (real JIT, native
speed, proven under KSP's Mono). This is the LINQ-provider pattern: a language-neutral tree
assembled via RPCs, so every client works in its own language; no protocol changes are needed; and
the node algebra is a whitelist, which is safer than arbitrary code. Client-side compilers map each
language's native syntax onto the same factories, so the tree is an intermediate representation
rather than something users assemble by hand (see "Client-side compilation").

Two alternatives were rejected:

* **JIT-compile user-supplied C# (Roslyn).** Non-C# clients would have to write C# source strings (a
  Python client writing C# is a bad fit), Roslyn is a very large dependency to ship inside a game
  mod, and arbitrary code is strictly less safe than a node algebra.
* **An embedded scripting language (MoonSharp Lua, the kOS model).** Every client would write a
  second language rather than none of them; it requires an auto-generated Lua binding for the whole
  service surface; and it pays per-tick interpreter overhead where compiled LINQ delegates are free.

No protocol (`krpc.proto`) changes. Everything is additive service API surface plus client library
helpers, so it stays within the current protocol and composes with the planned #906 protocol
improvements (see "Interaction with planned protocol work").

## Design

### Types and introspection

`KRPC.Type` names any type the wire can carry:

* `ClassType(service, name)`, `EnumerationType(service, name)` and `StructType(service, name)` for
  service-defined types.
* `TupleType(valueTypes)`, `ListType(valueType)`, `SetType(valueType)` and
  `DictionaryType(keyType, valueType)` for collections.
* `Double`, `Float`, `Int`, `Long`, `UInt`, `ULong`, `Bool`, `String` and `Bytes` for values.

Names avoid `class`/`list` style keyword collisions in generated clients. Class, enumeration and
structure name resolution needs the CLR type, which the scanner has in hand when it builds
`ClassSignature`, `EnumerationSignature` and `StructSignature`; it is stored there as a
non-serialized `UnderlyingType` property, so the service-definitions JSON is unaffected.
`Type.ClassType` then resolves through `Services.Instance.Signatures[service].Classes[name]`.

Introspection is the half a dynamic client needs to decode a computed value whose type the stub does
not declare:

* `[KRPCEnum] TypeCode` in the KRPC service mirrors the protocol's type codes: `Double`, `Float`,
  `SInt32`, `SInt64`, `UInt32`, `UInt64`, `Bool`, `String`, `Bytes`, `Class`, `Enumeration`,
  `Struct`, `Tuple`, `List`, `Set`, `Dictionary`.
* Instance properties on `Type`: `Code`, `Service` and `Name` (empty unless the type is defined by a
  service), and `Types` (generic arguments, empty otherwise).
* `Expression.ReturnType` gives the `Type` an expression evaluates to, and `HasReturnType` reports
  whether it has one at all. `ReturnType` throws for types that cannot be returned to a client, such
  as the lazy `IEnumerable<T>` produced by `Select`/`Where`, and the message says to wrap it in
  `ToList`/`ToSet`.

A dynamic client walks `ReturnType` recursively, reconstructs the equivalent protobuf `Type` message
locally, and feeds its existing decode machinery (`Types.as_type` in Python). Statically typed
clients do not need this: the user supplies the expected type as a generic parameter.

**As built, Java walks `ReturnType` too.** Its `Stream<T>` is constructed from a protobuf `Type`
rather than from a `Class<T>`, and its decoder takes the same message, so there is nothing for a
type argument alone to drive. `Connection.runFunction` and `Connection.addStream` therefore
introspect the type and cast the decoded value to `T`, which the compiler cannot check. C# and C++
follow the design and decode at the type the user names.

### Numeric promotion in binary operators

LINQ expression trees require exact operand type matches, so `int * double` is not directly
constructible. `Add`, `Subtract`, `Multiply`, `Divide`, `Modulo`, `Power` and the numeric
comparisons (`Equal`, `NotEqual`, `GreaterThan(OrEqual)`, `LessThan(OrEqual)`) therefore apply C#'s
standard binary numeric promotion before building the LINQ node: if either operand is `double` then
both go to `double`; else `float` to `float`; else `ulong` to `ulong` (an error if the other side
is a signed type that cannot be implicitly converted); else `long` to `long`; else `uint` plus
`int` to `long`; else `uint` to `uint`; else `int`. Promotion applies only when both operand types
are numeric and differ. `Power` converts its promoted operands to double for the underlying
`Math.Pow`, and takes its result at the promoted type. `Conditional` promotes its two branches the
same way. Explicit `Cast` remains available.

`Negate` follows the unary form of the same rules: a `uint` is negated as a `long`, and a `ulong`
is an error, as in C#. The compilers used to multiply by `-1`, which gave a `uint` operand the
wrong type and a `ulong` one no type at all.

A value used in a position of a fixed type follows one rule: a numeric conversion that widens is
implicit, and one that narrows needs `Cast`. The positions are:

* a procedure argument (`CallWithArguments`, `DeferredCallWithArguments`);
* a collection element, a dictionary key or value, the value given to `Append`, `Set`, `Remove`
  and `Contains`, and the key given to `Get` on a dictionary;
* a structure field (`CreateStruct`);
* a variable assignment (`Assign`), and an argument to `Invoke`.

A nullable number, which a procedure returning a nullable value type produces as `Nullable<T>`,
takes part in both rules as its underlying `T`: promotion and each position convert it to `T`
first, which throws when the value is null. A nullable parameter takes it as it is, so a null
passes through.

### Constants

Value constants are `ConstantDouble`, `ConstantFloat`, `ConstantInt`, `ConstantLong`,
`ConstantUInt`, `ConstantULong`, `ConstantBool`, `ConstantString` and `ConstantBytes`. Both
compilers use the wide integer constants, so a constant outside `int` keeps its value. The Python compiler gives
an integer literal the narrowest of `int`, `long` and `ulong` that holds it, and the exact type of a
parameter it is passed to.

`ConstantObject(ulong value)` is a constant object reference, passed as its object identifier (the
same `uint64` the protocol already uses to encode class instances; `0` is null, which is rejected
here). The server recovers the instance through `ObjectStore.GetInstance(id)` and uses its
most-derived `KRPCClass` type as the node's static type, so no protocol change and no
self-describing wire value is needed, which is what blocked
[#503](https://github.com/krpc/krpc/issues/503). Clients already expose the identifier
(`RemoteObject.id` in C#, `_object_id` in Python, `Object::_id` in C++, `RemoteObject.id` in Java).

`ConstantEnum(service, name, value)` names a member of a service's enumeration. Casting an int to an
enumeration type works too, but it makes the caller spell out a conversion that carries no
information and cannot check the value against the enumeration's members; `ConstantEnum` does check
it when the node is built.

### Null values

There is no null constant. A value can be null only where a procedure returns one, so the algebra
tests for it rather than producing it: `IsNull(value)` is a boolean, `ReferenceEqual` against null
for a class and `Equal` against a null `Nullable<T>` for a nullable number. A value whose type
cannot hold null is an error when the node is built. The compilers map `x is None` and `x == null`
onto it.

### Calls

`Expression.Call(ProcedureCall call)` embeds an RPC whose arguments are fixed when the node is
built. `Expression.CallWithArguments(ProcedureCall call, IDictionary<int, Expression> args)`
supplies the call's arguments as sub-expressions instead, keyed by the position of the parameter
each one supplies (position 0 is the instance for class members). A position with no entry falls
back to the argument encoded in `call`, then to the parameter's default value; a position outside
the procedure's parameter list is an error. Each expression's static type must be assignable to the
parameter's CLR type, or be a numeric type that widens to it (see "Numeric promotion"), checked when
the node is built. This is what makes per-element calls work (#517):

```
param     = Expression.Parameter("e", Type.ClassType("SpaceCenter", "Engine"))
hasFuel   = CallWithArguments(get_call(any_engine.has_fuel), {0: param})
predicate = Expression.Lambda([param], Expression.Not(hasFuel))
anyOut    = Expression.Any(Expression.Call(get_call(parts.engines)), predicate)
```

The client builds the template `ProcedureCall` from any convenient instance, since only the
procedure identity is used for overridden positions.

`CallWithArguments` subsumes `Call`, and the two share one implementation, so the second factory
costs a signature and nothing else. `Call` exists because it is the common case and the one a client
can build without knowing anything about parameter positions: a client already holds an encoded
`ProcedureCall` for any RPC it can make, and passing it is the whole call. Without it every embedded
call, including those with no computed arguments at all, would have to pass an empty collection.

Arguments are keyed by position rather than given as a list with null holes because nullable values
([PR #1017](https://github.com/krpc/krpc/pull/1017)) signal null out of band rather than by an
object id of 0, so a null element inside a collection is not encodable by any client. Positions need
no placeholder, and there are no trailing nulls to trim.

Both factories compile to a **direct, statically typed `LinqExpression.Call` of the procedure's
underlying `MethodInfo`**, exposed as `IProcedureHandler.Method` by all three handler types
(property accessors are wrapped through their getter/setter `MethodInfo`, so every RPC is
inlinable). Arguments are typed sub-expressions or typed constants, built at the method's own
parameter types rather than the procedure signature's: a nullable value-type parameter is `T` in the
signature and `Nullable<T>` on the method, and only the latter types the call. There is no
`object[]` allocation and no boxing, and the .NET JIT can inline the target: `StdLib.Sqrt` inlines
down to `Math.Sqrt`, measured 38.4 to 7.8 ns/call with gen-0 collections eliminated, which matters
under Unity's Boehm GC.

Semantics match an ordinary RPC exactly, via two lean static helpers emitted around the call:

* `Services.CheckExpressionGameScene(procedure)` before every invocation, the same scene-mask check
  and `RPCException` as the ordinary dispatch path;
* `Services.CheckExpressionReturnValue(procedure, value)` after invocation, emitted only for
  reference-typed returns where null is not permitted. A direct typed call can only violate the
  declared return type by returning null, so the per-evaluation `IsInstanceOfType` reflection check
  of the boxed dispatch path is provably unnecessary.

RPC errors are thrown as exceptions, so they propagate to whatever is evaluating the expression.
`YieldException` propagates too, and is reported as an error; see "Yielding procedures inside a
function".

### Statements, control flow and side effects

The node algebra covers running a function, not only computing a value, so that a client can express
anything it could write in a loop locally. LINQ expression trees support all of this; the work is
exposing it as factories with kRPC-shaped semantics.

* Local state: `Variable(name, type)` declares one, `Assign(variable, value)` writes it, and
  `BlockWithVariables(variables, expressions)` scopes them. `Block(expressions)` is the
  no-declaration form. A block evaluates to its last expression.
* Control flow: `IfThen`/`IfThenElse`, `While(condition, body)` and
  `ForEach(variable, collection, body)`, with `Break()` and `Continue()` inside loops. `While` and
  `ForEach` are desugared into LINQ's loop and label primitives. `Break`/`Continue` are emitted as
  calls to marker methods and rewritten to `goto` against the enclosing loop's labels when the loop
  node is built; binding to the nearest enclosing loop falls out of trees being built
  innermost-first.
* Early exit: `Return(value)` and `ReturnNothing()` are likewise markers, bound to a label that
  `Expression.Lambda` wraps around the function body, so a return anywhere in a nested block leaves
  the whole function. A body that ends with a statement, such as an `IfThenElse` returning on both
  branches, takes its result type from its first `Return(value)`. Reaching the end of such a body
  raises `KRPC.InvalidOperationException`.
* Side effects: calls to procedures with no return value (including property setters) are ordinary
  statement expressions, and collections can be built imperatively.

`ForEach` desugars to an enumerator loop wrapped in a `try`/`finally` that disposes the enumerator,
matching what a C# `foreach` statement compiles to. It matters for a loop over a lazy sequence,
whose enumerator holds the enumerator of its source. The loop variable is a `Variable` that an
enclosing `BlockWithVariables` declares, as LINQ requires. `ForEach` does not check this, so a
missing declaration surfaces as LINQ's own error when the function is compiled.

`Return` is bound when `Lambda` is built, and a function that returns early is therefore
`Invoke(Lambda([], body), {})`, which is what the Python compiler emits for a function with
statements. A block containing `Return` handed straight to `RunFunction` is reported as an unbound
marker. A bare `Lambda` is rejected too, since its type is a delegate, which cannot be sent to a
client.

Void-typed nodes are the reason several things elsewhere are special-cased: an expression whose type
is `void` has no return type to report, cannot be streamed, and is only meaningful under
`RunFunction`.

**A loop is not interruptible, and this is a hazard.** `MaxTimePerUpdate` is checked between
continuations in the execution loop, never inside one evaluation, so a `While` whose condition never
becomes false hangs the game's main thread with no recovery. Loops are what make that reachable, and
closing it needs its own design: an iteration or time budget checked inside the loop costs something
on every iteration of every loop, which is a trade worth deciding deliberately. It is documented as
a limitation.

### Tuples, collections and strings

Tuples are built by `CreateTuple` and read by `Get`, which special-cases tuple types to map the
index onto the corresponding `ItemN` property. The index must be a constant, and this is inherent
rather than a limitation to lift: tuple elements are differently typed, so an index computed at
evaluation time would leave the resulting node with no static type. It is documented as such.
A tuple has at most seven elements, matching the flat CLR tuple types; the eighth position holds
a nested tuple, which is not a shape kRPC can name or carry.

Structures ([#866](https://github.com/krpc/krpc/issues/866)) are built by
`CreateStruct(type, fieldValues)` and read by `GetField(value, name)`. A field is named to the
server by the name it is declared with, since the wire type carries only the structure's service
and name; the Python compiler maps a pythonic attribute name back to the declared one through the
structure's position in the definitions.

Collections are built from their elements by `CreateList`, `CreateSet` and `CreateDictionary`, or
created empty by `CreateEmptyList`, `CreateEmptySet` and `CreateEmptyDictionary`. An empty one
names its element types, since there is no element to infer them from. Either is then mutated by
`Append`, `Set`, `Remove`, `RemoveAt` and `Clear`, which "Collection operations named by what they
do" below covers. `Get` of a missing dictionary key raises `KRPC.ArgumentException`, where the CLR
indexer's `KeyNotFoundException` has no kRPC type. `ContainsKey` tests for a key, and `Contains`
rejects a dictionary with a message pointing at it, since the CLR would compare key and value pairs.
`StringSplit` gives a `List<string>`, so the parts can be appended to.
The query surface covers counting, membership, `Select`, `Where`,
`Any`, `All`, `Skip`, `Take`, `ToList`/`ToSet`, the aggregations `Sum`, `Average` and `Min`/`Max`,
`Aggregate`/`AggregateWithSeed`, and:

* **Dictionary enumeration**: `DictionaryKeys` and `DictionaryValues`, each producing a list rather
  than the `KeyCollection`/`ValueCollection` the CLR returns, because those are nested generic types
  whose first type argument is the dictionary's key type either way, so a value collection would
  report the wrong element type to everything downstream.
* **Element selection**: `First`, `Last`, `ElementAt`, and `MinBy`/`MaxBy`, which give back the
  value producing the smallest or largest key rather than the key.
* **Reshaping**: `SelectMany`, `Distinct`, `Reverse`, `Zip`, `Union`/`Intersect`/`Except`, `Concat`,
  `OrderBy`, `GroupBy`, and `BuildDictionary`, which builds a dictionary from a collection by
  running a key function and a value function on every element.

`GroupBy` produces `IDictionary<K, IList<T>>` rather than LINQ's `IEnumerable<IGrouping<K,T>>`,
since `IGrouping` is not a type kRPC can carry and a dictionary is what the result is wanted for.
Its key type is checked against the dictionary key rules when the node is built. `MinBy`, `MaxBy`
and `GroupBy` are single-pass helpers rather than LINQ calls.

#### Collection operations named by what they do

The mutations were first one node per collection and operation. Eleven nodes collapse into five,
each named for the operation, with the type of the collection deciding what it does:

| Node | List | Set | Dictionary | Replaces |
| --- | --- | --- | --- | --- |
| `Append(c, value)` | adds at the end | adds | - | `ListAdd`, `SetAdd` |
| `Set(c, index, value)` | writes an element | - | writes an entry | `ListSet`, `DictionarySet` |
| `Remove(c, value)` | removes a value | removes a value | removes by key | `ListRemove`, `SetRemove`, `DictionaryRemove` |
| `RemoveAt(list, index)` | removes by position | - | - | `ListRemoveAt` |
| `Clear(c)` | empties | empties | empties | `ListClear`, `SetClear`, `DictionaryClear` |

* **The shape follows `Get`**, which already read a tuple, a list and a dictionary through one
  node. A client learns one verb per operation, and the compilers dispatch on the tracked type
  rather than choosing a node per collection.
* **`Append` is not `Add`**, because `Add` is numerical addition.
* **Each node checks the kind of collection it was given.** The old `ListAdd`, `ListRemove`,
  `ListClear` and `SetClear` went through `ICollection`, so `ListAdd(set, value)` added to a set.
  The checks make a wrong collection an error when the tree is built.

**Strings are deliberately not collections.** Every collection operation rejects a string with a
message saying so, through `CheckIsNotAString`, reached either directly or through
`CheckIsEnumerable` (which `GetEnumerableValueType` calls). Strings have their own operations
instead, one `String` prefixed family. A string is immutable, so `StringConcat` produces a value
where `Append` mutates, and the algebra has no character type. The prefix keeps
`StringLength`, `StringGet` and `StringContains` distinct from the collection operations of the same
concept, and makes the family sort together in the generated reference and in `doc/order.txt`.

| Node | Returns |
| --- | --- |
| `StringLength(s)` | `int` |
| `StringGet(s, index)` | `string` of length one |
| `StringSubstring(s, start, length)` | `string` |
| `StringIndexOf(s, value)` | `int`, `-1` when absent |
| `StringContains`, `StringStartsWith`, `StringEndsWith` | `bool` |
| `StringToUpper(s)`, `StringToLower(s)` | `string` |
| `StringTrim(s)`, `StringTrimStart(s)`, `StringTrimEnd(s)` | `string` |
| `StringReplace(s, old, new)` | `string` |
| `StringSplit(s, separator)` | `IList<string>` |
| `StringJoin(separator, strings)` | `string` |
| `StringConcat(strings)` | `string` |

`StringIndexOf` returns `-1` rather than a nullable `int`. Nullable values would be the more honest
type, but `-1` is what `str.find` and `String.IndexOf` return in the languages both compilers
translate from, so it keeps the mapping transparent. `StringTrim` trims whitespace and takes no
character set, matching the no-argument form of both.

**Every one of these is culture sensitive and must be pinned.** `ToUpper`/`ToLower` are culture
sensitive in C#, and so are the default `IndexOf`, `StartsWith`, `EndsWith` and `Replace` overloads.
Left alone they would make the same function return different answers on a German or Turkish game,
which is the class of bug the [locale hardening](../locale-hardening.md) work fixed by hand and the
[culture analyzers](../build-tools/culture-analyzers.md) rules `CA1307`, `CA1310` and `CA1311` exist
to catch. So: `ToUpperInvariant`/`ToLowerInvariant`, and `StringComparison.Ordinal` on every
comparison overload. The nodes take no culture argument. A server side function is a program a
client wrote, not a readout for the player, so it wants one answer everywhere;
`ConvertToStringHelper` already pins `InvariantCulture` for the same reason.

**Characters are single-character strings.** There is no character type in the algebra or on the
wire. A one-character string composes directly with every other string operation, decodes correctly
in every client with no new code, and is what a Python or Lua user expects; C#, Java and C++ users
index it once to get a `char`. The reported type is `STRING`, which is true, rather than a value
carrying a convention the wire does not record. Two alternatives were rejected:

* **A `CHAR` type code in the protocol**, as disproportionate. No RPC anywhere in kRPC uses a
  character type, so the code would exist solely to serve this one operation, at the cost of
  encode/decode and dynamic type handling in all six clients plus a version-skew story, and half the
  clients (Python, Lua) have no character type to map it to. Worth reopening only if strings become
  iterable, or alongside #866, which already adds a type code and would amortize the per-client
  work.
* **Reusing `uint32`**, as the weakest option. It is not self-describing, so a dynamic client
  decoding by reported type yields a number with no way to tell it from one; it composes with no
  string operation, so it would need conversion nodes and numeric overloads to be usable at all; and
  as a Unicode code point it does not correspond to the UTF-16 code unit that C# and Java call
  `char`.

### Exceptions

A function that validates its inputs, or that wants to signal a condition to the client, needs to
raise; a function that calls an RPC which can fail needs to handle, or the whole function is
abandoned. Both halves are in the algebra.

Delivery needs nothing new. Any exception raised while evaluating an expression is passed to
`Services.HandleException`, which produces an `Error` carrying the service and name of the exception
type alongside its description, so the client reconstructs the correct typed exception.
`FunctionStream` and `EventStream` report it as an error result, and `RunFunction` propagates it as
an ordinary RPC error.

**Raising** is `Throw(service, name, message)`, evaluating as a statement, with `message` an
expression so that a function can build it rather than only name a constant. Only exceptions
registered with `[KRPCException]` can be raised, which keeps the boundary well defined and gives the
client a typed exception it can catch, applying the same principle as return values: only what kRPC
can represent crosses the wire. An arbitrary CLR exception would arrive as an opaque error. Naming
one as `(service, name)` follows `ClassType`, and the exception types already provide the
`(string message)` constructor this needs.

A throw is a statement rather than a value, so an early exit is written as an `IfThen` containing a
throw. The typed form LINQ offers, for a throw in a value position such as one branch of an
`IfThenElse`, is not proposed: trees are built innermost-first, so there is no surrounding context
to infer the type from and it would have to be supplied explicitly at every use.

There are five exceptions to choose from and no service defines its own: `ArgumentException`,
`ArgumentNullException`, `ArgumentOutOfRangeException`, `InvalidOperationException` and
`ObjectDestroyedException`, all in the KRPC service. Signaling a condition therefore means throwing
a generic type and putting the meaning in the message, which is worth documenting rather than
leaving users to work out that there is no custom exception type to define.

**Handling** is `TryCatch(body, service, name, message, handler)` for a named exception,
`TryCatchAll(body, message, handler)` for any, and `TryFinally(body, finalizer)` for cleanup that
runs either way. Body and handler are evaluated as statements through the existing `AsStatement`, so
they need not produce values of the same type.

`message` is an optional string variable that the caught exception's message is assigned to before
the handler runs. **The exception object itself is never exposed.** Binding only the message keeps
exceptions out of the value algebra entirely: nothing needs an exception-typed entry in `KRPC.Type`,
and no value that cannot cross the boundary can be carried toward it. LINQ's `Catch` binds the
exception rather than its message, so the implementation catches into a synthesized variable and
assigns `.Message` from it as the first statement of the handler.

**A name must resolve to every CLR type that reaches the client under it.** This is the one thing
that has to be right, and the obvious implementation gets it wrong.
`[KRPCException(MappedException = ...)]` maps a CLR exception type onto a kRPC one, and
`HandleException` applies that mapping on the way out; four of the five kRPC exceptions have one.
Services throw the CLR types, not the kRPC ones: `service/SpaceCenter/src` has 145
`throw new InvalidOperationException`, 73 `ArgumentException`, 46 `ArgumentNullException` and 22
`ArgumentOutOfRangeException`, and no service file imports the kRPC exception namespace, so every
one of those is a `System.*` type. A `TryCatch`
resolving `("KRPC", "InvalidOperationException")` to the kRPC type alone would catch almost nothing
an RPC actually throws, while the same exception escaping the function arrives at the client as
`KRPC.InvalidOperationException`. Catch and delivery would disagree, which is worse than not having
the node at all. So a name resolves to a **set**: the kRPC type plus every type mapped onto it,
obtained by inverting `Services.MappedExceptionTypes`, with one LINQ catch block emitted per type
over a shared handler. The set is fixed when the scanner runs.

**The set must not widen either, and a CLR catch block widens it.** `catch (System.ArgumentException)`
also catches `ArgumentNullException` and `ArgumentOutOfRangeException`, which map to kRPC types of
their own, and it catches `ObjectDisposedException`, which maps to nothing and so reaches the client
with no name at all. `HandleException` maps by exact type, so each of those arrives under a name the
catch did not name, and the kRPC exception classes are flat: they are all `sealed` and derive from
`System.Exception`, so no client can express the subclass relationship the catch is assuming. Each
handler therefore opens with `Services.ExpressionExceptionIsNamed(caught, type)` and rethrows when
it is false. An exception filter would say the same thing more directly, and is avoided here for the
reason `TryCatchAll` avoids it. The rule the two halves buy is one sentence: a name catches exactly
the exceptions that reach the client under it.

**An RPC failure is not nameable, and is documented as such.** Direct call emission means there is
no `ExecuteCall` wrapper, so a procedure's own exception propagates as it is, and the two checks
emitted around a call, the game scene mask and the null return from a non-nullable procedure, throw
`RPCException`, an internal sealed class with no `[KRPCException]`. Both can only be caught by
`TryCatchAll`, and both reach the client as an untyped error. Making `RPCException` a kRPC exception
would fix it, but it would also change what an ordinary failing RPC looks like to every client, so
it belongs to error reporting rather than to this work.

**A catch-all must not swallow `YieldException`.** A procedure that pauses execution unwinds by
throwing it, and the stream evaluating the expression reports the pause. Catching it would turn that
into a handled error and silently break any such procedure used inside a `TryCatchAll`. An exception
filter would express this directly, but LINQ filters are worth not depending on under KSP's Mono: a
`YieldException` handler whose body is a bare `Rethrow`, emitted ahead of the catch-all handler,
does the same job with primitives the algebra already compiles. Named catches are unaffected, since
`YieldException` is not a `[KRPCException]` and so cannot be named.

**Semantics per context** are documented rather than left to be discovered: an exception that
escapes a function surfaces immediately as an RPC error from `RunFunction`, and from a stream or
event it becomes an error result. The server then removes the stream, the rule
[#269](https://github.com/krpc/krpc/issues/269) settled for every stream, so a client that wants
to keep watching builds a new one.

`ExceptionSignature` does not record the CLR type of the exception, unlike `ClassSignature`,
`EnumerationSignature` and `StructSignature`, so resolving `(service, name)` to a type it can
construct requires an `UnderlyingType` on it, threaded through `ServiceSignature.AddException`. It
is not serialized, so the service-definitions JSON is unaffected, the same approach taken for
classes, enumerations and structures.

### Computed streams and events

`KRPC.AddFunctionStream(Expression function, bool start = true)` returns a `Stream` message,
symmetric with `AddStream`. It validates at creation time that the function's type is a
serializable kRPC type (`TypeUtils.IsAValidType` on the static type), with an error message pointing
at `ToList`/`ToSet` for lazy enumerables. A void function and a protocol buffer message type, which
`Type.Code` cannot describe, each get their own message, and `ReturnType` applies the same check.

`FunctionStream : Stream` compiles `Lambda<Func<object>>(Convert(expr, object))` once.
`UpdateInternal` evaluates it and turns any exception into a `Result.Error`. A `YieldException`
becomes an `InvalidOperationException` naming the pause, per "A yield is an error, and nothing
retries". Value-change detection through `ValueUtils.Equal` mirrors `ProcedureCallStream`, so
unchanged values are not resent. The `TypeSpec` built at creation time tells `Encoder.Encode` how to
serialize the boxed result, so no per-update type routing is needed.

`EventStream.UpdateInternal` has the same handling, so a predicate error becomes a stream error
result (surfaced by existing client stream machinery as a raised exception) instead of propagating
out of the per-frame update loop and starving every stream. `AddEvent` reports "The function must
evaluate to a boolean value" when given anything else.

Both reject a function containing a deferred call, since it would start the call again on every
update (see "Deferred calls").

**Function streams deduplicate like procedure call streams.** Two `FunctionStream`s are equal when
they share the compiled delegate, which the `Expression` caches, so a second `AddFunctionStream` of
the same function by the same client returns the existing stream's id, as `AddStream` does for an
equal call. The consequence is the one [#902](https://github.com/krpc/krpc/issues/902) describes:
one `RemoveStream` removes it for both. An event is not deduplicated, because `AddEvent` compiles a
fresh delegate on every call rather than reusing the cached one.

**Streams are not unified with procedure-call streams on the server, and are in the clients where
the language allows.** `AddStream` takes an encoded `ProcedureCall` and `AddFunctionStream` takes an
`Expression` object; kRPC procedures are not overloaded, so one procedure would have to take both
and reject one of them at runtime, replacing a signature that says what it accepts with an error
that says what it did not. The clients whose type systems overload do so: C# has an
`AddStream<T>(Expression)` overload and Java an `addStream(Expression)` overload, so a user of those
writes the same call for either. Python and C++ name them separately, matching how those clients
name everything else.

### Run-once functions

Events and streams re-evaluate on every update, which makes them the wrong home for a function with
side effects. `KRPC.RunFunction(Expression)` compiles the expression, invokes it exactly once inside
the calling tick, and returns its result.

The compiled delegate is cached on the `Expression` object, so a function is compiled the first time
it is run and reused on every later call. It is not compiled when the object is created: most
expression objects are interior nodes of a larger tree and are never run on their own, so compiling
every one of them would pay the cost hundreds of times over for a single function. `RunFunction`
and `FunctionStream` share the cached delegate; `AddEvent` compiles its own `Func<bool>` on every
call. Checking the tree for unbound `Break`/`Continue`/`Return` markers is cached the same way.

The return value is a `bytes` payload rather than a typed value, since the procedure's declared
return type cannot depend on the expression: the server encodes the value with the runtime-typed
`Encoder.Encode` and the client decodes it using `Expression.ReturnType` (dynamic clients) or a
user-supplied type parameter (static clients). A void-typed function returns an empty payload, which
is why `HasReturnType` exists: an empty collection encodes to an empty payload too, so a client that
decodes by payload length rather than by type would report `None` for an empty list.

A null value is carried by `ProcedureResult.is_null`, which `RunFunction` gets by declaring its
`bytes` return nullable. That is the channel every other nullable return uses, and the rule
[nested-nullable-values.md](../protocol/nested-nullable-values.md) sets for a value at the call
boundary. A null nested inside the result is an error naming the position, since C# and C++ decode
at a type the caller names: carrying one would mean writing
`run_function<std::vector<std::optional<Vessel>>>` for a `std::vector<Vessel>`.

`YieldException` is turned into a plain error, since a procedure that pauses and resumes on a later
tick cannot be honored by a call that must complete within this one.

### The StdLib service

Expressions can only call RPCs, so any arithmetic beyond the operator nodes would mean a round trip:
`math.sqrt` on a streamed value is not otherwise expressible. `StdLib` is a core service supplying
the missing primitives as ordinary RPCs:

* scalars: `Abs`, `Sqrt`, `Exp`, `Log`, `Log10`, `Floor`, `Ceiling`, `Sign`, `Clamp`, `Min`,
  `Max`, the trigonometric functions (`Sin`/`Cos`/`Tan`/`Asin`/`Acos`/`Atan`/`Atan2`) and
  `DegreesToRadians`/`RadiansToDegrees`. Exponentiation is the `Power` operator node.
* the constants `Pi` and `E`, as properties. A client that folds its own `math.pi` into a
  constant node never calls them, and a tree built through the expression API has no other
  source for them.
* one procedure per midpoint rounding rule, matching `Floor` and `Ceiling` beside them rather
  than taking a mode: `Round` rounds a halfway value to even, as Python and C# do, and
  `RoundHalfAwayFromZero` and `RoundHalfUp` are the C and Java rules. A client can then round
  the way its own language does. Each takes the number of decimal places, and `Log` takes the
  base of the logarithm, so a quantity is a parameter where a rule is a name.
* vectors and quaternions over the tuple types the SpaceCenter service already uses:
  `VectorAdd`/`Subtract`/`Scale`/`Dot`/`Cross`/`Magnitude`/`Normalize`/`Distance`/`Angle`/`Lerp`,
  and `QuaternionMultiply`/`Inverse`/`Angle`/`Slerp`/`FromAxisAngle`/`RotateVector`.

These exist to be called from inside functions, and are what the client compilers target when they
see `math.sqrt` (Python) or `System.Math.Sqrt` (C#). Each compiler holds the number of arguments its
target takes, so an overload with no equivalent, `Math.Round(x, MidpointRounding.ToZero)` for
instance, is reported when the function is compiled rather than when the server runs it. Only
`ToEven` and `AwayFromZero` map: `ToZero`, `ToNegativeInfinity` and `ToPositiveInfinity` are
directed rounding rather than midpoint rules, and no procedure performs them. A rounding mode
selects the procedure, so it has to be a constant. Because calls compile to direct typed invocations
of the underlying method, the JIT inlines them, so the indirection costs nothing at evaluation time.

### Client libraries

Building a tree needs no client work, since the factories are ordinary generated or dynamic service
stubs. Running a function as a stream or as a one-shot needs a small helper per client, in each case
decoding a value whose type the server reports rather than the stub declares.

* **Python** (dynamic): `Client.add_function_stream(function)` and the `Client.function_stream(...)`
  context manager call the RPC, walk `function.return_type` to rebuild the protobuf `Type`, and wrap
  the stream id with `Stream.from_stream_id(client, id, types.as_type(...))`, all existing
  machinery. `Client.run_function(function)` decodes the `RunFunction` payload the same way,
  returning `None` for a void function.
* **C#**: `Connection.AddStream<T>(Services.KRPC.Expression)` and `Connection.RunFunction<T>(...)`
  overloads, where the user supplies `T`; a non-generic `RunFunction` covers functions with no
  result. `T` is checked against the introspected type, so a void function or a mismatch throws
  rather than decoding bytes as the wrong type. A compiled `Func<T>` lambda skips the check, as its
  type comes from the lambda.
* **C++**: `run_function<T>` and `add_function_stream<T>` check `T` the same way, through a trait
  mapping C++ types onto type codes. Generated class, enumeration and structure types carry no
  names, so only their kind is compared.
* **Java**: typed helpers matching the client's stream-construction idiom, plus a run-once
  helper. Java decodes by the introspected type, per "Types and introspection", so there is no
  `T` to check.
* **Lua**: no helper. A Lua client builds trees through the ordinary factories, and `RunFunction`
  hands it back encoded bytes to decode itself. Events and function streams need streams, which
  the Lua client does not have. The tutorial says which clients support what.

Each helper introspects the type once per function and keeps it. Walking `ReturnType` is a round
trip per property of every type it is built from, and `run_function` would otherwise pay all of them
on every call, which is the opposite of what the procedure is for. The type a function returns
cannot change, so it is cached against the expression's object identifier.

**A Python function given to a helper is compiled on every call.** Caching the compiled function
against the Python function would freeze its captured values across calls, when they may have
changed. The compiler tracks the result type as it builds the tree, so the helper takes the type
from it instead of introspecting, and caches nothing for a function compiled for a single use. A
program that runs the same function repeatedly compiles it once with `compile_function` and passes
the result, as the docstrings say.

### Documentation ([#608](https://github.com/krpc/krpc/issues/608))

* A conceptual and tutorial page, `doc/src/tutorials/server-side-functions.rst`, covering what
  server side functions are and when to use them, custom events, computed streams, run-once
  functions and side effects, `Parameter`/`Lambda`/`Invoke` and how named parameters bind, `Select`
  versus `Where`, per-element RPC calls, object constants, type promotion and `Cast`, and errors and
  the yield limitation. Examples in all client languages, following the existing doc example
  conventions.
* Reference documentation for the `StdLib` service and for each client's compiler: what subset of
  the language is accepted, and the semantics that differ from running the code locally.
* XML doc summaries on every `Expression` and `Type` member, which feed the generated API reference
  in all languages.

## Error handling

Constructing an invalid program fails in one of three places, in increasing order of how far the
mistake travels before it is reported:

1. **In the client compiler**, before any RPC is sent, for constructs the compiler does not accept
   (`FunctionCompilationError` in Python, `FunctionCompilationException` in C#). These name the
   offending source construct.
2. **At tree construction**, which is where the majority of errors are caught and is the main
   ergonomic benefit of one RPC per node: the factory call that builds the bad node is the call that
   fails, so the error is localized to the node the client got wrong rather than to the tree as a
   whole. Operand types with no implicit conversion, an argument whose type does not match the
   procedure parameter, an assignment to something that is not a variable, an empty block, a
   `Return` whose type does not match the function's result type.
3. **At use**, when the tree is finally compiled. `AddEvent` requires a bool-typed expression, and
   `AddFunctionStream`/`RunFunction` require a serializable return type through
   `GetValidReturnType()`. Anything the node algebra did not check falls through to LINQ's own
   validation in `Compile()`, whose messages are not written for kRPC users.

**Unbound `Break`, `Continue` and `Return` are reported when the function is compiled.** The marker
methods are only rewritten when a loop or lambda node is built, so a `Break` with no enclosing loop,
or a `Return` with no enclosing lambda, is left as an ordinary call to a method that throws: it
compiles, and fails only when the function is evaluated, which for a stream means on every update.
The tree is therefore checked for residual marker calls at each point it is compiled, rather than
only in `Expression.Lambda`, since a block can be handed straight to `RunFunction` with no lambda
wrapper. A `Return` inside a lambda is also type-checked against the lambda's result type when the
lambda is built.

**A deferred call is reported when a stream or event is created.** `AddFunctionStream` and
`AddEvent` reject a function containing one, per "Deferred calls".

## Yielding procedures inside a function

Some procedures cannot finish within the tick they are called in. They signal this by throwing
`YieldException`, which carries a delegate that resumes the work. `ProcedureCallContinuation.Run`
catches it and rethrows a continuation wrapping `e.CallUntyped()`; the core parks that in
`rpcYieldedContinuations` and calls it again on each update until it completes. The client never
sees any of this: its call simply takes several ticks.

These are not obscure procedures. `Control.ActivateNextStage`, `SpaceCenter.WarpTo`,
`SpaceCenter.LaunchVessel`, `Part.Separate`, `AutoPilot.Wait` and vessel switching all yield, which
is to say the actions people most want a function to perform are exactly the ones that do this.

### A yield is an error, and nothing retries

Uniformly: `RunFunction` reports an RPC error, and a stream or event produces an error result.

**The yield cannot simply be honored.** The continuation resumes *the procedure*, not its caller.
Everything the function was doing around that call, loop counters, local variables, half-built
collections, which statement of a block it had reached, lives on the .NET stack of a compiled
delegate and is destroyed as the exception unwinds. There is no expression-level continuation to
park, so there is nothing for the core's existing retry machinery to resume.

**Streams do not retry.** Skipping the update and evaluating the function again from scratch on the
next one would be merely wasteful for a pure function and destructive for one with side effects: a
function that stages, then waits on the result of staging, re-stages on every update for as long as
the call keeps yielding.

**There is no side-effect-free exemption**, because the property is not decidable from the tree.
Void calls, assignments and collection mutation are the *visible* effects, but a procedure that
returns a value can change the game just as well: `ActivateNextStage`, `Undock` and `Part.Separate`
all return what they produced and are exactly the procedures that yield. A guard keyed on visible
effects would call those side-effect free and keep the destructive retry for precisely the cases it
exists to prevent.

**The refusal does not name the procedure that yielded.** `YieldException` does not carry it, and
the only way to attribute one is to wrap each embedded call, which would evaluate the arguments into
temporaries and cost the JIT the inlining that direct-call emission exists for. The message says
what happened and why instead.

Rejecting yielding procedures when the tree is built is not possible: yielding is a runtime
decision, since `WarpTo` yields only while the warp is incomplete, so nothing in a procedure's
signature says whether it will.

### The real question is atomicity

`RunFunction` exists to run a whole function inside one physics tick. Honoring a yield gives that
up: the function spans ticks, and everything read before the suspension may be stale after it. A raw
RPC that yields is a single operation, so it has nothing to be stale; a function reads many values
and combines them, so partial staleness would be the normal case rather than an edge one. The two
follow-ups below take opposite sides of that trade, and compose rather than compete.

### Deferred calls

Built. `Expression.DeferredCall` and `Expression.DeferredCallWithArguments` start a yielding
procedure and return within the same frame. If the call yields, its continuation is scheduled and
driven to completion by the core on subsequent updates, detached from the function, which carries
on immediately.

The emission wraps the ordinary direct call and its scene check in an `Action`, and passes that to
`Services.ExecuteDeferredCall` with the procedure's signature. A failure to start the call
propagates to the function, so an unavailable procedure is still reported to the client. A
`YieldException` hands a `DeferredCall` to the core, which runs the ones it holds ahead of each
update's calls, outside `MaxTimePerUpdate`, and logs a failure against the procedure's name.

**Only `RunFunction` may contain one.** A stream or event evaluates its function on every update,
so a deferred call in one would start the procedure again each time, and the pending calls would
accumulate without bound. `AddFunctionStream` and `AddEvent` reject such a function when they are
called, through `Expression.CheckNoDeferredCalls`.

**A deferred call is owned by the client that started it.** `ExecuteDeferredCall` records
`CallContext.Client`, and each resumption runs with that client set in `CallContext`, as an ordinary
resumed call does. The call is canceled when its client disconnects, and every call is canceled
once no server is running, alongside the object store being cleared. Canceling drops the
continuation and logs it; the procedures have no undo, so a canceled `WarpTo` leaves the game
warping. The precedent is `RPCServerUpdate`, which already drops a yielded continuation whose client
has disconnected.

Both compilers reach it. Python spells it `krpc.defer(call)`, a marker recognized by identity
like the `math` module functions, allowed wherever a statement goes. C# spells it
`Function.Defer(() => call)`, a marker taking a lambda, since a call returning nothing cannot be
an argument; an expression tree carries a single expression, so it is the whole body of a
`RunFunction` or `CompileFunction` lambda.

This lets a function trigger an action it does not need to wait for. It is genuinely limited, and
the limitation falls unevenly across the procedures that yield:

* `WarpTo` and `LaunchVessel` return nothing and read naturally as "start this", so deferring suits
  them.
* `AutoPilot.Wait` does nothing *but* wait, so deferring it is meaningless.
* `Undock`, `Part.Separate` and `ActivateNextStage` return the vessel or vessels they produce, which
  is usually the reason for calling them. A deferred call discards that, so the function cannot act
  on what it just created.

So the form is restricted to statement position, discarding any result, and documented as doing so
rather than returning a null the function might use. Two further consequences need stating: a
detached continuation has no request to report to, so a failure can only be logged and the client
never learns of it; and the function keeps running, so anything it does after the deferred call
observes game state from before the action completes.

For the calls it covers this removes the repeated-side-effect problem outright, because the function
no longer aborts part way through. A yielding procedure called through the ordinary form still
aborts the function.

### Resumable functions

Not built. A yield from an inner call is rethrown wrapped in a yield carrying a continuation for the
*function*, and the core's existing machinery resumes `RunFunction` on the next update exactly as it
resumes any other yielding RPC. The only hard part is what that continuation contains. Three
strategies:

* **State machine.** Compile the tree into a machine that lifts locals into a heap frame so
  evaluation can suspend and resume. A substantial compiler pass, essentially re-implementing what
  `async`/`await` does, over an algebra that keeps growing.
* **Thread per function.** Park the function's thread at the yield and release it on the next
  update. Far less code, but KSP and Unity APIs are main-thread affine and some assert on the
  calling thread, so the function's thread would have to hold the main thread's window while the
  main thread blocks. Workable in principle, fragile in practice, and one thread per in-flight
  function.
* **Journal and replay** (chosen). Do not capture the stack at all. Record each completed call's
  result in a journal held by the continuation, and on resumption re-run the function from the
  start, serving each call from the journal instead of invoking it, until execution passes the point
  it reached before. Everything in the algebra apart from calls is deterministic, so replay
  reproduces exactly the same control flow, locals and collections, and the call counter that keys
  the journal is deterministic for the same reason.

Journal and replay is much the cheapest, and it is the only one that makes side effects safe rather
than merely tolerated: a side-effecting call that already completed is replayed from the journal, so
it is not performed twice. Its costs are a journal per in-flight function, re-running pure
computation on each resumption (quadratic in the number of yields, which is fine when yields are
few) and cleanup of journals belonging to a disconnected client.

The implementation design is in [`resumable-functions.md`](resumable-functions.md), which covers the
journal, the call emission, the semantics a user sees and three correctness problems to settle
first. It is scoped to `RunFunction`, and is a follow-up PR rather than a phase of this one.

## Client-side compilation

Assembling a tree by hand is one RPC per node and unreadable at any real size, so each client that
can inspect its own code compiles native syntax into the tree. Both compilers share the same
strategy: subtrees that do not touch the server are evaluated client-side once and embedded as
constants, remote member access becomes embedded calls, and anything unsupported is a compile-time
error naming the construct rather than a confusing failure on the server.

Procedures are resolved from a cached `KRPC.GetServices` metadata index rather than by stub
introspection, since the dynamic Python stubs bake their metadata into closures and the index is the
only representation that works identically for both stub implementations. Template `ProcedureCall`s
carry no arguments; every argument the call supplies is an expression keyed by its parameter
position, with per-parameter numeric conversion (a Python float is a double, so single-precision
parameters get `constant_float` or casts). A position a keyword argument skips is simply absent, so
the server uses the parameter's default.

The Python compiler has one exception. A property read on an object captured from the client, such
as `vessel.met` with `vessel` captured, is built with the ordinary `Client.get_call`, with the
instance as a fixed argument, and embedded with `Call`. The instance is a constant either way.

### Python

`Client.compile_function` compiles a lambda or a function from its source; `add_event`,
`add_function_stream` and `run_function` accept functions directly.

* Expressions (`krpc/functioncompiler.py`): operators including floor division, true-division
  semantics, a remainder taking the sign of the divisor, the bitwise operators, and `is None`
  and `is not None` through `IsNull`; comprehensions (list, set and dict, nested) and generator
  expressions; `any`/`all`/`sum`/`min`/`max`/`len`/`sorted`/`abs`/`round`/`int`/`float`/`str`;
  subscripts and slices; f-strings; conditional expressions through `Expression.Conditional`;
  assignment expressions; parameterless lambdas and local function calls; and `math` module calls
  mapped onto `StdLib`.
* Statements (`krpc/functionstatements.py`): `if`/`elif`/`else`, `while` and `for` with
  `break`/`continue`, early `return`, local variables including augmented and annotated assignment,
  assignment to remote properties and to collection elements, `pass`, calls evaluated purely for
  their effects, and `krpc.defer(call)` for a procedure that pauses execution. A block holding
  only `pass` is an error, since the algebra has no empty block, except as the body of an
  `except`.
* Strings and collections dispatch on the statically tracked type: `len`, `[i]`, `[a:b]`, `in`,
  `.upper()` and `.split()` reach the string operations, with slicing compiling to
  `StringSubstring`. `min`/`max` with a `key` reach `MinBy`/`MaxBy`, `reversed` reaches `Reverse`,
  and the list, set and dictionary methods reach removal and clearing.
* Some reshaping operations have syntax: `sorted` reaches `OrderBy`, `reversed` reaches `Reverse`,
  a slice of a collection reaches `Skip` and `Take`, a nested comprehension reaches `SelectMany`,
  and a dict comprehension reaches `BuildDictionary`. `zip(a, b)` and `d.items()` reach `Zip`.
  The rest are factory-only. Their natural syntax does not name them in its error: `set(xs)`
  reports a client side function called with an argument computed on the server, and
  `list + list` fails on the server.
* Constructs with no node of their own lower onto existing ones, with no server change:

  | Construct | Lowering |
  |---|---|
  | `range`, `enumerate` | a value block building a list in a `While` or `ForEach` loop; `range` needs a constant step, whose sign picks the comparison |
  | `d.items()` | `Zip` of `DictionaryKeys` and `DictionaryValues`, with the dictionary in a temporary |
  | iterating `d`, `k in d` | over `DictionaryKeys(d)` |
  | tuple targets | `Get` by constant index, from a hidden variable in statements |
  | truth of a condition | `!= 0`, a length or count `!= 0`, or `IsNull` |
  | `a or b` on non-booleans | `Conditional` on the truth of a temporary holding `a` |

  `ContainsKey` and a `Range` node would replace two of these. A client side call written as a
  statement is an error, since it would run once, at compile time.
* Integer results keep their server type. `//` is an exact integer floor division built from
  `Divide` and `Modulo`, and integer `abs`, `min` and `max` are `Conditional` on temporaries.
  `int()` and `round()` of an integer are the integer itself, and of a float give an `int`. A
  negative constant index counts from the end through `Count` or `StringLength`, and a string
  slice clamps its bounds to the length, as Python does.
* A final `if`/`else` whose branches both return compiles to a `Conditional` of two blocks, so
  the function's value is its last expression.
* `except ValueError` catches the three argument exceptions, and a tuple in `except` gives one
  catch per exception, all recording the same clause.
* Left as documented differences: integer overflow wraps, a server computed negative index or
  exponent, negative slice bounds, and `str()` of a float using the server's formatting.
* An enumeration value captured from the client compiles to a `Cast` of an integer constant rather
  than `ConstantEnum`. The value comes from the client's own enumeration, so it is a member.
* `raise` and `try`/`except` map onto the exception nodes. A `try` with one `except` is one
  `TryCatch`. With several, the catches nest in the order written, and each catch only records
  which clause matched in a variable; the clauses then run after the catches, dispatched on that
  variable. So an exception raised by one clause is not caught by a later one, as in Python.

### C#

`Connection.CompileFunction` translates a LINQ expression tree, which the compiler hands the client
for free from an `Expression<Func<TResult>>` lambda, into the same server tree. `AddEvent` accepts a
boolean lambda, `AddStream` compiles compound lambdas, and `RunFunction` accepts
`Expression<Action>` lambdas so side-effecting functions can be written in the same style.

`Function.Defer` is the one statement the compiler reaches, and `CompileFunction` has an
`Expression<Action>` overload so a lambda with no result compiles to a reusable object.

Beyond the operator set: a comparison with `null` maps onto `IsNull`, and a conversion between a
value type and its nullable form is left to the server; `System.Math` methods map onto `StdLib`;
string `+` and `ToString` become `StringConcat` and `ConvertToString`; the bitwise complement and
the LINQ operators `Skip`, `Take`, `SelectMany`, `ToDictionary`, `Distinct`, `Reverse`, `Zip`,
`Union`, `Intersect`, `Except`, `First`, `Last` and `ElementAt` are supported; captured collections
are folded into constants; and `.Length`, `.Substring`, `.ToUpper` and `.Contains` dispatch onto the
string operations by static type.

Three things are deliberately out of reach. `GroupBy` is not mapped, since the node's result type
differs from LINQ's. `MinBy`/`MaxBy` have no syntax at net472, where `Enumerable.MinBy` does not
exist. Exceptions are unreachable in either direction, since an expression-tree lambda may neither
contain a throw expression nor have a statement body, which is consistent with that compiler being
limited to single-expression lambdas.

### Semantics that differ from running locally

Documented for both compilers, because they are the surprises: captured values are frozen at compile
time, so only remote calls re-evaluate per tick; and a procedure that pauses execution cannot be
used inside a function.

**Short-circuiting is not one of them.** `And` and `Or` compile to LINQ's `And`/`Or`, which evaluate
both operands, and mapping `and`/`or` and `&&`/`||` onto them would silently drop the guard in
`x.Count > 0 and x[0] == 1`. `ConditionalAnd` and `ConditionalOr` compile to `AndAlso`/`OrElse`, so
both compilers map the conditional operators onto them and the bitwise ones onto `And`/`Or`. Python
chained comparisons need one more thing: `a < b < c` expands to two comparisons over one `b`, so a
non-constant `b` is assigned to a temporary in an enclosing block and read from it twice, which is
where python evaluates it once.

**Nor is the sign of a remainder.** `Modulo` is the CLR remainder, whose sign follows the dividend,
and python's follows the divisor. The Python compiler emits `(a % b + b) % b`, assigning a
non-constant `b` to a temporary as it does for a chained comparison, so `-30 % 360` is 330 on the
server as it is locally. The C# compiler maps `%` straight onto `Modulo`, which is C#'s own
semantics.

## Object identity and lifetime

Every object a factory returns becomes an entry in the object store, and the store collapses
duplicates: `AddInstance` looks the instance up in a `Dictionary<object, ulong>` before allocating
an id, using the default comparer, so any class overriding `Equals`/`GetHashCode` is deduplicated
automatically. That is what `Equatable<T>` (`core/src/Utils/Equatable.cs`) exists for.

Nothing in the store is released except by the sweep described below: `RemoveInstance` has no
callers in `core/`, `server/` or `service/`, and `ObjectStore.Clear()` runs only once the last
server stops. A function that asks for `Type.Double()` five hundred times must therefore not
leave five hundred entries describing a single type.

Types and value constants are shared. Interior nodes are not, and the last two subsections say why
that is enough.

### Types

`Type` derives from `Equatable<Type>`, comparing `InternalType`. It is an immutable description of a
type with no per-client state, so value equality is the correct semantics and sharing a single
instance between clients is safe. No protocol or client change is involved.

Composite types collapse for free: the CLR interns constructed generic types, so `MakeGenericType`
returns the same `System.Type` for the same arguments, and `ListType(Double())` reduces to one id
provided the nested `Double()` did. `Equatable<T>` brings `operator ==`/`!=` with it, so `== null`
comparisons on a `KRPC.Type` change path; they stay correct, since those operators are null-safe,
and the code that builds trees compares with `ReferenceEquals` throughout in any case.

The client half matters as much as the server half, because each factory call is also a round trip.
The Python compiler shares one cache of the objects naming each type across every function compiled
for a connection, so a type is named to the server once rather than once per mention. The casts
the compiler inserts for `//`, `/`, `abs`, `round` and `int()` are the exception: they call
`Type.Int()` and `Type.Double()` directly, which costs a round trip per use but no new object store
entry, since types compare by value.

### Constants

Constants get the same treatment for the same reason: `false`, `0` and `1` recur throughout any
compiled function, and there is no more sense in minting an id per occurrence than there is for
types.

The mechanism differs. `Expression` wraps an arbitrary LINQ tree, and those have no structural
equality, so a blanket `Equals` override is not available: value equality is well defined for
constant nodes and for nothing else. The factories intern instead, through a
`Dictionary<Tuple<System.Type, object>, Expression>` keyed on the constant's type and value,
consulted by every value constant factory and `ConstantEnum`.
Reference equality then does the deduplication in the object store with no equality override at all,
and the allocation is avoided as well. Sharing is safe because LINQ trees are immutable and sharing
a subexpression between trees is supported. The key includes the type so that `ConstantInt(1)`,
`ConstantDouble(1.0)` and `ConstantFloat(1.0f)` stay distinct; `Tuple<,>` rather than a value tuple,
matching the codebase.

**`ConstantObject` is deliberately excluded.** Interning it would key a permanent, static, strong
reference on an arbitrary service object, keeping a destroyed vessel or part alive for the life of
the server. That is the exact leak shape [#771](https://github.com/krpc/krpc/issues/771) is about,
and it would defeat the object store sweep for precisely those objects. The value constants pin
nothing but a boxed primitive or a string, so they are safe; object constants are not. The saving
would be small in any case.

### Against the object store sweep

The object store reclaims what the game has destroyed, designed in
[object-lifetime.md](../object-lifetime.md) and merged as
[PR #1051](https://github.com/krpc/krpc/pull/1051). `ObjectStore.Sweep()` walks the registered
instances and drops those implementing `KRPC.Utils.IGameObjectState` that report
`GameObjectState.Destroyed`, driven from the game state load boundary. It is **liveness eviction,
not reference counting or reachability**: instances that do not implement the interface are kept.

Three consequences here:

* **Types and constants are unaffected, for free.** They stand for nothing in the game, have no
  state to report, and do not implement `IGameObjectState`, so the sweep keeps them. The "never
  released" property this section relies on is not "nothing is ever removed" but "nothing removes
  *these*", which is the property actually wanted.
* **Object constants are not reclaimed by it.** The sweep drops the store's entry, but a
  `ConstantObject` node holds the instance through `LinqExpression.Constant`, and the tree is a
  second and stronger root: the object stays alive in the CLR for as long as the function does.
  Eviction from the store is not collection.
* **What the client sees is nonetheless right.** A proxy for a game object the game has destroyed
  raises `ObjectDestroyedException` on access, so a function holding a constant for a
  since-destroyed part reports that per evaluation rather than reading stale data or throwing a bare
  `NullReferenceException`. The behavior falls out of #1051 instead of needing its own handling.

**Reclaiming trees that hold a dead object is rejected.** Making `Expression` implement
`IGameObjectState`, destroyed once any service object it closes over is, would bound the growth
described below, and it is wrong for three reasons:

* **The client can handle the exception, and will want to.** `ObjectDestroyedException` is a
  `[KRPCException]`, so `TryCatch(body, "KRPC", "ObjectDestroyedException", ...)` catches it inside
  the function like any other. A function written to survive its part being destroyed is working as
  intended, and pulling the tree out from under it destroys a program *because* it handled the case
  it was written to handle.
* **A dead constant does not mean a dead tree.** The object may be referenced only from a branch
  that never runs, or from the handler that exists to cope with its absence. Liveness of one leaf
  says nothing about whether the tree can still evaluate.
* **It does not fit the interface.** `IGameObjectState` is specified to report `Destroyed` only when
  the underlying object is definitively gone, so that objects a client legitimately still holds are
  not discarded. An expression has no underlying game object; it is a client-authored program whose
  continued usefulness is a matter of the client's intent, which the server cannot infer. The sweep
  answers "did the game destroy this?", not "does the client still want this?".

If interior-node growth is ever worth addressing, it therefore needs a client-driven answer, an
explicit release or a lifetime tied to the stream or event that consumes the tree, rather than the
server guessing from liveness. Not designed here.

### No refcounting for these

Deliberate, and it is the reason deduplication is enough on its own. Distinct types are bounded by
the service surface, distinct constants by the literals a program actually writes. Reaching a
troubling number would take thousands of distinct literals, which is not a realistic shape for
hand-written or compiled code. So nothing sweeps them. The interned constants are dropped once the
last server stops, alongside the object store whose identifiers name them; types need no such step,
since the object store holds the only references to them.

**This is not [#902](https://github.com/krpc/krpc/issues/902).** That issue is reference-counted
*streams*: two equal `AddStream` requests deduplicate to one id, and a single `RemoveStream` then
destroys it for both consumers. It concerns stream lifetime rather than the object store, and it is
a correctness bug rather than a growth concern. Deduplicating types and constants does not affect
it, but function streams are subject to it, per "Computed streams and events".

**What deduplication does not bound.** Interior nodes, every operator, call, block and lambda, are
not deduplicated, and they are the population that actually grows: one compile of a moderate
function is hundreds of permanent entries, and a program that recompiles inside a loop, or
repeatedly creates function streams, grows without limit. The sweep does not reach them either, and
for the reasons above should not be made to. This is close to a pre-existing property of the object
store rather than something the function work introduces, since every `Vessel` and `Part` ever
encoded is pinned the same way, which is what #771 and #1051 are about, and it is left alone here.

## Batched tree construction

Not built. Building a tree costs one blocking round trip per node. The Python compiler calls some
seventy distinct factories, and every one is an ordinary generated stub call going through
`Client._invoke`, which hard-codes a single call per `Request`. A compiled function of any real size
is therefore hundreds of sequential round trips.

**What this actually costs.** Not a frame stall. `RPCServerUpdate` (`core/src/Core.cs`) polls *and*
executes repeatedly within a single `FixedUpdate` until `MaxTimePerUpdate` is exceeded (5 ms by
default, self-tuning 1 to 25 ms), and with `BlockingRecv` it waits up to `RecvTimeout` for the next
request rather than returning early, so a client doing synchronous ping-pong is served many times
per tick. The per-node server work is a single LINQ node allocation. The costs are, in order:

* **Client wall clock, dominated by round-trip time.** Tolerable at loopback latency and bad at 5 to
  20 ms, which is exactly the run-the-script-on-another-machine case: 500 nodes at 10 ms is five
  seconds to compile one lambda.
* **Monopolizing the per-tick RPC budget**, starving other clients' streams and dragging the
  adaptive rate controller down while a tree is being built.
* **`OneRPCPerUpdate` degenerates to one node per frame**, so the same 500-node tree takes about ten
  seconds regardless of latency.

It is worst for `RunFunction`, whose whole premise is replacing many round trips with one. If
building the tree costs three hundred round trips to save twenty, the feature is a net loss unless
the function is reused.

**This does not fall out of #903.** Rung 1 of that design is a user-facing batch of *independent*
calls whose results are only readable after the block exits. Tree construction is the opposite
shape: each call's returned handle is the next call's argument, which an independent-call batch
cannot express.

**What makes batching possible anyway** is that the tree is fully determined client-side. The
compiler builds its procedure index from a single `get_services()` call and tracks `ptype` locally
through the whole walk; it never needs a server response to decide what to build next. The round
trips exist only to materialize object handles.

**Design: deferred handles with a level-ordered flush.** Have the factory wrappers return a deferred
handle holding `(procedure, arguments)`, where an argument may itself be a deferred handle. The
compiler runs to completion locally, building the tree as a client-side DAG, and the handles are
then flushed in dependency order, one multi-call `Request` per level, since all nodes at a given
depth are independent. That turns O(nodes) round trips into O(depth): typically 10 to 30 requests
for a tree of several hundred nodes. It is client-side work only, with no protocol change and no
change to any other client.

The server side already supports it. `RequestContinuation.Run` executes a multi-call request
sequentially within one tick, and `ProcedureResult` carries a per-call `error`, so a failure is
attributable to a specific node.

Two things to get right:

* **Error attribution.** Errors surface at the construction site, with the source location of the
  offending syntax. Each deferred handle has to carry its `ast` node so the flush can re-raise
  through the existing `self._error(node, ...)` path; otherwise the compiler's diagnostics regress
  to "something in this function was wrong".
* **Not leaking deferred handles.** `compile_function`, `run_function`, `add_event` and
  `add_function_stream` must flush and hand the real root handle onward.

**A cheaper win to take first.** `remote_type` (`client/python/krpc/expressionutils.py`) memoizes on
the serialized ptype, in the `client._expression_remote_types` cache every function on a connection
shares. Deduplicating repeated constants is the same shape and is still open. It is worth doing
regardless, and it changes the measurement that decides whether the deferred-handle work is
justified. That measurement should be taken before building it, by counting factory calls for
realistic inputs such as the launch-into-orbit tutorial function and the examples under
`doc/src/scripts/client/python/`.

**Alternatives considered.** Intra-request result references, a `oneof` on `Argument` letting a call
name the result of an earlier call in the same request, would send the whole tree in exactly one
request and would help any chained calls, not just functions. It is rejected as the first step
because it is a protocol bump touching every client's encoder, and it needs new semantics for
mid-batch failure and for the yield-and-retry path in `RequestContinuation`. Level-ordered batching
gets most of the win for none of that; this is the follow-up if measurement shows depth dominating.
A single `Expression.BuildTree(bytes)` RPC taking a serialized tree is rejected outright: it
duplicates every factory in a second encoding and discards the per-node error reporting that the
tree approach was chosen for in the first place.

The same design applies to the C# compiler. Java and C++ build trees by hand and would need an
explicit batch helper instead, which is only worth adding if hand-built trees there get large.

## Interaction with planned protocol work ([#906](https://github.com/krpc/krpc/issues/906))

* **#877 stream invalidation** builds on per-stream error results, which `FunctionStream` and
  `EventStream` emit in the same shape as `ProcedureCallStream`, so the removal convention can layer
  on unchanged.
* **#903 reverse streams and batched calls** is independent of the tree-construction round trips,
  per "Batched tree construction". The overlap is elsewhere: the expression registry, storing
  server-side state and evaluating it per tick, is the same machinery reverse streams cite as prior
  art.
* **#902 stream refcounting** applies to function streams as it does to procedure call streams,
  since both deduplicate; see "Computed streams and events". It is unrelated to deduplicating types
  and constants, despite the surface similarity; see "No refcounting for these".
* **#904 deprecation**: individual expression operators can be evolved or deprecated through the
  standard mechanism, since they are ordinary service members.

## Testing

* `core/test/Service/KRPC/ExpressionTest.cs`: promotion cases for every binary operator; `Call` and
  `CallWithArguments` against the scanned core `TestService`, with `ConstantObject`, class-typed
  `Parameter`, per-element `Any`/`Select` over real RPC calls, error propagation and `ReturnType` on
  every node kind; the statement nodes, covering block scoping, loops with `Break`/`Continue`, early
  `Return` and imperative collection construction; and the tuple, collection, string and exception
  operations.
* `TypeTest` for the factories and introspection, and `StdLibTest` for the scalar, vector and
  quaternion operations.
* Stream behavior (value change detection, error capture, a yield reported as an error) alongside
  the existing core stream tests.
* `TypeTest` and `ExpressionTest` also cover object identity: two equal factory calls yield the same
  object id, and types and constants differing only in type (`Int` versus `Long`, `ConstantInt(1)`
  versus `ConstantDouble(1.0)`) do not collide. `ObjectStoreTest` covers the equality path itself.
* Python integration tests against TestServer, part of `//:test`: computed streams end-to-end
  (value, collection and object results, and server-reported type decode), per-element call events,
  object constants, mixed-type arithmetic events, error surfacing, and `run_function` covering
  results, side effects and the void case.
* C#, Java and C++ client tests for the typed stream and run-once helpers, following each client's
  existing event and stream test structure.
* Compiler tests per client covering the accepted language subset and the diagnostics raised for
  unsupported constructs.
* `service/SpaceCenter/test/test_server_side_functions.py`, in the in-game suite, against a vessel
  on the launchpad: reading the game state, a single tick shared by every call, comprehensions and
  loops over the vessel's parts, side effects, `StdLib` on the game's vectors, a function stream, an
  event, and a deferred `WarpTo` beside the error a yielding procedure produces without it.

Three behaviors are decided rather than merely implemented, and each is covered explicitly: the
collection operations reject a string with the intended message rather than an internal exception;
case conversion and comparison are invariant, tested by evaluating under a Turkish culture rather
than by inspecting the emitted call; and a `TryCatch` naming a kRPC exception catches the mapped CLR
exception an RPC actually throws, while a `TryCatchAll` around a yielding procedure still reports
the pause rather than handling it.

**Each client names its test files explicitly**, so a new one is invisible until it is listed:
`client_tests` in `client/python/BUILD.bazel`, the `srcs` of `test-KRPC.Client` in
`client/csharp/BUILD.bazel`, `test_srcs` in `client/cpp/BUILD.bazel`, and the `SuiteClasses` of
`client/java/test/krpc/client/TestSuite.java`. Only the C# `src` tree and the core test assembly are
globbed.

### Golden expression-tree tests

A deterministic tree printer (`core/src/Service/KRPC/ExpressionTreePrinter.cs`: indented
`NodeType<Type> detail` lines, sequential ids for parameters, variables and labels, invariant
round-trip numeric formatting, and object constants printed as type name only so no run-to-run
identity leaks) is exposed through a test-only `DumpExpressionTree(Expression)` RPC on TestServer's
`TestService` and mirrored on the in-game `TestingTools` service. Three golden suites compare dumps
against expected strings, verifying the exact trees the API generates without depending on the
brittle compiled IL:

* `core/test/Service/KRPC/ExpressionTreePrinterTest.cs`, the factory API: direct-call emission
  (scene check, and null-return check only for non-nullable reference returns), numeric promotion
  `Convert` insertion, `While`/`ForEach` desugaring, marker-to-goto rewriting, and label binding of
  early returns.
* `client/python/krpc/test/test_expressiontree.py`, Python compiler output end-to-end in both stub
  modes: getter null-check blocks, true-division converts, `math.sqrt` to `StdLib.Sqrt`, statement
  functions as `Invoke(Lambda)`, loops with declared variables, void setter functions, and
  comprehensions as `Select` plus `ToList` with per-element narrowing converts.
* `client/csharp/test/ExpressionTreeTest.cs`, C# LINQ compiler output: `Math.Sqrt` mapping, folded
  captured collections, string `+` to `String.Concat`, and ternary conditionals.

Sets are deliberately excluded from the goldens, since client-side set iteration order is
nondeterministic. Generated C++ service headers do not include cross-service headers, so the C++
test sources include `krpc/services/krpc.hpp` before `services/test_service.hpp` for the new RPC's
`KRPC::Expression` parameter.

## Out of scope

* Java and C++ native-syntax compilers. Neither language exposes its own syntax tree to the client,
  so there is no equivalent of the Python source or C# LINQ route; both keep the run-once and stream
  helpers over hand-built trees.
* Batched tree construction, designed above; client-side only, and gated on measuring real tree
  sizes first.
* Bounding the time a loop can run for, so that a runaway function cannot hang the game.
* Resumable functions, designed under "Yielding procedures inside a function".
* Calling arbitrary CLR members from a function, sketched in
  [server-side-arbitrary-expressions.md](server-side-arbitrary-expressions.md).
