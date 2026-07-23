# Server-side functions: completing the feature

**Status:** in progress — implemented but not yet merged; umbrella issue [#679](https://github.com/krpc/krpc/issues/679).

The feature is named "server side functions"
throughout the user-facing API and documentation, and the service class is named to match: the
`KRPC.Expression` class is renamed to `KRPC.Function`, so the thing a client builds and the thing
the feature is called are the same word. A function is the whole program the client assembles —
statements, control flow and side effects included — rather than only a tree that computes a
value, which is what the old name implied and what the node algebra has outgrown. The feature was
experimental, so the rename is breaking and no compatibility shim is kept.

This frees `Function` as a factory name, so the node that builds a lambda is named for what it
actually constructs: `Expression.Function(parameters, body)` becomes `Function.Lambda(parameters,
body)`. Everything named after the class follows it (`AddFunctionStream`, `FunctionStream`,
`CompileFunction`, `krpc/functioncompiler.py`, …). "Expression" survives only as ordinary English
for a node in value position, and in the LINQ type names the implementation is built on.

Issue [#679](https://github.com/krpc/krpc/issues/679) (umbrella), with linked issues
[#517](https://github.com/krpc/krpc/issues/517) (per-element calls in predicates),
[#503](https://github.com/krpc/krpc/issues/503) (object constants),
[#521](https://github.com/krpc/krpc/issues/521) (multiplication/mixed-type arithmetic),
[#608](https://github.com/krpc/krpc/issues/608) (documentation).

## Goals

Server-side functions should let a client do *almost* anything on the server that it can do
locally:

1. Run a complex computation over multiple RPC results on the server, triggered/evaluated in a
   single physics tick, without network round trips (custom events, and — new — computed streams).
2. Stream the result of a computation out of the server (efficient telemetry), not just the result
   of a single RPC.
3. Run a whole function on the server once, within a single physics tick, for its result and its
   side effects — the case that events and streams cannot serve because they re-evaluate on every
   update.
4. Let clients write all of this in their own language rather than by hand-assembling trees.

This means: calling RPCs (including per-element inside collection operations), passing object
references around, arithmetic/comparisons/logic over mixed numeric types, collection processing,
statements and control flow, and returning any serializable kRPC value to the client.

## Approach decision

Three architectures were considered:

* **Extend the existing remote expression-tree API** (chosen). `KRPC.Function` /`KRPC.Type` are
  ordinary kRPC remote classes whose static factory RPCs build a `System.Linq.Expressions` tree
  server-side; `AddEvent` compiles it with `.Compile()` (real JIT, native speed, already proven
  under KSP's Mono). This is the LINQ-provider pattern: a language-neutral tree assembled via
  RPCs, so every client works in its own language; no protocol changes are needed; and the node
  algebra is a whitelist (safer than arbitrary code). Client-side compilers map each language's
  native syntax onto the same factories, so the tree is an intermediate representation rather
  than something users assemble by hand (see "Client-side compilation").
* **JIT-compile user-supplied C# (Roslyn)** — rejected. Non-C# clients would have to write C#
  source strings (a Python client writing C# is a bad fit), Roslyn is a very large dependency to
  ship inside a game mod, and arbitrary code is strictly less safe than a node algebra.
* **Embedded scripting language (MoonSharp Lua, the kOS model)** — rejected. Every client would
  write a second language rather than none of them; requires an auto-generated Lua binding for the
  whole service surface; per-tick interpreter overhead where compiled LINQ delegates are free.

## Limitations at the outset (root causes)

The state of the feature before this work, which the design below addresses:

* `Function.Call` (`core/src/Service/KRPC/Function.cs`) decodes the embedded `ProcedureCall`'s
  arguments at build time and bakes the instance and argument values in as
  `LinqExpression.Constant` nodes. A call therefore always re-invokes the same object with the
  same arguments — it can never be applied to a lambda parameter (`Select`/`Where`/`Any`/`All`
  per-element calls, #517), and call arguments cannot be computed sub-expressions.
* `Call` reads `ProcedureResult.Value` without checking `HasError`: `Services.ExecuteCall`
  converts exceptions into an error result, so a failing RPC inside an expression surfaces as a
  confusing null-conversion crash rather than the RPC's error.
* `KRPC.Type` has only five factories (double/float/int/bool/string). No class, enumeration or
  collection types can be named, so lambda parameters cannot have object types and `Cast` cannot
  target them ([#503](https://github.com/krpc/krpc/issues/503), [#517](https://github.com/krpc/krpc/issues/517)).
* Constants exist only for the five primitive types — an object reference (e.g. a
  `ReferenceFrame` to pass to a positional RPC) cannot appear as an expression argument ([#503](https://github.com/krpc/krpc/issues/503)).
* No numeric promotion: LINQ expression trees require exact operand type matches, so
  `int * double` throws (server half of #521).
* Expressions feed only `AddEvent` (must be bool-typed). There is no way to stream a computed
  value — goal 2 is impossible today.
* `EventStream.UpdateInternal` has no exception handling: a throwing predicate propagates out of
  the per-frame stream update loop (see also the #877 stream-invalidation design, which builds on
  top of per-stream error results).
* No conceptual documentation or examples ([#608](https://github.com/krpc/krpc/issues/608)).

## Design

No protocol (`krpc.proto`) changes. Everything below is additive service API surface plus client
library helpers, so it stays within the current protocol and composes with the planned #906
protocol improvements (see "Interaction with planned work").

### 1. Numeric promotion in binary operators

`Add`, `Subtract`, `Multiply`, `Divide`, `Modulo`, and the numeric comparisons (`Equal`,
`NotEqual`, `GreaterThan(OrEqual)`, `LessThan(OrEqual)`) apply C#'s standard binary numeric
promotion before building the LINQ node: if either operand is `double` → both to `double`; else
`float` → `float`; else `ulong` → `ulong` (error if the other side is a signed type that cannot
be implicitly converted); else `long` → `long`; else `uint` + `int` → `long`; else `uint` →
`uint`; else `int`. Promotion only applies when both operand types are numeric and differ.
`Power` already converts to double. Explicit `Cast` remains available. This fixes the server half
of #521 (`Multiply(ConstantDouble, ConstantInt)` etc.).

### 2. `KRPC.Type` expansion + introspection

New factories (names chosen to avoid `class`/`list` etc. keyword collisions in generated clients):

* `ClassType(string service, string name)` — a service-defined class type.
* `EnumerationType(string service, string name)` — a service-defined enumeration type.
* `TupleType(IList<Type> valueTypes)`, `ListType(Type valueType)`, `SetType(Type valueType)`,
  `DictionaryType(Type keyType, Type valueType)` — collection types.
* Value factories completing the wire-type set: `Long()`, `ULong()`, `UInt()`, `Bytes()`
  (existing: `Double`, `Float`, `Int`, `Bool`, `String`).

Class/enum name resolution: the scanner already has the CLR `System.Type` in hand when it builds
`ClassSignature`/`EnumerationSignature`; store it there as a non-serialized `UnderlyingType`
property (does not affect the service-definitions JSON, which serializes via `GetObjectData`).
`Type.ClassType` then resolves via `Services.Instance.Signatures[service].Classes[name]`.

Introspection (the "server reports type" half, used by dynamic clients to decode computed
streams):

* New `[KRPCEnum] TypeCode` in the KRPC service mirroring the protocol's type codes: `Double`,
  `Float`, `SInt32`, `SInt64`, `UInt32`, `UInt64`, `Bool`, `String`, `Bytes`, `Class`,
  `Enumeration`, `Tuple`, `List`, `Set`, `Dictionary`.
* Instance properties on `Type`: `Code` (TypeCode), `Service` (string; empty unless
  class/enumeration), `Name` (string; empty unless class/enumeration), `Types`
  (`IList<Type>`; generic arguments, empty otherwise).
* `Function.ReturnType` (property) — the `Type` an expression evaluates to. Throws for types
  that cannot be returned to a client (e.g. the lazy `IEnumerable<T>` produced by
  `Select`/`Where`; the fix is to wrap in `ToList`/`ToSet`, and the error message says so).

A dynamic client walks `ReturnType` recursively, reconstructs the equivalent protobuf `Type`
message locally, and feeds its existing decode machinery (`Types.as_type` in Python). Statically
typed clients don't need this — the user supplies the expected type as a generic parameter.

### 3. Object constants ([#503](https://github.com/krpc/krpc/issues/503))

`Function.ConstantObject(ulong value)` — a constant object reference, passed as its object
identifier (the same `uint64` the protocol already uses to encode class instances; `0` is null,
which is rejected here). The server recovers the instance via `ObjectStore.GetInstance(id)` and
uses its most-derived `KRPCClass` type as the node's static type — so no protocol change and no
self-describing wire value is needed, which is what blocked [#503](https://github.com/krpc/krpc/issues/503) originally. Clients already
expose the identifier (`RemoteObject.id` in C#, `_object_id` in Python, `Object::_id` in C++,
`RemoteObject.id` in Java).

`ConstantEnum` is not added: `Cast(ConstantInt(value), Type.EnumerationType(...))` covers it and
is documented.

> [!IMPORTANT]
> We should add `ConstantEnum` as this is cleaner API than using a cast.

### 4. Expression-valued calls (#517)

`Function.CallWithArguments(ProcedureCall call, IList<Function> arguments)` — like `Call`,
but the elements of `arguments` supply the call's arguments *by position* as sub-expressions
(position 0 is the instance for class members). Positions not covered by the list (or covered by
a null entry) fall back to the argument encoded in `call`, then to the parameter's default value.
Each expression's static type must be assignable to the parameter's CLR type (checked at build
time). This makes per-element calls work:

> [!IMPORTANT]
> Do we need the old `Call`? That is for calling a procedure from it's serialized arguments,
> to allow a procedure call compiled by the client to be called. We could just substitute with the
> the single `CallWithArguments` form

```
param    = Function.Parameter("e", Type.ClassType("SpaceCenter", "Engine"))
hasFuel  = CallWithArguments(get_call(any_engine.has_fuel), [param])
predicate= Function.Lambda([param], Function.Not(hasFuel))
anyOut   = Function.Any(Function.Call(get_call(parts.engines)), ...)
```
> [!IMPORTANT]
> `Function.Not(...)` is confusing. We should maybe use an alias such as:
>
> ```
> builder = conn.Function
> builder.Not(...)
> ```
>
> or even reconsider the name of this service, calling it something like `FunctionBuilder`

(The client builds the template `ProcedureCall` from any convenient instance — only the procedure
identity is used for overridden positions.)

Implementation: both `Call` and `CallWithArguments` compile to a **direct, statically typed
`LinqExpression.Call` of the procedure's underlying `MethodInfo`** (now exposed as
`IProcedureHandler.Method` by all three handler types — property accessors are wrapped via
their getter/setter `MethodInfo`, so every RPC is inlinable). Arguments are typed
sub-expressions or typed constants — no `object[]` allocation, no boxing, and the .NET JIT can
inline the target (e.g. `StdLib.Sqrt` inlines down to `Math.Sqrt`; measured 38.4 → 7.8 ns/call
with gen-0 collections eliminated, which matters under Unity's Boehm GC). Semantics match an
ordinary RPC exactly via two lean static helpers emitted around the call:

* `Services.CheckFunctionGameScene(procedure)` before every invocation (same scene-mask
  check and `RPCException` as the ordinary dispatch path);
* `Services.CheckFunctionReturnValue(procedure, value)` after invocation, emitted only for
  reference-typed returns where null is not permitted (a direct typed call can only violate
  the declared return type by returning null, so the per-evaluation `IsInstanceOfType`
  reflection check of the boxed dispatch path is provably unnecessary);
* RPC errors are thrown as exceptions so they propagate to the stream/event evaluating the
  expression (fixes the silent null-conversion crash in the pre-#679 `Call`);
* `YieldException` propagates — stream/event updates catch it and skip the tick (the
  continuation is dropped; a procedure that yields repeatedly never produces a value and is
  documented as unsupported inside expressions).

`Call(call)` keeps its exact current signature and "arguments fixed at build time" semantics
(they become constant sub-expressions on the shared path).

### 5. Computed streams (goal 2) + event error hardening

> [!IMPORTANT]
> Can we unify these into a single `AddStream` function?

* New `KRPC.AddFunctionStream(Function function, bool start = true)` returning a `Stream`
  message, symmetric with `AddStream`. Validates at creation time that the expression's type is a
  serializable kRPC type (`TypeUtils.IsAValidType` on the expression's static type, with an error
  message pointing at `ToList`/`ToSet` for lazy enumerables).
* New `FunctionStream : Stream` in `core/src/Service/`: compiles
  `Lambda<Func<object>>(Convert(expr, object))` once; `UpdateInternal` evaluates it, with
  `YieldException` → skip tick, any other exception → `Result.Error` (mirroring
  `ProcedureCallStream`'s behavior, including value-change detection via `ValueUtils.Equal` so
  unchanged values are not resent). The runtime-typed `Encoder.Encode` already serializes the
  boxed result correctly — no server-side type routing is needed.
* `EventStream.UpdateInternal` gets the same try/catch: predicate errors become a stream error
  result (surfaced by existing client stream machinery as a raised exception) instead of
  propagating out of the per-frame update loop and starving every stream. `AddEvent` also gains a
  friendly "expression must be of type bool" error.

### 6. Statements, control flow and side effects

The node algebra is extended from "compute a value" to "run a function", so that a client can
express anything it could write in a loop locally. LINQ expression trees already support all of
this; the work is exposing it as factories with kRPC-shaped semantics:

* Local state: `Variable(name, type)` declares one, `Assign(variable, value)` writes it, and
  `BlockWithVariables(variables, expressions)` scopes them. `Block(expressions)` is the
  no-declaration form; a block evaluates to its last expression.
* Control flow: `IfThen`/`IfThenElse`, `While(condition, body)` and `ForEach(variable,
  collection, body)`, with `Break()` and `Continue()` inside loops. `While` and `ForEach` are
  desugared into LINQ's loop/label primitives; `Break`/`Continue` are emitted as calls to marker
  methods and rewritten to `goto` against the enclosing loop's labels when the loop node is built.
  Binding to the nearest enclosing loop falls out of trees being built innermost-first.
* Early exit: `Return(value)`/`ReturnNothing()` are likewise markers, bound to a label wrapped
  around the function body by `Function`, so a return anywhere in a nested block leaves the whole
  function.
* Side effects: calls to procedures with no return value (including property setters) are
  ordinary statement expressions, and collections can be built imperatively —
  `CreateEmptyList`/`CreateEmptySet`/`CreateEmptyDictionary` plus `ListAdd`, `ListSet`, `SetAdd`
  and `DictionarySet`.

Void-typed nodes are the reason several things below are special-cased: an expression whose type
is `void` has no return type to report, cannot be streamed, and is only meaningful under
`RunFunction`.

### 7. Run-once functions

Events and streams re-evaluate their expression on every update, which makes them the wrong home
for a function with side effects — it would re-run every tick. `KRPC.RunFunction(Function)`
compiles the expression, invokes it exactly once inside the calling tick, and returns its result.

> [!IMPORTANT]
> Says that `RunFunction` compiles and runs the function. The function should already be compiled,
> so we don't pay the compilation cost on every call. Functions can be eagerly compiled when created.

The return value is a `bytes` payload rather than a typed value: the procedure's declared return
type cannot depend on the expression, so the server encodes the value with the runtime-typed
`Encoder.Encode` and the client decodes it using `Function.ReturnType` (dynamic clients) or a
user-supplied type parameter (static clients). A void-typed function returns an empty payload.

`YieldException` is turned into a plain error: a procedure that pauses and resumes on a later
tick cannot be honored by a call that must complete within this one, so this is reported rather
than silently dropping the continuation as the stream path does.

### 8. The StdLib service

Expressions can only call RPCs, so any arithmetic beyond the operator nodes would have meant a
round trip — `math.sqrt` on a streamed value is not expressible otherwise. `StdLib` is a new
core service supplying the missing primitives as ordinary RPCs:

* scalars: `Abs`, `Sqrt`, `Exp`, `Log`, `Floor`, `Ceiling`, `Round`, `Sign`, `Clamp`, `Min`,
  `Max`, the trigonometric functions (`Sin`/`Cos`/`Tan`/`Asin`/`Acos`/`Atan`) and
  `DegreesToRadians`/`RadiansToDegrees` (exponentiation is already the `Power` operator node);
* vectors and quaternions over the tuple types the SpaceCenter service already uses:
  `VectorAdd`/`Subtract`/`Scale`/`Dot`/`Cross`/`Magnitude`/`Normalize`/`Distance`/`Angle`/`Lerp`,
  and `QuaternionMultiply`/`Inverse`/`Angle`/`Slerp`/`FromAxisAngle`/`RotateVector`.

These exist to be called from inside functions, and are what the client compilers target when
they see `math.sqrt` (Python) or `System.Math.Sqrt` (C#). Because calls compile to direct typed
invocations of the underlying method, the JIT inlines them — `StdLib.Sqrt` reduces to
`Math.Sqrt`, so the indirection costs nothing at evaluation time.

### 9. Client libraries

Expression building needs no client work (the factories are ordinary generated/dynamic service
stubs). Running an expression as a stream or as a one-shot function needs a small helper per
client, in each case decoding a value whose type the server reports rather than the stub declares:

* **Python** (dynamic): `Client.add_function_stream(expression)` and the
  `Client.function_stream(...)` context manager — call the RPC, walk `function.return_type` to
  rebuild the protobuf `Type`, and wrap the stream id with `Stream.from_stream_id(client, id,
  types.as_type(...))` (all existing machinery). `Client.run_function(expression)` decodes the
  `RunFunction` payload the same way, returning `None` for a void function.
* **C#**: `Connection.AddStream<T>(Services.KRPC.Function expression)` and
  `Connection.RunFunction<T>(...)` overloads — the user supplies `T`; a non-generic
  `RunFunction` overload covers functions with no result.
* **Java** / **C++**: equivalent typed helpers matching each client's existing
  stream-construction idiom, plus their own run-once helpers.
* **Lua**: no helper (raw RPCs remain available); documented.

### 10. Documentation (#608)

* A new conceptual/tutorial page (`doc/src/tutorials/server-side-functions.rst`) covering: what
  server side functions are and when to use them; custom events; computed streams; run-once
  functions and side effects; `Parameter`/`Lambda`/`Invoke` (how named parameters bind);
  `Select` vs `Where`; per-element RPC calls; object constants; type promotion and `Cast`;
  errors and the yield limitation. Examples in all client languages following the existing doc
  example conventions.
* Reference documentation for the `StdLib` service and for each client's compiler: what subset
  of the language is accepted, and the semantics that differ from running the code locally.
* Improved XML doc summaries on every `Function`/`Type` member (these feed the generated API
  reference in all languages).

## Error handling

Constructing an invalid program fails in one of three places, in increasing order of how far the
mistake travels before it is reported:

1. **In the client compiler**, before any RPC is sent, for constructs the compiler does not accept
   (`FunctionCompilationError` in python, `FunctionCompilationException` in C#). These name the
   offending source construct.
2. **At tree construction**, which is where the majority of errors are caught and is the main
   ergonomic benefit of one RPC per node: the factory call that builds the bad node is the call
   that fails, so the error is localized to the node the client got wrong rather than to the tree
   as a whole. Operand types with no implicit conversion, an argument whose type does not match the
   procedure parameter, an assignment to something that is not a variable, an empty block, a
   `Return` whose type does not match the function's result type.
3. **At use**, when the tree is finally compiled: `AddEvent` requires a bool-typed expression, and
   `AddFunctionStream`/`RunFunction` require a serializable return type via
   `GetValidReturnType()`. Anything the node algebra did not check falls through to LINQ's own
   validation in `Compile()`, whose messages are not written for kRPC users.

**Known gap: unbound `Break`/`Continue` are deferred to evaluation.** The marker methods are only
rewritten when a loop node is built, and nothing checks for markers left unbound afterwards —
`Lambda()` binds the return target but passes null break/continue targets. A `Break` with no
enclosing loop therefore compiles successfully and throws
`InvalidOperationException("break used outside of a loop")` when the function runs. For a stream
that means an error on every update rather than one failure at creation. `Return` does not have
this problem, since it is bound and type-checked at `Lambda()` build time.

The fix is a check for residual marker calls, which has to run at each point the tree is compiled
rather than only in `Function()` — a block can be handed straight to `RunFunction` without a
`Lambda()` wrapper.

## Yielding procedures inside a function

Some procedures cannot finish within the tick they are called in. They signal this by throwing
`YieldException`, which carries a delegate that resumes the work. `ProcedureCallContinuation.Run`
catches it and rethrows a continuation wrapping `e.CallUntyped()`; the core parks that in
`rpcYieldedContinuations` and calls it again on each update until it completes. The client never
sees any of this — its call simply takes several ticks.

These are not obscure procedures. `Control.ActivateNextStage`, `SpaceCenter.WarpTo`,
`SpaceCenter.LaunchVessel`, `Part.Separate`, `AutoPilot.Wait` and vessel switching all yield, which
is to say the actions people most want a function to perform are exactly the ones that do this.

### What happens today

* `RunFunction` catches `YieldException` and converts it into an error saying a procedure that
  pauses execution cannot be used.
* A stream or event catches it and skips the update. The expression is evaluated again from
  scratch on the next update, and the procedure's continuation is discarded.

### Why the yield cannot simply be honored

The continuation resumes *the procedure*, not its caller. Everything the function was doing around
that call — loop counters, local variables, half-built collections, which statement of a block it
had reached — lives on the .NET stack of a compiled delegate, and is destroyed as the exception
unwinds. There is no expression-level continuation to park, so there is nothing for the core's
existing retry machinery to resume.

### The problem this now creates

Re-evaluating from scratch used to be merely wasteful: expressions were pure, so recomputing them
produced the same answer. Functions can now have side effects, and a retry repeats them. A function
that stages, then waits on the result of staging, re-stages on every update for as long as the call
keeps yielding. This is silent and destructive, and it is a consequence of adding side effects
rather than a pre-existing quirk — which makes it the part of this section that needs resolving
regardless of which direction is taken.

### The real question is atomicity, not mechanism

`RunFunction` exists to run a whole function inside one physics tick. Honoring a yield gives that
up: the function spans ticks, and everything read before the suspension may be stale after it.
A raw RPC that yields is a single operation, so it has nothing to be stale; a function reads many
values and combines them, so partial staleness would be the normal case rather than an edge one.
Whether that trade is acceptable is the decision to make here — the implementation strategy follows
from it.

### Options

1. **Reject precisely.** Keep the current refusal but make it useful: name the procedure that
   yielded rather than reporting that some procedure did. Preserves atomicity, costs almost
   nothing, and permanently excludes staging, warping and launching from functions.
2. **Retry the whole call, guarded.** Stop converting the yield in `RunFunction` and let it reach
   the standard request continuation machinery, so the entire call is retried on later updates and
   the client sees a call that takes several ticks — exactly like a raw yielding RPC. Correct for a
   function without side effects, unsafe for one with them, so it has to be gated on the function
   being side-effect free. That property is decidable when the tree is built: void calls,
   assignments and collection mutation are all visible nodes. Streams keep their present behavior
   under the same guard.
3. **Make the function itself resumable**, so that a yield from an inner call is rethrown wrapped in
   a yield carrying a continuation for the *function*, and the core's existing machinery resumes
   `RunFunction` on the next update exactly as it resumes any other yielding RPC. This is the full
   feature; the only hard part is what that continuation contains. See below.
4. **Reject yielding procedures when the tree is built.** Not possible: yielding is a runtime
   decision — `WarpTo` yields only while the warp is incomplete — so nothing in a procedure's
   signature says whether it will.

### Capturing the function's state

Option 3 needs the function's evaluation state to survive the unwind. Three strategies:

* **State machine.** Compile the tree into a machine that lifts locals into a heap frame so
  evaluation can suspend and resume — a substantial compiler pass, essentially re-implementing what
  `async`/`await` does, over an algebra that keeps growing.
* **Thread per function.** Park the function's thread at the yield and release it on the next
  update. Far less code, but KSP and Unity APIs are main-thread affine and some assert on the
  calling thread, so the function's thread would have to hold the main thread's window while the
  main thread blocks. Workable in principle, fragile in practice, and one thread per in-flight
  function.
* **Journal and replay.** Do not capture the stack at all. Record each completed call's result in a
  journal held by the continuation, and on resumption re-run the function from the start, serving
  each call from the journal instead of invoking it, until execution passes the point it reached
  before. Everything in the algebra apart from calls is deterministic, so replay reproduces exactly
  the same control flow, locals and collections.

  The last is much the cheapest, and it is the only one that makes side effects safe rather than
  merely tolerated: a side-effecting call that already completed is replayed from the journal, so it
  is not performed twice. Its costs are a journal per in-flight function, a call counter to key it
  (deterministic for the same reason replay works), re-running pure computation on each resumption —
  quadratic in the number of yields, which is fine when yields are few — and cleanup of journals
  belonging to a disconnected client.

  Its semantics are worth stating plainly: replayed reads return the values seen when the function
  started, so a function that spans frames sees a consistent but increasingly stale view of the
  game. That is inherent to any resumable design, not specific to this one — a captured stack would
  hold the same stale locals.

### Deferred calls

A much smaller feature, worth having whether or not option 3 is built: a call form that starts a
yielding procedure and returns within the same frame. If the call yields, its continuation is
scheduled and driven to completion by the core on subsequent updates, detached from the function,
which carries on immediately.

This lets a function trigger an action it does not need to wait for. It is genuinely limited, and
the limitation falls unevenly across the procedures that yield:

* `WarpTo` and `LaunchVessel` return nothing and read naturally as "start this" — deferring suits
  them.
* `AutoPilot.Wait` does nothing *but* wait, so deferring it is meaningless.
* `Undock`, `Part.Separate` and `ActivateNextStage` return the vessel or vessels they produce, which
  is usually the reason for calling them. A deferred call discards that, so the function cannot act
  on what it just created.

So the form has to be restricted to statement position, discarding any result, and documented as
doing so rather than returning a null the function might use. Two further consequences need
stating: a detached continuation has no request to report to, so a failure can only be logged and
the client never learns of it; and the function keeps running, so anything it does after the
deferred call observes game state from before the action completes.

It does not remove the need for the guard in option 2 — a yielding procedure called through the
ordinary form still aborts and retries the function — but for the calls it does cover it removes
the repeated-side-effect problem outright, because the function no longer aborts part way through.

### Direction

Staged, since these compose rather than compete:

1. Close the correctness problem first, with option 2's guard and option 1's precise refusal. This
   is small and stops functions silently repeating side effects.
2. Add deferred calls. Small, independently useful, and covers triggering an action without waiting.
3. Build option 3 on the journal-and-replay strategy when waiting on a result is actually wanted.
   Scope it to `RunFunction` initially — a stream that suspends across updates raises its own
   questions about update rate and staleness that are better answered separately.

This also constrains the exception design: a catch-all must not swallow `YieldException`, or a
paused procedure silently becomes a handled error. See "Exceptions".

## Client-side compilation

Assembling a tree by hand is one RPC per node and unreadable at any real size, so each client
that can inspect its own code compiles native syntax into the tree. Both compilers share the
same strategy: subtrees that do not touch the server are evaluated client-side once and embedded
as constants, remote member access becomes embedded calls, and anything unsupported is a
compile-time error naming the construct rather than a confusing failure on the server.

Procedures are resolved from a cached `KRPC.GetServices` metadata index rather than by stub
introspection — the dynamic Python stubs bake their metadata into closures, so the index is the
only representation that works identically for both stub implementations. Template
`ProcedureCall`s carry no arguments; every argument is supplied positionally as an expression,
with per-parameter numeric conversion (a Python float is a double, so single-precision parameters
get `constant_float`/casts).

### Python

`Client.compile_function` compiles a lambda or a function from its source; `add_event`,
`add_function_stream` and `run_function` accept functions directly.

* Expressions (`krpc/functioncompiler.py`): operators including floor division, true-division
  semantics and the bitwise operators; comprehensions (list/set/dict, nested) and generator
  expressions; `any`/`all`/`sum`/`min`/`max`/`len`/`sorted`/`abs`/`round`/`int`/`float`/`str`;
  subscripts and slices; f-strings; conditional expressions via `Function.Conditional`;
  assignment expressions; parameterless lambdas and local function calls; and `math` module
  calls mapped onto `StdLib`.
* Statements (`krpc/functionstatements.py`): `if`/`elif`/`else`, `while` and `for` with
  `break`/`continue`, early `return`, local variables including augmented and annotated
  assignment, assignment to remote properties and to collection elements, `pass`, and calls
  evaluated purely for their effects.

### C#

`Connection.CompileFunction` translates a LINQ expression tree — which the compiler hands the
client for free from an `Expression<Func<TResult>>` lambda — into the same server tree.
`AddEvent` accepts a boolean lambda, `AddStream` compiles compound lambdas instead of rejecting
them, and `RunFunction` accepts `Expression<Action>` lambdas so side-effecting functions can be
written in the same style.

Beyond the operator set: `System.Math` methods map onto `StdLib`; string `+` and `ToString`
become `ConcatStrings`/`ConvertToString`; the bitwise complement and the LINQ operators `Skip`,
`Take`, `SelectMany` and `ToDictionary` are supported; captured collections are folded into
constants.

### Semantics that differ from running locally

Documented for both compilers, because they are the surprises: `and`/`or` do not short-circuit on
the server; captured values are frozen at compile time, so only remote calls re-evaluate per
tick; and a procedure that pauses execution cannot be used inside a function.

## Batched tree construction

Building a tree costs one blocking round trip per node. The python compiler has 72 distinct
factory call sites, and every one of them is an ordinary generated stub call going through
`Client._invoke` (`client/python/krpc/client.py:261-299`), which hard-codes a single call per
`Request`. A compiled function of any real size is therefore hundreds of sequential round trips.

**What this actually costs.** Not a frame stall. `RPCServerUpdate` (`core/src/Core.cs:428-483`)
polls *and* executes repeatedly within a single `FixedUpdate` until `MaxTimePerUpdate` is exceeded
(5 ms by default, self-tuning 1–25 ms), and with `BlockingRecv` it waits up to `RecvTimeout` for
the next request rather than returning early — so a client doing synchronous ping-pong is served
many times per tick. The per-node server work is a single LINQ node allocation. The costs are, in
order:

* **Client wall clock, dominated by round-trip time.** Tolerable at loopback latency and bad at
  5–20 ms, which is exactly the run-the-script-on-another-machine case: 500 nodes at 10 ms is five
  seconds to compile one lambda.
* **Monopolizing the per-tick RPC budget**, starving other clients' streams and dragging the
  adaptive rate controller down while a tree is being built.
* **`OneRPCPerUpdate` degenerates to one node per frame**, so the same 500-node tree takes about
  ten seconds regardless of latency.

It is worst for `RunFunction`, whose whole premise is replacing many round trips with one. If
building the tree costs three hundred round trips to save twenty, the feature is a net loss unless
the function is reused.

**This does not fall out of #903.** Rung 1 of that design is a user-facing batch of *independent*
calls whose results are only readable after the block exits. Tree construction is the opposite
shape: each call's returned handle is the next call's argument, which an independent-call batch
cannot express.

**What makes batching possible anyway** is that the tree is fully determined client-side. The
compiler builds its procedure index from a single `get_services()` call (`Metadata`,
`client/python/krpc/expressionutils.py:53`) and tracks `ptype` locally through the whole walk; it
never needs a server response to decide what to build next. The round trips exist only to
materialize object handles.

**Design: deferred handles with a level-ordered flush.** Have the factory wrappers return a
deferred handle holding `(procedure, arguments)`, where an argument may itself be a deferred
handle. The compiler runs to completion locally, building the tree as a client-side DAG, and the
handles are then flushed in dependency order — one multi-call `Request` per level, since all nodes
at a given depth are independent. That turns O(nodes) round trips into O(depth): typically 10–30
requests for a tree of several hundred nodes. It is client-side work only, with no protocol change
and no change to any other client.

The server side already supports it. `RequestContinuation.Run`
(`core/src/Service/RequestContinuation.cs:52-83`) executes a multi-call request sequentially within
one tick, and `ProcedureResult` carries a per-call `error`, so a failure is attributable to a
specific node.

Two things to get right:

* **Error attribution.** Errors currently surface at the construction site, with the source
  location of the offending syntax. Each deferred handle has to carry its `ast` node so the flush
  can re-raise through the existing `self._error(node, …)` path; otherwise the compiler's
  diagnostics regress to "something in this function was wrong".
* **Not leaking deferred handles.** `compile_expression`, `run_function`, `add_event` and
  `add_expression_stream` (`client/python/krpc/client.py:128-167`) must flush and hand the real
  root handle onward.

**Two cheaper wins to take first.** `remote_type` (`client/python/krpc/expressionutils.py:91`) is
uncached, so every `self._remote_type(...)` is a fresh `Type.*` round trip and composite types
recurse into several more; memoizing on the ptype removes a large and highly repetitive slice of
the traffic for a few lines. Deduplicating repeated constants is the same shape. Both have a
server-side counterpart, covered in "Object identity and lifetime" below. Both are worth
doing regardless, and they change the measurement that decides whether the deferred-handle work is
justified — which should be taken before building it, by counting factory calls for realistic
inputs such as the launch-into-orbit tutorial function and the examples under
`doc/src/scripts/client/python/`.

**Alternatives considered.** Intra-request result references — a `oneof` on `Argument` letting a
call name the result of an earlier call in the same request — would send the whole tree in exactly
one request and would help any chained calls, not just functions. It is rejected as the first step
because it is a protocol bump touching every client's encoder, and it needs new semantics for
mid-batch failure and for the yield-and-retry path in `RequestContinuation`. Level-ordered batching
gets most of the win for none of that; this is the follow-up if measurement shows depth dominating.
A single `Function.BuildTree(bytes)` RPC taking a serialized tree is rejected outright: it
duplicates every factory in a second encoding and discards the per-node error reporting that the
extend-the-tree approach was chosen for in the first place.

The same design applies to the C# compiler. Java and C++ build trees by hand and would need an
explicit batch helper instead, which is only worth adding if hand-built trees there get large.

## Object identity and lifetime

Every object a factory returns becomes an entry in the object store, and the store already has the
machinery to collapse duplicates: `AddInstance` (`core/src/Service/ObjectStore.cs:34-46`) looks the
instance up in a `Dictionary<object, ulong>` before allocating an id, and that dictionary uses the
default comparer — so any class overriding `Equals`/`GetHashCode` is deduplicated automatically.
That is what `Equatable<T>` (`core/src/Utils/Equatable.cs`) exists for, and what the SpaceCenter
classes use.

Neither `KRPC.Type` nor `KRPC.Expression` overrides it. Both fall back to reference equality, and
every factory returns a freshly constructed instance, so every call mints a new id. Nothing is ever
released either: `RemoveInstance` has no callers anywhere in `core/`, `server/` or `service/`, and
`ObjectStore.Clear()` runs only from `Server.Stop()` (`core/src/Server/Server.cs:114`). Compiling
one function that asks for `Type.Double()` five hundred times therefore leaves five hundred
permanent entries describing a single type.

That second property is about to change, which sets the ordering for this work — see "Sequencing
against #894" below.

### Types

`Type` derives from `Equatable<Type>`, comparing `InternalType`. It is an immutable description of
a type with no per-client state, so value equality is the correct semantics and sharing a single
instance between clients is safe. No protocol or client change is involved.

Composite types collapse for free: the CLR interns constructed generic types, so `MakeGenericType`
returns the same `System.Type` for the same arguments, and `ListType(Double())` reduces to one id
provided the nested `Double()` did. Two things to check when implementing — `Equatable<T>` brings
`operator ==`/`!=` with it, so existing `== null` comparisons on `KRPC.Type` change path (they stay
correct, since those operators are null-safe), and the `ReferenceEquals` guards at
`Type.cs:160-187` are unaffected.

### Constants

Constants get the same treatment for the same reason: `false`, `0` and `1` recur throughout any
compiled function, and there is no more sense in minting an id per occurrence than there is for
types.

The mechanism has to differ, though. `Expression` wraps an arbitrary LINQ tree, and those have no
structural equality, so a blanket `Equals` override on `Expression` is not available — value
equality is well defined for constant nodes and for nothing else. Intern in the factories instead:
a `Dictionary<Tuple<System.Type, object>, Expression>` keyed on the constant's type and value,
consulted by `ConstantDouble`, `ConstantFloat`, `ConstantInt`, `ConstantBool` and `ConstantString`.
Reference equality then does the deduplication in the object store with no equality override at
all, and the allocation is avoided as well. Sharing is safe because LINQ trees are immutable and
sharing a subexpression between trees is supported. The key includes the type so that
`ConstantInt(1)`, `ConstantDouble(1.0)` and `ConstantFloat(1.0f)` stay distinct; `Tuple<,>` rather
than a value tuple, matching the codebase (`core/src/Configuration.cs:37`).

**`ConstantObject` is deliberately excluded.** Interning it would key a permanent, static, strong
reference on an arbitrary service object — a destroyed vessel or part kept alive for the life of
the server. That is the exact leak shape [#771](https://github.com/krpc/krpc/issues/771) is about,
and it would defeat the reclamation #894 introduces for precisely those objects. The value
constants pin nothing but a boxed primitive or a string, so they are safe; object constants are
not. The saving was small anyway, and the interaction is discussed below.

### Sequencing against #894

[PR #894](https://github.com/krpc/krpc/pull/894) (`fix-objectstore-771`, open) gives the object
store a reclamation sweep, and **it should land before the server-side function work**. The
function work adds a new population to the store and a new way to hold references to service
objects, so it wants to be written against the store's final shape rather than retrofitted onto it.
It also touches `core/src/Service/ObjectStore.cs`, `CallContext.cs` and `Core.cs`, which is where
the conflicts would be.

What #894 actually does: `ObjectStore.RemoveDead()` walks the registered instances, and evicts
those implementing the new `KRPC.Utils.ITrackedObject` whose `IsAlive` is false, driven from the
game-state load boundary. It is **liveness eviction, not reference counting or reachability** —
instances that do not implement `ITrackedObject` are explicitly skipped.

Three consequences here:

* **Types and constants are unaffected, for free.** They wrap no game object, have no liveness to
  test, and will not implement `ITrackedObject`, so the sweep skips them. The "never released"
  property this section relies on survives #894 without a special case — it stops being "nothing is
  ever removed" and becomes "nothing removes *these*", which is the property actually wanted.
* **Object constants are not reclaimed by it**, which is the answer to the obvious hope.
  `RemoveDead` drops the store's entry, but a `ConstantObject` node holds the instance through
  `LinqExpression.Constant`, and the tree is a second and stronger root: the object stays alive in
  the CLR for as long as the function does. Eviction from the store is not collection.
* **What the client sees is nonetheless right, thanks to #894.** A function holding a constant for
  a since-destroyed part re-derives on access and raises the new `ObjectDestroyedException` per
  evaluation, instead of reading stale data or throwing a bare `NullReferenceException`. This is a
  good reason to build the function work on top of #894 rather than alongside it — the behavior
  falls out instead of needing its own handling.

**Rejected: reclaiming trees that hold a dead object.** Making `Expression` implement
`ITrackedObject`, alive only while every service object it closes over is alive, would bound the
growth described below. It is wrong for three reasons, recorded because it is an easy idea to
arrive at twice.

* **The client can handle the exception, and will want to.** `ObjectDestroyedException` is a
  `[KRPCException]`, so `TryCatch(body, "KRPC", "ObjectDestroyedException", …)` catches it inside
  the function like any other. A function written to survive its part being destroyed is working
  as intended, not broken, and pulling the tree out from under it destroys a program *because* it
  handled the case it was written to handle.
* **A dead constant does not mean a dead tree.** The object may be referenced only from a branch
  that never runs, or from the handler that exists to cope with its absence. Liveness of one leaf
  says nothing about whether the tree can still evaluate.
* **It does not fit the interface.** `ITrackedObject.IsAlive` is specified to return false only
  when the underlying object is definitively gone, so that objects a client legitimately still
  holds are not discarded. An expression has no underlying game object; it is a client-authored
  program whose continued usefulness is a matter of the client's intent, which the server cannot
  infer. The sweep answers "did the game destroy this?", not "does the client still want this?".

If interior-node growth is ever worth addressing, it therefore needs a client-driven answer — an
explicit release, or lifetime tied to the stream or event that consumes the tree — rather than the
server guessing from liveness. Not designed here.

### No refcounting for these

Deliberate, and it is the reason deduplication is enough on its own. Distinct types are bounded by
the service surface; distinct constants by the literals a program actually writes. Reaching a
troubling number would take thousands of distinct literals, which is not a realistic shape for
hand-written or compiled code. So nothing sweeps them and they live for the server session.

**This is not #902.** That issue is reference-counted *streams* — two equal `AddStream` requests
deduplicate to one id, and a single `RemoveStream` then destroys it for both consumers. It concerns
stream lifetime rather than the object store, and it is a correctness bug rather than a growth
concern. Nothing here affects it, and it still needs doing.

**What deduplication does not bound.** Interior nodes — every operator, call, block and lambda —
are not deduplicated, and they are the population that actually grows: one compile of a moderate
function is hundreds of permanent entries, and a program that recompiles inside a loop, or
repeatedly creates function streams, grows without limit. #894 does not reach them either, and for
the reasons above should not be made to. This is close to a pre-existing property of the object
store
rather than something the function work introduces — every `Vessel` and `Part` ever encoded is
pinned the same way, which is what #771 and #894 are about — and it is left alone here. The
conclusion above is that types and constants need no refcounting, not that the object store as a
whole is bounded.

### Testing

`core/test/Service/KRPC/TypeTest.cs` and `ExpressionTest.cs` gain cases that two equal factory
calls yield the same object id, and that types and constants differing only in type — `Int` versus
`Long`, `ConstantInt(1)` versus `ConstantDouble(1.0)` — do not collide. `ObjectStoreTest` already
covers the equality path itself.

## Interaction with planned protocol work (#906)

* **#866 named tuples/structs**: adds a `STRUCT` type code and definitions. Extends naturally
  here: a new `TypeCode.Struct` value, `Type.StructType(service, name)`, and
  `Function.CreateStruct`/field access nodes; computed streams then return structs with no
  further changes (runtime-typed encoding + client-declared/reported type both extend).
* **#877 stream invalidation**: builds on per-stream error results, which
  `FunctionStream`/hardened `EventStream` now emit in the same shape as `ProcedureCallStream`;
  the removal convention can layer on unchanged.
* **#903 reverse streams / batched calls**: independent of the tree-construction round trips —
  rung 1 batches calls whose results are not needed until the batch completes, which is the wrong
  shape for a tree (see "Batched tree construction"). The overlap is elsewhere: the expression
  registry ("store server-side state, evaluate per tick") is the same machinery reverse streams
  cite as prior art.
* **#902 stream refcounting**: unrelated, despite the surface similarity. It reference-counts
  *streams*, not object-store ids; the object store has no refcounting today and, per "Object
  identity and lifetime", deliberately gains none for types and constants.
* **#904 deprecation**: individual expression operators can be evolved/deprecated through the
  standard mechanism since they are ordinary service members.

## Testing

* `core/test/Service/KRPC/FunctionTest.cs`: promotion cases for every binary op; the `Call`
  test implemented against the scanned core `TestService` (plus `CallWithArguments`,
  `ConstantObject`, class-typed `Parameter`, per-element `Any`/`Select` with real RPC calls,
  error propagation, `ReturnType` on every node kind); and the statement nodes — block scoping,
  loops with `Break`/`Continue`, early `Return`, and imperative collection construction.
* New `TypeTest` coverage for the factories and introspection, and `StdLibTest` for the
  scalar, vector and quaternion operations.
* Stream behavior (value change detection, error capture, yield skip) unit-tested alongside the
  existing core stream tests.
* Python integration tests (against TestServer, part of `//:test`): computed streams end-to-end
  (value, collection and object results; server-reported type decode), per-element call events,
  object constants, mixed-type arithmetic events, error surfacing, and `run_function` covering
  results, side effects and the void case.
* C#/Java/C++ client tests for the typed stream and run-once helpers, following each client's
  existing event/stream test structure.
* Compiler tests per client covering the accepted language subset and the diagnostics raised for
  unsupported constructs.
* **Golden expression-tree tests.** A deterministic tree printer
  (`core/src/Service/KRPC/FunctionTreePrinter.cs`: indented `NodeType<Type> detail` lines;
  sequential ids for parameters/variables/labels; invariant round-trip numeric formatting;
  object constants printed as type name only, so no run-to-run identity leaks) is exposed
  through a test-only `DumpFunctionTree(Function)` RPC on TestServer's `TestService` and
  mirrored on the in-game `TestingTools` service. Three golden suites compare dumps against
  expected strings, verifying the exact trees the API generates without depending on the
  (brittle) compiled IL:
  - `core/test/Service/KRPC/FunctionTreePrinterTest.cs` — factory API: the direct-call
    emission (scene check, null-return check only for non-nullable reference returns), numeric
    promotion `Convert` insertion, `While`/`ForEach` desugaring, marker→goto rewriting, label
    binding of early returns.
  - `client/python/krpc/test/test_functiontree.py` — python compiler output end-to-end (both
    stub modes): getter null-check blocks, true-division converts, `math.sqrt`→`StdLib.Sqrt`,
    statement functions as `Invoke(Lambda)`, loops with declared variables, void setter
    functions, comprehensions as `Select`+`ToList` with per-element narrowing converts.
  - `client/csharp/test/FunctionTreeTest.cs` — C# LINQ compiler output: `Math.Sqrt` mapping,
    folded captured collections, string `+` → `String.Concat`, ternary conditionals.
  Sets are deliberately excluded from goldens (client-side set iteration order is
  nondeterministic). Generated C++ service headers don't include cross-service headers, so the
  C++ test sources include `krpc/services/krpc.hpp` before `services/test_service.hpp` for the
  new RPC's `KRPC::Function` parameter.

## Gaps to close

The node algebra is intended to cover tuples, collections and strings completely. It does not yet,
and the gaps below are all planned rather than deliberate omissions.

### Tuples — complete

`CreateTuple` builds them and `Get` reads elements, special-casing tuple types to map the index
onto the corresponding `ItemN` property.

One constraint is inherent rather than a gap, and should be documented as such: the index must be a
constant, because `Get` evaluates the index expression when the node is built in order to pick the
property. Tuple elements are differently typed, so an index computed at evaluation time has no
static type to give the resulting node.

### Collections

Creation, mutation by addition, and the query surface are covered. Missing:

* **Removal and clearing** — `ListRemove`, `SetRemove`, `DictionaryRemove`, and a `Clear` for each.
  Collections are currently build-up-only: elements can be added and overwritten but never taken
  away, which is the most conspicuous asymmetry in the algebra.
* **Dictionary enumeration** — `Keys` and `Values`. Without them a dictionary cannot be iterated
  with `ForEach` at all, which makes dictionaries substantially weaker than lists inside a
  function, rather than merely less convenient.
* **Element selection** — `First`, `Last`, `ElementAt`, and min/max by key selector.
* **Reshaping** — `Distinct`, `Reverse`, `GroupBy`, `Zip`, and `Union`/`Intersect`/`Except`.

### Strings

**Strings are deliberately not collections.** They should be rejected by the collection operations
with a clear message saying so, and given their own operations instead.

They are currently accepted and then fail internally, because `CheckIsEnumerable` tests
`IEnumerable`, which `string` satisfies:

* `Count` throws `ArgumentNullException` on the `property` parameter — `string` has `Length`, not
  `Count`.
* `Contains` throws `IndexOutOfRangeException` — `GetGenericArguments()[0]` indexes an empty array
  for a non-generic type.
* `Get` throws `ArgumentNullException` on the `method` parameter.

Reaching for `Count` to get a string's length is the obvious thing to try, so the guard is worth
having independently of the operations below.

Beyond `ConstantString`, `ConcatStrings` and `ConvertToString`, string handling needs: length,
case conversion, substring, character access, index of, replace, split, join, trim, and the
`StartsWith`/`EndsWith`/`Contains` predicates.

Names must not collide with the collection operations that share a concept — the algebra already
avoids collisions this way (`ConvertToString`, `ConcatStrings`, `BuildDictionary`), and string
length, containment and indexing all need distinguishing from their collection counterparts.

#### Characters are single-character strings

**Decided:** character access returns a string of length one. There is no character type in the
algebra or on the wire.

A one-character string composes directly with every other string operation, decodes correctly in
every client with no new code, and is exactly what a python or lua user expects; C#, java and C++
users index it once to get a `char`. The reported type is `STRING`, which is true, rather than a
value carrying a convention the wire does not record.

Two alternatives were considered:

* **A `CHAR` type code in the protocol.** Rejected as disproportionate: no RPC anywhere in kRPC
  uses a character type, so the code would exist solely to serve this one operation, at the cost of
  encode/decode and dynamic type handling in all six clients plus a version-skew story. Half the
  clients (python, lua) have no character type to map it to in any case. Worth reopening only if
  strings become iterable, or alongside #866, which already adds a type code and would amortize the
  per-client work.
* **Reusing `uint32`.** Rejected as the weakest option. It is not self-describing, so a dynamic
  client decoding by reported type yields a number rather than a character with no way to tell the
  difference; it composes with no string operation, so it would need conversion nodes and numeric
  overloads to be usable at all; and as a Unicode code point it does not correspond to the UTF-16
  code unit that C# and java call `char`, losing the fidelity that motivated the idea.

### Exceptions

A function cannot raise an exception. There is no `Throw` node, so the only errors a function can
produce are the ones evaluation happens to hit — an RPC that fails, a null dereference, a marker
left unbound. A function that validates its inputs, or that wants to signal a condition to the
client, has no way to say so.

**The delivery half is already built.** Any exception raised while evaluating an expression is
passed to `Services.HandleException`, which produces an `Error` carrying the service and name of
the exception type alongside its description, so the client reconstructs the correct typed
exception. Streams catch and report it as an error result; `RunFunction` propagates it as an
ordinary RPC error. Nothing about that pathway needs changing — the gap is only the node that
constructs and raises the exception.

Handling is needed alongside raising, not after it: a function that calls an RPC which can fail has
no way to respond to that today, and the whole function is abandoned.

**Raising.** `Throw(service, name, message)`, evaluating as a statement.

Only exceptions registered with `[KRPCException]` can be raised, which keeps the boundary well
defined and gives the client a typed exception it can catch, applying the same principle as return
values: only what kRPC can represent crosses the wire. An arbitrary CLR exception would arrive as an
opaque error. Naming one as `(service, name)` follows `ClassType`, and the exception types already
provide the `(string message)` constructor this needs.

A throw is a statement rather than a value, so an early exit is written as an `IfThen` containing a
throw. The typed form LINQ offers, for a throw in a value position such as one branch of an
`IfThenElse`, is not proposed: trees are built innermost-first, so there is no surrounding context
to infer the type from and it would have to be supplied explicitly at every use.

**Handling.** `TryCatch(body, service, name, message, handler)` for a named exception,
`TryCatchAll(body, message, handler)` for any, and `TryFinally(body, finalizer)` for cleanup that
runs either way. Body and handler are evaluated as statements through the existing `AsStatement`, so
they need not produce values of the same type.

`message` is an optional string variable that the caught exception's message is assigned to before
the handler runs. **The exception object itself is never exposed.** Binding only the message keeps
exceptions out of the value algebra entirely — nothing needs an exception-typed entry in
`KRPC.Type`, and no value that cannot cross the boundary can be carried toward it.

**A catch-all must not swallow `YieldException`.** A procedure that pauses execution unwinds by
throwing it, and the stream evaluating the expression resumes the procedure on a later update.
Catching it would silently break any such procedure used inside a `TryCatchAll`, turning a paused
call into a handled error. The catch-all therefore needs a filter excluding it so that it continues
to propagate. Named catches are not affected, since `YieldException` is not a `[KRPCException]` and
so cannot be named.

**Semantics per context** are worth documenting rather than leaving to be discovered: an exception
that escapes a function surfaces immediately as an RPC error from `RunFunction`, but from a stream
or event it becomes an error result on every update for as long as the condition holds.

**Implementation note.** `ExceptionSignature` does not record the CLR type of the exception, unlike
`ClassSignature` and `EnumerationSignature`, so resolving `(service, name)` to a type it can
construct requires adding an `UnderlyingType` to it and threading it through
`ServiceSignature.AddException`. It is not serialized, so the service-definitions JSON is
unaffected — the same approach already taken for classes and enumerations.

### Client compilers

Each addition needs the corresponding native syntax mapped in both compilers to be reachable from
compiled code — `len(s)`, `s.upper()`, slicing and `in` in python; `.Length`, `.ToUpper()`,
`.Substring()` and `.Contains()` in C#. Until then these are factory-only, and a user writing the
natural thing gets an unsupported-construct error.

Exceptions are asymmetric between the two. Python `raise` and `try`/`except` map onto the nodes
directly, and the statement compiler needs to handle both. C# cannot reach either: an
expression-tree lambda may neither contain a throw expression nor a statement body, so exceptions
stay factory-only there, consistent with that compiler already being limited to single-expression
lambdas.

### Testing

Each addition needs core coverage of the operation itself, and the string work additionally needs
tests that the collection operations reject a string with the intended message rather than an
internal exception.

## Out of scope (follow-up candidates)

* Java and C++ native-syntax compilers. Neither language exposes its own syntax tree to the
  client, so there is no equivalent of the Python source / C# LINQ route; both keep the run-once
  and stream helpers over hand-built trees.
* Batched tree construction, which would cut the one-RPC-per-node cost of building a tree. Designed
  in "Batched tree construction" above; client-side only, and gated on measuring real tree sizes
  first.
