# Resumable server side functions

**Status:** proposal — not started. A follow-up to server side functions
([PR #1069](https://github.com/krpc/krpc/pull/1069), now being split into a stack of PRs), to be
built once that stack merges. No GitHub issue filed yet.

Supersedes the "Resumable functions" sketch in
[`server-side-functions.md`](server-side-functions.md), under "Yielding procedures inside a
function". That section states the choice between the three strategies and why journal and replay
won; this doc is the implementation design.

## What it buys

`KRPC.RunFunction` currently reports an error when a procedure inside the function pauses
execution. Deferred calls cover part of that ground, and the coverage is uneven:

| Procedure | Returns | Deferred call | Needs resumption |
| --- | --- | --- | --- |
| `WarpTo`, `LaunchVessel` | nothing | fits | no |
| `AutoPilot.Wait` | nothing | meaningless | yes |
| `ActivateNextStage`, `Undock`, `Part.Separate` | the vessel(s) produced | discards the result | yes |

A deferred call is restricted to statement position and throws the result away. So a function can
start a warp, and it cannot stage and then act on the vessels staging produced. Resumption is what
lets a client push a whole sequence to the server: point at a target, wait for the autopilot,
stage, read what came off.

**No new API.** `RunFunction` keeps its signature in every client, and both compilers keep the
syntax they have. The client-visible change is that the call may take several ticks, which is
already how a yielding RPC behaves.

**Scope is `RunFunction` alone.** A function stream and an event keep the error. A stream that
suspends across updates raises its own questions about update rate and staleness.

## It needs no new machinery

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

## The journal

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

## Call emission

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

## Two compiled delegates

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

## Three correctness problems to settle first

These are why the work wants its own PR rather than another phase of the server side functions stack.

**1. Replay repeats local mutation of a journaled object.** "Everything but calls is deterministic"
is not quite true. `vessel.parts.all` returns a fresh list per call. The journal records that
reference, and the function then appends to it. On replay the call is served from the journal and
the append runs again, so the list holds the element twice. Either record a defensive copy of a
mutable collection result, or bring the collection mutation nodes into the journal.

**2. A `TryFinally` runs its finalizer once per attempt.** A pause unwinds as an exception through
the compiled tree, so every enclosing finalizer runs on the way out and again on replay.
`TryCatchAll` is already correct: it rethrows `YieldException` ahead of the catch-all.

**3. Deferred calls need a journal index.** `Expression.DeferredCall` is emitted through the same
`BuildCall`. Without an index, a resumed function starts the warp again on every replay.

## Semantics to document

* **A function is no longer evaluated within a single physics tick.** The tutorial states this twice
  as a headline property. A resumed function spans ticks, and replayed reads return the values seen
  when it started, so its view of the game is internally consistent and grows stale. That is
  inherent to resumption, not to this strategy; a captured stack would hold the same stale locals.
* **A completed side effect is not performed twice.**
* **Pure computation is re-run on each resumption**, which is quadratic in the number of pauses.
  That is fine while pauses are few.
* `Expression.YieldedMessage` currently tells the user to reach for a deferred call. After this it
  applies to streams and events alone, and needs rewording.

## Phases

| Phase | Content |
| --- | --- |
| 1 | `FunctionJournal`, the emission change, `JournalingEvaluator` and `JournalingRunner` |
| 2 | `RunFunction` throwing the wrapped yield, and the three problems above |
| 3 | Documentation, tutorial and changelog |

## Testing

`TestService.BlockingProcedureReturns (n, sum)` pauses `n` times and returns a sum, so the whole
thing is testable in the `ExpressionTest` partial files in `core/test/Service/KRPC/` with no game
running. Assert the value, the number of invocations, and that a side-effecting call placed before
the pause happens exactly once. `core/test/CoreTest.cs` covers the parked continuation against the
`TestServer` harness.

In game, stage and then read the vessels staging produced is the case worth covering, beside an
`AutoPilot.Wait` that spans several ticks.
