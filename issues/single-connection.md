# Merge the RPC and stream connections into one

Each client opens two connections: one for RPCs and one for stream and event updates. TCP/IP, websockets and the local socket transport all carry this split, and every client pairs the two by a client id. Replace it with one bidirectional connection that carries responses and stream updates, read by a demultiplexing reader in each client.

This is a breaking change to the wire protocol and to connection setup in every client, with no transition: the server drops the two-connection protocol in the same release. It lands with request ids (#<request-ids>), which needs the same reader, and bumps the protocol version (#1162) to 2. Part of #906.

Design: [single-connection.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/single-connection.md)
