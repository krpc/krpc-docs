# A public `Debug` service

**Status:** in progress — meta issue
[#955](https://github.com/krpc/krpc/issues/955), children
[#145](https://github.com/krpc/krpc/issues/145),
[#466](https://github.com/krpc/krpc/issues/466),
[#799](https://github.com/krpc/krpc/issues/799),
[#826](https://github.com/krpc/krpc/issues/826).

## Context

kRPC ships no supported way to modify simulation state: teleport a vessel, set its attitude, refuel
it, or flip one of KSP's cheat toggles. The functionality already exists in `tools/TestingTools`, an
add-on built only for the in-game test suite and deliberately left out of the mod release, so players
cannot reach it. #799 is a user asking how to move a vessel and being told it is not possible; #826 is
a user who gave up and wrote their own teleport RPCs.

This promotes the player-useful half of `TestingTools` into a new shipping service, `Debug`, reworked
into an idiomatic public API, and adds KSP's `CheatOptions` toggles (#466). `TestingTools` keeps only
test-harness plumbing, and the test framework drives the new public service rather than private
copies, so every in-game test run exercises the shipped API.

**Decisions:**

- **Name `Debug`** (`conn.debug`), a separate assembly `KRPC.Debug.dll`, not additions to SpaceCenter.
  A separate service keeps the "this is cheating" boundary visible in client code.
- **Move, don't duplicate.** Anything promoted is deleted from `TestingTools`, which gains a
  dependency on `KRPC.Debug`.
- **Rework the signatures.** The test-shaped API (body names as strings, degrees where kRPC uses
  radians) is not what should become public.
- **Physics range (#145's second half) is out of scope** — already shipped as
  `Vessel.PhysicsRange`, see [vessel-physics-range.md](vessel-physics-range.md).
- **No opt-in gate.** #466 suggests the cheats only work when explicitly enabled on the KSP side,
  to put them on a par with the Alt+F12 menu. Rejected: a script has to name the service to reach
  it, so it cannot be triggered by accident the way a stray keypress can, and a setting that makes
  documented RPCs fail is a worse experience than simply not calling them.

## Public API

Service `Debug`, namespace `KRPC.Debug`, class `Debug`. Teleport, attitude and resource members are
`GameScene = GameScene.Flight`; the cheat toggles are available in every scene.

The attitude, rotation and resource RPCs take a trailing optional `Vessel vessel = null` defaulting
to the active vessel, so the common case is a one-liner. The teleports have no such parameter: they
go through the game's own API, which only moves the active vessel (see [Teleporting](#teleporting)).
Units follow kRPC conventions rather than KSP's: radians
for orbital elements (matching `SpaceCenter.Orbit`), degrees for latitude/longitude and
pitch/heading/roll (matching `SpaceCenter.Flight`), rad/s for angular velocity (matching
`Vessel.AngularVelocity`).

### Teleport

| RPC | Change from `TestingTools` |
| --- | --- |
| `SetOrbit(CelestialBody body, double semiMajorAxis, double eccentricity, double inclination, double longitudeOfAscendingNode, double argumentOfPeriapsis, double meanAnomalyAtEpoch, double epoch)` | `CelestialBody` not a name; inclination/LAN/argument of periapsis in radians, converted to KSP degrees internally (the test version passed them through as degrees) |
| `SetCircularOrbit(CelestialBody body, double altitude)` | `CelestialBody` not a name |
| `SetLanded(CelestialBody body, double latitude, double longitude, double altitude = 0)` | `CelestialBody` not a name |
| `SetFlight(CelestialBody body, double latitude, double longitude, double altitude, double speed, double heading, double pitch = 0, double roll = 0, double angleOfAttack = 0)` | `CelestialBody` not a name |
| `SetPosition(Tuple<double,double,double> position, ReferenceFrame referenceFrame = null)` | new; the inverse of `Vessel.Position`. A position in another vessel's frame gives a rendezvous |
| `SetVelocity(Tuple<double,double,double> velocity, ReferenceFrame referenceFrame = null)` | new; the inverse of `Vessel.Velocity`, covering the velocity half of #145. Defaults to the orbited body's rotating frame, so a zero velocity is at rest relative to the ground |

### Attitude and rotation

| RPC | Change from `TestingTools` |
| --- | --- |
| `SetPitchHeadingRoll(double pitch, double heading, double roll, ReferenceFrame referenceFrame = null, Vessel vessel = null)` | unchanged |
| `SetDirection(Tuple<double,double,double> direction, double roll, ReferenceFrame referenceFrame = null, Vessel vessel = null)` | renamed from `SetDirectionAndRoll`; NaN roll leaves roll uncontrolled, as `AutoPilot.TargetRoll` does |
| `ApplyRotation(double angle, Tuple<double,double,double> axis, Vessel vessel = null)` | `float` angle → `double` |
| `SetAngularVelocity(Tuple<double,double,double> angularVelocity, ReferenceFrame referenceFrame = null, Vessel vessel = null)` | renamed from `ApplyAngularVelocity`; zero stops the vessel rotating |

### Resources

`FillAllResources(Vessel vessel = null)`, `FillResources(string resourceName, Vessel vessel = null)`.

### Cheat options

`bool` properties over every meaningful field of KSP's `CheatOptions`: `InfinitePropellant`,
`InfiniteElectricity`, `NoCrashDamage`, `UnbreakableJoints`, `IgnoreMaxTemperature`,
`AllowPartClipping`, `NonStrictAttachmentOrientation`, `IgnoreKerbalInventoryLimits`,
`IgnoreEVAConstructionMassLimit`, `IgnoreAgencyMindsetOnContracts`, `PauseOnVesselUnpack`,
`BiomesVisible`. `MiddleMouseClickSetPosition` is left out: it binds a mouse gesture, so it means
nothing to a script.

`GravityMultiplier` is the Alt+F12 hack-gravity slider, `PhysicsGlobals.GraviticForceMultiplier`.
It is not part of `CheatOptions`.

### Career

The Alt+F12 career tab, which has no kRPC equivalent — `SpaceCenter.Funds`, `Science` and
`Reputation` are read-only. Each maps onto the game's own implementation of the corresponding
button, so behavior matches the debug menu exactly.

| Member | KSP |
| --- | --- |
| `double Funds { get; set; }` | `Funding.Instance.SetFunds` |
| `float Science { get; set; }` | `ResearchAndDevelopment.Instance.SetScience` |
| `float Reputation { get; set; }` | `Reputation.Instance.SetReputation` |
| `void UnlockTechnologyTree()` | `ResearchAndDevelopment.Instance.CheatTechnology()` |
| `void UpgradeFacilities()` | `ScenarioUpgradeableFacilities.Instance.CheatFacilities()` |
| `void MaxKerbalExperience()` | `KerbalRoster.CheatExperience()` |

Each throws when the game mode has no such concept, matching how `SpaceCenter.Funds` already
behaves in sandbox. The debug menu's "max progress" button (`ProgressTracking.CheatProgression`)
is left out — it rewrites the first-flight milestone records, which nothing in kRPC reads.

## Staying in `TestingTools`

`CurrentSave`, `LoadSave`, `Quit`, `PartAvailable`, `PartModuleAvailable`, `LoadedPartCount`,
`FlightStateVesselCount`, `RecoveryDialogCount`, `FlightInputStageLock`, `RemoveOtherVessels`,
`SetCrewToPilot`, `ClearRotation`.

`RemoveOtherVessels` is destructive and irreversible with no undo, and `ClearRotation` orients a
vessel to an arbitrary test-fixture pose. Neither is a sensible public API. `ClearRotation` keeps its
own attitude reset and calls the public `Debug.SetAngularVelocity` for the spin-damping half.

Destroying a single named vessel is proposed separately, as `SpaceCenter.Vessel.Terminate` rather
than a Debug member, in [terminate-vessel.md](terminate-vessel.md): terminating is a stock action and
not cheating.

## Teleporting

The teleports go through the game's own `FlightGlobals.SetShipOrbit`, which is what the Alt+F12
menu uses. It wraps writing the orbit in a prepare/restore sequence that a mod cannot reproduce from
public API alone: taking every vessel off physics, clearing the landed and ground-contact state,
moving the floating origin to the new position, suppressing the collision and g-force checks for a
few frames, and firing the sphere-of-influence change event.

Consequences of using it:

- **Active vessel only.** `SetShipOrbit` acts on `FlightGlobals.ActiveVessel`, so the teleports take
  no `vessel` parameter. The attitude, rotation and resource RPCs still do.
- **The epoch is always "now".** `SetShipOrbit` ignores the epoch it is passed, so `SetOrbit`
  propagates the mean anomaly forward itself, `M + n·Δt` with `n = sqrt(mu / a³)`.
- **State vectors go in as elements.** `SetFlight`, `SetPosition` and `SetVelocity` build a
  throwaway `Orbit` with `Orbit.UpdateFromStateVectors` and read the elements back off it.
- **Launch clamps are removed first.** The game's prepare step does not, so a clamped craft is
  otherwise dragged back to the pad.

**Nearby vessels are loaded after a teleport.** `PostOrbitSet` moves the floating origin and calls
`OrbitPhysicsManager.CheckReferenceFrame`, so the game re-evaluates what is in range of the new
position. A vessel the teleported craft lands next to is now loaded, where the previous
implementation left it unloaded. This is the more correct state — a vessel 100 m away belongs in
physics — but it is a visible difference: `test_comms.py` asserted on a comm node name, which the
game formats differently for a loaded and an unloaded vessel, and had to stop pinning the load
state.

`SetLanded` keeps kRPC's own placement code (`Landing.cs`): it measures the vessel's ground clearance
from its colliders and puts its lowest point on the PQS terrain height. The game's own
`SetVesselPosition(..., easeToSurface: true)` was tried instead and rejected — it holds the vessel in
an "easing" state with a raised gravity multiplier until it touches down, and a vessel that never
touches down stays in that state permanently, overriding every later teleport.

## Licensing

Earlier versions of the orbit code were adapted from HyperEdit. It has been replaced by the game's
own API, so kRPC owns all of this code and there is no third-party attribution.

`KRPC.Debug.dll` still ships GPLv3, because it links against `KRPC.SpaceCenter.dll`, which is GPLv3 —
its RPCs take `Vessel`, `CelestialBody` and `ReferenceFrame`. So the arrangement is the same as
`KRPC.SpaceCenter`: a `service/Debug/LICENSE`, a `LICENSE.KRPC.Debug` entry in the release zip, and a
line in the root `BUILD.bazel` GPL exception list. Dropping to LGPL would mean severing the
SpaceCenter dependency, which would undo the idiomatic API.

## Commits

1. **Add a Debug service for modifying the state of the simulation** — the assembly, its build
   wiring (`BUILD.bazel`, `KRPC.sln`, release zip, `csproj-test`), the slimming of `TestingTools`,
   and pointing `tools/krpctest/krpctest/testcase.py` and the SpaceCenter tests at `conn.debug`. The
   `testcase.py` wrappers keep their existing Python signatures (body names, degrees) and convert,
   so the ~20 existing call sites are untouched.
2. **Generate client stubs for the Debug service** — `clientgen` rules for the Python, C++, C#, Java
   and C-nano clients. Lua builds services dynamically and needs nothing.
3. **Document the Debug service** — `doc/api/debug*.tmpl`, per-language toctrees, `doc/order.txt`,
   changelog wiring.
4. **Add in-game tests for the Debug service** — `service/Debug/test/test_debug.py`.

The changelog entry sits in commit 1 rather than a separate final commit: the file is created by
this branch, so only one commit touches it.
