# KSA API coverage

**Status:** in progress. Part of [kRPC for KSA](README.md). The service merged in PR #1190. The
manual control inputs are built and tested in game, not yet in a PR. Audited against KSA build
2026.10.19.5638.

The `KSA` service covers flight basics. KSP's `SpaceCenter`, `Drawing` and `UI` services go much
further. This doc lists the gaps that KSA can fill today, and orders them into phases.

## Service Rules

* **One `KSA` service, in KSA's terms** (`Vehicle`, `Body`, `Sequence`, KSA's eight `Situation`
  values), not KSP names.
* **A member with no game counterpart is dropped**, never approximated.
* **`TestingTools`** is a second service, for the in-game tests only.

The original proposal was a strict subset of `SpaceCenter`, with kRPC's signatures, so KSP scripts
would run unchanged. It was dropped on the prototype's findings:

* Much of KSP's API has no exact KSA meaning. Rotation inputs are on/off keys, and `MET` and
  `Vessel.Thrust` have no counterpart.
* Stubs of the same name would collide with KSP's `SpaceCenter` stubs in the static clients.
* C-nano calls by procedure id, numbered in scan order, so a subset gets different ids from KSP's
  until [procedure-ids.md](../protocol/procedure-ids.md) lands.

## Method

* Current API: the `[KRPC*]` members of `experimental/ksa/service/src/Services/`.
* KSP baseline: `service/SpaceCenter`, `service/Drawing`, `service/UI` and `service/Debug`.
* Game surface: reflection over `KSA.dll` (monodis cannot read .NET 10 assemblies), and the module
  kinds used in `Content/Core/*GameData.xml`. The game types named below were checked to exist in
  the dump. Members marked *verify* were not.

## Coverage Matrix

| KSP area | In KSA | Key game types | `KSA` service today | Phase |
| --- | --- | --- | --- | --- |
| Vessels, active vessel | Yes | `Vehicle`, `Universe` | `Vehicle`, `ActiveVehicle`, `Vehicles` | 1 |
| Bodies | Yes | `Celestial`, `PhysicalAtmosphereReference`, `BiomesReference` | Mass, gravity, rotation, SOI, terrain height | 1 |
| Atmosphere queries | Yes, no temperature | `PhysicalAtmosphereReference`, `PhysicsEnvironment` | Pressure and density at the vehicle only | 1 |
| Biomes | Yes | `Celestial.SampleBiomeIdMap`, `BiomesReference` | None | 1 |
| Orbits, patches | Yes | `Orbit`, `PatchedConic`, `TargetData` | Elements, anomalies, `PositionAt`, `NextOrbit` | 1 |
| Targets, closest approach | Yes | `Vehicle.SetTarget(orbiter, part)`, `TargetData` | `TargetVehicle`, `TargetBody` | 1 |
| Reference frames | Yes | Ecl frame chain | Vehicle and body frames, `Transform*` | 1 |
| Maneuver nodes | Yes | Flight computer burns | `Burn`, `AddBurn`, `AutoBurn` | 1 |
| Structural load, debris | Yes | `StructuralLoad`, `Vehicle.IsDebris` | None | 1 |
| Saves | Yes | `GameSaves` | `TestingTools` only | 1 |
| Stages, delta-v | Yes | `Sequence`, `SequencePerformance` | `Sequence` | Done |
| Parts tree | Yes | `PartTree`, `Part` | `Part` | 1 |
| Engines, gimbal | Yes | `RocketCore`, `Gimbal`, `GimbalState` | `Engine` without gimbal | 2 |
| Tanks, crossfeed, transfer | Yes | `Tank`, `FuelLink`, `TankTransferMode` | `Resource` (amounts only) | 2 |
| RCS | Yes | `ThrusterController` | `RCS.Active` | Done |
| Decouplers, docking ports | Yes | `Decoupler`, `DockingPort` | Both, separation returns nothing | 1 |
| Parachutes | Yes | `Parachute` | `Parachute` | Done |
| Power | Yes | `Battery`, `SolarPanel`, `Generator`, `PowerConsumer` | None | 3 |
| Lights | Yes | `PowerConsumer.LightSwitch`, `Vehicle.LightsOn` | None | 3 |
| Legs, bays, deployables | Partial | `KeyframeAnimationModule` (`DeploymentState`) | None | 3 |
| Radiation | Yes, KSA only | `Radiation.ComputeDoseRate`, `ComputeOrbitAverage` | None | 3 |
| Crew | Yes | `KittenRosterData`, `KittenRosterEntryData`, `IVASeat` | None | 4 |
| EVA | Yes | `EVADoor`, `KittenEva` | None. Kittens on EVA are not vehicles | 4 |
| Camera | Yes | `Camera`, `CameraMode`, `OrbitController` | `ActiveVehicle` setter moves it | 5 |
| Screenshots, messages | Yes | `ScreenshotCapture`, `TimedAlert` | None | 5 |
| Debug cheats | Partial | `Vehicle.Teleport`, `TeleportToLocation`, `Universe.DestroyVehicle`, console commands | None | 5 |
| Editor | Yes | `VehicleEditor.LoadVehicle`, `Build` | `LaunchVehicle` only | 5 |
| Drawing | Yes | `GizmosRenderer`, ImGui draw lists | None | 6 |
| UI | Yes | ImGui windows (as in the server window) | None | 7 |
| Manual controls | Yes | `ManualControlInputs`, `FlightComputer.ManualThrustMode` | `Pitch`, `Yaw`, `Roll`, `Forward`, `Right`, `Up` as -1, 0 or 1, and `Pulse` | Done, not yet in a PR |
| Auto-pilot | Yes | `FlightComputer` | `AutoPilot` | Done |

### Absent in KSA

These have no game type, so no API is possible today. Revisit at each KSA release.

| Area | Note |
| --- | --- |
| Science, experiments | No type |
| Career: funds, reputation, contracts, waypoints | No type |
| Antennas, comms | No type |
| Reaction wheels | Attitude comes from RCS and gimbals |
| Control surfaces, lift, aero coefficients | Aero is drag only (`BoundingBoxCdA`) |
| Wheels, landing gear | Legs are animations, ground contact is `Situation` |
| Fairings | Fairing parts are tanks and decouplers |
| Action groups | Toggles live on the modules and `InputAction` |
| Alarms | Only on-screen `TimedAlert` toasts |
| Thermal simulation | `FxTemperature` is visual only |
| Air temperature, Mach | `PhysicalAtmosphereReference` has pressure and density only |

## Phases

Each phase merges on its own, with in-game tests for every new member.

### 1. Existing Classes

| Class | Add | Game source |
| --- | --- | --- |
| `KSA` | `ClearTarget`, `Save`, `Load`, `SaveExists` (from `TestingTools`), last physics step | `Universe.UnsetTarget`, `GameSaves`, `Universe.GetLastSimStep` |
| `Vehicle` | `TargetPart`, `IsDebris`, `PeakGLoad`, `MaxGLoad`, `PeakDynamicPressure`, `MaxDynamicPressure`, surface velocity | `Vehicle.TargetPart`, `StructuralLoad`, `GetSurfaceVelocityCci` |
| `Flight` | Velocity, direction, center of mass, prograde/normal/radial vectors, `Biome` | Existing frames, `SampleBiomeIdMap` |
| `Body` | `HasAtmosphere`, `SeaLevelPressure`, `SeaLevelDensity`, `ScaleHeight`, `PressureAt`, `DensityAt`, `HasOcean`, `OceanDensity`, `Biomes`, `BiomeAt`, `LatitudeAtPosition`, `LongitudeAtPosition`, `AltitudeAtPosition`, `SurfaceReferenceFrame(lat, lon)`, `IsStar`, `Direction` | `PhysicalAtmosphereReference`, `PhysicsEnvironment`, `BiomesReference`, `Celestial.IsStar` |
| `Orbit` | `Position`, `Velocity`, `Altitude`, `SemiMinorAxis`, `MeanMotion`, `SpecificEnergy`, `EccentricAnomaly`, AN/DN anomalies, `RelativeInclination`, closest approach | `TargetData`; closest approach source *verify* (the HUD `TgtClosest*` rollers) |
| `ReferenceFrame` | `CreateRelative`, `CreateHybrid` | Service-side, as in KSP |
| `Burn` | `TimeTo`, `ReferenceFrame`, `Position` | Existing burn data |
| `Part` | `Velocity`, `Direction`, `CenterOfMass`, a `Parts` filter by name and module | `Part` poses |
| `Decoupler`, `DockingPort` | `Decouple` and `Undock` return the new vehicles | As `Control.ActivateNextSequence` does |

### 2. Propulsion and Fuel

| Class | Members | Game source |
| --- | --- | --- |
| `Gimbal` | `AngleY`, `AngleZ`, range, `CanActuate` | `Gimbal`, `GimbalState`, `GimbalController` |
| `Tank` | `Volume`, `FilledFraction`, contents mix, `PropellantUseEnabled` (rw), `TransferMode` (rw) | `Tank`, `TankTransferMode` |
| `FuelLink` | Parts, flow direction, `Enabled` (rw) | `FuelLink`, `FuelLinkFlow` |
| `Engine` | `Gimbal`, propellants, minimum throttle *verify* | `RocketCore` |

### 3. Power, Lights, Deployables

| Class | Members | Game source |
| --- | --- | --- |
| `Battery` | `Charge`, `Capacity` (J) | `Battery`, `BatteryState` |
| `SolarPanel` | `Power` (W), `SunAngle`, `Occluded` | `SolarPanelState` |
| `Generator`, `PowerConsumer` | Power (W), on/off | `GeneratorState`, `PowerConsumerState` |
| `Vehicle` | Total stored charge, net power | `PowerManager` |
| `Light` | `Active` (rw) | `LightModule`, `PowerConsumer.LightSwitch` |
| `Control` | `Lights` (rw) | `Vehicle.LightsOn`, `ToggleLights` |
| `Deployable` | `State` (Deployed, Retracted, Deploying, Retracting, Broken), `Deploy`, `Retract` | `KeyframeAnimationModule` with `ShowDeployRetract` |
| `MagneticScoop` | `Active` (rw), collection rate | `MagneticScoop` |
| `Flight`, `Orbit` | Radiation dose rate, orbit-average dose | `Radiation.ComputeDoseRate`, `ComputeOrbitAverage` |

`Deployable` covers landing legs and service module doors, which are both animations in KSA.

### 4. Crew and EVA

| Class | Members | Game source |
| --- | --- | --- |
| `Kitten` | `Name`, `Vehicle`, `MissionCount`, `KIA`, mission time, distance traveled | `KittenRosterEntryData` |
| `KSA` | `Kittens`, `GetKitten(name)` | `KittenRosterData` |
| `Vehicle`, `Part` | `Crew`, `CrewCapacity`, seats | `Vehicle.Crew`, `IVASeat` |
| `Seat` | `Kitten`, `AddCrew`, `RemoveCrew` | `Vehicle.SetSeatCrew`, `RemoveCrew` |
| `Kitten` | `OnEVA`, `EVA()`, `Board()`, `LocomotionMode`, `Position`, `Velocity` | `EVADoor.SpawnEva`, `KittenEva` |

Kittens on EVA are not vehicles. `Vehicles` keeps excluding them, and EVA members live on `Kitten`.
EVA spawns likely need the Update-phase deferral that KSP's EVA did.

### 5. Game Level

| Class | Members | Game source |
| --- | --- | --- |
| `Camera` | `Mode` (Orbit, Free, Map, IVA, Fixed), azimuth, elevation, distance, `FieldOfView`, focused vehicle or body | `Camera`, `CameraMode`, `OrbitController`, `Program.SetOrbitCamera` |
| `KSA` | `Screenshot(scale)`, `Message(text, duration)` | `ScreenshotCapture.Request`, `TimedAlert.Create` |
| `Vehicle` | `Destroy()` | `Universe.DestroyVehicle` |
| `Editor` | Load a design, read its mass and delta-v | `VehicleEditor.LoadVehicle` |

### Debug

Typed RPCs mirror KSP's `Debug` service where KSA has the mechanism. `RunCommand` is the fallback
for console commands with no typed RPC.

| Members | Game source |
| --- | --- |
| `SetOrbit(vehicle, body, elements...)`, `SetCircularOrbit(vehicle, body, altitude)` | `Vehicle.Teleport(orbit)`, orbit from elements *verify* |
| `SetLanded(vehicle, body, lat, lon)` | `Vehicle.TeleportToLocation` |
| `SetPosition`, `SetVelocity` (in a frame) | `Orbit.CreateFromStateCci`, `Vehicle.Teleport` |
| `SetRotation`, `SetPitchHeadingRoll`, `SetAngularVelocity` | `Vehicle.Teleport` attitude and rate arguments |
| `AddForce`, `InstantaneousForce` | `Disturbances.AddForceBody`, applied each step *verify* |
| `FillResources`, `EmptyResources` | `Vehicle.RefillConsumables`, `Universe.Empty` |
| `DuplicateVehicle(vehicle, name)`, `ExplodeVehicle(vehicle)` | `Universe.Duplicate`, `Universe.Explode` |
| `VelocityArrows` (rw) | `Universe.DisplayVelocityDebugArrows` |
| `RunCommand(command)`, returning the console output | `Program.TerminalInterface.Execute` and `OnOutput` |

KSP's cheat toggles have no KSA counterpart: infinite propellant and electricity, no crash damage,
unbreakable joints, ignore max temperature, gravity multiplier, part clipping. Neither do the career
members (funds, science, reputation, tech tree, facilities, kerbal experience).

`TestingTools` keeps only test harness members: `RegisterVehicle` and `Quit`. Its save members move
to `KSA` in phase 1, matching `SpaceCenter.Save` and `Load`.

### 6. Drawing

`Drawing`, `UI` and `Debug` are classes in the `KSA` service, holding static methods, for example
`Drawing.AddLine`. Their stubs then cannot collide with KSP's `Drawing`, `UI` and `Debug`
services. Once the KSP and KSA stubs are separated, each class becomes a service of the same name
with the same members, which breaks the least client code.

Lines, spheres, boxes, circles and arcs over `GizmosRenderer`, each in a reference frame. Text and
markers over ImGui draw lists, placed with `Camera.EclToEgo` and `EgoToScreen`. `GizmosRenderer`
is immediate-mode, so the service keeps its own object list and redraws it every frame.

### 7. UI

Windows, text, buttons, input fields, sliders, toggles and dropdowns over ImGui, plus messages. The
kRPC server window in KSA already draws ImGui windows from a mod. The service keeps
a retained widget tree and redraws it every frame, with events for clicks and edits.

## Cross-Cutting Issues

* **Vehicle identity.** A KSA vehicle's id is its name, the only stable identifier. A `Vehicle`
  object throws after docking or undocking, and this stays. Calls that split a vehicle return the
  new vehicles instead (phase 1).
* **Module writes.** Module setters wait up to 10 updates for the change. New writable members
  (lights, deployables, tanks) follow the same pattern.
* **Service names.** `Drawing`, `UI` and `Debug` are static classes in `KSA` until the KSP and KSA
  stubs are separated (phase 6).

## Open Questions

* Where does closest approach come from? The HUD shows it, but the source type is unchecked.
