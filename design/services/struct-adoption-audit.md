# Audit: RPCs that should return a structure

**Status:** proposal. No issue yet. Follows
[structure types](../protocol/struct-types.md) (issue
[#866](https://github.com/krpc/krpc/issues/866)), which landed in the unreleased 0.7.0 cycle and
named two first-adoption candidates without surveying the rest. This audit does that survey.

Nothing under `service/` uses `[KRPCStruct]` today. The only structures in the tree are the test
fixtures in `tools/TestServer/src/TestService.cs` and `core/test/Service/TestService.cs`.

Each conversion below is its own issue and its own PR. All of them are breaking, except the
`RCS.Override` merge in the last section.

## Why it matters

A structure sends the values of all its fields in the reply to one call. A class costs one call
per member, plus an entry in the global object store (`core/src/Service/ObjectStore.cs`) keyed by
the object itself, so every instance returned pays an `Equals`/`GetHashCode` lookup and is swept
when the game state changes. The hash code cost of exactly these short-lived handles was the
subject of [#1071](https://github.com/krpc/krpc/pull/1071).

The per-call cost is often worse than the round trips alone. `Propellant.InternalPropellant` runs
`GetComponents<ModuleEngines>` and a linear search on every property read, so `Engine.Propellants`
on a four-propellant engine is 41 calls, 40 component scans and 4 handles. As a structure it is
one call and four scans.

## Method

Enumerated every `[KRPCClass]` in `service/` and `core/`, 96 of them: 68 in SpaceCenter, 26 in
the mod services and 2 in `core`. Each was classified against the rules below. Rules 1 to 3 are
enforced by `TypeUtils.ValidateKRPCStruct`. Rules 4 and 5 are judgment, and restate the guidance
already in `doc/src/extending.rst`.

1. Every `[KRPCProperty]` is read-only. A setter mutates game state, which a value cannot do.
2. There are no `[KRPCMethod]` members. `ServiceSignature.AddStruct` collects fields only.
3. No field is nullable, sets a `GameScene`, or makes the structure recursive.
4. Clients read the fields together, and a snapshot taken at the call is what they want. A class
   whose value a client holds and re-reads is a live view, and stays a class.
5. Every field is cheap. A structure computes all of them on every read.

A nullable *return* composes fine. `[KRPCProcedure (Nullable = true)]` on a structure generates
`TestStruct?` in the C# client. Only fields may not be null.

A structure carries no `GameScene`, but the four classes recommended below are all reached through
a Flight-scoped member, so the restriction survives on the producing RPC.

## Convert

| Class | Fields | Returned by |
| --- | --- | --- |
| `LaunchSite` | 3 | `SpaceCenter.LaunchSites` |
| `Propellant` | 10 | `Engine.Propellants` |
| `ScienceSubject` | 7 | `Experiment.ScienceSubject` |
| `ScienceData` | 3 | `Experiment.Data` |

`LaunchSite` already stores its three values in auto-properties, so the conversion changes no
behavior at all. It is the worked example in `doc/src/extending.rst`, under the name
`LaunchSiteInfo`.

`ScienceData.TransmitValue` builds an `ExperimentResultDialogPage` and runs a `ScienceLabSearch`,
so a structure pays that on every read of the record. It is still worth converting, because
`Experiment.Data` returns a list and a client reading one field of one record is rare.

## Blocked on nullable structure fields

| Class | Fields | Blocker |
| --- | --- | --- |
| `ActionGroupAction` | 4 | `Module` is `Nullable = true`, null only under Extended Action Groups |
| `CommNode` | 5 | `Vessel` throws for a ground station rather than returning null |

Both are otherwise textbook records. `ActionGroupAction` stores all four values at construction
and has no methods, and `Control.GetActionGroupActions` returns a list of them.

`CommNode` gates `CommLink` as well. `CommLink` has four read-only fields, no methods, and builds
its two `CommNode` values eagerly in its constructor, so it is already a snapshot in all but name.
`Comms.ControlPath` returns a list of them.

[structure types](../protocol/struct-types.md) made fields non-nullable in v1 and put per-field
presence behind the tagged encoding it rejected. That is the right call for value-typed fields. It
is more than this shape needs: both blockers are class-typed fields, and
`ObjectStore.AddInstance (null)` already returns 0, which is still the reserved null id. A
class-typed field can therefore carry null with no wire change. What stands in the way is the null
guard in `Encoder.WriteStruct` and `Encoder.DecodeStruct`, the `ValidateStructFields` rejection of
`Nullable`, and decoding id 0 as absent in each client.

## Blocked on other rules

| Class | Fields | Blocker |
| --- | --- | --- |
| `ContractParameter` | 11 | `Children` makes it recursive |
| `ConfigNode` | 3 | Recursive through `Nodes`, and six methods |
| `Stage` | 19 | One method, `Resources (bool cumulative)` |
| `Contract` | 25 | Three methods: `Cancel`, `Accept`, `Decline` |
| `ClosestApproach` | 8 | Four nullable fields and six reference frame methods |

`Stage` and `Contract` are the largest round-trip wins in the list, at 19 and 25 members. Neither
is a straight conversion even once the methods move, for the reason under *Leave as classes*.

## Leave as classes

`Comms` passes rules 1 to 3. Its `ControlPath` field would rebuild the whole control path on every
read of `SignalStrength`, so it fails rule 5. `Stage` has the same shape: its `Parts` field would
build a part list per stage on every read of `Vessel.Stages`. A structure for either one has to
drop the collection field, which is an API redesign rather than a migration.

Outside SpaceCenter there are no candidates at all. All 26 classes in Drawing, UI,
InfernalRobotics, KerbalAlarmClock, RemoteTech, LiDAR and DockingCamera wrap a Unity `GameObject`
or a mod API object, and nearly all of them implement `IGameObjectState`. `KRPC.Type` and
`KRPC.Expression` are opaque handles with no fields at all.

Everything else in SpaceCenter is a live handle. Note for anyone repeating this by counting
properties: the part-module wrappers that look read-only at a glance (`Wheel`, `ControlSurface`,
`Light`, `Radiator`, `Sensor`, `Intake`, `Leg`, `ReactionWheel`, `SolarPanel`, `CargoBay`,
`RoboticRotor`, `ResourceHarvester`) each carry actuator setters, and a naive scan reads them as
candidates.

## Tuples that should be structures

23 RPCs return `TupleT3`, an unnamed
`Tuple<Tuple<double,double,double>,Tuple<double,double,double>>`, in three families.

| Family | Count | Fields | Members |
| --- | --- | --- | --- |
| Positive and negative axis torque or force | 20 | `Positive`, `Negative` | `Vessel.AvailableTorque` and 13 siblings, `ReactionWheel.AvailableTorque`, `ReactionWheel.MaxTorque`, `ControlSurface.AvailableTorque`, `Engine.AvailableTorque`, `RCS.AvailableTorque`, `RCS.AvailableForce` |
| Bounding box corners | 2 | `Min`, `Max` | `Vessel.BoundingBox`, `Part.BoundingBox` |
| Force and torque together | 1 | `Force`, `Torque` | `Flight.SimulateAerodynamicWrenchAt` |

These cost nothing extra on the wire: a structure encodes as a `Tuple` message, so the bytes are
identical and the saving is in the names. The Python client builds a structure as a named tuple,
so index access keeps working there. The typed clients get a new type and break.

`Tuple3` and `Tuple4` positions, directions and rotations stay tuples. They are coordinates, not
records, and every client already has vector conventions built around them.

## Do before 0.7.0 ships

`RCS.OverrideForce` and `RCS.OverrideTorque` are new in the unreleased cycle
([#1080](https://github.com/krpc/krpc/issues/1080)). They take the same two parameters and differ
only in what they return. One `RCS.Override` returning a structure of
both halves the calls, and breaks nothing, since neither has shipped.

Every other conversion in this document is breaking, so each one either lands in 0.7.0 or waits
for the next cycle that carries a break.
