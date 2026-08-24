# Proxy object conventions

**Status:** reference. Describes the rules in force in `krpc`, for writing a service class,
auditing an existing one and reviewing a pull request that adds or changes one. The reasoning
behind the rules, and the per-class survey of how every service meets them, is in
[object-lifetime.md](object-lifetime.md); this doc is the rules alone.

## What this covers

A **proxy object** is an instance of a `[KRPCClass]` that the server hands to a client as an
object id. The server keeps it in the object store for as long as it is useful, and the client
calls back into it by id. Everything below follows from two facts about that arrangement:

* the store is a dictionary **keyed on the proxy**, so equality and hashing are load-bearing
  infrastructure, not conveniences;
* a proxy outlives what it stands for, so every access has to ask the game again, and the object
  has to be able to say the thing is gone.

Four kinds of proxy, each with a different answer to "what ends its life":

| Kind | Examples | Identity is | Life ends when |
|---|---|---|---|
| names something in the game | `Part`, `Vessel`, `Node`, `Alarm`, `Servo` | the game's stable identifier for it | the game destroys the thing |
| defined against other proxies | `ReferenceFrame`, `ClosestApproach`, `Flight`, `Thruster` | the proxies it is built on | those proxies die |
| created on a client's request | `Force`, `Line`, `Panel`, a constructed `Orbit`, a created `ReferenceFrame`, `ResourceTransfer` | itself, or the values it was built from | the client removes it, or disconnects |
| stands for nothing destructible | `CelestialBody`, `ConfigNode`, `KRPC.Expression` | values | never |

The last kind opts out of everything here except [Identity](#identity). The first three do not.

## Identity

| # | Rule | Why |
|---|---|---|
| I1 | A proxy that can be built more than once for the same thing derives from `KRPC.Utils.Equatable<T>` and implements `Equals (T)` and `GetHashCode ()`. | Supplies `Equals (object)`, `==` and `!=`, so those two members are all a class writes, and is what makes the store hand back one object however often the thing is asked for. An object that is a distinct thing each time it is created, a force, a drawing or a transfer, keeps reference identity. |
| I2 | Store the identifier, and nothing else, as identity. | The identifier is the only thing that survives the game rebuilding what the proxy names. |
| I3 | Equality and hashing read the identifier **only**. | A hash derived from resolved state moves over the proxy's life, and an entry whose hash has moved can neither be found nor removed. |
| I4 | Neither may resolve, dereference a game object, or throw. Where the game only hands the identifier over fresh, a Unity object's `name` being the one that comes up, take it once at construction. | Both run while the store is looking an entry up, including the sweep removing a proxy whose game state is gone, which is exactly when a resolve would fail. There is no client call there to attribute a failure to. Reading a name per hash also allocates a string per lookup. |
| I5 | Build the hash with `Hash.Of (a).And (b).And (c)`, never `^` and never a fold written by hand. | Exclusive-or is blind to which field a value came from, so two fields holding the same value cancel out and the objects differing only in them hash alike. Where a pair is always equal, as a hybrid reference frame's components are, every one of them does and the store degrades to a linear walk. |
| I6 | Compare a Unity object or component by `ReferenceEquals`, and hash it by `RuntimeHelpers.GetHashCode`. | Unity's `==` reports a destroyed object as equal to null, so two proxies for different destroyed components compare equal and the store hands back the wrong one. |
| I7 | An object built fresh on each call, for something that was already there before the call, must have value identity. | Otherwise the store takes an entry per call and a script that polls the getter grows it without bound. See [Ways the store grows](#ways-the-store-grows). |

`Hash` (in `core/src/Utils/Hash.cs`) folds each field in at a place of its own, takes any number of
fields, asks a field only for its own hash code so nothing is dereferenced, and converts implicitly
to `int` so it can be returned straight from `GetHashCode`. A value tuple is otherwise the same
idea, but hashes only the last eight fields and silently ignores the rest.

The one place still combining with `^` is the C# client's `Stream`, which is a separate assembly
that does not reference the core, and combines a stream with a conversion key, two values that are
never equal.

## Access

| # | Rule | Why |
|---|---|---|
| A1 | Every member that reaches the game goes through **one** accessor. | One place resolves, one place decides what to raise. |
| A2 | Resolve from the identifier on each access. Never hold the resolved object as state. | A proxy must resolve to what the identifier names in the game **now**, never to data belonging to a replaced game state. |
| A3 | Cache a resolved object only in a `CachedObject<T>` field. | Weak, so a cache never pins a destroyed part and its part graph; stamped with the game-state generation, so an object left over from a replaced state is never handed back; Unity-null-checked against `UnityEngine.Object`, because `==` on a type parameter is reference equality. |
| A4 | Cache only where the lookup costs more than the cache read. | Reading the weak reference is around 23 ns. A part lookup is 113 ns and up, so `Part` caches; a walk of one part's module list is cheaper than that, and is made on each access instead. |
| A5 | A member that hands back what the proxy was built from does not resolve, and so raises nothing. | The part a module belongs to, the name of a field, a stage's number: all identity the proxy has held since construction. What is handed back raises from its own first member that resolves. |
| A6 | Anything else a proxy caches is scoped to `GameState.Generation`. | Nothing a proxy holds otherwise reveals that a game-state boundary was crossed. |

## Classification

Every proxy that can go away implements `KRPC.Utils.IGameObjectState`: one `GameObjectState`
property, returning `Live`, `Dormant` or `Destroyed`.

| State | Meaning | An access that fails to resolve raises | Swept |
|---|---|---|---|
| `Live` | the game state is current | - | no |
| `Dormant` | the game still holds what it needs to build the thing again | `InvalidOperationException`, saying the object is not currently loaded | no |
| `Destroyed` | the game holds nothing for it, and never will again | `ObjectDestroyedException` | yes |

| # | Rule | Why |
|---|---|---|
| C1 | Put the property on **everything** that can go away, whether or not the class re-derives its state. | The sweep reclaims only what opts in, so a class left out accumulates in the store for the whole session however well its accesses behave. |
| C2 | Exactly one classifier per class, exposed as it is rather than as a yes/no derived from it. | The sweep is the only caller that needs less than the full answer, and it can compare against `Destroyed` itself. |
| C3 | `Destroyed` means **definitively gone**. Anything less certain is `Dormant`. | The two mistakes do not cost the same: an object wrongly dropped is gone for good, one wrongly kept costs memory until the next sweep. |
| C4 | It must not throw. | One pass calls it on every entry in the store. The sweep catches and keeps a proxy that throws anyway, and logs it. |
| C5 | Nothing follows from a thing's absence while `GameState.Settled` is false. | The game fills its vessel list, and an editor its part list, over several frames after a boundary. |
| C6 | A proxy defined against others defers rather than classifying itself: `LeastAlive` where it needs all of them, `MostAlive` where any will do. | One classifier per underlying object, no second opinion to keep in step. |
| C7 | Classification may search as widely as it needs to. | It runs only after a resolve has already failed, or from a sweep at a load boundary. The exception is a class read every fixed update, `Part` being the one, which answers `Live` straight from its cache. |

## Objects created for a client, and `Remove`

An object the client asked the server to build stands for nothing the game destroys, so nothing
the game does ever retires it and it would sit in the store for the rest of the session. Such a
class gets a `Remove`. The shape:

```csharp
// Whether the client has removed the frame. A frame a client constructs stands for
// nothing in the game, so nothing the game destroys ever retires one and the client
// saying it is finished with it is the only thing that can.
bool removed;

[KRPCMethod]
public void Remove ()
{
    CheckExists ();
    // only where some instances are the client's and others are not
    if (type != ReferenceFrameType.Relative && type != ReferenceFrameType.Hybrid)
        throw new InvalidOperationException (
            "Only a reference frame created by CreateRelative or CreateHybrid " +
            "can be removed");
    removed = true;
    // whatever lets go of the object; a collection doing so asks for the sweep itself
    GameState.RequestSweep ();
}

void CheckExists ()
{
    if (removed)
        throw new ObjectDestroyedException (
            "The reference frame no longer exists, as it has been removed.");
}

public GameObjectState GameObjectState {
    get {
        if (removed)
            return GameObjectState.Destroyed;
        ...                                   // what it is defined against
    }
}
```

| # | Rule | Why |
|---|---|---|
| R1 | `Remove` is not idempotent: `CheckExists` first, so a second call raises `ObjectDestroyedException`. | Removing something twice is the client using an object that is gone, which is what that exception says. |
| R2 | **Every** member calls `CheckExists`, including those that read no game state. | The object stands for nothing in the game, so there is no resolve to raise on its behalf. |
| R3 | Something has to ask for a sweep. Letting the object go from a `ClientOwnedObjects` collection does; otherwise call `GameState.RequestSweep ()`. | Removing a line, a frame or a force destroys nothing the game raises an event for, so nothing else would take the object out of the store. |
| R4 | Where only some instances are the client's, refuse the rest with `InvalidOperationException` naming the members that build a removable one. | A vessel's orbit or a body-relative frame is named by something in the game, which is what says when it is finished with, and one object is shared by every client that asks. |
| R5 | Anything built on the removed object goes with it through classification, not through bookkeeping. | A `ReferenceFrame` built on a removed frame or orbit, and a `Flight` measured in a removed frame, have nothing left to be evaluated against. |
| R6 | Say in the `<remarks>` who else the removal affects. | A `ReferenceFrame` is deduped, so a frame one client removes is removed for all; a constructed `Orbit`, a `ResourceTransfer` and a `Force` belong to the client that asked for them and go when it disconnects. |
| R7 | Where the disconnect path has teardown of its own, give the collection an `internal Release ()` rather than pointing it at the RPC. | `Remove` is a client call and checks; release is not, and may have to stop something as well as let go. |
| R8 | An addon acting on its objects every frame calls `ClientOwnedObjects.RemoveDestroyed ()` first, then acts only on what is `Live`. | There is no client call in the frame loop to attribute a failure to, so a destroyed object is dropped, and a dormant one waits. |
| R9 | A collection whose objects are never handed to a client passes `givenToClients: false`. | Otherwise a client pushing a part every frame sweeps the store every frame. |

## Exceptions

| Situation | Raise |
|---|---|
| a member of a destroyed proxy that resolves | `KRPC.Service.KRPC.ObjectDestroyedException`, with a message saying why if it is known |
| a member of a dormant proxy | `InvalidOperationException`, saying the object is not currently loaded |
| `Remove` on an instance that is not the client's to remove | `InvalidOperationException`, naming what does build a removable one |
| an id below the store's high-water mark that is not in the store | `ObjectDestroyedException`, from `ObjectStore` |
| an id at or above the high-water mark | `ArgumentException` (a client error) |
| `Equals`, `GetHashCode`, `GameObjectState`, or anything in a frame loop | nothing, ever |

`ObjectDestroyedException` is one type shared by every service, thrown directly with no
`MappedException`, and caught by name in each client language.

## Ways the store grows

What an audit looks for first. The first four have each been a real leak.

| Symptom | Cause |
|---|---|
| an entry per call to a getter | a proxy built fresh per call with no value identity: a per-call wrapper object compared by reference, a `GetComponent` result, a snapshot including a value re-solved on each call |
| an entry per object, forever | the class does not implement `IGameObjectState`, so the sweep skips it |
| an entry that survives its game object | the classifier answers `Dormant` where the thing is definitively gone, or the class has no `Remove` and nothing in the game retires it |
| calls getting slower as a script runs | fields combined with `^` in `GetHashCode`, collapsing distinct objects onto one hash |
| an entry that can never be removed | the hash reads something that changes over the proxy's life |

## What a change has to come with

* A doc comment saying what removes the object, that further use raises, and what goes with it.
* `doc/src/tutorials/object-lifetime.rst` updated where what a client sees changes, and
  `doc/order.txt` where a new member is added.
* An entry in the component's `CHANGELOG.md`.
* An in-game test in `service/SpaceCenter/test/test_object_lifetime.py`: the object works, the
  thing behind it goes away, every kind of member raises, and what was built on it raises too.
  Identity and hashing are testable without the game, in `core/test`.

## Review checklist

1. Does `GetHashCode` read anything but the identifier, or combine fields with `^` or a fold of its own rather than with `Hash`?
2. Can `Equals` or `GetHashCode` resolve, dereference a game object, or throw?
3. Is any Unity object compared with `==` where `ReferenceEquals` is meant?
4. Does the class hold a resolved game object as state, or cache one outside `CachedObject<T>`?
5. Does every member that reaches the game go through the one accessor?
6. Does the class implement `IGameObjectState`, and can that property throw?
7. Does it answer `Destroyed` anywhere the game might still bring the thing back, or draw a
   conclusion from an absence while `GameState.Settled` is false?
8. Is a proxy built on others classifying itself instead of deferring?
9. If a client asks the server to build it: is there a `Remove`, does every member check, and does
   something ask for a sweep?
10. Is a new proxy built fresh on each call to a getter?
11. Does an addon's frame loop reach into an object that may be destroyed?
