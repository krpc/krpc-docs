# Audit: RPCs that should return a structure

**Status:** in progress. No issue yet. Follows
[structure types](../protocol/struct-types.md) (issue
[#866](https://github.com/krpc/krpc/issues/866)), which landed in the unreleased 0.7.0 cycle and
named two first-adoption candidates without surveying the rest. This audit does that survey.

The three conversions that nullable fields blocked are done, as step 5 of Phase 2 of
[nested nullable values](../protocol/nested-nullable-values.md). Everything else here is
outstanding.

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
3. No field sets a `GameScene` or makes the structure recursive. A field may be null.
4. Clients read the fields together, and a snapshot taken at the call is what they want. A class
   whose value a client holds and re-reads is a live view, and stays a class.
5. Every field is cheap. A structure computes all of them on every read.

A nullable *return* composes fine. `[KRPCProcedure (Nullable = true)]` on a structure generates
`TestStruct?` in the C# client.

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

## Converted, once a structure field could be null

| Class | Fields | Nullable field |
| --- | --- | --- |
| `ActionGroupAction` | 4 | `Module`, null only under Extended Action Groups |
| `CommNode` | 5 | `Vessel`, null for a ground station |

[nested nullable values](../protocol/nested-nullable-values.md) made a structure field nullable,
which is what these two waited on. `CommNode.Vessel` reads as null for a node that is not a
vessel, in place of the exception it threw.

`Control.GetActionGroupActions` returns a list of `ActionGroupAction` values, and `CommLink.Start`
and `CommLink.End` are `CommNode` values. A two-hop control path read in full is 9 calls rather
than 29.

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

`CommLink` fails rule 4, which the count of read-only fields hides. `Type` and `SignalStrength`
are live readings, rewritten by the game as it rebuilds the network, and a client watching one hop
wants to stream that one double rather than the whole control path. The two `CommNode` values a
link holds are snapshots, so `Start` and `End` cost one call each.

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
