# Raise the default receive timeout

Milestone: 0.8.0 · Labels: enhancement, server

A client that takes longer than `RecvTimeout` between calls drops from hundreds of calls a second to one per FixedUpdate. The default is 1000 us (`core/src/Configuration.cs`), which is below the turnaround of a Python or Lua client doing any work per call. 2000 to 3000 us covers most of them, at a cost of 1 to 2 ms of frame time per update while idle.

Measure the idle frame cost at 1000, 2000 and 3000 us, and the Python and Lua per-call turnaround in the benchmark suite. Pick the smallest value that clears the Python turnaround, and update `doc/src/internals.rst`. An existing `settings.cfg` keeps its value, which the changelog entry should say.

Design: [recv-timeout-cliff.md](https://github.com/krpc/krpc-docs/blob/main/design/server/recv-timeout-cliff.md)
