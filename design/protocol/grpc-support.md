# gRPC support (issue #1187)

**Status:** proposal (2026-10-25). Not scheduled. Issue [#1187](https://github.com/krpc/krpc/issues/1187),
which replaced the gRPC discussion on [#899](https://github.com/krpc/krpc/issues/899).

Related: [local-transports.md](local-transports.md) (why the game's runtime cannot host gRPC),
[single-connection.md](single-connection.md), [request-ids.md](request-ids.md),
[non-blocking-calls.md](non-blocking-calls.md), [fire-and-forget.md](fire-and-forget.md),
[reverse-streams.md](reverse-streams.md), [client-disconnect-cleanup.md](client-disconnect-cleanup.md).

## Why gRPC

* Generated clients for any language gRPC supports, including Go
  ([#512](https://github.com/krpc/krpc/issues/512)), Rust, Swift, Kotlin and Dart. A `.proto` file
  replaces a hand-maintained client per language.
* gRPC-web, through a proxy such as Envoy, gives browser clients typed stubs.
* Tooling: `grpcurl`, Postman and other gRPC tools work against kRPC with no kRPC-specific code.
* Requested repeatedly: [#342](https://github.com/krpc/krpc/issues/342), #899, Discord.

## Constraint

The server cannot host gRPC. A gRPC server needs HTTP/2 and `System.Net.Http`, which KSP's Mono
runtime lacks. The legacy `Grpc.Core` depends on an unsupported native library for each platform.
[local-transports.md](local-transports.md) records the details.

## How gRPC works

A `.proto` file declares **services**, which are groups of methods, and **messages**, the request
and response types. gRPC generates a typed client stub and a server skeleton per language.

* **Transport.** HTTP/2. A client holds a **channel**, which manages one or more TCP connections and
  reconnects transparently. Each call is its own HTTP/2 stream, so calls run concurrently over one
  connection.
* **Per call.** Metadata (key/value headers), an optional deadline, and cancellation, all
  propagated to the server. A call ends with a status: a code (`OK`, `CANCELLED`,
  `DEADLINE_EXCEEDED`, `UNAVAILABLE`, ...), a message and optional structured details.
* **Ordering.** Messages within one call arrive in order. Separate calls have no relative order.
* **Flow control.** HTTP/2 windows apply backpressure. A slow reader slows the writer, and no
  message is dropped.
* **Also:** server reflection (runtime schema discovery, as `grpcurl` uses), interceptors,
  keepalive pings, retry policies, load balancing.
* **No session.** The connection is hidden from the application. Each call stands alone.

Every method has one of four shapes:

| Shape | Client sends | Server sends |
| --- | --- | --- |
| Unary | one message | one message |
| Server streaming | one message | many messages, then the status |
| Client streaming | many messages | one message |
| Bidirectional | many messages | many messages, independently |

## Proposed approach: an external bridge

A separate process on a current runtime. It speaks gRPC to clients and the kRPC protocol to the
server:

```
gRPC client --HTTP/2--> krpc-grpc-bridge --kRPC/TCP--> KSP
```

The game-side server is unchanged. The bridge is an ordinary kRPC client, so it needs no mod changes
and adds no load inside KSP. A loopback hop costs well under a millisecond.

1. **`.proto` generator.** A clientgen target emitting a `.proto` from the service definitions.
   * A procedure becomes an `rpc`, with a request message holding its parameters and a response
     message holding its return value.
   * A class becomes a message wrapping its `uint64` object id.
   * Tuples, lists, dictionaries and nullable values map onto proto messages, with wrappers where
     proto has no direct form: nested lists, non-scalar map keys.
   * Streams and events become server-streaming RPCs.
2. **Bridge.** Reads `GetServices` at startup and transcodes each call generically, with no
   generated code per service. kRPC encodes each argument as its own bytes field, so transcoding is
   per argument. Built on the existing C# client, on .NET 8.
3. **Distribution.** A `.proto` for the stock services and the supported mods, plus the bridge as a
   standalone binary.

### Sessions

The server ties client identity, object lifetimes, stream ownership and disconnect cleanup to the
connection. gRPC has no connection the application can see. The bridge models one explicitly:

* The client opens a long-lived bidirectional **`Session`** call. The bridge holds one kRPC
  connection for its lifetime, and the client name travels as metadata on it.
* Other calls name the session in metadata.
* When the `Session` call ends, by close, cancellation or a keepalive failure, the bridge closes the
  kRPC connection, and the server's existing disconnect cleanup runs.
* Calls sent inside the `Session` call keep their order, which recovers per-client FIFO for clients
  that need it.
* gRPC-web has no bidirectional streaming. Browser clients fall back to a `Connect` call returning a
  session token, with an idle timeout to reclaim abandoned sessions.

## Mapping kRPC features to gRPC

| kRPC feature | gRPC equivalent | Fit |
| --- | --- | --- |
| Procedure call | Unary RPC | Direct |
| Discovery (`GetServices`), dynamic clients | Server reflection, of the generated schema | Good |
| Errors (service, name, description, stack trace) | Status code plus structured details | Good |
| Nullable values, tuples, collections | `optional`, wrapper messages, `repeated`, `map` (scalar keys only) | Good, with wrappers |
| Yielding RPCs (`WarpTo`) | Long-running unary call, with an optional deadline | Good; other calls keep flowing |
| Streams (server to client, at a rate) | Server-streaming RPC per kRPC stream, rate as a request field | Good |
| Events | Server-streaming RPC that sends when the event fires | Good |
| Stream refcounting and invalidation | Ending the call removes the stream; invalidation is a final error status | Good |
| Request ids, async calls, pipelining (0.8) | Concurrent calls over HTTP/2 | Built in |
| Single connection (0.8) | The channel multiplexes everything | Not needed |
| Per-client FIFO execution | None across calls; ordered only within one streaming call | Gap; the `Session` call recovers it |
| Batching: several calls in one tick ([non-blocking-calls.md](non-blocking-calls.md)) | None. A batch RPC with a `oneof` per procedure would be enormous. The bridge can coalesce concurrent calls into one tick, with no guarantee they land together | Gap |
| Fire-and-forget ([fire-and-forget.md](fire-and-forget.md)) | None. A unary call always responds, though an empty response is cheap. A client-streaming call carries one-way messages | Workaround |
| Reverse streams, latest-wins pushes ([reverse-streams.md](reverse-streams.md)) | Client-streaming RPC, which delivers every message. The bridge implements latest-wins | Partial |
| Remote objects | None; ids are message fields | Gap, by design |
| Objects and state tied to a client session | None | Gap; the `Session` call models it |
| Client name, handshake | Metadata | Direct |
| Server-side functions (expression trees) | A recursive message carrying the tree, in a unary call. Stubs give raw tree messages with none of the client builder APIs | Works, low ergonomics |
| Browser clients | gRPC-web: unary and server streaming only, through a proxy | Partial |

The transport and call shapes cover kRPC well, and pipelining and long calls better than the 0.7
protocol. The gaps are the semantics kRPC builds on a connection with one client behind it:
sessions, FIFO order, same-tick batching and remote objects.

gRPC users get a flat, id-based API with no batching, so `vessel.flight()` becomes
`SpaceCenter.Vessel_get_Flight({vessel: id})`. That suits tooling and dashboards. Flight scripts are
better served by the native clients.

## gRPC features kRPC lacks

Three matter, and no planned design covers them. Each is worth doing in kRPC itself, with or without
the bridge.

| gRPC feature | kRPC today | Proposal |
| --- | --- | --- |
| **Cancellation** of an in-flight call | None. A running `WarpTo` or yielding wait ends only by completing or by disconnect | `Cancel { id }`, naming a request by its id ([request-ids.md](request-ids.md), [#1175](https://github.com/krpc/krpc/issues/1175)). A follow-up to request ids. It also gives the bridge a way to pass gRPC cancellation through |
| **Deadlines** | Client-side timeouts only. A call that timed out on the client still runs later, so a setter can land after the script has moved on | A deadline on `ProcedureCall`; the server skips expired calls. Same server check as cancellation, so built together |
| **Dead peer detection** (keepalive) | TCP only. A dropped or sleeping laptop leaves a half-open connection for minutes to hours. The server keeps the client, and the disconnect cleanup ([PR #934](https://github.com/krpc/krpc/pull/934)) never runs: the auto-pilot stays engaged and part forces keep applying | A heartbeat in the single-connection protocol: ping when idle, drop the client after missed replies. TCP keepalive is the alternative, but per-OS tuning from Mono is unreliable. **The most important of the three**, as a safety issue independent of gRPC |

The rest do not apply to a game server:

| gRPC feature | Why it does not matter |
| --- | --- |
| Concurrent execution | RPCs run on the game thread. Pipelining from 0.8 gives the latency benefit |
| Flow control, backpressure | Latest-wins streams and reverse streams, plus TCP. SerialIO flow control is its own draft ([serialio-streams.md](../../issues/serialio-streams.md)) |
| TLS, authentication | [#11](https://github.com/krpc/krpc/issues/11): use a proxy or tunnel. The bridge could add TLS if needed |
| Compression | Messages are small and traffic mostly local |
| Metadata, interceptors, tracing | Service middleware, with no user need here |
| Retries, load balancing, health checks | Built for server fleets. Retrying a non-idempotent game action is wrong |
| Status code taxonomy | kRPC errors carry more detail, though no machine-readable code |
| Language reach, tooling | The purpose of this proposal |

## Open questions

* **Mod-dependent schema.** The `.proto` reflects the installed mods. Users with other mods
  regenerate it, with clientgen or with a bridge command that writes it from the running server.
* **Protocol changes.** Each kRPC protocol change must be carried through the bridge.
* **Where it lives.** Under `tools/` in `krpc`, or a separate repo with its own release cycle.
* **Bridge language.** C# reuses the kRPC client and codecs. Go gives a single static binary.
