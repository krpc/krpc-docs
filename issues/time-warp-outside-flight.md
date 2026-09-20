# Time warp outside the flight scene — vessel-independent warp API

**Status:** proposal — no issue filed yet.

Surfaced by the TODO/FIXME sweep (§3e, [`todo-fixme-sweep.md`](../design/todo-fixme-sweep.md)): the warp
RPCs in `SpaceCenter.cs` are gated `GameScene = GameScene.Flight`, with the constraint now
documented in a comment above the warp region — the API is defined in terms of the active vessel
(rails-warp altitude limits, the physics-warp fallback in `WarpTo`, `CanRailsWarpAt`). KSP itself
supports on-rails warp in the space center and tracking station scenes, so clients should be able
to warp from there too — e.g. a script that sits at the space center and warps to an alarm or
transfer window.

## Per-member sketch

The gating is per-RPC via the `GameScene` attribute, so this decomposes cleanly:

- **Read-only surface** (`WarpMode`, `WarpRate`, `WarpFactor`, `RailsWarpFactor` getter) — scene
  independent; the `TimeWarp` singleton exists in all three scenes. Widen to
  `Flight | SpaceCenter | TrackingStation`.
- **`RailsWarpFactor` setter** — valid in all three scenes; outside flight there are no altitude
  limits, so clamp only to the warp-rate table length.
- **`PhysicsWarpFactor`** — stays flight-only (`TimeWarp.Modes.LOW` is a flight-scene concept).
- **`CanRailsWarpAt` / `MaximumRailsWarpFactor`** — vessel-dependent by definition; outside flight
  every factor is allowed, so return true / the table maximum rather than reading `ActiveVessel`.
- **`WarpTo`** — works on rails outside flight; the physics-warp fallback branch only applies in
  flight. Needs the `CanRailsWarpAt` call guarded by scene.

## Reachability and testing

The settable `KRPC.GameScene` ([#897](https://github.com/krpc/krpc/pull/897), merged) makes this
both reachable (clients can switch to the space center scene) and testable (krpctest can drive the
scene switch in-game). Widening the `GameScene` metadata changes the service definitions, so client
stubs need regenerating; the change is additive (RPCs callable in more scenes), not breaking.
