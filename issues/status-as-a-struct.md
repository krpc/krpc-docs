# Return the server status as a kRPC struct, not a protobuf message

`KRPC.GetStatus` returns `KRPC.Status`, a message from `krpc.proto`. It is the only procedure that returns a protocol message as plain data. The other message results are protocol objects a client handles itself: `GetServices` builds the stubs, and `AddStream`, `AddFunctionStream` and `AddEvent` return stream and event handles. `GetStatus` predates kRPC structs, which the `KRPC` service already uses for `Clients` (`ClientInfo`).

Returning a message costs every client special handling:

- Each client decodes the result with its own protobuf library, and hands its users that library's type: a generated `Status` class in Python, C#, Java and C++, and a lua-protobuf table in Lua. A service author's API is the only place a protobuf type reaches a user.
- The clientgen dispatch backends skip message results, so the conformance testees cannot call `GetStatus`. Each client keeps its own `GetStatus` test as a result.
- The protocol docs use `GetStatus` as the example call, so a third-party client must decode `Status` to run the first example.
- `Status` mixes the release version and the connection's protocol version with server settings and performance counters. Several of those counters and settings date from before the single connection.

## Proposal

Replace the message with a kRPC struct in the `KRPC` service, such as `ServerStatus`, holding the same fields under kRPC names. Clients then decode it like any other struct, through their generated code. The conformance suite can test it, and the `Status` message leaves `krpc.proto`.

A struct is better than a tuple:

| | Struct | Tuple |
| --- | --- | --- |
| Field access | By name, as `Status` is today (`status.version`) | By position, over about 20 items |
| Docs | Each field documented | One description for the whole tuple |
| Precedent | `ClientInfo` in the same service | None in the `KRPC` service |

Neither form can gain a field without breaking older clients today, as both check their item count when decoding. How a struct grows later belongs to service versioning, not to this change.

## Open questions

- **Which fields stay.** The version and protocol version are what users read. The settings (`one_rpc_per_update`, `max_time_per_update`, `adaptive_rate_control`, `blocking_recv`, `recv_timeout`) and the rate counters may be stale after the single connection, or better as separate properties.
- **Properties instead.** A `KRPC.Version` property plus a statistics struct would serve the common case without a struct at all.
- **Breaking or deprecated.** Planned for 0.8, which breaks the protocol anyway with the single connection and protocol version 2, so the return type can change there. Adding the struct under a new name and deprecating `GetStatus` is the gentler path. Every client's docs and examples call `get_status().version`.
- **Protocol docs.** The example call would move to a procedure with a scalar result, such as `GetClientName`, so a first client needs no message decoding.
