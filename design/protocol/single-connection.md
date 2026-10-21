# A single bidirectional connection

**Status:** proposal, ready to implement (revised 2026-10-21). Planned for 0.8 as a hard break, built
together with [request ids](request-ids.md) phase 1 and
[protocol version](protocol-version.md) 2. Issue drafted in
[issues/single-connection.md](../../issues/single-connection.md).

Related: [request-ids.md](request-ids.md) (built alongside this),
[protocol-version.md](protocol-version.md), [protocol-compatibility.md](../protocol-compatibility.md)
(the 1.0 additivity rules this design must keep), [improvements.md](improvements.md) (meta-issue
[#906](https://github.com/krpc/krpc/issues/906)), [local-transports.md](local-transports.md),
[client-disconnect-cleanup.md](client-disconnect-cleanup.md).

## Decisions

| Decision | Outcome |
| --- | --- |
| Transition | None. The server moves to protocol version 2 in one step, with no version 1 path kept, and the clients follow on the same branch (see "Phases"). |
| Message type | One protobuf type, `Message`, a `oneof` of the handshake, `Request`, `Response`, `StreamUpdate` and `Disconnect`. Every message on every transport is a `Message`, in both directions. Replaces `MultiplexedRequest` and `MultiplexedResponse`. |
| Handshake | A `connection_request` `Message` and a `connection_response` `Message`, on every transport, after the HTTP upgrade on WebSockets. Nothing else is accepted before a successful response. A `connection_request` during a session reconnects, on every transport, and goes through connection approval like any other. |
| Ending a connection | Either side may send a `disconnect` with a reason before it ends a connection. Its reason is informational, and the receiver must handle an end without one. On a socket the sender then half-closes and drains for up to 1 second, so the `disconnect` is not lost to a reset. The server answers a `connection_request` it refuses with a `connection_response` instead. A connection denied on approval gets the new status `DENIED`, and a client does not retry it. |
| Partial messages | A message that stalls partway ends the connection: after 3 seconds on SerialIO, 30 seconds on TCP, the local socket and WebSockets. |
| Connection approval | `AutoAcceptConnections` defaults to true, for new installs. An existing settings file keeps its value. |
| Request ids | Phase 1 of [request-ids.md](request-ids.md) lands with this: an id on every `Request`, echoed on its `Response`. |
| Client threads | A reader thread that never runs user code and never writes, and a dispatcher thread that runs callbacks and makes the writes the reader asks for. See "Client reader". |
| Endpoints | One per transport. Port 50000 and the `rpc` socket path stay. Port 50001 and the `stream` path go. |
| Client API | `stream_port`, `stream_path` and their counterparts are removed from every client. Connecting without streams is no longer an option. |
| Streams over SerialIO | Unsupported on this branch, and undefined behavior if used. The server does not check for them. Additive later, and needs flow control first ([draft issue](../../issues/serialio-streams.md)). |

## Problem

A kRPC client opens two connections: one to the RPC endpoint and one to the stream endpoint. The
server wraps the pair in `KRPC.Server.Server`, which starts, stops and updates both and reports
`Running` only when both are up.

| Transport | RPC endpoint | Stream endpoint |
| --- | --- | --- |
| Protocol buffers over TCP | `rpc_port`, 50000 | `stream_port`, 50001 |
| Protocol buffers over websockets | `rpc_port` | `stream_port` |
| Protocol buffers over a local socket | `rpc_path`, `krpc/rpc` | `stream_path`, `krpc/stream` |
| Protocol buffers over serial | the one port | none, streams are unavailable |

All four are built in `Configuration.Server.Create` (`core/src/Configuration.cs`).

**The split is a workaround for the absence of request ids.** `Request` and `Response` carry no id.
Correlation is positional: the server reads no second request from a client while one is in flight
(`pollRequestsCurrentClients` in `Core.PollRequests`), and the client takes the next message as its
response. A `Response` and a `StreamUpdate` on one wire could not be told apart, so each got a
socket. The second socket is the discriminator.

Everything below exists only to serve it:

- `ConnectionRequest.type` (`RPC`/`STREAM`) and the `WRONG_TYPE` status.
- The client GUID echo: returned in `ConnectionResponse.client_identifier` on the RPC connection,
  sent back in `ConnectionRequest.client_identifier` on the stream connection, length-checked in
  `ProtocolBuffers.StreamServer.CreateClient` and matched against live RPC clients in the `Server`
  constructor.
- `Core.streamClients`, `StreamClientConnected`/`StreamClientDisconnected`, and the stream server
  classes for each protocol under `core/src/Server/{Message,ProtocolBuffers,WebSockets,SerialIO}`.
- Two endpoints in the settings file (`server/src/ConfigurationFile.cs`) and two fields per
  transport in the server editor (`server/src/UI/EditServer.cs`).
- Two connections to document per transport in `doc/src/communication-protocols/`.

**The GUID itself stays.** It is the client's identity for `KRPC.GetClientID`, `Core.rpcClients`
and the tick hold, and the server still returns it in the handshake (see "Client identifier"). Only
the echo goes.

## The case for consolidating

- **The envelope is proven.** `MultiplexedRequest`/`MultiplexedResponse` already discriminate message
  kinds on SerialIO, and `MultiplexedResponse` reserves a `stream_update` field. `Message` replaces
  both.
- **The server merge is small in `Core`.** `Core.Update` runs `RPCServerUpdate` then
  `StreamServerUpdate` on the game thread, and both write inline. The two writes simply target one
  socket. The cost is in the message layer, where the stream server, client and stream classes for
  each protocol fold into the RPC ones.
- **It deletes a class of bugs.** No GUID echo, no half-dead state with one socket closed, no
  stream-connects-before-RPC race, no second port to open in a firewall, no second socket path.
- **Each transport paid for the split again.** The local socket transport
  ([PR #1065](https://github.com/krpc/krpc/pull/1065)) copied it wholesale.
- **Client-to-server streams need an envelope anyway.**
  [#903](https://github.com/krpc/krpc/issues/903) ([reverse-streams.md](reverse-streams.md)) pushes
  updates up the RPC connection, which must then tell a push from a `Request`. Enveloping both
  directions now makes #903 a new `oneof` case, and keeps it additive on protocol version 2.
- **It removes a race the clients work around.** See "Ordering guarantees".

The split lets a client with no streams run no reader thread. Lua and cnano keep that (see "Simple
clients"). No real use case needs a connection without streams.

## Protocol

### Message

```protobuf
message Message {
  oneof content {
    Request request = 1;            // client to server
    Response response = 2;          // server to client
    StreamUpdate stream_update = 3; // server to client
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

message Request {
  uint64 id = 2;
  repeated ProcedureCall calls = 1;
}

message Response {
  uint64 id = 3;
  Error error = 1;
  repeated ProcedureResult results = 2;
}
```

- **One type for both directions.** `Message` names no direction, so client stream pushes for
  [#903](https://github.com/krpc/krpc/issues/903) become a new case of their own, sent only once the
  server has granted the feature. Each case but `disconnect` is valid in one direction, as
  commented. A known case received in the wrong direction is a protocol error, and ends the
  connection.
- **The name.** A `Message` is one complete, self-contained unit, as in Cap'n Proto RPC. In the
  server, the `KRPC.Server.Message` namespace takes precedence over the bare name, so server files
  alias `KRPC.Schema.KRPC.Message`, as they already alias `ConnectionRequest`.
- **`oneof` works on the server's pin.** protoc 3.10.1 generates the C# `oneof`, it
  compiles against Google.Protobuf 3.10.1 (`net45`) under Mono, and a message with an unknown field
  parses with no case set (`ContentCase == None`). A set case holding an empty message still encodes, as a tag and a zero length,
  so an empty `Response` is never mistaken for an unset one. nanopb, lua-protobuf and the stock
  runtimes all support `oneof`.
- **An unknown case is skipped** by both sides once a session has started, per the rule in
  [protocol-version.md](protocol-version.md) "Additive changes". The server logs it at debug level.
  During the handshake it is an error. See "Handshake".
- **Framing is the transport's.** A protobuf message carries no length, so each transport delimits
  `Message`s: a varint length prefix on TCP, the local socket and SerialIO, and one binary WebSocket
  message on WebSockets. The WebSocket frame header carries the length, and a client may split one
  message across fragments.

### Handshake

The handshake is two `Message`s: a `connection_request` from the client, and a
`connection_response` from the server. They hold the `ConnectionRequest` and `ConnectionResponse`
types, minus the fields listed under "Removed". On WebSockets they follow the HTTP upgrade, which
carries no kRPC parameters: no client name in the query string and no version in a subprotocol. The
server ignores any subprotocol and returns none. Every transport then speaks one protocol from its
first `Message`, and anything added to `ConnectionRequest` later, such as the `features` list,
reaches every transport.

**The server**, before a session starts, reads one `Message` and answers with a
`connection_response`:

| First `Message` | Status, then |
| --- | --- |
| Fails to parse | `MALFORMED_MESSAGE`, end |
| A `disconnect` | No response, end |
| Any other case but `connection_request`, or none | `MALFORMED_MESSAGE`, end |
| No complete `Message` within 3 seconds of the connection opening, a partial one included. On WebSockets the clock starts at the TCP accept, so it covers the upgrade. TCP, the local socket and WebSockets only: a serial line has no opening to time from. | `TIMEOUT`, end |
| A `connection_request` with no version, or an unsupported one | `WRONG_PROTOCOL_VERSION`, end |
| A `connection_request` with a supported version, denied on approval | `DENIED`, end |
| A `connection_request` with a supported version, approved | `OK`, and the session starts |

`ConnectionResponse.Status` gains `DENIED = 5`, for a connection the player or a mod handling
`OnClientRequestingConnection` denies. The server writes nothing while approval is pending, and
sets no timeout on it.

The server does not reject a `connection_request` for carrying unknown fields. The `features` list
of [protocol-version.md](protocol-version.md) relies on an older server ignoring them.

**The client** sends nothing after its `connection_request` until it has read the
`connection_response`, and gives up after its handshake timeout (see "Partial messages"). On a new
connection a `disconnect` ends the connection with its reason, and any other `Message`, including
one with no known case, is a protocol error. On a refusal the client reports the status and
message, and ends the connection.

A client that may be resuming a line used by an earlier session, such as a serial client after a
reset, differs in three ways (see "Reconnecting"):

- It skips a `response`, `stream_update` or `disconnect` while it waits, since those can be left
  over from that session.
- It treats `MALFORMED_MESSAGE` and `TIMEOUT` like no answer: it stays silent until its handshake
  timeout, then retries.
- It never retries after `DENIED` or `WRONG_PROTOCOL_VERSION`.
- It keeps reading `connection_response`s until the first `response` of the session. Retries
  queue on the line while the server is not reading, such as during a scene load, and the server
  answers each with a new session. A later `OK` replaces the session, and the client's ids already
  restart at 1. A later refusal returns the client to the handshake.

#### Ending a connection

Either side ends a connection by writing a `disconnect`, then closing. The server answers a
`connection_request` it refuses with a `connection_response` instead, as in the table above.

| Cause | Sent by | `Disconnect.Reason` |
| --- | --- | --- |
| The program closes the connection | Client | `CLOSED` |
| The server stops | Server | `SERVER_STOPPED` |
| The player removes the client from the server window | Server | `REMOVED` |
| A `Message` fails to parse | Either | `MALFORMED_MESSAGE` |
| A known case arrives in the wrong direction or out of place, or a response has an unknown id | Either | `PROTOCOL_ERROR` |
| A partial message stalls (see "Partial messages") | Either | `TIMEOUT` |

- **The reason is informational.** The receiver may log it, show it, or clean up on it. The end is
  not optional: the sender writes nothing more, and the receiver ends the connection.
- **It is best effort.** A crashed or killed program sends none, and a sender writes one only
  while the connection accepts writes. Every receiver handles an end with no `disconnect`.
- **The `message` field** says what happened, for the other side to log or show.
- **A reconnect** ends the old session with no `disconnect`. The new `connection_response` answers
  it.

The server reads a client's `disconnect` in order, after the call before it completes. It ends the
session as on a close: it drops the client, its streams and any tick it holds. The server logs a
`CLOSED` end at info level, and any other reason, or an end with no `disconnect`, as a warning.

**Closing a socket.** On TCP, the local socket and WebSockets, closing a socket with unread data
sends a reset, which can discard a `disconnect` still in flight. A streaming client nearly always
has unread updates. So the sender of a `disconnect` closes in three steps, in both directions:

1. Write the `disconnect`, then half-close the write side: `shutdown` on TCP and the local socket,
   a close frame on WebSockets.
2. Read and discard until the peer closes, for up to 1 second. The receiver of a `disconnect`
   closes at once, on WebSockets by answering the close frame with its own, so this is normally
   one round trip.
3. Close the socket.

The server never blocks the game thread on step 2. It moves the connection to a closing list,
drains it on each update, and closes it at end of stream or after 1 second.

A serial port has nothing to close. A `disconnect` is the only end of a session the server can see
there, besides a reconnect, so the server drops the session and waits for a new
`connection_request`.

#### Reconnecting

A `connection_request` received during a session starts a new one, on every transport.

- The server reads a client's messages in order, one request at a time. A `connection_request` is
  therefore read only once the call before it has completed and its response is written. A yielding
  call such as `WarpTo` delays a reconnect until it completes.
- The server then ends the current session as it would on a disconnect: it drops the client, its
  streams and any tick it holds, and writes nothing more for that session.
- It handles the `connection_request` as the first `Message` of a new session, on the same
  connection, approval included. Success gives a new client, with a new GUID. Request ids start
  again from 1. A denial answers `DENIED` and ends the connection.
- Every `Message` the client reads before the `connection_response` belongs to the old session.
- Each protocol's message stream does this, for every transport. It generalizes the reconnect that
  `SerialIO.ByteServer.ClientConnectionRequest` performs today.

On a serial line this is how a client that resets, such as an Arduino after a power cycle, gets
back in, since the line carries no connect or disconnect. Bytes from the old session can leave a
partial message on the line, which the client sees as a parse error and answers by retrying the
handshake (see "Partial messages"). On TCP, the local socket and WebSockets a bundled client opens
a new connection instead, but the server treats a `connection_request` the same way on every
transport.

#### Partial messages

A message that stops arriving partway ends the connection, on every transport and on both sides.

- Once the first byte of a message has arrived, the rest must keep arriving. If no byte of it
  arrives within the stall timeout, the receiver discards the partial message and ends the
  connection. The server ends it with a `disconnect`, reason `TIMEOUT`. On a serial port the
  server then waits for a new `connection_request`.

| Transport | Stall timeout | Reason |
| --- | --- | --- |
| SerialIO | 3 seconds | How a reset client resynchronizes, below. Matches the server's existing handshake timeout (`ProtocolBuffers.Utils.ReadMessage`). |
| TCP, local socket, WebSockets | 30 seconds | A bundled client never reconnects in place, so only a dead peer needs catching. TCP's retransmission backoff can stall a message for several seconds over a lossy link. |

- This is the only timeout on a serial line. The handshake `TIMEOUT` row does not apply there.
- On the other transports the handshake `TIMEOUT` row covers the first `Message`, partial or not.
  The stall timeout applies from the second.
- The clock restarts with every byte received, so a large message over a slow link is never cut
  off. At 9600 baud a serial line carries about 1 KB per second.
- The receiver checks the clock only after a read finds no new bytes. A game freeze, such as a
  scene load, then never ends a message whose bytes are already waiting in the socket.
- No timeout applies between messages. An idle connection, or a client between calls, stays open.

This is how a reset serial client resynchronizes. An Arduino that restarts after sending a length
prefix leaves the server waiting for bytes that never come. If it stays down for 3 seconds the
server has already ended the session. If it is back sooner, its new `connection_request` lands
inside the stale message. If the request leaves the stale message short, the server answers
nothing. If it completes the stale message, the server fails to parse it and ends the session
with a `disconnect`. It then reads the rest of the request as a new first message, and refuses it
with `MALFORMED_MESSAGE`. So a client waits longer than 3 seconds for its `connection_response`,
skips a `disconnect`, treats `MALFORMED_MESSAGE` like no answer, and stays silent while it waits.
By the time it retries, the server has discarded the stale bytes.

The client handshake timeout is a parameter of each connect function: 5 seconds by default, or
none to wait indefinitely. A serial client's, when set, is never under 3.5 seconds. A server with
`AutoAcceptConnections` turned off answers only once the player approves, so a user who turns it
off connects with no handshake timeout. A serial client then never retries, so it recovers from a
stale partial message only by a manual reset. Retrying would raise an approval prompt per queued
`connection_request`. The default changes for new installs only, since every
save of the settings file writes the setting.

#### Old and new clients

A 0.7 client and a 0.8 server always fail to connect, in either direction, and the client always
raises an error. The error is often misleading, which is accepted to keep the server free of special
cases for old clients. The cases are in [protocol-version.md](protocol-version.md) "Per transport".

### Removed

| Item | Replacement |
| --- | --- |
| `ConnectionRequest.type`, `ConnectionRequest.client_identifier` | Field numbers reserved |
| `ConnectionResponse.Status.WRONG_TYPE` | Value reserved |
| `MultiplexedRequest`, `MultiplexedResponse` | `Message` |
| The stream listener on every transport, `stream_port`, `stream_path` | None |


### Client identifier

`ConnectionResponse.client_identifier` stays: the 16 bytes of the client's GUID, as now. It is a
debugging aid, for matching a client to the server's log lines. Clients may ignore it, and need no
new API for it. `KRPC.GetClientID` returns the same bytes.

The server's logs name a client by its `Address` alone today, which does not tell clients apart:

| Transport | `Address` |
| --- | --- |
| TCP, WebSockets | The remote IP, with no port, so every local client is `127.0.0.1` |
| Local socket | The socket path, the same for every client |
| SerialIO | The port name, the same for every session |

So the server's client label in log lines becomes the address followed by the identifier, as in
`127.0.0.1 (a1b2c3d4)`. The identifier is written as lowercase hex of the wire bytes in order,
first 4 bytes, so that it matches a client printing the bytes it received. `Guid.ToString()` is not
used, as .NET orders the first three groups of a GUID's bytes little-endian, and its text does not
match the bytes. A session started by a reconnect gets a new identifier on the same address, so the
label also tells sessions apart.

### Ordering guarantees

Within one `Core.Update`, the call phase writes every response before `StreamServerUpdate` writes
any stream update. `RemoveStream` takes effect at the start of `StreamServerUpdate`. One ordered
connection therefore guarantees:

1. **The first update for a stream follows the response to the call that added it.**
2. **No update for a stream follows the response to the call that removed it.**
3. **A response follows every update the server wrote before it.**

(1) has one exception. A batched `Request` that adds a stream and also holds a call that yields
completes in a later update. The stream is registered when its call runs, so its first update
precedes the response, and the reader drops it by Streams rule 3. No bundled client batches calls.
The fix is a follow-up (see "Follow-ups").

Over two sockets, (1) and (2) do not hold. Each client grew machinery for an update that arrives
before its stream is registered, or after it is removed. Python's is `StreamManager._keep`,
`_pending`, `_issued`, `_unregistered`, `note_issued` and `note_removed`, added in 0.7 by
[PR #1122](https://github.com/krpc/krpc/pull/1122), with its tests in `test_stream.py` (the
`test_kept_results_*` tests and their neighbors). Under the reader rules below it is deleted. (3) is
new: a caller that returns from a call sees stream values at least as new as the server's state
before that call.

### Server

- One listener per transport. `KRPC.Server.Server` wraps one `IServer`, and `Address`, `Running`,
  `BytesRead` and `BytesWritten` report it alone.
- One client object per connection. Its stream reads `Request`s out of `Message`s and writes
  `Response`s and `StreamUpdate`s in them. `Core.streamClients` and the stream server classes go.
  Core keys streams by the RPC client.
- `ExecuteContinuation` and `SendErrorResponse` copy the request's id onto the response. A request
  that parses but fails to decode, such as one naming a reclaimed object, still has its id: the
  stream reads `Request.id` before decoding the calls, and `RequestDecodeException` carries it to
  `SendErrorResponse`.
- **A message the server cannot parse ends the connection**, with a `disconnect`, reason
  `MALFORMED_MESSAGE`. It has no id to answer with, and the client cannot match an id-less
  response. Any other failure to read a request ends it the same way, since no valid request
  exists to tie a `Response` to. This covers the final `catch` in `Core.PollRequests`, which sends
  an id-less error `Response` today.
- The server does not validate ids. It copies them.
- Log lines name a client by address and identifier. See "Client identifier".
- Every connection the server ends gets a reason. See "Ending a connection". On TCP a denial today
  closes the socket with no response, and now answers `DENIED`.
- `AutoAcceptConnections` defaults to true. An existing settings file keeps its value, and the
  changelog's **Breaking:** entry says so.
- Streams over SerialIO are unsupported, and `Core` does not check for them. A SerialIO client that
  adds a stream gets undefined behavior. The serial IO docs say streams are unavailable.
- The settings file reads `rpc_port` and `rpc_path` as now, and ignores `stream_port` and
  `stream_path` from an older file. The server editor and status display show one endpoint.

## Client reader

The rules every client with streams follows: Python, C#, Java and C++. They are the target for the
conformance suite ([client-conformance.md](../client-conformance.md)), which may later adjust a
client's internals but not these behaviors. The priority is correctness at the protocol level.

### Threads

| Thread | Owns | Never |
| --- | --- | --- |
| Callers | Their own calls | Read the socket |
| Reader, one per connection | Every read from the socket, the pending-call table, the stream registry, stored stream values | Run user code. Write to the socket. Take a lock user code can hold, such as a stream's condition. |
| Dispatcher, one per connection | Waking stream waiters, running value, event, update and end callbacks, the writes the reader queues | Read the socket |

**Why the reader never writes.** Writes are serialized by a lock that callers hold for a whole
blocking socket write. A caller blocked on a full send buffer would stall a reader waiting for that
lock, and the server's writes would then back up behind the unread socket. The reader queues each
write it needs with the dispatcher instead, in order with the callbacks. A slow callback delays
such a write, which is harmless for both kinds: a `RemoveStream` for an abandoned stream, and a
`disconnect` on a protocol error.

**Why the reader runs no user code.** Today callbacks run on the stream thread. If that thread also
read responses, two ordinary programs would deadlock:

- An RPC from a callback waits for a response that only its own thread can read. Removing a stream
  from its own callback is one such call.
- An RPC made while holding a stream's condition, such as
  `with alt.condition: alt.wait(); vessel.control.throttle = 0`. The reader would block taking the
  condition to notify, and never read the throttle response.

With a separate dispatcher, both work as they do today. A blocked callback stalls other callbacks
and waiters, never responses.

### Connecting

The connecting thread does the handshake itself, before the reader and dispatcher start. A bundled
client never sends a second `connection_request` on a connection; it opens a new one instead.

### Calls

1. Ids are per session, start at 1 and increase by one. 0 is never sent.
2. A caller adds a pending slot for the id **before** writing the request, so a fast response always
   finds it.
3. Writes are serialized by a write lock, held for one whole message. No other lock is held across
   a call. The Python `_rpc_connection_lock` goes, so threads no longer queue behind a slow call on
   the client.
4. The caller waits on its slot. The reader fills it with the response whose id matches.
5. A caller that stops waiting, from an interrupt or a timeout, marks its slot abandoned. The reader
   discards the response when it arrives. This fixes Python bug 25
   ([client-api-parity-audit.md](../client-api-parity-audit.md)) without further work.
6. A response whose id is neither pending nor abandoned is a protocol error. The reader closes the
   connection, as in "Failure and close".

Several threads may have requests on the socket at once. The server still runs one request per
client at a time, in order, and TCP holds the rest. That is safe with no server change, and is the
first step towards pipelining ([request-ids.md](request-ids.md) phase 2).

### Streams

1. **The reader registers a stream.** A call returning a `KRPC.Stream` or `KRPC.Event` carries the
   stream's value type in its slot. On its response, the reader adds the stream to the registry
   before reading the next message. By ordering guarantee (1), no update for the stream can come
   first. If the slot was abandoned, the reader instead queues a `RemoveStream` for the id with the
   dispatcher, so the server stream does not leak. The dispatcher writes it with an abandoned slot
   of its own, and rule 3 drops the stream's updates until then.
2. On a `stream_update`, the reader decodes each result and stores the value under an internal lock.
   It then queues the work for the dispatcher: notify the stream's waiters and pass the value to its
   callbacks.
3. A result for an id not in the registry is dropped. It is for a stream the client has removed
   locally, still in flight before the `RemoveStream` response.
4. A final result (an error) ends the stream on the reader, and the dispatcher calls its end
   callbacks.
5. The dispatcher runs work in arrival order. A waiter woken by it reads the stored value, which is
   at least as new as the update that woke it.
6. `RemoveStream` keeps today's client semantics: the stream ends locally at once, and the call is
   sent. Rule 3 drops any update still in flight.

Values are stored on the reader and not the dispatcher so that ordering guarantee (3) reaches the
caller: when a call returns, every update written before its response is already stored. Callbacks
can lag behind; stored values cannot.

### Failure and close

1. The connection fails when a read or write fails, on a protocol error, when a partial message
   stalls (see "Partial messages"), or on a `disconnect`. The connection error carries the
   `disconnect`'s reason and message when there is one. The reader fails every
   pending slot with a connection error, and queues the ending of every stream with the dispatcher.
   The dispatcher drains its queue and exits.
2. On a protocol error, the reader first queues a `disconnect` naming it. The dispatcher writes it
   and half-closes, and the reader discards input until end of stream or for 1 second after the
   half-close. The reader then closes the socket. See "Closing a socket".
3. `close`, if the connection has not failed, writes a `disconnect` with reason `CLOSED` and
   half-closes. If it cannot take the write lock within 1 second, such as behind a caller blocked
   on a full send buffer, it skips the `disconnect`. It waits up to 1 second for the reader to reach end of stream, then closes the
   socket. It then joins the reader and the dispatcher, except a thread `close` is running on.
   Closing from a callback runs on the dispatcher and so does not join it.
4. A call made after the connection fails raises the connection error at once.
5. A `Message` with no known case set is skipped. A known case not expected in a session, such as
   a `request` or a `connection_response`, is a protocol error. A server exception the client does
   not know maps to its generic error. All three are pinned by the conformance suite.

### Per client

| Client | Today | Change |
| --- | --- | --- |
| Python | Update thread reads the stream socket and runs callbacks. Calls under `_rpc_connection_lock`. | Reader plus dispatcher. Kept-results machinery deleted. |
| C# | `StreamManager` update thread | Same split. Keep the lock order fixed in [PR #1005](https://github.com/krpc/krpc/pull/1005): never take a stream's condition under the update lock. |
| Java | `StreamManager` update thread | As C# |
| C++ | `StreamManager` update thread | As C# |
| Lua, cnano | Synchronous, no streams | See "Simple clients" |

### Simple clients

Lua and cnano have no streams and stay single-threaded. A call writes the request in a `Message`, then
reads `Message`s until a `response` with its id arrives. It skips a `Message` with no known case.
A `disconnect` fails the call with its reason. Any other case, or a mismatched id, is a protocol
error, except a `connection_response` before the first `response` on a resumed serial line (see
"Handshake"). Since these clients never add a stream, a `stream_update` never arrives. Their close
function writes a `disconnect` too, which on a serial line is how the server learns the session
has ended. On a socket it then half-closes and drains for up to 1 second, as in "Closing a
socket".

cnano decodes the `oneof` with nanopb's `submsg_callback` option on `Message`. nanopb clears a
`oneof` member when it decodes the case's tag. That wipes the error decode callbacks cnano sets
before decoding today, so cnano sets them from the `submsg_callback` instead.

### Client API

- Removed: `stream_port`/`stream_path` (Python, C++), `streamPort`/`streamPath` (C#, Java), from
  every connect function. Each client then fails loudly on old code, as a compile error or a
  `TypeError`.
- Added: a handshake timeout on every connect function, 5 seconds by default, or none to wait
  indefinitely (see "Partial messages").
- A refused or ended connection raises the client's connection error, naming the status or
  reason and the server's message. A `DENIED` refusal is distinguishable from the others.
- The client guides say callbacks run on the client's callback thread, and may make RPCs. A
  callback must not wait on a stream, since the same thread wakes the waiters.

## Phases

All on one branch for 0.8. The server moves to version 2 in one step, with no version 1 path kept
alongside it. Client tests then fail until each client has moved. Only the head of the branch must
build and pass `//:test` and `bazel build //...`. Each phase is still one or more commits that do
one thing.

| Phase | Work | Tests at the end |
| --- | --- | --- |
| 1 | **Server, version 2 only.** `Message`, `Request.id`, `Response.id`, the handshake in a `Message`, reconnecting with approval, the partial message timeouts, `DENIED`, `disconnect` sent and received, the closing list that drains a socket after a `disconnect`, a `disconnect` for a request that fails to read, `AutoAcceptConnections` on by default, the client label in log lines. One listener and one client object per connection on every transport, SerialIO included. Remove the stream listener and server classes, `Core.streamClients`, `ConnectionRequest.type`, `ConnectionRequest.client_identifier`, `WRONG_TYPE`, `MultiplexedRequest`, `MultiplexedResponse`, the `stream_port`/`stream_path` settings and server editor fields, and the `TestServer` stream flags. | Server tests pass. Every client's tests fail. |
| 2 | **Python**: reader, dispatcher, removed parameters, the handshake timeout, `disconnect` sent on close and raised on receipt, `DENIED` errors. The reference implementation of "Client reader". Measure per-call latency against a `main-0.8` build (see "Open questions"). | Python tests pass |
| 3 | **C#, Java, C++**, one at a time. | Each passes once moved |
| 4 | **Lua, cnano**, and the `serialio` and `websockets` test harnesses. Test a serial client reset in the middle of a message, both with its new request short of the stale message and completing it, and a serial client whose handshake retries queue while the server is not reading. | `//:test` passes |
| 5 | **Docs and changelog.** `doc/src/communication-protocols/`, the client guides, the doc examples. Changelog with a **Breaking:** entry, naming the `AutoAcceptConnections` default for new installs. | `//:test`, `bazel build //...` and the docs gates pass |
| 6 | `RemoveStream` and `SetStreamRate` take a `Stream` ([draft issue](../../issues/remove-stream-takes-stream.md)), if it fits. Otherwise delete the FIXME. | As phase 5 |

In-game tests run through the Python client, so they work again from phase 2.

### Streams over SerialIO

Streams over SerialIO are unsupported in 0.8, and the server does not check for them (see
"Server"). They follow later as an addition
([draft issue](../../issues/serialio-streams.md)). Before then the server needs flow control. Its
write buffer drops the connection when full (`serialio.rst`, "Buffering and Data Rates"), and a
fast stream at 9600 baud would fill it. The `Message` wrapper's 2 to 4 bytes per message are not
the concern.

## Follow-ups

Out of this branch. The protocol ones are additive on protocol version 2.

| Follow-up | Proposal |
| --- | --- |
| Streams over SerialIO | [Draft issue](../../issues/serialio-streams.md). Flow control, then support them. |
| Ctrl-C during a Python call on Windows | [Draft issue](../../issues/python-ctrl-c-windows.md). A caller waiting on its slot may not be interruptible there. Client only. |
| Bounding the dispatcher queue | Unbounded in 0.8: a slow dispatcher grows its queue instead of stalling the socket. Decide later whether to bound it, and what to drop. Client only. |
| A batched `Request` with a yielding call breaks ordering guarantee (1) | A call that yields in a `Request` of more than one call fails with an error, so the request completes in the update it is read. No wire change, and no bundled client batches calls. |

## Open questions

- **Per-call latency of the reader hand-off.** A call now wakes a waiting caller from the reader,
  where it used to return from its own `recv`. [Tick holding](../server/tick-hold.md) makes per-call
  latency what a control loop feels. In Python the wakeup also needs the GIL. Measure in phase 2
  with `tools/benchmarks`, version 1 against version 2, over TCP and the local socket. If the cost
  is material, the fallback is for a caller to read the socket itself while no other thread is
  reading, at the cost of a second code path.
