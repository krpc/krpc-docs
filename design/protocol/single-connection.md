# A single bidirectional connection

**Status:** implemented (2026-10-22), not yet in a PR. Planned for 0.8 as a hard break, built
together with [request ids](request-ids.md) phase 1 and [protocol version](protocol-version.md) 2.
Issue drafted in [issues/single-connection.md](../../issues/single-connection.md).

Related: [protocol-compatibility.md](../protocol-compatibility.md) (the 1.0 additivity rules),
[improvements.md](improvements.md) ([#906](https://github.com/krpc/krpc/issues/906)),
[local-transports.md](local-transports.md),
[client-disconnect-cleanup.md](client-disconnect-cleanup.md).

## Problem

A 0.7 client opens two connections, one for RPCs and one for streams (ports 50000/50001, or socket
paths `rpc`/`stream`). SerialIO has only the first, so no streams.

The split exists because `Request` and `Response` carry no id. Correlation is positional, so a
`StreamUpdate` on the same wire could not be told from a `Response`. The split costs:

- `ConnectionRequest.type`, `WRONG_TYPE`, and the GUID echo that pairs the stream connection with
  its RPC client.
- `Core.streamClients` and a stream server class per protocol.
- Two endpoints in the settings, the server editor, the docs and every client.
- A second firewall port, a half-dead state with one socket closed, and the stream-before-RPC races
  each client works around (see "Ordering guarantees").

Each new transport pays it again, as the local socket did in
[PR #1065](https://github.com/krpc/krpc/pull/1065). Client-to-server streams
([#903](https://github.com/krpc/krpc/issues/903)) need an envelope anyway, and become a new `oneof`
case. No real use case needs a connection without streams.

## Decisions

| Decision | Outcome |
| --- | --- |
| Transition | The server moves to protocol version 2 in one step. No version 1 path. |
| Envelope | Every message on every transport, both directions, is a `Message`: a `oneof` of the handshake, `Request`, `Response`, `StreamUpdate` and `Disconnect`. Replaces `MultiplexedRequest`/`MultiplexedResponse`. |
| Request ids | Phase 1 of [request-ids.md](request-ids.md): an id on every `Request`, echoed on its `Response`. |
| Endpoints | One per transport. Port 50000 stays and 50001 goes. The default socket is `krpc.sock` in `XDG_RUNTIME_DIR` or `LOCALAPPDATA`, or `/tmp/krpc-<user>.sock`, in place of `krpc/rpc` and `krpc/stream`. |
| Handshake | `connection_request`/`connection_response` on every transport, after the HTTP upgrade on WebSockets. A `connection_request` mid-session reconnects, through approval. New status `DENIED`, never retried. |
| Ending | Either side may send a `disconnect` with an informational reason. On a socket the sender then half-closes and drains for up to 1 s. |
| Stalls | A message stalled partway ends the connection: 3 s on SerialIO, 30 s elsewhere. |
| Approval | `AutoAcceptConnections` defaults to true for new installs. An existing settings file keeps its value. **Breaking:** changelog entry. |
| Client threads | Callers read the socket in turn, under a reader role. A reader thread reads only while streams are open and no call waits. A dispatcher runs callbacks and the writes a reader queues. |
| Client API | `stream_port`/`stream_path` and counterparts removed, no shims. `rpc_port`/`rpc_path` and counterparts renamed `port`/`path`. A handshake timeout on every connect function but cnano's. |
| SerialIO streams | Unsupported and undefined behavior; no server check. Additive later, after flow control ([draft issue](../../issues/serialio-streams.md)). |

## Protocol

### Message

```protobuf
message Message {
  oneof content {
    Request request = 1;                        // client to server
    Response response = 2;                      // server to client
    StreamUpdate stream_update = 3;             // server to client
    ConnectionRequest connection_request = 4;   // client to server
    ConnectionResponse connection_response = 5; // server to client
    Disconnect disconnect = 6;                  // both directions
  }
}

message Disconnect {
  Reason reason = 1;
  string message = 2;
  enum Reason {
    CLOSED = 0;            // a normal close, or no more specific reason
    SERVER_STOPPED = 1;    // server only
    REMOVED = 2;           // server only: by the player, from the server window
    MALFORMED_MESSAGE = 3;
    PROTOCOL_ERROR = 4;    // a valid message the receiver did not expect
    TIMEOUT = 5;           // a partial message stalled
  }
}

message Request  { uint64 id = 2; repeated ProcedureCall calls = 1; }
message Response { uint64 id = 3; Error error = 1; repeated ProcedureResult results = 2; }
```

- A known case in the wrong direction is a protocol error.
- An unknown case is skipped once a session has started, and logged at debug level by the server.
  During the handshake it is an error.
- Framing is the transport's: a varint length prefix, or one binary WebSocket message (fragments
  allowed).
- `oneof` works on the server's protoc and Google.Protobuf 3.10.1 pin under Mono, and in nanopb and
  lua-protobuf. A set case holding an empty message still encodes.
- Server files alias `KRPC.Schema.KRPC.Message`, as the `KRPC.Server.Message` namespace shadows it.

### Handshake

The server reads one `Message` and answers with a `connection_response`:

| First `Message` | Status, then |
| --- | --- |
| Fails to parse, or any case but `connection_request` | `MALFORMED_MESSAGE`, end |
| A `disconnect` | No response, end |
| None complete within 3 s of accept (TCP accept on WebSockets; never on SerialIO) | `TIMEOUT`, end |
| Stalls partway past the stall timeout | `TIMEOUT`, end |
| No version, or an unsupported one | `WRONG_PROTOCOL_VERSION`, end |
| Denied on approval | `DENIED`, end |
| Approved | `OK`, the session starts |

- Approval has no timeout, and the server writes nothing while it is pending. A client that
  disconnects while pending is dropped, and the approval dialog closes.
- Stopping the server during the handshake or approval sends a `SERVER_STOPPED` `disconnect` in
  place of a `connection_response`.
- Unknown fields in `ConnectionRequest` are accepted, for the `features` list of
  [protocol-version.md](protocol-version.md).
- On WebSockets the upgrade carries no kRPC parameters, and any subprotocol is ignored.

WebSockets fails before a `connection_response` can be framed in two places:

- A bad upgrade gets an HTTP error (400, 404, 405, 426 or 505). An upgrade still incomplete at 3 s
  gets nothing. Either way the server half-closes and drains.
- After the upgrade, a text frame or a framing error in place of the `connection_request` gets a
  close frame (1002, 1003, 1007 or 1009), with no `connection_response`.

The client sends nothing more until the `connection_response`, and gives up after its handshake
timeout: 5 s by default, or none. A `disconnect` ends the attempt with its reason, and any other case
is a protocol error. A refusal raises the client's connection error with the status and message.

A 0.7 client and a 0.8 server always fail to connect, in either direction, often with a misleading
error. The cases are in [protocol-version.md](protocol-version.md) "Per transport".

### Reconnecting

A `connection_request` during a session starts a new one on the same connection, on every
transport. The server reads it in order, once the call before it has completed, so a yielding call
such as `WarpTo` delays it. The old session ends with no `disconnect` and nothing more is written for
it. The new session goes through approval, gets a new GUID, and restarts ids at 1.

This is how a reset serial client, such as an Arduino after a power cycle, gets back in. Bundled
socket clients open a new connection instead.

**A resuming serial client** may meet leftovers of the old session, so it:

- skips `response`, `stream_update` and `disconnect` while it waits;
- treats `MALFORMED_MESSAGE` and `TIMEOUT` as no answer, stays silent until its handshake timeout,
  then retries;
- never retries after `DENIED` or `WRONG_PROTOCOL_VERSION`;
- keeps reading `connection_response`s until the session's first `response`. Retries queue on the
  line while the server is not reading, such as during a scene load, and each starts a session. A
  later `OK` replaces the session, and a later refusal returns to the handshake.

Its handshake timeout, when set, is at least 3.5 s, above the server's 3 s stall timeout. With
`AutoAcceptConnections` off the server answers only after the player approves, so such a user
connects with no timeout. cnano has no timed read, so no timeout and no silent retry (see "Simple
clients").

The reason is serial resynchronization. An Arduino that restarts after sending a length prefix
leaves the server mid-message. Down for 3 s, the stall timeout has already ended the session. Back
sooner, its `connection_request` lands inside the stale message. Either the message stays short and
the server answers nothing, or the parse fails: the server sends a `disconnect`, then refuses the
remainder with `MALFORMED_MESSAGE`.

### Ending a connection

| Cause | Sent by | Reason |
| --- | --- | --- |
| The program closes | Client | `CLOSED` |
| The server stops | Server | `SERVER_STOPPED` |
| The player removes the client | Server | `REMOVED` |
| A `Message` fails to parse, or a request fails to read | Either | `MALFORMED_MESSAGE` |
| A case out of place or in the wrong direction, or an unknown response id | Either | `PROTOCOL_ERROR` |
| A partial message stalls | Either | `TIMEOUT` |

- The reason is informational. The sender writes nothing more, and the receiver ends the connection.
- It is best effort: every receiver handles an end with no `disconnect`.
- The server reads a `disconnect` in order and drops the client, its streams and any held tick. It
  logs `CLOSED` at info, anything else as a warning.
- On a serial port a `disconnect` or a reconnect is the only end the server can see.
- A WebSockets framing error, or a text frame, ends a session with a close frame only (1002,
  1003, 1007 or 1009), with no `disconnect`. A binary frame that fails to parse gets
  `MALFORMED_MESSAGE`. Either way the server drains.

Closing a socket with unread data sends a reset, which can discard a `disconnect` in flight. So the
sender of a `disconnect` writes it, half-closes (`shutdown`, or a WebSocket close frame), reads and
discards until the peer closes for up to 1 s, then closes. The server drains from a closing list it
polls each update. Stopping the server is the exception: it blocks for up to 1 s in total to drain
every connection.

### Partial messages

Once a message's first byte has arrived, if no byte arrives within the stall timeout, the receiver
ends the connection with `TIMEOUT`. This holds on both sides.

| Transport | Stall timeout | Why |
| --- | --- | --- |
| SerialIO | 3 s | Resynchronizes a reset client. Its only timeout. |
| TCP, local socket, WebSockets | 30 s | Catches a dead peer, above TCP retransmission backoff on a lossy link. Applies from the second message; the handshake timeout covers the first. |

- The clock restarts with every byte, and no timeout applies between messages.
- The clock is checked only after a read finds no new bytes, so a game freeze never ends a message
  whose bytes are waiting.

### Removed

| Item | Replacement |
| --- | --- |
| `ConnectionRequest.type`, `ConnectionRequest.client_identifier` | Field numbers reserved |
| `ConnectionResponse.Status.WRONG_TYPE` | Value reserved |
| `MultiplexedRequest`, `MultiplexedResponse` | `Message` |
| Stream listeners, `stream_port`, `stream_path` | None; old settings files' values are ignored |
| Test and benchmark variables `RPC_PORT`, `RPC_PATH`, `PORT`, and TestServer's `--rpc-port`, `--rpc-path`, `--port` | `KRPC_TEST_TCPIP_PORT`, `KRPC_TEST_LOCALSOCKET_PATH`, `KRPC_TEST_SERIALIO_PORT`, and `--tcpip-port`, `--localsocket-path`, `--serialio-port` |
| Server settings `address`, `rpc_port`, `rpc_path`, `port`, `baud_rate`, ... | Prefixed by protocol: `tcpip_address`, `tcpip_port`, `localsocket_path`, `serialio_port`, `serialio_baud_rate`, ... The serial port name and the TCP port shared `port`. Old values are ignored, so a server reverts to defaults |

`ConnectionResponse.client_identifier` stays, the client's GUID bytes as `KRPC.GetClientID` returns
them. The server labels a client in its logs as address plus the lowercase hex of the first 4 wire
bytes, e.g. `127.0.0.1 (a1b2c3d4)`. `Guid.ToString()` would byte-swap the first groups.

### Ordering guarantees

Within one `Core.Update` the call phase writes every response before any stream update, and
`RemoveStream` takes effect at the start of the stream phase. One ordered connection therefore
guarantees:

1. The first update for a stream follows the response to the call that added it.
2. No update for a stream follows the response to the call that removed it.
3. A response follows every update the server wrote before it.

(1) and (2) did not hold over two sockets. Python's machinery for early and late updates (from
[PR #1122](https://github.com/krpc/krpc/pull/1122)) is deleted. (3) is new: a caller returning from
a call sees stream values at least as new as the server state before it.

Exception to (1): a batched `Request` that adds a stream and also yields completes a later update,
so the first update precedes the response and is dropped (Streams rule 3). No bundled client
batches. Fix in Follow-ups.

### Server

- One listener per transport, one `IServer` in `KRPC.Server.Server`.
- `Message.Connection` owns framing, handshake and session state per connection. The byte servers
  accept every connection; approval runs on the `connection_request`.
- Each session is its own client, so a reconnect gets a new GUID with no byte-level reconnect. Core
  keys streams by client and writes updates through the session's `IMessageStream`.
- The server copies ids without validating them. It reads `Request.id` before decoding the calls,
  and `RequestDecodeException` carries it, so a failed decode still answers with the id.
- On TCP a denial now answers `DENIED`; 0.7 closed the socket.

## Client reader

The rules for the clients with streams: Python (the reference), C#, Java and C++. They are the target
for the conformance suite ([client-conformance/spec.md](../client-conformance/spec.md)).

### Threads

| Thread | Does | Never |
| --- | --- | --- |
| Caller | Writes its request, then reads while it holds the reader role | Reads without the role |
| Reader thread | Reads while streams are open and no caller waits | Runs user code, writes |
| Dispatcher | Wakes stream waiters, runs callbacks, makes the writes a reader queues | Reads without the role |

The role holder completes slots, registers streams, stores stream values and queues dispatcher work.
It runs no user code, never writes, and takes no lock user code can hold.

- **No writes**, because callers hold the write lock for a whole blocking write. A reader stuck
  behind a full send buffer would stop draining the server. A reader queues its writes
  (`RemoveStream` for an abandoned stream, a protocol-error `disconnect`) with the dispatcher.
- **No user code**, because an RPC from a callback would wait on its own thread to read the
  response, and an RPC made while holding a stream's condition would block a reader notifying it.
  A blocked callback stalls only other callbacks and waiters.

### Reader role

A flag under the session lock. Callers read their own responses because a reader-thread hand-off
cost 3.5 to 4 us a call.

| Step | Behavior |
| --- | --- |
| Call | Add the slot and take the role if free, in one lock hold. Write, then read until the slot completes. |
| Role taken | Wait until the slot completes or the role frees, then take it if still waiting. |
| Release | Clear the flag and wake waiting callers, or the reader thread if none wait and streams are open. |
| Reader thread | Waits for data with `select` without the role, so callers never queue behind it. |
| No streams | Nothing reads between calls. The next call finds any `disconnect` or end of stream. |
| Close | Take the role and drain for up to 1 s. If a caller holds it, wait for that caller to see the end. |

A `KeyboardInterrupt` can land on a Python caller holding the role. Framing survives, as bytes are
buffered before parsing, but another caller's response being handled can be lost, leaving it waiting.

### Calls

1. Ids are per session, start at 1, and increase by one.
2. The pending slot is added **before** the write, so a fast response finds it.
3. A write lock is held for one whole message, and no lock across a call.
4. The request is written inside its `Message` without building one; a response is parsed straight
   out of it.
5. A caller that stops waiting (interrupt, timeout) abandons its slot, and the response is discarded.
   This fixes Python bug 25 of the client API parity audit ([client-conformance/defects.md](../client-conformance/defects.md)).
6. A response id neither pending nor abandoned is a protocol error.

The handshake runs on the connecting thread before the reader and dispatcher start.

### Streams

1. A slot whose call returns a `KRPC.Stream` or `KRPC.Event` is marked. The reader registers the
   stream untyped on its response, before the next message, so by guarantee (1) no update precedes
   it. If the slot was abandoned, the reader queues a `RemoveStream` instead.
2. An untyped stream keeps its latest result undecoded until a handle gives the type.
3. On a `stream_update` the reader stores each result, then queues the waiter wake-up and callbacks.
   A result for an unregistered id is dropped: a stream removed locally, still in flight.
4. A final result (an error) ends the stream, and the dispatcher runs its end callbacks.
5. The dispatcher runs work in arrival order. A woken waiter reads a value at least as new as the
   update that woke it.
6. Removing through the handle ends the stream locally at once. `KRPC.RemoveStream` through a stub
   leaves the entry until the connection closes.

Values are stored by the reader so that guarantee (3) reaches the caller. Callbacks can lag; values
cannot.

### Failure and close

1. A failed read or write, a protocol error, a stall or a `disconnect` fails the connection. The error
   carries the `disconnect`'s reason and message. Pending slots fail with it, and the dispatcher ends
   every stream and exits.
2. On a protocol error the reader queues a `disconnect`, waits up to 1 s for the dispatcher to write
   it and half-close, drains for up to 1 s, then closes.
3. `close` writes a `CLOSED` `disconnect` unless the write lock takes over 1 s, half-closes, drains as
   under "Reader role", and joins both threads except the one it runs on. It skips the dispatcher
   when the closing thread holds a stream's condition, as a callback may be waiting for it. The
   dispatcher then ends once the condition is released.
4. A call after failure raises the connection error at once.
5. An unknown server exception maps to the client's generic error.

### Per client

| Client | Note |
| --- | --- |
| C# | Keeps the lock order from [PR #1005](https://github.com/krpc/krpc/pull/1005): no stream condition under the update lock. |
| C++ | An atomic flag says whether streams are open, as the map needs its lock. The reader thread checks the read buffer only with the role. |
| Java | Non-blocking after the handshake, as a blocking channel closes on interrupt. Three selectors (role holder, reader thread, a write that fills the send buffer), each capped at 1 s since closing the channel does not wake one. The stall timeout is timed on the read itself. |

### Simple clients

Lua and cnano have no streams and one thread. A call writes its request, then reads until the
`response` with its id. They skip unknown cases, fail the call on a `disconnect`, and treat anything
else as a protocol error (except a `connection_response` before the first `response` on a resumed
serial line). Close sends a `disconnect`, which is how a serial server sees the session end.

| Client | Note |
| --- | --- |
| Lua | A socket timeout only for the handshake, as a luasocket timeout costs about 2 us a call. A stalled message blocks a call. Close half-closes and drains for up to 1 s. |
| cnano | No timed read: no handshake timeout or silent retry, and a refusal returns `KRPC_ERROR_CONNECTION_FAILED` for the program to retry. `krpc_disconnect` sends the `disconnect` and closes (`krpc_close` is the custom transport hook). No half-close. Ids and the resumed flag are file statics. The `oneof` decodes via nanopb's `submsg_callback`, which also re-sets the error decode callbacks nanopb clears. |

### Client API

- Removed: `stream_port`/`stream_path` (Python, C++), `streamPort`/`streamPath` (C#, Java). Old code
  fails as a compile error or a `TypeError`.
- Renamed, as there is one endpoint: `rpc_port`/`rpc_path` to `port`/`path` (Python, C++, Lua),
  `rpcPort`/`rpcPath` to `port`/`path` (C#, Java). Positional arguments are unaffected.
- Added: a handshake timeout on every connect function but cnano's, and `krpc_disconnect` in cnano.
- A refused or ended connection raises the connection error with the status or reason and message.
  `DENIED` is distinguishable.
- The guides say callbacks run on a callback thread and may make RPCs, but must not wait on a stream.

## Per-call latency

`//tools/benchmarks:clients`, version 1 against version 2 on an unpaced TestServer. Ten alternating
pairs, 95% interval of the paired difference. Plain call:

| Client | TCP/IP | Local socket |
| --- | --- | --- |
| Python | +3.4% | -3.6% |
| C# | +1.0% (noise) | +4.5% |
| Java | +7.6% | +4.4% |
| C++ | -0.5% (noise) | +6.5% |
| Lua | +6.8% | +7.1% |
| cnano | +1.0% | +5.0% |

Version 1 plain calls were 12.5 to 19.2 us over TCP/IP and 8.9 to 15.3 us over the local socket.
Calls with arguments track the plain call; lists of 100 are within noise except cnano (+5 to 7%,
decoding through the `Message`).

- A reader thread reading every message cost +26 to +43% in the threaded clients. Hence callers read.
- Java's non-blocking read is `epoll_wait` plus `read`, most of its TCP gap. Lua's is the `Message`
  wrapper.
- The local socket gap appears in cnano too, which has no threads. A raw socket loop puts the server
  and kernel path at +0.3 us there. Cause open.

## Follow-ups

| Follow-up | Proposal |
| --- | --- |
| Streams over SerialIO | [Draft issue](../../issues/serialio-streams.md). Flow control first: a fast stream at 9600 baud fills the write buffer, which drops the connection. |
| Ctrl-C in a Python call on Windows | [Draft issue](../../issues/python-ctrl-c-windows.md). A caller waiting on its slot may not be interruptible. |
| Bounding the dispatcher queue | Unbounded in 0.8. Decide whether to bound it and what to drop. |
| Batched `Request` with a yielding call | Fail a yielding call in a multi-call `Request`, so it completes in the update it is read. No wire change. |
| Residual latency | Left for a later performance pass. cnano is the probe for the local socket gap. |
| Latency with streams open | Not measured. The reader thread can again hand responses to callers. |
