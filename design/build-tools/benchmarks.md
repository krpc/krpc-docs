# Server-side benchmarks

**Status:** in progress (2026-07-25) - built as designed, PR not yet raised. See
[As built](#as-built) for where the implementation differs. Split out of
[object-lifetime.md](../object-lifetime.md), which is its first consumer, so the benchmarks can be
designed and built independently of that work. They are its last two phases, and land as a pull
request of their own after the behavior change.
**Issue:** _none yet - needs filing (`krpc/krpc`)._

## Problem

kRPC has no way to measure the cost of a server-side accessor. The numbers that decided the object
lifetime design came from a throwaway `[KRPCService]` assembly, hand-built and hand-run, that was
deleted afterwards. That means:

 * Any later change to a hot path is checked against those numbers by re-deriving them by hand, or
   not at all.
 * Absolute timings drift between KSP sessions by more than the differences being measured, and
   there is no baseline or comparison procedure to say whether a change is a result or noise.
 * Nothing measures allocations, which matter more than nanoseconds for frame time in a stream over
   hundreds of parts.

The hot path is real: a stream over a few hundred parts re-evaluates its accessors every fixed
update, so a per-access regression of tens of nanoseconds, or a single allocation, shows up as frame
time in game.

## Approach: benchmarks are integration tests

A benchmark needs exactly what an in-game test needs: the mod built and installed, KSP launched, a
save loaded, a craft on the pad, and an RPC connection. That is `tools/krpctest`, and it already
does all of it. So the benchmarks are **not** a separate tool; they are integration tests that
happen to measure instead of assert, and the only genuinely new thing is the timing loop itself.

 1. **The timing RPCs go in `TestingTools`.** It is already a `[KRPCService]`, already references
    core, server and SpaceCenter, is already built by Bazel, already excluded from `//:krpc`, and is
    already installed into `GameData` by `install.py` on top of the extracted release archive. A new
    `src/Benchmark.cs` needs one `<Compile Include="…" />` line in `TestingTools.csproj`; the
    `BUILD.bazel` `srcs` is a glob, and `install.py` copies whatever `cquery` reports, so neither
    changes.
 2. **The benchmark scripts go in `tools/benchmarks/`,** written exactly like the tests in
    `service/*/test/`: `krpctest.TestCase` subclasses that set up their state in `setUpClass` and do
    the work in `test_*` methods. `bazel run //:test-ingame -- tools/benchmarks/ -v` runs them,
    because `run_tests.py` chdirs to the invocation directory and passes its arguments straight to
    pytest, so any path works. `pytest.ini` sets `testpaths = service/*/test`, so they are **not**
    collected by a bare `bazel run //:test-ingame`: opt-in, which is right for a slow suite.
 3. **Craft files go in `tools/benchmarks/craft/`.** `TestCase._stage_craft` already resolves the
    craft directory relative to the test module's own file, so `launch_vessel_from_vab("Station300")`
    finds it with no framework change at all.

State setup uses the helpers that already exist: `new_save`, `launch_vessel_from_vab`,
`remove_other_vessels`, `set_orbit`, `set_circular_orbit`, `set_landed`, `set_flight`,
`fill_all_resources`. This replaces the idea of shipping pre-built scenario saves. A craft file plus
a few lines of setup is the framework's existing idiom, is diffable, and cannot go stale against a
KSP version the way a `.sfs` can.

### What actually has to be built

| Piece | Where | Size |
|---|---|---|
| timing and allocation RPCs, case registry | `tools/TestingTools/src/Benchmark.cs` (+ one `.csproj` line) | the only real new code |
| benchmark scripts | `tools/benchmarks/*.py` | like any test file |
| craft | `tools/benchmarks/craft/*.craft` | fixtures |
| result recording, reporting | `tools/benchmarks/conftest.py` | a fixture and a `pytest_terminal_summary` hook |
| pylint config and lint target | `tools/benchmarks/pylint.rc`, `tools/benchmarks/BUILD.bazel` | copy of the `py_lint_test` in `service/SpaceCenter/BUILD.bazel` |

Nothing else: no new assembly, no new Python package, no new `py_binary`, no `install.py` step, no
`//:krpc` exclusion to arrange, and no second way to launch the game.

The cost of putting the RPCs in `TestingTools` is that benchmark code is present in every in-game
test session. It is a static registry that nothing calls unless a benchmark asks for it, so the
runtime cost is zero; the real coupling is that `TestingTools` gains references to whatever
internals a case measures.

## The timing RPCs

Entry points are typed on the object under test, so the proxy is decoded before timing starts:

```
TestingTools.BenchmarkPart   (Part part,     string case, uint iterations) -> IDictionary<string,double>
TestingTools.BenchmarkModule (Module module, string case, uint iterations) -> IDictionary<string,double>
TestingTools.BenchmarkVessel (Vessel vessel, string case, uint iterations) -> IDictionary<string,double>
```

Each returns the metrics for **one chunk**: nanoseconds per operation, bytes allocated per operation,
and the GC collection count delta. A dictionary rather than a `[KRPCClass]` because a class would
put a proxy in the object store on every call, which is one of the things being measured; and it can
gain a metric without a signature change.

The case is a delegate in a registry inside `Benchmark.cs`, invoked in a tight loop under a
`System.Diagnostics.Stopwatch`. Chunking, repeats and aggregation are the script's job, in Python.
The measured work all happens inside one RPC, server side: the client picks the objects and names
the case, and never times anything itself.

Five pieces of hygiene are what make the numbers mean anything:

| Concern | Handling |
|---|---|
| Dead-code elimination | Every case accumulates its result into a `static volatile` sink. Without this the JIT hoists the read out of the loop; the 0.3 ns/op measured for a captured `module.name` is about one cycle, which is what a hoisted loop looks like, not what a property read costs. |
| Dispatch overhead | A delegate call and loop bookkeeping cost single-digit nanoseconds, which is not negligible against a 36 ns target. Every suite includes an `empty` case with the identical delegate shape, and results report both raw and empty-subtracted timings. |
| JIT warmup | A warmup pass (a few thousand iterations) before the timed loop, discarded. Mono compiles on first call. |
| Frame jitter | Time with the game paused (`KRPC.Paused`) wherever the case allows, so physics and rendering are not competing for the frame. Cases that require an unpaused sim are marked and reported separately. |
| Blocking the game | The script sizes chunks so no single RPC runs for more than a few hundred milliseconds. A multi-second RPC stalls the game and perturbs the server's adaptive `MaxTimePerUpdate` (`core/src/Core.cs:374-390`), which then feeds back into later measurements. |

Report min and median over repeats rather than the mean, with the spread, since the distribution is
one-sided: interference only ever makes a sample slower.

## Measuring allocations

Bytes per operation, measured around the same loop:

 * Preferred: `GC.GetAllocatedBytesForCurrentThread()`, which is exact and unaffected by
   collections. Availability under KSP's Mono is not guaranteed, so probe for it by reflection once
   and report which method was used.
 * Fallback: the delta in `GC.GetTotalMemory(false)` across the loop, divided by the iteration
   count. Coarse per operation, but over a million iterations even four bytes per operation is four
   megabytes, far above the noise floor. That is enough for the question being asked, which is "is
   this path allocation free", not "how many bytes exactly".
 * Either way, return `GC.CollectionCount(0)` before and after. A collection inside the window makes
   a `GetTotalMemory` delta meaningless (memory was also freed), so a chunk with a non-zero
   collection delta is discarded and retried at a smaller iteration count. A path that cannot
   complete the loop without triggering a collection has already failed any allocation budget.

Do not use the Unity profiler API for this. It is restricted in non-development players, so it would
report differently in a real KSP install than in a dev build.

## What a benchmark asserts

Running under pytest raises the question the standalone-tool design ducked: a test passes or fails,
but a measurement is a number, and absolute nanoseconds depend on the machine. Splitting by what is
machine-independent settles it:

| Measurement | Machine-independent? | Treatment |
|---|---|---|
| bytes per operation, collections triggered | yes, it is a count | **assert**: a fast path claiming to be allocation free fails the test at one byte per operation |
| A/B between two cases in the same session | yes, same build, same session, same frame | **assert** the relationship the design claims (e.g. indexed lookup beats the by-name scan) |
| empty-subtracted ns/op for one case | no | **record and report**; assert only a loose sanity ceiling (below) |
| ns/op against a previous session's run | no, sessions drift | **record**; compared by hand between a run before a change and a run after it |

So the assertions are about ratios and counts, and the timings are output. `conftest.py` collects
every recorded metric and prints a table in `pytest_terminal_summary`, with `--benchmark-json=PATH`
to write the same data so two runs can be diffed. A failing benchmark then means something
structural broke (an allocation appeared, a strategy got slower than the one it replaced), not that
the machine was busy.

### The sanity ceiling

Each case declares a `max_ns` in its script, set to **5x** the value the case is expected to
produce, and the benchmark fails above it. The multiple has to survive a slow machine under load,
which is a factor of two or three, and still catch a regression worth catching. The gap it is aimed
at is wide: the `OfType<T>().ToList()` path the object-lifetime work removes measured ~1770 ns
against ~36 ns for an indexed lookup, roughly 50x, and the difference between a cached and an
uncached resolve is a similar shape. So 5x sits well clear of noise and well below anything that
matters.

This is a guess. It is a per-case constant in Python, so raising one that cries wolf, or dropping
the ceiling entirely if it turns out to fail more often than it catches anything, is a one-line
change.

## Comparing across builds

Comparing two implementations means two sets of DLLs, so a KSP restart, and absolute timings drift
between sessions. In the object-lifetime measurements a cached-reference helper beat a hand-inlined
weak reference in one session and lost in another, both times by more than the difference being
measured. Two things follow:

 * **Put the primitives in the benchmark service.** Where the thing being compared is a small
   strategy (a plain `FindPartByID`, a weak-reference cached resolve, an indexed module lookup, a
   by-name module scan), implement each as a case in `Benchmark.cs`. That measures them against each
   other in one session on one build, which is drift free, and makes the comparison assertable per
   the table above. This is where component-level numbers should come from.
 * **Whole-getter numbers stay cross-build.** The procedure is A/B by hand around a change: run the
   suite on the unmodified build, run it again on the modified one, diff the two result files.
   Nothing is retained between changes, and no baseline is committed, since a baseline is only
   meaningful on the machine and in the session that produced it. Treat a difference smaller than
   the session-to-session drift seen on the unchanged build as no result.

## Suite

Per-consumer: a design that wants a budget enforced adds its cases and its script. The initial set
comes from [object-lifetime.md](../object-lifetime.md):

| Case | What it isolates |
|---|---|
| `part.mass` | a KSP-dominated part getter, where resolution is a small slice |
| `part.name` | a trivial part getter, where resolution dominates |
| `module.name` | a trivial module getter, the path most sensitive to how a proxy resolves |
| `engine.thrust`, `parachute.state` | concrete module proxies, including the ones that use `OfType<T>().ToList()` |
| resolution primitives | the in-session A/B described above |
| `vessel.parts.all` | bulk proxy construction and object-store dedup, which the accessor cases never touch |
| object-store sweep | sweep cost as a function of store size |
| stream update | `time_per_stream_update` from `KRPC.GetStatus` with N streams over N parts: the realistic workload, server side, no round trip. Sample only after the reading settles, since it is an exponential moving average (`core/src/Core.cs:267-268`) |

Scenarios are one script per craft, since each sets up different state: the reference craft
(`Parts.craft`, reused from the SpaceCenter tests, 58 parts in flight), a 300+ part station, and a multi-vessel scene
with several loaded vessels. The last two exist specifically because part lookup by id is linear in
loaded parts, which a single small craft cannot show.

## As built

The suite is `tools/TestingTools/src/Benchmark.cs` plus `tools/benchmarks/`
(`harness.py`, `conftest.py`, one script per scenario, `Station300.craft`), run with
`bazel run //:test-ingame -- tools/benchmarks/`. Where it differs from the design above:

| Design | As built | Why |
|---|---|---|
| a new `Benchmark.cs` plus one `.csproj` line | also `TestingTools` became a `partial` class, and `core` gained `InternalsVisibleTo("TestingTools")` | procedures have to be members of the `[KRPCService]` class; the store case measures the real `KRPC.Service.ObjectStore` rather than a copy of it |
| time with the game paused | nothing pauses | the timed loop runs on the game's main thread inside the server's update, so physics and rendering cannot interleave with it anyway; and against a server configured with `pauseServerWithGame` (which the local KSP install was) pausing deadlocks the suite, since the server stops answering the RPC that would unpause it |
| object-store sweep case | `store.dedup`, over a private store pre-filled with one entry per part | there is no sweep until object-lifetime's core infrastructure phase; the dedup path is what exists to measure, and is the other store cost that work has to not regress |
| multi-vessel scene | three copies of the reference craft, spaced 500 m apart on one orbit | no new craft needed, and the point is the number of *loaded vessels* the scan walks |
| 300+ part station | `Station300.craft`: a pod carrying 320 cubic octagonal struts in 40 stacks | a fixture, not a spacecraft |
| results recorded through a pytest fixture | a module-level list in `harness.py` | pytest cannot inject fixtures into `unittest`-style test methods; `conftest.py` keeps the `pytest_terminal_summary` hook and `--benchmark-json` |
| report min and median over repeats, with the spread | one number per case on the terminal - the fastest sample with the empty loop subtracted - in a block per scenario, with the allocation figure beside it | median, spread, every sample and the iteration count are in `--benchmark-json`, so the terminal can be the answer rather than the working: the spread appears as a note under the block, and only for a case noisy enough to doubt, and the empty case is the range it was subtracted from rather than a row of its own |
| ceiling of 5x the expected value | 5x, with a floor of 50 ns | five times a 4 ns case is inside the noise of subtracting the empty case |

Two things the harness learned the hard way, both now asserted or commented in place: a stream
the python client has added but never read is not started, and the server skips it, so the
stream-update case has to start its streams explicitly and check the server's stream rate before
believing the reading; and the allocation figures come from
`GC.GetAllocatedBytesForCurrentThread`, which the Mono KSP ships does provide, so the
`GetTotalMemory` fallback is untested in practice.

Both gaps left open for [object-lifetime.md](../object-lifetime.md) are now closed by its
SpaceCenter benchmarks phase, which measures what its infrastructure phases ship:

 * `resolve.cached` was a stand-in written to the shape that design proposes. It now goes
   through the cache the service layer ships, so the case says what a part getter pays rather
   than what a copy of it would.
 * `resolve.cached_bare` was added beside it: the same idea with nothing added - no game-state
   stamp, typed on the part rather than shared - so the two are measured against each other in
   one session and the price of what the shipped cache guarantees is a number rather than an
   assumption. Nothing measures a delegate-based helper against a hand-inlined one; that
   refinement still rests on the throwaway measurements alone, and is a case if it ever needs
   evidence.

The runs, `main` and after each phase, are tabulated in
[object-lifetime.md](../object-lifetime.md#measured), the design that asked for the suite.
They are recorded there rather than here because they are that design's own before-and-after, not a
property of the tool, and nothing in this repo is a committed baseline.

One thing that run corrected: the reference craft is 58 parts in flight, not the 62 the earlier
measurements were described against. The scenario labels are built from the part count the scene
actually reports, so a report cannot claim a count the craft does not have.

## Decided

 * **Benchmarks live in `tools/benchmarks/`, not under `service/*/test/`.** They are not service
   tests, and a suite that takes minutes has no business in the default sweep. The cost is a
   directory pytest only reaches when named, which is the intent.
 * **Nothing is retained between runs.** A/B around a change is the whole procedure; there is no
   committed baseline and no long-lived result history to keep current.
 * **The sanity ceiling is 5x the expected value per case**, guessed rather than derived, and tuned
   or dropped once there is evidence either way.
