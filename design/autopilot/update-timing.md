# When the auto-pilot's control loop runs in a tick

**Status:** in progress (2026-08-22) — raised as
[#1070](https://github.com/krpc/krpc/pull/1070), together with
[holding a tick](../server/tick-hold.md), which gives a program a whole tick but no say in
where in it the auto-pilot runs.

## Problem

The control loop runs once per physics tick. A program has no say in where in that tick it
runs relative to its own calls, which breaks the loop patterns the tick hold was built for:
holding a tick puts a whole read, compute and write inside one tick, but the auto-pilot may
already have flown that tick by the time the writes land.

The reported symptom was an attitude error a few degrees behind, proportional to rotation
rate, from a program that rebuilt the auto-pilot's reference frame from the vessel's current
rotation on every iteration.

Measurement came before design, and moved the problem.

### What kRPC controlled: nothing

The loop computes inside `Vessel.OnFlyByWire`. KSP raises that from
`FlightInputHandler.FixedUpdate`, which walks `FlightGlobals.VesselsLoaded` calling
`Vessel.FeedInputFeed`, which raises `OnPreAutopilotUpdate`, `OnAutopilotUpdate`,
`OnPostAutopilotUpdate` and `OnFlyByWire` in that order and then calls
`Part.propagateControlUpdate`. Calls execute in kRPC's own `Addon.FixedUpdate`.

Neither `Assembly-CSharp` nor kRPC declared a `[DefaultExecutionOrder]`, and there is no
Harmony patch or script execution order anywhere in either. The relative order of those two
`FixedUpdate` methods was Unity's undefined default. Whether a call's effect was seen in the
tick it was made in was therefore incidental.

### What the order actually was

Probe: stamp `Time.fixedTime` at the top of the server update and compare it in
`OnFlyByWire`. Result: the server had **not** yet updated, on 55 of 55 sampled ticks.

| | order within a fixed step |
|---|---|
| measured | control input (loop runs), then server update (calls execute), then physics |

So the loop flew tick N with the target written by the calls of tick N-1: one full tick of
skew, on every tick, for every program. That is the opposite of the assumption the work
started from, and it is the bug.

A second probe read the diagnostic log from inside a held tick, before and after writing a
target. Its readings are consistent with the above, but it does not discriminate on its own:
whichever order holds, the new target lands on the first row committed after the last row
visible inside the hold. The `fixedTime` probe is the one that settles it.

### What is left of the repro, and what actually caused it

Run end to end with the loop placed, one iteration per held tick and the vessel spun at 0.2
and 0.5 rad/s, the pointing error read where the info window reads it (after physics) is
under a tick of rotation in every mode, and well under a degree. The modes do not separate
cleanly there and are not meant to: the auto-pilot is damping the spin throughout, so the
rate the error is divided by is not the rate the vessel has. A tick is also the floor, since
the error is read after physics has moved past the frame the program set. The discriminating
measurement is the diagnostic-log test below, which reads which tick the loop consumed a
target on rather than inferring it from an angle.

The reported few degrees are a second cause, which this work does not address.
`ReferenceFrame.CreateRelative` stores a static rotation; its `angularVelocity` argument
affects velocity transforms only and never turns the frame over time. The frame is a
snapshot, so a loop managing one iteration every N ticks is N ticks stale whatever the
ordering, and the ordering was only ever one of those ticks. Slowing the same loop down, at
0.5 rad/s in `AfterCalls`:

| ticks per iteration | worst error |
|---|---|
| 1.0 | 0.38 deg |
| 3.1 | 1.31 deg |
| 8.1 | 3.16 deg |

So the few degrees are a loop running every eighth tick, not a misplaced control loop.
`ReferenceFrame.CreateRelative` now says its offsets are fixed, which its docs did not,
rather than the behavior being worked around.

## What was built

Compute and apply were already separated: the loop wrote into a per-vessel `ControlInputs`
cache and `OnFlyByWire` only added that cache to the live `FlightCtrlState`. So the loop's
position in the tick could be chosen without touching the control law.

* The controller owns its output and exposes `Step`, which runs the loop once and stamps the
  tick. `OnFlyByWire` became apply-only.
* `Core` raises `OnBeforeCalls` and `OnAfterCalls` around the call phase of each update. The
  SpaceCenter pilot addon subscribes and runs the loops whose mode selects that point.
* `AutoPilot.UpdateMode` picks the point per vessel; `AutoPilot.Update` runs the loop for the
  manual mode.
* `KRPC.Addon` declares `[DefaultExecutionOrder (-100)]`, so the server updates before the
  game collects control inputs and a call's effect is seen in the tick it is made in. Unity
  honors the attribute for an assembly KSP loads at runtime, which was the open question:
  the pilot addon reports the order it observes once per flight session at debug level, and
  with the attribute it reports the server going first.

### Decisions

| Decision | Choice | Why |
|---|---|---|
| One enum, not a flag plus a boolean | `AutoPilotUpdateMode` with `AfterCalls`, `BeforeCalls`, `Manual` | Where the loop runs is one question with three answers. A boolean for the two automatic points plus a separate manual flag makes two settings that cannot both be honored |
| Default | `AfterCalls` | The point of the change: a target set in a tick is flown on that tick. `BeforeCalls` is what the game happened to do before, kept because reading the loop's own output back in the tick it was computed for is worth a mode |
| Naming | "calls", not "RPCs" | The vocabulary `internals.rst` already uses |
| Where it lives | Per vessel, on the controller | One loop per vessel running once per tick, so two clients cannot each have their own placement for it, for the same reason `TargetPitch` is not per client. On the controller because the `AutoPilot` objects are transient views |
| Tick identity | `Time.fixedTime` equality | The same value for every script in a fixed step however they are ordered, and frozen while the game is paused. A counter incremented by an addon would depend on that addon's own place in the frame, which is the thing in question |
| A missed tick in manual mode | Hold the last output for 0.1 s, then contribute nothing | A hiccup should not drop the controls to zero mid-burn; a program that stops driving the loop should not leave a deflection latched on the vessel |
| A second `Update` in one tick | Silent no-op | The loop's numerics assume one run per tick. This is also what makes the no-server fallback safe |
| `Wait` in manual mode | Throws | It takes several ticks and blocks the caller for all of them, so the caller cannot run the loop and the vessel never converges. Its timeout defaults to none, so it would never return |
| Pinning the execution order | `[DefaultExecutionOrder (-100)]` on the server addon | Without it `AfterCalls` still fixes the target/state mismatch but the command is applied one tick later, since apply is pinned to a point that runs first |

### Things that fall out of it, and are easy to get wrong

* **The no-server fallback must be gated on there being no server, not on the loop not having
  run yet.** The loop still has to run when the server is not updating: stopped, or the game
  paused with `PauseServerWithGame` off. Running it from `OnFlyByWire` when it has not run
  this tick looks equivalent and is not: with control input ahead of the server update, that
  test is true every tick, the fallback wins every tick, and no mode ever has any effect.
* **The events must be raised outside the poll loop.** A held update runs its poll loop many
  times over. Raising them in `Core.Update` around `RPCServerUpdate` makes once-per-update
  true by construction rather than by care, and keeps handler cost out of the RPC timings.
  Raising `OnAfterCalls` before the stream update also means streams see what the handlers
  did.
* **A handler that throws takes the server's update with it.** An exception escaping a `Core`
  event handler propagates into the addon's `FixedUpdate`; before this it escaped into KSP's
  `FeedInputFeed` and cost one vessel. Each controller's step is caught and logged.
* **Pinning the order moves every call, not just the auto-pilot's.** Reads are unaffected, as
  the physics step runs after all of them, and kRPC's control writes are applied at the game's
  control input point regardless. The exposure is calls whose side effects stock code consumes
  later in the same step, and mods that depended on the previous incidental order.

## Tests

* `service/SpaceCenter/test/test_autopilot_update_mode.py` reads the diagnostic log from
  inside a held tick and asks whether the held tick's row is already committed: it is under
  `BeforeCalls`, carrying the previous target, and is the next row committed under
  `AfterCalls`, carrying the target the hold wrote.

  Asking that needs the log's tick stamp tied to a tick the client can name, and the second
  probe above is the cautionary tale: "the new target is on the first row after the last
  one visible inside the hold" reads like a discriminator and is true under both orderings.
  The test calibrates instead, in manual mode, where one `Update` inside a held tick commits
  exactly one row and that row is that tick's by construction. That fixes the offset between
  the stamp and universal time, and the modes under test are then measured against it.

  Also covers manual mode running the loop exactly once per `Update`, the no-op on a second
  `Update` in a tick, the output going away when the loop stops being run, and `Wait`
  refusing.
* `core/test/UpdateEventsTest.cs` covers the events firing exactly once per update, including
  an update that held a tick, and bracketing the calls.

## Relationship to the planned work

Composes with the tick hold: the hold decides which tick the calls happen in, the update mode
decides where among them the loop runs, and manual mode plus a hold gives both. Neither is
needed to use the other.

Independent of batching (#903) and request ids
([request-ids.md](../protocol/request-ids.md)): those decide how calls reach a tick, not what
the auto-pilot does within it.
