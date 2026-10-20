# Raise the default receive timeout

**Status:** draft issue, not filed. Small, after 0.7.0. Labels: `enhancement`, `server`.

With blocking receives on (the default), the server waits up to `RecvTimeout` for a client's next
call. The default is 1000 us, set in `core/src/Configuration.cs`. A client that takes longer than
that between calls drops from hundreds of calls a second to one per FixedUpdate. The details and
measurements are in [recv-timeout-cliff.md](../design/server/recv-timeout-cliff.md).
`doc/src/internals.rst` already documents the cliff.

1000 us is below the turnaround of a Python or Lua client that does any work per call. 2000 to
3000 us covers most of them.

## Cost

While idle, the server spends up to the timeout of frame time per update. A larger default costs
1 to 2 ms more per frame for every user, including users with no client connected.

## Proposal

* Measure, using the reproduction in the design doc: the idle frame cost at 1000, 2000 and
  3000 us, and the Python and Lua per-call turnaround in the benchmark suite.
* Pick the smallest value that clears the typical Python turnaround. Change the default and the
  "one millisecond" in `internals.rst`.

A default applies only to new installs. `ConfigurationFile` persists `recvTimeout`, so an existing
`settings.cfg` keeps 1000. Say so in the changelog entry.

The per-client "patience" procedure, the other recommendation in the design doc, is larger. It is
in [post-0.7-backlog.md](post-0.7-backlog.md).

## Changelog impact

Server: one entry for the new default.
