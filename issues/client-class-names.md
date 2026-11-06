# Clients: use `Connection` for the entry point in every client

The threaded clients share a design, and name two of its layers differently:

| Layer | C++, Python, Lua | C#, Java |
| --- | --- | --- |
| Entry point | `Client` | `Connection` |
| Framing | `Connection` | `MessageReader` |

`Connection` therefore means a different layer depending on the client. This makes the shared client design page and cross-client changes harder to follow.

`Connection` fits the API of the entry point. `krpc.connect()` returns the object and `close()` ends it. The Python and Lua guides already say that `close()` "closes a connection", on a class named `Client`. The errors are `ConnectionError` and `ConnectionException`, and C-nano passes a `krpc_connection_t` to every call.

Programs never use the framing layer, so it takes a new name. `Transport` matches the term the client design pages and C-nano use for TCP/IP, local sockets and serial.

Proposal:

| Client | Change | Effect |
| --- | --- | --- |
| C++, Python, Lua | `Connection` to `Transport`, `LocalConnection` to `LocalTransport` | Internal. Goes first, to free the name |
| C++, Python, Lua | `Client` to `Connection` | **Breaking**, softened by an alias. The public class, in generated C++ and Python stubs and the docs |
| C#, Java | `MessageReader` to `Transport` | Internal. `MessageReader` only reads from a stream it is given, so the socket and the writes move into it from `Connection` |
| C-nano | None | Already `krpc_connection_t` |

The C# and Java public APIs do not change. `doc/src` has 33 lines naming `krpc::Client`, and the Python and Lua guides link `krpc.client.Client` and `krpc.Client` throughout.

Points to settle:

- **Deprecation.** `using Client = Connection` in C++ and `Client = Connection` in Python and Lua keep existing code working, for one deprecation cycle.
- **`krpc.Connection` in Python.** `krpc/__init__.py` imports the framing class under this name today, so the name changes meaning instead of disappearing. A program constructing it directly breaks. The modules also move: `krpc/connection.py` to `krpc/transport.py`, then `krpc/client.py` to `krpc/connection.py`.
- **C++ ordering.** [cpp-client-lifetime.md](cpp-client-lifetime.md) reworks how `krpc::Client` is held. The rename goes after it, to avoid conflicts between the two.
- **C# and Java scope.** Moving the socket and the writes is a refactor these clients do not need for their API. The alternative is to leave `MessageReader` as it is, and record it on each client's design page.

The client design pages update with the change.
