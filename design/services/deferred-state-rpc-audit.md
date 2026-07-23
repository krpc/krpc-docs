# Audit: same-tick "deferred-state" RPC bugs (the #236 class)

**Status:** done — actioned by [PR #983](https://github.com/krpc/krpc/pull/983) (2026-07-19). A
codebase-wide sweep triggered while fixing
[#236](https://github.com/krpc/krpc/issues/236) (SAS mode dropped when set in the same tick as
enabling SAS, itself merged as [PR #928](https://github.com/krpc/krpc/pull/928)). The issue text
noted "there are other RPCs like this" but named none, so this audit set out to find them. Every
finding was dispositioned: Findings 1–2 fixed, Finding 3 documented, and Finding 5 plus the
test-suite cleanups tidied up — all in PR #983; Finding 4 was already covered by the
custom-control-axis work ([PR #938](https://github.com/krpc/krpc/pull/938)). No umbrella GitHub
issue was filed — the PR is the record.
This doc is the historical record of the audit; shipped behavior lives in the `krpc` docs and PR
history.

## The bug class

A setter RPC writes some KSP state, but the game engine only *acts on* that write during a later
`Update`/`FixedUpdate` (or over a multi-frame animation). A second RPC in the **same server tick** —
or a read-back — then observes stale state, or the game later overwrites/resets what the first RPC
set. The command is silently lost with no error to the client; the only client-side workaround is an
arbitrary `sleep` between the two calls.

The canonical instance (#236): `Control.SAS = true` only flips a KSP action group; KSP's
`VesselAutopilot` does not enable itself until its own `Update` observes that group on a later frame.
`Control.SASMode = x` in the same tick ran `Autopilot.SetMode(x)` while the autopilot was still
disabled, so KSP merely stored the mode field; the pending `Update` then called
`Enable()` = `Enable(StabilityAssist)`, overwriting it. Fixed by enabling atomically with the
requested mode (`VesselAutopilot.Enable(mode)`) when the SAS group is on but the autopilot has not yet
enabled.

## Why some setters are vulnerable and others are not

The sweep is really a classification of every state-setting RPC into one of:

* **Override-store (immune).** kRPC keeps its own copy of the requested value and applies it to the
  game every `FixedUpdate` (the `PilotAddon.ControlInputs` mechanism for throttle/axes, the
  `AttitudeController` for autopilot attitude). The *set* is reliable because it is re-applied; it
  cannot be "dropped." (Read-back symmetry is a separate question — see Finding 3.)
* **Synchronous direct write (safe).** The setter writes a KSP field/toggle that the game applies
  immediately, and any dependent getter reads the same field. `ActionGroupList.SetGroup` updates its
  `groups` array synchronously; `MultiModeEngine.SetPrimary`, `VesselAutopilot.Enable(mode)`,
  `MapView.enterMapView`, `PatchedConicSolver.UpdateFlightPlan` all apply in-call. These are the
  bulk of the surface and are fine.
* **Deferred direct write (vulnerable).** The setter writes state the game only reacts to later, and
  something in the same tick depends on it having been processed. This is the #236 class. It is rare —
  it needs *two* coupled operations where the second's success depends on the game having digested the
  first.

The audit looked hardest at the third bucket, and at getters that read a field the setter just wrote
before the game applied it.

## Methodology

Three parallel read-only auditors, cross-checked against the real game DLL
(`Assembly-CSharp.dll` via `ikdasm`) and re-verified by hand for the actionable leads:

1. `Control.cs` / `AutoPilot.cs` (+ `PilotAddon.cs`) — the direct control surface.
2. `service/SpaceCenter/src/Services/Parts/**` and the other service DLLs — part/module setters.
3. The test suites — `wait()`/`sleep()`/`TODO` evidence of latency the tests already work around.

## Findings (ranked)

### 1. ResourceHarvester `Active` silently dropped during the deploy animation — genuine #236 class

`service/SpaceCenter/src/Services/Parts/ResourceHarvester.cs` (`Active` setter, ~line 104):

```csharp
public bool Active {
    get { return State == ResourceHarvesterState.Active; }
    set {
        if (!Deployed)          // Deployed == false for the whole deploy animation
            return;             // -> activation silently dropped
        if (value && !harvester.IsActivated)
            harvester.StartResourceConverter ();
        ...
    }
}
```

`Deployed` returns false while `State == Deploying`, i.e. for the entire multi-second deploy
animation (`ModuleAnimationGroup.DeployModule` sets `isDeployed` and starts the animation; `State`
reports `Deploying` until it finishes). So the natural sequence

```python
harvester.deployed = True
harvester.active   = True     # dropped: the drill never starts
```

discards the activation with no error. This is **worse than #236**: the window is the whole animation
(seconds), not a single physics tick, so even a short client `sleep` can miss it. To make it work a
client must poll `deployed` until true, then set `active`.

* **Confidence:** High that the drop happens (provable from kRPC source; animation timing confirmed in
  the DLL). The judgment call is whether it's "intended" — stock KSP's PAW also disables *Start*
  until deployed — but the silent, feedback-free drop across an RPC boundary is the defect.
* **Fix options:** (a) drop the `if (!Deployed) return;` guard and let `StartResourceConverter()` be
  issued (KSP produces once deployed); (b) defer the requested active-state and apply it when the
  deploy completes; or (c) throw instead of silently returning, so a client can react. Option (b) best
  matches the #236 "apply atomically / when the prerequisite is ready" philosophy.
* **Test:** an in-game `test_parts_resource_harvester.py` that sets `deployed=True` then immediately
  `active=True` and asserts the harvester reaches `Active` (polling a bounded number of ticks) goes
  red today. (The deploy animation does not run for a packed vessel, so this needs the live game, like
  the #889 ExtractionRate test.)
* **Related but distinct** from the completed #889 (`ResourceHarvester.ExtractionRate` read fix).

### 2. Thrust-reverser `Reversed` is non-idempotent mid-animation — minor

`service/SpaceCenter/src/Services/Parts/ThrustReverser.cs` (`AnimationThrustReverser`, ~line 128):

```csharp
public bool Reversed {
    get { return (animation.animTime > 0.5f) == reversedWhenDeployed; }
    set { if (value != Reversed) animation.Toggle (); }
}
```

`Reversed` is inferred from `ModuleAnimateGeneric.animTime`, which ramps across the toggle animation
and only crosses 0.5 mid-transition. A client that sets `thrust_reversed = True`, reads it back (still
`False` because the animation hasn't reached the midpoint), and — seeing it "didn't take" — sets
`True` again will `Toggle()` a *second* time and cancel the first, ending *not* reversed. Only affects
client retry loops; `Control.ThrustReversers` (one set per engine) is unaffected.

* **Confidence:** Low–Medium (needs a client re-assert inside the animation window).
* **Fix:** track the commanded target (like the `ActuatorControl` overrides) instead of inferring from
  animation progress. A "set True twice in immediate succession, assert reversed" test would catch it.

### 3. Control-input getters read *applied* state, not the set value — by design, worth documenting

`Control.Throttle` / `Pitch` / `Yaw` / `Roll` / `Forward` / `Up` / `Right` / `WheelThrottle` /
`WheelSteering` (`Control.cs`), backed by `PilotAddon.cs`:

The setter writes kRPC's `manualInputs`; the getter reads `currentInputs`, a *different* dictionary
that KSP refreshes via the `OnFlyByWire` callback on the **next** `FixedUpdate`, and which reflects
the *combined* applied input (manual + SAS + autopilot + keyboard) taken from the real
`FlightCtrlState`. So `control.pitch = 1; control.pitch` reads stale by one tick, and a stream on
`control.pitch` lags a set by a tick.

This is **not** a dropped-command bug — the override-store makes the *set* reliable — but the get/set
asymmetry is a genuine gotcha. It is arguably intended (get = "what the craft is using", set = "your
override"). Decide the semantics, then either document it or have the getter return the requested
value from `manualInputs`.

### 4. CustomAxis get-after-set staleness — already tracked, do not double-solve

`Control.CustomAxis01`–`04` get-after-set is stale (the getter reads a `FlightCtrlState` field the
game only writes during its axis-module update), and the write targets the active vessel rather than
the RPC's target vessel. Both were addressed by the custom-control-axis work
([PR #938](https://github.com/krpc/krpc/pull/938)), which routes custom axes through the control
state. Flagged here only so it was not fixed twice.

### 5. Engine `HasFuel` — false positive (test cruft only)

`Engine.HasFuel` (`Engine.cs` ~line 366) already calls `propellant.UpdateConnectedResources()` —
which synchronously refreshes `actualTotalAvailable` via `Part.GetConnectedResourceTotals` — and
computes fuel from live propellant totals. It does **not** depend on the engine having fired. The
`# FIXME: have to activate engine for this to work` comments in `test_parts_engine.py` and
`test_vessel.py` are **stale**, predating that reimplementation; their `active`/`throttle` waits are
removable. Recorded so the FIXMEs are not mistaken for a live bug.

## Cleared as safe (spot-checked, several against the DLL)

* Action groups SAS(fixed)/RCS/Gear/Lights/Brakes/Abort and the aggregate part setters — `SetGroup`
  updates the `groups` array synchronously; no action group other than SAS has a coupled dependent
  RPC.
* Staging (`ActivateNextStage`) — deferral already handled via `YieldException` gated on
  `StageManager.CanSeparate`.
* Maneuver `Node` — every setter calls `patchedConicSolver.UpdateFlightPlan()` synchronously, so the
  read-back orbit is correct.
* Engine `Mode`/`ToggleMode`/`AutoModeSwitch` — `MultiModeEngine.SetPrimary` flips mode + running
  engine synchronously.
* `Camera.Mode = Map` then pitch/heading/distance — `MapView.enterMapView` sets `MapIsEnabled`
  synchronously (not via the `MapView.Start` coroutine).
* ReactionWheel `Active`, SolarPanel/Radiator/Antenna/CargoBay/Wheel deploy getters (treat
  `…ing`/`Opening` as deployed by design), warp config, `Module.SetField*`/`TriggerEvent`, and the
  InfernalRobotics / RemoteTech / UI / Drawing setters.
* Navball `SpeedMode` — writes `FlightGlobals.speedMode` exactly as KSP's own `CycleSpeedModes` button
  does; any per-frame revert would affect stock too. (Minor cosmetic nit: unlike the stock button it
  has no "skip Target when no target is set" guard.)

## Test-suite cleanup found along the way (not bugs)

* **Vestigial removable waits** (verified against synchronous C# setters): `test_control.py`
  `test_speed_mode` trailing waits; `test_parts_wheel.py` friction round-trips; `test_parts_antenna.py`
  `allow_partial`; the Drawing/UI post-assert render waits.
* **Unexplained**: three `test_spacecenter.py` warp setups carry `cls.wait(1)  # TODO: why is this
  wait needed?` — almost certainly rails-warp readiness (physics settling) but never pinned down.
* Stale engine `has_fuel` FIXMEs (Finding 5).

## Recommendation

Only **Finding 1 (ResourceHarvester deploy→activate)** was a genuine new #236-class defect worth a
dedicated fix + in-game regression. Findings 2–3 were lower-severity and bundled or documented;
Finding 4 was covered by existing work; Finding 5 and the test-cleanup items were opportunistic
tidy-ups. The broader, reassuring result is that #236 was
close to unique — the control surface is dominated by the override-store and synchronous-write
patterns, which are immune by construction.
