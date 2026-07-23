# KSPTrajectories service for kRPC

**Status:** proposal — no integration exists yet; no issue filed yet, one should be filed.

## Context

**Today kRPC has no KSPTrajectories integration.** The only connection is *borrowed source*:
`service/SpaceCenter/src/ExtensionMethods/StockAerodynamics.cs` is an MIT-licensed copy of the
mod's stock-aero math (attributed in `LICENSE`), exposed via `CelestialBody.TemperatureAt/DensityAt/
PressureAt` and `Flight.SimulateAerodynamicForceAt`. There is **no runtime dependency on, or RPC
bridge to, the KSPTrajectories mod itself.**

The goal is to let kRPC scripts read and drive KSPTrajectories' atmospheric impact predictions
(impact point/velocity/time, descent profile, target) — invaluable for autopilot and precision-landing
scripts. KSPTrajectories is an *optional* third-party mod, so the integration must degrade gracefully
when it isn't installed.

**Decisions:**
- **Dedicated `Trajectories` service** (mirroring `service/RemoteTech/`), *not* additions to SpaceCenter
  — SpaceCenter must stay free of optional-mod dependencies, and one-service-per-mod is the established
  kRPC convention.
- **Full API surface** — read-only predictions *and* the writable descent-profile / target controls.

## Pattern to replicate

`service/RemoteTech/` is the template. The generic binder `server/src/Utils/APILoader.cs`
(`KRPC.Utils.APILoader.Load`) loads an external assembly by name, version-checks it, finds the API
type by full name, then binds each **delegate-typed property** on a static `API` class to a same-named
**static method** on the external type via `Delegate.CreateDelegate`. Mod-not-installed is a soft
failure (returns `null`, no exception).

**Critical binding nuance:** `APILoader` matches by exact method name (`APILoader.cs:56`). The
KSPTrajectories API exposes several members as C# **properties** (`DescentProfileAngles`,
`ProgradeEntry`, `RetrogradeEntry`, `DescentProfileModes`, `DescentProfileGrades`, `AlwaysUpdate`,
`GetVersion`, `GetVersionMajor/Minor/Patch`) and others as **methods** (`GetImpactPosition()`,
`SetTarget()`, etc.). Property accessors compile to `get_X`/`set_X` methods, which `Type.GetMethods()`
returns — so bind a property by declaring delegate properties named `get_X` / `set_X` (e.g.
`Func<List<double>> get_DescentProfileAngles`, `Action<List<double>> set_DescentProfileAngles`).
Methods bind by their plain name (`Func<Vector3?> GetImpactPosition`).

## External API surface (from `neuoy/KSPTrajectories` `src/Plugin/API.cs`)

Assembly name `Trajectories`, API type `Trajectories.API`. Members to expose:

- **Predictions (methods):** `GetEndTime()→double?`, `GetTimeTillImpact()→double?`,
  `GetImpactPosition()→Vector3?`, `GetImpactVelocity()→Vector3?`, `GetSpaceOrbit()→Orbit`,
  `PlannedDirection()→Vector3?`, `CorrectedDirection()→Vector3?`, `UpdateTrajectory()→void`.
- **Target (methods):** `HasTarget()→bool`, `SetTarget(double lat, double lon, double? alt)→void`,
  `GetTarget()→Vector3d?` (lat/lon/alt), `ClearTarget()→void`.
- **Descent profile (properties):** `DescentProfileAngles` (List<double>, rad, get/set),
  `DescentProfileModes` (List<bool>, get/set), `DescentProfileGrades` (List<bool>, get/set),
  `ProgradeEntry` (bool?, get/set), `RetrogradeEntry` (bool?, get/set),
  `ResetDescentProfile(double AoA)→void` (method), `AlwaysUpdate` (bool, get/set).
- **Version (properties):** `GetVersion` (string), `GetVersionMajor/Minor/Patch` (int).

> The exact assembly version to require, and the precise return frames of `Vector3`/`Vector3d`
> results, must be verified against the installed mod DLL during implementation (see Verification).

## Files to create — `service/Trajectories/`

Mirror `service/RemoteTech/` exactly:

1. **`src/API.cs`** — `static class API` in `namespace KRPC.Trajectories`. `IsAvailable` flag; `Load()`
   calls `APILoader.Load(typeof(API), "Trajectories", "Trajectories.API", new Version(<major>,<minor>))`.
   One delegate property per external member, using the `get_`/`set_` naming rule above for
   property-backed members.
2. **`src/Addon.cs`** — `[KSPAddon(KSPAddon.Startup.Flight, false)]` MonoBehaviour whose `Start()`
   calls `API.Load()`. Copy from `service/RemoteTech/src/Addon.cs`.
3. **`src/Trajectories.cs`** — `[KRPCService(Id = <unused id>, GameScene = GameScene.Flight)]`
   `public static class Trajectories`. Include `[KRPCProperty] public static bool Available =>
   API.IsAvailable;` and a private `CheckAPI()` that throws `InvalidOperationException("Trajectories
   is not available")` when unavailable; call it at the top of every other procedure.
   - **Service Id:** pick an unused numeric id. Used: Drawing=3, InfernalRobotics=4,
     KerbalAlarmClock=5, RemoteTech=6, UI=7, LiDAR=10, DockingCamera=11. Use **8** (verify it's free
     by grepping `KRPCService (Id =` across `service/*/src`).
   - Expose the API as `[KRPCProcedure]`/`[KRPCProperty]` static members. Convert types to kRPC
     conventions:
       - Impact/velocity/direction `Vector3?` → return as kRPC position/velocity tuples in a
         `ReferenceFrame` parameter, converting with the same world↔frame helpers SpaceCenter uses
         (see `CelestialBody.cs` position RPCs and the `ReferenceFrame` transform helpers). A nullable
         result that is null (no atmospheric trajectory / no impact) maps to throwing or to a `HasImpact`
         guard — follow how SpaceCenter handles "no value" cases.
       - `GetTarget()` lat/lon/alt `Vector3d?` → a 3-tuple or dedicated accessors.
       - `GetSpaceOrbit()→Orbit` → wrap in SpaceCenter's existing `Orbit` KRPCClass if cross-service
         reference is acceptable (RemoteTech already depends on `//service/SpaceCenter`); otherwise
         expose raw elements.
       - Descent-profile lists/bools and version ints → direct `[KRPCProperty]` get/set.
4. **`CHANGES.txt`** — new component changelog (leave the entry for the pre-merge changelog commit,
   per repo policy — do **not** add it during regular commits).
5. **`src/KRPC.Trajectories.csproj`** — copy/adapt from RemoteTech (IDE-only; Bazel is canonical).
6. **`BUILD.bazel`** — copy RemoteTech's: `csharp_assembly_info`, `csharp_library` (name
   `KRPC.Trajectories`, `deps = service_deps + ["//service/SpaceCenter:KRPC.SpaceCenter"]` if reusing
   the `Orbit`/frame types), `service_definitions` emitting `KRPC.Trajectories.json`, and a
   `filegroup(name = "Trajectories", ...)` visible to `//:__pkg__`.
7. **`test/`** — `test_trajectories.py` integration tests + `pylint.rc` (+ any `craft/`). Tests should
   tolerate the mod being absent (assert `Available == False` path) since CI likely won't have it.

## Files to modify — top-level `BUILD.bazel`

Register the new service in each place RemoteTech appears (mechanical, follow existing lines):
- Add `"//service/Trajectories",` to the release `srcs` under `# Services`.
- Add `path_map` entries: service dir → `GameData/kRPC/`, and
  `"service/Trajectories/CHANGES.txt": "GameData/kRPC/CHANGES.Trajectories.txt"`.
- Add to the aggregate `test` suite and `lint` suite.
- Add to the services list used for docs/clientgen (~lines 212-219).

Add doc coverage under `doc/` alongside the other service docs if documenting the new RPCs.

## Reuse — do not write new

- `server/src/Utils/APILoader.cs` — the binder; no changes needed.
- `service/RemoteTech/` — copy its `Addon.cs`, `API.cs` shape, `BUILD.bazel`, csproj, test layout.
- `service/build.bzl` `service_deps` — shared dependency list.
- `KRPC.Utils.Equatable<T>` base + `[KRPCClass]`/`[KRPCEnum]` attributes for any returnable objects.
- SpaceCenter `ReferenceFrame` / vector-conversion helpers and the `Orbit` class for type conversion.

## Verification

1. **Discover real assembly details:** disassemble the installed mod to confirm assembly name,
   version, full type name, and exact member signatures (esp. the frame of `Vector3` results):
   `monodis --output=/tmp/traj.il "<KSP>/GameData/Trajectories/Plugin/Trajectories.dll"` then grep the
   `Trajectories.API` class. Adjust `API.cs` delegate signatures and the required `Version` to match.
2. **Build:** `bazel build //service/Trajectories:KRPC.Trajectories` and `bazel build //:krpc`
   (full release archive) must succeed.
3. **Service definition / clientgen:** confirm `KRPC.Trajectories.json` is produced and clients
   generate stubs without error.
4. **Lint/tests:** `bazel test //service/Trajectories:test` (or the aggregate suites).
5. **Mod-absent path:** with KSPTrajectories *not* installed, connect a client and check
   `conn.trajectories.available == False` and that other calls raise the "not available" error — no
   crash, matching RemoteTech behavior.
6. **Mod-present path (manual, in-game):** install KSPTrajectories, enter flight on an atmospheric
   descent, set a target, and verify `get_impact_position`, `time_till_impact`, descent-profile
   get/set, and `set_target/clear_target` round-trip against the in-game Trajectories UI.

## References

- KSPTrajectories repo: <https://github.com/neuoy/KSPTrajectories>
- Public API source: <https://github.com/neuoy/KSPTrajectories/blob/master/src/Plugin/API.cs>
- kOS Trajectories addon (prior-art binding): <https://ksp-kos.github.io/KOS/addons/Trajectories.html>
