# A local socket transport, and what else the game's runtime can carry (issue #899)

**Status:** in progress (2026-08-15). Built and tested on Linux, with one Windows build break
outstanding; pull requests not yet raised.
[Issue #899](https://github.com/krpc/krpc/issues/899) asks for more communication protocols; this
settles which of them the game's runtime can actually carry, measures whether a cheaper local
transport is worth having, and records what was built.

Related: [improvements.md](improvements.md) (meta-issue
[#906](https://github.com/krpc/krpc/issues/906), which deliberately left #899 out of scope),
[reverse-streams.md](reverse-streams.md), [single-connection.md](single-connection.md).

## The question

When the game and the client run on the same machine, TCP loopback may not be the cheapest way to
carry the same messages. Whether anything else is *possible* depends on what KSP's Mono runtime can
load and call, and whether anything else is *worth it* depends on where the time in an RPC actually
goes. Both were treated as questions to measure rather than reason about.

## What the game's runtime can do

Probed from inside the game, which reported itself as runtime `4.0.30319.42000`, `mono 5.11.0`, on
Unity 2019.4.18f1. This table is the durable part of this document: it answers "can KSP do X?" with
evidence rather than argument.

| Capability | Result |
| --- | --- |
| AF_UNIX stream sockets | **Yes.** Bind, accept and echo all work. |
| AF_UNIX socket semantics | **Yes.** `NetworkStream.DataAvailable`, `Socket.Poll(0, SelectRead)`, `Receive(SocketFlags.Peek)` and `Socket.Available` all behave exactly as they do on TCP, including a closed peer polling readable and then reading zero bytes. |
| Named pipes, synchronous | **Yes.** |
| Named pipes, `PipeOptions.Asynchronous` | **No** — `NotImplementedException: Asynchronous pipe mode is not supported`. The exception lives in Mono's private `UnixNamedPipe` class; the sibling `Win32NamedPipe` has no such check, so this is Mono's unix backend rather than a Mono-wide gap. |
| Shared memory | **Yes.** A file-backed `MemoryMappedFile` and a named `EventWaitHandle` both work. |
| `netstandard.dll` and the facade set | **Absent.** No `System.Runtime`, `System.Memory`, `System.Buffers`, `System.Threading.Tasks.Extensions`, `System.Runtime.CompilerServices.Unsafe`. |
| `System.Net.Http`, HTTP/2 | **Absent.** No assembly in the install mentions HTTP/2 at all. |
| Shipping extra managed DLLs | **Established.** `Google.Protobuf.dll` and `KRPC.IO.Ports.dll` already ship in `GameData`. |
| Shipping native libraries | **No precedent.** The one native dependency in the repository is used only by out-of-game builds. |

**AF_UNIX needs no `Mono.Posix` dependency.** `Mono.Posix` does ship with the game and does provide
`Mono.Unix.UnixEndPoint`, but an `EndPoint` subclass marshalling a `sockaddr_un` through
`SocketAddress` is about forty lines and works just as well. That matters more than it sounds — see
[Design decisions](#design-decisions).

## Candidates assessed

| Candidate | Verdict |
| --- | --- |
| **AF_UNIX socket** | **Built.** A byte stream, so it drops into the existing `IServer<byte,byte>` layer and the protocol buffer layer above it is untouched. |
| **Named pipe** | **Deferred.** The intended Windows fallback. Cannot be tested here, and the async-mode gap means a pipe transport must assume a reader thread rather than an outstanding asynchronous read. |
| **Shared memory** | **Rejected on design grounds**, though technically available. Its sub-microsecond latency comes from busy-waiting on a ring buffer, and the server reads on the game thread once per fixed update, so it cannot spin. With a blocking wakeup it degrades towards socket latency while adding hand-rolled cross-process synchronization and a crash-recovery problem: a client dying mid-write leaves the ring corrupt, where a socket is closed by the operating system. |
| **ZeroMQ / NetMQ** | **Rejected.** NetMQ ships a real `net47` build, so the target framework was never the obstacle. It needs five assemblies KSP lacks, and its uses of them are core rather than incidental: `System.ServiceModel.Channels.BufferManager` is its buffer pool and `Span<T>`/`ReadOnlySpan<T>`/`Memory<T>` are its message handling. `System.ServiceModel` is WCF; `System.Memory` and `System.Threading.Tasks.Extensions` are facades that collide with Mono 5.11's own in-mscorlib definitions. `AsyncIO.CompletionPort` would also put a second I/O event loop, with its own threads, inside a server that executes only on the game thread. Its `ipc://` transport is AF_UNIX underneath, so it adds a dependency to reach what the server can already reach directly. |
| **gRPC** | **Rejected**, confirming the conclusion already recorded on #899, now with the specific missing assembly named. `Grpc.Net.Client` ships a `net462` build, but every transport type it uses comes from `System.Net.Http` — `HttpClient`, `HttpMessageHandler`, `DelegatingHandler`, the header types — and that assembly is absent. Legacy `Grpc.Core` ships a `net45` build but requires the native `libgrpc_csharp_ext` per platform, for which there is no shipping precedent, and is unsupported upstream. |

The earlier assumption that the target framework was the blocker for gRPC and NetMQ was wrong. The
blocker is the BCL underneath.

## Measuring: the client came first

The server has had extensive performance work; the clients have had none. Measuring a transport
through a client that spends more time in its own dispatch than on the wire would measure the
client, so the Python client was profiled and fixed first.

What was actually costing time, measured rather than guessed:

| Cost | Before | After |
| --- | --- | --- |
| `types.tuple_type(double, double, double)` | 3.345 µs | 0.189 µs |
| `types.class_type(service, name)` | 0.708 µs | 0.147 µs |
| `types.float_type` | 0.608 µs | 0.029 µs |
| `Encoder.encode(3.14, float)` | 1.120 µs | 0.340 µs |
| System calls per RPC | 4 (`select`, `recv`, `recv`, `send`) | 2 (`recv`, `send`) |

A type object was found by building a protocol buffer type message and serializing it to key the
type store with, and the generated stubs name the type of every parameter and return value on each
call — so that was paid several times per RPC. Keying a second index on the arguments instead
removed most of it. Round-trip time fell 7% to 16% depending on argument and return types.

Two findings from that work are worth keeping:

- **The pregenerated stubs were slower than the dynamic fallback** they replace, by up to 10 µs per
  call, because the dynamic path resolves types once into the closure it builds while the stubs
  re-evaluate them per call. Fixing the type store closed the gap to under 3 µs and made
  restructuring the generator unnecessary.
- **A stub sends its default arguments explicitly** where the dynamic path omits them via
  `DefaultArgument` sentinels, which is a wire-size difference rather than a performance bug.
  Changing it would make stubs defer to the server's defaults instead of their own — a behavior
  change under version skew. Left alone.

## Measuring: is the transport worth it

Measured against the game-less test server with one server running at a time, since each polls
continuously and two of them depress both results. Every case is warmed before any is measured;
without that the first case measured absorbs the server's own warmup and reads half again as slow.

Round-trip time, median of three runs, server saturated at 60 updates per second:

| Case | TCP | AF_UNIX | Improvement |
| --- | --- | --- | --- |
| Trivial RPC, no arguments | 19.31 µs | 15.27 µs | 21% |
| Value argument | 21.24 µs | 17.18 µs | 19% |
| Remote object property | 20.67 µs | 16.92 µs | 18% |
| Large payload, 100 kB | 171.84 µs | 108.09 µs | **37%** |

**Calls completed per server update — the number that matters — improved 18% to 26%** (806 → 985,
784 → 970, 869 → 1092). Raw socket echo without kRPC in the way is 12.9 µs on TCP against 7.5 µs on
AF_UNIX.

**The prediction that this would barely move was wrong, and the reason is worth recording.** Tick
quantization only dominates a *latency-bound* call — one RPC, then wait for the next frame. A client
issuing calls back to back is *throughput-bound*, and there the per-RPC transport cost sits directly
in the critical path with nothing to hide behind. Both regimes are real; the earlier reasoning
covered the first and the measurement covered the second.

**Batching is still an order of magnitude larger.** Ten calls in one request take 17–22 µs against
roughly 200 µs issued singly, and fifty take about 40 µs against roughly 1000 µs — 10× and 23×,
against the transport's 20%. So the ranking in [reverse-streams.md](reverse-streams.md) stands even
though the transport is worth having: the two are complementary, and batching is where the larger
win remains.

The honest summary for release notes: a local transport buys around 20% more calls per update for a
throughput-bound client and around 37% on large payloads, and changes nothing for a latency-bound
one.

## What was built

Three changes, stacked in this order. Pull requests are not yet raised; the changelog entries carry
predicted issue numbers that need confirming when they are.

1. **Python client performance.** Independent of the transport question and worth having on its own.
   Also replaces a performance test that printed a rate and asserted nothing with one that measures a
   set of calls and fails only on a collapse, so a regression cannot pass unnoticed.
2. **The server transport, and the Python client.** The byte transport, a `Protocol` enum entry, the
   settings and server-window surface, test server support, and `krpc.connect_local`.
3. **The remaining clients.** C#, C++, Lua and cnano.
4. **The Java client**, preceded by moving the build to JDK 25 so the JDK's own unix socket
   address type is available. The JDK move is a breaking change for consumers and is worth keeping
   as its own change ahead of the transport it enables.

### Design decisions

| Decision | Why |
| --- | --- |
| Write `UnixEndPoint` in the tree rather than reference `Mono.Posix` | One source then serves both the game's .NET Framework build and the .NET 8 build the tests run against, so the tested path is the shipped path. A `#if` fork would leave the tested path and the shipped path different, and the automated tests only ever exercise the latter. |
| Reuse `TCPStream` and `TCPClient`'s connectedness idiom unchanged | The probe established that a unix socket reports waiting data and a departed peer identically. An assumptions test pins this, so a runtime where it differs fails there rather than somewhere obscure. |
| One `Protocol` enum entry, appended | The server editor casts the combo box index straight to the enum, so order is load-bearing and per-OS filtering of the list would corrupt saved configurations. |
| Sockets default to a per-user directory | `XDG_RUNTIME_DIR` where set, a per-user temporary directory otherwise. Access is then controlled by the permissions on the path, and no network port is opened. |
| Check the path length explicitly | A path longer than the kernel's address structure is reported by `bind` as nothing more specific than an invalid argument. This is not theoretical: it fired first as a build sandbox path far longer than a socket address can hold. |
| Open the stream connection only after the RPC connection is accepted | Preserves existing behavior. Opening both up front leaks the stream connection when the RPC handshake is rejected — which surfaced as the test server dying of an unhandled broken pipe. |
| Run each client's existing test suite over both transports | Stronger than a bespoke wire-level suite and far less code: the Python suite alone is 205 tests over the new transport for one build target. |

The wrong-server error message named a port number, which is no longer the only way to name an
endpoint, so it now mentions the socket path as well. That string is asserted by five client test
suites and by two server tests that check the response's exact byte length.

## Client support

| Client | Entry point | Notes |
| --- | --- | --- |
| Python | `krpc.connect_local` | Opening the socket is the only transport-specific part. |
| C# | `Connection.ConnectLocal` | Moved from `TcpClient` to `Socket` so both transports share everything above the socket. Needs the same in-tree endpoint, as its .NET Framework profile has none. |
| C++ | `krpc::connect_local` | `Connection` holds a protocol-agnostic asio socket. It is opened by connecting one of the specific protocol and handing over the descriptor, which keeps each endpoint type where it belongs and avoids a clang-analyzer false positive on asio's generic endpoint. |
| Lua | `krpc.connect_local` | Uses luasocket's `socket.unix`, which it builds on the platforms that have unix sockets. |
| cnano | `KRPC_COMMUNICATION_LOCALSOCKET` | A socket is read and written through the same calls as a serial port, so only opening it differs. Not auto-detected, as a serial port remains the usual choice where both exist. |
| Java | `Connection.newLocalInstance` | `java.net.UnixDomainSocketAddress` needs JDK 16 or later, so the build moved from JDK 11 to 25 first. Breaking for consumers below that, and the reason the client's own sockets moved from `Socket` to `SocketChannel`. |

## Windows

The transport ships as Linux and macOS only, so there is no feature to test on Windows. What does
need testing there is the collateral: making room for a second transport changed the connection
layer of every client, and those changes reach Windows users over TCP.

### Confirmed: the C++ client no longer builds on Windows

`client/cpp/src/connection.cpp` names `asio::local::stream_protocol` unconditionally. asio defines
`ASIO_HAS_LOCAL_SOCKETS` only off Windows, and `asio/local/stream_protocol.hpp` declares nothing
without it, so the type does not exist under MSVC. Reproduced on Linux by disabling the same
feature:

```
$ bazel build //client/cpp:krpc --copt=-DASIO_DISABLE_LOCAL_SOCKETS
client/cpp/src/connection.cpp:56:28: error: no member named 'local' in namespace 'asio'
client/cpp/src/connection.cpp:57:58: error: no member named 'local' in namespace 'asio'
```

`connection.cpp`, `krpc.cpp` and `connection.hpp` all ship in the release archive, so this breaks
anyone building the released client on Windows, not just CI. The fix is to guard `LocalConnection`
behind `ASIO_HAS_LOCAL_SOCKETS` and give `connect_local` a defined behavior where the guard fails.
It has to land before any other Windows result means anything, since both Windows C++ jobs stop at
the compile.

### The Windows coverage that exists

Four CI jobs run on `windows-latest`, all MSVC and vcpkg package builds of a release archive:
cnano and C++, each by CMake and by vcpkg. Bazel never runs on Windows, so no client test suite,
no core tests and no lint run there. Reproducing those jobs locally needs MSVC, vcpkg
(`protobuf`, `asio`, `nanopb`), CMake and bash.

### What has no Windows coverage at all

| Change | Risk on Windows | How to test |
| --- | --- | --- |
| C#: `TcpClient` replaced by `Socket` plus `NetworkStream`, `StreamManager` takes a stream | The `net472` assembly is what a .NET Framework consumer uses and no suite runs it; the tests run the `net8.0` build | Connect, stream and dispose against the test server on .NET Framework |
| Java: JDK 11 to 25, `Socket` to `SocketChannel` | Breaking for every consumer, not only on Windows | Build and connect with JDK 25 |
| Python: buffered reads, one `recv` per message rather than one per byte of prefix | Platform independent, low risk; `connect_local` fails with `AttributeError` on `socket.AF_UNIX` rather than a kRPC error | Run the suite over TCP |
| Lua, cnano | Both guard the new path (`require` inside the open call, an opt-in define excluded from auto-detect), so the Windows path is untouched | Covered by the cnano CI jobs |
| Mod: the protocol list offers "Protobuf over local socket" everywhere | `LocalSocketServer.Start` catches only `SocketException` and `IOException`, so a `PlatformNotSupportedException` or `ArgumentException` from the runtime escapes into the UI | Select the protocol in a Windows KSP install and start the server |

Filtering the protocol list per OS is already ruled out above, because the editor casts the combo
box index straight to the enum. So the option stays visible on Windows and the requirement is that
choosing it fails with a clear message rather than an unhandled exception.

### Could AF_UNIX itself work on Windows

Windows has had AF_UNIX since Windows 10 1803, but the pieces do not line up:

| Piece | AF_UNIX on Windows |
| --- | --- |
| KSP's Mono, the server | Unknown. Needs the probe from [What the game's runtime can do](#what-the-games-runtime-can-do) run on a Windows install. |
| .NET Framework, the C# client's `net472` build | **No.** Unix sockets arrived in .NET Core 2.1. |
| .NET 8, the C# client's other build | Yes, on Windows 10 1803 or later. |
| JDK 16 or later, the Java client | Yes. This is the one client that would work as written. |
| asio, the C++ client | **No.** Compiled out, as above. |
| CPython | **No.** `socket.AF_UNIX` is not exposed on Windows. |
| luasocket | **No** `socket.unix` build. |
| cnano | Would need `afunix.h` and winsock in place of `sys/un.h`. |

So even a positive probe result buys only the Java client and a .NET 8 C# client. The named pipe
fallback, deferred above, remains the route to Windows rather than AF_UNIX.

### Loose ends found reading for this, not Windows specific

- Python's `DEFAULT_RPC_PATH` and `DEFAULT_STREAM_PATH` are `/tmp/krpc/rpc` and `/tmp/krpc/stream`,
  where the server and the C#, C++ and Java clients all derive `$XDG_RUNTIME_DIR/krpc/<name>`
  falling back to `<tmpdir>/krpc-<user>/<name>`. The Python default can never match the server's.
- The C# local socket path is exercised only on `net8.0`. The shipped `net472` assembly's copy of it
  is untested on any platform.

## Open

- **Windows.** See [Windows](#windows) above: one confirmed build break to fix, a regression surface
  with no automated coverage, and the runtime probe still to run on a Windows install. The transport
  ships as Linux and macOS only until then, and TCP remains the default everywhere.
- **The named pipe fallback** has not been built, and is what Windows support would rest on.
- **Batching** ([reverse-streams.md](reverse-streams.md)) remains the larger performance lever and is
  unaffected by any of this.
