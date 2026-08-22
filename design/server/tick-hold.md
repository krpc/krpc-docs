# Holding a physics tick for a control loop

**Status:** in progress (2026-08-17) — implemented, PR not yet raised. A deliberate stopgap for
[#251](https://github.com/krpc/krpc/issues/251), to be retired once real tick synchronization
lands in the protocol rewrite.

## Problem

A control loop reads the game state, computes with it and writes the result back, and the
computing happens between the calls. The server executes RPCs inside `FixedUpdate` and polls for
the next one for at most `RecvTimeout`, so a client that takes longer than that to send its next
call is not waiting when the server looks, and the server leaves the update. That client is served
**one RPC per tick**, however many it makes: see
[the receive timeout cliff](recv-timeout-cliff.md) for the measurements.

So an iteration of N calls costs N ticks, and the values written were computed from a state N ticks
old. Measured against a 60 Hz `TestServer`, five calls with 2 ms of work between them:

| | per iteration | ticks |
|---|---|---|
| as it was | 83.33 ms | 5 |
| holding the tick | 16.63 ms | 1 |

Nothing already available fixes this:

 * **Batching** ([reverse-streams.md](../protocol/reverse-streams.md) rung 1, #903) puts several
   calls in one request so they run in one tick. It cannot help: the computing sits between the
   reads and the writes, so the writes are a separate request in a later tick.
 * **Raising `RecvTimeout`** moves the cliff and costs that much frame time on every idle update.
 * **Server-side functions** (#679) move the computing to the server, which answers some loops and
   is not general.
 * `KRPC.Paused` stops physics altogether, which is not a control loop.

## What was built

`KRPC.HoldTick` holds the game on its current tick; `KRPC.ReleaseTick` lets it move on. Every call
made in between is executed inside the same update, so the reads, the computing and the writes all
happen in the state of one tick.

This is not new machinery. At a 950 us client gap the server already served ~10 round trips inside
one update; the hold removes the time bounds on a loop that already runs, for one client, for as
long as it asks.

```python
while True:
    conn.krpc.hold_tick()
    try:
        pitch = vessel.flight().pitch
        vessel.control.pitch = control_law(pitch)
    finally:
        conn.krpc.release_tick()
```

### Decisions

| Decision | Choice | Why |
|---|---|---|
| Names | `HoldTick` / `ReleaseTick` | Says what it does. "Transaction" would promise atomicity and rollback that this has not, and would collide with #903's batching, which the design repo already calls batching/transactions |
| Timeout | `TickHoldTimeout` setting, 1 s default | It is the server owner's game that freezes, so the server owns the bound. Follows `RecvTimeout` through `Configuration`, the settings file and the settings window |
| Exclusive | One holder at a time | What a hold offers is that nothing else happens, which two clients cannot both be given. Two holders would also livelock: one releases, re-reads the same unchanged tick and recomputes until the other lets go |
| `ReleaseTick` with no hold | Tolerant no-op | Always safe to call from a `finally`, which is how a hold must be released |
| `HoldTick` while held | Refused | Re-arming would let a client renew before its deadline and hold the game for as long as it liked |
| `HoldTick` after a release in the same tick | Yields to the next tick | One hold per tick, whoever asks. A tick that has been held and let go has done its waiting, and a client looping on hold and release, or two passing it between them, could otherwise defer it for as long as they kept asking. Yielding rather than refusing means a control loop just gets its next tick, with no retry to write |
| Client libraries | None | The two RPCs work from every client as they are |

### How the update loop honors it

`RPCServerUpdate` in `core/src/Core.cs` has six exits, and a held tick suppresses five of them: the
`RecvTimeout` poll break, both `MaxTimePerUpdate` breaks, the per-continuation "delay to the next
update", and `OneRPCPerUpdate`. The poll loop then has no exit left but the hold ending, which is
what `TickHeld` decides on every pass. `rpcContinuations.Count == 0` stays as it was, since while
held the poll only comes back empty once the hold has gone.

Three things fall out of that and are easy to get wrong:

 * **Adaptive rate control must skip an update that held a tick.** It shrinks `MaxTimePerUpdate` by
   100 us whenever an update overran the 59 FPS target, down to a 1 ms floor. A held tick overruns
   it by design, so a control loop would otherwise ratchet the budget to its floor within seconds
   and throttle every other client as a side effect.
 * **A call that needs another tick ends the hold.** A yielding RPC (staging, warping, vessel
   switching) puts its continuation aside for the next update, and `PollRequests` skips a client
   that has one in flight — so the client waits for a response that cannot arrive until the update
   ends, which the hold prevents, until the timeout fires. The hold is released instead, with a
   warning, and the call finishes in the next tick.
 * **The update ends when a hold ends, and a second hold in the same update is refused.** The
   update ending covers a client whose release is the last call of the update. It does not
   cover a release and a hold sent in one request, which run in one continuation: the release
   cannot end the update before the hold behind it executes, and the hold arrives to find the
   tick free. `HoldTick` therefore turns itself down when the update has already held a tick,
   which is the check that holds for both. Without it, one request repeated is enough to defer
   the tick for as long as a client keeps asking.

### Ways a hold ends

Released, timed out, the client disconnected, or the client called something that needs another
tick. Disconnection is checked by the hold itself rather than left to the between-updates
reconciliation, since nothing reconciles clients while an update is in progress: without that, a
killed client freezes the game for the whole timeout.

A hold cannot be taken by a stream or an event. Those run after the update has finished with the
calls, so a hold taken there would be found in force by the next update with no client waiting to
release it, and taken again before that one ended — a game frozen for a timeout every tick, with no
client left to blame. This is guarded rather than documented.

## What it costs, and what it does not

The game renders no frame, takes no input and runs no physics while a tick is held. A 5 ms hold
costs 5 ms of every update it happens in; a 100 ms hold leaves the game at about 10 frames a
second. What it does not cost is the simulation: physics runs on a fixed time step, so a game whose
ticks are held runs slower than real time rather than differently. KSP clamps
`Time.maximumDeltaTime` (0.04 s in `settings.cfg`), so the time a hold costs is dropped rather than
caught up in a burst of ticks afterwards.

For a control loop that is the right trade. For anything else it is not, which is why this is opt
in, per client, and bounded.

Also worth knowing:

 * Streams do not update inside a hold, since stream updates are sent after the calls are executed.
   Read with calls, and never wait for a stream or an event inside a hold: it cannot arrive until
   the hold has ended, so it waits out the timeout.
 * New connections are not accepted while a hold is in force, since the servers are polled between
   updates.
 * A hold taken while the game is paused, with `PauseServerWithGame` off, blocks the pause menu for
   its duration and gains nothing, as physics is not advancing anyway. Documented rather than
   special-cased.
 * `MaxTimePerUpdate` is not observed during a hold, so any number of RPCs, including other
   clients', can execute in that tick.
 * A hold does not change the read-after-write staleness of the deferred-write setters catalogued
   in [deferred-state-rpc-audit.md](../services/deferred-state-rpc-audit.md).

## Relationship to the planned work

[#251](https://github.com/krpc/krpc/issues/251) ("Execute one RPC per frame") is the planned
feature, listed as tick control in [single-connection.md](../protocol/single-connection.md) with no
dedicated design. It suggests batching RPCs into transactions that execute in one frame, which is
#903's batching, and which as noted above does not serve a loop that computes between its calls.
This holds the tick instead, which is the part no other design covers.

It composes with, rather than competes with, batching (#903) and request ids
([request-ids.md](../protocol/request-ids.md)): a batch inside a hold is fine, and pipelining does
not need the tick held. When #251 lands properly, these two procedures can be marked `[Obsolete]`
under the mechanism from PR #926.

## Tests

 * `core/test/TickHoldTest.cs` drives `Core.Update()` with a scripted client whose requests are
   released only after the server has polled for them enough times, so "the client is thinking" is
   counted in polls rather than measured on a clock. The discriminating pair: four scripted calls
   take one update with a hold and one call per update without. Also covers the timeout, a client
   that goes away mid-hold, the refusal outside a call, the tolerant release, and one hold per
   tick both ways round, the second of which needs the scripted client to send several calls in
   one request.

   Two things the tests got wrong at first, since both hid real failures: a call that fails is
   reported in its own result rather than on the response, so asserting on the response alone
   passed however the calls went; and the game scene the calls are gated on was left to whichever
   fixture happened to run first, which put every call one error away from being noticed.
 * `service/SpaceCenter/test/test_tick_hold.py` proves the physics tick: universal time does not
   change at all across a wait inside a hold, and changes again once released.
 * Measured end to end against `TestServer` with a probe that busy-waits between calls, which is
   where the 5 ticks to 1 above comes from.
