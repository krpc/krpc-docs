# Synchronization design docs

How a client program's calls line up with the game's physics ticks: which tick they run in, where
in the tick, and how they get there. These are design records. The `krpc` docs are the source of
truth for shipped behavior, mainly `user-guide/control-loops.rst` and
`user-guide/server-performance.rst`.

## The tick, in brief

The server runs in the game's fixed step, ahead of the game's own scripts. Each update executes
calls, polling for more for up to `RecvTimeout` at a time and `MaxTimePerUpdate` in all, then sends
stream updates. Execution is FIFO per client and round-robin across clients. All the calls in one
`Request` run in one update, and a blocking call's response means every earlier call from that
client has run. [tick-control.md](tick-control.md#the-ksp-tick) maps where the game's own work
falls in the tick.

## Which tick

| Doc | Status | Covers |
| --- | --- | --- |
| [tick-hold.md](tick-hold.md) | Done, [#1070](https://github.com/krpc/krpc/pull/1070) | `HoldTick`, `ReleaseTick` and `NextTick`: a client keeps the game on one tick while it computes, and takes consecutive ticks. A stopgap |
| [tick-control.md](tick-control.md) | Proposal, design open | The replacement under [#251](https://github.com/krpc/krpc/issues/251): which tick, where in it, and how many calls per tick |

## Where in a tick

| Doc | Status | Covers |
| --- | --- | --- |
| [update-timing.md](update-timing.md) | Done, [#1070](https://github.com/krpc/krpc/pull/1070) | `AutoPilot.UpdateMode`: the auto-pilot's loop runs before or after the tick's calls, or when the client says. Pins the server ahead of the game's scripts |
| [tick-control.md](tick-control.md) | Proposal, design open | The same choice for a program's own calls, and the KSP tick map it needs |

## How calls reach a tick

| Doc | Status | Covers |
| --- | --- | --- |
| [recv-timeout-cliff.md](recv-timeout-cliff.md) | Investigation, done | Why a client slower than `RecvTimeout` gets one call per tick, two negative results, and the options |
| [non-blocking-calls.md](non-blocking-calls.md) | Proposal, not started | `submit` futures and client batches. Client APIs only |
| [fire-and-forget.md](fire-and-forget.md) | Proposal, not started | `Request.no_response`, negotiated in the handshake |
| [reverse-streams.md](reverse-streams.md) | Proposal, not started | A registered call whose arguments the client pushes, applied at most once per tick, latest wins |

The last three are [#903](https://github.com/krpc/krpc/issues/903), tracked as one issue and
planned for 1.0. Each ships on its own, in the order listed, and each makes the next smaller.

## Related docs elsewhere

| Doc | Covers |
| --- | --- |
| [server-side-functions.md](../server-side-functions/server-side-functions.md) | `RunFunction` runs read, compute and write within one tick. A function stream does it every tick |
| [yielding-procedures.md](../server-side-functions/yielding-procedures.md) | Functions that call procedures taking several ticks |
| [request-ids.md](../protocol/request-ids.md) | Pipelining (phase 2) and out-of-order completion (phase 3). Keeps the one-update guarantee of a multi-call `Request` |
| [stream-freezing-removal.md](../protocol/stream-freezing-removal.md) | Reads from one tick: function streams in place of freezing |
| [protocol-compatibility.md](../protocol-compatibility.md) | The rules each 1.0 item follows, tick control included |
| [deferred-state-rpc-audit.md](../services/deferred-state-rpc-audit.md) | Setters the game only acts on in a later update, which no placement in the tick fixes |
