# Custom transports in every client

C-nano takes a transport of the program's own: a `krpc_transport_t` table of read, write and close
functions. The other clients only open their built-in TCP/IP and local socket transports, and a
program cannot supply another. Give each of them the same choice.

Examples of what this allows, with no new dependency in the client:

* Serial from a desktop client, through the program's own serial library.
* Bluetooth, or a tunnel the program opens itself, such as TLS. SSL support was closed as "use a
  proxy or tunnel", and this removes the need for a separate process.
* A fake link in a test, which injects faults and delays.

## What Each Client Depends On

C-nano's three functions are enough because it is single-threaded and its calls block. Python, C++,
C# and Java have a reader role moving between threads, so they use more of the socket:

| Behavior | Used for |
| --- | --- |
| Wait until readable, with a timeout | Handshake and stall timeouts, and the reader role |
| Read what is available, as against an exact count | Filling the message buffer |
| Close the sending side only | Sending a `disconnect`, then draining before close |
| A close that wakes a blocked read | Ending the reader thread |

| Client | Where the socket sits | Work |
| --- | --- | --- |
| Python | Behind `Connection`, whose subclasses override `_open`. Uses `select.poll` directly | Small |
| C++ | Behind `Connection`, as an asio generic stream socket with timed reads | Medium |
| C# | `Session` holds the `Socket` and calls `Poll` and `Shutdown` itself, and `NetworkStream` feeds `MessageReader` | Large |
| Java | `MessageReader` holds a `SocketChannel` and uses a `Selector` | Large |
| Lua | Behind `Connection`, single-threaded on luasocket, close to C-nano's contract | Small |

## Approaches

| Approach | Program writes | For | Against |
| --- | --- | --- | --- |
| **A. Timed read interface** | `read(max, timeout)`, `write`, `close`, and an optional half-close | One call replaces the readiness wait and the read. Sockets become one implementation, so there is one code path. No extra thread | Every transport must implement a timeout, and a close that wakes a read |
| **B. Blocking read, with a pump thread** | `read`, `write`, `close`, as C-nano | The simplest contract, and the same in every language | An extra thread and a handoff per message on custom transports. `close` must still wake a blocked read. Two code paths |
| **C. The language's own stream** | Nothing new: `System.IO.Stream`, `InputStream`, a file object | Familiar, and fits existing libraries | Most have no timed read and no half-close, so the timeouts stop working. Differs per language |

A is the recommendation. B can be an adapter on top of A for a link with no timed read, if one turns
up.

## Design Points

* **The program opens the link**, and passes the open transport to a new `connect` form. The handshake
  then runs over it, as it does in C-nano.
* **A resumable flag**, as in `krpc_transport_t`. A link that outlives the client, such as a serial
  line, can hold messages from an earlier session, which the client skips while connecting.
* **Byte streams only.** A transport carries the varint-framed bytes. The server's WebSockets protocol
  frames each message itself with no length prefix, so a byte transport cannot carry it. Whether to
  add a message-level hook is left open until something needs it.
* **Errors.** A transport raises the language's usual error, and the client reports it as its usual
  connection failure.
* **No cost to sockets.** Going through the interface adds one indirect call per read and write.
  Measure with `//tools/benchmarks:clients` against `main`, and hold the built-in transports level.
* **Streams and events over a slow link.** The client does not limit them. Serial's limits are the
  server's, and the guide states them.

## Phases

1. Python and Lua, the two smallest, to prove the interface.
2. C++.
3. C# and Java, which first need the socket moved out of `Session` and `MessageReader`.

Each phase merges on its own. A client left behind records that on its design page.

## Tests

* `client/conformance`: a new `custom-transport` profile, and a testee command that connects through
  a transport written in the client's language, wrapping a TCP socket. The tests cover the handshake,
  a call, stream updates, close sending a `disconnect`, and a link that fails partway through a
  message.
* C-nano joins the profile. Today only its native `test_transport.cpp` covers custom transports.
* A serial example in each guide, not a dependency of the client.

## Documentation

An "Over a Custom Transport" section in each client's guide, as `cnano.rst` has, with an example. The
reason for the interface goes on `client-design.rst`, and each client's differences on its design
page.
