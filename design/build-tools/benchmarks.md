# Benchmarks

**Status:** in progress (2026-08-16) - built, restructured, PR not yet raised. The first build was
shaped by [object-lifetime.md](../object-lifetime.md), which is where it came from; it has since
been reorganized around what it is actually for, and given client-side suites. See
[As built](#as-built).
**Issue:** _none yet - needs filing (`krpc/krpc`)._

## Problem

kRPC has no way to measure what a change to it costs. The numbers that decided the object lifetime
design came from a throwaway `[KRPCService]` assembly, hand-built and hand-run, that was deleted
afterwards. That means:

 * Any later change to a hot path is checked against those numbers by re-deriving them by hand, or
   not at all.
 * Absolute timings drift between sessions by more than the differences being measured, and there
   is no baseline or comparison procedure to say whether a change is a result or noise.
 * Nothing measures allocations, which matter more than nanoseconds for frame time in a stream over
   hundreds of parts.
 * Nothing measures a client at all. Four `test_performance` files, one each in the python, csharp,
   java and lua clients, time a hundred calls and print a rate. Nothing measures a stream.

The purpose is **A/B testing**: make a change to the server or a client, and find out what it did.
Everything else follows from that. A benchmark that fails is a benchmark that produced no number,
so nothing here asserts; the report is the output, and comparing two of them is the procedure.

## Structure

Three suites and a comparison tool, one `bazel run` target each.

| Suite | Target | Needs | Measures |
|---|---|---|---|
| Server, game-less | `//tools/benchmarks:testserver` | nothing, seconds | what the server pays per remote procedure call, against `TestServer` |
| Client, python | `//tools/benchmarks:python` | nothing, seconds | round-trip time for a call, and how often a stream arrives |
| Server, in game | `//tools/benchmarks:server` | KSP, minutes | the same per-call cost against real `SpaceCenter` procedures, the object-access microbenchmarks, and stream cost over a few hundred parts |
| A/B | `//tools/benchmarks:compare` | two result files | what moved, and whether it moved by more than the noise |

The split is by what a number is for rather than by how it is taken. A change to `core/` or
`server/` is prototyped against the game-less suite, which runs in seconds, and confirmed against
the in-game one. A change to a service is measured in game. A change to a client is measured by
that client's suite.

## The measurement

Timing happens server side. A benchmark procedure runs an operation in a tight loop and returns
what one iteration cost - nanoseconds, bytes allocated, collections triggered - for one chunk. The
client sizes the chunks, takes several, and keeps the fastest; it never times anything itself, so
no server-side number includes a round trip.

Two kinds of case, and the difference between them is the point:

 * **End to end.** `Benchmark.Call (ProcedureCall call, uint iterations)` looks the procedure up
   once and then loops `Services.ExecuteCall` followed by encoding the result: argument decode,
   dispatch, the procedure, result encode. Everything the server does per request except the
   socket. Because the client names the call - the python client already builds a `ProcedureCall`
   for streams, through `Client.get_call` - **any procedure of any service is measurable with no
   server-side code**. Measuring a new getter is a line of python.
 * **Microbenchmarks.** A registry of named cases inside `TestingTools`, for the operations no
   procedure exposes on its own: the ways of getting from a stable identifier back to a game
   object. These exist to be compared with each other within one session, which is the only
   comparison between them that holds.

`Benchmark` is **an assembly of its own** (`tools/benchmarks/src/`, built as `KRPC.Benchmark.dll`),
not code copied into each host. It is a service like any other, so it is loaded by whichever server
it is installed beside: TestServer references it, and `krpctest`'s installer puts it into `GameData`
next to `TestingTools`. An in-game number and a game-less one are then the same code rather than
two builds of the same source, and both suites call the same `Benchmark.Call`. It does not ship
with the mod - nothing in `//:krpc` lists it.

Two consequences worth recording:

 * **Not a procedure on `TestService`.** `TestService` is a fixture: its exact member list is
   asserted by the python and lua client tests, and its definitions drive the clientgen golden
   files for every language, so a procedure added to it churns all of those and then sits in them
   forever. A separate service touches none of it, and needs no clientgen either, since a client
   with no pre-generated stubs builds a service from the definitions the server hands over on
   connecting. What it does cost is one line in each client test that asserts the full set of
   services a connection exposes.
 * **TestServer has to touch it before the scan.** Services are found by walking the assemblies
   the runtime has loaded, and nothing in TestServer calls into the benchmark service, so it
   would never be loaded. One statement naming a type from it, before the server starts, is
   enough. The game has no such problem: KSP loads every assembly in `GameData`.

The microbenchmarks stay in `TestingTools`, since they reach into KSP and SpaceCenter internals
that a game-less assembly cannot see. They time their cases with `Benchmark`'s timer, which is
public for exactly that, so their numbers are in the same units as its.

Five pieces of hygiene are what make the numbers mean anything:

| Concern | Handling |
|---|---|
| Dead-code elimination | Every case accumulates its result into a `static volatile` sink. Without this the JIT hoists the read out of the loop; the 0.3 ns/op measured for a captured `module.name` is about one cycle, which is what a hoisted loop looks like, not what a property read costs. |
| Dispatch overhead | A delegate call and loop bookkeeping cost single-digit nanoseconds, which is not negligible against a 36 ns target. Each microbenchmark registry includes an `empty` case with the identical delegate shape, subtracted from the rest. The end-to-end cases have none: hundreds of nanoseconds against single digits, and no delegate shape to match. |
| JIT warmup | A warmup pass (a few thousand iterations, or 50 ms, whichever comes first) before the timed loop, discarded. Mono compiles on first call. |
| Frame jitter | Nothing pauses. The timed loop runs on the game's main thread inside the server's update, so physics and rendering cannot interleave with it however long it takes; and against a server configured with `pauseServerWithGame` pausing deadlocks the suite, since the server stops answering the RPC that would unpause it. |
| Blocking the game | Chunks are sized to about 200 ms. A multi-second RPC stalls the game and perturbs the server's adaptive `MaxTimePerUpdate`, which then feeds back into later measurements. |

### Allocations

Bytes per operation, measured around the same loop with
`GC.GetAllocatedBytesForCurrentThread`, which is exact and unaffected by collections. The Mono KSP
ships does provide it; the `GC.GetTotalMemory(false)` fallback is there for a runtime that does
not, and is untested in practice. Which was used is reported alongside the figure, and a chunk
taken with the coarse method that spans a collection is discarded and retried smaller.

Not the Unity profiler API: it is restricted in non-development players, so it would report
differently in a real KSP install than in a dev build.

The two kinds of case mean different things by an allocation figure. A microbenchmark measures an
operation on its own, so zero bytes is a claim it can be held to. An end-to-end case encodes a
reply, which allocates whatever the reply is made of, so its figure is the whole call's and is
never zero; what it is good for is noticing that it moved. This is a change from the first build,
where whole getters were measured without the encode and did report zero - the accessor tables in
[object-lifetime.md](../object-lifetime.md#measured) are from that build and say zero for the same
getters.

### Reading a result

The fastest sample is the estimate. The distribution is one sided - interference only ever makes a
sample slower - so the minimum is the best available answer and everything above it is the machine
getting in the way.

The reported **spread** is how far the *median* sample ran above the fastest, not the slowest. A
case that allocates triggers a collection in nearly every run, so one sample is always far out;
that says nothing about how far the estimate can be trusted, and measured against the max it made
every allocating case look untrustworthy. Against the median the spread tracks the run-to-run
reproducibility, which on one machine is about 3%.

`compare` marks a change only when it exceeds both the spread either run showed and a 3% floor.
Comparing two runs of an unchanged build reports nothing, which is also how to establish what a
given machine's floor actually is.

## Client benchmarks

Against `TestServer`, started by the runner itself: the python client's suite launches the
executable, reads the ephemeral ports out of its log and connects, so a run needs nothing
installed and nothing running.

| Case | Measures |
|---|---|
| `round trip` | `TestService.FloatToString` in a hot loop: latency, and the call rate it works out to |
| `round trip, 3 arguments` | `AddMultipleValues`, so argument encoding separates from the round trip |
| `stream interval, N streams` | how long a client waits between updates of one stream, with N running, for N of 1, 10 and 100 |
| `stream evaluation, N streams` | what the server spends on one pass over all N, from `time_per_stream_update` |

`TestService.Counter` increments every time it is called, so a stream over it carries how many
times the server has evaluated it; counting increments over a window measures updates that
actually arrived rather than how often the client thought to look. Each stream gets its own
counter, since streams over identical calls are the same stream.

The two stream figures answer different questions, and both are needed. A stream arrives once per
server update however cheap it is, so the interval is pinned to 16.7 ms at every N the suite
measures - that is what a program written against kRPC sees, and it only moves once the server
cannot keep up. What the server spends is the number that moves with every change to the
evaluation path, and so the one worth comparing between runs.

Every client figure is a time per operation, so lower is always better in every table; the rates
they work out to are notes under the block. `TestServer` runs a 60 Hz update loop and the server's
adaptive rate control bounds how much of an update goes to RPCs, so the report carries
`one_rpc_per_update`, `max_time_per_update`, `adaptive_rate_control`, `blocking_recv` and
`recv_timeout` in its header: two runs taken under different settings are not comparable.

A run warms up for a second before measuring anything. Without it the first case measured came out
*slower* than the second, because the rate control was still adapting to the load.

Python is the first client. The others follow the same shape: each emits the same rows, and the
four `test_performance` files they have today are superseded as each lands.

## In-game suite

Written exactly like the tests in `service/*/test/`: `krpctest.TestCase` subclasses that set up
their state in `setUpClass` and measure in `test_` methods, so the scene helpers (`new_save`,
`launch_vessel_from_vab`, `remove_other_vessels`, `set_circular_orbit`) come for free. Craft files
sit in `tools/benchmarks/server/craft/`, which `TestCase._stage_craft` resolves relative to the
test module. `pytest.ini` points a bare run at the service test directories, so the suite is only
collected when it is named, which is right for one that takes minutes.

Two scenarios, one script each, because each sets up different state:

| Scenario | Why |
|---|---|
| `Parts.craft`, 58 parts in flight, reused from the SpaceCenter tests | the per-access scenario: the cheapest scene to reason about, and every case runs here |
| `Station300.craft`, a pod carrying 320 cubic octagonal struts | five times the parts, so what is linear in loaded parts separates from what is flat |

| Case | Kind | What it isolates |
|---|---|---|
| `part.name`, `part.mass` | end to end | a trivial getter where resolution dominates, and a KSP-dominated one where it is a small slice |
| `module.name`, `module.part` | end to end | the path most sensitive to how a proxy resolves |
| `engine.thrust`, `parachute.state`, `part.engine` | end to end | concrete module proxies, read through and constructed |
| `vessel.parts.all` | end to end | bulk proxy construction, object-store dedup and encoding |
| `resolve.captured`, `resolve.cached`, `resolve.cached_bare`, `resolve.find_part_by_id` | micro | getting from a flight id back to a part: a captured reference, the shipped cache, the barest weak-reference cache, and the linear scan |
| `module.indexed`, `module.by_persistent_id`, `module.ref`, `module.by_name_scan` | micro | getting from a part back to one of its modules |
| `module.of_type_to_list` | micro | the allocating LINQ pattern a concrete proxy can use to collect its modules |
| `store.dedup` | micro | what returning an already-known proxy costs, over a private store holding one entry per part |
| `stream update` | scene | `time_per_stream_update` with one stream per part: the realistic workload, server side, no round trip |

## As built

Where the implementation differs from what was first designed:

| Design | As built | Why |
|---|---|---|
| a per-getter case registry in C# | one `BenchmarkCall` taking a `ProcedureCall`; the registries keep only the object-access primitives | measuring a getter stopped needing a mod rebuild, and the eight hand-written whole-getter cases went with it. `BenchmarkModule` and its registry went too: a module getter is a call like any other |
| entry points typed on the object under test | still true of the microbenchmarks; `BenchmarkCall` is typed on the call | the proxy is decoded before timing starts either way |
| the suite asserts allocations, A/B ordering and a per-case ceiling | it asserts nothing | 29 ceilings across three scripts, guessed rather than derived, and a run that fails is a run that produced no table. Allocations are a reported column, and the A/B relations they asserted are read off the table |
| server-side benchmarks only | plus a `Benchmark` service loaded by both servers, and a client suite | a game-less run is seconds against 90+, which is the difference between prototyping a server change and not; and nothing measured a client |
| a `TestingTools`-only `Benchmark.cs` | an assembly of its own that both servers load | shared source compiled into two assemblies was the first shape; one assembly is a real dependency instead of a `<Compile Include="..\...">` in two `.csproj`s, and makes the two hosts run the same code rather than two builds of it |
| results reported through a pytest fixture | a module-level list, and a shared `report.py` the three runners print through | pytest cannot inject fixtures into `unittest`-style test methods, and the client suites are not pytest at all |
| a multi-vessel scenario, three copies of the reference craft | dropped | the station shows the same linear scan, and the three-vessel numbers fell on the same line |
| spread as max over min | median over min | see [Reading a result](#reading-a-result) |
| `--benchmark-json`, diffed by hand | `--json` and a `compare` target | a by-hand diff of two files of numbers is not a procedure anyone follows |
| `TestingTools` became a `partial` class, and `core` gained `InternalsVisibleTo` | also for `KRPC.Benchmark` | a benchmark procedure has to be a member of a `[KRPCService]` class, and dispatch through `Services` is internal to core |
| object-store sweep case | `store.dedup`, over a private store pre-filled with one entry per part | there is no sweep until object-lifetime's core infrastructure phase; the dedup path is what exists to measure |
| 300+ part station | `Station300.craft`: a pod carrying 320 cubic octagonal struts | a fixture, not a spacecraft |

Two things the harness learned the hard way, both now asserted or commented in place: a stream the
client has added but never read is not started, and the server skips it, so a stream case has to
start its streams explicitly and check the server's stream count and rate before believing the
reading; and a benchmarked call that fails comes back as a result carrying an error, which costs
about what any other result costs, so `BenchmarkCall` makes the call once outside the loop and
raises rather than quietly reporting the price of failing.

The runs that decided the object lifetime design are tabulated in
[object-lifetime.md](../object-lifetime.md#measured), the design that asked for the suite. They are
recorded there rather than here because they are that design's own before-and-after, not a property
of the tool, and nothing in this repo is a committed baseline. The case names they use survive this
restructure, so those tables still say what they said.

## Decided

 * **Benchmarks live in `tools/benchmarks/`, not under `service/*/test/`.** They are not service
   tests, and a suite that takes minutes has no business in the default sweep.
 * **Nothing asserts.** A/B around a change is the whole procedure. A benchmark that can fail is a
   benchmark that sometimes produces no number, which is the one thing it must not do.
 * **Nothing is retained between runs.** No committed baseline and no result history: a timing only
   means something on the machine and in the session that produced it.
 * **The end-to-end case is named by the client.** Adding a server-side case is for operations no
   procedure exposes; everything else is a line of python.
