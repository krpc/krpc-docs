# Object lifetime, destroyed objects and object-store reclamation

**Status:** in progress. Everything below is built, on a branch whose history is being restructured
into the phases below; no PR is raised yet. The approach was agreed
on [PR #894](https://github.com/krpc/krpc/pull/894), whose own branch predates that discussion and is
not the implementation. Covers issues
[#885](https://github.com/krpc/krpc/issues/885),
[#764](https://github.com/krpc/krpc/issues/764),
[#771](https://github.com/krpc/krpc/issues/771), and the follow-up left open by
[#770](https://github.com/krpc/krpc/pull/770).

## Problem

First, a note on terminology. Three different things here are called objects:

| Term | What it is |
|---|---|
| **game object** | What the client means: this part, this vessel, this maneuver node. A concept, not a type. It lasts for as long as the game keeps state for it, whatever the game does with its representation in the meantime. |
| **Unity object** | How the game represents a game object while it is in the scene: a `Part`, a `PartModule`, a `Vessel`, all of them `UnityEngine.Object`s. The game makes and destroys these as it needs them, so several can stand for one game object over its life, and at times none does. `UnityEngine.GameObject` is one Unity type among these; it is not what "game object" means here. Not every game object has one: a science data record is plain state the game keeps, in the scene or not. |
| **proxy** | The kRPC service object a client holds an id for. |

A proxy represents a game object. Previously, most part-related proxies **capture** a Unity object at
construction and hold that instance forever, so what they represent is the instance rather than the
game object. That single decision causes four reported problems:

| Issue | Symptom | Cause |
|---|---|---|
| [#885](https://github.com/krpc/krpc/issues/885) | `Parachute.deployed` throws a bare `NullReferenceException` after the part is destroyed | captured `PartModule`, no liveness check |
| [#764](https://github.com/krpc/krpc/issues/764) | parachute state unreadable after loading a save | captured module belongs to the previous game state |
| [#771](https://github.com/krpc/krpc/issues/771) | memory grows with each quickload | the object store holds proxies forever, and each captured object pins a destroyed part, vessel and part graph |
| [#770](https://github.com/krpc/krpc/pull/770) | the same leak via `CrewMember` | fixed by re-deriving from an id; the general case was left open |

Proxies that already store an id and re-derive (`Vessel`, `Part`, `Resource`, `Propellant`,
`CrewMember`) do not have the access bug, but they still accumulate in the object store forever.

Two independent halves, and both must be solved:

1. **Access.** Every proxy access must either reach the game state that currently represents its
   game object, or fail with a meaningful, catchable error.
2. **Reclamation.** The object store must drop proxies whose game objects are gone.

## Scope

In scope:

* `KRPC.Service.ObjectStore` and the core service infrastructure
* The SpaceCenter proxies for parts, part modules, vessels, maneuver nodes, comm nodes and reference frames.

Out of scope:

* Other proxies are left as is, and maintain their existing behavior.
* Proxies for objects that kRPC itself creates and the client explicitly removes (Drawing, UI).
* The protocol change once considered for [#877](https://github.com/krpc/krpc/issues/877). See
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
(PR #894 positioned a protocol-facing `StateGeneration` as a seam for
[#877](https://github.com/krpc/krpc/issues/877);
[protocol/stream-invalidation.md](protocol/stream-invalidation.md) has since settled on granular
per-stream errors, so the generation carries no protocol meaning.)

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

Destruction events ask for a sweep, but do not move the generation on. Nothing has been rebuilt, so
nothing a proxy resolved before the event has to be resolved again. One sweep also covers a whole
vessel coming apart, which destroys many parts in a single moment.

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
| it must not throw | one pass calls it on every entry in the store |

**The state getter goes on everything, whether or not the class re-derives.** The sweep reclaims
only what opts in, so a class left out accumulates in the store for the whole session however well
its accesses behave, which is the half of #771 that re-derivation does not touch. A proxy that
already resolves correctly, and one whose access path is left exactly as it is because a cheaper
lookup would buy nothing, both still need it.

Classification is off the fast path by construction. It runs only once a resolve has already
failed, or from a sweep at a load boundary, so it may search as widely as it needs to. Searching
every persistent form the game keeps, to prove nothing holds the object before calling it
destroyed, is affordable exactly because nothing reaches that code on a working access.

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
| `Changed` | the addon, when a game is loaded, quickloaded or reverted, and on a scene change | moves `Generation` on and asks for a sweep |
| `RequestSweep` | the addon, on a destruction event (`onPartDie`, `onVesselDestroy`) | asks for a sweep, leaving the generation alone: what was destroyed is gone, but nothing has been rebuilt for a cache to look up again |
| `Sweep` | the addon, from the first server update where the game has stopped adding vessels | runs the sweep and clears `SweepPending` |
| `Generation` | a proxy caching something it looked up, or classifying something that cannot outlive one game state | a `uint` that identifies the current game state |

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

It is a struct field on the proxy rather than a wrapper it calls through. Keeping it
**delegate-free** matters: the measured penalty of the first helper cut came from indirection, so
a proxy costs one extra allocation rather than three, and the resolve stays inline in the accessor.
It is typed on `UnityEngine.Object`, which gets DRY and the inlined null check both.

Caching is worth it only where the lookup it avoids costs more than the cache read. Reading the
weak reference is ~23 ns, against 112 ns for a part lookup on the reference craft and 516 ns on a
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

## SpaceCenter implementation

What the infrastructure needs from a service, per kind of game object: what identifies it, what
resolving that costs, and how its state is decided. **Not every kind is covered**, and nothing has
to be: a class that does not implement `IGameObjectState` behaves as it does today, always
usable and never swept, which is the right answer wherever what a proxy stands for cannot be
destroyed. [Deliberately not covered](#deliberately-not-covered) lists the classes on that path
on purpose.

| Kind | Proxy classes | Identity | Resolved by |
|---|---|---|---|
| [vessel](#vessels) | `Vessel` | the game's vessel id, a `Guid` | a search of every vessel in the game, loaded or not |
| [part](#parts) | `Part` | the part's flight id | a search of the parts of every loaded vessel |
| [part module](#part-modules) | `Module` and ~28 module proxies (`Engine`, `Parachute`, `Thruster`, `Experiment`, `ResourceConverter`, `Antenna`, `Sensor`, `Light`, ...) | its part, the module's class name, and which occurrence of that class it is | the module found last, or `part.Modules[id]` for the id the game knows it by, or counting the part's modules of the class |
| [field, event, action](#a-modules-fields-events-and-actions) | `PartField`, `PartEvent`, `PartAction`, `ActionGroupAction` | its module, and the name the game gives it | a lookup by name on the module, or nothing at all for the record of one assigned to an action group |
| [named against a vessel or a part](#anything-named-against-a-vessel-or-a-part) | the parts collections, `AutoPilot`, `Control`, `Comms`, `Flight`, `Orbit`, `Resources`, `Resource`, `Propellant`, `Stage`, `ResourceTransfer` | that vessel's or part's identity, plus whatever picks it out among its siblings: a resource id, a stage number | resolving the owner |
| [maneuver node](#maneuver-nodes) | `Node` | nothing the game offers, so the node object itself, plus its vessel's id | nothing to resolve |
| [crew member](#crew-members) | `CrewMember` | the kerbal's name | a search of the game's roster |
| [reference frame](#reference-frames) | `ReferenceFrame` | the identities of everything it is defined against | resolving each of them |
| [comm node](#comm-nodes) | `CommNode` | nothing the game offers, so the node object itself | nothing to resolve |
| [science data](#science-data) | `ScienceData` | its part, its experiment module, and the record itself | nothing to resolve for the record; its owner resolves |
| [science subject](#science-subjects) | `ScienceSubject` | the subject id, within one game state | nothing to resolve; the generation is compared |

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

### Part modules

A module and its part are components of the same `GameObject`, so destroying the part destroys its
modules. A module proxy inherits its part's classification and needs no separate persistent-form
search: it is destroyed or dormant exactly when its part is, and live while a live part still has
the module. The implication runs the other way too, a module that is not
Unity-destroyed proves its part is not either, which is what lets a resolved module answer for
both without the part being resolved at all.

Every module proxy captures its module today, which is the rest of #885 and all of #764.
`ModuleRef` replaces the captured reference. A module proxy is keyed on its part, the module's
class, and which of the part's modules of that class it is. The game rebuilds a part's modules in
the order its configuration lists them, so that outlives any one of them, which is why it is what
equality and hashing use, and why `Module` hashing the captured `PartModule` has to go.

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

A proxy standing for several modules holds a reference to each rather than a list of the modules:
`Engine` keeps one per mode, and `ResourceConverter` one per converter, in the order its index
arguments count in. A list of modules is the same captured reference in another shape.

`Decoupler` keeps its access path as it is and takes the state getter only, deferred to its part. Its
per-access cost is reflection inside a compatibility wrapper shared with
`PartExtensions.DecoupledAt`, so a cheaper module lookup buys nothing, and keeping that wrapper
does not stop it being reclaimed.

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

`Stage` holds a `Vessel` proxy rather than the KSP vessel, so its identity is a vessel id and
resolving is the vessel's job. Reading `.id` off a captured Unity object inside `Equals` is the one
thing [Identity](#identity) forbids.

`ResourceTransfer` is the one of these that runs on its own. Its update is driven by the game's
fixed update rather than by a client call, so there is nobody to raise the exception at, and it
reads its parts' states instead of resolving them: a destroyed part cancels the transfer, since
nothing can move into or out of it again, and a part whose vessel the game has unloaded is
neither gone nor being simulated, so the transfer waits for it. Without that, a transfer over a
part the game destroyed threw on every update and never completed.

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
celestial body alone never dies.

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

### Deliberately not covered

These classes do not implement `IGameObjectState`, on the same two grounds: what they stand for is
never destroyed, and the set of them is bounded, so the state would always be live and nothing
would ever be swept.

| Excluded | Why |
|---|---|
| `CelestialBody` | bodies are never destroyed and the set is bounded |
| `ConfigNode` | a part's configuration comes from the game's part database, which is built once at startup and not torn down with any game state |
| `Camera`, `AlarmManager`, `ContractManager`, `WaypointManager` | one instance each |
| `Alarm`, `Contract`, `ContractParameter`, `Waypoint`, `LaunchSite`, `CommLink`, `ClosestApproach` | outside the scope above; each is worth revisiting on its own evidence |
| `Force` | kRPC creates it and the client removes it, like the Drawing and UI proxies |

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

D is the only variant that is fast on both axes, it fixes all four issues, and each alternative
below was turned down on evidence, several of them after being built and measured:

| Alternative | Why not |
|---|---|
| Check the remembered position against the module list's length and the class at it | Built that way before the id gave the position something exact to be checked against. Those are the only signals `PartModuleList` offers, and neither sees a change that leaves the length alone. Measured, the two checks cost about what the id check costs, so exactness here is free. |
| Remember the module itself, in the same weak reference the part path uses | Exact, and it lets a module getter skip resolving its part, but a weak reference costs about as much to read as resolving the part does, where reading a remembered position costs a fifth of that. Built and measured: `module.ref` 43.8 ns against 15.4, and `engine.thrust`, which reaches two modules, 81.9 ns against 46. It also allocates one weak reference per reference. The part path caches because its lookup is a search of every loaded vessel; a module's lookup is a walk of one part's modules, which is cheaper than the cache that would avoid it. |
| Let the persistent id be what a module proxy stands for | Tempting: it is the game's own name for a module, a part's flight id one level down, and it makes every lookup exact. It is not durable in the direction that matters. The game gives a module an id only when something asks, and writes out only ids it has already given, so a save written before a client named the module carries none for it. A quickload to such a save would leave every module proxy holding an id nothing answers to, which is [#764](https://github.com/krpc/krpc/issues/764) again, so the id is a way to find a module rather than what one is. |
| Keep captured references, check `Destroy()` before use | The fastest possible access, but a strong reference to a destroyed object is exactly the #771 leak, and it does not fix #764: after a load the captured module is stale even though an equivalent one exists. |
| Pure id re-derivation everywhere (version A) | Correct, but pays a module scan on every access and gives up a free win on the part path. |
| Pure weak references, no ids | Identity, hashing and store dedup need a value that outlives the object; hashing a weak referent changes the hash when it is collected, so the proxy can never be removed from the store. Also cannot detect destroy-and-recreate-with-the-same-id. |
| KSP `GameEvents` (`onPartDie` and friends) as the primary mechanism | Requires a case-by-case implementation per object kind, and KSP does not raise events for every kind or every destruction path. Fine as a latency optimization on top (see [Phases](#phases)), wrong as the foundation. |
| Weak references in the object store itself | The store holds the only strong reference to a proxy; making it weak collects proxies that clients still hold ids for. |
| Record only where a module was found, not that a part has none | An object with an optional module it does not have, an engine with no gimbal, then searches the whole module list on every access, since nothing records the absence. Built that way, `engine.thrust` cost 1165 ns. A reference records a part having no such module as readily as which module it found, so both answers cost an index and a string comparison. |
| A module reference generic on the module type | Built and measured: the shared generic it compiles to costs 21 ns against 7 ns for the indexed lookup underneath it, so the wrapper cost three times the work it wrapped. Naming the module by its class name keeps the whole resolve path non-generic; with the absence fix above it took `module.name` from 51 ns to 46 ns and `engine.thrust` from 1165 ns to 46 ns. |

Two findings from that run outlived its numbers. **The part lookup was never the bottleneck**:
`part.mass` is mostly KSP's own mass computation, and the resolve strategy moves the total by
single-digit percent. **The real cost of the fix is module re-derivation**, from a captured
reference to a re-derived one.

One optimization deliberately **not** adopted: caching the resolved `PartModule` behind the same
weak reference would let module getters skip part resolution entirely, and would be correct, since
destroying a part destroys its modules. It was first turned down on a gain within measurement
noise, then built and measured when the id gave it a second reason to exist, and it is a
regression on both counts; the numbers are in the table above.

## Phases

The general infrastructure comes first, the game-object-specific work next, the documentation and
the SpaceCenter benchmarks last. That order is what lets the work land as separate pull requests:
phases 1 to 3 name no game object, phase 4 is one game object at a time, and phases 5 to 7 sit on
top of whatever of phase 4 has landed.

Phases run in order, and within phase 4 each game object builds on the ones above it. A phase is a
sequence of commits wherever it needs to be, each commit doing one thing. Tests land with the phase
they exercise. Changelog entries belong to no phase; they are consolidated into a single commit
before the branch is pushed.

| # | Phase | Contents |
|---|---|---|
| 1 | Benchmarking framework | Per [build-tools/benchmarks.md](build-tools/benchmarks.md): the timing RPCs in `TestingTools`, the runner, and the scripts and craft under `tools/benchmarks/`, with its section of the development guide. Nothing here is specific to this design, and no case it ships measures anything this design adds. Each later phase A/Bs against the build before it. |
| 2 | Core infrastructure | `ObjectDestroyedException`; `IGameObjectState` and `GameObjectState`; the store sweep and reclaimed-id semantics; `GameState` and the load boundary the server addon raises it at; core unit tests. No service uses any of it yet, so no behavior changes. |
| 3 | SpaceCenter infrastructure | The SpaceCenter-side pieces every later phase builds on, and no game object of its own: the testing tools a lifetime test needs, destroying a part and sizing the store, and `CachedObject<T>`, which stamps its weak reference with `GameState`'s generation and so comes after phase 2. |
| 4 | SpaceCenter game objects | One sub-phase per kind of game object, in the order of [SpaceCenter implementation](#spacecenter-implementation); see below. |
| 5 | Event-driven reclamation | Subscribe to `onPartDie` / `onVesselDestroy` so obviously dead proxies leave the store immediately rather than at the next load boundary. Pure latency improvement over the sweep from phase 2. |
| 6 | Documentation | `doc/src/object-lifetime.rst`, a page of its own explaining rebinding, the exception, and what a client should do about it, linked from every client's page where remote procedures are introduced, and in `doc/order.txt`. It is client-facing behavior rather than part of any one language's client, and nothing else in the docs covers what an object is. The exception itself is documented across all client languages. |
| 7 | SpaceCenter benchmarks | The cases that measure what this design added: the resolution primitives against each other (captured reference, cached resolve, `FindPartByID`, indexed module lookup, the module reference, a by-name scan), and the accessors the [Budgets](#budgets) are written against. Last because each of them names something phase 3 or 4 introduces. |

Phase 4, one game object at a time:

| # | Game object | Contents |
|---|---|---|
| 4a | [Vessels](#vessels) | `Vessel` opts into liveness and resolves through the cache; a failed lookup throws `ObjectDestroyedException`, and the between-states window is dormant. |
| 4b | [Parts](#parts) | `Part` resolves through the cache and classifies itself against the proto-part snapshots of unloaded vessels, so an unloaded vessel's parts are dormant rather than destroyed. Fixes the `Part` half of #885 and, with the sweep, the pinning half of #771. |
| 4c | [Part modules](#part-modules) | `ModuleRef`, keyed on the part, the module's class and the occurrence, and resolving through the remembered position validated by the persistent id; `Module` and the ~28 concrete module proxies converted onto it; their equality and hashing rebased off the captured module. Fixes the rest of #885 and all of #764. |
| 4d | [Fields, events and actions](#a-modules-fields-events-and-actions) | `PartField`, `PartEvent` and `PartAction` look themselves up by name on their module on each access; `ActionGroupAction` carries the part, module and names as values and defers its state. |
| 4e | [Named against a vessel or a part](#anything-named-against-a-vessel-or-a-part) | The parts collections, `AutoPilot`, `Control`, `Comms`, `Flight`, `Resources`, `Resource`, `Propellant`, `Stage` and `ResourceTransfer` defer to their owner. `Stage` holds a `Vessel` proxy rather than the KSP vessel; `ResourceTransfer` reads its parts' states rather than resolving them, so a destroyed part cancels the transfer and an unloaded one makes it wait. |
| 4f | [Maneuver nodes](#maneuver-nodes) | `Node` holds the node object for its whole life and answers from the vessel's flight plan instead. Closes the hash bug that nulling the field on removal would cause, and the FIXME on `Node`. `Orbit` lands here rather than in 4e: an orbit is named against its owner like the rest, but one owner is a maneuver node, so it cannot be written before the node can be asked. |
| 4g | [Crew members](#crew-members) | `CrewMember` compares by the name it is already named by, so the store dedups it and the roster search answers for its state. |
| 4h | [Reference frames](#reference-frames) | A frame is as alive as everything it is defined against, hybrid frames included; part-relative and docking-port frames re-derive from ids, which closes the raw `NullReferenceException` from `DockingPort.ReferenceFrame`. |
| 4i | [Comm nodes](#comm-nodes) | `CommNode` holds the game's object and is live while its transform is either absent or not Unity-destroyed. |
| 4j | [Science data](#science-data) | `ScienceData` defers to its experiment module, and to that module still listing the record where the part is live. |
| 4k | [Science subjects](#science-subjects) | `ScienceSubject` gains an identity, the subject id plus the generation it was read in, and is live while that generation is the loaded one. The science gain multiplier is read on each access rather than captured. |

## Testing

`service/SpaceCenter/test/test_object_lifetime.py` and the core unit tests in
`core/test/Service/` cover:

| Case | Covered by |
|---|---|
| destroyed part, and the modules of a destroyed part, raise `ObjectDestroyedException` | `test_reading_a_destroyed_part`, `test_reading_a_module_of_a_destroyed_part` |
| proxies survive a quickload and read the rebuilt objects (#764) | `test_objects_survive_a_quickload`, `test_modules_survive_a_quickload` |
| module proxies survive a load of a game state written before the client named the module, which carries no id for it | `test_modules_survive_a_load_of_a_save_that_predates_them` |
| a destroyed part leaves the store on the destruction event (#771) | `test_the_store_drops_a_destroyed_part` |
| a load boundary sweeps the store (#771) | `test_the_store_drops_dead_objects_on_a_load`, which uses a maneuver node: a load rebuilds a vessel's parts under the ids their proxies name them by, so parts survive it and demonstrate nothing, and no destruction event covers a node |
| a destroyed vessel, and everything reached through it, raise `ObjectDestroyedException` | `TestObjectLifetimeDestroyedVessel` |
| a part of an unloaded vessel reports not-loaded rather than destroyed, survives a sweep, and works again once the vessel loads | `test_parts_of_an_unloaded_vessel`. Asserting on the client's `RuntimeError` cannot tell the two apart, since the Python client builds `ObjectDestroyedException` as a subclass of it and maps `InvalidOperationException` to it, so the test asserts on the exception's type and message |
| sweep drops dead proxies, keeps proxies without liveness, removes one exactly once, never reuses ids | `ObjectStoreTest` |
| reclaimed id throws `ObjectDestroyedException`, unissued id throws `ArgumentException` | `ObjectStoreTest.RemovedAndUnissuedObjectIds` |
| the generation moves at a boundary, a sweep leaves it alone, a change leaves a sweep pending | `GameStateTest` |

The service suites for maneuver nodes, orbits, reference frames, resource transfers, resources,
comms, docking ports and part modules were run against each phase; the maneuver node tests were
updated to expect the object-destroyed error where they expected an invalid-call error.

Specified in this design and **not** covered by a test:

 * the fields, events and actions of a destroyed part raising the exception (the part and its
   modules are covered);
 * a merely packed vessel, inside `unload` range, being entirely unaffected;
 * store size returning to a stable level over *repeated* quickloads, rather than the single load
   the store tests check;
 * a stream over a destroyed part delivering the error once and being removed, per
   [protocol/stream-invalidation.md](protocol/stream-invalidation.md);
 * every liveness implementation other than `Part` and the module reference. `CommNode`,
   `ScienceData`, `ReferenceFrame`, `ResourceTransfer`, `ScienceSubject` and `Stage` all carry
   real logic and none of it is exercised. `CommNode`'s is the one to pin down first: it is alive
   when its transform is either absent or not Unity-destroyed, which is the two-stage death of a
   Unity object written out in one line;
 * a module reference rebinding when a part's module list changes under it, which is the case
   [Open questions](#open-questions) identifies as the one a mod could provoke. Nothing in KSP
   does it, so provoking it needs a test module built for the purpose;
 * a dormant object reporting not-loaded on a path other than `Part`: a maneuver node on a vessel
   the game is not solving conics for, and any object at all in the window where the game is
   between states and lists no vessels.

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

From the benchmark suite ([build-tools/benchmarks.md](build-tools/benchmarks.md)), run as
`bazel run //:test-ingame -- tools/benchmarks/`, all on 2026-07-25 on one machine, five chunks per
case, best of the five with the empty-loop cost subtracted. Each column is a whole build, so the
four are an A/B of the work: `main` before any of it, then after the core infrastructure and the
vessel and part work, then after the part modules, then after the module reference was reworked
onto the persistent id. Absolute values are
machine specific; the ratios within a run and the allocation counts are what carry. The variant
numbers under [Alternatives considered](#alternatives-considered) came from another harness on
another machine and do not compare with these at all: that run put `part.mass` at 667 ns.

Per access, on the reference craft (`Parts.craft`, 58 parts in flight):

| Case | `main` | after parts | after modules | after the id | |
|---|---:|---:|---:|---:|---|
| `part.name` | 107 | 32 | | 32 | a scan on every access became a cache read |
| `part.mass` | 1431 | 1355 | | 1411 | budget met: no slower than `main` |
| `module.name` | 4.5 | 4.7 | 46 | 45 | budget met, against a ceiling of 50. Still the captured module, and the bug, until the module reference lands |
| `module.part` | | | 4.8 | 4.7 | no module lookup, so unchanged |
| `engine.thrust` | 6.3 | 5.9 | 46 | 46 | one part and two module lookups |
| `parachute.state` | 5.4 | 5.2 | 42 | 40 | same, after the getter was made to resolve its module once rather than on each mention |
| `part.engine` | 8940 ns, 2212 B | 9032 ns, 2095 B | 9000 ns, 1882 B | 9104 ns, 2070 B | the engine no longer keeps a list of its modules. The 188 bytes the id adds are `Guid.NewGuid` inside the game's own id generation, once per reference built, on no fast path |
| `vessel.parts.all` | 1782 ns, 2493 B | 1955 ns, 3433 B | | 1995 ns, 3435 B | 58 part objects, each 16 bytes larger for the cache it carries. No new allocation, and nothing on a fast path |
| store dedup | 12.4 | 12.9 | 13.1 | 12.5 | equality rebased onto identifiers without moving it |
| stream update, one per part | 0.75 / 3.81 ms | 0.76 / 3.70 ms | | 0.75 / 3.71 ms | 58 / 321 parts |

Every access fast path measures 0.00 bytes per operation, with no collections, in all four runs.

The resolution primitives are implemented in the benchmark service and measured against each other
within one session, so comparisons down a column are results; comparisons across columns are not.
On the reference craft:

| Primitive | `main` | after parts | after modules | after the id |
|---|---:|---:|---:|---:|
| captured reference plus a Unity null check | 3.0 | 3.9 | | 3.7 |
| weak-reference cached resolve, nothing added | 22.8 | 23.2 | | 23.0 |
| the cache as shipped | | 32.3 | | 32.2 |
| `FindPartByID` | 112 | 124 | | 113 |
| indexed module lookup, hand written | 7.2 | | 6.8 | 7.7 |
| the module reference as shipped | | | 15.4 | 14.8 |
| module lookup by persistent id | | | | 14.8 |
| by-name module scan | 39.8 | | 42.5 | 43.7 |
| `OfType<T>().ToList()` | 1551 (163 B) | | 1628 (164 B) | 1622 (160 B) |

What that settles:

 * **A cached resolve beats re-deriving, and more so at scale.** 23 ns flat against `FindPartByID`
   at 112 / 301 / 516 ns for 58 parts, 174 parts over 3 vessels, and 321 parts: linear in loaded
   parts across vessels as well as within one.
 * **The game-state stamp and the shared shape cost about 9 ns** (32.3 against 23.2), against 90 ns
   saved on the smallest scene the suite has and 470 ns on the largest. If that 9 ns is ever worth
   chasing, the two things it pays for are a static property read across the assembly boundary and
   a generic type shared between every kind of Unity object.
 * **Indexed module lookup beats a by-name scan**, 7 ns against 40, a wider margin than the numbers
   this design was written from; and `OfType<T>().ToList()` at 1551 ns and 163 bytes per call is
   ~200x an indexed lookup, so it is worth avoiding anywhere on a fast path.
 * **Validating the index with the id is free.** The shipped reference costs the same checked
   against a `uint` the game guarantees as it did checked against the module list's length and the
   class at the index, 14.8 ns against 15.4, so nothing was traded for exactness.
 * **Looking a module up is cheaper than caching it.** A weak reference costs 23 ns to read, and
   the walk it would save costs 15, so remembering the module rather than where it was is a loss
   before the part is even considered: `module.ref` 43.8 ns and `engine.thrust` 81.9 ns when it
   was built that way. This is the opposite of the part path, whose lookup is a search of every
   loaded vessel, and it is why only one of the two caches.
 * **The id walk and the remembered position are level on these parts** (14.8 against 14.8), which
   carry few modules. The walk is linear in a part's modules and the position is not, so the
   margin is a property of the craft rather than of the code.

Still unmeasured:

 * **The store sweep.** It exists, but nothing times it. The dedup path is measured in its place and
   is flat in store size (12.4 ns at 58 entries, 12.5 ns at 321).
 * **A delegate-based helper against hand inlining.** No case exists for it. The design avoids
   delegates on the strength of one earlier cut that measured as a regression, and of B against B.2
   above, which was noise in both directions.

Nothing in the suite bears on the correctness half of this design, dormant versus destroyed, sweep
semantics, reclaimed-id lookup or hash stability. That is what the tests under
[Testing](#testing) are for.

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
 * **Is a kerbal's name stable enough to be an identity?** A `CrewMember` is named by it, and
   the game keeps its roster under it, but `CrewMember.Name`'s setter renames the kerbal
   through `ProtoCrewMember.ChangeName`. The object is then holding a name the roster no
   longer answers to: it stops resolving, reports itself destroyed and is swept, so a client
   loses the very object it renamed through, while a client that had another object for the
   same kerbal loses that one too. Nothing but that setter renames a kerbal. The ways out are
   to name a kerbal by something the client cannot change, if the game offers one, to have the
   setter carry the object's identity forward with the rename, or to leave it and say that
   renaming invalidates the objects for that kerbal.