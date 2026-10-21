# Add request ids to RPC requests and responses

A response is matched to its request by position only. A client cannot pipeline calls, a yielding RPC such as `WarpTo` blocks every other call on the connection, and an interrupted call leaves the client reading the previous call's response for good.

Add an id to each request, echoed in its response. Clients match responses by id, which fixes the desynchronized connection and lets several threads send at once. Pipelining and out-of-order completion follow later as negotiated additions. The ids land with the single connection (#<single-connection>), whose client reader matches by id. Part of #906.

Design: [request-ids.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/request-ids.md)
