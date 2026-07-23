# Client-disconnect cleanup as a shared component

**Status:** done — merged as [PR #934](https://github.com/krpc/krpc/pull/934), 2026-07-12.

## Motivation

When a client disconnects (script crash, network drop, or plain exit without cleanup), any
in-game state it set up should not leave the game stuck. The AutoPilot and actuator-control
addons already handled this; other addons did not, and those that did each rolled their own
mechanism:

| Addon | Before this change |
|---|---|
| `AutoPilot` | polls `requestingClient.Connected` in `Fly()`; disengages + resets on disconnect |
| `PilotAddon` | polls a `HashSet<IClient>`; clears manual inputs (except throttle) when **all** setting clients are gone |
| `ActuatorControlAddon` | per-entry client tag in a generic `OverrideRegistry`; `Sweep()` in FixedUpdate releases on disconnect or module destruction, restoring saved KSP state |
| `PartHighlightAddon` | subscribed `Core.Instance.OnClientDisconnected` in `Awake` and **never unsubscribed** — one leaked handler per Flight-scene load |
| `PartForcesAddon` | **nothing** — `Part.AddForce` forces kept pushing the vessel forever after a disconnect |
| `ResourceTransferAddon` | **nothing** — transfers kept running to completion |
| `Drawing.Addon`, `UI.Addon` | per-client dictionaries polled in `Update()` — two near-identical copies of the same code |

The goal: one reusable component shared by all of these, plus new disconnect cleanup for part
highlighting (mechanism unified), part forces (forces removed) and resource transfer
(in-progress transfers canceled).

## The three ownership models

The addons do not all share one ownership shape, so the component provides two registry
classes over one low-level primitive rather than forcing everything into a single mold:

1. **Per-object ownership, flat set** — forces, transfers, highlighted parts, drawables, UI
   objects. Each object is tagged with the client that added it; release it when that client
   disconnects. → `ClientOwnedObjects<T>`.
2. **Per-key override with install/release and saved state** — actuator overrides (gimbal,
   RCS, control surface), keyed by the part module, restoring saved KSP state on release.
   → `ClientOwnedOverrides<TKey, TEntry>`.
3. **Aggregate / single-owner with custom semantics** — PilotAddon (clear only when *all*
   setting clients are gone, preserving throttle) and AutoPilot (single engaging client;
   reset-and-disengage). These keep their bespoke logic and use only the shared primitive.

## Component API (server assembly, `KRPC.Utils`, `server/src/Utils/`)

The component lives in the server assembly because every service DLL references it and it
needs UnityEngine (`MonoBehaviour`, `Time.frameCount`); `core/` is Unity-free (used by the
standalone TestServer) so only non-Unity code could go there, and nothing needed to.

* **`ClientConnections.Disconnected(IClient)`** — the primitive. Returns false for a null
  client (state set outside an RPC is never swept, matching the actuator addon's old guard).
  Caches `IClient.Connected` per `Time.frameCount`: TCP's `Connected` does a real socket
  `Poll` + zero-byte `Peek` per call, so with many registries sweeping many entries this
  collapses to **one socket poll per client per rendered frame** across the whole mod
  (`Time.frameCount` is stable across multiple FixedUpdate steps within a frame, which at
  worst delays detection by one frame — polling is self-correcting).
* **`IClientOwnedCollection`** — `Sweep()` / `Clear()`.
* **`ClientOwnedObjects<T>`** — flat list of (object, owner) entries; owner captured from
  `CallContext.Client` in `Add`. Optional release callback invoked on `Sweep`/`Clear` (not on
  `Remove` — call sites do their own teardown, matching prior behavior). `OwnedByCaller`
  preserves the Drawing/UI semantic that a client removing another client's object gets an
  `ArgumentException`. A per-client `Clear(IClient)` overload backs the `Drawing.Clear`/
  `UI.Clear` `clientOnly` RPCs. A flat list rather than the old `Dictionary<IClient, IList<T>>`
  tolerates null owners (the dictionaries would have thrown).
* **`ClientOwnedOverrides<TKey, TEntry>`** — `ActuatorControlAddon.OverrideRegistry` lifted
  verbatim, with the key constraint relaxed from `PartModule` to `UnityEngine.Object`. The
  Unity-null "destroyed" check lives here because it is inherent to any registry keyed by a
  Unity object; `ClientOwnedObjects` element types are not Unity objects, so there the release
  callbacks guard instead (e.g. un-highlight checks `part == null`). `ClientOwnedEntry` holds
  the `Owner` tag.
* **`ClientCleanupAddon`** — abstract `MonoBehaviour` base. `Collections` (abstract) lists the
  addon's registries; `Sweep()`/`Clear()` iterate them; `Awake`/`OnDestroy` clear (scene
  changes). Registries remain `static` fields of each addon so RPC service classes can reach
  them through static internal methods; the MonoBehaviour instance only drives lifecycle.

### Cadence rules (deliberately not in the base class)

* Addons that affect **physics** (actuators, forces, transfers, pilot inputs) sweep at the
  **top of `FixedUpdate`**, before applying any client state, so a disconnected client's
  force/override/transfer is never applied in the physics step in which the disconnect is
  detected.
* Purely **visual** addons (highlighting, Drawing, UI) sweep in **`Update`**, which — unlike
  `FixedUpdate` — still runs while the game is paused, so their state disappears promptly
  even when paused.

### Polling vs the disconnect event

Everything is unified on polling `Connected` (via the cache): it is self-correcting, catches
dead sockets independent of the event delivery path, and removing PartHighlightAddon's
`OnClientDisconnected` subscription fixes its per-scene-load handler leak. The
`Core.Instance.OnClientDisconnected` event remains available for other uses.

## Migration summary

* **ActuatorControlAddon** — deleted its private `Entry`/`OverrideRegistry`/`Disconnected`
  machinery (~120 lines) in favor of the shared classes; zero behavior change.
* **PartHighlightAddon** — `ClientOwnedObjects<Part>` swept from `Update`; event subscription
  deleted; un-highlight release guards against the part having been destroyed (fixes a latent
  NRE); `Remove` now delists the part regardless of owner (previously another client's entry
  went stale).
* **PartForcesAddon** *(new behavior)* — both persistent and instantaneous force lists are
  `ClientOwnedObjects<Force>` (no release callback — a removed force simply stops being
  applied); sweep-first `FixedUpdate`. Also fixes `OnDestroy` not clearing instantaneous
  forces. `Part.AddForce` docs note the force is removed on disconnect.
* **ResourceTransferAddon** *(new behavior)* — `ClientOwnedObjects<ResourceTransfer>` with
  release `transfer.Cancel()`, a new internal method that marks the transfer `Complete` so it
  moves no more resource; other clients holding the object see it complete with a partial
  `Amount` rather than hang forever (documented on `Complete`). Sweep-first `FixedUpdate`
  means a canceled transfer never moves resource in the tick the disconnect is seen.
* **Drawing.Addon / UI.Addon** — the duplicated dictionaries replaced by
  `ClientOwnedObjects<T>` with `Destroy()` release; the `Clear(clientOnly)` RPCs route through
  the registry's per-client clear. No behavior change.
* **AutoPilot / PilotAddon** — one-line swaps to `ClientConnections.Disconnected`; their
  special semantics are untouched. PilotAddon does not inherit the base class (its
  scene-lifecycle state is not registry-shaped). Net effect: all disconnect detection across
  the mod keys off one socket poll per client per frame.

## Testing

In-game integration tests (krpctest), following the existing second-connection pattern from
`test_autopilot.test_reset_on_disconnect`: connect a second client (`use_cached=False`), set
state, `close()`, wait, assert cleanup from the primary client.

New tests (all red on `main`, except the highlight ones which pass there via the old event):

* `test_parts_engine.test_gimbal_override_released_on_disconnect`
* `test_parts_rcs.test_input_override_released_on_disconnect`
* `test_parts_control_surface.test_deflection_override_released_on_disconnect` (also asserts
  the saved surface state is restored)
* `test_parts_part.test_highlighting_removed_on_disconnect` and
  `test_highlighting_persists_for_connected_client` (per-owner scoping)
* `test_parts_part.TestPartsPartForceDisconnect.test_force_removed_on_disconnect` — in a
  100 km Kerbin orbit, a second client applies a torque-producing force; angular speed grows
  while connected and stops growing after disconnect.
* `test_resource_transfer.TestResourceTransferDisconnect.test_transfer_cancelled_on_disconnect`
  — fresh craft, Oxidizer `fuelTank` (50/220) → `fuelTankSmallFlat` (30/55) at 5.5 u/s
  (~4.5 s to fill); disconnect mid-flow; asserts some-but-not-all moved, the destination still
  has free space (so the transfer would still be running had it not been canceled), and the
  source amount stops changing.

Regression acceptance: existing `test_autopilot.test_reset_on_disconnect`,
`test_dont_reset_on_clean_disconnect` and `test_control.test_clear_on_disconnect` cover the
AutoPilot/PilotAddon primitive swap; the Drawing/UI suites cover their no-behavior-change
migration.

## Rejected alternatives

* **Event-based cleanup everywhere** (`OnClientDisconnected`): would need careful
  subscription lifecycle management per addon (the existing use leaked), and misses any
  disconnect the event path fails to deliver; polling with a per-frame cache costs one socket
  poll per client per frame.
* **One registry class for everything**: PilotAddon's aggregate clear-when-empty (throttle
  preserved) and AutoPilot's reset-and-disengage do not fit per-entry release semantics;
  forcing them in would obscure behavior that must not change.
* **Sweep cadence in the base class**: would either break paused-game cleanup for visual
  addons (FixedUpdate does not run while paused) or same-tick guarantees for physics addons.
