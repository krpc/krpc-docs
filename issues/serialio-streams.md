# Streams and events over serial IO

The single connection (#<single-connection>) carries stream updates on the RPC connection, but streams over serial IO are unsupported in 0.8. The server does not check for them, so a serial IO client that adds a stream or event gets undefined behavior. A microcontroller polls instead.

They are unsupported because of flow control. The server's write buffer drops the connection and stops the server when it fills, and a fast stream at 9600 baud fills it. The server needs to throttle stream updates to what the port can carry before streams are supported. The protocol needs no change: `stream_update` is already a case of `Message`, so this is additive on protocol version 2.

The cnano client then needs a stream API sized for a microcontroller, decoding updates in its read loop without a thread.

Design: [single-connection.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/single-connection.md), "Streams over SerialIO"
