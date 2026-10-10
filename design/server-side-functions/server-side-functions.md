# Server-side functions

**Status:** done, in review. The work ships as a stack of 7 PRs grouping its 19 phases (see
"Phases"). None of the stack is opened yet. It closes umbrella issue
[#679](https://github.com/krpc/krpc/issues/679).

Builds on [`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md), which lands first. That doc owns the behavior every stream and event shares:
one stream per add, removal, error results and the update loop. This doc covers what function streams
and events add.

Follow-ups, not built, each designed in its own doc:
[`yielding-procedures.md`](yielding-procedures.md) (deferred calls and resumable functions),
[`shared-nodes.md`](shared-nodes.md) (compiling shared nodes once),
[`function-release.md`](function-release.md) (releasing functions) and
[`batched-tree-construction.md`](batched-tree-construction.md).

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

| Term | Meaning | Examples |
|---|---|---|
| **expression** | A node of the algebra. Control flow nodes are expressions too. | `Add`, `Not`, `ConstantInt`, `While`, `Block`, `Break` |
| **function** | The whole tree a client assembles, i.e. its root expression. The unit that is run, streamed or compiled. | |

Naming rules:

* The node class keeps the name `Expression`, as in `System.Linq.Expressions`, which it compiles to.
  `Function` would make every node read as a function (`Function.ConstantInt(1)`).
* Server entry points are named for the function: `KRPC.RunFunction`, `KRPC.AddFunctionStream`,
  `KRPC.CompileFunction`, `krpc/function_stream.hpp`.
* Client methods drop the suffix: `compile`, `run`, and `add_stream`, which takes a remote
  procedure or a function. C# and Java spell them `Compile`, `Run`, `AddStream` and `run`,
  `addStream`.
* The split is a naming rule, not a type. `RunFunction`, `AddFunctionStream` and `AddEvent` take an
  `Expression`, in a parameter named `function`.
* The lambda node is `Expression.Lambda(parameters, body)`, after its LINQ node. It is `Invoke`d or
  passed to `Select`/`Where`. A function needs no lambda around it, except one that uses `Return`,
  which is a parameterless lambda, invoked (see "Statements, control flow and side effects").
* Prose, error messages and XML summaries follow the same split. The API reference page keeps the
  title `Expressions` and links the tutorial.
* Factories are static members of the class in every client, not reached through a builder object
  (`conn.Expression.Not(...)`).

Breaking changes:

| Change | Effect |
|---|---|
| `KRPC.AddEvent` parameter renamed `expression` to `function` | Breaks calls that pass it by name |
| `Expression.Function` renamed `Lambda`, with no deprecated alias | A v0.6 client calling `Function` fails |
| New procedures declared among the released ones, and `Expression` split into one partial class file per feature | `KRPC` procedure ids renumber; a client calling by id (cnano) needs regenerated stubs |
| `Power` takes the common type of its operands | The result takes the common type, not the first operand's type |
| `Get` on a tuple takes a constant index | A computed tuple index is an error |
| `CreateTuple` takes at most seven elements | An eight-element tuple is an error |
| Calls to `KRPC` service procedures are rejected in a function | A function calling one fails when built |
| Any service's null, missing key, index, division by zero, unsupported, timeout and overflow errors reach Python, C# and Java as built-in exceptions | Breaks code that catches `RPCError` or `RPCException` for them, such as a timeout from `AutoPilot.Wait` |
| C# `AddStream` of a single call with a remote procedure call in an argument | The argument's call is made on every update, not once when the stream is created |

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
* `NullableType(valueType)` for a nullable value of any type, `bool`, strings, classes and
  collections included. Naming a nullable type nullable again gives the same type.

Nullability is part of the type, at every position. A `Type` wraps the server's `TypeSpec`, the
tree of CLR type and nullable flag the encoder already works from, so equality includes it:
`String()` and `NullableType(String())` are different types. A set element and a dictionary key
are never nullable, as in the protocol, and `SetType` and `DictionaryType` reject a nullable one.

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
  service), `Types` (generic arguments, with their own nullability, empty otherwise), and
  `Nullable`. `Nullable` says whether a value of the type may be null; a `String` that is not
  nullable refuses one, though a C# string can hold it. A function's value is encoded with a
  presence flag at each nullable position, so a client builds its type message with `nullable` set
  there. The C++ return type check requires `std::optional` at exactly the nested nullable
  positions. The value itself may be a `std::optional` or not, and reading a null into a plain type
  throws `std::runtime_error`. The C# check is exact at value-type positions and follows the server
  at reference-type ones, since a C# reference type does not say at run time whether it is nullable.
* `Expression.ReturnType` gives the `Type` an expression evaluates to, and `HasReturnType` reports
  whether it has one at all. `ReturnType` throws for types that cannot be returned to a client, such
  as the lazy `IEnumerable<T>` produced by `Select`/`Where`, and the message says to wrap it in
  `ToList`/`ToSet`.

A dynamic client walks `ReturnType` recursively, reconstructs the equivalent protobuf `Type` message
locally, and feeds its existing decode machinery (`Types.as_type` in Python). Statically typed
clients do not need this: the user supplies the expected type as a generic parameter.

**As built, Java walks `ReturnType` too.** Its `Stream<T>` is constructed from a protobuf `Type`
rather than from a `Class<T>`, and its decoder takes the same message, so there is nothing for a
type argument alone to drive. `Connection.run` and `Connection.addStream` therefore
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
are numeric and differ. `Power` of integers is exact, by repeated squaring, and wraps on overflow
as the other integer operators do; a negative integer exponent goes through `Math.Pow` and
truncates. `Power` of floating point operands uses `Math.Pow`. `Conditional` promotes its two
branches the same way. Branches with no common type are an `InvalidOperationException`, as for the
values of a collection. Explicit `Cast` remains available.

`Equal`, `NotEqual` and `Contains` compare objects, tuples, bytes and collections by value, since a
getter such as `SpaceCenter.ActiveVessel` returns a new object on each call. A list compares in
order, a set as a set and a dictionary entry by entry, as Python does. Numeric elements compare
after widening, so a list of ints can equal a list of doubles. A structure compares field by field.
Operands of unrelated types are a `KRPC.ArgumentException` when the node is built. Two collections
or tuples are related when they are of the same kind and their elements are related.

Every collection compares its values the same way. A set the server builds hashes with a comparer
that pairs this equality with an agreeing hash, so two equal lists or bytes values are one member.
`Distinct`, `Union`, `Intersect` and `Except` take the same comparer. `Append`, `Remove` and
`Contains` compare by value on a set a procedure returns too, since that set hashes by default
equality.

Equality and `Conditional` keep a null. When either operand is a nullable value type, both widen
to the nullable common type.

`Negate` follows the unary form of the same rules: a `uint` is negated as a `long`, and a `ulong`
is an error, as in C#.

`And`, `Or` and `ExclusiveOr` promote integer operands the same way. A shift takes its count as an
`int`, converting any other integer count, and uses its low bits as C# does. `Divide` and `Modulo`
of the smallest `int` or `long` by -1 wrap, giving that value and 0, where the CLR throws.

A value used in a position of a fixed type follows one rule: a numeric conversion that widens is
implicit, and one that narrows needs `Cast`. The positions are:

* a procedure argument (`CallWithArguments`);
* a collection element, a dictionary key or value, the value given to `Append`, `Set`, `Remove`
  and `Contains`, and the key given to `Get`, `ContainsKey` and `Remove` on a dictionary;
* a structure field (`CreateStruct`);
* a variable assignment (`Assign`), and an argument to `Invoke`;
* the seed of `AggregateWithSeed`, which widens to the type the function accumulates.

A value of an unrelated type at any of these positions is an `InvalidOperationException`. An index
or count, as given to `Get` on a list, `ElementAt`, `Set`, `RemoveAt`, `Skip` and `Take`, takes
exactly an `int`, and any other type needs `Cast`.

A nullable value type, which a procedure returning one produces as `Nullable<T>`, takes part in
promotion as its underlying `T`, which throws when the value is null. A position of a plain type
converts it to `T` the same way. A nullable position takes a plain or nullable value of the same or
a narrower numeric type, so a null passes through. Nullable enumerations, `bool?` and nullable
structures follow the same rules. A condition, and the operands of `Not`, `ConditionalAnd` and
`ConditionalOr`, take a `bool?` as its value, so a null there throws.

### Constants

| Factory | Notes |
|---|---|
| `ConstantDouble`, `ConstantFloat`, `ConstantInt`, `ConstantLong`, `ConstantUInt`, `ConstantULong`, `ConstantBool`, `ConstantString`, `ConstantBytes` | Value constants |
| `ConstantNull(type)` | A null of `type`, made nullable |
| `ConstantObject(ulong id)` | An object reference, by its object id |
| `ConstantEnum(service, name, value)` | A member of a service's enumeration |

* **Integer literals.** Both compilers use the wide integer constants, so a constant outside `int`
  keeps its value. The Python compiler gives a literal the exact type of the parameter it is passed
  to, otherwise the narrowest of `int`, `long` and `ulong` that holds it.
* **Object ids** start at 1, and `ConstantObject(0)` is an error. The server looks the id up with
  `ObjectStore.GetInstance(id)`, and the node's static type is the instance's most-derived
  `KRPCClass`. This needs no protocol change, which is what blocked
  [#503](https://github.com/krpc/krpc/issues/503).
* **Clients expose the id** as `RemoteObject.id` in C#, `_object_id` in Python, `Object::_id` in C++
  and `RemoteObject.id` in Java, which the Java phase makes public.
* **A KRPC service object is rejected**, such as an `Expression`. A function holding one could run
  or stream it, bypassing the checks in `RunFunction`, `AddEvent` and `AddFunctionStream`.
* **`ConstantEnum` checks the value** against the enumeration's members when the node is built.
  Casting an int to the enumeration type also works, but checks nothing.

### Null values

`ConstantNull(type)` produces a null, and `IsNull(value)` tests for one. `IsNull` is a boolean,
`ReferenceEqual` against null for a reference type and `Equal` against a null `Nullable<T>` for a
value type. `IsNull` of a value that is not nullable is an error when the node is built, a string
or class included. The compilers map `x is None` and `x == null` onto it.

Every node carries a spec, the same tree of type and nullable flag a `Type` wraps, beside its CLR
type. The CLR type alone cannot say whether a string or class is nullable. A node that computes a
fresh value is not nullable. A node that passes a value on takes the spec of where it came from:

| Node | Spec |
| --- | --- |
| A call | The procedure's return spec, its `[KRPCNullable]` positions included |
| `GetField` | The structure field's spec |
| `Cast`, `Parameter`, `Variable` | The `Type` given |
| `ConstantNull` | The `Type` given, nullable |
| `Conditional`, `CreateList`, `CreateDictionary` values, `Concat` and the like | Nullable wherever any input is |
| `Get`, `First`, `Last`, `ElementAt`, `MinBy`, `MaxBy`, `ToList`, `DictionaryValues` | The element or value position of the collection |
| `Select`, `SelectMany`, `Zip`, `Invoke` | The function's result, joined over its body and every `Return` |
| `Aggregate` | Nullable wherever the element, seed or function result is |

A nullable value going into a position that is not nullable is checked when it is evaluated, and
throws `KRPC.NullReferenceException` if it is null, with a message naming the position. A nullable
value type is unwrapped through the check. A reference type passes through a null check, and a
collection whose nested reference positions differ is walked for nulls at those positions only.
A nullable value type nested in a collection or tuple goes only to a nullable position, and the
error says to convert the values with `Select`. A plain value type widens to a nullable position.
The positions are the ones listed under numeric promotion, plus operands, conditions, the
collection an operation is given, string operands, the value given to `ConvertToString`, the
`Throw` message, a set element and a dictionary key.

The check is emitted only where the spec allows a null, so a value that cannot be null costs
nothing. A call checks more: a computed reference argument for a parameter that is not nullable, and
a reference a procedure returns where its return is not nullable, are checked on every evaluation,
as for an ordinary RPC. A lookup is the exception: `Contains`, `ContainsKey` and `Remove` give false
for a null sought in a collection that cannot hold one, as `Equal` gives false for a null. A lambda
given to a collection operation is adapted the same way when its parameter is less nullable than the
elements. A predicate's result is never nullable. A key function's result can be, and `OrderBy`,
`MinBy` and `MaxBy` order a null key first.

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

Any service's procedures can be called except the KRPC service's. That service builds, runs and
streams functions, so a function calling it could create a function at run time, past the checks
made on the function it runs in, and could add a stream or an event on every update. For the same
reason a plain `AddStream` of `RunFunction`, `AddFunctionStream` or `AddEvent` is rejected;
`AddFunctionStream` is how a function is streamed. A call to any procedure that returns an event or
a stream is rejected when the call node is built. Creating one adds a stream to the client, and a
function can be evaluated while the server iterates over the client's streams.

`CallWithArguments` subsumes `Call`, and the two share one implementation, so the second factory
costs a signature and nothing else. `Call` exists because it is the common case and the one a client
can build without knowing anything about parameter positions: a client already holds an encoded
`ProcedureCall` for any RPC it can make, and passing it is the whole call. Without it every embedded
call, including those with no computed arguments at all, would have to pass an empty collection.

Arguments are keyed by position rather than given as a list with null holes. A null is signaled
out of band, and only at a position marked nullable
([PR #1017](https://github.com/krpc/krpc/pull/1017)), so a list of argument expressions cannot hold
one. Positions need no placeholder, and there are no trailing nulls to trim.

Both factories compile to a **direct, statically typed `LinqExpression.Call` of the procedure's
underlying `MethodInfo`**, exposed as `IProcedureHandler.Method` by all three handler types
(property accessors are wrapped through their getter/setter `MethodInfo`, so every RPC is
inlinable). Arguments are typed sub-expressions or typed constants, built at the method's own
parameter types rather than the procedure signature's: a nullable value-type parameter is `T` in the
signature and `Nullable<T>` on the method, and only the latter types the call. There is no
`object[]` allocation and no boxing, and the .NET JIT can inline the target: `StdLib.Sqrt` inlines
down to `Math.Sqrt`, measured 38.4 to 7.8 ns/call with gen-0 collections eliminated, which matters
under Unity's Boehm GC.

Semantics match an ordinary RPC exactly, via four lean static helpers emitted around the call:

* `Services.CheckExpressionGameScene(procedure)` before every invocation, the same scene-mask check
  and `RPCException` as the ordinary dispatch path;
* `Services.CheckExpressionArgument(procedure, position, value)` around each computed argument of
  reference type at a parameter that is not nullable, the null check the dispatch path makes;
* `Services.CheckExpressionValueArgument(procedure, position, value)` around each computed
  nullable value-type argument at a parameter that is not nullable, which unwraps it or throws;
* `Services.CheckExpressionReturnValue(procedure, value)` after invocation, emitted only for
  reference-typed returns where null is not permitted. The call node's spec is the procedure's
  return spec, so a nullable return and its nullable element positions stay nullable. A direct typed
  call can only violate the declared return type by returning null, so the per-evaluation
  `IsInstanceOfType` reflection check of the boxed dispatch path is provably unnecessary.

A call's result is copied where it holds a collection. Each list, set and dictionary in it is
rebuilt, including nested ones and those in a tuple or structure field, as decoding the value for a
client would. A function therefore never holds a collection the procedure keeps, such as the list
`SpaceCenter.Contract.Keywords` returns. A mutation statement, or a state variable initialized from
a call, changes only the function's copy.

RPC errors are thrown as exceptions, so they propagate to whatever is evaluating the expression.
`YieldException` propagates too, and is reported as an error; see "Yielding procedures inside a
function".

### Statements, control flow and side effects

The node algebra covers running a function, not only computing a value, so that a client can express
anything it could write in a loop locally. LINQ expression trees support all of this; the work is
exposing it as factories with kRPC-shaped semantics.

* Local state: `Variable(name, type)` declares one, `Assign(variable, value)` writes it, and
  `BlockWithVariables(variables, statements)` scopes them. `Block(statements)` is the
  no-declaration form. A block evaluates to its last statement.
* Control flow: `IfThen`/`IfThenElse`, `While(condition, body)` and
  `ForEach(variable, collection, body)`, with `Break()` and `Continue()` inside loops. `While` and
  `ForEach` are desugared into LINQ's loop and label primitives. `Break`/`Continue` are emitted as
  calls to marker methods and rewritten to `goto` against the enclosing loop's labels when the loop
  node is built; binding to the nearest enclosing loop falls out of trees being built
  innermost-first.
* Early exit: `Return(value)` and `ReturnNothing()` are likewise markers, bound to a label that
  `Expression.Lambda` wraps around the function body, so a return anywhere in a nested block leaves
  the whole function. The result type is the common type of the body's value and every
  `Return(value)`, by the rule in "The element type of a collection", so a `ConstantNull(Int())`
  among them makes it nullable. A body that ends with a statement, such as an `IfThenElse`
  returning on both branches, takes it from the returns alone. Reaching the end of such a body
  raises `KRPC.InvalidOperationException`.
* Side effects: calls to procedures with no return value (including property setters) are ordinary
  statement expressions, and collections can be built imperatively.

`ForEach` over a list iterates by position, as Python does, so the body can append to the list it
loops over. Over any other collection it desugars to an enumerator loop wrapped in a `try`/`finally`
that disposes the enumerator, matching what a C# `foreach` statement compiles to. It matters for a
loop over a lazy sequence, whose enumerator holds the enumerator of its source. The loop variable is
a `Variable` that an enclosing `BlockWithVariables` declares, as LINQ requires. `ForEach` does not
check this itself. `Expression.Check` rejects a variable used outside the block that declares it
before the function is compiled.

`Return` is bound when `Lambda` is built, and a function that returns early is therefore
`Invoke(Lambda([], body), {})`, which is what the Python compiler emits for a function with
statements. A block containing `Return` handed straight to `RunFunction` is reported as an unbound
marker. A `Lambda` at the root is called with the `RunFunction` arguments, as "Function
arguments" describes.

Void-typed nodes are the reason several things elsewhere are special-cased: an expression whose type
is `void` has no return type to report, cannot be streamed, and is only meaningful under
`RunFunction`.

**State between evaluations.** A control loop run as a function stream needs a value that
survives from one tick to the next, such as a PI controller's integral. A local variable lasts one
evaluation and a captured value is a constant, so `StateVariable(name, initialValue)` provides it:

* It evaluates `initialValue` once, when the factory is called, and holds the result in a
  `StrongBox<T>` that the node owns. The node compiles to `Field(Constant(box), "Value")`, which
  is writable, so it is read like a variable and is a valid `Assign` target.
* Its type is the initial value's type, which cannot be a function. A narrowing assignment is an
  error, as for any variable. A collection state variable is changed in place by the mutation
  statements.
* The state belongs to the node. A built function keeps it across `RunFunction` calls, streams and
  events. Each evaluation advances it once, and every stream or event of the function evaluates it
  once per update, so two streams of one function advance it twice. Building the function again
  gives a separate state, and there is no reset RPC.
* The box needs no lock, since functions are evaluated on the main thread only.
* A plain `AddStream` of `StateVariable` is rejected, as each update would evaluate the initial
  value again.
* A lazily evaluated initial value, such as from `Select`, is a `KRPC.ArgumentException` pointing
  to `ToList` or `ToSet`.

A per-stream state array passed into the compiled delegate was rejected. A function run through
`RunFunction` would lose its state between calls, unlike a Python closure.

**A loop runs to completion.** `MaxTimePerUpdate` is checked between continuations, never within
one evaluation. A `While` whose condition never becomes false therefore hangs the game's main
thread. An iteration or time budget would close this, at a cost on every iteration, and needs its
own design. The tutorial documents it as a limitation.

### Tuples, collections and strings

Tuples are built by `CreateTuple` and read by `Get`, which special-cases tuple types to map the
index onto the corresponding `ItemN` property. The index must be a constant, and this is inherent
rather than a limitation to lift: tuple elements are differently typed, so an index computed at
evaluation time would leave the resulting node with no static type. It is documented as such.
A tuple has one to seven elements, matching the flat CLR tuple types; the eighth position holds
a nested tuple, which is not a shape kRPC can name or carry.

Structures ([#866](https://github.com/krpc/krpc/issues/866)) are built by
`CreateStruct(type, fieldValues)` and read by `GetField(value, name)`. A field is named to the
server by the name it is declared with, since the wire type carries only the structure's service
and name; the Python compiler maps a pythonic attribute name back to the declared one through the
structure's position in the definitions.

Collections are built from their elements by `CreateList`, `CreateSet` and `CreateDictionary`, or
created empty by `CreateEmptyList`, `CreateEmptySet` and `CreateEmptyDictionary`. The element
type is the common type of the elements, as "The element type of a collection" below defines it.
An empty one names its element types, since there is no element to infer them from, nullable
positions included. `CreateSet` takes a set of values, so the order it evaluates them in is
unspecified. A key repeated in `CreateDictionary` takes the last of its values. Either is then
mutated by `Append`, `Set`, `Remove`, `RemoveAt` and `Clear`, which "Collection operations named by
what they do" below covers. `Get` of a missing dictionary key raises `KRPC.KeyNotFoundException`. A
list index out of range in `Get`, `ElementAt`, `Set` or `RemoveAt`, and a string index in
`StringGet` or `StringSubstring`, raise `KRPC.IndexOutOfRangeException`. Both are added for it, and
Python maps them to `KeyError` and `IndexError`. It maps the CLR `KeyNotFoundException` for every
service, so any service's missing key now reaches a Python client as a `KeyError`. `ContainsKey`
tests for a key, and `Contains` rejects a dictionary with a message pointing at it, since the CLR
would compare key and value pairs. `StringSplit` gives an `IList<string>`, so the parts can be
appended to. An integer `Sum` wraps on overflow, and the aggregations accept unsigned integers.
`Average` of longs is taken over doubles, since `Enumerable` sums longs checked. Both apply to
nullable integers too, with a null skipped.

A collection built inside a function is typed by the interface a `Type` names. The collection
factories, `ToList` and `BuildDictionary` give an `IList<T>` or `IDictionary<K,V>`, so their
`ReturnType` is the `ListType` or `DictionaryType`. A variable of a nested type, such as
`IList<IList<int>>`, can then hold a list of lists the function builds. A tuple widens
element by element to a tuple type it is used at, as an argument, a variable or a structure field,
so `(x, 0, 0)` with a double `x` is a `Tuple<double,double,double>` argument.
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
  running a key function and a value function on every element. A repeated key takes the last
  of its values, as in `CreateDictionary`.

`Concat`, `Union`, `Intersect` and `Except` combine collections whose values have a common type,
and widen each value to it, so a list of ints and a list of nullable doubles give nullable
doubles.

`GroupBy` produces `IDictionary<K, IList<T>>` rather than LINQ's `IEnumerable<IGrouping<K,T>>`,
since `IGrouping` is not a type kRPC can carry and a dictionary is what the result is wanted for.
Its key type is checked against the dictionary key rules when the node is built. The key of
`OrderBy`, `MinBy` and `MaxBy` must have an order: a number, string, boolean or enumeration, a
nullable one, or a tuple of them, checked when the node is built. `MinBy`, `MaxBy` and `GroupBy`
are single-pass helpers rather than LINQ calls.

#### The element type of a collection

The element type of `CreateList` and `CreateSet`, and the key and value types of
`CreateDictionary`, are the **common type** of the values. It is a function of the set of types
present, computed over all of them at once:

1. **Nullable** at a position wherever any value is nullable there. This holds for strings,
   classes and collections as for numbers, and nulls are kept. A set element and a dictionary key
   are never nullable, so a nullable one is checked for null as it goes in.
2. **One type** gives that type. A `List<T>` counts as an `IList<T>`, and a `Dictionary<K,V>` as
   an `IDictionary<K,V>`.
3. **Numbers** give `double` if any is a `double`, else `float` if any is a `float`. Otherwise:
   * any `ulong` gives `ulong` when every other is a `uint` or `ulong`, and an error otherwise;
   * else any `long`, or both `int` and `uint`, gives `long`;
   * else any `uint` gives `uint`, and only `int` gives `int`.
4. **Tuples of one length, or collections of one kind**, give that tuple or collection with the
   common type of the set of types at each position.
5. **Anything else** is a `KRPC.InvalidOperationException` when the node is built, as for
   `Concat`, `Union`, `Intersect` and `Except`. The message lists the distinct types sorted by
   name.

Each value then widens to the common type, as a value at any position of a fixed type does.

| Values | Common type |
| --- | --- |
| `1`, `2.5` | `double` |
| `1`, `2**63` | error: no integer type holds both |
| `1`, `2**63`, `2.5f` | `float` |
| `(1, "a")`, `(2.5, "b")` | `Tuple<double, string>` |
| `1`, `null` of `long?` | `long?` |

**The rule is a function of the set, not a fold.** The pairwise join of C# binary promotion is
not associative. `int` and `ulong` have no common type, but joining `int` with `float` first and
then `ulong` gives `float`. A fold over the values therefore depends on their order, and a set
arrives in the order of the client's hash table. Taking the set of types at once makes order
and repeats irrelevant, at every nested position. For two types the rule is binary promotion, so
`Conditional` and the operators agree with it.

**`int` with `ulong` is an error, not `float`.** In the implicit-widening order `float` is their
least upper bound, which would make the join associative. It also turns a list of large `ulong`
ids into floats silently, so it is rejected, as C# rejects `int + ulong`. A `float` or `double`
among the values makes the precision loss explicit, and the rule then accepts it.

The **result type of a function** follows the same rule. It is the common type of the body's
value, when it has one, and of every `Return(value)`, and each returned value widens to it.

**The type is deduced, not passed.** A client that wants a specific type already has three ways
to state it:

* `Cast(CreateList(values), ListType(Double()))` converts a list element by element, narrowing
  too, as a `Cast` of each element would.
* A typed variable, argument or structure field widens a collection used there.
* Casting one element resolves an `int` and `ulong` mix.

A required type parameter would make the Python compiler find a type it often does not know,
such as the result of a call it has no definitions for. A typed overload would add three RPCs to
every client for the case `Cast` covers. With an order-independent rule the deduced type is
deterministic, and the Python compiler mirrors it to type its results.

#### Collection operations named by what they do

Mutations are five nodes, each named for the operation, with the type of the collection deciding
what it does:

| Node | List | Set | Dictionary |
| --- | --- | --- | --- |
| `Append(c, value)` | adds at the end | adds | - |
| `Set(c, index, value)` | writes an element | - | writes an entry |
| `Remove(c, value)` | removes a value | removes a value | removes by key |
| `RemoveAt(list, index)` | removes by position | - | - |
| `Clear(c)` | empties | empties | empties |

* **The shape follows `Get`**, which already read a tuple, a list and a dictionary through one
  node. A client learns one verb per operation, and the compilers dispatch on the tracked type
  rather than choosing a node per collection.
* **`Append` is not `Add`**, because `Add` is numerical addition.
* **Each node checks the kind of collection it was given**, so a wrong collection is an error when
  the tree is built.

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

`ConvertToString` throws for a null, since the text of a null differs between languages. The Python
compiler writes `None` for one and the C# compiler an empty string, each with a conditional. A value
other than a number, boolean, string or enumeration converts as .NET formats it, which for a
collection is the name of its type. The Python compiler formats collections itself.

`StringIndexOf` returns `-1` rather than a nullable `int`. Nullable values would be the more honest
type, but `-1` is what `str.find` and `String.IndexOf` return in the languages both compilers
translate from, so it keeps the mapping transparent. `StringTrim` trims whitespace and takes no
character set, matching the no-argument form of both.

**Every one of these is culture sensitive and must be pinned.** `ToUpper`/`ToLower` are culture
sensitive in C#, and so are the default `IndexOf`, `StartsWith` and `EndsWith` overloads.
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
to infer the type from and it would have to be supplied explicitly at every use. `Conditional` does
give a `Throw` in one branch the type of the other, which the C# compiler uses for a client side
branch that fails to evaluate.

A function throws an exception a service declares with `[KRPCException]`, and a function cannot
declare its own. The KRPC service's set covers the common conditions, with `Error` for any other,
whose meaning goes in the message:

| Exception | Maps the CLR type | Python | C# | Java |
| --- | --- | --- | --- | --- |
| `ArgumentException` | `System.ArgumentException` | `ValueError` | `ArgumentException` | `IllegalArgumentException` |
| `ArgumentNullException` | `System.ArgumentNullException` | `ValueError` | `ArgumentNullException` | `IllegalArgumentException` |
| `ArgumentOutOfRangeException` | `System.ArgumentOutOfRangeException` | `ValueError` | `ArgumentOutOfRangeException` | `IndexOutOfBoundsException` |
| `NullReferenceException` | `System.NullReferenceException` | `TypeError` | `NullReferenceException` | `NullPointerException` |
| `InvalidOperationException` | `System.InvalidOperationException` | `RuntimeError` | `InvalidOperationException` | `UnsupportedOperationException` |
| `KeyNotFoundException` | `System.Collections.Generic.KeyNotFoundException` | `KeyError` | `KeyNotFoundException` | `NoSuchElementException` |
| `IndexOutOfRangeException` | `System.IndexOutOfRangeException` | `IndexError` | `IndexOutOfRangeException` | `IndexOutOfBoundsException` |
| `DivideByZeroException` | `System.DivideByZeroException` | `ZeroDivisionError` | `DivideByZeroException` | `ArithmeticException` |
| `NotSupportedException` | `System.NotSupportedException` | `NotImplementedError` | `NotSupportedException` | `UnsupportedOperationException` |
| `TimeoutException` | `System.TimeoutException` | `TimeoutError` | `TimeoutException` | generated |
| `OverflowException` | `System.OverflowException` | `OverflowError` | `OverflowException` | `ArithmeticException` |
| `ObjectDestroyedException` | none | generated | generated | generated |
| `Error` | none | generated | generated | generated |

The Python, C# and Java clients raise the built-in type in the table itself. "generated" is the
class the client generates for the exception, a `RuntimeError` subclass in Python. Java keeps the
generated `TimeoutException`, as Java's own is a checked exception. The C++ client raises the
generated class for every exception. `Get`, `ElementAt`, `StringGet`, `StringSubstring` and the
list mutation statements check the index and throw `IndexOutOfRangeException`, and so does `Get`
with a constant tuple index, when the node is built. A service's own
index check still throws the argument exception.
The mappings apply to every service, so a service that throws one of the new CLR types reaches
the client as a typed exception.

**Handling** is `TryCatch(body, service, name, message, handler)` for a named exception,
`TryCatchAll(body, message, handler)` for any, and `TryFinally(body, finalizer)` for cleanup that
runs either way. Body and handler are evaluated as statements through the existing `AsStatement`, so
they need not produce values of the same type.

LINQ cannot compile a jump out of a finally block, so `Check` rejects a break, continue or return
that leaves a finalizer, with a message naming the rule.

`message` is an optional string variable that the caught exception's message is assigned to before
the handler runs. **The exception object itself is never exposed.** Binding only the message keeps
exceptions out of the value algebra entirely: nothing needs an exception-typed entry in `KRPC.Type`,
and no value that cannot cross the boundary can be carried toward it. LINQ's `Catch` binds the
exception rather than its message, so the implementation catches into a synthesized variable and
assigns `.Message` from it as the first statement of the handler.

**A name must resolve to every CLR type that reaches the client under it.** This is the one thing
that has to be right, and the obvious implementation gets it wrong.
`[KRPCException(MappedException = ...)]` maps a CLR exception type onto a kRPC one, and
`HandleException` applies that mapping on the way out, for every exception in the table above
apart from `ObjectDestroyedException` and `Error`.
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

**The set must not widen either, and a CLR catch block widens it.** `catch
(System.ArgumentException)` also catches `ArgumentNullException` and `ArgumentOutOfRangeException`,
which map to kRPC types of their own, and `catch (System.InvalidOperationException)` catches
`ObjectDisposedException`, which maps to nothing and so reaches the client with no name at all.
`HandleException` maps by exact type, so each of those arrives under a name the catch did not name,
and the kRPC exception classes are flat: they are all `sealed` and derive from `System.Exception`,
so no client can express the subclass relationship the catch is assuming. Each handler therefore
opens with `Services.ExpressionExceptionIsNamed(caught, type)` and rethrows when it is false. An
exception filter would say the same thing more directly, and is avoided here for the reason
`TryCatchAll` avoids it. The rule the two halves buy is one sentence: a name catches exactly the
exceptions that reach the client under it.

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
event it becomes an error result, which ends the stream as any error result does ([`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md)).

`ExceptionSignature` does not record the CLR type of the exception, unlike `ClassSignature`,
`EnumerationSignature` and `StructSignature`, so resolving `(service, name)` to a type it can
construct requires an `UnderlyingType` on it, threaded through `ServiceSignature.AddException`. It
is not serialized, so the service-definitions JSON is unaffected, the same approach taken for
classes, enumerations and structures.

### Computed streams and events

`KRPC.AddFunctionStream(Expression function)` returns a `Stream` message, started, and is
symmetric with `AddStream`. It validates at creation time that the function's type is a
serializable kRPC type (`TypeUtils.IsAValidType` on the static type), with an error message pointing
at `ToList`/`ToSet` for lazy enumerables. A void function and a protocol buffer message type, which
`Type.Code` cannot describe, each get their own message, and `ReturnType` applies the same check.

`FunctionStream : Stream` evaluates the `Func<object[], object>` the `Expression` caches, with no
arguments. `UpdateInternal` turns any exception into a `Result.Error`. A `YieldException` becomes an
`InvalidOperationException` naming the pause, per "A yield is an error, and nothing retries". Each
value is compared with the last one sent by its encoding, so an unchanged value is not resent. A
collection changed in place is the same object with a new encoding, so it is sent. The `TypeSpec`
built at creation time tells `Encoder.Encode` how to serialize the boxed result, so no per-update
type routing is needed.

`FunctionStream` encodes its value in `UpdateInternal`, so a value that cannot be encoded, such as
a null element in a list of objects, fails only its own stream. That is the rule for every stream
kind ([`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md)), as is `EventStream` turning a predicate error into an error result. `AddEvent` reports "The function must
evaluate to a boolean value" when given anything else. It takes a `bool?` as its value, so a null
becomes an error on the event's stream.

**Every `AddFunctionStream` and every `AddEvent` creates a new stream**, per the rules in
[`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md). Function streams are never shared, so two streams of one
function are two evaluations per update. The stack deduplicates them by `Expression` object as
written, and the rebase onto that work removes it.

**Streams are not unified with procedure-call streams on the server, and are in the clients where
the language allows.** `AddStream` takes an encoded `ProcedureCall` and `AddFunctionStream` takes an
`Expression` object; kRPC procedures are not overloaded, so one procedure would have to take both
and reject one of them at runtime, replacing a signature that says what it accepts with an error
that says what it did not. The clients whose type systems overload do so: C# has an
`AddStream<T>(Expression)` overload and Java an `addStream(Expression)` overload, so a user of those
writes the same call for either. Python's `add_stream` takes either a remote procedure or a
function. C++ has a `krpc::add_stream` function for a function, and a procedure call stream comes
from the generated `_stream` method.

### Run-once functions

Events and streams re-evaluate on every update, which makes them the wrong home for a function with
side effects. `KRPC.RunFunction(Expression, IList<byte[]> arguments)` compiles the
expression, invokes it exactly once with the arguments inside the calling tick, and returns its
result.

The compiled delegate is cached on the `Expression` object, so a function is compiled the first time
it is run and reused on every later call. It is not compiled when the object is created: most
expression objects are interior nodes of a larger tree and are never run on their own, so compiling
every one of them would pay the cost hundreds of times over for a single function. `RunFunction`,
`FunctionStream` and `AddEvent` share the cached delegate. Checking the tree for unbound
`Break`/`Continue`/`Return` markers is cached the same way.

`KRPC.CompileFunction(Expression)` checks and compiles a function without running it. Compiling
runs on the game's main thread, so a large function stalls the frame it is compiled in. Compiling
it in advance moves that stall to a moment the client chooses, such as before launch, and its first
run is then as fast as later ones. The clients' `compile` and `Compile` call it,
since a compiled function is one meant for reuse. The helpers that compile a function for a single
use do not, as the run compiles it anyway. Compiling on a worker thread, with `RunFunction` waiting
for the delegate, would remove the stall altogether, at the cost of threading under KSP's Mono.

The return value is a `bytes` payload rather than a typed value, since the procedure's declared
return type cannot depend on the expression: the server encodes the value with the runtime-typed
`Encoder.Encode` and the client decodes it using `Expression.ReturnType` (dynamic clients) or a
user-supplied type parameter (static clients). A void-typed function returns an empty payload, which
is why `HasReturnType` exists: an empty collection encodes to an empty payload too, so a client that
decodes by payload length rather than by type would report `None` for an empty list.

A null value is carried by `ProcedureResult.is_null`, which `RunFunction` gets by declaring its
`bytes` return nullable. That is the channel every other nullable return uses, and the rule
[nested-nullable-values.md](../protocol/nested-nullable-values.md) sets for a value at the call
boundary. The result is encoded with the function's spec, so a null nested inside it is carried at a
nullable position and is an error naming the position elsewhere. A null result is an error when the
function's spec is not nullable. On the client, a null result at a type that cannot hold one is an
error too: a C# value type that is not nullable, or a C++ type that is not a `std::optional`. A C++
function stream read with such a type throws `std::runtime_error`. In a stream callback that error
is written to stderr and the callback does not run. A C++ caller names `std::optional` at each
nullable nested position, as in `run<std::vector<std::optional<Vessel>>>`.

`YieldException` is turned into a plain error, since a procedure that pauses and resumes on a later
tick cannot be honored by a call that must complete within this one.

### Function arguments

**Status:** built, and folded into the stack's phases (see "Phases"). Where the build diverged
from the design is noted below.

A function compiled once can be run many times with different inputs. Capturing a new value
otherwise means building the tree again, one RPC per node, and compiling it again on the server.
`RunFunction` takes zero or more argument values. Streams and events take functions with no
parameters, since nothing would supply the arguments on each update.

```python
@conn.compile
def burn_time(delta_v: float) -> float:
    ...
for dv in (100.0, 250.0, 400.0):
    print(conn.run(burn_time, dv))
```

**Server.**

| Item | Design |
|---|---|
| Shape | A function with parameters is a `Lambda` at the root. A root `Lambda` is called with the arguments; any other root is a function with no parameters, as now |
| `RunFunction(Expression function, IList<byte[]> arguments)` | Arguments by position, one per parameter. Elements nullable (`[KRPCNullable (Position.Element)]`); the parameter defaults to an empty list, so a call with no arguments is unchanged |
| Decoding | Each argument is decoded at its parameter's spec, as the result is encoded at the function's. A null at a parameter that is not nullable, a wrong count, or bytes that do not decode to the parameter's type, such as an object of another class, are a `KRPC.ArgumentException` naming the parameter, before anything runs |
| `ReturnType`, `HasReturnType` | Of a `Lambda`, describe the value it returns when called. A delegate type is never a valid result, so the meaning is unambiguous |
| `ParameterTypes` | New `IList<Type>` property: the types of a root `Lambda`'s parameters, with their nullability. Empty for any other function |
| Compiled delegate | `Func<object[], object>`, unpacking the array into the lambda's parameters. Cached on the `Expression` as now, shared by `RunFunction`, `CompileFunction`, streams and events |
| Streams and events | `AddFunctionStream` and `AddEvent` accept a `Lambda` with no parameters. One with parameters is a `KRPC.ArgumentException`: "A function that is streamed, or checked for an event, cannot take parameters" |

Arguments are encoded values rather than `Expression` constants. A constant is an RPC per value, and
the server caches every constant for the life of the connection, so a constant per call is the cost
this removes. Encoded bytes mirror the result, which is already sent as bytes and decoded at a type
the client learns from the function.

**Clients.** Each client encodes an argument at its parameter's type. A Python function carries
its parameter types from the compiler. Any other function's are read from `ParameterTypes` once
and cached by object id, as `ReturnType` is, including a compiled C# lambda, whose reference-type
nullability only the server records. Every client introspects a function without compiler types
on its first run, given arguments or not. A wrong argument count, including none, is then a
client side error, a `TypeError` in Python.

| Client | API |
|---|---|
| Python | `run(function, *args, **kwargs)`. Each argument is coerced as an ordinary call's is and checked against its parameter, a `TypeError` naming the argument's position. `compile` accepts a function with parameters; `add_stream`, `stream` and `add_event` reject one before calling the server, an uncompiled `def` as a compile error and a compiled one as a `StreamError` |
| C# | `Run<TResult>(Expression function, params object[] args)` and the non-generic form. `Compile` overloads for `Func<T1, ..., TResult>` and `Action<T1, ...>` up to four parameters. A number widens as C# widens it, including `sbyte`, `byte`, `short`, `ushort` and `char`. A signed integer that is not negative converts to an unsigned parameter at least as wide: `sbyte`, `short` and `int` to `uint` or `ulong`, `long` to `ulong`. An array other than `object[]` passed as the only argument of a one-parameter function is that argument. The argument count is checked on the client, including for no arguments. An argument the parameter's type cannot hold, including a null element of a collection that cannot hold one, throws an `ArgumentException` before the call, naming the argument's position. A null for a parameter that is not nullable is checked by the server |
| C++ | `run<T = void>(function, args...)`, one template for a value and for effects, since separate overloads are ambiguous for `run<int>(f, 3)`. Each argument is checked against `ParameterTypes`: by structure for collections and tuples, and by kind only for classes, enumerations and structures. A nested nullable position takes a `std::optional` or a plain value, a non-nullable one only a plain value, and a `std::string` matches `String` or `Bytes`. A number converts to a `double`, and an integer or a `float` to a `float`, as C++ converts it implicitly, which can round. An integer converts to a signed parameter that holds every value of its type, and an integer that is not negative to an unsigned parameter at least as wide. A number a collection or tuple holds converts the same way. `std::nullopt` or `nullptr` is a null. The argument count is checked on the client, including for no arguments. A mismatch names the argument's position. The server checks an object's class and a null for a parameter that is not nullable (`ArgumentException`) |
| Java | `run(function, Object... args)`, encoded at the introspected `ParameterTypes`, with a number widened as Java widens it (`byte`, `short`, `int`, `long`, `float`, `double` only). The client holds unsigned values in signed types bit for bit, so an `int` passes to `UINT32` and a `long` to `UINT64` with any value. A `byte` or `short`, and an `int` for `UINT64`, must not be negative. A mismatch, a wrong argument count including for no arguments, or an argument that fails to encode is an `IllegalArgumentException` naming the argument's position, and the item within a collection, tuple or structure. The server checks a null for a parameter that is not nullable and an object's class, also an `IllegalArgumentException`, with no client position |
| Lua | No helper. The raw `RunFunction` takes the encoded arguments |

**Python parameters.** Only a `def` takes parameters, each annotated with a form a variable
annotation accepts: `float`, `list[int]`, `Optional[str]`, `Vessel`. A lambda with parameters, or
a parameter without an annotation, is a compile error naming the fix.

* Defaults, keyword arguments, positional-only and keyword-only parameters are bound on the client
  by `inspect.signature(func).bind`, which applies Python's own rules and raises its `TypeError`.
  The server sees every argument, by position.
* A default is the value the `def` evaluated, as in Python, checked against the parameter's type
  when the function is compiled.
* `compile` records the signature against the function's object id, beside its types, for
  `run` to bind with. A hand-built function takes positional arguments only.
* `*args` and `**kwargs` are a compile error, since a `Lambda` has a fixed parameter list.

The compiled tree of a top-level `def` with parameters is the `Lambda` from `compile_function`,
without the `Invoke` a parameterless function wraps it in. `run` given an uncompiled
`def` compiles it on each call, as now.

A parameter annotation names a type where the function is defined, which need not be a free variable
of the function. The compiler resolves annotation names from the evaluated `__annotations__` first.
A class reached through a service, as in `Vessel = conn.space_center.Vessel`, is a wrapped subclass
of the stub class with the pre-generated stubs, and is unwrapped.

Defaults stay on the client. Server-side defaults would serve hand-built C++ and Java trees only,
since a C# expression-tree lambda cannot declare one, and would need position-keyed arguments and a
default introspected per parameter.

**C#.** `FunctionCompiler.Compile` maps the lambda's parameters to `Parameter` nodes through the
dictionary the nested-lambda support already keeps, and wraps the body in a `Lambda`. The types
come from the delegate's generic arguments, with a reference type nullable at its top level, as a
local is.

**Testing.**

* Core: argument count, null and decode errors; `ParameterTypes`; a nullable parameter; streams
  and events rejecting parameters; a parameterless root `Lambda` streamed and run.
* Python and C# golden trees for a function with parameters; client tests running one with
  several argument sets, including an object and a collection.
* C++ and Java client tests against the TestServer, and one in-game test.

### The StdLib service

Expressions can only call RPCs, so any arithmetic beyond the operator nodes would mean a round trip:
`math.sqrt` on a streamed value is not otherwise expressible. `StdLib` is a core service supplying
the missing primitives as ordinary RPCs:

* scalars: `Abs`, `Sqrt`, `Exp`, `Log`, `Log10`, `Floor`, `Ceiling`, `Sign`, `Clamp`, `Min`,
  `Max`, the trigonometric functions (`Sin`/`Cos`/`Tan`/`Asin`/`Acos`/`Atan`/`Atan2`) and
  `DegreesToRadians`/`RadiansToDegrees`. Exponentiation is the `Power` operator node. `Clamp`
  throws if its minimum is greater than its maximum.
* further scalars: `CopySign`, `IsNan`, `IsFinite`, `Hypot`, scaled so its squares do not
  overflow, `Lerp`, which extrapolates outside 0 to 1 and is exact at both ends, and
  `InverseLerp`, which is limited to 0 to 1 and gives 0 when the two ends are equal.
* the constants `Pi` and `E`, as properties. A client that folds its own `math.pi` into a
  constant node never calls them, and a tree built through the expression API has no other
  source for them.
* one procedure per midpoint rounding rule, matching `Floor` and `Ceiling` beside them rather than
  taking a mode: `Round` rounds a halfway value to even, as Python and C# do, and
  `RoundHalfAwayFromZero` and `RoundHalfUp` are the C and Java rules. A client can then round the
  way its own language does. Each takes the number of decimal places, and decides on the exact value
  of the double, as Python's `round` does, so `Round(2.675, 2)` is 2.67. A NaN or an infinity passes
  through, more than 323 places returns the number unchanged, and fewer than -308 gives 0, as in
  Python. A result too large for a double throws `OverflowException`. `Log` takes the base of the
  logarithm, so a quantity is a parameter where a rule is a name.
* vectors and quaternions over the tuple types the SpaceCenter service already uses:
  `VectorAdd`/`Subtract`/`Scale`/`Dot`/`Cross`/`Magnitude`/`Normalize`/`Distance`/`Angle`/`Lerp`,
  and `QuaternionMultiply`/`Inverse`/`Angle`/`Slerp`/`FromAxisAngle`/`RotateVector`. A magnitude
  is scaled, as `Hypot` is, and a vector is divided by its largest component before it is
  normalized, so a vector of any finite size normalizes. `VectorAngle` and `QuaternionAngle` use
  an arc tangent, precise near 0 and pi, and `QuaternionSlerp` follows the arc down to 1e-8
  radians. Every quaternion procedure throws for a zero quaternion.
* `QuaternionToAxisAngle`, giving a unit axis, or zero for no rotation, and an angle between 0
  and pi; `QuaternionFromToRotation`, the shortest rotation between two directions, a half turn
  within 1e-8 radians of opposite; and `QuaternionLookRotation`, Unity's convention of the z
  axis forward and the y axis toward up, an error when the two are parallel.
* `Print`, which writes the message to the game's log at the Info level, for debugging a function.
  Python's `print` and C#'s `Console.WriteLine` compile to it. A function evaluated by a stream
  or an event prints on every update.

These exist to be called from inside functions, and are what the client compilers target when they
see `math.sqrt` (Python) or `System.Math.Sqrt` (C#). Each compiler holds the number of arguments its
target takes, so an overload with no equivalent, `Math.Round(x, MidpointRounding.ToZero)` for
instance, is reported when the function is compiled rather than when the server runs it. Only
`ToEven` and `AwayFromZero` map: `ToZero`, `ToNegativeInfinity` and `ToPositiveInfinity` are
directed rounding rather than midpoint rules, and no procedure performs them. A rounding mode
selects the procedure, so it has to be a value the client computes, such as a constant or a
captured variable. Because calls compile to direct typed invocations
of the underlying method, the JIT inlines them, so the indirection costs nothing at evaluation time.

### Client libraries

Building a tree needs no client work, since the factories are ordinary generated or dynamic service
stubs. Running a function as a stream or as a one-shot needs a small helper per client, in each case
decoding a value whose type the server reports rather than the stub declares.

* **Python** (dynamic): `Client.add_stream(function)` and the `Client.stream(...)` context manager
  take a function where they take a remote procedure. They tell the two apart by the call builder
  every remote procedure carries, and reject arguments to a function. For a function they call the
  RPC, walk `function.return_type` to rebuild the protobuf `Type`, and wrap the stream id with
  `Stream.from_stream_id(client, id, types.as_type(...))`, all existing machinery.
  `Client.run(function, *args, **kwargs)` passes the arguments and decodes the `RunFunction`
  payload the same way, returning `None` for a void function. `Client.add_event(function)` checks
  for a stream connection, as `add_stream` does.
* **C#**: `Connection.AddStream<T>(Services.KRPC.Expression)` and `Connection.Run<T>(...)`
  overloads, where the user supplies `T`; a non-generic `Run` covers functions with no
  result. `T` is checked against the introspected type, so a void function or a mismatch throws
  rather than decoding bytes as the wrong type. A lambda passed to a helper skips the check, and
  is decoded at the type of its body, which `T` must be able to hold. Where that type holds a
  reference in a collection or tuple, whose nullability only the server records, the helper
  introspects it on every call, uncached, as the lambda is compiled for that call only. An
  undecodable body type throws before the server runs anything. `AddStream` and `AddEvent` need
  a stream connection. An argument converts as C# converts it, and a signed integer that is not
  negative converts to an unsigned parameter at least as wide, so a `long` converts to a `ulong`
  but not a `uint`.
* **C++**: `krpc::run<T>` and `krpc::add_stream<T>` check `T` the same way, through a trait
  mapping C++ types onto type codes. Generated class, enumeration and structure types carry no
  names, so only their kind is compared. `krpc::add_event` creates an event from a function.
  `add_stream` and `add_event` check for a stream connection and throw `StreamError`
  without one.
* **Java**: typed helpers matching the client's stream-construction idiom, plus a run-once
  helper and `Connection.addEvent`. Java decodes by the introspected type, per "Types and
  introspection", so there is no `T` to check. Java always has a stream connection.
* **Lua**: no helper. A Lua client builds trees through the ordinary factories, and `RunFunction`
  hands it back encoded bytes to decode itself. Events and function streams need streams, which
  the Lua client does not have. The tutorial says which clients support what.

In every client, two events or streams over one function are two server streams.

Each helper introspects the type once per function and keeps it, apart from the C# lambda case
above. Walking `ReturnType` is a round trip per property of every type it is built from, and
`run` would otherwise pay all of them on every call, which is the opposite of what the
procedure is for. The type a function returns cannot change, so it is cached against the
expression's object identifier. Python's `compile` keeps the type the compiler tracked against the
function it returns, so a compiled function is not introspected on its first run.

**A Python function given to a helper is compiled on every call.** Caching the compiled function
against the Python function would freeze its captured values across calls, when they may have
changed. The compiler tracks the result type as it builds the tree, so the helper takes the type
from it instead of introspecting, and caches nothing for a function compiled for a single use.
The compiler reports a function with no value apart from one whose type it does not know, so a
function with no value is never introspected. A program that runs the same function repeatedly
compiles it once with `compile` and passes the result, as the docstrings say.

### Documentation ([#608](https://github.com/krpc/krpc/issues/608))

* A conceptual and tutorial page, `doc/src/tutorials/server-side-functions.rst`, covering what
  server side functions are and when to use them, custom events, computed streams, run-once
  functions and side effects, `Parameter`/`Lambda`/`Invoke` and how named parameters bind, `Select`
  versus `Where`, per-element RPC calls, object constants, type promotion and `Cast`, and errors and
  the yield limitation. The expression API examples cover Python, C#, Java and C++, the
  clients with streams; the compiled examples cover Python and C#, the clients with compilers.
  C, Lua and cnano build functions with the generated stubs, without examples of their own.
* The launch into orbit tutorial waits with events in place of busy loops, and the sub-orbital
  flight tutorial builds its events with each client's event helper. The control loops and
  buoyancy tutorials read a consistent tick with a function run once, and the parts tutorial
  deploys every parachute in one tick. The client guides link to the tutorial.
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
or a `Return` with no enclosing lambda, is left as a call to an empty marker method.
`Expression.Check` rejects a leftover marker at each point the tree is compiled, rather than only in
`Expression.Lambda`, since a block can be handed straight to `RunFunction` with no lambda wrapper. A
`Return` inside a lambda is also type-checked against the lambda's result type when the lambda is
built.

## Yielding procedures inside a function

### Background

Some procedures cannot finish within the tick they are called in. Called as a normal RPC, such a
procedure signals this by throwing `YieldException`, which carries a delegate that resumes the
work. `ProcedureCallContinuation.Run` catches it and rethrows a continuation wrapping
`e.CallUntyped()`; the core parks that in `rpcYieldedContinuations` and calls it again on each
update until it completes. The client never sees any of this: its call simply takes several ticks.

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

The one re-run is for a lookup that fails while the game is between states.
[`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md) holds that error, restores the function's
state variables, and evaluates again on the next update. The game settling ends the window, so an
effect before the lookup repeats for the length of a load, not for as long as a call yields.

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

### Follow-ups

Neither is built. Both are designed in [`yielding-procedures.md`](yielding-procedures.md), as
follow-ups to this stack rather than phases of it.

* **Deferred calls.** A function starts a procedure that pauses, and carries on without waiting
  for it. The core drives the call to completion on later updates. The function stays within one
  tick, and the procedure's result is discarded.
* **Resumable functions.** A pause suspends the whole function, and `RunFunction` resumes it on a
  later update. The function can use what the procedure returns, and spans several ticks.

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

`Client.compile` compiles a lambda or a function from its source, and a `def` with parameters as
"Function arguments" describes; `add_event`, `add_stream` and `run` accept
functions directly. `compile` returns the compiled function, so it also works as a decorator. A
lambda is located in the parse of its whole source file by its exact position, from its code
object. A lambda that cannot be identified is a compile error. Every compile rejects a stream read
inside a function, as it would be evaluated once. `add_event` and `add_stream` reject a
Python function passed without `compile` that makes no remote call and uses no state variable; a
compiled one is accepted. A `StdLib` call or property does not count as a remote call, as it gives
the same value for the same arguments.

* Expressions (`krpc/functioncompiler.py`): operators including floor division, true-division
  semantics, a remainder taking the sign of the divisor, the bitwise operators, and `is None`
  and `is not None` through `IsNull`; comprehensions (list, set and dict, nested) and generator
  expressions; `any`/`all`/`sum`/`min`/`max`/`len`/`sorted`/`abs`/`round`/`int`/`float`/`str`;
  subscripts and slices; f-strings; conditional expressions through `Expression.Conditional`;
  assignment expressions in a function body, where one in a lambda binds a variable of the
  lambda; parameterless lambdas and local function calls; `math` module calls mapped onto
  `StdLib`; and `print`, with a constant `sep`, mapped onto `StdLib.Print`.
  A generator expression compiles to a list, so it can be held or passed. `any` and `all` over a
  generator expression nest the quantifier per `for` clause, so they stop at the deciding value;
  one held in a variable is computed in full. Arithmetic, `math` calls and `sum` widen a `float`
  operand to `double`, as Python holds a single precision value as a double. `math.dist` takes
  tuples of any length, through `StdLib.Hypot` where they are not 3-D. Float floor division
  follows CPython's remainder-based algorithm, and float `min` and `max` keep the first value
  unless a later one compares smaller or larger, as Python does with a NaN. A condition tests a
  tuple, an enumeration value or a structure as true unless null, and bytes as true unless
  empty. A dictionary display, keyword arguments and structure fields are evaluated in source
  order, held in variables where the server's order differs.
* Statements (`krpc/functionstatements.py`): `if`/`elif`/`else`, `while` and `for` with
  `break`/`continue`, early `return`, local variables including augmented and annotated assignment,
  assignment to remote properties and to collection elements, `pass`, calls evaluated purely for
  their effects. A block holding only `pass` statements or local function definitions compiles
  to a no-op. List `+=` extends the list in place, as `list.extend` does.
* `nonlocal x` at the top level of the compiled function makes `x` a `StateVariable`. Its initial
  value is the closure cell's value at compile time, and the cell is never updated. A compiled
  function keeps its state, and an uncompiled one is rebuilt on each call, so it starts again from
  the cell. The type comes from the initial value. A statement `x = cast(T, x)` of the function's
  body, before any other use of `x`, gives it the type `T` instead, so it can start as `None` or
  an empty collection; an annotation cannot, as Python forbids one on a `nonlocal` name. A cast in
  a nested block or after a use is a compile error. A state variable can be a `for` target, assigned
  from a hidden loop variable, since `ForEach` takes a variable. A variable first assigned a single
  precision value is declared a `double`, as Python holds one as a double, so arithmetic on it
  assigns back. A `for` loop over single precision values assigns each to its variable from a
  hidden loop variable.
* Strings and collections dispatch on the statically tracked type: `len`, `[i]`, `[a:b]`, `in`,
  `.upper()` and `.split()` reach the string operations, with slicing compiling to
  `StringSubstring`. `min`/`max` with a `key` reach `MinBy`/`MaxBy`, taking several arguments as
  a list of them, and the list, set and dictionary methods reach appending, removal and clearing.
  `keys()` and `values()` reach the dictionary views.
* Some reshaping operations have syntax: `sorted` reaches `OrderBy`, `reversed` reaches `Reverse`,
  a slice of a collection reaches `Skip` and `Take`, and a nested comprehension reaches
  `SelectMany`. A dict comprehension is a `ForEach` that sets each key, so a repeated key takes the
  last value, as in Python and in `BuildDictionary`. `zip(a, b)` and `d.items()` reach `Zip`.
  `list + list` reaches `Concat` and `ToList`. The rest are factory-only. Their natural syntax does
  not name them in its error: `set(xs)` reports a client side function called with an argument
  computed on the server. A client side function called when compiling, such as a captured helper
  or a property of a captured object, is an error if it makes a remote procedure call. The
  compiler counts the calls each thread sends through the connection while the function runs.
* Constructs with no node of their own lower onto existing ones, with no server change:

  | Construct | Lowering |
  |---|---|
  | `range`, `enumerate` | a value block building a list in a `While` or `ForEach` loop; `range` needs a constant step, whose sign picks the comparison. A constant `range` is lowered the same way, so its size does not set the size of the tree. The loop counts in a long, so a range ending near the limits of an int ends |
  | `d.items()` | `Zip` of `DictionaryKeys` and `DictionaryValues`, with the dictionary in a temporary |
  | iterating `d` | over `DictionaryKeys(d)` |
  | `k in d` | `ContainsKey(d, k)` |
  | tuple targets | `Get` by constant index, from a hidden variable in statements |
  | truth of a condition | `!= 0`, a length or count `!= 0`, or `IsNull`, after an `IsNull` test of a nullable value |
  | `a or b` on non-booleans | `Conditional` on the truth of a temporary holding `a` |

  A `Range` node would replace the `range` lowering. A client side call written as a statement is
  an error, since it would run once, at compile time.
* Integer results keep their server type. `//` is an exact integer floor division built from
  `Divide` and `Modulo`, and integer `abs`, `min` and `max` are `Conditional` on temporaries.
  `int()` of an integer, and `round()` of one to a place at or after the point, are the integer
  itself. `round()` of an integer to negative places is computed in the integer's type, half to
  even. `int()` and `round()` of a float give an `int`. `min` and `max` of an empty collection
  raise `ValueError`. A negative constant index counts from the end through `Count` or
  `StringLength`, and a string slice clamps its bounds to the length, as Python does. A `None`
  slice bound is no bound, and a computed tuple sliced by constant bounds is a `CreateTuple` of
  `Get`s. `int()`, `float()`, `round()` and `abs()` of a nullable number cast it to its plain type
  first, which raises `TypeError` for `None`. Inverting a `uint` with `~` gives a `long`, as
  negation does, and inverting a `ulong` is an error. A float remainder of zero takes the sign of
  the divisor, and a float floor quotient of zero the sign of the true quotient.
* A final `if`/`else` whose branches both return a value, or are a single `raise`, compiles to a
  `Conditional` of two blocks, so the function's value is its last expression. Any other final
  `if` that returns or raises on every path, and a final `try` whose body and every handler
  return, is a statement, with its returns bound by the function's `Lambda`. A final `while True`
  with no `break` returns on every path. A function annotated with a return type whose every path
  raises, including a final `if`/`else` that raises in both branches, ends with an unreached
  `Cast` of a null to that type, so the server gives it the annotated type.
* An operator whose operand type is known and is not a number is a compile error: arithmetic
  other than string and list `+`, ordering comparisons, `sum`, and `min`/`max` without a key.
  `&`, `|` and `^` take integers or bools. `str()` and an f-string take a string, a number or a
  bool, as the server names the CLR type of any other value. `==`, `!=` and `in` between
  operands of known types the server cannot compare, such as a bool and an int, are a compile
  error. So are an arithmetic operator, comparison or `in` between a `ulong` and a signed
  integer, which have no common type (a shift takes a count of any integer type), a computed
  tuple index, an index into a value that is not a string, list, dictionary or tuple, `in` on a
  value that is not a string or collection, `len` of bytes, `==`, `!=` or `in` between objects of
  different classes, `math.dist` of non-numeric coordinates, a dictionary key type the server
  rejects (keys are integers, bools or strings), a `typing.cast` to an unrelated type, a list or
  string index that is not an `int`, and a tuple of more than 7 values. Slicing or reversing a
  set, `len` of a number, and `sorted`, `min` or `max` of values Python cannot order (objects,
  enumeration values) are compile errors too. So are an unsupported method of a server side
  string or collection, and a return, break or continue leaving a `finally`.
* `is None` on a value that is not nullable is the constant `False` when the operand only reads
  names and constants. Otherwise the operand is evaluated, as it can have an effect or raise, and
  the result is `False`. The compiler's type for a value keeps the server's nullable flag at
  every position, since it decodes the result. A list literal, a conditional, the returns of a
  function and the assignments to a variable join their types, nullable wherever one of them is,
  and `Optional[T]` in an annotation is nullable. The values of a set and the keys of a
  dictionary are never nullable, as the server unwraps them. A bitwise operator on a nullable bool
  gives a bool. `len` of a tuple is its arity, with the tuple evaluated unless it only reads names
  and constants, and `x in (a, b)` compiles to equality tests
  against each element, with `x` evaluated once.
* A shift follows Python where the server follows C#: a count of at least the width gives 0, or -1
  for a negative value shifted right, and a negative count raises `ValueError`. The count keeps its
  own type, and the value widens to the common type of the two, or keeps its own when they have
  none.
* `None` passed to a nullable parameter is a null argument of the call. Anywhere else it is a
  `ConstantNull`, typed from its context: a conditional's other branch, a literal's other
  elements, the function's other returns, the variable's other assignments, an `Optional[T]`
  annotation on a variable or `->`, or `typing.cast(T, None)`. A `None` with no context is a
  compile error. A bare `return` in a function that returns a value is an error, as in mypy.
  An empty list, set or dictionary is typed from the same contexts, from a parameter and from
  the other operand of a binary operator, built as a `CreateEmptyList`, `CreateEmptySet` or
  `CreateEmptyDictionary`. `x in []` is `False`. `x in d` with a nullable key gives `False` for
  `None`, and a key of a wider numeric type than the dictionary's keys is compared with each key
  widened. An empty collection given the type of another kind of collection is an error naming
  the empty value to use, as is a parameter default of another kind.
* `typing.cast(T, value)` of any other value is a `Cast`, so it can narrow, such as a float to
  an `int`. It is the explicit form of the narrowing an assignment rejects. A cast to a type the
  value cannot convert to is a compile error.
* `raise` and `except` name an exception by its Python type in the exceptions table.
  `except ValueError` catches the three argument exceptions. `except RuntimeError` catches
  `InvalidOperationException` and every exception a service declares apart from `Error`, as the
  Python client raises a service exception as a `RuntimeError` subclass.
  `raise Exception(message)` throws `Error`, which `except RuntimeError` does not catch, as in
  Python. The message is the argument as `str()` gives it. A tuple in `except` gives one catch
  per exception, all recording the same clause. A tuple naming `Exception` catches every
  exception.
* Left as documented differences: integer overflow wraps, a server computed negative index or
  exponent, negative slice bounds, and `str()` of a float using the server's formatting. A float
  divided by zero gives `inf` or `nan`. A math function outside its domain gives `nan` or `inf`
  where Python raises, such as `math.sqrt(-1)`. `sum`, `min` and `max` skip a `None` among the
  values, and `sorted` puts it first, where Python raises `TypeError`. `sum` of floats adds in
  order, where CPython 3.12 and later compensate for rounding.
* Both compilers compile an enumeration value captured from the client to a `Cast` of an integer
  constant, so no compiler emits `ConstantEnum`. The value comes from the client's own
  enumeration, so it is a member.
* A name assigned anywhere in the function is local throughout it, as in Python. Reading it is a
  compile error unless every path to the read assigns it first (`krpc/definiteassignment.py`).
  The check is conservative, as C#'s is: an assignment in a loop or a `try` body does not count
  after it. Declaring the name up front would need its type, which only the assignment gives. A
  local function defined in a nested block is callable only inside it, since which branch's
  definition ran is known only at run time.
* Writing to or deleting an element of a captured collection is an error, as the server holds a
  copy. A valued function that can reach its end without a `return` is an error.
* An argument, element or field narrowing to an integer type is an error, as assignment is.
  A double narrows to a float with a `Cast`, since Python has one float type.
* `and`/`or` fold left to right and stop at a constant that decides the result, so a guard such as
  `d != 0 and x / d > 1` with `d` captured as 0 never folds the division. `set.discard` has no
  value.
* `del` removes a list element or a dictionary key. `raise` and `try`/`except`/`finally` map onto
  the exception nodes. A `try` with one `except` is one
  `TryCatch`. With several, the catches nest in the order written, and each catch only records
  which clause matched in a variable; the clauses then run after the catches, dispatched on that
  variable. So an exception raised by one clause is not caught by a later one, as in Python.

### C#

`Connection.Compile` translates a LINQ expression tree, which the compiler hands the client
for free from an `Expression<Func<TResult>>` lambda, into the same server tree. `AddEvent` accepts a
boolean lambda, `AddStream` compiles compound lambdas, and `Run` accepts
`Expression<Action>` lambdas so side-effecting functions can be written in the same style.

`Compile` has an `Expression<Action>` overload so a lambda with no result compiles to a reusable
object, and overloads for lambdas with parameters (see "Function arguments").

Beyond the operator set: a comparison with `null` maps onto `IsNull`, or folds to a constant when
the operand's `ReturnType` is not nullable, and a conversion between a value type and its nullable
form is left to the server; a `null` is a `ConstantNull` of its static type; `??`, `.HasValue`,
`.Value` and `GetValueOrDefault` on a nullable remote value compile to `IsNull` and `Conditional`,
with the value held in a variable; a lifted arithmetic, bitwise or shift operator is cast back to
its nullable type, since the server unwraps a nullable operand and throws on a null; `??` and
`GetValueOrDefault` cast the held value to the expression's type, so `int? ?? long` is a `long`;
a dictionary's `Keys` and `Values` map onto `DictionaryKeys` and `DictionaryValues`;
`System.Math` methods map onto `StdLib`, and `Console.WriteLine` onto
`StdLib.Print`, its arguments formatted as `string.Format` formats them, so a number computed on
the server needs an invariant `ToString` first;
string `+` and `ToString` become `StringConcat` and `ConvertToString`; the bitwise complement and
the LINQ operators `Skip`, `Take`, `SelectMany`, `ToDictionary`, `Distinct`, `Reverse`, `Zip`,
`Union`, `Intersect`, `Except`, `First`, `Last` and `ElementAt` are supported; captured collections
are folded into constants; and `.Length`, `.Substring`, `.ToUpperInvariant` and `.Contains`
dispatch onto the string operations by static type.

**Culture.** The server formats and compares strings with the invariant culture, so a call whose
result depends on the current culture is a `FunctionCompilationException`: `ToString`, a
concatenation or a format of a number computed on the server without
`CultureInfo.InvariantCulture`; `IndexOf`, `StartsWith` and `EndsWith` of a string without
`StringComparison.Ordinal`; `ToUpper` and `ToLower` without the invariant culture; and `OrderBy`
of a string key without `StringComparer.Ordinal`. A format specifier or alignment in a format
string is rejected too. A value the client computed is formatted on the client, as C# formats
it.

A lazy `IEnumerable<T>` result is wrapped in `ToList` and decoded as `IList<T>`. Only an
`IOrderedEnumerable<T>` result type is rejected, with a hint to call `ToList`.

A client side subtree is evaluated once, as a whole, at the outermost node that does not interact
with the server, so a side effect in it happens once. A delegate call in it is rejected, including a
call through `Invoke`. So is a call to a method, a constructor, a property getter or setter with a
body, or a user-defined operator or conversion, defined outside the .NET base library, the kRPC
client and the generated service stubs, as a remote call made inside it would run only then. Passing
the base library a delegate other than a lambda or a base-library method group, or a value whose
type implements a virtual method outside those assemblies, is rejected too, since the library can
call it. This covers a `ToString` override in a concatenation or format, and a user `IEnumerable<T>`
or `IComparer<T>` given to LINQ. So is reading `Lazy<T>.Value`. An auto-property, whose getter is
compiler generated, is folded, so a captured settings object can be read. A read of a `Stream<T>` is
rejected, since it would be evaluated once, and so are `AddStream` and `AddEvent` of a lambda that
makes no remote call, and a lambda with no value that makes none, which has no effect on the server.
A streamed lambda with parameters is rejected before a single call in it is streamed as that call.

`AddStream` streams a single call as that call only when its arguments make no remote call;
otherwise it compiles the lambda, so the arguments are evaluated on every update. The instance of a
single call is evaluated once, when the stream is created, even when it is itself a remote call, so
`vessel.Flight(frame).MeanAltitude` stays a procedure stream. A call of a `KRPC` service procedure
wrapped only in conversions is streamed as that call too, with the conversions made on the client,
since a function cannot call the `KRPC` service.

A tuple's `ItemN` maps onto `Get`, `Tuple.Create` onto `CreateTuple`, and a dictionary initializer
onto `CreateDictionary`. An error from the server while building the tree is raised as a
`FunctionCompilationException`, with the server's exception inside it.

Where C# semantics and the server differ, the compiler does the following:

* An explicit `null` argument is left out where the parameter's default is null, so the server
  takes its default, and is otherwise sent as a null argument. An expression tree cannot omit an
  optional argument.
* A comparison with a nullable number is a null test and the comparison, false on null as in C#.
  Arithmetic and logic on a null still throw.
* `Math.Round` takes any number of decimal places, where C# throws outside 0 to 15.
* `Math.Sign` of a float or double throws for a NaN, as C# does, where `StdLib.Sign` gives 0.
* A null new value in `Replace`, a null separator in `string.Join`, and a null element of the
  collection `string.Join` or `string.Concat` takes are empty strings, and `Trim` of a null array
  trims white space, as in C#.
* A local or lambda parameter of a reference type is nullable at its top level, as in C#.
* A result is decoded at the type the caller names, with the server's nullable flag at each
  reference-type position, which a C# type does not carry.
* `checked` arithmetic is rejected, since server integer arithmetic wraps. Integer `Math.Abs`,
  `Min`, `Max` and `Clamp` are `Conditional` on temporaries, exact at their own type.
* `List<T>.Contains`, `HashSet<T>.Contains` and an interpolated string with plain placeholders
  compile to `Contains` and `StringConcat`. A client side subtree with no case of its own is
  folded, and `&&`/`||` with a client side left operand short-circuit at compile time.
* A branch of a server side `?:`, or the right operand of a server side `&&` or `||`, that holds a
  client side sub-expression that fails to evaluate becomes a `Throw`, so the error is raised only
  when that operand is evaluated.
* `==` and `!=` on tuples and collections compare by content on the server, where C# compares
  references.
* A reference upcast, such as a set to `IEnumerable<T>` or `ICollection<T>`, leaves the value as
  it is. A `?:` choosing between a set and a list chooses between lists.
* A `checked` conversion between an enumeration and its underlying type, or a wider one, is
  allowed. `<`, `>`, `<=` and `>=` on structures are a `FunctionCompilationException`.
* `ToString` of an object computed on the server gives the server's class name, which can differ
  from the client's. A `double` converted to a string on the server is formatted by KSP's Mono,
  which can print fewer digits than a .NET Core client.
* An index out of range throws `IndexOutOfRangeException`, where C# throws
  `ArgumentOutOfRangeException`.

Four things are deliberately out of reach. `GroupBy` is not mapped, since the node's result type
differs from LINQ's. `Aggregate` is not mapped either; a fold over a collection is built with the
expression API's `Aggregate`. `MinBy`/`MaxBy` are not mapped: net472 has no `Enumerable.MinBy`, and
on a later framework the call is rejected as an unsupported collection operation. Exceptions are
unreachable in either direction, since an expression-tree lambda may neither contain a throw
expression nor have a statement body, which is consistent with that compiler being limited to
single-expression lambdas. For the same reason a `StateVariable` is reachable only through the raw
factory.

### Semantics that differ from running locally

Documented because they are the surprises: captured values are frozen at compile time, so only
remote calls re-evaluate per tick, which both client guides say; and a procedure that pauses
execution cannot be called inside a function, which the tutorial says.

**Short-circuiting is not one of them.** `And` and `Or` compile to LINQ's `And`/`Or`, which evaluate
both operands, and mapping `and`/`or` and `&&`/`||` onto them would silently drop the guard in
`x.Count > 0 and x[0] == 1`. `ConditionalAnd` and `ConditionalOr` compile to `AndAlso`/`OrElse`, so
both compilers map the conditional operators onto them and the bitwise ones onto `And`/`Or`. Python
chained comparisons need one more thing: `a < b < c` expands to two comparisons over one `b`, so a
non-constant `b` is assigned to a temporary in an enclosing block and read from it twice, which is
where python evaluates it once.

**Nor is the sign of a remainder.** `Modulo` is the CLR remainder, whose sign follows the dividend,
and python's follows the divisor. The Python compiler takes `r = a % b` and adds `b` when `r` is
nonzero and its sign differs from `b`'s, holding `r` and `b` in temporaries, so `-30 % 360` is 330
on the server as it is locally. Adding `b` only when needed keeps `0.1 % 360` exact and an `int`
remainder in range. The C# compiler maps `%` straight onto `Modulo`, which is C#'s own
semantics.

**A repeated key in C#'s `ToDictionary` takes the last of its values.** It compiles to
`BuildDictionary`, where C# itself throws. The C# guide says so.

## Object identity and lifetime

Every object a factory returns becomes an entry in the object store, and the store collapses
duplicates: `AddInstance` looks the instance up in a `Dictionary<object, ulong>` before allocating
an id, using the default comparer, so any class overriding `Equals`/`GetHashCode` is deduplicated
automatically. That is what `Equatable<T>` (`core/src/Utils/Equatable.cs`) exists for.

Nothing in the store is released except by the sweep described below: `RemoveInstance` is called
only by that sweep, and `ObjectStore.Clear()` runs only once the last server stops. A function that
asks for `Type.Double()` five hundred times must therefore not leave five hundred entries
describing a single type.

Types and value constants are shared. Interior nodes are not, and the last two subsections say why
that is enough.

A client can still share a node by passing it to several factories, and the Python compiler reuses
one `Lambda` for each call of a local function. LINQ compiles a shared node once per use, so a
chain of steps that each use the step before twice doubles the compiled size at every step.
Thirty such steps hang the game for hours, since compiling runs on the main thread and cannot be
cancelled.

The visitors that check, bind and rewrite a function therefore throw past `MaxNodes`, 1,000,000
nodes counted per use. That many compiled in 1.4 s in the core tests under .NET. `AddEvent`,
`RunFunction` and `AddFunctionStream` also count the nodes before compiling, through
`Expression.Check`, which checks the markers and scopes in the same pass.

The bound only stops the blowup. A program built from distinct nodes needs a million RPCs to reach
it. Compiling each shared node once would make the work grow with the distinct nodes, and remove
the bound. It is a follow-up, designed in [`shared-nodes.md`](shared-nodes.md).

A function itself is never released either, nor its delegate or the constants interned for it. A
client that builds a new function per call, such as `run(lambda)` in a loop, grows the
store without bound. The tutorial says to compile once and reuse the function. A release procedure
and client-side caching of compiled lambdas are a follow-up, designed in
[`function-release.md`](function-release.md).

### Types

`Type` derives from `Equatable<Type>`, comparing its spec: the CLR type and the nullable flag at
every position. It is an immutable description of a
type with no per-client state, so value equality is the correct semantics and sharing a single
instance between clients is safe. No protocol or client change is involved.

Composite types collapse for free: the CLR interns constructed generic types, so `MakeGenericType`
returns the same `System.Type` for the same arguments, and the spec compares structurally, so
`ListType(Double())` reduces to one id provided the nested `Double()` did. `Equatable<T>` brings
`operator ==`/`!=` with it, so `== null` comparisons on a `KRPC.Type` change path; they stay
correct, since those operators are null-safe, and the code that builds trees compares with
`ReferenceEquals` throughout in any case.

The client half matters as much as the server half, because each factory call is also a round trip
([`batched-tree-construction.md`](batched-tree-construction.md)).
The Python compiler shares one cache of the objects naming each type across every function compiled
for a connection, so a type is named to the server once rather than once per mention. The casts
the compiler inserts for `/`, a float `//`, a negative constant exponent, `round`, `int()` and
`float()` are the exception: they call
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
consulted by every value constant factory and `ConstantEnum`. `ConstantNull` interns through a
second dictionary keyed on the `TypeSpec`, since two specs can share a CLR type.
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
server guessing from liveness. The explicit release is designed in
[`function-release.md`](function-release.md).

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
it. [`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md) fixes it by removing stream deduplication, for function streams too.

**What deduplication does not bound.** Interior nodes, every operator, call, block and lambda, are
not deduplicated, and they are the population that actually grows: one compile of a moderate
function is hundreds of permanent entries, and a program that recompiles inside a loop, or
repeatedly creates function streams, grows without limit. The sweep does not reach them either, and
for the reasons above should not be made to. This is close to a pre-existing property of the object
store rather than something the function work introduces, since every `Vessel` and `Part` ever
encoded is pinned the same way, which is what #771 and #1051 are about, and it is left alone here.

## Interaction with planned protocol work ([#906](https://github.com/krpc/krpc/issues/906))

* **#877 stream invalidation and #902 stream refcounting** are designed in [`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md), which lands
  before this work. Function streams and events follow its model: each add is a new stream, they end with a
  final error result, and they are held while the game is between states.
* **#903 reverse streams and batched calls** is independent of the tree-construction round trips,
  per [`batched-tree-construction.md`](batched-tree-construction.md). The overlap is elsewhere: the
  expression registry, storing server-side state and evaluating it per tick, is the same machinery
  reverse streams cite as prior art.
* **#902** is unrelated to deduplicating types and constants, despite the surface similarity; see
  "No refcounting for these".
* **#904 deprecation**: individual expression operators can be evolved or deprecated through the
  standard mechanism, since they are ordinary service members.

## Testing

* The `ExpressionTest` partial files in `core/test/Service/KRPC/`: promotion cases for every
  binary operator; `Call` and `CallWithArguments` against the scanned core `TestService`, with
  `ConstantObject`, class-typed `Parameter`, per-element `Any`/`Select` over real RPC calls, error
  propagation and `ReturnType` on every node kind; the statement nodes, covering block scoping,
  loops with `Break`/`Continue`, early `Return` and imperative collection construction; and the
  tuple, collection, string and exception operations.
* `TypeTest` for the factories and introspection, and `StdLibTest` for the scalar, vector and
  quaternion operations.
* Stream behavior (value change detection, error capture, a yield reported as an error) alongside
  the existing core stream tests.
* `TypeTest` and `ExpressionTest` also cover object identity: two equal factory calls yield the same
  object id, and types and constants differing only in type (`Int` versus `Long`, `ConstantInt(1)`
  versus `ConstantDouble(1.0)`) do not collide. `ObjectStoreTest` covers the equality path itself.
* Python integration tests against TestServer, part of `//:test`: computed streams end-to-end
  (value, collection and object results, and server-reported type decode), per-element call events,
  object constants, mixed-type arithmetic events, error surfacing, and `run` covering
  results, side effects and the void case.
* C#, Java and C++ client tests for the typed stream and run-once helpers, following each client's
  existing event and stream test structure.
* `test_mapped_exceptions` in the Python and C++ client tests, `MappedExceptions` in the C#
  `ConnectionTest` and `testMappedExceptions` in the Java `ConnectionTest`: each mapped kRPC
  exception reaches the client as its built-in or generated type.
* Compiler tests per client covering the accepted language subset and the diagnostics raised for
  unsupported constructs.
* `service/SpaceCenter/test/test_server_side_functions.py`, in the in-game suite, against a vessel
  on the launchpad: reading the game state, a single tick shared by every call, comprehensions and
  loops over the vessel's parts, side effects, a function compiled in advance and one taking
  arguments, `StdLib` on the game's vectors, a function stream, a state variable kept across
  stream updates, an event, a compiled handler catching a service exception, the unnamed error
  from a procedure unavailable in the scene, and the error a yielding procedure produces.

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

A deterministic tree printer (`core/src/Service/KRPC/ExpressionTreePrinter.cs`) prints one
indented `NodeType<Type> detail` line per node. Parameters, variables, state variables and labels
get sequential ids, and a name that is not an identifier is quoted. Block variables print with
their type, as in `(x#0: System.Int32)`, and a binary or unary node prints its operator method.
Numbers use invariant round-trip formatting. Collection, tuple and structure constants print value
by value, a type prints as `typeof(...)` and a procedure as its name. Any other object constant
prints as its type name only, so no run-to-run identity leaks. A node kind or part of a tree the
printer does not render, such as a catch filter, throws.

A test-only `DumpExpressionTree(Expression)` RPC on TestServer's `TestService` exposes the printer.
It checks the function first, so the node limit bounds the output. Three golden suites compare
dumps against expected strings, verifying the exact trees the API generates without depending on
the brittle compiled IL:

* `core/test/Service/KRPC/ExpressionTreePrinterTest.cs`, the factory API: direct-call emission
  (scene check, and null-return check only for non-nullable reference returns), numeric promotion
  `Convert` insertion, `While`/`ForEach` desugaring over lists and sets, marker-to-goto rewriting,
  label binding of early returns, state variables, catch and catch-all blocks, structures,
  `Invoke`, constants, negative zero, type spec constants, a type nested in a generic type and
  string escaping, `Set`, `Conditional`, `ConstantNull` and `CallWithArguments`, operator methods,
  quoted names, and the error for a node kind or part the printer does not render.
* `client/python/krpc/test/test_expressiontree.py`, Python compiler output end-to-end in both stub
  modes: getter null-check blocks, true-division converts, `math.sqrt` to `StdLib.Sqrt`, statement
  functions as `Invoke(Lambda)`, loops with declared variables, void setter functions, and
  comprehensions as `Select` plus `ToList` with per-element narrowing converts.
* `client/csharp/test/ExpressionTreeTest.cs`, C# LINQ compiler output: `Math.Sqrt` mapping, folded
  captured collections, string `+` to `String.Concat`, and ternary conditionals.

Sets built on the client are excluded from the Python and C# goldens, since their iteration order
is nondeterministic. A set built on the server enumerates in insertion order, so the core suite
has one. Generated C++ service headers do not include cross-service headers. The C++ test sources
and `client/cpp/benchmark/benchmark.cpp` therefore include `krpc/services/krpc.hpp` before
`services/test_service.hpp` for the new RPC's `KRPC::Expression` parameter, and
`client/cnano/benchmark/benchmark.c` includes `krpc_cnano/services/krpc.h` before
`services/test_service.h`.

## Phases

The phases in [`stream-and-event-improvements.md`](../protocol/stream-and-event-improvements.md) land first, so the stack starts from their stream and event
machinery. The first phase removes the v0.6.0 `Expression`, `Type` and `AddEvent`, so each later phase is an
addition reviewed on its own. The stack's net change against v0.6.0 is the design above, and the
breaking changes it lists are relative to v0.6.0. The phases are grouped into 7 PRs. Each phase
is a commit, and each PR that changes what a user sees ends with one commit holding its changelog
entries. Each phase builds and passes `//:test` on its own.

| PR | Phase | Content |
| --- | --- | --- |
| `core` | 0 | Remove the v0.6.0 server side expression API. The sub-orbital tutorial polls until phase 2 restores events |
| `core` | 1 | `KRPC.Type`: class, enumeration, structure, collection and nullable types of any kind, the `Long`, `UInt`, `ULong` and `Bytes` types, `KRPC.TypeCode`, and the `Code`, `Service`, `Name`, `Types` and `Nullable` properties |
| `core` | 2 | `KRPC.Expression` core: the spec each node carries and the null check where a nullable value meets a position that is not, `KRPC.NullReferenceException` and its client mappings, constants including `ConstantNull`, numeric promotion, comparisons, content equality, logic, casts, conditionals, `IsNull`, lambdas and `Invoke`, calls compiled to direct method calls and `CallWithArguments`, `ReturnType` and `HasReturnType`, the node limit, and `AddEvent`, with which the client guides' event sections return |
| `core` | 3 | `KRPC.RunFunction` with arguments, `KRPC.AddFunctionStream`, `KRPC.CompileFunction` and `Expression.ParameterTypes` |
| `core` | 4 | Building tuples, structures and collections, and `GetField` |
| `core` | 5 | Collection and dictionary operations, `KRPC.KeyNotFoundException` and `KRPC.IndexOutOfRangeException` with their client mappings |
| `core` | 6 | Statements and control flow: variables, blocks, loops, `Break`, `Continue`, `Return`, `StateVariable` |
| `core` | 7 | Collection mutation: `Append`, `Set`, `Remove`, `RemoveAt`, `Clear` |
| `core` | 8 | String operations |
| `core` | 9 | Exceptions: `Throw`, `TryCatch`, `TryCatchAll`, `TryFinally`, and `KRPC.DivideByZeroException`, `NotSupportedException`, `TimeoutException`, `OverflowException` and `Error` with their client mappings |
| `stdlib` | 10 | The `StdLib` service |
| `tree-printer` | 11 | `ExpressionTreePrinter` and the TestServer `DumpExpressionTree` RPC |
| `python` | 12 | Python `run` with arguments, `add_stream` and `stream` over functions, and `add_event`, all over hand-built trees |
| `python` | 13 | Python compiler, lambdas, and `None` typed from its context |
| `python` | 14 | Python compiler, functions with statements and parameters, and `nonlocal` state variables |
| `csharp` | 15 | C# compiler including lambdas with parameters, `Run` with arguments, `AddEvent` and the `AddStream` overloads |
| `java-cpp` | 16 | Java `run` with arguments, `addStream` and `addEvent` helpers, and a public `RemoteObject.id` |
| `java-cpp` | 17 | C++ `run` with arguments, `add_stream` and `add_event` helpers |
| `docs` | 18 | The tutorial, the events and run-once functions in five other tutorials, the client guide links, and the in-game tests |

The golden tree tests for each compiler land with that compiler.

## Out of scope

* Java and C++ native-syntax compilers. Neither language exposes its own syntax tree to the client,
  so there is no equivalent of the Python source or C# LINQ route; both keep the run-once and stream
  helpers over hand-built trees.
* Batched tree construction, designed in
  [`batched-tree-construction.md`](batched-tree-construction.md); client-side only, and gated on
  measuring real tree sizes first.
* `nonlocal` in a nested local function, meaning a local of the compiled function. It is
  ordinary scoping in the compiler, with no server change. `global` stays unsupported.
* Declaring exception types in a function. A function throws one a service declares.
* Bounding the time a loop can run for, so that a runaway function cannot hang the game.
* Deferred calls and resumable functions, designed in
  [`yielding-procedures.md`](yielding-procedures.md).
* Compiling a shared node once, which would remove `MaxNodes`, designed in
  [`shared-nodes.md`](shared-nodes.md).
* Releasing functions and caching compiled lambdas, designed in
  [`function-release.md`](function-release.md).
* Calling arbitrary CLR members from a function, sketched in
  [server-side-arbitrary-expressions.md](server-side-arbitrary-expressions.md).
