# Add request ids to RPC requests and responses

A response is matched to its request by position only. A client cannot pipeline calls, a yielding RPC such as `WarpTo` blocks every other call on the connection, and an interrupted call leaves the client reading the previous call's response for good.

Add an id to each request, echoed in its response. Clients can then pipeline calls and detect a desynchronized connection. This goes with the single connection (#<single-connection>), since both need the same demultiplexing reader in each client. Part of #906.

Design: [request-ids.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/request-ids.md)
