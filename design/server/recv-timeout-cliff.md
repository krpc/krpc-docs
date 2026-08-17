# The receive timeout throughput cliff

**Status:** investigation. No issue or PR yet. Two adaptive schemes were tried and measured as
negative results; a recommendation is below.

## Summary

A client whose own work between calls exceeds the server's **receive timeout** (`RecvTimeout`,
1000 us by default) drops from hundreds or thousands of calls a second to exactly one per
FixedUpdate, 60 a second. The step is abrupt: 50 us more work on the client side costs a factor
of ten in throughput.

The cause is not a bug. The receive timeout is what stops the server spending a whole frame
waiting on a client that has nothing to say. The problem is the shape of the failure: it is a
cliff rather than a slope, it is silent, and it lands where a python or lua program lands easily.

## Mechanism

`RPCServerUpdate` in `core/src/Core.cs` alternates between polling for requests and executing
them, for up to `MaxTimePerUpdate` (10000 us by default):

 * The poll is a **spin** on `stream.DataAvailable`, not a blocking socket read. It gives up
   after `RecvTimeout`.
 * When a poll gives up, `if (rpcContinuations.Count == 0) break` leaves **the whole update**,
   not just that poll. The rest of `MaxTimePerUpdate` goes unused.
 * So each update holds at most one timed out poll. A client that answers within `RecvTimeout`
   is served over and over inside one update; a client one microsecond slower is served once
   per update, and waits a whole frame for its next turn.

Waiting is unavoidable for a synchronous client. The reply goes out during the update, the
client's next request can only be received during an update, so throughput above one call per
frame exists only for as long as the server is willing to sit and wait for the client inside a
single update. Moving the receive off the game thread would not change this: the request would
be queued sooner, but it could still only be executed in the next update.

## How it was measured

A probe client against `TestServer` (the game-less server, same core, same 60 Hz update loop),
busy-waiting a controlled gap after each reply so that the client's turnaround is the only
variable, and reading the server process's CPU time from `/proc` to price the waiting. Server
variants were built by patching `core/src/Core.cs` behind an environment variable.

The `server core` column is the fraction of a core the server process used. At 60 Hz, 1.00 means
every frame was fully consumed. It stands in for the frame time kRPC takes from the game.

## What it costs today

No other work in the frame, so the whole 16.6 ms is available to kRPC:

| client gap | calls/s | ms per call | server core |
|---|---|---|---|
| idle, no calls | - | - | 0.19 |
| 0 us | 41500 | 0.024 | 0.90 |
| 600 us | 1016 | 0.98 | 0.70 |
| 900 us | 653 | 1.53 | 0.69 |
| **950 us** | **661** | **1.51** | 0.70 |
| **1000 us** | **61** | **16.32** | 0.15 |
| 2000 us | 61 | 16.39 | 0.16 |
| 16000 us | 61 | 16.39 | 0.16 |

Note the CPU column below the cliff. A client with a sub-millisecond turnaround already makes
the server spend **most of its update budget spinning**, 0.7 of a core. The receive timeout is
not protecting the frame from a slow client; it is protecting it from an absent one.

## Options measured

Two variants, both against a server given 8000 us of simulated physics work per frame, so that
`AdaptiveRateControl` sees a realistic frame and the frame cost is visible:

| client gap | today (recv 1 ms) | recv 3 ms | poll to the update budget |
|---|---|---|---|
| idle, no calls | 0.68 core | 0.79 core | **1.04 core** |
| 1000 us | 61 calls/s | 557 calls/s | 559 calls/s |
| 2000 us | 61 | 287 | 287 |
| 5000 us | 61 | 61 | 116 |
| 16000 us | 61, 0.64 core | 61, 0.76 core | **58, 0.99 core** |

Reading the table:

 * **Raising `RecvTimeout` moves the cliff** to the new timeout and costs that much frame time
   per update whenever nothing is calling. The idle cost is exactly linear in the window:
   +2 ms of timeout measured as +0.11 core, which is 2/16.6.
 * **Polling to the update budget removes the cliff** and gives a smooth slope instead
   (throughput settles at about `MaxTimePerUpdate / gap` calls per frame). It costs the whole
   frame: with an idle client connected the server saturates at 1.04 core, and adaptive rate
   control drags `MaxTimePerUpdate` down from 10000 to 8900 us trying to recover.
 * The bottom row is the case against it. For a client that calls once a frame, which is what a
   control loop does, polling to the budget buys **no throughput at all** (58 vs 61 calls/s,
   frames now overrunning at 17.1 ms) and takes the entire frame to do it.
 * Everything `recv 3 ms` misses is the 3 ms to 10 ms band. That band costs a full frame to
   serve.

## Negative results

Both attempts to tell a slow client from an absent one without paying for the wait failed, for
the same underlying reason.

 * **Estimate the client's turnaround** (time from response sent to next request received) and
   size the poll window from it. This locks in. Once the server has given up on a client, it
   only notices the next request at the start of the following frame, so the measured turnaround
   is ~16 ms whatever the client actually took. The estimate is polluted by the server's own
   inattention, the window stays short, and the cliff stays exactly where it was. Measured:
   identical to today's numbers at every gap.
 * **Grow the window when a wait pays off, shrink it when it does not.** Does not converge. A
   client served once a frame produces exactly one payoff (the request already waiting at the
   start of the frame) and one miss per frame, so the doubling and the halving cancel and the
   window stays wherever it started. Measured: identical to polling to the budget, including the
   full frame cost.

The reason both fail: **the server cannot distinguish a slow client from an absent one without
waiting long enough to find out**, and that wait is the whole cost. Any scheme that learns the
difference has to pay for it, either continuously or by probing.

## Recommendation

A control loop, which is the shape that suffers most, has since been given a way out:
[holding a physics tick](tick-hold.md) lets a client keep the game on one tick while it computes,
so its reads and writes land in the same tick instead of one call per tick. That does not change
anything below, which is about what the server does for a client that has not asked for a hold.

In order of cost:

1. **Document the cliff.** `doc/src/internals.rst` already explains blocking receives and the
   receive timeout accurately, but not the consequence: if your client takes longer than the
   receive timeout between calls, you get one call per frame, and the fix is to raise the
   timeout or to stop making sequential calls. This is the whole fix for a user who hits it and
   has no idea why their program became twenty times slower.
2. **Consider a larger default.** 1000 us is below the turnaround of a python or lua client
   doing any real work per call. 2000 or 3000 us would cover most of them, at 1 to 2 ms of
   frame time per update while idle. This is a real cost paid by every user, including those
   with no client connected, so it is a judgment call rather than an obvious win.
3. **Let the client say it is coming back.** The information the server is missing is held by
   the client, which knows whether it is mid-sequence. A per-client patience value, set through
   a new procedure on the `KRPC` service (`CallContext` already identifies the caller, so this
   needs no protocol change), would let a program that does 2 ms of work per call ask to be
   waited for, and cost nothing to every program that does not. Better still as a per-request
   hint, since the promise then expires on its own and a client that stops calling costs one
   window rather than every frame, but that is a protocol change.
4. **Batch.** The protocol already carries several calls in one request, but no client exposes
   it. A program reading twenty values one at a time pays twenty round trips and hits this cliff
   with any of them; the same twenty in one request pay one. This is the real answer for the
   workload that suffers most, and it is a client-side change with no frame time cost at all.
   See also [server-side functions](../server-side-functions/server-side-functions.md), which
   attacks the same problem from the other end.

Not recommended: polling to the update budget unconditionally. It trades a cliff that costs a
slow client for a permanent tax on every frame, and it does not help the once-a-frame client at
all.

## Reproducing

Patch the poll loop in `core/src/Core.cs` behind an environment variable, build
`//tools/benchmarks:python`, run `TestServer` from its runfiles tree on a fixed port, and drive
it with a client that busy-waits a controlled gap between calls. `RPC_PORT` and `STREAM_PORT`
make the benchmark runners target a server that is already running
(`tools/benchmarks/testserver.py`).

The client benchmarks in `client/*/benchmark.*` deliberately sit on the fast side of the cliff
so that they measure the client rather than the frame rate. Raising the list size in
`client/lua/benchmark.lua` from 100 to 500 pushes the lua client over it, which is how this was
first noticed.

That the suite has to stay clear of the cliff at all is a problem of its own, and it has a fix
that needs nothing from the server: see
[frame pacing and the round trip](../build-tools/benchmarks.md#frame-pacing-and-the-round-trip).
Unpacing `TestServer` removes the cliff from the measurement without touching the receive
timeout, because the timeout only bites when the next update is a frame away.
