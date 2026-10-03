# Batched tree construction

**Status:** proposal, not started. A follow-up to server side functions, client-side only, and gated
on measuring real tree sizes first. No GitHub issue filed yet.

[`server-side-functions.md`](server-side-functions.md) builds a function one factory RPC per node.
This doc is the plan to send those calls in batches.

## The problem

Building a tree costs one blocking round trip per node. The Python compiler calls some seventy
distinct factories, and every one is an ordinary generated stub call going through `Client._invoke`,
which hard-codes a single call per `Request`. A compiled function of any real size is therefore
hundreds of sequential round trips.

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

## Design: deferred handles with a level-ordered flush

Have the factory wrappers return a deferred
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

## A cheaper win to take first

`remote_type` (`client/python/krpc/expressionutils.py`) memoizes on
the serialized ptype, in the `client._expression_remote_types` cache every function on a connection
shares. Deduplicating repeated constants is the same shape and is still open. It is worth doing
regardless, and it changes the measurement that decides whether the deferred-handle work is
justified. That measurement should be taken before building it, by counting factory calls for
realistic inputs such as the launch-into-orbit tutorial function and the examples under
`doc/src/scripts/client/python/`.

## Alternatives considered

Intra-request result references, a `oneof` on `Argument` letting a call
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
