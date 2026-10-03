# Releasing server side functions

**Status:** proposal, postponed. A follow-up to server side functions, to be built once that stack
merges. No GitHub issue filed yet.

[`server-side-functions.md`](server-side-functions.md) keeps every function until the server
stops. This doc is the plan to let a client release the functions it no longer needs.

## The problem

Every factory call returns an `Expression`, and encoding it puts it in the object store. Nothing
takes it out again until the last server stops.

| Held | By | Bounded by |
|---|---|---|
| Interned types and value constants | the store and the constant caches | the service surface and the literals a program writes, so left alone |
| Interior nodes | the store, one entry per factory call | nothing |
| A function's compiled delegate | its root `Expression`, which caches it | nothing |
| A function stream's or event's delegate | the stream | the stream's lifetime |

A client that builds a new function per call, such as `run_function(lambda)` in a loop, grows the
store and the heap without bound. Disconnecting does not help, since the nodes outlive the client.
The tutorial says to compile once and reuse the function, which avoids the cost but does not remove
it.

## Design

### 1. Nodes are owned by the client that built them

An interior node is the creating client's, in a `ClientOwnedObjects` collection, as drawings,
forces and created reference frames are ([`object-lifetime.md`](../object-lifetime.md)). Interned
types and constants are shared between clients, so they stay out of it.

* **Disconnect.** The collection releases a client's nodes when it disconnects. This alone bounds
  growth across sessions.
* **Store and heap.** Releasing a node removes its store entry. The LINQ node goes once nothing else
  holds it: a parent node, a stream or an event.
* **Another client's id.** A node passed to another client out of band stops resolving once its
  owner goes. Drawings and forces behave the same way.

### 2. A client releases a function

`KRPC.RemoveFunction(Expression function)` releases a function and every node built for it.

* **Finding the nodes.** An `Expression` records the owned nodes it was built from, as it is
  created. The LINQ tree cannot be walked back to the wrappers, since a parent holds the child's
  internal node.
* **Shared nodes.** A node that a function the client still holds was also built from stays.
  Ownership counts the roots that reach each node, and a node goes when its count reaches zero.
* **Streams and events.** A function stream or an event holds only the compiled delegate. Removing
  the function leaves it running, and removing the stream or event then frees the delegate.
* **The caller's only.** It refuses a function another client built, through
  `ClientOwnedObjects.RemoveOwnedByCaller`.

### 3. Interior nodes released after a build

A client needs only a function's root once it is built. The compilers can release the interior
nodes right after, keeping one store entry per function. The nodes stay alive through the root.

This is the same procedure applied early, so it needs no server change beyond 2. It costs a round
trip per function, or none if [batched tree construction](batched-tree-construction.md)
carries it.

### 4. Client caching

The Python and C# compilers cache the compiled function for a lambda, so `run_function(lambda)` in
a loop builds one function.

| Client | Key |
|---|---|
| Python | the code object, and the values of the captured variables and globals it reads |
| C# | the lambda's expression tree compared structurally, with captured values evaluated |

* **Captured values.** A captured remote object compares by its id, and a captured collection by
  its contents. A value that is not hashable makes the lambda uncacheable, and it is compiled each
  time as now.
* **Bound.** The cache is a small LRU per connection. Eviction calls `RemoveFunction`.
* **Explicit compiles.** `compile_function` stays uncached. Its result is the caller's to keep and
  remove.

## Phases

| Phase | Change | Effect |
|---|---|---|
| 1 | Client-owned nodes, released on disconnect | Growth bounded per session |
| 2 | `RemoveFunction`, with node reference counts | A long session can release what it built |
| 3 | Compilers release interior nodes after a build | One store entry per live function |
| 4 | Client caching in Python and C# | `run_function(lambda)` in a loop is cheap |

## Testing

* A function built and removed in a loop leaves the store at its starting size.
* A node shared by two functions survives the removal of one, and the other still runs.
* A function stream keeps running after its function is removed, and goes with the stream.
* A disconnecting client leaves no nodes behind, and another client's functions are untouched.
* Removing another client's function is refused.
* A cached lambda reruns with the same function, and a changed captured value builds a new one.

## Open questions

* Whether a function stream or event should own its function, releasing it on removal, so that the
  client makes one call instead of two.
* Whether phase 3 makes the reference counts in phase 2 unnecessary, since a client would then hold
  only roots.
