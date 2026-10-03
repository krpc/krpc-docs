# Compiling shared nodes once

**Status:** proposal, postponed. A follow-up to server side functions, to be built once that stack
merges. No GitHub issue filed yet.

[`server-side-functions.md`](server-side-functions.md) bounds a function at `MaxNodes` nodes,
counted once per use. This doc is the plan to compile each shared node once, so the bound can go.

## The problem

A tree is built one factory RPC per node, and a client can pass one node to several factories. The
tree is then a DAG. Everything on the server treats it as a tree:

| Step | Where | Cost of a node used in `k` places |
|---|---|---|
| Binding returns, loops and markers | `ReturnFinder`, `MarkerRewriter`, `MarkerChecker`, at factory time | visited `k` times |
| Size check | `NodeCounter`, from `Expression.CheckSize` | visited `k` times |
| Compiling | LINQ `Compile()` | compiled `k` times; an `Invoke` of a `LambdaExpression` is inlined |

A chain where each step uses the step before twice doubles the work at every step. Thirty RPCs
describe 2^30 nodes, and compiling runs on the game's main thread with no way to cancel it.
`MaxNodes` (1,000,000) turns that hang into an error.

The size is not visible in the source. The Python compiler reuses one `Lambda` for every call of a
local function, so local functions that each call the one before twice form such a chain. Python
already assigns a value it uses twice to a temporary, such as a slice's lower bound or a chained
comparison's operands. A shared lambda is the case left.

## Goal

The work on the server grows with the number of distinct nodes, and so with the number of RPCs a
client makes. `MaxNodes` and `CheckSize` are then removed. A program that is large because it has
many nodes compiles; it costs about a microsecond a node, plus the RPCs that built it.

## Design

### 1. Visitors memoize on node identity

`BoundedVisitor` becomes a visitor that keeps a reference-identity map from each visited node to
its result, and returns the stored result on a second visit.

* `ReturnFinder` and `MarkerChecker` visit each distinct node once.
* `MarkerRewriter` maps a shared node to one rewritten node, so its output keeps the sharing of its
  input. A rewriter instance has fixed targets, so one map per instance is correct.
* `NodeCounter` counts distinct nodes, and records how many places use each one. The hoisting pass
  reads these counts.

### 2. Hoisting shared lambdas

A `LambdaExpression` used as the target of more than one `Invoke` is assigned once to a block
variable, and each call invokes the variable:

```
Block([f], Assign(f, Lambda(...)), ... Invoke(f, args) ... Invoke(f, args) ...)
```

* **Placement.** The assignment wraps the lowest node enclosing every use. Every use is in the
  scope of the lambda's free variables, so that node is too.
* **Closures.** A lambda reading an outer variable becomes a closure. LINQ captures the variable by
  reference, so each call sees its current value, as the inlined body does.
* **Cost.** A call becomes a delegate invocation, and a captured variable moves to the heap. Both
  are measured before and after (see "Testing").

This alone removes the blowup from the Python compiler.

### 3. Hoisting shared value nodes

A shared node that is not a lambda is wrapped in a lambda with no parameters, hoisted as above, and
invoked at each use. Each use still evaluates the node, so a procedure call in it runs once per use,
as before.

* **Jumps stay inline.** A node containing a `break`, `continue`, `return` or `goto` whose label is
  outside it cannot move into a lambda, since a jump cannot leave one. It is compiled once per use.
* **Small nodes stay inline.** A node whose subtree is under a few nodes, counting a hoisted node as
  one, costs less to repeat than to call through a delegate. The pass runs bottom up, so a chain of
  small shared nodes is still hoisted once a step's subtree passes the threshold. The threshold is
  set by measurement.

A shared node containing a jump can still form a doubling chain, so a bound remains for that case.
It counts only the nodes that stay inline, and a real program does not come near it.

### 4. Removing the bound

With 1 to 3 in, the nodes compiled are at most the distinct nodes. `MaxNodes`, `CheckSize` and
their tests are removed, along with the size check in `AddEvent`, `RunFunction` and
`AddFunctionStream`. The bound on inline jump nodes from 3 stays, under its own name.

## Phases

Each phase merges on its own. The bound stays until the last one.

| Phase | Change | Effect |
|---|---|---|
| 1 | Memoizing visitors; `NodeCounter` counts distinct nodes and uses | Factory calls are linear in distinct nodes |
| 2 | Hoist shared lambdas | Python local functions compile once |
| 3 | Hoist shared value nodes | Hand-built sharing compiles once |
| 4 | Replace `MaxNodes` with the inline jump node bound | Large programs compile |

## Testing

* The doubling chain tests, which now expect the `MaxNodes` error, go to 30 steps and compile in
  milliseconds. They cover a chain of `Add` nodes, and a chain of local function calls from each
  compiler.
* A shared node calling a procedure runs the procedure once per use, in source order.
* A shared lambda reading a variable that changes between calls, and one declared inside a loop
  body, give the inlined results.
* A shared node containing a `break` stays inline and is still bound to its loop.
* The golden expression-tree tests change where they share a node. The printer gains a way to print
  a hoisted variable.
* A benchmark of a function calling a local function in a loop, before and after phase 2, sizes the
  delegate cost and the threshold in phase 3.

## Open questions

* Whether phase 3 is worth building. Phase 2 covers the compilers, and hand-built trees in Java and
  C++ rarely share interior nodes.
* Whether the inline threshold in phase 3 is a node count or an estimate of compiled size.
