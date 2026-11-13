# Trajectories: four errors in the log when Trajectories is not installed

With Trajectories absent, the Trajectories service logs four errors at load:

```
[kRPC] Error - [Trajectories API] Failed to grab VesselState Type
[kRPC] Error - [Trajectories API] Failed to grab Point Type
[kRPC] Error - [Trajectories API] Failed to grab Patch Type
[kRPC] Error - [Trajectories API] Failed to grab Node Type
```

`Trajectory.Load` combines its loaders with `&=`, so `VesselState.Load`, `Point.Load` and `Patch.Load` still run, and log, after `APILoader.Load` finds no `Trajectories.Trajectory`. The descent profile node loader does the same. Every game without Trajectories shows these errors, which reads as a kRPC fault.

Proposed fix: skip the nested loaders when the mod's assembly is missing, and log nothing, as the other mod services do. Keep an error, or a warning, for a Trajectories that is installed but lacks a type.

Tests: start the game without Trajectories and check the log has no `[Trajectories API]` errors.

Labels: `bug`, `service`, `ksp`, `mods`. Milestone: `ksp-v0.8.0`.
