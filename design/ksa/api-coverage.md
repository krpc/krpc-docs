# KSA API coverage

**Status:** in progress. Part of [kRPC for KSA](README.md). The service merged in PR #1190. The
manual control inputs and phases 1 to 7 are built and tested in game, not yet in a PR. Audited against KSA
build 2026.10.19.5638.

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
| Vessels, active vessel | Yes | `Vehicle`, `Universe` | `Vehicle`, `ActiveVehicle`, `Vehicles` | Done |
| Bodies | Yes | `Celestial`, `PhysicalAtmosphereReference`, `BiomesReference` | Mass, gravity, rotation, SOI, terrain, atmosphere, ocean, position queries | Done, not yet in a PR |
| Atmosphere queries | Yes, no temperature | `PhysicalAtmosphereReference`, `PhysicsEnvironment` | Pressure and density at the vehicle and at any altitude | Done, not yet in a PR |
| Biomes | Yes | `Celestial.SampleBiomeIdMap`, `BiomesReference` | `Body.Biomes`, `BiomeAt`, `Flight.Biome` | Done, not yet in a PR |
| Orbits, patches | Yes | `Orbit`, `PatchedConic`, `TargetData` | Elements, anomalies, nodes, `PositionAt`, `NextOrbit` | Done, not yet in a PR |
| Targets, closest approach | Yes | `Vehicle.SetTarget(orbiter, part)`, `PatchedConic.TryFindClosestApproach` | Target vehicle, body and part, closest approach | Done, not yet in a PR |
| Reference frames | Yes | Ecl frame chain | Vehicle, body, burn, relative and hybrid frames, `Transform*` | Done, not yet in a PR |
| Maneuver nodes | Yes | Flight computer burns | `Burn`, `AddBurn`, `AutoBurn` | Done, not yet in a PR |
| Structural load, debris | Yes | `StructuralLoad`, `Vehicle.IsDebris` | Peak and max g-load and dynamic pressure, `IsDebris`, `OnRails` | Done, not yet in a PR |
| Saves | Yes | `GameSaves` | `Save`, `Load`, `SaveExists` | Done, not yet in a PR |
| Stages, delta-v | Yes | `Sequence`, `SequencePerformance` | `Sequence` | Done |
| Parts tree | Yes | `PartTree`, `Part` | `Part`, part lists by name and module | Done, not yet in a PR |
| Engines, gimbal | Yes | `RocketCore`, `Gimbal`, `GimbalState` | `Engine`, `Gimbal` | Done, not yet in a PR |
| Tanks, crossfeed, transfer | Yes | `Tank`, `FuelLink`, `TankTransferMode` | `Resource`, `Tank` (with the rated pressure for gas), `FuelLink` | Done, not yet in a PR |
| RCS | Yes | `ThrusterController` | `RCS.Active` | Done |
| Decouplers, docking ports | Yes | `Decoupler`, `DockingPort` | Both, separation returns the new vehicles | Done, not yet in a PR |
| Parachutes | Yes | `Parachute` | `Parachute` | Done |
| Power | Yes | `Battery`, `SolarPanel`, `Generator`, `PowerConsumer` | All four, vehicle totals | Done, not yet in a PR |
| Lights | Yes | `PowerConsumer.LightSwitch`, `Vehicle.LightsOn` | `Control.Lights`, `Light.Active` | Done, not yet in a PR |
| Legs, bays, deployables | Partial | `KeyframeAnimationModule` (`DeploymentState`) | `Deployable` | Done, not yet in a PR |
| Radiation | Yes, KSA only | `Radiation.ComputeDoseRates`, `TryComputeOrbitDoseRates`, `ParticleEvents` | `Flight` and `Burn` dose rates, with particle events as the HUD gauges | Done, not yet in a PR |
| Radiation shielding | Yes, KSA only | `RadiationShield`, tank cover | None. `Kitten.DoseRate` gives the dose behind the shield | Not started |
| Space weather | Yes, KSA only | `ActivityCycle`, `ParticleEvents`, `StormState`, `SpaceWeather` | None. Deferred: the model changed across many revisions in v2026.10.25.5707, and parts are unused in game | Not started |
| Crew | Yes | `KittenRosterData`, `KittenRosterEntryData`, `IVASeat` | `Kitten` (with radiation doses, sickness and retirement), `Seat`, vehicle and part crew | Done, not yet in a PR |
| EVA | Yes | `EVADoor`, `KittenEva` | `GoOnEva`, `Board`, `ActiveKitten`. Kittens on EVA are not vehicles | Done, not yet in a PR |
| Camera | Yes | `Camera`, `CameraMode`, `OrbitController`, `MapController` | Mode, view angles and distance, field of view, focus | Done, not yet in a PR |
| Screenshots, messages | Yes | `ScreenshotCapture`, `TimedAlert` | `Screenshot`, `Message` | Done, not yet in a PR |
| Debug cheats | Partial | `TeleportInputData`, `TeleportToLocation`, the vehicle input events, console commands | `Debug`, `Vehicle.Destroy`, `Recover` | Done, not yet in a PR |
| Editor | Yes | `VehicleSave`, `PartTree.PerformanceSequences` | `VehicleDesigns`, with mass and delta-v | Done, not yet in a PR |
| Drawing | Yes | `GizmosRenderer`, ImGui draw lists | Lines, polylines, circles, arcs, boxes, spheres and text | Done, not yet in a PR |
| UI | Yes | ImGui windows (as in the server window) | Windows of labels, buttons, input fields, sliders, toggles and dropdowns | Done, not yet in a PR |
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

Built and tested in game, not yet in a PR. The table is the plan. The built API and where it
differs follow it.

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

Built differently, or dropped:

| Class | Change | Why |
| --- | --- | --- |
| `KSA` | `ClearTarget` dropped | Setting a target property to `null` clears it |
| `KSA` | Last physics step dropped | `UT` covers it, and no use was found |
| `Vehicle` | `OnRails` added | The structural load is zero on rails, in the four odd `Situation` values |
| `Vehicle` | Surface velocity dropped | `Velocity(body.ReferenceFrame)` |
| `Vehicle` | `PartsWithName`, `Engines`, `RCS`, `Decouplers`, `Parachutes`, `DockingPorts` | The parts filter, by module type rather than module name |
| `Flight` | `Prograde`, `Normal`, `Radial` take a frame, relative to the surface velocity | `Flight` has no frame of its own |
| `Flight` | Velocity, direction and center of mass dropped | `Vehicle.Velocity`, `Direction`, `Position` |
| `Flight`, `Body` | The biome is the one with the highest weight | Up to four biomes blend at each point |
| `Body` | Sea-level values come from the model at altitude 0 | The data gives them in mixed units |
| `Body` | `SurfaceReferenceFrame(lat, lon)` and `Direction` dropped | `CreateRelative` covers the first, the second has no clear meaning |
| `Orbit` | `Position`, `Velocity`, `Altitude` dropped | `PositionAt`, `VelocityAt`, `RadiusAt` |
| `Orbit` | `TimeOfClosestApproach`, `DistanceAtClosestApproach` | To the vehicle's target, from the encounters the game finds while predicting the trajectory |
| `ReferenceFrame` | No `Remove` | Equal frames share an id, and a frame is freed with what it is built on |
| `Part` | `Direction` and `CenterOfMass` dropped | A part has no forward axis, and `Rotation` gives its axes |

### 2. Propulsion and Fuel

Built and tested in game, not yet in a PR. The table is the plan.

| Class | Members | Game source |
| --- | --- | --- |
| `Gimbal` | `AngleY`, `AngleZ`, range, `CanActuate` | `Gimbal`, `GimbalState`, `GimbalController` |
| `Tank` | `Volume`, `FilledFraction`, contents mix, `PropellantUseEnabled` (rw), `TransferMode` (rw) | `Tank`, `TankTransferMode` |
| `FuelLink` | Parts, flow direction, `Enabled` (rw) | `FuelLink`, `FuelLinkFlow` |
| `Engine` | `Gimbal`, propellants, minimum throttle *verify* | `RocketCore` |

Built differently:

| Class | Change | Why |
| --- | --- | --- |
| `Part` | `Gimbals`, a list, in place of `Engine.Gimbal` | An engine part has a gimbal per nozzle, such as a 5 degree main nozzle and 70 degree turbopump nozzles |
| `Gimbal` | `Active` in place of `CanActuate` | `CanActuate` only says a max angle is nonzero. `Active` is whether an engine it steers is active |
| `Gimbal` | Angles in degrees | The game stores radians, its data gives degrees |
| `Tank` | Contents dropped | `Part.Resources` |
| `Engine` | `MinimumThrottle` from `EngineController` | Verified to exist |
| `Vehicle` | `Tanks`, `FuelLinks` | As the phase 1 module lists |
| `TestingTools` | `AddFuelLink` | No stock vehicle has a fuel link |

Disabling propellant use on every tank stops the engines. Whether they restart once it is enabled
again varies between runs, so the tests do not check it.

### 3. Power, Lights, Deployables

Built and tested in game, not yet in a PR. The table is the plan.

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

Built differently:

| Class | Change | Why |
| --- | --- | --- |
| `Light` | `Active` is read-only | The game switches a vehicle's lights together, through `Control.Lights`. Cabin lights are always on |
| `Vehicle` | `StoredEnergy`, `EnergyCapacity`, `NetPower`, summed over the modules | No `PowerManager` total covers all three |
| `Vehicle` | Module lists for each class | As the phase 1 module lists |
| `SolarPanel` | `Active` added, sun efficiency and distance left out | `Power` gives the output |
| `Deployable` | `Deploy` and `Retract` return once the part moves | As KSP's solar panels do. A full deploy takes about 10 s |
| `Flight` | Both dose rates, none on `Orbit` | The orbit average uses the vehicle's position for the star dose. NaN with no magnetosphere or a periapsis below the surface |

No stock part has a `Generator`, so its tests cover only empty lists. The stock vehicles have no
solar panels or scoops, and the tests launch one-part test vehicles. The default vehicles Banjo,
Hunter and Polaris are kittens with a backpack, which `LaunchVehicle` rejects.

### 4. Crew and EVA

Built and tested in game, not yet in a PR. The table is the plan.

| Class | Members | Game source |
| --- | --- | --- |
| `Kitten` | `Name`, `Vehicle`, `MissionCount`, `KIA`, mission time, distance traveled | `KittenRosterEntryData` |
| `KSA` | `Kittens`, `GetKitten(name)` | `KittenRosterData` |
| `Vehicle`, `Part` | `Crew`, `CrewCapacity`, seats | `Vehicle.Crew`, `IVASeat` |
| `Seat` | `Kitten`, `AddCrew`, `RemoveCrew` | `Vehicle.SetSeatCrew`, `RemoveCrew` |
| `Kitten` | `OnEVA`, `EVA()`, `Board()`, `LocomotionMode`, `Position`, `Velocity` | `EVADoor.SpawnEva`, `KittenEva` |

Kittens on EVA are not vehicles. `Vehicles` keeps excluding them, and EVA members live on `Kitten`.

Built differently:

| Class | Change | Why |
| --- | --- | --- |
| `Kitten` | Keyed by name, `Character` left out | The roster's only identifier. The object survives EVA, boarding and a save load |
| `Kitten` | `FastestSpeed` added, `Vehicle` found from the seats | The roster's vehicle id is `EVA` on EVA and stale after a rename |
| `Seat` | `Kitten` (rw) replaces `AddCrew` and `RemoveCrew` | One setter, as the game's crew assignment window. `null` empties the seat |
| `Kitten` | `GoOnEva()` for `EVA()`, `Board()` returns the vehicle | A method is a verb. `Board` boards the nearest free hatch within 1 m, as the board key does |
| `KSA` | `ActiveKitten` (rw) added, `ActiveVehicle` is `null` while a kitten has control | Going on EVA hands control to the kitten |
| `KSA` | `LaunchVehicle` rejects the three default kittens | The placement code divides by zero for them |

EVA and boarding go through the game's `EvaSpawnBuffer` and `KittenBoardBuffer`, which apply at the
start of the next frame. Neither needs a deferral of its own. A kitten fresh out of the hatch is
over 1 m from it, and comes in range once it grabs the hatch rail, after a fraction of a second of
simulation.

The start save has Hunter, Banjo and Polaris on EVA near Gemini7, and one kitten in each of Gemini7
and Rocket. The roster names the others at random on each new game, so the tests find crew through
the vehicles.

### 5. Game Level

Built and tested in game, not yet in a PR. The tables are the plan.

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

Built differently:

| Class | Change | Why |
| --- | --- | --- |
| `Camera` | `Azimuth` and `Elevation` in degrees, `Distance` in meters | The game stores radians, and the orbit distance as a multiple of the focused object's radius |
| `Camera` | `FocusedVehicle`, `FocusedBody`, `FocusedKitten` (rw) | One property per type, as KSP's camera. Setting one leaves the active vehicle |
| `KSA` | `Screenshot(scale, ui)` returns the file path | The game names the file by the time. It reduces the scale to fit graphics memory |
| `KSA` | `Message(text, duration, warning)` | The game's two alert tones. It shows an alert for at least 2 s |
| `Vehicle` | `Recover()` and `CanRecover` added | The game's recover button, at rest on the home planet |
| `VehicleDesign` | Replaces `Editor`: `KSA.VehicleDesigns`, with `PartCount`, `Mass`, `DryMass`, `DeltaV` | The editor's figures come from the design's part tree, loaded and freed without opening the editor |
| `Debug` | The vehicle is the first parameter of each method | `ActiveVehicle` is `null` while a kitten has control |
| `Debug` | `SetRotation` replaces `SetPitchHeadingRoll`, `SetLanded` has no altitude | Quaternions as `Vehicle.Rotation`. The game places a landed vehicle on the terrain |
| `Debug` | `ShowVelocityArrows(visible)` replaces `VelocityArrows` | A service class holds static methods, not static properties |
| `Debug` | `AddForce`, `InstantaneousForce` not built | `Disturbances.AddForceBody` was not verified |
| `Debug` | `RunCommand` checks the command name | The console logs an unknown command, and most commands write to the log, not the console output |

Teleports go through the game's `TeleportInputBuffer`. A vehicle's cached position and velocity
refresh at the start of the frame after the teleport applies, so each `Debug` teleport waits one
extra update. A pause set through `SimulationSpeed` also takes effect a frame late. The start save
has no landed vehicle, so the recover test launches one.

`TestingTools` keeps only test harness members: `RegisterVehicle` and `Quit`. Its save members move
to `KSA` in phase 1, matching `SpaceCenter.Save` and `Load`.

### 6. Drawing

Built and tested in game, not yet in a PR. The two paragraphs are the plan.

`Drawing`, `UI` and `Debug` are classes in the `KSA` service, holding static methods, for example
`Drawing.AddLine`. Their stubs then cannot collide with KSP's `Drawing`, `UI` and `Debug`
services. Once the KSP and KSA stubs are separated, each class becomes a service of the same name
with the same members, which breaks the least client code.

Lines, spheres, boxes, circles and arcs over `GizmosRenderer`, each in a reference frame. Text and
markers over ImGui draw lists, placed with `Camera.EclToEgo` and `EgoToScreen`. `GizmosRenderer`
is immediate-mode, so the service keeps its own object list and redraws it every frame.

Built:

| Members | Game source |
| --- | --- |
| `Drawing.AddLine`, `AddDirection`, `AddPolyline(vertices, frame, closed)` | `GizmosRenderer.DrawLine` |
| `Drawing.AddCircle`, `AddArc` | `DrawLine`, 64 segments per turn |
| `Drawing.AddBox(center, size, rotation)` | `GizmosRenderer.DrawWireBox` |
| `Drawing.AddSphere(center, radius)`, solid | `GizmosRenderer.DrawSphere` |
| `Drawing.AddText(text, position, frame, size)`, centered on the position | The background ImGui draw list, at `EgoToScreen` |
| `Drawing.Clear(clientOnly)`; on each object `ReferenceFrame`, `Visible`, `Color`, `Remove()` | Service object list |

Built differently, or dropped:

| Member | Change | Why |
| --- | --- | --- |
| `Thickness` | Dropped. Lines are 1 pixel wide | `GizmosRenderer` draws a line list with no width. On a 4K window the lines are thin and pale (see below) |
| `Material` | Dropped | The gizmo pipeline has one shader |
| `Color` | `StdLib.ColorRGB`, opaque | As KSP's `Drawing` in 0.7.0. The gizmo shader's alpha blending was not verified |
| `Polygon` | `Polyline.Closed` | One class for open and closed lines |
| `Point`, `NavballMarker`, `MapMarker`, `OrbitPath`, `Image` | Not built | A sphere covers a point. KSA's navball and map have no marker API. Orbit paths and images are left for later |
| `Text` | Screen-space overlay, a font size in pixels, no rotation | ImGui text faces the screen. It is hidden with the game's UI, as the game's own labels are |
| Circles and arcs | Own segments | `GizmosRenderer.DrawArc` uses 12 segments per turn, visibly polygonal |

**Line thickness.** The game's lines are 1 pixel wide and blended. On a 3840 pixel wide window a
magenta line shows as a faint pink thread, hard to see against the planet. The game has no width
setting, and a thin `DrawWireBox` per segment still draws 1 pixel edges. The options:

* Several parallel lines, offset by a pixel in screen space each frame.
* A chain of solid `DrawSphere` beads along each segment, a width in meters.
* ImGui overlay segments with `AddLine(thickness)`, a width in pixels. These are hidden with the UI
  and drawn over the scene with no depth test.

Not done. Revisit if users find the lines too thin.

Mechanics:

* A Harmony prefix on `Program.OnPreRender` draws the gizmos. The game resets them at the start of
  `OnFrame` and renders them after `OnPreRender`, the slot the editor's own gizmos use. Gizmo
  positions are relative to the camera, `Camera.EclToEgo`.
* Text is drawn from the StarMap before-GUI hook, which runs only while the UI is shown.
* Each object records its client. A disconnect removes the client's objects, and a removal sweeps the
  object store, so a later call through a removed object raises `ObjectDestroyedException`.
* An object in a frame that cannot be placed, such as a destroyed vehicle's, is skipped that frame.
* The stubs need the StdLib definitions for the colors. The stub build generates them from
  `KRPC.Core.dll` and passes the StdLib header paths to the C++ and C nano generators.
* Over gRPC a color is the `krpc.stdlib.ColorRGB` message (see [grpc.md](grpc.md)).
* The tests draw in magenta around the focused vehicle and count magenta pixels in a screenshot.

### 7. UI

Built and tested in game, not yet in a PR. The first paragraph is the plan.

Windows, text, buttons, input fields, sliders, toggles and dropdowns over ImGui, plus messages. The
kRPC server window in KSA already draws ImGui windows from a mod. The service keeps
a retained widget tree and redraws it every frame, with events for clicks and edits.

Built:

| Members | Game source |
| --- | --- |
| `UI.AddWindow(title)`, `UI.Clear(clientOnly)` | Service window list |
| `Window`: `Title`, `Position`, `Size`, in pixels | `ImGui.Begin`, `SetNextWindowPos`, `SetNextWindowSize` |
| `Window` and `Row`: `AddLabel`, `AddButton`, `AddInputField`, `AddSlider`, `AddToggle`, `AddDropdown`, `AddSeparator`, `AddRow` | Service widget tree |
| `Label.Content`, `Button.Content` and `Clicked` | `ImGui.Text`, `Button` |
| `InputField`, `Slider` and `Dropdown`: `Label`, the value, `Changed`. `Slider.Minimum` and `Maximum`, `Dropdown.Options` | `InputText`, `SliderFloat`, `BeginCombo` |
| `Toggle.Content`, `State` and `Changed` | `Checkbox` |
| On each widget and window: `Visible`, `Enabled`, `Remove()` | `BeginDisabled` |

Built differently, or dropped:

| Member | Change | Why |
| --- | --- | --- |
| `Canvas`, `Panel`, `RectTransform`, `Layout` | `Window` and `Row` | ImGui lays out its items. A window stacks its widgets, and a row lines them up |
| `Text` | `Label` | `Text` is the drawing class |
| `Message` | `KSA.Message` (phase 5) | Already built |
| `ScrollView`, `Image`, `ToggleGroup`, styles, fonts, colors | Not built | Left for later |

Mechanics:

* The windows are drawn from the StarMap before-GUI hook, so they are hidden with the game's UI.
* A window auto-fits its widgets until a client sets `Size`. New windows cascade from the top left
  corner. ImGui saves no settings for them.
* Each window records its client, as the drawing objects do, and a disconnect removes the client's
  windows. Removing a window or a row removes the widgets in it, and sweeps the object store.
* `Clicked` and `Changed` latch until the client clears them, as in KSP's `UI`. A client write to a
  value leaves `Changed` unchanged.
* The tests click the widgets through ImGui's input queue (`AddMousePosEvent`,
  `AddMouseButtonEvent`, `AddInputCharactersUTF8`), from `TestingTools`. Each widget records its
  screen rectangle for this, and an open dropdown records its options.

## Cross-Cutting Issues

* **Object lifetime.** Every service class reports the state of its game object, and the server
  sweeps the object store when the vehicles or their parts change. A call through a gone object
  raises `KRPC.ObjectDestroyedException`, as in KSP. Built, not yet in a PR.
* **Vehicle identity.** A KSA vehicle's id is its name, the only stable identifier. A `Vehicle`
  object throws after docking or undocking, and this stays. Calls that split a vehicle return the
  new vehicles instead (phase 1).
* **Module writes.** Module setters wait up to 10 updates for the change. New writable members
  (lights, deployables, tanks) follow the same pattern.
* **Service names.** `Drawing`, `UI` and `Debug` are static classes in `KSA` until the KSP and KSA
  stubs are separated (phase 6).
