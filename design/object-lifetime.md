# Object lifetime, destroyed objects and object-store reclamation

**Status:** in progress. Phases 1 to 14 are built; no PR is raised yet. Phases 15 and 16, the
benchmarking, are a pull request of their own and are not built here; the numbers under
[Performance](#performance) were measured on a build that carried them. Covers issues
[#885](https://github.com/krpc/krpc/issues/885),
[#764](https://github.com/krpc/krpc/issues/764),
[#771](https://github.com/krpc/krpc/issues/771) and the follow-up left open by
[#770](https://github.com/krpc/krpc/pull/770); the approach was agreed on
[PR #894](https://github.com/krpc/krpc/pull/894). It sits on top of the editor scene API
([services/editor-scene-api.md](services/editor-scene-api.md)) and the user interface controls work
([services/ui-controls-and-layout.md](services/ui-controls-and-layout.md)), so it also answers for
the vessel under construction, which is a second kind of thing a part can belong to, and for the
controls and layout objects those add. It settles the reload half of the follow-up the editor scene
API leaves open; see [The vessel in the editor](#the-vessel-in-the-editor).

## Problem

First, a note on terminology. Three different things here are called objects:

| Term | What it is |
|---|---|
| **game object** | What the client means: this part, this vessel, this maneuver node. A concept, not a type. It lasts for as long as the game keeps state for it, whatever the game does with its representation in the meantime. |
| **Unity object** | How the game represents a game object while it is in the scene: a `Part`, a `PartModule`, a `Vessel`, all of them `UnityEngine.Object`s. The game makes and destroys these as it needs them, so several can stand for one game object over its life, and at times none does. `UnityEngine.GameObject` is one Unity type among these; it is not what "game object" means here. Not every game object has one: a science data record is plain state the game keeps, in the scene or not. |
| **proxy** | The kRPC service object a client holds an id for. |

A proxy represents a game object. Most part-related proxies **capture** a Unity object at
construction and hold that instance forever, so what they represent is the instance rather than the
game object. That single decision causes four reported problems:

| Issue | Symptom | Cause |
|---|---|---|
| [#885](https://github.com/krpc/krpc/issues/885) | `Parachute.deployed` throws a bare `NullReferenceException` after the part is destroyed | captured `PartModule`, no liveness check |
| [#764](https://github.com/krpc/krpc/issues/764) | parachute state unreadable after loading a save | captured module belongs to the previous game state |
| [#771](https://github.com/krpc/krpc/issues/771) | memory grows with each quickload | the object store holds proxies forever, and each captured object pins a destroyed part, vessel and part graph |
| [#770](https://github.com/krpc/krpc/pull/770) | the same leak via `CrewMember` | re-deriving from an id fixed that one case; the general case was left open |

Proxies that already store an id and re-derive (`Vessel`, `Part`, `Resource`, `Propellant`,
`CrewMember`) do not have the access bug, but they still accumulate in the object store forever.

The same two causes run through every other service, and through the SpaceCenter classes the four
reports do not name. None of those is in a report, and half of them take a mod to reach at all, but
the code is the same shape: a captured `PartModule` behind an InfernalRobotics servo, a captured
alarm in KerbalAlarmClock, a captured contract, waypoint and comm link in SpaceCenter, a captured
`GameObject` behind every Drawing and UI object. Two are worse than anything in SpaceCenter, because
they are keyed on an object the game or the wrapper builds afresh on every read, so the store takes
an entry per call rather than per game object, and two objects for one thing never compare equal:

| Where | What is keyed on a per-call object |
|---|---|
| `InfernalRobotics.Servo`, `InfernalRobotics.ServoGroup` | the wrapper `IRWrapper` allocates for each servo and group every time one is listed, compared with `==` on an interface type, which is reference equality |
| `UI.RectTransform` | built fresh from `GetComponent` on every read of any `RectTransform` property, and it defines no equality at all |

Two independent halves, and both must be solved:

1. **Access.** Every proxy access must either reach the game state that currently represents its
   game object, or fail with a meaningful, catchable error.
2. **Reclamation.** The object store must drop proxies whose game objects are gone.

## Scope

In scope:

* `KRPC.Service.ObjectStore` and the core service infrastructure.
* Everything SpaceCenter hands out that stands for something the game can destroy: its parts, part
  modules, vessels, maneuver nodes, comm nodes and reference frames, which is where the four
  reported issues are, and its alarms, contracts, waypoints, comm links and close approaches. See
  [SpaceCenter](#spacecenter).
* Every other service that hands out proxies: Drawing, UI, RemoteTech, InfernalRobotics,
  KerbalAlarmClock, LiDAR and DockingCamera. See [The other services](#the-other-services). This
  includes proxies for objects kRPC itself creates and the client explicitly removes, which the game
  destroys anyway when it takes the scene away.

Out of scope:

* Proxies that stand for nothing in the game: the `KRPC` service's own `Expression` and `Type`, and
  the classes listed under [What SpaceCenter leaves out](#what-spacecenter-leaves-out) and
  [What the other services leave out](#what-the-other-services-leave-out).
* The protocol change proposed for [#877](https://github.com/krpc/krpc/issues/877). See
  [protocol/stream-invalidation.md](protocol/stream-invalidation.md); the granular error-per-stream
  design agreed there needs nothing from this work beyond the exception itself.

## Semantics

A proxy object supplies three things:

* Identity: how a proxy uniquely and persistently identifies the underlying game state,
* Access: the operation that obtains the game state backing the proxy,
* Classification: whether the backing game state is live, dormant or destroyed.

Additionally:

* A game-state generation counter records when the game replaces the state that proxies stand for.
* A new `ObjectDestroyedException` is added, to communicate the state of a proxy to clients.
* The object store manages proxy object lifetime based on whether a proxy is in the destroyed state.

### Identity

A proxy is a **value keyed by a stable identifier**, not a handle to a memory location. The
identifier is whatever the game guarantees to be stable for that kind of object, and it is the
only thing the proxy is allowed to store as identity.

Equality and hash codes derive **only** from the identifier, never from a resolved object.
The object store is keyed by the proxy object's equality and hash code, so a hash that changes over
the proxy's lifetime, or that dereferences a destroyed Unity object, corrupts the store.

### Access

A proxy resolves to whatever game state is currently tied to the identifier that it carries.
For example, if the proxy resolves to a Unity game object, and that object is later torn down
and replaced by another equivalent one, the proxy resolves to the new instance rather than the
old stale instance.

The consequence of these semantics for the client is that a proxy obtained before a game-state
change keeps working after it, provided the object it identifies still exists. The proxy never
resolves to data belonging to a replaced game state, which is the #764 bug.

### Classification: Live, dormant and destroyed

The game state that a proxy resolves to is classified into three states, shown in the table below.
These dictate what happens when a proxy resolves its game state. They also determine whether the
object store will remove the proxy object when it does a sweep.

| State | Definition | Access | Reclaimed |
|---|---|---|---|
| live | resolves to game state that is current | normal | no |
| dormant | does not resolve, but the game still holds what it needs to instantiate the state again | throws `InvalidOperationException`, message says the object is not currently loaded | no |
| destroyed | no game state exists | throws `ObjectDestroyedException` | yes |

Failing to resolve is not evidence of destruction, and this is why the dormant state exists. A proxy
identifies a game object, which is what the client reasons about. A Unity object is a scene object, which the
game instantiates only while it needs to simulate or render it. When the game keeps the game
object's state in a persistent form, it can tear the scene object (Unity object) down and rebuild an equivalent
one under the same identifier later, so a game object can be entirely intact with no Unity object
existing for it at that moment. KSP does exactly this for anything outside loading range; see
[Parts](#parts).

Determining a proxy object's classification is up to the service code, since only it knows where the game
keeps the persistent form, and whether a proxy that fails to resolve is dormant or destroyed.

Anything that fails to resolve, where it is uncertain whether the game still keeps state for it, is
dormant. A proxy is reclaimed only when it is definitively gone.

The bias toward dormant is there because the two mistakes do not cost the same. Calling a dormant
object destroyed cannot be undone: the client is told to give up on a game object that is fine,
and the sweep retires its id for good, so the proxy stays dead even once the game instantiates the
object again. Calling a destroyed object dormant only leaves a proxy in the store until a later
sweep, which costs a bounded amount of memory and nothing else.

This bias toward dormant also covers the case where the game does not currently know what exists
at all: a game between states (e.g. during a quick load) lists no vessels, and neither the access
path nor the sweep may conclude anything from that.

A proxy exposes its classification directly, rather than a yes or no derived from it. The sweep is
the only caller that needs less than the full answer, and it can compare against destroyed itself.
Keeping the three states visible means there is one classifier per proxy however many callers it
grows, and dormancy is there for anything else that comes to want it.

Note for Unity objects: a reference is not liveness. A Unity object dies in two stages: `Destroy()` tears down
the native object while the managed wrapper survives until the GC collects it, and Unity's
overloaded `operator ==` reports that wrapper as null while `ReferenceEquals` does not. So a
non-null reference is no evidence that the object is usable, and every check has to go through
Unity's null semantics, never reference equality.

### Game-state generation

The game can replace everything that proxies stand for in a single step: loading a save,
quickloading, reverting, or changing scene. The server records that with a **game-state
generation**, a counter that moves on at every such boundary and so names the state the game is
currently in.

It exists because [Access](#access) requires that a proxy never resolves to data belonging to a
replaced game state, and nothing a proxy holds reveals that a boundary was crossed. A proxy holds
an identifier, and once it has resolved it also holds a direct reference to the game's object,
either cached (see [`CachedObject<T>`](#cached-resolve-cachedobjectt)) or, where the game offers
no stable identifier, as the identity itself (a maneuver node, a comm node). Both outlive the
boundary. The reference stays readable: an instance the game has abandoned need be neither
garbage-collected nor Unity-destroyed, so it passes every liveness check and answers like a live
object while standing for nothing the game simulates any more. The identifier stays valid, and can
name a different object in the new state. So "is this still the state I resolved that in" is a
question only a counter can answer.

Two consequences:

* **Anything a proxy caches is scoped to the generation it was cached in.** A value resolved in an
  earlier generation is resolved again rather than reused, whatever state it appears to be in.
* **A game object that cannot outlive one game state is destroyed once the generation moves on.**
  Where what a proxy stands for is a record in the loaded game, rather than something the game
  rebuilds under the same identifier, a generation mismatch is not a failure to resolve but
  destruction, and there is no dormant state to return to.

The generation is otherwise no part of a proxy's identity. A proxy whose game object survives a
boundary has to keep working across it, which is the whole of the #764 fix, so the counter
invalidates what a proxy caches without invalidating what it is.

The counter is server-internal and never protocol-visible: no RPC exposes it and no client sees it.

Moving the generation on and sweeping the object store are separate steps; see
[Triggering a sweep](#triggering-a-sweep).

### `KRPC.ObjectDestroyedException`

There is **one exception type** shared by every service, rather than a service-specific
`PartDestroyedException` or similar. The condition is not specific to parts,
and other services will want it, so a client catches one thing whatever it was holding.

It is also caught as itself. It stands for nothing in any client language's own exceptions and
is not presented as one, so a client that handles it handles it by name.

This exception is raised when:

 * A client attempts to access a proxy object that no longer exists, as it has been removed from the
   object store by a previous sweep.

 * A proxy is accessed and it is in the destroyed state, which is the case when resolving the game
   state that the proxy identifies finds that the game no longer holds it.

Note that this exception must be raised from **every** member of a destroyed proxy that
reaches into the game, which is every member that has to resolve to answer: reading and
writing properties, calling methods, and members that read game state to build another
proxy from it.

The exception is what resolving raises, so a member that does not resolve does not raise it,
and none is asked to. What is left out is a member that hands back what the proxy was built
from: the part a module belongs to, the name of a field, a stage's number. Each of those is
identity the proxy has held since it was constructed, held by the same rule that keeps
equality and hashing off the game (see [Identity](#identity)), so there is nothing for the
game to have destroyed and nothing to look up. A proxy handed back that way then raises the
exception itself, from the first member of it that resolves.

This should never be raised when hashing or comparing proxy objects. The object store uses those
paths to manage its mapping from proxy objects to ids, and it has to be able to find and remove the
entry for a proxy whose game state is gone, which is exactly when hashing would be tempted to
dereference it. There is no client call there to attribute a failure to either.

If it is known why an object is now gone, a message is included in the exception saying why.

### Object-store reclamation

The object store performs a sweep that drops every proxy reporting its game state as destroyed.
Proxies opt in through a service-agnostic `IGameObjectState` interface; anything not implementing it is
never swept, so the change is additive per class.

The sweep runs at game-state boundaries: after a game state is loaded or replaced (quickload,
loading a save, reverting) and on scene changes. It also runs when the game destroys something a
proxy may stand for, such as a part or a vessel, so an obviously dead proxy does not have to wait
for the next boundary. It is never run on a timer, so it cannot cause periodic frame-rate hitches,
and a boundary is already a multi-second stall.

Proxy ids are never reused by the object store. It allocates monotonically, so it can distinguish
an id it once issued and has since reclaimed from an id that was never valid.

| Lookup | Meaning | Result |
|---|---|---|
| id present | live proxy | the proxy |
| id absent, below the high-water mark | issued, then reclaimed | `ObjectDestroyedException` |
| id at or above the high-water mark | never issued | `ArgumentException` |

Without this, a client that holds an id across a quickload gets `ArgumentException: Instance
not found`, which reads like a client bug rather than "the thing you had is gone". The two
ways a proxy can die, reclaimed by the sweep or still present but unable to resolve, then look
identical to the client.

Note: the object store might not be the only location that a proxy object is stored. An active
stream could reference a proxy object. If the proxy object is in the destroyed state, it continues
to exist attached to the stream, and raises `ObjectDestroyedException` the next time the stream is
updated. The server sends that error to the client exactly once and then removes the stream, per
[protocol/stream-invalidation.md](protocol/stream-invalidation.md).

#### Triggering a sweep

When a game event (such as a quickload) is detected, the server **asks** for a sweep rather than
immediately running one. This splits the game state boundary into two calls: `GameState.Changed`
marks a sweep pending and moves the generation on, and `GameState.Sweep` runs the sweep from the
first server update where the game state has settled.

The generation has to move at the boundary itself; the sweep must not. For example, when a scene
change starts the game's vessel list is empty, and it fills over the following frames. A sweep
must run after the vessel list has stabilized.

"Stabilized" is a count that has stopped changing, since the game offers no event for having
finished. In an editor the vessel list is beside the point and is empty on a save with nothing in
flight; what settles there is the part count of the vessel the editor has open, which is rebuilt a
part at a time in the same way. Without that, a sweep landing in the middle of a craft being
reloaded would see every part of it as absent and drop the proxies for the very parts about to
come back.

Only counts taken since the sweep was asked for say anything about whether the game has finished.
A count left over from an earlier sweep can equal the first count of this one by coincidence, which
would report a state that has not begun to settle as settled, so the count is forgotten whenever no
sweep is due.

Destruction events ask for a sweep, but do not move the generation on. Nothing has been rebuilt, so
nothing a proxy resolved before the event has to be resolved again. One sweep also covers a whole
vessel coming apart, which destroys many parts in a single moment.

The access path needs the same guard, which this design first stated for the sweep alone. A vessel
missing from a list that is still being filled is not destroyed; it is one the game has not rebuilt
yet, and a client calling in those frames, or a stream updating in them, would otherwise be told
that its vessel is gone for good. Guarding only against a wholly empty list is not enough, because
the list holds some vessels for most of the window. `GameState.Settled` therefore carries the
answer to both sides: false from `Changed` until the sweep that follows it, and read by
`FlightGlobalsExtensions.VesselsKnown`, which is what decides between destroyed and dormant for a
vessel and for a part in flight.

## Infrastructure

The following general infrastructure is provided for services to use, to implement semantics above
for proxy objects that a service defines. One piece per part of the semantics:

| Semantics | Infrastructure |
|---|---|
| [Identity](#identity) | `Equatable<T>`, and the rule that only the identifier feeds it |
| [Access](#access) | the accessor shape, and `CachedObject<T>` where resolving directly is expensive |
| [Classification](#classification-live-dormant-and-destroyed) | `GameObjectState` and `IGameObjectState` |
| [Game-state generation](#game-state-generation) | `GameState` |
| [`KRPC.ObjectDestroyedException`](#krpcobjectdestroyedexception) | one type in core, raised by the classification |
| [Object-store reclamation](#object-store-reclamation) | `ObjectStore`: the sweep, and ids that are never reused |

### The shape of a proxy

Every proxy that participates has the same shape, whatever it stands for: it stores its identifier
and nothing else that identifies it, equality and hashing read only that, every member reaches the
game through one accessor, and one property answers the sweep.

```csharp
readonly Identifier id;      // identity: all that equality and hashing use
CachedObject<T> cache;       // optional, where resolving directly is expensive

public override bool Equals (Proxy other) { return id == other.id; }
public override int GetHashCode () { return id.GetHashCode (); }

T Internal {                 // every member reaches the game through this
    get {
        var obj = cache.Get ();
        if (obj != null)
            return obj;
        obj = Resolve (id);            // the service's lookup
        if (obj == null)
            throw NotResolvable ();    // destroyed, or merely not loaded
        cache.Set (obj);
        return obj;
    }
}

public GameObjectState GameObjectState {   // live, dormant or destroyed
    get { ... }
}
```

A proxy derives from `KRPC.Utils.Equatable<T>` in core, which supplies `Equals (object)`, `==` and
`!=` from the two members above, so those two are all a class writes. Neither may resolve, and
neither may touch a resolved object: they run while the store is looking an entry up, including the
sweep's own removal of a proxy whose game state is gone, which is exactly when a resolve would
fail. That is the shape behind the rule that the exception is never raised from hashing or
comparison.

Only two things in the accessor are the service's own. `Resolve` is its lookup, and whatever
decides between the two exceptions `NotResolvable` chooses from is its classification, which is
also what `GameObjectState` returns. The rest is shared: the classification's shape and the
interface it is exposed through, the game-state generation, and the cache.

### The classification: `GameObjectState` and `IGameObjectState`

**A class has exactly one classifier**, and exposes it as it is: a `GameObjectState` property
returning the enum of the same name, one of `Live` / `Dormant` / `Destroyed`. It answers for the
game object the proxy stands for, in the sense the [terminology](#problem) gives that term and not
`UnityEngine.GameObject`, which is what both callers want to know:

 * an access that failed to resolve asks it what to throw, `ObjectDestroyedException` for destroyed
   and `InvalidOperationException` for dormant;
 * the sweep removes the proxy when it reads `GameObjectState.Destroyed`.

The name avoids `State`, which a dozen service classes already expose as an RPC of their own,
`Parachute`, `Antenna`, `SolarPanel` and the rest, a name a shared interface cannot take from a
service that is entitled to it.

Both the enum and the interface exposing it, `KRPC.Utils.IGameObjectState`, live in core. The three
states are general, [Classification](#classification-live-dormant-and-destroyed) defines them
without reference to any game, and what stays the service's own is deciding which of them applies,
never what they mean.

The rest of the interface's contract is what makes a sweep over the whole store safe:

| Rule | Why |
|---|---|
| implementing it is opt-in | additive per class, and what a class that does not implement it gets is the behavior of today: never swept, always usable. Anything not yet reasoned about falls back to that |
| `Destroyed` means definitively gone; anything less certain is `Dormant` | the two mistakes do not cost the same, per [Classification](#classification-live-dormant-and-destroyed). The store removes on one value only, so the conservative answer is the implementer's to give |
| it must not throw | one pass calls it on every entry in the store. The sweep catches one that does anyway and keeps the proxy, because several implementations reach into a mod's API through reflection and one that breaks the rule must not stop the rest of the store being checked |

**The state getter goes on everything, whether or not the class re-derives.** The sweep reclaims
only what opts in, so a class left out accumulates in the store for the whole session however well
its accesses behave, which is the half of #771 that re-derivation does not touch. A proxy that
already resolves correctly, and one whose access path is left exactly as it is because a cheaper
lookup would buy nothing, both still need it.

Classification is off the fast path by construction. It runs only once a resolve has already
failed, or from a sweep at a load boundary, so it may search as widely as it needs to. Searching
every persistent form the game keeps, to prove nothing holds the object before calling it
destroyed, is affordable exactly because nothing reaches that code on a working access.

The exception is a caller that asks on every update rather than on a client call: a force being
applied to a part, and a resource transfer running between two. A `Part` therefore answers live
straight from its cache, since a part looked up in this game state and still there is the part,
and only falls through to the search on a miss. That holds in flight alone. A part in an editor
belongs to the vessel it was taken from, and one of a vessel the editor has loaded over is gone
however alive the game object it was still is; see
[The vessel in the editor](#the-vessel-in-the-editor).

A proxy with no existence of its own does not classify itself, it defers: one that only names
something reached through another is exactly as live, dormant or destroyed as its owner. Where it
is built on several, which of them it needs decides how they combine, and `GameObjectStates` in
core supplies both:

| It needs | Combines with | Example |
|---|---|---|
| all of them | `LeastAlive` | a `ReferenceFrame`, which is defined against every one of them; a `ResourceTransfer`, which needs both its parts |
| any of them | `MostAlive` | a `Parachute`, carried by a stock module, a RealChutes one or both; a `Radiator`; a `Thruster` |

The enum is ordered live, dormant, destroyed for this: combining is a comparison, not a table.

### Game-state boundaries: `GameState`

`KRPC.Service.GameState` in core carries the state a boundary changes, and the server addon is what
tells it about one, since only the addon sees `GameEvents`.

| Member | Called by | Does |
|---|---|---|
| `Changed` | the addon, when a game is loaded, quickloaded or reverted, and on a scene change | moves `Generation` on, clears `Settled` and asks for a sweep |
| `RequestSweep` | the addon, on a destruction event (`onPartDie`, `onVesselDestroy`); a collection of client-owned objects, on letting one go | asks for a sweep, leaving the generation alone: what was destroyed is gone, but nothing has been rebuilt for a cache to look up again |
| `Sweep` | the addon, from the first server update where the game has stopped adding vessels | runs the sweep, clears `SweepPending` and sets `Settled` |
| `Generation` | a proxy caching something it looked up, or classifying something that cannot outlive one game state | a `uint` that identifies the current game state |
| `Settled` | an access path deciding whether the absence of a game object means it is gone | whether the game has finished building the state it moved to |

Why a boundary asks for a sweep instead of running one is in
[Triggering a sweep](#triggering-a-sweep). The two uses of `Generation` are the two consequences in
[Game-state generation](#game-state-generation), and both cost a `uint` comparison: a cache
ignores a value stamped with any generation but the current one, and a proxy whose game state
cannot outlive the one it was read from is destroyed as soon as they differ, with no search
either way.

### Cached resolve: `CachedObject<T>`

Resolving an identifier directly can be expensive. A vessel id costs a search of every vessel in
the game, and a part's flight id a search of the parts of every loaded vessel, both linear in the
size of the scene, on getters a stream re-evaluates every fixed update. `CachedObject<T>` is what
makes that a field read instead: a proxy keeps its identifier plus a **weak reference** to the
object it last resolved, stamped with the **generation** it resolved in.

| Rule | Why |
|---|---|
| the reference is weak | a strong one pins a destroyed part, its vessel and its part graph, which is #771 exactly |
| a reference from another generation is ignored | a weak referent can be neither collected nor Unity-destroyed and still be the wrong object, because it belongs to a replaced game state while its identifier now denotes something else. That is #764 |
| the Unity null check is made against `UnityEngine.Object`, never the type parameter | `==` on a type parameter is reference equality, which hands back a torn-down object |
| a miss re-resolves, re-caches, and classifies a failure to resolve | the cache is an optimization, never the thing that decides anything |

It is a struct field on the proxy rather than a wrapper it calls through, and it is
**delegate-free**: indirection costs more here than it saves, so a proxy costs one extra allocation
rather than three and the resolve stays inline in the accessor. It is typed on `UnityEngine.Object`,
which gets DRY and the inlined null check both.

Caching is worth it only where the lookup it avoids costs more than the cache read. Reading the
weak reference is ~23 ns, against 113 ns for a part lookup on the reference craft and 516 ns on a
321-part station, so the part path caches; a lookup that is a walk of one part's module list costs
less than that and so does not. The numbers are under [Performance](#performance).

### The object store: `ObjectStore`

The store already maps proxies to ids in both directions, keyed on the proxy through the equality
and hash the shape above fixes. It gains the two operations reclamation needs, both in core and
neither knowing anything about a game:

| Operation | Does |
|---|---|
| `Sweep` | one pass over the entries, removing each whose proxy is an `IGameObjectState` reporting `Destroyed`, and returning how many went. An entry whose proxy does not implement the interface is skipped, which is what makes participation opt-in |
| id allocation | strictly increasing, never reused, so the next id to be issued doubles as a high-water mark |

Emptying the store, which resets that counter and so is the one thing that can hand an id
out twice, happens when the last server stops rather than when any one of them does. Several
servers share the store and draw ids from its single sequence, so stopping one while another
is running would retire every id the running one's clients hold.

A lookup then tells the two failures apart with no tombstone table, since an id below the
high-water mark that is not in the store is one the store issued and has since reclaimed. That is
the [reclaimed-id table](#object-store-reclamation): present, reclaimed and never issued are three
distinguishable cases, and only the last is a client error.

Removal goes through the proxy, so a proxy whose hash has moved since it was added cannot be found
and cannot be removed. That is why the hash rule is a rule and not a preference.

### Where each piece lives

`core` does not reference `UnityEngine` (its only deps are `Google.Protobuf` and
`KRPC.IO.Ports`), and the "destroyed but not yet collected" check *is* Unity's overloaded
`operator ==`. That constraint splits the work across the assemblies:

| Piece | Where | Why |
|---|---|---|
| `ObjectDestroyedException` | core, `KRPC` service | protocol-visible, service-agnostic; thrown directly, with no `MappedException`, since it corresponds to no BCL exception |
| `IGameObjectState` and `GameObjectState` | core utils | the store must not know about KSP, and the three states are general enough for core to own: what a service decides is which one applies |
| store sweep + reclaimed-id semantics | core | store lives there |
| `GameState` | core, driven by the server addon | the store and the caches both need the boundary; only the addon sees `GameEvents` |
| the `GameObjectState` properties | **service layer** | which persistent forms a game keeps, and so which state a proxy is in, is the service's to decide |
| `CachedObject<T>` | **service layer**, typed on `UnityEngine.Object` | a core version has to call back into the service to test the object, which costs an indirection on the hottest path in the mod |
| `ModuleRef` | SpaceCenter | KSP specific |
| `ClientOwnedObjects.RemoveDestroyed` | server assembly | it is one more operation on the collection every addon holding client-owned state already uses, and only that assembly and the services see both it and `IGameObjectState` |

`CachedObject<T>` and `ModuleRef` stay internal to SpaceCenter. No other service resolves anything
of its own: each reaches the game through a `Part` or a `Vessel`, which is public and does its own
resolving and caching.

## SpaceCenter

What the infrastructure needs from a service, per kind of game object: what identifies it, what
resolving that costs, and how its state is decided. The first eleven kinds are what a client reaches
through a vessel or a part; the rest are the records the game keeps for the loaded game, and two
objects defined against others.

| Kind | Proxy classes | Identity | Resolved by |
|---|---|---|---|
| [vessel](#vessels) | `Vessel` | the game's vessel id, a `Guid` | a search of every vessel in the game, loaded or not |
| [part](#parts) | `Part` | the part's flight id in flight, its craft id in the editor | a search of the parts of every loaded vessel, or of the vessel the editor has open |
| [part module](#part-modules) | `Module` and ~28 module proxies (`Engine`, `Parachute`, `Thruster`, `Experiment`, `ResourceConverter`, `Antenna`, `Sensor`, `Light`, ...) | its part, the module's class name, and which occurrence of that class it is | the module found last, or `part.Modules[id]` for the id the game knows it by, or counting the part's modules of the class |
| [field, event, action](#a-modules-fields-events-and-actions) | `PartField`, `PartEvent`, `PartAction`, `ActionGroupAction` | its module, and the name the game gives it | a lookup by name on the module, or nothing at all for the record of one assigned to an action group |
| [named against a vessel or a part](#anything-named-against-a-vessel-or-a-part) | the parts collections, `AutoPilot`, `Control`, `Comms`, `Flight`, `Orbit`, `Resources`, `Resource`, `Propellant`, `Stage`, `ResourceTransfer` | that vessel's or part's identity, plus whatever picks it out among its siblings: a resource id, a stage number | resolving the owner |
| [maneuver node](#maneuver-nodes) | `Node` | nothing the game offers, so the node object itself, plus its vessel's id | nothing to resolve |
| [crew member](#crew-members) | `CrewMember` | the kerbal's name | a search of the game's roster |
| [reference frame](#reference-frames) | `ReferenceFrame` | the identities of everything it is defined against | resolving each of them |
| [comm node](#comm-nodes) | `CommNode` | nothing the game offers, so the node object itself | nothing to resolve |
| [science data](#science-data) | `ScienceData` | its part, its experiment module, and the record itself | nothing to resolve for the record; its owner resolves |
| [science subject](#science-subjects) | `ScienceSubject` | the subject id, within one game state | nothing to resolve; the generation is compared |
| [alarm](#alarms) | `Alarm` | the alarm's id, a `uint` the game writes into the save | asking the alarm scenario for the id |
| [contract](#contracts) | `Contract` | the contract's guid, which the game writes into the save | a search of the contracts the system lists, running and finished |
| [contract parameter](#contracts) | `ContractParameter` | its contract, and the indices that lead to it | walking the contract's parameters from the top |
| [waypoint](#waypoints) | `Waypoint` | the waypoint's navigation id, a `Guid` it is given when it is built | a search of the waypoint manager's list |
| [comm link](#comm-links) | `CommLink` | the vessel whose control path it is a hop in, and the two nodes it joins | a walk of that vessel's control path as it stands |
| [close approach](#close-approaches) | `ClosestApproach` | the two orbits and the time, all held as values | nothing to resolve; its orbits resolve |

**Not every kind is covered**, and nothing has to be: a class that does not implement
`IGameObjectState` behaves as it does today, always usable and never swept, which is the right
answer wherever what a proxy stands for cannot be destroyed. See
[What SpaceCenter leaves out](#what-spacecenter-leaves-out).

### Vessels

`FlightGlobalsExtensions.GetVesselById` searches every vessel in the game, loaded or not, so a
`Vessel` proxy resolves regardless of load state, and the resolve is cached. Load state gives it no
dormant state: it either resolves or the vessel is gone, so finding nothing throws
`ObjectDestroyedException` rather than the `ArgumentException` a failed lookup would otherwise
raise. The one exception is the between-states window, where the game lists no vessels at all
(`FlightGlobalsExtensions.VesselsKnown` is false) and nothing can be concluded from a vessel being
absent, which is dormant like any other uncertainty. Everything reached through a vessel resolves
that way, so they all want that answer.

### Parts

`FlightGlobals.FindPartByID` scans `FlightGlobals.VesselsLoaded` only (verified from the
`Assembly-CSharp.dll` disassembly), so a part resolves exactly while its vessel is **loaded**, and
the resolve is cached. Loaded and packed are independent states (see
[services/vessel-physics-range.md](services/vessel-physics-range.md)): a loaded but packed vessel
is on rails and still has its `Part` objects, so its parts resolve normally. An **unloaded** vessel
has no `Part` objects at all, only a `ProtoVessel` snapshot, so its parts are **dormant**, and the
classifier finds them by searching the proto-part snapshots of every unloaded vessel. Destroyed is
what is left: no live part and no snapshot.

A failed lookup returning null, with every member then dereferencing it, is the `Part` half
of #885. Resolving, classifying the failure and throwing for it is what closes it.

A part in the editor is a different game object reached through the same proxy, and is identified
and classified differently; see [The vessel in the editor](#the-vessel-in-the-editor). `PartId`
holds which of the two a proxy names, so `Part` itself only caches and throws.

### The vessel in the editor

The editor holds one `ShipConstruct`, which is not a `Vessel` and whose parts have no flight id:
the game assigns one only when a vessel is launched. What it does give them is a **craft id**,
which it writes into the craft file and restores whenever it builds the vessel again, so the id
outlives the reload and the undo that both destroy every part and build them anew. A proxy taken
in the editor names its part by that, and one taken in flight names its part by the flight id;
neither id means anything in the other scene, so `PartId` records which kind it holds and resolves
accordingly.

The id outliving the rebuild is not by itself enough to name a part, because it says nothing about
which vessel it belongs to; see [Which vessel a craft id belongs to](#which-vessel-a-craft-id-belongs-to).
That is what separates the undo, where the proxy keeps working, from the reload, where it does
not.

There is no dormant state in the editor. The editor has exactly one vessel and no persistent form
of anything outside it, so a part it does not have is **destroyed**, not out of range, and leaving
the editor destroys the vessel and everything in it. The one uncertainty is an editor that has not
finished starting up and has no vessel yet, which says nothing about any part and is dormant, per
the bias in [Classification](#classification-live-dormant-and-destroyed).

`EditorExtensions` answers in one place what the game holds for the vessel in the editor, which
vessel that is, and how to reach it.

| Situation | State |
|---|---|
| the editor has the part in the vessel the proxy was taken from | live |
| the editor has that vessel, and the part is not in it | destroyed |
| the editor has loaded another vessel over the one the proxy was taken from | destroyed |
| an undo or redo has rebuilt the vessel, and it still has the part | live |
| an undo or redo has rebuilt the vessel without the part | destroyed |
| an editor scene is loaded but has no vessel yet | dormant |
| no editor scene is loaded | destroyed |

#### Which vessel a craft id belongs to

A craft id is unique only within one vessel, and it is saved into the craft file, so a craft file
saved from another carries its ids over. That makes a clash between two vessels the normal case
rather than a remote one: across the 44 craft the SpaceCenter test suite ships, 50 craft ids appear
in more than one file, and **every one of those names a different part in each**. `ActionGroups`
was saved from `Basic` and carries all nine of its ids. Resolving by craft id alone, a proxy taken
in one and used after the other is loaded silently returns the part of the new vessel that answers
to the old id, with nothing to say the answer came from a vessel the client never asked about;
confirmed in game.

So a proxy taken in the editor also records **which vessel** it was taken from, as a ship
generation the editor keeps, and a part of any earlier vessel is destroyed rather than resolved.
What counts as a new vessel is the `ShipConstruct` object being a different one, read from the game
rather than waited for as an event, with one exception below for undo.

##### Why not the persistent id

`persistentId` is the game's own globally unique part id, it is in the craft file too, and it is a
far better discriminator: of the 44 craft, 9 persistent ids appear in more than one file and **none
of them names a different part**. It cannot be used, because the game regenerates it every time it
builds a ship: measured in game, a part keeps its craft id across a reload 9 times out of 9, and
its persistent id 0 times out of 9. An id that changes whenever the vessel is rebuilt cannot name a
part across a rebuild at all.

##### Undo is not a new vessel

An undo, and a redo, restore the vessel from the game's own backup rather than from a craft file,
and hand back a `ShipConstruct` of their own: measured in game, the vessel object is a different
object afterwards. The parts it builds carry the craft ids they had, so a part the undo did not
touch is the same part. Treating the object changing as a new vessel would therefore throw away
every part proxy on every undo, which is exactly what a script editing a vessel cannot afford.

An editor ship addon hears `onEditorUndo`, `onEditorRedo` and `onEditorRestoreState` and marks the
next vessel as restored rather than new, so the generation adopts it without moving on. A part the
undo took away is then simply not in the vessel and is destroyed by the ordinary rule; nothing has
to know which parts an undo affected. Parts are not expected to survive an undo followed by a redo.

The handlers are **instance** methods, and have to be. `EventData.Add` wraps the delegate in an
`EvtDelegate` whose constructor reads the target the delegate was made over and raises a null
reference when there is none, which throws out of whatever registered it. A static handler
therefore looks from the outside exactly like an event that never fires.

##### The trade this forces

An id that survives a rebuild has to come from the craft file; an id that cannot clash has to come
from the running game. No id is both, and no structural check separates the two cases either:
`Basic` and `ActionGroups` have the same nine parts, with the same names, the same craft ids and
the same tree, differing only in action group configuration. There is nothing to compare.

So a part of a vessel the editor has loaded another vessel over is **destroyed**, whether or not
the vessel loaded was the same craft file. Nothing tells a reload from a replacement, and the safe
answer is the same for both. Reloading a craft therefore invalidates the part proxies taken before
it, which is the reload half of the follow-up left open by
[services/editor-scene-api.md](services/editor-scene-api.md), settled against surviving the reload.

### Part modules

A module and its part are components of the same `GameObject`, so destroying the part destroys its
modules. A module proxy inherits its part's classification and needs no separate persistent-form
search: it is destroyed or dormant exactly when its part is, and live while a live part still has
the module. The implication runs the other way too, a module that is not
Unity-destroyed proves its part is not either, which is what lets a resolved module answer for
both without the part being resolved at all.

Every module proxy captures its module, which is the rest of #885 and all of #764. `ModuleRef`
replaces the captured reference. A module proxy is keyed on its part, the module's class, and which
of the part's modules of that class it is. The game rebuilds a part's modules in the order its
configuration lists them, so that outlives any one of them, which is why it is what equality and
hashing use, and why `Module` hashing the captured `PartModule` has to go.

The search that identity implies is not what gets paid. A reference also keeps **where in
`part.Modules` the module was** and the **persistent id** the game knows it by, and an access is a
look at that one position: what is there is the module exactly when it carries the id. No proxy
walks a module list, and none allocates, on a normal access. A proxy that found no module when it
was built, an engine with no gimbal, answers null without looking at anything.

The position is a hint; the id is what makes reading it safe. `PartModuleList` offers nothing that
changes when its contents do, so a hint checked against the list's length and the class at the
position cannot see a change that leaves the length alone, one module added and another removed
between two accesses, which leaves the right class at the remembered position while renumbering the
occurrences. That is exactly the parts carrying several modules of one class (multi-mode engines).
The id is the game's own name for a module, unique among the modules of a part, so checking it is
one `uint` comparison and cannot be fooled.

A miss looks the id up along the list, which is exact wherever the game knows the module by one.
Where it does not, counting the part's modules of the class answers instead, and settles the id and
the position again for next time. That fallback is not optional:

| Fact | Consequence |
|---|---|
| `PartModule.PersistentId` returns a raw field that is **0** until something asks for it. `GetPersistentId()` is what generates one, from a fresh `Guid`'s hash, regenerating until it is unique among the part's modules | a reference asks for one as soon as it finds a module, and never looks up an id of 0, which would match the first module that has been given none |
| `PartModule.Save` writes the id only when it is nonzero, `Load` reads it back, and `ProtoPartModuleSnapshot`'s constructor saves the module as the vessel unloads | an id given out while the vessel was loaded is in the snapshot, so a part torn down and built again carries the same one, and the id finds the module |
| a game state written before the id was given out holds none. No `MODULE` node in a stock KSP save has a `persistentId`, where every `VESSEL` and `PART` node does | loading such a state, a quickload to a save the client predates, leaves nothing to look the module up by, and only the class and the occurrence can answer |
| uniqueness is enforced when an id is generated, never when one is loaded | what carries the id has to be of the reference's class before it is taken to be the module |

Asking for an id writes it into the save file, so a read-only client call has a side effect on the
game state. That is what the game does with it itself: `ModuleRoboticController` stores a (part id,
module id) pair per controlled field and rebinds through `part.Modules[moduleId]` in
`Expansions.Serenity.ControlledBase.AssignReferenceVars`. Nothing in KSP ever reassigns a module's
id.

Every change to a part's module list is then something an access notices rather than something it
can be caught by: the position stops carrying the id, and the lookup that follows finds the module
wherever it moved to, or reports it gone. What it costs is a walk of the list, once, until the next
change; see [Open questions](#open-questions).

There is a third outcome, where the id answers to nothing and the count is what decides. A module
removed from a part carrying several of its class renumbers the occurrences of the rest, so the
reference for the one that went finds the module that has taken its place rather than reporting it
gone. That needs a part's module list to change at runtime with ids already given out, which
nothing in KSP does, and the count is what has to answer wherever the game knows a module by no id
at all.

A proxy standing for several modules holds a reference to each rather than a list of the modules:
`Engine` keeps one per mode, and `ResourceConverter` one per converter, in the order its index
arguments count in. A list of modules is the same captured reference in another shape.

`Decoupler` was to keep its access path as it is and take the state getter only, deferred to its
part, on the grounds that its per-access cost is already reflection inside a compatibility wrapper
shared with `PartExtensions.DecoupledAt`, so a cheaper module lookup buys nothing. **That was
wrong, and the implementation takes a `ModuleRef` like the rest.** The argument was about cost and
missed what the reference is actually for. The wrapper resolves the module once, in its
constructor; it uses reflection for the module's *members*, not to find it. So the proxy held a
module from one game state, and a load left it:

 * comparing unequal to a freshly obtained `Decoupler` for the same part, and hashing differently,
   because both used the module instance. The store then kept one entry per load, which is the
   accumulation this work exists to end.
 * reading the destroyed module. `Decoupled` and `Impulse` returned the values it had before the
   load, with no error, and `Decouple` threw out of the reflected call.
 * reporting itself live throughout, since the state getter deferred to the part, and the part
   really was alive.

Deferring the state getter to the part is only sound for a proxy that re-derives; for one holding a
captured module it reports the opposite of the truth. Wrapping whichever module the reference
resolves to costs one small allocation per access, which is nothing beside the reflection the
wrapper does anyway.

### A module's fields, events and actions

`PartField`, `PartEvent` and `PartAction` are named by their module plus the name the game gives
them, and resolve by a lookup by name on the module. Their state is the module's, so they
are as live, dormant or destroyed as the part underneath.

`ActionGroupAction` is the record that an action is assigned to an action group. It carries the
part, the module, and the action's display name and non-localized identifier, all as values,
with nothing of its own to resolve. It takes the state getter, deferred to its module, and to
its part where it has no module: the Extended Action Groups mod can assign an action defined on
a part rather than on one of its modules, which is also why the module is left out of its hash.

### Anything named against a vessel or a part

`Control`, `Comms`, `Flight`, `Orbit`, `Resources`, `Resource`, `Propellant`, `AutoPilot`, `Stage`,
`ResourceTransfer`, the parts collections and the rest have no existence of their own: each is
exactly as live, dormant or destroyed as the vessel or part it was reached through, and each
resolves by resolving that owner and then picking itself out with a resource id, a stage number or
nothing at all.

`Stage` names its vessel by id rather than holding the KSP vessel, so resolving is a lookup by
that id. Reading `.id` off a captured Unity object inside `Equals` is the one thing
[Identity](#identity) forbids.

`Orbit` is one of these, and the game rebuilds an orbit with the thing that has it, so an orbit
asks its owner for it on each access rather than holding the one the owner had. What it is, is
whose orbit it is, so that is also its identity, and the store hands back one object for a
vessel's orbit however often it is asked for. A patch is the exception: it is an orbit the object
follows on to rather than the owner's own, and the game offers nothing to ask for it by, so a
patch holds the KSP orbit and is identified by it, while still taking its state from the owner.

Three of these can be named against the vessel in the editor instead: the parts collection,
`Resources` and `Stage`. That vessel has no id, so each carries a flag saying it is the editor's
and takes its state from [The vessel in the editor](#the-vessel-in-the-editor) rather than from a
vessel lookup. Judging them by an absent vessel id would find no such vessel and drop every one of
them at the first sweep. `Resources` has a third case, a single part's, which answers from that
part, in flight as much as in the editor.

`ResourceTransfer` is the one of these that runs on its own. Its update is driven by the game's
fixed update rather than by a client call, so there is nobody to raise the exception at, and it
reads its parts' states instead of resolving them: a destroyed part cancels the transfer, since
nothing can move into or out of it again, and a part whose vessel the game has unloaded is
neither gone nor being simulated, so the transfer waits for it. Otherwise a transfer over a part
the game destroyed throws on every update and never completes.

### Maneuver nodes

The game offers nothing to identify a node by, so a `Node` is live while the vessel still lists it
in its flight plan and destroyed once it does not. Removing a node and loading a game state both
leave the vessel without that node for good, so there is no dormant state to return to. When the
flight plan cannot be consulted at all, which is the case for any vessel the game is not solving
conics for, nothing can be concluded and the answer is dormant.

This is where hashing matters most. The proxy holds the node's own object and hashes its identity,
which means it must hold it for its whole life and never let go, even once the node is removed;
whether the vessel still lists the node in its flight plan is what both the access path and the
sweep ask instead. Nulling the field on removal is the bug to avoid: the hash changes with it, and
the store can then no longer find the entry to remove. Holding the object is only safe because
reclamation takes the proxy with it.

### Crew members

A `CrewMember` is named by the kerbal's name and resolves by a search of the game's roster. A
kerbal is live while the game still has them on it. A game that has not been loaded has no roster
to look in, which says nothing about anyone, so that is dormant.

### Reference frames

A frame is as alive as everything it is defined against: its vessel, part, maneuver node, thruster
or parent frames, and for a hybrid frame each of its components. A frame defined against a
celestial body alone never dies, and neither does one defined against a constructed orbit, which
names nothing the game can destroy. The frames on a constructed orbit are still a new producer of
retained proxies, and are reclaimed with the orbit they belong to rather than on their own; see
[constructed orbits](#constructed-orbits).

`DockingPort.ReferenceFrame` captures its `ModuleDockingNode` and so can still raise a raw
`NullReferenceException`. Giving part-relative reference frames the same id-based re-derivation the
other part frames use closes it.

### Comm nodes

Nothing identifies a comm node, so the proxy holds the game's own object, and it is live while that
object still has its scene presence: its transform is either absent or not Unity-destroyed, which
is the two-stage death of a Unity object written out in one line. As with a maneuver node, holding
the object is safe only because reclamation takes the proxy with it.

### Science data

A record is named by its part, its experiment module and the record object itself, which nothing
identifies. The owner is what answers for it: the record is alive while the experiment module is,
and, where the part is live and the module can be asked, while that module still lists the record
among its data.

### Science subjects

A science subject is named by an id, but only once the game has banked science against it; one that
has not been researched yet is built on the spot and the game keeps nothing to look it up by. What
it stands for is a record in one game's science database, so the proxy is live while the game state
it was read from is the loaded one, and destroyed once that state has been replaced. Comparing
`GameState.Generation` is the whole of both the access check and its state, so it costs a `uint`
comparison and no search.

The subject is also looked up by its id on each access, falling back to what the proxy was built
from. Dedup and a held object do not go together otherwise: the game builds a subject nothing has
been banked against on the spot, so the first read of one takes a throwaway, and every later read
is deduped onto that proxy and would go on reporting no science after some had been banked.

`ScienceSubject` also needs an identity, having none today, so that the store dedups it instead of
taking a new entry per read. That identity is the subject id **and** the generation it was read in,
which is stable for the proxy's life because both are fixed at construction. A subject read again
after a load is a new proxy rather than the old one rebound, and the old one is swept: what it
stands for is a record in the replaced game's database, not the thing the new game has under the
same id.

The science gain multiplier that `Science` and `ScienceCap` scale by is read on each access
rather than captured when the proxy is built. It is a setting of the loaded game, which the
player can change while the game runs, so a captured one is a second thing the proxy holds
that the game can move on from, in the same way a captured Unity object is.

### Alarms

`Alarm` already looks its alarm up by id on each access, and the id is durable: `AlarmTypeBase`
writes it out and reads it back, which is why it also survives the game destroying and rebuilding an
alarm when the player edits one. Two things are missing. A lookup that finds nothing leaves the
object using the alarm it found last, so an alarm the game no longer has still answers, out of a
game state that may since have been replaced. And nothing classifies the object, so it stays in the
store for the session.

One change covers both: resolve by id on every access and take finding nothing as the answer. Live
while the scenario has an alarm with the id, destroyed once it does not, and dormant while there is
no scenario to ask.

`Remove` then leaves the object destroyed for the sweep to reclaim, rather than nulling the alarm it
holds and reporting an invalid operation from every member afterwards.

### Contracts

A contract is keyed on `ContractID`, read off the captured contract every time the object is hashed,
which is what [Identity](#identity) forbids: hashing must not dereference anything. That much is
survivable, since a contract is a plain object that nothing can Unity-destroy, but what it holds is
not. The contract system builds new contract objects when a game is loaded, so a proxy taken before
a quickload reports the state of a contract in a game that is no longer loaded, which is #764 again
with nothing about parts in it.

The contract's guid is the identity instead, held as a value: the game writes it into the save and
reads it back, and it is what `ContractSystem.GetContractByGuid` looks up. That method searches the
running contracts only, and kRPC hands out objects for finished contracts too, so resolving searches
both lists. Live while a contract answers to the guid, destroyed once none does, and dormant while
there is no contract system, which is every game without contracts and every moment between states.

A `ContractParameter` is keyed on the parameter object itself. A parameter has no id of its own, but
the game reaches one the same way twice: a contract's parameters are an ordered list, and each
parameter's children are another, so the indices that lead to a parameter name it. The object holds
its contract and that path, resolves by walking it, and is as alive as its contract, plus destroyed
when the path no longer leads anywhere.

### Waypoints

A waypoint gets a `navigationId`, a `Guid`, in its constructor, and it is the only thing that names
one, so the object holds it and searches the manager's list. Live while the list has it, destroyed
once it does not, dormant while there is no waypoint manager.

What survives a load is worth saying out loud, because little of it does. The game saves the id only
for the waypoints registered with `ScenarioCustomWaypoints`, and this service creates its own through
`WaypointManager.AddWaypoint`, which does not register them, so a waypoint a client created does not
outlive the game state it was created in. A contract waypoint is rebuilt by the contract that owns
it, with a fresh id where the saved one does not survive. Either way a load can leave the object
standing for nothing, which it then reports; nothing else names a waypoint, so that is the honest
answer rather than a choice.

`Remove` leaves the object holding a waypoint the manager no longer has, and every member then
writes through to it, changing a waypoint that is not in the game. Classification is what makes that
raise instead.

### Comm links

A `CommLink` holds the game's link object, which is a hop in a vessel's control path. What matters
about that path is that it is a **deep copy**: `Path.CopyTo` clears the vessel's path and builds a
new link object per hop, carrying over the two nodes and the cost, and the signal strength and hop
type are then written onto the copies. The game does that every time it works out the vessel's
connection. So the object a client is given stands for one hop at one moment:

* a client streaming `signal_strength` reads the value the hop had when it asked for the object,
  for as long as it holds it, because the link it holds is not the one the game is updating;
* every read of `ControlPath` gives objects the store has never seen, so a client polling it grows
  the store without bound.

The vessel and the two nodes are the identity, the nodes held the way [Comm nodes](#comm-nodes)
holds one, and the hop is found by walking that vessel's control path. Nothing else identifies it:
the network's own edge between the two nodes is a different object, carrying none of the per-path
values a client reads a link for. The three states fall out of that:

| Situation | State |
|---|---|
| the path takes the hop | live |
| the vessel and both nodes are there, and the path does not take the hop | dormant: a path that has lost contact takes the hop again when the two are in range, and nothing has been destroyed |
| the vessel, or either node, is destroyed | destroyed |

### Close approaches

A `ClosestApproach` is a snapshot of values plus the two `Orbit` objects it was computed for, and it
already compares by value, so the store dedups it. It needs the state getter alone, `LeastAlive` of
its two orbits, exactly as a reference frame combines what it is defined against.

### What SpaceCenter leaves out

These classes do not implement `IGameObjectState`, on the same two grounds: what they stand for is
never destroyed, and the set of them is bounded, so the state would always be live and nothing
would ever be swept.

| Excluded | Why |
|---|---|
| `CelestialBody` | bodies are never destroyed and the set is bounded |
| `ConfigNode` | a part's configuration comes from the game's part database, which is built once at startup and not torn down with any game state |
| `Camera`, `AlarmManager`, `ContractManager`, `WaypointManager` | one instance each |
| `LaunchSite` | named by a string and built from values, so the store dedups it already, and the game's list of sites is bounded and outlives any game state |

`Force` is not on this list. It is an object kRPC creates for a client, and is covered with the
Drawing and UI objects it is shaped like; see
[Objects kRPC creates for a client](#objects-krpc-creates-for-a-client).

## The other services

Every other service that hands out proxies is covered. Between them they need one piece of shared
infrastructure, for the objects kRPC creates, and nothing else: what the rest need is a state getter
and, in two cases, an identity that is not a per-call object.

| Service | Proxy classes | Stands for | Identity |
|---|---|---|---|
| [Drawing](#drawing) | `Line`, `Polygon`, `Text`, `NavballMarker` | a drawing kRPC made in the scene | itself |
| [UI](#ui) | `Canvas`, `Panel`, `Text`, `Button`, `InputField` | an interface element kRPC made | itself |
| [UI](#ui) | `RectTransform` | the Unity rect transform of one of those | that transform |
| [RemoteTech](#remotetech) | `Antenna` | a part carrying `ModuleRTAntenna` | its part |
| [RemoteTech](#remotetech) | `Comms` | a vessel's communications | its vessel |
| [InfernalRobotics](#infernalrobotics) | `Servo` | a part carrying `ModuleIRServo_v3` | its part |
| [InfernalRobotics](#infernalrobotics) | `ServoGroup` | the servos of a vessel sharing a group name | its vessel and that name |
| [KerbalAlarmClock](#kerbalalarmclock) | `Alarm` | an alarm Kerbal Alarm Clock holds | the alarm's id, a string |
| [LiDAR](#lidar-and-dockingcamera) | `Laser` | a part carrying `LiDARModule` | its part |
| [DockingCamera](#lidar-and-dockingcamera) | `Camera` | a part carrying `PartCameraModule` | its part |

None of these services owns anything the game rebuilds under an id of its own, so none of them needs
a cached resolve, a module reference or any other piece of
[the SpaceCenter infrastructure](#where-each-piece-lives). What they reach the game through is a
`Part` or a `Vessel`, which already resolves, classifies itself and is public.

### Objects kRPC creates for a client

Drawing objects, UI objects and SpaceCenter's `Force` are one kind of thing: one client owns each of
them, the client removes it, and an addon holds it in a `ClientOwnedObjects` collection and walks
that collection every frame. A client owning an object says who normally removes it, not whether
anything else can; four things remove one first. The service's `Clear`, the addon releasing what a
disconnected client owned, the addon clearing everything when the scene changes, and, for a force,
the part it is applied to being destroyed.

A drawing and an interface element are a game object kRPC made, so each is its own identity and
classifies itself from what it holds: live while its `GameObject` is not Unity-destroyed, destroyed
once it is, and no dormant state, because nothing rebuilds a client's line or panel. It also
records having been taken out, because the game tears a game object down at the end of the frame
rather than at once, and an object the client has removed should not answer for the rest of that
frame. A `Force` is not a game object at all. It is an instruction naming a part, so it takes its
part's state, dormant included, and it records having been taken out for a reason of its own: the
part goes on living, so nothing else would ever say that a force the client removed is no longer
applied.

What they share is the frame loop, and that is the one piece of infrastructure the other services
need. It goes where `ClientOwnedObjects` already lives:

| Piece | Where | Does |
|---|---|---|
| `ClientOwnedObjects.RemoveDestroyed` | server assembly, `KRPC.Utils` | drops the entries whose object is an `IGameObjectState` reporting destroyed, without running the release action: there is nothing left to tear down |
| the addons' update loops | each service | call it, and then act only on what is live |
| `ClientOwnedObjects` asking for a sweep | server assembly, `KRPC.Utils` | every path that lets an object go asks for one, since removing a line, a panel or a force destroys nothing the game raises an event for, and nothing else would take the object out of the store. A collection whose objects are never handed to a client, the instantaneous forces, says so and asks for nothing, so a client pushing a part every frame does not sweep the store every frame |

`Force` is what makes this more than tidiness. The forces addon applies every force in its
collection on every fixed update, through `Part.InternalPart`, so a force on a part the game has
destroyed throws out of the physics step, every step, with no client call to attribute it to. That
is the `ResourceTransfer` problem in another addon, and it gets the same answer: a destroyed part
takes the force with it, and an unloaded part, which has no rigidbody to push, makes it wait. A
reference frame that is not live makes it wait too, on the same grounds as a drawing's: a frame is a
settable property, so the client can point the force at another one. `Force.Remove` then drops its
object from the store rather than leaving it there for the session.

#### Constructed orbits

`Orbit.CreateFromPositionAndVelocity` and `Orbit.CreateFromOrbitalElements`
([`services/orbits-from-state-vectors.md`](services/orbits-from-state-vectors.md)) put a third kind
of thing in this category, and the purest one: an orbit a client asks for names **no game object at
all**. Not a `GameObject` the mod made, as a drawing is, and not an instruction naming a part, as a
`Force` is. It is arithmetic the server holds on the client's behalf.

That makes it the one member of the category where only the reclamation half applies. There is no
liveness question the game can answer, because there is nothing it can destroy: a constructed orbit
is as valid on the last frame of the session as on the first, and every scene change leaves it
alone. So it needs no dormant state and no addon walking it every frame. It needs exactly one
thing, and it is the thing that is missing today: **the proxy leaving the store when the owning
client goes.**

What says so is the orbit recording that it has been let go of, exactly as a `Force` records having
been removed. An orbit whose client is gone reports itself destroyed, and the sweep the collection
already asks for on letting an object go is what takes it out. Nothing else can say it: the
collection otherwise releases the *game-side* resource, destroying the drawable, canceling the
transfer, stopping the force from being applied, and for a constructed orbit there is no such
resource. The store entry **is** the whole cost, so a collection that only released would be
bookkeeping that releases nothing.

Three details for whoever builds it:

- **Only constructed orbits.** Only the two constructors record the orbit as a client's. Orbits read
  off a vessel, body or node are named by the thing whose orbit it is, so the store hands back one
  object for each however often it is asked for, and they are bounded by the number of such objects
  rather than accumulating. Recording those too would take a vessel's orbit proxy away from every
  other client when the first one to ask for it disconnects.
- **Three proxies, not one.** `Orbit.ReferenceFrame` and `Orbit.OrbitalReferenceFrame` are stored
  too. They dedupe per orbit, since `ReferenceFrame.Equals` compares the orbit it is built on, so a
  constructed orbit is at most three entries, and all three go together without anything saying so:
  a frame is as alive as what it is defined against, so the orbit reporting itself destroyed covers
  both of them, and a `CreateRelative` or `CreateHybrid` frame a client builds on either.
- **The host.** Every collection today is a static field of a scene-scoped addon,
  `PartForcesAddon` being `KSPAddon.Startup.Flight`. A constructed orbit carries no `GameScene`
  restriction, matching `Orbit` itself, so it is reachable from the tracking station and the space
  center and needs a host that is too. That host is not a `ClientCleanupAddon`, which gives its
  collections up on entering a scene: an orbit is as valid in one scene as in the next, so only a
  game ending takes it.

Releasing on disconnect makes the id invalid for anyone else still holding it, which matters only if
a client passes an id to another client out of band, since ids come from one sequence and one store.
That is already true of drawings and forces, so a constructed orbit behaving the same way is
consistent rather than new.

### Drawing

`Line`, `Polygon`, `Text` and `NavballMarker` take the rule above: live while the drawable's game
object is, destroyed once it is not. A client that reads a line it has removed gets
`ObjectDestroyedException` rather than whatever Unity raises for a torn-down renderer, and the
object leaves the store at the next sweep.

The addon has a second problem of its own. It positions every drawable on every frame through the
drawable's reference frame, and that frame can be defined against a part or a vessel the game has
destroyed, so one destroyed vessel turns into an exception per drawable per frame. A drawable whose
frame is not live is not drawn, rather than positioned: the frame is a settable property, so a
client can point the drawable at another one, and destroying the drawing because the thing it was
measured against went away would take that away.

### UI

Every user interface object takes the same rule, from the `Canvas` and `Panel` an interface is built
in down to each control in it. As with a drawing, what raises is what reaches into the game, and a
member that only hands back what the object was built from does not resolve: a button's, toggle's or
input field's label, an input field's placeholder, and a scroll view's panel. Each of those is an
object in its own right and raises from the first of its own members that reaches the game. Three
things are specific to the service:

* The controls share a base, `Control`, which reaches the game through the component that handles
  interaction, so one checked accessor there answers for the interactable state, the tint and the
  tooltip of every control built on it. Each control checks its own component for the rest, as
  `Panel` does for the members it has beyond adding elements to itself.
* `RectTransform`, `Layout`, `LayoutElement` and `SizeFitter` wrap a component of the element they
  were taken from rather than standing for an element of their own, and none of them says whether
  the game still has it. `RectTransform` has no identity at all and is built fresh from
  `GetComponent` on every read, so a client that reads `panel.rect_transform` in a loop adds an
  object to the store on every iteration.
  The other three do have one, but built on Unity's `operator ==`, which reports a destroyed
  component as equal to null, so two objects standing for different destroyed components compare
  equal and the store can hand back the wrong one. All four are named by the component they wrap,
  compared by reference and hashed by identity hash, as [Comm nodes](#comm-nodes) does, so the store
  dedups them; each takes its state from that component, which is what lets the sweep drop it. The
  interface objects themselves compare their game objects the same way, for the same reason.
* The stock canvas hangs off `UIMasterController`, which the game keeps across scene changes, so it
  is always live and is never reclaimed. This is the one UI object that is not a client's own.

The service and its addon both run in every scene, and leaving a scene destroys the elements built
in it, so the object standing for such an element says so rather than failing on a torn down game
object.

### RemoteTech

`Antenna` holds a `Part` and reaches the mod's API with it, so it needs no resolve of its own: it is
as live, dormant or destroyed as its part, and destroyed when a part that is live no longer carries
`ModuleRTAntenna`. Checking the module list is a walk of one part's modules, which is only ever run
from the classifier, and the classifier is off the fast path by construction.

`Comms` reads its vessel's id out of the game at construction, through `vessel.InternalVessel.id`,
which fails for a vessel that is dormant or destroyed at that moment. The id is what the `Vessel`
object holds anyway, so it takes it from there, and its state is the vessel's.

### InfernalRobotics

A servo is a `ModuleIRServo_v3`, a part module, and `IServo.UID` is the part's craft id, so the mod
identifies a servo by its part. `Servo` does the same: it holds the `Part`, finds the module by name
on each access, and wraps whatever it finds. Its state is its part's, and destroyed when a live part
no longer carries the module.

`ServoGroup` is named by its vessel and the group's name, and resolves through the same
`ServoGroupsForVessel` that lists them. Its state is its vessel's, and dormant, never destroyed,
where the mod's assembly is not there to be asked at all: a group absent from a list that nothing
populated proves nothing. The mod not being *ready* is not that case, and must not be treated as
one: its controller only ever tracks the active vessel, and kRPC's own synthesized groups are what
answer for every other vessel whether the controller is ready or not.

What this fixes is not only the store. Both classes compare their wrapper objects with `==` on an
interface type, which is reference equality, and the wrappers are allocated per call: `IRWrapper`
builds a new `IRServo` for every servo every time a group's servos are listed, and a new synthesized
group for every group of a non-active vessel. So two objects for one servo never compare equal, the
store takes a fresh entry for each, and a script that polls `servo_group.servos` grows the store
without bound. Naming a servo by its part and a group by its vessel and name is what makes the store
dedup them at all.

Wrapping a module on each access is only affordable because wrapping is cheap, and it is not:
`IRServo`'s constructor looks up around forty properties and methods by reflection, per instance,
and those lookups depend on the mod's types alone. They move to the one-time wrapper initialization,
which also takes that cost off every existing listing call. `KACWrapper`'s alarm wrapper has the same
shape and needs the same treatment, for the same reason; see [KerbalAlarmClock](#kerbalalarmclock).

### KerbalAlarmClock

`Alarm` already holds the alarm's id, which is what the mod's API creates and finds alarms by, and
it holds the alarm object too. The object is what it uses, so an alarm the mod has rebuilt, which is
what loading a game does, is read out of the old one. It resolves by id from the mod's alarm list on
each access instead. Live while an alarm with the id is in the list, destroyed once none is, and
dormant while the mod is not ready, which says nothing about any alarm.

`Remove` deletes the alarm and leaves the object destroyed, rather than nulling the alarm it holds
so that every later member reports an invalid operation.

Resolving walks the mod's alarm list, and listing the alarms wraps every one of them, which costs
about twenty reflection lookups each. Those lookups depend on the mod's alarm type alone, so, as in
[InfernalRobotics](#infernalrobotics), they are made once for the assembly rather than for every
alarm wrapped.

### LiDAR and DockingCamera

`Laser` and `Camera` are `Antenna` again with another module name, `LiDARModule` and
`PartCameraModule`: each holds a `Part`, passes it to its mod's API, and takes its part's state,
plus destroyed when a live part no longer carries the module. The code is a state getter in each and
nothing else.

### What the other services leave out

| Excluded | Why |
|---|---|
| `KRPC.Expression`, `KRPC.Type` | neither stands for anything in the game. An expression is built from values and used to make a stream, and nothing can destroy it. They do accumulate in the store, one entry per expression a client builds, which is a real cost for a client that rebuilds expressions in a loop, but it is a question about objects the client owns and not about game state, so it belongs with whatever answers that generally |
| the `Debug` service | it has no classes, only procedures |
| `Drawing`'s and `UI`'s services and `RemoteTech.Target` | static classes and an enum |

## Alternatives considered

The approach was chosen by measuring whole builds of each variant, on a temporary `[KRPCService]`
assembly that was hand-built, hand-run and then deleted. Those numbers are **not reproducible**,
and are comparable only with each other. Full detail on
[PR #894](https://github.com/krpc/krpc/pull/894#issuecomment-4837124825).

| Version | Part resolve | `part.mass` ns/op | Module resolve | `module.name` ns/op |
|---|---|---:|---|---:|
| baseline (`main`) | `FindPartByID` | 667 | captured (the bug) | 0.3 |
| A: re-derive everything from ids | `FindPartByID` | 651 | by-name scan | 87 |
| B: cached resolve via a helper | weak ref + delegates | 612 | by-name scan | 95 |
| B.2: cached resolve, hand-inlined | weak ref | 628 | by-name scan | 85 |
| C: indexed modules only | `FindPartByID` | 652 | indexed | 36 |
| **D: cached resolve + indexed modules** | **weak ref** | **621** | **indexed** | **48** |

D is the only variant that is fast on both axes, and it fixes all four issues. Two findings from
that run outlived its numbers. **The part lookup was never the bottleneck**: `part.mass` is mostly
KSP's own mass computation, and the resolve strategy moves the total by single-digit percent. **The
real cost of the fix is module re-derivation**, from a captured reference to a re-derived one.

Each alternative below was turned down on evidence, several of them after being built and measured:

| Alternative | Why not |
|---|---|
| Check the remembered position against the module list's length and the class at it | Those are the only signals `PartModuleList` offers, and neither sees a change that leaves the length alone. Measured, the two checks cost about what the id check costs (15.4 ns against 14.8), so exactness here is free. |
| Remember the module itself, in the same weak reference the part path uses | Exact, and it lets a module getter skip resolving its part, but a weak reference costs about as much to read as resolving the part does, where reading a remembered position costs a fifth of that. Built and measured: `module.ref` 43.8 ns against 15.4, and `engine.thrust`, which reaches two modules, 81.9 ns against 46. It also allocates one weak reference per reference. The part path caches because its lookup is a search of every loaded vessel; a module's lookup is a walk of one part's modules, which is cheaper than the cache that would avoid it. |
| Let the persistent id be what a module proxy stands for | Tempting: it is the game's own name for a module, a part's flight id one level down, and it makes every lookup exact. It is not durable in the direction that matters. The game gives a module an id only when something asks, and writes out only ids it has already given, so a save written before a client named the module carries none for it. A quickload to such a save would leave every module proxy holding an id nothing answers to, which is [#764](https://github.com/krpc/krpc/issues/764) again, so the id is a way to find a module rather than what one is. |
| Keep captured references, check `Destroy()` before use | The fastest possible access, but a strong reference to a destroyed object is exactly the #771 leak, and it does not fix #764: after a load the captured module is stale even though an equivalent one exists. |
| Pure id re-derivation everywhere (version A) | Correct, but pays a module scan on every access and gives up a free win on the part path. |
| Pure weak references, no ids | Identity, hashing and store dedup need a value that outlives the object; hashing a weak referent changes the hash when it is collected, so the proxy can never be removed from the store. Also cannot detect destroy-and-recreate-with-the-same-id. |
| KSP `GameEvents` (`onPartDie` and friends) as the primary mechanism | Requires a case-by-case implementation per object kind, and KSP does not raise events for every kind or every destruction path. Fine as a latency optimization on top (see [Phases](#phases)), wrong as the foundation. |
| Weak references in the object store itself | The store holds the only strong reference to a proxy; making it weak collects proxies that clients still hold ids for. |
| Record only where a module was found, not that a part has none | An object with an optional module it does not have, an engine with no gimbal, then searches the whole module list on every access, since nothing records the absence. Built that way, `engine.thrust` cost 1165 ns. A reference records a part having no such module as readily as which module it found, so both answers cost an index and a string comparison. |
| A module reference generic on the module type | Built and measured: the shared generic it compiles to costs 21 ns against 7 ns for the indexed lookup underneath it, so the wrapper cost three times the work it wrapped. Naming the module by its class name keeps the whole resolve path non-generic; with the absence fix above it took `module.name` from 51 ns to 46 ns and `engine.thrust` from 1165 ns to 46 ns. |
| Cache the resolved `PartModule` behind the same weak reference the part uses | It would let module getters skip part resolution entirely, and it is correct, since destroying a part destroys its modules. Measured a regression on both counts; see the second row of this table. |
| Make `ModuleRef` public, so the module-backed objects in other services use it | It buys them nothing. `Antenna`, `Laser`, `Camera` and `Servo` each hand a `Part` to their mod's API and never touch a `PartModule` on the way, so the only place a module has to be found is the classifier, which runs after a resolve has already failed or from a sweep, and a walk of one part's modules is affordable there. `Servo` does resolve a module, but Infernal Robotics itself names a servo by its part, so a lookup by name is exact. Keeping the two SpaceCenter pieces internal keeps the fast path they exist for from being an inter-assembly contract. |
| Give a `Servo` a cached resolve of the module it wraps | Every member of a servo is a reflection call into the mod, hundreds of nanoseconds at best, so the tens of nanoseconds a cache saves are invisible. What made wrapping expensive was the wrapper's own per-instance reflection lookups, and those are the thing to move, since every listing call pays them today too. |
| Leave Drawing and UI out, as objects the client owns | The client owning an object says who removes it, not whether the game can. A scene change destroys every drawing and every interface element, so the objects standing for them are as dead as any part's, and reading one raises whatever Unity raises for a torn-down object rather than saying so. |
| Destroy a drawing whose reference frame is destroyed | The frame is a settable property, so the object is recoverable and taking it away is not. Not drawing it is enough, and it is reversible. |
| Identify a `CommLink` by the link object the network holds, and only classify it | The network drops a link object when contact is lost and never gives it back, so a client streaming through it would read the last values it had forever. What is durable is which two nodes the link is between. |
| Key a `Waypoint` on its name, or on its seed and index | A name is neither unique nor stable, and a seed and index only name a contract's waypoints, not the custom ones this service creates. The navigation id names both, and the game saves it for the ones that are saved at all. |

## Phases

The general infrastructure comes first, the game-object-specific work next, one service at a time
after that, the documentation once every service is covered, and the benchmarking last. That order
is what lets the work land as separate pull requests: phases 1 and 2 name no game object, phase 3
is one game object at a time, phases 4 to 7 sit on top of whatever of phase 3 has landed, and
phases 8 to 13 are one service at a time, each of which only needs what phase 3 did to parts and
vessels.

Phases run in order, and within phase 3 each game object builds on the ones above it. A phase is a
sequence of commits wherever it needs to be, each commit doing one thing. Tests land with the phase
they exercise. Changelog entries belong to no phase; they are consolidated into a single commit
before the branch is pushed.

Phases 6 to 13 are one service, or one kind of object within a service, at a time. They depend on
phase 3 and on nothing in each other, apart from Drawing and UI both needing the collection change
in phase 8, so the order among them is only a running order and any of them can be dropped or
deferred without touching the rest. Three of them, 11 to 13, need a mod installed to run at all,
which is why they come last among the services: what they change cannot be exercised by the
non-game test suite, and two of the mods are not in the test harness's mod list at all.

Phases 15 and 16 are the benchmarking, and they are a pull request of their own, following the one
the behavior phases make. Nothing this design changes depends on them: the framework measures
whatever build it is run against, and the cases in 16 name what phases 2 and 3 ship rather than
adding to it. Splitting them off keeps the first pull request to the behavior change.

| # | Phase | Contents |
|---|---|---|
| 1 | Core infrastructure | `ObjectDestroyedException`; `IGameObjectState` and `GameObjectState`; the store sweep and reclaimed-id semantics; `GameState` and the load boundary the server addon raises it at; core unit tests. No service uses any of it yet, so no behavior changes. |
| 2 | SpaceCenter infrastructure | The SpaceCenter-side pieces every later phase builds on, and no game object of its own: the testing tools a lifetime test needs, which are destroying a part, driving the editor's undo and reading the store's size; and `CachedObject<T>`, which stamps its weak reference with `GameState`'s generation and so comes after phase 1. |
| 3 | SpaceCenter game objects | One sub-phase per kind of game object, in the order of [SpaceCenter](#spacecenter); see below. |
| 4 | Event-driven reclamation | Subscribe to `onPartDie` / `onVesselDestroy` so obviously dead proxies leave the store immediately rather than at the next load boundary. Pure latency improvement over the sweep from phase 1. |
| 5 | [The vessel in the editor](#the-vessel-in-the-editor) | Everything the editor's vessel needs, which is a second kind of thing a part can belong to rather than another kind of game object; see below. |
| 6 | SpaceCenter records | [`Alarm`](#alarms), [`Contract`, `ContractParameter`](#contracts) and [`Waypoint`](#waypoints): the records the game keeps for the loaded game rather than for a vessel. Each gains an identity the game writes into the save and re-derives from it; each `Remove` leaves its object destroyed rather than holding something the game no longer has. |
| 7 | SpaceCenter objects defined against others | [`CommLink`](#comm-links) is named by the vessel whose control path it is a hop in and the two nodes it joins, and finds that hop in the path as it stands, so it reports the link as it is rather than as it was when the object was made; [`ClosestApproach`](#close-approaches) takes the state getter alone. Needs 3a, 3h and 3i for what it defers to. |
| 8 | [Objects kRPC creates for a client](#objects-krpc-creates-for-a-client) | `ClientOwnedObjects.RemoveDestroyed`, and `Force` as its first user: a destroyed part takes its forces with it, and an unloaded part, or a reference frame that cannot be measured in, makes them wait, instead of the physics step dereferencing a part that is gone. `Force.Remove` leaves the object gone, as removing a drawing does. [Constructed orbits](#constructed-orbits) are the other user, and the one that needs only the store-dropping half. Needs 3b and 3h. |
| 9 | [Drawing](#drawing) | `Line`, `Polygon`, `Text` and `NavballMarker` classify themselves from their game object and from having been removed, so that removing one twice reports it gone rather than not found, and the addon does not draw a drawable whose reference frame is not live. Needs 8 and 3h. |
| 10 | [UI](#ui) | Every user interface object classifies itself and raises from the members that reach the game, removal included, with `Control` answering for the members its controls share; `RectTransform`, `Layout`, `LayoutElement` and `SizeFitter` gain a state, and an identity the store can dedup, so reading one repeatedly stops adding an object to the store per call. Needs 8. |
| 11 | [RemoteTech](#remotetech), [LiDAR and DockingCamera](#lidar-and-dockingcamera) | `Antenna`, `Laser` and `Camera` defer to their part and are destroyed when a live part no longer carries their module; `Comms` names its vessel by the id its `Vessel` already holds. Three services, one shape, so one phase. Needs 3a and 3b. |
| 12 | [InfernalRobotics](#infernalrobotics) | `Servo` named by its part and resolving its module on each access, `ServoGroup` named by its vessel and the group name, and `IRWrapper`'s per-instance reflection lookups moved to its one-time initialization so that wrapping a module is cheap. Both stop being keyed on a wrapper the mod's listing calls allocate, which is what makes the store dedup them. Needs 3a and 3b. |
| 13 | [KerbalAlarmClock](#kerbalalarmclock) | `Alarm` resolves by its id on each access, is dormant while the mod is not ready, and is destroyed by `Remove`; `KACWrapper` binds the mod's alarm fields once for the assembly, as 12 does for the servo ones, since resolving now walks the alarm list. |
| 14 | Documentation | An `object-lifetime` page of its own in the manual. It explains rebinding, the exception, what a client should do about it, what the editor does differently, and what the other services' objects do, linked from every client's page where remote procedures are introduced. It is client-facing behavior rather than part of any one language's client, and nothing else in the docs covers what an object is. The exception itself is documented across all client languages. Last of the behavior phases, so that it describes every service rather than one. |
| 15 | Benchmarking framework | Per [build-tools/benchmarks.md](build-tools/benchmarks.md): the timing RPCs, the runner, and the benchmark scripts and craft, with its section of the development guide. Nothing here is specific to this design, and no case it ships measures anything this design adds, so nothing before it needs it and it lands after the behavior phases, in a pull request with 16. |
| 16 | SpaceCenter benchmarks | The cases that measure what this design added: the resolution primitives against each other (captured reference, cached resolve, `FindPartByID`, indexed module lookup, the module reference, a by-name scan), and the accessors the [Budgets](#budgets) are written against. Last because each of them names something phase 2 or 3 introduces, and has nothing to run in until 15. Phases 6 to 13 add no case; see [Performance](#performance). |

Phase 3, one game object at a time:

| # | Game object | Contents |
|---|---|---|
| 3a | [Vessels](#vessels) | `Vessel` opts into liveness and resolves through the cache; a failed lookup throws `ObjectDestroyedException`, and the between-states window is dormant. |
| 3b | [Parts](#parts) | `Part` resolves through the cache and classifies itself against the proto-part snapshots of unloaded vessels, so an unloaded vessel's parts are dormant rather than destroyed. Fixes the `Part` half of #885 and, with the sweep, the pinning half of #771. |
| 3c | [Part modules](#part-modules) | `ModuleRef`, keyed on the part, the module's class and the occurrence, and resolving through the remembered position validated by the persistent id; `Module` and the ~28 concrete module proxies converted onto it; their equality and hashing rebased off the captured module. Fixes the rest of #885 and all of #764. |
| 3d | [Fields, events and actions](#a-modules-fields-events-and-actions) | `PartField`, `PartEvent` and `PartAction` look themselves up by name on their module on each access; `ActionGroupAction` carries the part, module and names as values and defers its state. |
| 3e | [Named against a vessel or a part](#anything-named-against-a-vessel-or-a-part) | The parts collections, `AutoPilot`, `Control`, `Comms`, `Flight`, `Resources`, `Resource`, `Propellant`, `Stage` and `ResourceTransfer` defer to their owner. `Stage` names its vessel by id rather than holding the KSP vessel; `ResourceTransfer` reads its parts' states rather than resolving them, so a destroyed part cancels the transfer and an unloaded one makes it wait. |
| 3f | [Maneuver nodes](#maneuver-nodes) | `Node` holds the node object for its whole life and answers from the vessel's flight plan instead. Closes the hash bug that nulling the field on removal would cause. `Orbit` lands here rather than in 3e: an orbit is named against its owner like the rest, but one owner is a maneuver node, so it cannot be written before the node can be asked. |
| 3g | [Crew members](#crew-members) | `CrewMember` compares by the name it is already named by, so the store dedups it and the roster search answers for its state. |
| 3h | [Reference frames](#reference-frames) | A frame is as alive as everything it is defined against, hybrid frames included; part-relative and docking-port frames re-derive from ids, which closes the raw `NullReferenceException` from `DockingPort.ReferenceFrame`. |
| 3i | [Comm nodes](#comm-nodes) | `CommNode` holds the game's object and is live while its transform is either absent or not Unity-destroyed. |
| 3j | [Science data](#science-data) | `ScienceData` defers to its experiment module, and to that module still listing the record where the part is live. |
| 3k | [Science subjects](#science-subjects) | `ScienceSubject` gains an identity, the subject id plus the generation it was read in, and is live while that generation is the loaded one. The science gain multiplier is read on each access rather than captured. |

Phase 5 is the vessel in the editor. It lands only with the editor scene API (see
[services/editor-scene-api.md](services/editor-scene-api.md)), and everything before it is
independent of that. Not all of it can wait for the phase, though, because this work sits on top of
that API rather than introducing it: the editor's parts and its vessel already exist when phase 3
runs, and a proxy that classifies itself at all has to answer for both scenes from the moment it
answers for either. Deferring the shared half would leave a window in which the editor's objects are
misclassified and swept.

| # | Step | Lands in | Contents |
|---|---|---|---|
| 5a | `EditorExtensions` | 3e, then 5 | One place for the vessel the editor has open, what the game holds for it, and which vessel it is. 3e needs the first two as soon as the parts collection and `Resources` classify themselves, so it introduces them; the phase then replaces the copies of the same lookup that the editor scene API left behind. |
| 5b | Parts in the editor | 3b | `PartId` holds a craft id or a flight id and says which, so a `Part` resolves against the vessel the editor has open or against the loaded vessels. Editor parts have no dormant form, and the errors say so. |
| 5c | The editor's vessel as an owner | 3e | The parts collection, `Resources` and `Stage` can be named against the vessel in the editor, which has no id, so each takes its state from the editor rather than from a vessel lookup. `Resources` also answers from its part when it is a single part's, which applies in flight too. |
| 5d | Reclamation in the editor | 5 | `onEditorShipModified` asks for a sweep, the game raising no part-died event in an editor, and the sweep settles on the editor vessel's part count rather than on the game's vessel list, which is empty on a save with nothing in flight. Needs 4. |
| 5e | Which vessel a craft id belongs to | 5 | The ship generation, so that a part of a vessel the editor has loaded over is gone rather than whatever now answers to its id; and the editor ship addon, so that an undo is not taken for a new vessel. Needs 5a and 5b. |

## Testing

What has to be shown, in the in-game suites for the service each case belongs to and in the core
unit tests for the store and the generation:

* a destroyed part, and the modules of a destroyed part, raise `ObjectDestroyedException`;
* a destroyed vessel, and everything reached through it, raise it too;
* proxies survive a quickload and read the objects the game rebuilt (#764), modules included;
* module proxies survive a load of a game state written before the client named the module, which
  carries no persistent id for it;
* a destroyed part leaves the store on the destruction event, and a load boundary sweeps the store
  (#771). The sweep case uses a maneuver node: a load rebuilds a vessel's parts under the ids their
  proxies name them by, so parts survive it and demonstrate nothing, and no destruction event covers
  a node;
* a part of an unloaded vessel reports not-loaded rather than destroyed, survives a sweep, and works
  again once the vessel loads;
* the sweep drops dead proxies, keeps proxies that do not implement `IGameObjectState`, removes one
  exactly once and never reuses an id; a reclaimed id raises `ObjectDestroyedException` and an
  unissued one `ArgumentException`;
* the generation moves at a boundary, a sweep leaves it alone, and a change leaves a sweep pending;
* in the editor: a part of a vessel the editor has loaded over, and its modules, raise and leave the
  store, whether the vessel loaded is the same craft or another; a part is not confused with the
  part of another vessel that shares its craft id; the parts collection, `Resources` and `Stage` of
  the vessel in the editor survive a sweep; leaving the editor destroys the vessel it had open and
  everything named against it; and a part survives an undo, which replaces the vessel object while
  keeping the craft ids;
* an orbit survives a quickload, reads the orbit the game rebuilt with its vessel, and is still the
  one object the vessel answers with afterwards;
* an alarm survives a quickload and reads the one the game rebuilt; a removed alarm, waypoint or
  drawing raises rather than writing through to something the game no longer has, and removing one
  twice reports it gone rather than not found;
* a force on a destroyed part leaves the store, rather than being applied on every physics step,
  and a removed force reports itself gone rather than the force it was applying;
* an orbit a client constructed, and both of the reference frames on it, leave the store when that
  client disconnects, while the orbit of a vessel, which is no one client's, survives another
  client going;
* the sweep survives a proxy whose state getter throws, keeping it and checking the rest;
* a rect transform, a servo and a servo group each read twice are one object, not two.

Two things the tests have to work around:

* asserting on the client's `RuntimeError` cannot tell dormant from destroyed, since the Python
  client builds `ObjectDestroyedException` as a subclass of it and maps `InvalidOperationException`
  to it, so a test asserts on the exception's type and message;
* a part cannot be deleted from the editor's vessel one at a time. `EditorLogic.DeletePart`
  refreshes the editor's attach-node icons before it deletes anything, which raises a
  `NullReferenceException` when the call did not come from the editor UI, so the part is never
  deleted. A part leaving the vessel is provoked by loading a different craft instead, and the two
  craft used are checked to have disjoint craft ids.

Specified here and **not** reachable from a test:

* **LiDAR and DockingCamera at all**, neither mod being in the test harness's mod list. Both are the
  same handful of lines as `Antenna`, and that is the whole argument for them.
* **A comm link coming back.** Two vessels losing contact is drivable; getting them back into
  contact within a test is not, so the dormant-to-live direction is by argument.
* **Contract parameters, and a contract across a load**, which take a career game with a contract
  accepted.
* **A drawing whose reference frame is destroyed.** What it demonstrates is the absence of an error
  per frame, which a test cannot see; the frame's own state is what decides it.
* **A module reference rebinding when a part's module list changes under it.** Nothing in KSP does
  it, so provoking it needs a test module built for the purpose.
* **A client-owned object read in the frame it was removed in.** Each of these objects records that
  it has been taken out, which makes removal immediate, so the window the Unity check alone would
  leave never opens.
* **A store returning to a stable size over repeated quickloads**, as opposed to the single load the
  store tests check.
* **A stream over a destroyed part** delivering the error once and being removed, per
  [protocol/stream-invalidation.md](protocol/stream-invalidation.md).

## Performance

This feature sits on the hottest path in the mod: a stream over a few hundred parts re-evaluates
these accessors every fixed update, and one stream per part already costs the server 3.81 ms per
update on a 321-part station, a fifth of a 20 ms frame, before this work adds anything.

### Budgets

| Path | Budget |
|---|---|
| `part.mass` (and any KSP-dominated part getter) | no slower than `main` |
| `module.name` (and any trivial module getter) | <= 50 ns/op on the reference craft |
| any access fast path | allocation free (under one byte per operation as measured, no collection triggered), no loop over a module or part list |
| failure and classification paths | unconstrained |
| store sweep | O(store size x the cost of one liveness check), at load boundaries only |

The sweep budget is the loosest of these on purpose. A liveness check is not constant: `Part` asks
the game for the part, and on a miss searches the proto-part snapshots of every unloaded vessel,
so a store full of parts on the 321-part station is on the order of a hundred thousand iterations
per boundary. That is affordable only because a load boundary is already a multi-second stall and
nothing else runs there.

All the budgets are met, the sweep by argument rather than by measurement; nothing times it.

The allocation budget is a hard assertion in the suite, which fails at one byte; the
ns/op budgets are checked by running the suite before and after a change on the same machine,
because absolute timings drift between sessions by more than the differences being measured.
Nothing is retained between changes.

### Measured

From the benchmark suite ([build-tools/benchmarks.md](build-tools/benchmarks.md)), on one machine,
five chunks per case, best of the five with the empty-loop cost subtracted. Each column is a whole
build, so the two are an A/B of the work. Absolute values are machine specific; the ratios within a
run and the allocation counts are what carry. The variant numbers under
[Alternatives considered](#alternatives-considered) came from another harness on another machine and
do not compare with these at all: that run put `part.mass` at 667 ns.

Per access, on the reference craft (58 parts in flight):

| Case | `main` | this design | |
|---|---:|---:|---|
| `part.name` | 107 | 32 | a scan on every access became a cache read |
| `part.mass` | 1431 | 1411 | budget met: no slower than `main` |
| `module.name` | 4.5 | 45 | budget met, against a ceiling of 50. `main` is the captured module, and the bug |
| `module.part` | | 4.7 | no module lookup |
| `engine.thrust` | 6.3 | 46 | one part and two module lookups |
| `parachute.state` | 5.4 | 40 | same, the getter resolving its module once rather than on each mention |
| `part.engine` | 8940 ns, 2212 B | 9104 ns, 2070 B | the engine no longer keeps a list of its modules. The 188 bytes the id adds are `Guid.NewGuid` inside the game's own id generation, once per reference built, on no fast path |
| `vessel.parts.all` | 1782 ns, 2493 B | 1995 ns, 3435 B | 58 part objects, each 16 bytes larger for the cache it carries. No new allocation, and nothing on a fast path |
| store dedup | 12.4 | 12.5 | equality rebased onto identifiers without moving it |
| stream update, one per part | 0.75 / 3.81 ms | 0.75 / 3.71 ms | 58 / 321 parts |

Every access fast path measures 0.00 bytes per operation, with no collections.

The resolution primitives are implemented in the benchmark service and measured against each other
within one session, on the reference craft:

| Primitive | ns/op |
|---|---:|
| captured reference plus a Unity null check | 3.7 |
| weak-reference cached resolve, nothing added | 23.0 |
| the cache as designed | 32.2 |
| `FindPartByID` | 113 |
| indexed module lookup, hand written | 7.7 |
| the module reference as designed | 14.8 |
| module lookup by persistent id | 14.8 |
| by-name module scan | 43.7 |
| `OfType<T>().ToList()` | 1622 (160 B) |

What that settles:

 * **A cached resolve beats re-deriving, and more so at scale.** 23 ns flat against `FindPartByID`
   at 113 / 301 / 516 ns for 58 parts, 174 parts over 3 vessels, and 321 parts: linear in loaded
   parts across vessels as well as within one.
 * **The game-state stamp and the shared shape cost about 9 ns** (32.2 against 23.0), against 90 ns
   saved on the smallest scene the suite has and 470 ns on the largest. If that 9 ns is ever worth
   chasing, the two things it pays for are a static property read across the assembly boundary and
   a generic type shared between every kind of Unity object.
 * **Indexed module lookup beats a by-name scan**, 8 ns against 44; and `OfType<T>().ToList()` at
   1622 ns and 160 bytes per call is ~200x an indexed lookup, so it is worth avoiding anywhere on a
   fast path.
 * **Looking a module up is cheaper than caching it.** A weak reference costs 23 ns to read, and
   the walk it would save costs 15, so remembering the module rather than where it was is a loss
   before the part is even considered. This is the opposite of the part path, whose lookup is a
   search of every loaded vessel, and it is why only one of the two caches.
 * **The id walk and the remembered position are level on these parts** (14.8 against 14.8), which
   carry few modules. The walk is linear in a part's modules and the position is not, so the
   margin is a property of the craft rather than of the code.

Still unmeasured:

 * **The store sweep.** The dedup path is measured in its place and is flat in store size (12.4 ns
   at 58 entries, 12.5 ns at 321).
 * **A delegate-based helper against hand inlining.** No case exists for it. The design avoids
   delegates on the strength of B against B.2 under
   [Alternatives considered](#alternatives-considered), which was noise in both directions.

Nothing in the suite bears on the correctness half of this design, dormant versus destroyed, sweep
semantics, reclaimed-id lookup or hash stability. That is what the tests under
[Testing](#testing) are for.

### The later phases

Phases 6 to 13 get no budgets and add no benchmark case, because nothing they touch is on a path
that a stream re-evaluates over hundreds of objects:

| Path | Why it is not measured |
|---|---|
| the other services' accessors | every one of them is a call into a mod's API, and RemoteTech's, Infernal Robotics' and Kerbal Alarm Clock's go through reflection, which costs hundreds of nanoseconds before kRPC's own work is counted. Naming a servo by its part adds a part resolve, which is a cache read, and a lookup of one module by name, which was measured at 44 ns |
| SpaceCenter's records | a client reads a contract, an alarm or a waypoint when something changes, not every fixed update, and each resolve is a search of a list the game keeps short |
| a comm link | a walk of one vessel's control path, which is a handful of hops, against a captured reference today. `control_path` already allocates a list and an object per hop |
| the drawing and interface update loops | one state check per client-owned object per frame, on a collection whose size is what a client explicitly created |

The one thing phases 12 and 13 make faster is worth recording anyway. Moving `IRWrapper`'s
per-instance reflection lookups to its one-time initialization takes about forty `GetProperty` and
`GetMethod` calls off every servo and group the mod lists, which is per servo per call today, and
`KACWrapper` gives about twenty back per alarm the same way.

## Open questions

 * **Should dormant get its own exception type?** Reusing `InvalidOperationException` with a clear
   message adds no API surface; a dedicated type would let a client retry on dormant and give up
   on destroyed without matching on message text. Recommendation: start with
   `InvalidOperationException`, add a type only if users ask.
 * **Should clients be able to test liveness without catching?** A `bool` member ("does this still
   exist") would suit polling a parachute during descent, the actual use case in #885. It is
   per-class API surface for something `try` / `except` already handles. Recommendation: defer,
   revisit after the exception ships.
 * **Do any mods change a part's module list at runtime?** It is no longer a correctness
   question: whatever the change, the remembered position stops carrying the id and the lookup
   that follows finds the module or reports it gone. What is left is cost. A change sends the
   next access through a walk of the module list, and if a popular mod rearranges modules often
   enough that the walk becomes the common case, the hint stops earning its place. Nothing in
   KSP itself does this.
 * **Should the objects a client owns be reclaimed when the client disconnects?** The addons
   already destroy the game objects of a client that has gone, so the objects standing for them
   report themselves destroyed and the next sweep takes them. But a sweep runs at a game-state
   boundary, and a client disconnecting is not one, so they sit in the store until something else
   moves. Asking for a sweep when a client disconnects would close that, and it is a change to
   when sweeps happen rather than to what they do. Recommendation: leave it, and revisit with
   phase 8, which is where the disconnect path is already being read.
 * **Is a Kerbal Alarm Clock alarm's id durable across a load?** The mod's API creates alarms by
   it and finds them by it, and kRPC already uses it that way, but nothing here has checked that
   the mod writes it into its own scenario rather than assigning it at load. If it does not, an
   alarm object is a record of one game state, like a `ScienceSubject`, and phase 13 compares the
   generation instead of searching.
 * **Is a kerbal's name stable enough to be an identity?** A `CrewMember` is named by it, and
   the game keeps its roster under it, but `CrewMember.Name`'s setter renames the kerbal
   through `ProtoCrewMember.ChangeName`. The object is then holding a name the roster no
   longer answers to: it stops resolving, reports itself destroyed and is swept, so a client
   loses the very object it renamed through, while a client that had another object for the
   same kerbal loses that one too. Nothing but that setter renames a kerbal. The ways out are
   to name a kerbal by something the client cannot change, if the game offers one, to have the
   setter carry the object's identity forward with the rename, or to leave it and say that
   renaming invalidates the objects for that kerbal. **Settled:** the last of the three. A
   kerbal has nothing else to be named by, and carrying the identity forward would still strand
   a second object taken before the rename, so it buys a partial answer for a mutable hash. What
   the option asks for in return is that it be said, which the changelog and
   [doc/src/object-lifetime.rst](https://github.com/krpc/krpc/blob/main/doc/src/object-lifetime.rst)
   now do.
 * **Should a `CrewMember` rename be handled the way a `ServoGroup` rename is?** A servo group has
   the same problem, its name being both what identifies it and a settable property, and phase 12
   settles it: the object follows the name it is given, and the hash is taken from the vessel
   alone, so the name can change without stranding the object in the store. Taking the hash off
   the mutable part is the whole of what makes carrying an identity forward safe, and it is what
   the second of the answers above would need. What it does not fix is a second object for the same
   group, taken before the rename, which stands for a name nothing answers to; the same would be
   true of a kerbal.
