# A single bidirectional connection

**Status:** proposal — sketch (2026-07-21), revised 2026-08-27 against `main` at version 0.7.0.
No issue filed yet.

Related: [request-ids.md](request-ids.md) (the same client refactor — read
these two together), [improvements.md](improvements.md) (meta-issue
[#906](https://github.com/krpc/krpc/issues/906)),
[local-transports.md](local-transports.md),
[client-api-parity-audit.md](../client-api-parity-audit.md).

## Since the sketch

Four things landed in `krpc` that bear on this design. None of them start it, and two enlarge it.

- **A local socket transport** ([PR #1065](https://github.com/krpc/krpc/pull/1065),
  [local-transports.md](local-transports.md)) copies the two-connection arrangement wholesale, as a
  pair of socket paths. That is a third transport carrying the workaround, and a third place the
  eventual removal has to reach.
- **A sixth client, cnano**, ships without streams. There are now two clients that already use one
  connection, and four that would need the demultiplexing reader.
- **Tick holding** ([PR #1070](https://github.com/krpc/krpc/pull/1070),
  [tick-hold.md](../server/tick-hold.md)) gives a control loop several calls inside one physics
  tick, as a stopgap for [#251](https://github.com/krpc/krpc/issues/251). It makes per-call latency
  the number that a control loop feels, which the demultiplexing reader adds a thread hand-off to.
  See the open questions.
- **Client disconnect cleanup** merged ([PR #934](https://github.com/krpc/krpc/pull/934)), so the
  half-dead two-socket state is now handled rather than open. Consolidation deletes the state
  instead.

## The v1.0 rewrite as a whole

This connection change is one component of the v1.0 protocol rewrite — a single breaking wire format
carrying message ids and async messages, client-to-server streams, batching/transactions, tick
control ([#251](https://github.com/krpc/krpc/issues/251)), and the stream and event rework. The
components land together because they share the wire format.

| Component | Issue | Design |
| --- | --- | --- |
| Single bidirectional connection | none yet | this doc |
| Message ids / async messages | none yet | [request-ids.md](request-ids.md) |
| Client-to-server streams | [#903](https://github.com/krpc/krpc/issues/903) | [reverse-streams.md](reverse-streams.md) |
| Batching / transactions | [#903](https://github.com/krpc/krpc/issues/903) | [reverse-streams.md](reverse-streams.md) |
| Tick control — one RPC/batch per physics update | [#251](https://github.com/krpc/krpc/issues/251) | [tick-hold.md](../server/tick-hold.md) ships an RPC-level stopgap; the protocol design is still open |
| Stream freezing removal | [#901](https://github.com/krpc/krpc/issues/901) | [stream-freezing-removal.md](stream-freezing-removal.md) |
| Stream refcounting | [#902](https://github.com/krpc/krpc/issues/902) | [stream-refcounting.md](stream-refcounting.md) |
| Stream invalidation | [#877](https://github.com/krpc/krpc/issues/877) | [stream-invalidation.md](stream-invalidation.md) |

Every issue in that table is still open.

Two questions to settle before any of it starts:

- **One change or a sequence?** The components share a wire format, but stream refcounting (#902),
  stream invalidation (#877) and stream freezing removal (#901) are separable and already designed
  against the *current* protocol, so they could ship earlier if v1.0 turns out to be distant.
- **What compatibility is offered during the transition?** Whether the server speaks both formats
  during a transition, or v1.0 is a hard break with every client updated in lockstep. That answer
  sets the scope of the client work, which is six clients wide and is the bulk of the effort.

## Problem

A kRPC client opens two connections: one to the RPC endpoint and one to the stream endpoint. Every
transport that can carry two of them does. They are configured as two servers, wrapped in a `Server`
façade that starts, stops and updates the pair and reports `Running` only when both are up
(`core/src/Server/Server.cs:99-122`, `:145-147`).

| Transport | RPC endpoint | Stream endpoint |
| --- | --- | --- |
| Protocol buffers over TCP | `rpc_port`, 50000 | `stream_port`, 50001 |
| Protocol buffers over websockets | `rpc_port` | `stream_port` |
| Protocol buffers over a local socket | `rpc_path`, `krpc/rpc` | `stream_path`, `krpc/stream` |
| Protocol buffers over serial | the one port | none — see below |

All four are built in one method (`core/src/Configuration.cs:95-140`).

**This is not a design decision about streams. It is a workaround for the absence of request
ids.**

`Request` and `Response` (`protobuf/krpc.proto:36-57`) have no id field. Correlation is
positional: the server refuses to read a second request from a client while one is in flight
(`core/src/Core.cs:912`), and the client assumes the next bytes on the socket are its response.
Given that, there is no way to distinguish a `Response` from a server-initiated `StreamUpdate`
arriving on the same wire — so the two message kinds were given a socket each. The second socket
*is* the discriminator.

Everything else follows from that choice and exists only to serve it:

- `ConnectionRequest.Type` (`RPC`/`STREAM`) and the `WRONG_TYPE` status
  (`protobuf/krpc.proto:11-32`).
- A server-allocated 16-byte GUID per client (`core/src/Server/TCP/TCPClient.cs:17`,
  `core/src/Server/LocalSocket/LocalSocketClient.cs:18`), returned on the RPC connection
  (`core/src/Server/ProtocolBuffers/Utils.cs:152`), echoed back by the client in the stream
  connection's `ConnectionRequest.client_identifier`, length-checked
  (`core/src/Server/ProtocolBuffers/StreamServer.cs:45-46`) and cross-referenced against live RPC
  clients to decide whether to allow the connection (`core/src/Server/Server.cs:85-94`).
- Two endpoints in the settings file (`server/src/ConfigurationFile.cs:35-36`) and two fields per
  transport in the in-game server editor (`server/src/UI/EditServer.cs:177-182`, `:197-202`,
  `:301-308`).
- Two connections to document per transport, in `doc/src/communication-protocols/tcpip.rst`,
  `websockets.rst` and `localsocket.rst`.

Websockets and local sockets inherit the arrangement unchanged. A transport that is natively
bidirectional and message-framed, and a transport whose endpoint is a path on the same machine,
both nonetheless open a second connection and repeat the GUID handshake.

## What the split actually buys

One real thing, worth stating before arguing against it: **a client that never uses streams needs
no reader thread and no demultiplexer.** It can be naively blocking — send a `Request`, read a
`Response`. Streams cost a thread only if you use them, and that thread is neatly isolated behind
its own socket.

Lua and cnano are the existence proof: neither has a stream manager, both open only the RPC
endpoint, and both are entirely synchronous. C++, Python, C# and Java each spawn a dedicated update
thread when streams are in play (`client/cpp/src/stream_manager.cpp:29`,
`client/python/krpc/client.py:194`, `client/csharp/src/StreamManager.cs:22`).

This property should survive consolidation — see "Simple clients" below. It very nearly does, for
free.

## The case for consolidating

**The envelope already exists in the schema.** `MultiplexedRequest`/`MultiplexedResponse`
(`protobuf/krpc.proto:277-285`) discriminate message kinds on a single wire, and
`MultiplexedResponse` already reserves a `stream_update` field. SerialIO uses this today to tell
`ConnectionRequest` from `Request` (`core/src/Server/SerialIO/RPCStream.cs:20-49`,
`core/src/Server/SerialIO/RPCServer.cs:33-55`).

**Server-side merging is nearly free.** `Core.Update()` already calls `RPCServerUpdate()` then
`StreamServerUpdate()` sequentially on the same game thread (`core/src/Core.cs:399-401`), and
stream updates are written inline on that thread (`core/src/Core.cs:638`). There is no writer
thread to reconcile and no server-side lock to redesign; the two writes would simply target the
same socket.

**It deletes a class of bugs and a chunk of surface.** No GUID minting, echoing, length-checking
or cross-referencing. No half-dead state where one socket has closed and the other has not, which
[`client-disconnect-cleanup.md`](client-disconnect-cleanup.md) had to work out how to reason about.
No stream-connects-before-RPC race. No second port to open in a firewall, forward through NAT, or
explain in the docs, and no second socket path to place and clean up.

**Each new transport pays for the split again.** The local socket transport
([PR #1065](https://github.com/krpc/krpc/pull/1065)) is the most recent bill: a second server
instance, a second configurable path, a second field in the server editor, and a docs section
explaining the second connection and the GUID it carries. Its own design doc
([local-transports.md](local-transports.md)) notes that it copies the arrangement rather than
choosing it.

**Client-to-server streams force multiplexing anyway.**
[#903](https://github.com/krpc/krpc/issues/903)
([reverse-streams.md](reverse-streams.md)) adds streams flowing the other way:
registered by ordinary RPCs, but with their updates pushed by the client. Those updates have
nowhere to go except the RPC connection — a third socket for them would be absurd — so that
connection must start discriminating a client stream update from a `Request`. **The
client→server direction therefore needs an envelope whether or not this design happens.**

That makes the current arrangement actively incoherent as soon as #903 lands: server→client
streams on their own socket, client→server streams multiplexed onto the RPC socket, and two
different mechanisms for what is one concept. Consolidating first makes #903 a new field in an
envelope that already exists in both directions, rather than a new multiplexing mechanism
invented for one direction. It also lets both stream directions share one registration,
lifetime, refcounting ([#902](https://github.com/krpc/krpc/issues/902)) and invalidation
([#877](https://github.com/krpc/krpc/issues/877)) model instead of two.

**It is the honest transport model.** Websockets should be one connection because that is what
websockets is. SerialIO has exactly one channel and must multiplex regardless.

## The SerialIO precedent, stated accurately

SerialIO is the natural place to point for "we already do this", and the pointer is half right —
so be precise about which half, because the docs currently are not.

The envelope works and is proven for connection-request/RPC discrimination. But **streams have
never worked over SerialIO.** `core/src/Server/SerialIO/StreamServer.cs:14` constructs its base
with a `NullServer`, which never fires connection events, and `CreateClient` throws
unconditionally (`:21-24`). Nothing anywhere populates `MultiplexedResponse.stream_update` — not
in `core/src/Server/SerialIO/`, not in `client/serialio/`.

`doc/src/communication-protocols/serialio.rst:105-112` nonetheless documents receiving stream
updates over the serial connection as `MultiplexedResponse` messages with `stream_update` set.
That section is aspirational and describes behavior that does not exist. Its own example script
(`doc/src/scripts/communication-protocol-serialio.py`) only exercises the handshake and a
`GetStatus` call.

**This is a shipped-docs bug independent of this design, and should be fixed on its own** — either
by deleting the section or marking it unimplemented. Do not let it wait on consolidation. It is
still unfixed as of 0.7.0.

The correct reading of the precedent: the envelope design is sound and partly proven, the slot is
reserved, and implementing streams over SerialIO would fall out of this work rather than
motivating it.

## Sketch

Reuse the existing envelope rather than inventing one. Both directions become a single message
type carrying a oneof:

```protobuf
message MultiplexedRequest {
  ConnectionRequest connection_request = 1;
  Request request = 2;
  StreamUpdate stream_update = 3;               // later, for #903
}

message MultiplexedResponse {
  Response response = 1;
  StreamUpdate stream_update = 2;
  ConnectionResponse connection_response = 3;   // new
}
```

Whether to convert these to a proto3 `oneof` is an open question below.

The client→server `stream_update` is not part of this work — it belongs to
[#903](https://github.com/krpc/krpc/issues/903) — but the envelope should be shaped with it in
mind, since that is the slot #903 would otherwise have to invent for itself.

Negotiated at connection time, exactly as [`request-ids.md`](request-ids.md) proposes for in-flight depth:

- Add a field to `ConnectionRequest` (e.g. `bool single_connection`, absent = today's two-socket
  behavior) and have `ConnectionResponse` report what the server granted. An old server ignores
  the field and reports nothing, which is indistinguishable from a refusal — so the client learns
  whether it must still dial the stream endpoint.
- On a granted single connection, the server sends stream updates down the same socket and the
  stream listener is simply never contacted by that client.
- The stream endpoint stays configurable and its listener keeps running until the two-socket path
  is eventually retired. Nothing existing breaks.

`AddStream`/`RemoveStream` are ordinary RPCs and stay ordinary RPCs; only the *delivery* of
`StreamUpdate` moves.

## Client reader loops

This is the whole cost of the change, and the reason to sequence it with request ids.

Today a client's calling thread owns the RPC socket and blocks on it, while a separate daemon
thread owns the stream socket. Merged, one owner reads the socket and dispatches by message kind:
`stream_update` goes to the stream manager, `response` goes to the caller waiting for it.

That is **the same demultiplexing reader** [`request-ids.md`](request-ids.md) describes for pipelining
(that doc's "Client APIs" section). The difference is only what the reader keys on — message kind
here, request id there — and both want the same structure: one socket owner, a table of pending
work, and callers that wait on a future rather than on a `recv`.

**Doing these as two projects means writing that reader twice, in four clients.** The C#
lock-ordering deadlock fixed in [PR #1005](https://github.com/krpc/krpc/pull/1005)
(`client/csharp/src/StreamManager.cs`) is a fair sample of what that concurrency rework
costs when it goes wrong — and Java and Python had already needed the same fix. Pay it once.

Per client:

- **Python** — the reader thread already exists (`client/python/krpc/streammanager.py:241`); it
  gains response dispatch and the client loses `_rpc_connection_lock`
  (`client/python/krpc/client.py:154`), under which a yielding RPC currently blocks every thread.
- **C#, Java, C++** — `StreamManager`'s thread becomes the connection's reader; the RPC path
  changes from "write then read" to "write then await".
- **Lua, cnano** — no stream support, so nothing to demultiplex. See below.

Tick holding does not complicate the reader. A stream update is produced in `StreamServerUpdate`,
which runs after the update's calls, so no stream update is written while a client holds a tick.
What tick holding does change is how much a per-call latency increase costs, which is the open
question below.

### Simple clients

The "no streams, no thread" property is preserved *by construction*: a client that never calls
`AddStream` never receives a `StreamUpdate`, so a naive send-then-read loop remains correct on a
single connection. The client must only be prepared to see a `MultiplexedResponse` envelope
instead of a bare `Response`, which is a decode change, not a concurrency one.

So the cost is conditional on using streams — the same condition as today. Lua and cnano stay
synchronous and single-socket; they just speak the envelope. Arduino/serial clients keep working
the way they already do.

## Migration

1. Fix the SerialIO docs (independent, do now).
2. Add `connection_response` to `MultiplexedResponse`; negotiate `single_connection` on
   `ConnectionRequest`/`ConnectionResponse`. Server supports both paths.
3. Move clients to the demultiplexing reader, one at a time, alongside the request-ids work.
4. Implement streams over SerialIO, which now costs almost nothing.
5. Only once every bundled client negotiates single-connection: deprecate `stream_port` and
   `stream_path`, then remove the second listener on all three transports, the GUID handshake,
   `ConnectionRequest.Type` and the `WRONG_TYPE` status. This is a **breaking** change and wants
   its own release cycle and changelog marker.

Steps 2–4 are additive and backwards compatible in both directions. Step 5 is the only break, and
it can be deferred indefinitely.

## Open questions

- **What the demultiplexing reader costs per call.** Today a calling thread writes a request and
  blocks on `recv` for its response. Merged, it hands off to a reader thread and waits on a future,
  which adds a wakeup to every RPC. [Tick holding](../server/tick-hold.md) made per-call latency
  the number a control loop feels — a held tick is real time in which no physics runs — so measure
  the added latency against a hold loop before committing the client rework.
- **Head-of-line blocking between the two message kinds.** One socket means a large `StreamUpdate`
  can delay a `Response` and vice versa. Interleaving is at message boundaries so the delay is
  bounded by one message, but a client that stops reading now stalls both kinds rather than one.
  Is that ever worse in practice than today's independent stalls? Probably not — a client that has
  stopped reading is broken either way — but it deserves a measurement with a large stream set.
- **Should the envelope be a proto3 `oneof`?** Semantically correct and self-documenting, but it
  changes the generated API in every language and the existing messages are not `oneof`s. Weigh
  against leaving them as optional fields and validating that exactly one is set.
- **Envelope overhead.** Every message gains a tag and length prefix. Negligible for TCP and for a
  local socket, possibly not for SerialIO at 9600 baud with a fast stream. Measure before
  implementing step 4.
- **Does the negotiation belong on `ConnectionRequest` at all**, or should a single connection just
  be the behavior of a *new* protocol version? A version field would carry request ids too, and
  avoid accumulating one negotiated boolean per protocol change. This is the more important
  question of the two and should be settled jointly with [`request-ids.md`](request-ids.md).
- **Interaction with stream refcounting ([#902](https://github.com/krpc/krpc/issues/902)) and
  invalidation ([#877](https://github.com/krpc/krpc/issues/877)).** Both are keyed on the stream
  client's identity, which under consolidation is the same object as the RPC client. Should
  simplify those rather than complicate them — confirm.
- **`Server.Running` and the in-game UI.** Currently reports the pair; the status display and
  `EditServer` both assume two endpoints, in both the port form and the socket-path form. Decide
  what the UI shows during the migration when a server is listening on both but some clients use
  one.
