# Kitten Engineer Redux service

**Status:** in progress. Built and tested locally on a branch off `ksa-v2026.11.10`, no PR yet.

The KSA equivalent of the KSP [Kerbal Engineer Redux service](../services/kerbal-engineer-redux.md).
It also exercises the best-effort binding of mod members from
[partial loading](../server/partial-loading.md) in a real integration, ahead of `core`.

## Context

[Kitten Engineer Redux](https://github.com/BarneyCompiler/Kitten-Engineer-Redux) (KER, 0.5.9,
assembly `KittenEngineerRedux`, MIT) draws a flight HUD and an editor panel. It has no public API.
Its calculations are `internal` static classes in `KittenEngineerRedux.Analysis`:

| Class | Computes | Overlap with the `KSA` service |
| --- | --- | --- |
| `SequenceAnalyzer.AnalyzeNative` | The game's stage performance, plus reachable fuel, TWR, max TWR, part and engine counts, feed warnings | `Sequence` has delta-v, thrust, Isp, burn time and masses |
| `SequenceAnalyzer.Analyze` | KER's own stage estimate at an ambient pressure | None |
| `SuicideBurnCalculator` | Burn altitude, time to burn, duration | None |
| `OrbitSummaryCalculator` | Orbit elements, times to equatorial AN/DN, surface velocities | `Orbit` and `Flight`, except the times to AN/DN |
| `OrbitPlanner` | Hohmann estimate to a circular altitude | A formula over `Orbit` |
| `ActiveEngineThrust` | Actual and maximum thrust | `Vehicle.Thrust`, `AvailableThrust` |
| `TelemetryHistory`, `HudAlerts` | UI state | Not analysis |

## Decisions

* **Wrap the stages and the suicide burn.** The rest is in the `KSA` service or a formula over it.
* **Service `KittenEngineerRedux`**, its own assembly `KRPC.KSA.KittenEngineerRedux` in the kRPC mod
  folder, which the server loads as it loads every `KRPC.KSA.*.dll`. Stubs for each client ship
  beside the `KSA` stubs.
* **Snapshot structs**, as on KSP: `Stage` and `SuicideBurn`.
  ```csharp
  [KRPCProperty] public static bool Available
  [KRPCProcedure (Nullable = true)] public static SuicideBurn? SuicideBurn (Vehicle vehicle)
  [KRPCProcedure] public static IList<Stage> Stages (Vehicle vehicle)
  [KRPCProcedure] public static IList<Stage> EstimateStages (Vehicle vehicle, double altitude)
  [KRPCProcedure] public static IList<Stage> DesignStages (VehicleDesign design, Body body, double altitude = 0)
  ```
* **Any vehicle.** KER's calculations take a vehicle, unlike KSP KER's processors.
* **`Stages` reads the game's simulation**, KER's default mode. The service recomputes the
  performance first, as `Sequence` does, since the game recomputes it in flight only while its
  windows are open. TWR uses the gravity at the vehicle's altitude.
* **`EstimateStages` is KER's altitude estimate**: pressure and gravity at the altitude above the
  vehicle's body. Above the atmosphere it is vacuum, so it needs no vacuum flag. KER skips
  sequences without engines here.
* **`DesignStages`** loads the design's parts as `VehicleDesign` does, the editor panel's analysis.
* **`SuicideBurn` is null** when the vehicle is not descending or its active engines cannot
  overcome gravity. `TimeTo` is zero once KER says burn now.
* **Binding by `MemberBinder`.** `Available` is whether the assembly is loaded. Members bind on first
  use, after StarMap has loaded every mod. A missing member binds to a stub that throws, so only
  the RPCs using it fail, and the log names it.
* **`KRPC.Core` copies.** The mod builds against the 0.7.0 release, which has no `Accessor`.
  `Accessor`, `Field` and `MemberBinder` are copied into the `KSA` service assembly until it builds
  against a release with them.
* **gRPC through an import.** The gRPC server already served any procedure whose types it can
  encode, classes of other services included. Only `protogen.py` refused a class or enumeration of
  another service. It now imports them from that service's `.proto`, as it did structures, so
  `KittenEngineerRedux.proto` imports `KSA.proto`. Any mod service gets its `.proto` this way.
* **KER is MIT.** Nothing of it ships with kRPC. The tests download the pinned release.

## Tests

The KSA harness gains per-class mod sets, as the KSP harness has: a class lists `mods`, the harness
installs the pinned archive, toggles the mod in `manifest.toml`, and restarts a game it launched
between groups.

| Class | Checks |
| --- | --- |
| No mods | `Available` false, an RPC throws "not available" |
| `Stages` | Matches `Sequence` per stage, TWR against the gravity at altitude |
| `EstimateStages` | Sea level against vacuum: lower Isp and delta-v, TWR at sea level gravity |
| `DesignStages` | Delta-v and mass match `VehicleDesign`, TWR scales with gravity |
| `SuicideBurn` | Descending, ascending and too fast, on Luna, against constant-thrust physics |
| gRPC | `Available`, `Stages`, `DesignStages` and `SuicideBurn` match the kRPC calls |

A negative control, with one member misspelled, failed only the two suicide burn tests that read it,
with the `MemberBinder` message, and logged one warning.
