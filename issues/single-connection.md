# Merge the RPC and stream connections into one

Milestone: 0.8.0 · Labels: enhancement, protocol, server, client

Each client opens two connections: one for RPCs and one for stream and event updates. TCP/IP, websockets and the local socket transport all carry this split, and every client pairs the two by a client id. Replace it with one bidirectional connection that carries responses and stream updates, read by a demultiplexing reader in each client.

This is a breaking change to the wire protocol and to connection setup in every client. It lands with request ids (#<request-ids>), which needs the same reader. Part of #906.

Design: [single-connection.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/single-connection.md)
