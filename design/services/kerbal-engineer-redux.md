# Kerbal Engineer Redux service

**Status:** in progress. GitHub #288 (shared with MechJeb2, in [mechjeb.md](mechjeb.md)).

## Context

Kerbal Engineer Redux (KER, 1.1.9.5, assembly `KerbalEngineer`) shows flight readouts. It has no
public API. Its values sit in static properties of eight *processor* classes, singletons with an
`Update()` that computes them for `FlightGlobals.ActiveVessel`. `FlightEngineerCore.Update` runs a
processor only when a visible readout has set its `UpdateRequested` flag.

| Processor | Computes | Overlap with SpaceCenter |
| --- | --- | --- |
| `ImpactProcessor` | Impact time, site and biome; suicide burn altitude, countdown, dV, distance, length | None |
| `SimulationProcessor` | KER's own staged simulation, on a thread pool, at most every 150 ms | Stock dV in `Stage`. KER adds RCS, thrust torque and offset, and its own dV algorithm |
| `ManoeuvreProcessor` | First node's burn time and half burn time, from the simulation | `Node` has dV, post-burn orbit. No burn time |
| `RendezvousProcessor` | Phase, intercept and transfer angles, relative AN/DN, launch plane timing | `Orbit` has relative inclination, AN/DN anomalies; `ClosestApproach` covers encounter |
| `ThermalProcessor` | Hottest, coolest and critical part titles, flux totals | Per part. A server side function finds the extremes and sums the fluxes |
| `AttitudeProcessor` | Heading, pitch, roll and rates, AoA, sideslip, glideslope | `Flight` covers all but rates and glideslope |
| `AtmosphericProcessor` | Terminal velocity, pressures, efficiency | `Flight` covers it |
| `SurfaceDistanceProcessor` | Great-circle distance and bearing to target and waypoint | Positions, one formula |

Readouts outside the processors are one-line formulas over values SpaceCenter already has, such
as TWR and time to atmosphere.

## Decisions

* **Wrap three processors**: impact (with the suicide burn), simulation (with burn time) and
  rendezvous. The rest are covered by `SpaceCenter.Flight`, a single formula, or a server side
  function.
  Attitude rates are a finite difference across `Update` calls, so they are only right when
  something calls `Update` exactly once per physics tick.
* **Service `KerbalEngineerRedux`**, in `service/KerbalEngineerRedux/`, no id. `Available` works in every scene, and the procedures in flight.
* **Snapshot structs from procedures.** Each procedure takes a vessel and returns a `KRPCStruct`.
  One call gives a consistent set of values, and a stream of one procedure covers the readout
  group. Groups with no value return null: no impact, no suicide burn, no target, too little dV.
  ```csharp
  [KRPCProcedure (Nullable = true)] public static Impact? Impact (Vessel vessel)
  [KRPCProcedure (Nullable = true)] public static SuicideBurn? SuicideBurn (Vessel vessel)
  [KRPCProcedure] public static IList<Stage> Stages (Vessel vessel)
  [KRPCProcedure (Nullable = true)] public static BurnTime? BurnTime (Vessel vessel, double deltaV)
  [KRPCProcedure (Nullable = true)] public static Rendezvous? Rendezvous (Vessel vessel)
  ```
* **Active vessel only.** Every processor reads `FlightGlobals.ActiveVessel`. Each procedure
  throws for any other vessel, so a script names the vessel it means and a switch fails loudly.
* **Updated on demand.** Each procedure calls the processor's `Update()` itself, so KER's display
  flags are left alone. There is no per-tick cache: other RPCs in the same tick can change the
  inputs, such as the target.
* **Simulation results wait.** The simulation is asynchronous. `Update()` requests a run and
  `SimulationProcessor.Stages` holds the last finished one. A procedure that needs it throws
  `YieldException` until a result arrives that started after the active vessel last changed. A
  stream holds its value while it waits. After 5 s of real time with no result, it throws, with
  `SimManager.failMessage`. The impact procedures need it too: `ImpactProcessor.Update` reads
  `SimulationProcessor.LastStage`.
* **Burn time for any delta-v.** `ManoeuvreProcessor` computes burn time for the first node only,
  through its private static `GetBurnTime (double, ref double, ref double)`. The service binds that
  method and takes the delta-v as an argument. A node's burn time is `BurnTime (vessel, node.DeltaV)`.
* **SI units, SpaceCenter's angle conventions.** KER's tonnes, kN and kN.m become kg, N and N.m.
  Orbital angles are in radians, as in `SpaceCenter.Orbit`. Latitude, longitude and the thrust
  offset angle stay in degrees, as in `SpaceCenter.Flight`.
* **Rendezvous follows the readouts' landed override.** With the vessel or target landed on the
  same body, KER's AN/DN readouts show the launch plane crossing (`AngleToPlane`, `TimeToPlane`).
  The struct does the same.
* **No thermal readouts.** KER keeps only the titles of the hottest, coolest and critical parts. A
  title does not identify a part, and finding the `Part` would be kRPC's own computation. A server
  side function over `Part.Temperature` gives the extremes, and the flux totals, as `Part` objects.
* **No career gating.** KER hides readouts in career without an engineer or the ER-7500 part.
  `FlightEngineerCore.IsDisplayable` also reads false while the UI is hidden. The service ignores it.
* **Binding by reflection** with `Accessor`, as DockingCamera does. `IsAvailable` is false when a
  member is missing. Version 1.1.9.5 is pinned in the in-game test mods.

## API

| Struct | Fields |
| --- | --- |
| `Impact` | `TimeTo`, `Latitude`, `Longitude`, `Altitude`, `Biome` |
| `SuicideBurn` | `TimeTo`, `Altitude`, `DeltaV`, `Distance`, `Duration` |
| `Stage` | `Number`, `DeltaV`, `TotalDeltaV`, `SpecificImpulse`, `Thrust`, `ActualThrust`, `TWR`, `MaxTWR`, `ActualTWR`, `Mass`, `TotalMass`, `ResourceMass`, `BurnTime`, `TotalBurnTime`, `MaxThrustTorque`, `ThrustOffsetAngle`, `RCSSpecificImpulse`, `RCSThrust`, `RCSDeltaVStart`, `RCSDeltaVEnd`, `RCSTWRStart`, `RCSTWREnd`, `RCSBurnTime`, `Cost`, `TotalCost`, `PartCount`, `TotalPartCount` |
| `BurnTime` | `Duration`, `HalfDuration` |
| `Rendezvous` | `PhaseAngle`, `InterceptAngle`, `TimeToTransferAngle`, `AngleToAscendingNode`, `AngleToDescendingNode`, `TimeToAscendingNode`, `TimeToDescendingNode` |

## Editor

`EditorStages (CelestialBody body, double altitude = 0, double mach = 0)` simulates the editor
ship, as KER's editor window does: the body's surface gravity (`9.81 * GeeASL`), and the pressure
at the altitude.

* **A simulation of the service's own.** KER's editor windows write `SimManager`'s gravity,
  atmosphere and Mach each frame, and its results are shared. The service creates its own
  `Simulation` and runs `PrepareSimulation` and `RunSimulation` synchronously on the main thread.
  The part pools the simulator borrows from lock, so this is safe beside a KER run on its worker.
* **Masses without the crew.** In the editor, `part.mass` gains the crew's mass in
  `Part.FixedUpdate` and loses it in `ShipConstruct.GetShipMass`, so KER's result flipped
  between calls. The service calls `UpdateMass ()` on each part first, as `GetShipMass` does,
  which leaves the crew out every time. KER's own editor window normally shows the same.
* **Cost and part counts** join `Stage`: `Cost`, `TotalCost`, `PartCount`, `TotalPartCount`. They
  are for designing a craft, and stock editor delta-v has none of them.
