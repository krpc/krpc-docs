# Inheritance for remote objects (issue #905)

**Status:** proposal (2026-10-25). Nothing implemented. Written against `krpc` at version 0.8.0.

[Issue #905](https://github.com/krpc/krpc/issues/905) asks for service class hierarchies to reach
the clients. Today the scanner flattens them, so each class carries a copy of every inherited
member. The issue thread settled on three things:

* explicit `[KRPCClass]` on every exposed class
* the parent's name stored in the class definition
* C# rules, meaning single class inheritance, with base class instances allowed

It left multiple inheritance and the wire format open. This doc closes both.

## Why

UI and Drawing already have C# hierarchies. Duplicated procedures, counted by member name in the
generated service definitions:

| Service | Classes | Procedures | Duplicated | C# hierarchy |
| --- | --- | --- | --- | --- |
| UI | 15 | 234 | ~90 (38%) | `Object` → `Control`, `Container` → `Button`, `Panel`, … |
| Drawing | 13 | 294 | ~186 (63%) | `Drawable<T>` → `Path<T>`, `SphereShape<T>` → `Line`, `Box`, … |
| SpaceCenter | 64 | 1464 | ~248 | None among `[KRPCClass]` types |

With a hierarchy, `List<UI.Object>` and `List<Drawing.Drawable>` become typeable. One
`remove_all(drawables)` then covers every drawing type, and the generated clients and API docs
shrink.

Inheritance also unblocks two follow-ups that
[extension-members.md](extension-members.md) deferred: a polymorphic `Module` bridge and typed
module discovery (`Part.modules_of_type`).

## Decisions

| Question | Decision | Reason |
| --- | --- | --- |
| Which classes are exposed | Only those marked `[KRPCClass]`, as today | The author controls the hierarchy, e.g. exposing `A`, `B`, `C` and hiding `D` |
| Base of an exposed class | The nearest `[KRPCClass]` ancestor, or none | Skips internal helper classes |
| Multiple inheritance | Single class inheritance only. Interfaces are out of scope | Every OOP client supports a single base. The interface cases below are weak |
| Member placement | A member belongs to the class that declares it | Virtual dispatch on the server runs any `override` |
| Override of a KRPC member | Not a new member. Same procedure as the base | The base procedure already dispatches to it |
| `[KRPCMethod]` in an unexposed class whose subclass is exposed | Scanner error | Otherwise the member has no class to belong to |
| Generic base class | Scanner error if `[KRPCClass]` | Clients have no generics for classes. Drawing drops its type parameter |
| Base in another service | Allowed. `base` is a service-qualified name | The #900 case: `TestFlight.FailureModule : SpaceCenter.Module` |
| Abstract base class | Exposed like any other class | The server never returns an instance whose runtime type is abstract |

## Wire and schema

**The schema change is additive.** `Class` gains a field:

```proto
message Class {
  ...
  string base = 5;  // "Service.Class", empty for none
}
```

The service definition JSON from `servicedefs` gains the same key. Under proto3, an older client
ignores the unknown field.

**The flattened procedures stay.** The scanner emits `Object_get_Visible` for the declaring class
and keeps `Button_get_Visible`. Each rule below matches a rule in
[protocol-compatibility.md](../protocol-compatibility.md):

* A 0.8 client sees what it sees today, plus the new base classes, which are harmless.
* A new client reads `base` and skips each member already declared on an ancestor. The match is
  by member name, which is unambiguous because an override keeps its name.
* Dropping the flattened copies is a breaking change for a later major release. It is not part of
  this design.

**Upcasts need no wire change.** Object ids carry no type. The server checks an argument with
`Type.IsInstanceOfType` (`core/src/Service/Services.cs`), so a `Button` passed to
`Object_get_Visible` already decodes.

**Downcasts need a runtime type.** A client builds a proxy from the static return type. A
`FailureModule` returned as `Module` therefore arrives as a `Module` proxy. The options:

| Option | Wire change | Cost |
| --- | --- | --- |
| A. `KRPC.GetObjectClass(object) -> string`, used by an explicit client-side cast | One new RPC | A round trip per cast |
| B. Class tag on every object value, under a handshake flag | Object encoding changes for clients that opt in | Bytes on every object, and every client's decoder changes |

**Recommendation: A.** No procedure in today's services returns a base-typed value. A cast is
rare, and the RPC is additive. Revisit B if a polymorphic collection turns out to be hot.

## Clients

| Client | Generated form | Notes |
| --- | --- | --- |
| Python | `class Button(Control)` in stubs and in the dynamic client | The dynamic client builds classes in dependency order |
| C# | `class Button : Control` | `UI.Object` collides with `object` only if a generated name is unqualified. Check this in clientgen |
| C++ | Restructure `krpc::Object<T>` | CRTP blocks a base. Split the equality and hashing helpers from the base, or template the leaf only |
| Java | `class Button extends Control` | |
| Lua | Metatable chain | Dynamic, so no clientgen |
| cnano | No change | Objects are `typedef krpc_object_t`, so base functions already accept a derived handle. Emit base functions only |
| docgen | Base class line plus "inherited from" links | Members are listed on the declaring class |

Option A adds a cast helper per client: `conn.cast(obj, FailureModule)`, `obj.as<FailureModule>()`,
and similar. The cast throws an exception if the runtime class is not a subclass of the requested
one.

## SpaceCenter audit

| Candidate | Fit | Reason |
| --- | --- | --- |
| `Part` → `Engine`, `Decoupler`, … | **No** | These are composition views, not subtypes. One part can be an engine, a decoupler and a docking port at once. [#63](https://github.com/krpc/krpc/issues/63)'s question, whether a part is a solar panel, is answered by the nullable `Part.solar_panel` |
| `Module` → mod-defined module classes ([#900](https://github.com/krpc/krpc/issues/900)) | **Yes, strongest** | Gives a polymorphic `Part.modules` and `modules_of_type`. Needs a cross-service base and option A |
| `RoboticHinge`, `RoboticPiston`, `RoboticRotation`, `RoboticRotor` | **Yes** | All four share `Part`, `Locked`, `MotorEngaged` and `IsMoving`. All but the rotor also share `Damping`, `Rate` and `MoveHome`. A `RoboticServo` base fits |
| `Antenna`, `Leg`, `Radiator`, `SolarPanel`, `Wheel` | Weak | They share `Deployable` and `Deployed`, but each `State` returns its own enum. This needs an interface |
| `Vessel`, `CelestialBody`, `Part`, `DockingPort`, `Node` | No | They share `Position`, `Rotation`, `Direction` and `ReferenceFrame`. This is an interface pattern for convenience, with no is-a relation |
| The `Part` back-reference on 32 classes | Marginal | A `PartComponent` base allows a mixed list, but no API returns one |

UI and Drawing hold the near-term value. In SpaceCenter the value is the #900 module story plus
robotics.

## Phases

Each phase is mergeable on its own.

1. **Schema, scanner and clients.**
   * `Class.base` and the JSON key.
   * The scanner places each member on its declaring class, keeps the flattened copies, and
     reports the new errors.
   * clientgen for Python, C#, C++ and Java, the dynamic Python and Lua clients, and docgen.
   * Conformance tests for skipping inherited members and for tolerating an unknown base.
2. **Adopt in UI and Drawing.**
   * Mark `UI.Object`, `Control` and `Container` as `[KRPCClass]`.
   * Drop the type parameter from Drawing's `Drawable<T>`. It names the GameObject and nothing
     else. Expose `Drawable`, `Path`, `FramedPath` and `SphereShape`.
   * Add a TestServer hierarchy for the client tests.
3. **SpaceCenter robotics.** Add a `RoboticServo` base. The change is additive.
4. **Runtime type and casts.** `KRPC.GetObjectClass` plus the client cast helpers. Then the #900
   follow-ups: a mod `[KRPCClass]` deriving from `SpaceCenter.Module`, and `Part.modules`
   returning it.
5. **Later major release.** Drop the flattened procedures.

## Constructors

[#898](https://github.com/krpc/krpc/issues/898) asked for `[KRPCConstructor]`, called from the
client as `Vessel("foo")`. It is closed. A `public static` `[KRPCMethod]` on a `[KRPCClass]` is the
supported factory, e.g. `Orbit.CreateFromOrbitalElements`, `ReferenceFrame.CreateRelative` and
`ResourceTransfer.Start`.

| Constructor drawback | Detail |
| --- | --- |
| One per class | Procedure names are unique, so `Orbit`'s two factories cannot both be constructors |
| Clashes with decoding | Each OOP client's class constructor wraps a returned object id |
| Weaker semantics | A constructor cannot be streamed or return null |
| Few objects to construct | The game creates vessels, parts and bodies. kRPC-created objects need a parent, e.g. `Container.AddButton` |

Inheritance needs no constructor support. A C# constructor is not inherited.

## Open points

* Whether an override may narrow a return type (C# 9 covariant returns). The mod targets net472,
  whose runtime lacks covariant returns, so not yet.
* Whether `[KRPCClass]` on a base should require at least one member. Lean no: an empty base is
  still useful for typing a list.
* Interfaces, if the deployable or spatial cases ever earn them. They would need a repeated
  `interfaces` field, and the cnano and Lua mapping.
