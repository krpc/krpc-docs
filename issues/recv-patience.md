# Let a client ask the server to wait longer for its next call

Milestone: none · Labels: enhancement, server

With blocking receives, the server waits up to `RecvTimeout` for a client's next call, and a client slower than that gets one call per FixedUpdate. Raising the default (#<recv-timeout-default>) costs every user frame time. A procedure on the `KRPC` service that sets this client's receive patience would let a client doing 2 ms of work per call ask to be waited for, at no cost to other clients. `CallContext` identifies the caller, so this needs no protocol change.

Batching (#903) is the other answer for the same workload.

Design: [recv-timeout-cliff.md](https://github.com/krpc/krpc-docs/blob/main/design/server/recv-timeout-cliff.md), option 3 under "Recommendation".
