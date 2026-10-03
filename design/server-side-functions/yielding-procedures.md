# Yielding procedures in server side functions

**Status:** proposal — not started. Two follow-ups to server side functions, deferred calls and
resumable functions, to be built once the server side functions stack merges. No GitHub issue
filed yet.

[`server-side-functions.md`](server-side-functions.md) describes the problem under "Yielding
procedures inside a function". This doc holds the design of both follow-ups.

## The problem

`KRPC.RunFunction` reports an error when a procedure inside the function pauses execution. The
procedures that pause are the actions people most want a function to perform:

| Procedure | Returns | Deferred call | Needs resumption |
| --- | --- | --- | --- |
| `WarpTo`, `LaunchVessel` | nothing | fits | no |
| `AutoPilot.Wait` | nothing | meaningless | yes |
| `ActivateNextStage`, `Undock`, `Part.Separate` | the vessel(s) produced | discards the result | yes |

The two follow-ups take opposite sides of one trade. A deferred call keeps the function within a
single tick, and detaches the paused call from it. A resumable function waits for the call, and
spans several ticks. They compose: a resumable function can still start a warp it does not wait
for.

## Deferred calls

A deferred call starts a procedure that pauses, and the function carries on without waiting for
it. The core drives the paused call to completion on later updates, detached from the function.

It was built as three phases of the server side functions stack, and removed before review. The
design below is what was built. "Open questions" lists what needs more design.

### API

* `Expression.DeferredCall (call)` and `Expression.DeferredCallWithArguments (call, args)`, beside
  `Call` and `CallWithArguments`. The node is a statement, and the procedure's value is discarded.
* Python spells it `krpc.defer(call)`, a marker recognized by identity like the `math` module
  functions, allowed wherever a statement goes.
* C# spells it `Function.Defer(() => call)`, a marker taking a lambda, since a call returning
  nothing cannot be an argument. An expression tree carries a single expression, so it is the whole
  body of a `RunFunction` or `CompileFunction` lambda.

### Emission

The emission wraps the ordinary direct call and its scene check in an `Action`, and passes that to
`Services.ExecuteDeferredCall` with the procedure's signature. A failure to start the call
propagates to the function, so an unavailable procedure is still reported to the client.

A `YieldException` hands a `DeferredCall` to the core. The core runs the ones it holds ahead of
each update's calls, outside `MaxTimePerUpdate`, and logs a failure against the procedure's name.

The arguments are evaluated into temporaries before the `Action`, so a pause in an argument belongs
to the function, and is reported as any other pause is.

### Rules

**Only `RunFunction` may contain one.** A stream or event evaluates its function on every update,
so a deferred call in one would start the procedure again each time, and the pending calls would
accumulate without bound. `AddFunctionStream` and `AddEvent` reject such a function when they are
called, through `Expression.CheckNoDeferredCalls`.

**A deferred call is owned by the client that started it.** `ExecuteDeferredCall` records
`CallContext.Client`, and each resumption runs with that client set, as an ordinary resumed call
does. The call is canceled when its client disconnects, and every call is canceled once no server
is running. Canceling drops the continuation and logs it. The procedures have no undo, so a
canceled `WarpTo` leaves the game warping. The precedent is `RPCServerUpdate`, which drops a
yielded continuation whose client has disconnected.

### Open questions

* **The result is discarded.** The form is restricted to statement position. `Undock`,
  `Part.Separate` and `ActivateNextStage` return the vessels they produce, which is usually the
  reason for calling them, so a deferred call suits only `WarpTo` and `LaunchVessel`.
* **A failure after the pause is only logged.** A detached continuation has no request to report
  to, so the client never learns of it.
* **The function sees stale state.** Everything after the deferred call reads the game from before
  the action completes.
* **Cancellation is partial.** A canceled call leaves its effect part way through.
* **Interaction with resumable functions.** A deferred call inside a resumable function needs a
  journal index, or each replay starts it again (problem 3 below).

## Resumable functions

A yield from an inner call is rethrown wrapped in a yield carrying a continuation for the
*function*. The core's existing machinery resumes `RunFunction` on the next update, as it resumes
any other yielding RPC. Resumption lets a client push a whole sequence to the server: point at a
target, wait for the autopilot, stage, read what came off.

**No new API.** `RunFunction` keeps its signature in every client, and both compilers keep the
syntax they have. The client-visible change is that the call may take several ticks, which is
already how a yielding RPC behaves.

**Scope is `RunFunction` alone.** A function stream and an event keep the error. A stream that
suspends across updates raises its own questions about update rate and staleness.

### Strategies

The only hard part is what the continuation contains:

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

### It needs no new machinery

`RunFunction` is an ordinary RPC, so the existing continuation machinery already carries it:

1. `ProcedureCallContinuation.Run` catches any `YieldException` and rethrows
   `YieldException<ProcedureCallContinuation>` wrapping `() => e.CallUntyped ()`.
2. `RequestContinuation.Run` catches that and throws `YieldException<RequestContinuation>`.
3. `Core.RPCServerUpdate` parks it in `rpcYieldedContinuations` and runs it on the next update.

Today `RunFunction` swallows the yield and converts it to an `InvalidOperationException`. The
change is to let it out, wrapped around a journal:

```csharp
static byte[] RunJournaled (Expression function, TypeSpec spec, FunctionJournal journal)
{
    journal.Rewind ();
    var previous = FunctionJournal.Current;
    FunctionJournal.Current = journal;
    try {
        var value = function.JournalingEvaluator ();
        return ReferenceEquals (value, null) ? null : Encode (value, spec);
    } catch (YieldException e) {
        journal.Suspend (e);
        throw new YieldException<Func<object>> (
            () => RunJournaled (function, spec, journal));
    } finally {
        FunctionJournal.Current = previous;
    }
}
```

Each fresh pause throws a new `YieldException` carrying the same journal, grown. `Core.cs`,
`RequestContinuation.cs` and `ProcedureCallContinuation.cs` need no change.

The return type is still validated before the first evaluation, so a function whose value cannot
be sent reports without performing its effects.

**Cleanup is free.** The journal is reachable only from the parked continuation. `RPCServerUpdate`
already skips a continuation whose client has disconnected, and the list is cleared on the swap, so
a journal dies with the request that owns it.

### The journal

```csharp
sealed class FunctionJournal
{
    public static FunctionJournal Current;   // ambient, as CallContext.Client is

    List<object> results;                    // completed call results, in call order
    int index;                               // cursor, reset by Rewind
    YieldException pending;                  // the call that suspended
    int pendingIndex;
}
```

`Current` is safe as an ambient value because a function cannot call a `KRPC` procedure, so
`RunFunction` never runs inside another `RunFunction`.

The cursor is a runtime counter rather than a per-node identifier, because a call inside a loop
executes many times. Replay reproduces the counter because everything in the algebra apart from
calls is deterministic.

Each index is in one of three states:

| State | On replay |
| --- | --- |
| Result recorded | Return it, skip the invocation |
| Pending | Resume through `e.CallUntyped ()`, record the result |
| Fresh | Invoke the method, record the result |

The pending slot is what makes side effects safe. A pause inside `ActivateNextStage` at index 7
resumes that call on the next update; nothing stages a second time.

### Call emission

This is the work, and it costs some of what
[`server-side-functions.md`](server-side-functions.md) bought under "Calls". A call compiles to a
direct typed `LinqExpression.Call` of the procedure's `MethodInfo`, which took `StdLib.Sqrt` from
38.4 to 7.8 ns/call by letting the JIT inline it.

The journaling form hoists the arguments into temporaries first, then branches:

```
Block(vars: [a0, a1, idx, tmp],
  a0  = <arg0>,
  a1  = <arg1>,
  idx = Journal.Next (),
  Condition(Journal.HasResult (idx),
    tmp = (T)Journal.Result (idx),
    Condition(Journal.IsPending (idx),
      tmp = (T)Journal.Resume (idx),
      Block(sceneCheck, tmp = method (a0, a1), Journal.Record (idx, tmp)))),
  tmp)
```

* Arguments still evaluate on replay. A nested call inside an argument takes its own journal index,
  and replay must reach it in the same order.
* The call itself stays direct and inlinable.
* Added cost is a static field increment, one taken branch of three, and a box per value-returning
  call on the record path.
* A void call records a null, so the counter stays aligned.
* `Journal.Suspend` reads the cursor the emitted code already set, so the index of the suspended
  call needs no separate plumbing.

### Two compiled delegates

`Expression` caches its compiled delegate, which `RunFunction` and `AddFunctionStream` share;
`AddEvent` compiles its own. Emitting journaling unconditionally makes every function stream pay it
on every update.

So `Expression` gains a `JournalingEvaluator` beside `Evaluator`, compiled lazily from a rewritten
tree and used by `RunFunction` alone. A function with no value runs through `Runner`, the `Action`
form of the same delegate, so it needs a `JournalingRunner` as well. Laziness applies to the tree, not to the attempt: the first
run must journal, or a pause leaves side effects performed and nothing recorded.

The rewrite has to find the call sites, and `BuildCall` has already flattened them into a `Block`
by the time a visitor sees one. Mark them with a custom `ExpressionType.Extension` node whose
`Reduce ()` gives the plain form, and match on the node type in `VisitExtension`.

**Extension nodes work on the runtime KSP ships**, verified against the `System.Core.dll` in
`KSP_Data/Managed` from KSP 1.12.5 on Unity 2019.4.18f1. That assembly carries the Microsoft
reference implementation, in which `StackSpiller.RewriteExtensionExpression` calls
`ReduceExtensions ()` ahead of compilation. A node reduces correctly when compiled bare, inside a
block with variables, as an argument to another call, inside a loop, and at a reference type, and
an `ExpressionVisitor` reaches it through `VisitExtension` and rewrites it into the journaling
form. Reduction is managed code in `System.Core`, so it runs before any IL is emitted and does not
depend on the runtime underneath.

`ConditionalWeakTable<LinqExpression, ProcedureSignature>` filled by `BuildCall` is the fallback if
the extension node causes trouble. It matches on identity, which holds because nodes are immutable
and shared by reference.

### Three correctness problems to settle first

These are why the work wants its own PR rather than another phase of the server side functions stack.

**1. Replay repeats local mutation of a journaled object.** "Everything but calls is deterministic"
is not quite true. `vessel.parts.all` returns a fresh list per call. The journal records that
reference, and the function then appends to it. On replay the call is served from the journal and
the append runs again, so the list holds the element twice. Either record a defensive copy of a
mutable collection result, or bring the collection mutation nodes into the journal.

**2. A `TryFinally` runs its finalizer once per attempt.** A pause unwinds as an exception through
the compiled tree, so every enclosing finalizer runs on the way out and again on replay.
`TryCatchAll` is already correct: it rethrows `YieldException` ahead of the catch-all.

**3. Deferred calls need a journal index**, if they are built first. A deferred call is emitted
through the same `BuildCall`. Without an index, a resumed function starts the warp again on every
replay.

### Semantics to document

* **A function is no longer evaluated within a single physics tick.** The tutorial states this twice
  as a headline property. A resumed function spans ticks, and replayed reads return the values seen
  when it started, so its view of the game is internally consistent and grows stale. That is
  inherent to resumption, not to this strategy; a captured stack would hold the same stale locals.
* **A completed side effect is not performed twice.**
* **Pure computation is re-run on each resumption**, which is quadratic in the number of pauses.
  That is fine while pauses are few.
* `Expression.YieldedMessage` says a function cannot call a procedure that pauses. After this it
  applies to streams and events alone, and needs rewording.

### Phases

| Phase | Content |
| --- | --- |
| 1 | `FunctionJournal`, the emission change, `JournalingEvaluator` and `JournalingRunner` |
| 2 | `RunFunction` throwing the wrapped yield, and the three problems above |
| 3 | Documentation, tutorial and changelog |

### Testing

`TestService.BlockingProcedureReturns (n, sum)` pauses `n` times and returns a sum, so the whole
thing is testable in the `ExpressionTest` partial files in `core/test/Service/KRPC/` with no game
running. Assert the value, the number of invocations, and that a side-effecting call placed before
the pause happens exactly once. `core/test/CoreTest.cs` covers the parked continuation against the
`TestServer` harness.

In game, stage and then read the vessels staging produced is the case worth covering, beside an
`AutoPilot.Wait` that spans several ticks.
