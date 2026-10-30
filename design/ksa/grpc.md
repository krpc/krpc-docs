# gRPC on KSA

**Status:** in progress. Part of [kRPC for KSA](README.md). The unary server is built and tested in
game on Linux, not yet in a PR. [Streams](#streams) wait for KSA to build against KRPC.Core 0.8.

KSA runs on .NET 10, so kRPC for KSA hosts a gRPC server in the game process, beside the kRPC
protocol server. The server is built from the service definitions:

 * A generated `.proto` gives each procedure a typed unary method.
 * The server decodes the typed messages straight to the values the procedures take.
 * Calls run through the same server core as kRPC protocol calls, on the game thread.

Any language with gRPC support gets a typed client with no kRPC-specific code. The gRPC support
design for KSP, [grpc-support.md](../protocol/grpc-support.md) (issue
[#1187](https://github.com/krpc/krpc/issues/1187)), keeps the bridge for KSP, whose runtime cannot
host gRPC.

## Approaches Dropped

 * **gRPC in place of the kRPC protocol.** It would break every existing kRPC client and script.
   Streams of arbitrary calls, server-side functions, events, remote objects and `GetServices`
   discovery would all need rebuilding on top of it.
 * **An external bridge** (#1187). A separate process, with every call crossing the kRPC protocol.
   Cancellation and deadlines could only pass through once the kRPC protocol carries them.
 * **kRPC framing behind a gRPC front end.** A gRPC server writing kRPC protocol bytes into the
   protocol buffers server's byte stream. This is the bridge moved in-process, with the same limits.
 * **Tunneling kRPC messages through one bidirectional call.** Another transport, like WebSockets,
   that gives gRPC clients nothing new.

## Example

With the `.proto` compiled by `grpc_tools.protoc`:

```python
import grpc
import KSA_pb2 as pb
import KSA_pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:50002")
ksa = KSA_pb2_grpc.KSAStub(channel)
vehicle = ksa.get_ActiveVehicle(pb.get_ActiveVehicleRequest()).value
name = ksa.Vehicle_get_Name(pb.Vehicle_get_NameRequest(this=vehicle)).value
```

## Hosting

grpc-dotnet runs on Kestrel and the `Microsoft.AspNetCore.App` shared framework. KSA ships only
`Microsoft.NETCore.App`, and StarMap runs on the system .NET 10 runtime.

 * `build.sh` downloads the ASP.NET Core runtime packs `Microsoft.AspNetCore.App.Runtime.win-x64`
   and `.linux-x64` from NuGet, pinned by version and sha256 in `versions.sh`. Their assemblies go
   in the mod's `grpc/win-x64/` and `grpc/linux-x64/`, beside `KRPC.KSA.Grpc.dll` in `grpc/`.
 * The pack assemblies are ReadyToRun images stamped with one OS, and a Windows image throws
   `BadImageFormatException` on Linux. The mod carries both packs, about 28 MB each, and loads the
   one for the platform it runs on. This is the packaging for releases. Borea supports one archive
   for every platform with runtime selection, and defers per-platform downloads
   ([content-manager-design#75](https://github.com/KSAModding/content-manager-design/discussions/75)).
 * The game loads its own copies of the `Microsoft.Extensions` assemblies that ASP.NET Core also
   uses. Sharing them fails with a `MissingMethodException`. `Addon` therefore loads the `grpc/`
   folders into their own `AssemblyLoadContext`. That context resolves the folder's assemblies
   itself, and takes the rest, including `KRPC.Core`, from the mod's context.
 * The server project has no reference to the gRPC project. `Addon` calls `GrpcServer.Create`
   through reflection, so ASP.NET Core never enters the mod's context.
 * KSA's `Brutal.*` assemblies reference `Microsoft.Extensions.ObjectPool` 11. The gRPC project
   drops the game references, which would otherwise conflict with the framework's version 10.
 * Kestrel serves h2c, HTTP/2 without TLS, on `127.0.0.1:50002`. It is a second `[[servers]]` entry
   in `settings.toml`, with `protocol = "gRPC"`.
 * `Addon.CreateServer` builds gRPC servers, for the settings file and the server window alike. gRPC
   is a protocol in the window's edit form, with an address and a port
   ([server.md](server.md)). A server that fails to build leaves the form open with the error.

## Mapping

`grpc/protogen.py` writes the `.proto` from `KRPC.KSA.json`, and `grpc/src/ProtoCodec.cs` encodes by
the same rules. Only field numbers and wire types reach the wire, so those are all the two must agree
on.

| kRPC | proto |
|---|---|
| Service `S` | `service S` in `package krpc.s` (`s` in lower case) |
| Procedure `P` | `rpc P (PRequest) returns (PResponse)`; names as in kRPC, e.g. `Vehicle_get_Name` |
| Parameter at position `i` | field `i + 1` of `PRequest`, in snake case; `this` included |
| Return value | field 1 of `PResponse`, named `value`; empty message when there is none |
| Class `C` | `message C { uint64 id = 1; }`; id 0 is null |
| Enumeration `E`, value `V` | `enum E` with `E_V` at kRPC's number; `E_UNSPECIFIED = 0` if no value is 0 |
| Tuple | `message Tuple_<types>`, item `i` as field `i + 1` |
| Structure `T` | `message T`, field `i` as field `i + 1` in snake case; another service's from its own `.proto` |
| List, set | `repeated` |
| Dictionary | `map`, with a scalar key |
| Nullable scalar, or scalar parameter with a default | `optional`; an absent argument takes its default |
| Error | status code, with the description as its message |

Errors map by kRPC exception name:

 * `ArgumentException` and its subclasses map to `INVALID_ARGUMENT`.
 * `InvalidOperationException` maps to `FAILED_PRECONDITION`.
 * All others map to `UNKNOWN`.

The trailers carry `krpc-error-service`, `krpc-error-name` and `krpc-error-stack-trace-bin`. A
request that does not decode, such as one naming an unknown object id, is `INVALID_ARGUMENT`.

Object ids come from the same object store as the kRPC protocol, so a gRPC client and a kRPC client
see the same id for a vehicle.

Both the generator and the server leave out types with no typed form: nested containers,
nullable scalars or structures inside a container, and classes of another service. The KSA service
uses none of them. Its drawing colors are `StdLib.ColorRGB`, so `KSA.proto` imports `StdLib.proto`,
which the build also generates.

## Sessions and Threading

 * **Session.** One kRPC client per HTTP/2 connection, created by the first call over it. The
   optional `krpc-client-name` metadata names it. When the connection closes, the client
   disconnects and the server core's disconnect cleanup runs.
 * **Shared connections.** grpc-python shares one connection between the channels of a process to
   the same address, so those channels are one kRPC client, named by the first call. A channel
   created with the `grpc.use_local_subchannel_pool` option gets its own connection, as the tests
   do.
 * **Threading.** Kestrel runs handlers on the thread pool. A handler queues the call on its client
   and awaits a `TaskCompletionSource`. On the game thread, the server core reads the queue in its
   update, as it polls a TCP client. Connection events are queued the same way and raised in
   `GrpcServer.Update`.
 * **Decoding** happens on the game thread, in the stream's `DataAvailable`, because the object
   store is not thread safe.
 * **Order.** The server core runs one request at a time per client, in order. Concurrent calls
   over one channel queue behind each other. A yielding call such as `WarpTo` holds up the rest of
   its channel, and other channels keep running.
 * **Approval.** The connection request goes through the server core's events, so
   `auto_accept_connections` applies.

## Core Internals Used

The gRPC assembly compiles against the internals of the KRPC.Core 0.7.0 release through
`Krafs.Publicizer`, which emits `IgnoresAccessChecksTo`. The KRPC.Core release DLL is unchanged.
This list is the public seam `core` would need for a gRPC server outside it:

 * `Services.Instance.Signatures`, for the procedures and their `TypeSpec`s.
 * `ObjectStore.Instance.AddInstance` and `GetInstance`.
 * `ProcedureCall.CachedSignature`.
 * The internal constructors of `ClientRequestingConnectionEventArgs<,>`,
   `ClientConnectedEventArgs<,>` and `ClientDisconnectedEventArgs<,>`.
 * `SerialIO.StreamServer`, as the stream server that serves no clients.

## Limits of the Prototype

 * **Unary calls only.** Streams wait for the 0.8 core ([Streams](#streams)).
   The `KRPC` service is left out, as its stream, event and expression procedures have no unary
   form.
 * **Cancellation and deadlines are ignored.** A call the client cancels, or whose deadline passes,
   still runs in game, and its response is dropped.
 * **No server reflection or gRPC-web.** `grpcurl` needs the `.proto` passed with `-proto`.
 * **Release size.** The release archive would carry the 55 MB `grpc/` folder, 25 MB zipped.
   `release.sh` is unchanged.
 * **Tested on Linux only.** `build.bat` fetches the runtime packs and builds the gRPC assembly,
   but has not been run on Windows.
 * The gRPC server's `Protocol` value is outside the server core's enumeration, because the core
   has no gRPC protocol.

## Streams

kRPC streams become server-streaming gRPC methods, one per procedure that returns a value.

### Why Wait for 0.8

In 0.8 one connection carries both RPCs and streams
([single-connection.md](../protocol/single-connection.md)):

 * `Core.streamClients` and the stream server classes go away. The core keys streams by the RPC
   client and writes updates through that client's session stream.
 * On 0.7.0, the gRPC server would need its own `IServer<NoMessage,StreamUpdate>`. It would hold a
   stream client per gRPC client, sharing the client's GUID, so that `Core.AddStream` accepts it.
   That whole layer would be thrown away in 0.8.

On 0.8 the gRPC session needs no stream server. Its client's stream receives the stream updates
alongside the responses.

### Example

`protogen.py` adds a second service to `KSA.proto`, which reuses each procedure's messages:

```proto
service KSAStream {
  rpc get_UT (get_UTRequest) returns (stream get_UTResponse);
  rpc Vehicle_get_Name (Vehicle_get_NameRequest) returns (stream Vehicle_get_NameResponse);
}
```

From Python, using the same channel as the unary stub:

```python
streams = KSA_pb2_grpc.KSAStreamStub(channel)
for response in streams.get_UT(pb.get_UTRequest()):
    print(response.value)
```

### Semantics

 * **Methods.** `krpc.ksa.KSAStream/<procedure>`, for each supported procedure with a return value.
   A separate service avoids clashing with the unary method names. Calls with no value join once
   0.8 lets them be streamed
   (issue [#1198](https://github.com/krpc/krpc/issues/1198)). Their methods
   return a stream of empty responses.
 * **Values.** The first message is the current value. Each later message is sent when the value
   changes, as with a kRPC stream.
 * **Rate.** Optional request metadata `krpc-stream-rate`, in Hz, sets `Stream.Rate`.
 * **Errors.** If the procedure throws, the call ends with the status and trailers that the unary
   error mapping produces. The core removes the stream once it carries an error.
 * **Ending.** When the client cancels the call or closes the connection, the stream is removed.

### Mechanism

 * **Adding.** On the game thread, the handler's call is wrapped as a call to `KRPC.AddStream`. It
   goes through the normal call path, so approval, `CallContext` and the error mapping all apply.
   When the response is written, still on the game thread, the stream is registered under its id
   in the client's stream map. By the 0.8 ordering guarantee (1), the first update reaches the
   client after this registration.
 * **Updates.** The session stream receives each `StreamUpdate` on the game thread. Each result is
   encoded at that point with `ProtoCodec.EncodeResponse`, because the core reuses its cached
   `StreamUpdate`. The encoded result is then posted to the call's `Channel<byte[]>`.
 * **Back pressure.** The channel has capacity 1 and uses `DropOldest`. A slow reader gets the
   latest value, as a kRPC stream gives the latest value. An error completes the channel with an
   `RpcException`.
 * **Writing.** The Kestrel handler awaits the channel reader and calls `WriteAsync` for each
   message. `WriteAsync` must not run concurrently, so only the handler writes.
 * **Removal.** The handler's `finally` queues the stream id on the client. The queue is drained on
   the game thread, in the server's update, into `Core.RemoveStream`. When the connection closes,
   the core's client-disconnect cleanup removes the remaining streams.

### Out of Scope

 * **Events.** The KSA service has none.
 * **Function streams** (`AddFunctionStream`). These need Expressions over gRPC, so they wait for
   the `KRPC` service to be served.

### Tests

These go in `test_grpc.py`, as a `KSAStreamStub` on the existing channel:

 * Stream `get_UT` and check that it increases and tracks `ksa.ut`.
 * Stream `Vehicle_get_Name`, rename the vehicle through the unary stub, and check that the next
   message carries the new name.
 * Stream a call that fails (an unknown object id) and check for `INVALID_ARGUMENT`.
 * Cancel a stream, close a channel that holds one, and check that the server status stream count
   falls back each time.
 * Set `krpc-stream-rate` to 1 Hz and check that about one message arrives per second.

## Next Steps

1. Streams as server-streaming methods, once KSA builds on the 0.8 single-connection core
   ([Streams](#streams)).
2. Cancellation and deadlines in `core`, so a queued or yielding call can be dropped.
3. Server reflection, built from the same signatures.
4. The `KRPC` service's plain procedures, such as `GetStatus` and `Clients`.
5. Packaging: an optional gRPC download, or the `grpc/` folder in the release; Windows.
6. A public seam in `core` replacing the publicized internals.

## Open Questions

 * **Method names.** kRPC names (`Vehicle_get_Name`) keep the procedures recognizable from the kRPC
   docs. gRPC style would be `GetVehicleName`, at the risk of collisions.
 * **Session per connection.** A client cannot see or choose its connections. Channels share them
   in grpc-python, and other libraries may open several for one channel. Metadata naming a session
   would make sessions explicit, with an idle timeout in place of the connection close.
