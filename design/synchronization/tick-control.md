# Tick control

**Status:** proposal, design open. The planned replacement for [the tick hold](tick-hold.md), under
[#251](https://github.com/krpc/krpc/issues/251). Planned for 1.0. This doc gathers the problem, the
facts and the constraints. It has no design decisions yet.

## Problem

A program has three questions about the game's physics ticks, and kRPC answers one of them:

| Question | Today |
| --- | --- |
| Which tick do my calls run in? | `HoldTick` and `NextTick`, the 0.7 stopgap |
| Where in the tick do my calls run? | Always at one point, before the game's own scripts. Only the auto-pilot can choose ([update-timing.md](update-timing.md)) |
| How many calls per tick? | As many as the time budget allows. #251 asks for one call, or one batch, per tick |

The second question came up in review of [#1245](https://github.com/krpc/krpc/pull/1245), per
thruster RCS control. A fly-by-wire program reads the pilot's input, computes thruster levels and
writes them. Inside a held tick it reads the input of the previous tick. The game collects pilot
input after the server has run the tick's calls.

## The KSP tick

Read from the `Assembly-CSharp` IL, KSP 1.12.5. One frame runs zero or more fixed steps, then
`Update`.

| Point | What runs | Order fixed by |
| --- | --- | --- |
| Frame start | Unity samples keyboard and joystick input for the frame | Unity |
| Fixed step, first | kRPC `Addon.FixedUpdate`: the tick's calls, the auto-pilot step, then stream updates | `[DefaultExecutionOrder (-100)]` |
| Fixed step | `FlightInputHandler.FixedUpdate`: reads the axis bindings into `FlightInputHandler.state`, then for each loaded vessel `FeedInputFeed` raises `OnPreAutopilotUpdate`, `OnAutopilotUpdate`, `OnPostAutopilotUpdate` and `OnFlyByWire`, and sets `Vessel.ctrlState` | Default order |
| Fixed step | Part module `FixedUpdate`s. `ModuleRCS` fires from inputs it latched in `Update`. `ModuleGimbal` runs its adjuster here | Default order |
| Fixed step, end | Physics step | Unity |
| `Update` | `FlightInputHandler.Update` handles toggles only (staging, gear, lights, precision mode). `ModuleRCS.Update` reads `ctrlState` and latches its input | Default order |

So a write lands in the tick it is made in, and a read of the pilot's input sees the previous
tick. `FlightInputHandler` and the part modules share the default order, so Unity does not fix
which runs first. Execution order alone cannot place code after input and before the parts.

KSP has its own staging inside a fixed step: `TimingManager.TimingStage`, from `ObscenelyEarly` to
`BetterLateThanNever`, run by the `TimingPre`, `Timing0` to `Timing5` and `TimingFI` components.
Where `FlightInputHandler` and the part modules fall among those stages is not yet measured.

KSA has no `FixedUpdate`. Its server runs from a Harmony prefix on
`Universe.ExecuteNextVehicleSolvers` ([../ksa/server.md](../ksa/server.md)). Phase names have to
describe both games' ticks.

## Constraints

* **Opt in per connection, defaults untouched**, and the tick hold procedures deprecated rather than
  removed. See "Breaks at the service level" in
  [protocol-compatibility.md](../protocol-compatibility.md).
* **The server owner bounds the freeze.** Every hold takes `TickHoldTimeout`, for the reasons in
  [tick-hold.md](tick-hold.md).
* **One holder at a time**, for the livelock reason in [tick-hold.md](tick-hold.md).
* **Streams, reverse streams and function streams** take a placement in the tick too, not only
  calls. See open question 4 of [reverse-streams.md](reverse-streams.md).

## Open questions

1. **Phases.** Which points to expose, and under what game-neutral names. Candidates: before input,
   after input and before the parts, after physics.
2. **Reaching a point.** `TimingManager` stages, a `FeedInputFeed` callback, or a Harmony patch.
   Holding inside a game callback blocks the game mid-tick, which the current hold never does.
3. **Choosing a phase.** Per connection, per hold, or per call. One program may want two: read
   after input, write before the parts.
4. **#251's ask.** One call or batch per tick as a connection mode, and how it relates to a hold
   that is taken every tick.
5. **The auto-pilot's update mode.** Whether `AutoPilot.UpdateMode` becomes a phase like any other.

## Next step

Measure the `TimingManager` stages against `FlightInputHandler.FixedUpdate` and the part modules
in game, stamping `Time.fixedTime` at each point, as [update-timing.md](update-timing.md) did for
the server and `OnFlyByWire`.
