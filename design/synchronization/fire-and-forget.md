# Fire-and-forget requests (issue #903)

**Status:** proposal, design agreed (2026-07-03), not started. Planned for 1.0. Revised
2026-10-21 for the 0.8 single connection and features negotiated in the handshake. The second of
the three #903 designs, see the [index](README.md#how-calls-reach-a-tick).

## Context

* **Responses are written at one place**, `client.Stream.Write(response)` in
  `Core.ExecuteContinuation`, which is the seam for a no-response flag.
* **The gain is smaller since [non-blocking calls](non-blocking-calls.md).** A submitted call whose
  future is never read already costs the caller nothing. The flag saves the response bytes and the
  reader's work, which matters most on SerialIO.

## Design

**Schema**: `bool no_response = 3` on `Request`, beside `calls = 1` and `id = 2`. Request-level,
not per-call, since mixed batches would need partial responses.

**Server**: thread the flag through `Messages.Request` → `RequestContinuation`;
`ExecuteContinuation` skips `client.Stream.Write (response)` when set.
Errors from no-response requests are logged at info level and otherwise dropped.
Execution is unchanged — same FIFO ordering, same tick budget, same per-client queue
(a burst of pipelined fire-and-forget requests drains within ticks).

**The fence idiom** (document): because execution is FIFO per client, a subsequent
*normal* RPC's response confirms that all prior fire-and-forget requests have executed —
a free flush/barrier. A call marked for out-of-order completion
([request-ids.md](../protocol/request-ids.md) phase 3) is not covered by the fence.

**Version skew — the one hazard**: an older server ignores the unknown field and writes a
`Response` the client does not expect. Client libraries therefore ask for the
`no_response` feature in the handshake, and raise a clear "server too old" error on first
use if it was not granted. The rule is in
[protocol-version.md](../protocol/protocol-version.md) under "Additive changes". Old client + new
server is trivially fine.

**Client APIs**: an option on a batch send (`batch.send(no_response=True)`,
`b.Send(noResponse: true)`), which also covers the single-call case.

## Documentation

`doc/src/communication-protocols/messages.rst`: `no_response` semantics, the fence idiom and the
handshake feature. Client docs: the batch send option.

## Tests

- **Fire-and-forget**: no-response setter observed applied via a subsequent read (the
  fence); ordering across a mix of no-response and normal requests; gating against a
  server that grants no features.

## Implementation order

1. Schema, server, handshake feature.
2. The client batch option and the "server too old" error.
3. Docs, then `CHANGELOG.md` entries as the final pre-merge commit.
