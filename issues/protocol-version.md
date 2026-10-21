# Add a protocol version to the connection handshake

The protocol has no version of its own. `ConnectionRequest` and `ConnectionResponse` carry none, and compatibility rests on the server and clients sharing one release number. 0.7 already breaks 0.6 clients that call the `KRPC` procedures by id, and the single connection (#<single-connection>) breaks every client in 0.8. A mismatched client and server fail with a decode error or a hang instead of a message.

Add one integer protocol version to the handshake, starting at 1 in 0.7. `ConnectionRequest` and `ConnectionResponse` gain a `protocol_version` field, absent meaning a client or server from before 0.7. WebSockets carry it as the subprotocol `krpc.1`. The server rejects an unsupported version with a new `ConnectionResponse` status and a message naming the versions it supports. `KRPC.Status` reports the version of the connection.

A 0.7 server serves a client with no version as version 1, with a warning in the log, so 0.6 clients that work today keep working. A 0.7 client rejects a server that reports no version. 0.8 bumps the version to 2. Each transport keeps its handshake framing unchanged, so a client of any version gets an error it can read.

Only the protocol version decides compatibility. The release versions of the server and clients become informational, and services stay unversioned. Part of #906.

Design: [protocol-version.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/protocol-version.md)
