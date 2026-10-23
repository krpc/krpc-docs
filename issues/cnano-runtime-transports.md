# C-nano: choose the transport at run time, with all of them compiled in

The C-nano client picks its transport with a compile-time define, `KRPC_COMMUNICATION_TCP` or `KRPC_COMMUNICATION_LOCALSOCKET`, with a serial port as the default. The define sets the type of `krpc_connection_t` and `krpc_connection_config_t`, the `krpc_open` that gets compiled, and whether the client is resumable (`KRPC_RESUMABLE`). Two transports therefore cannot be built together, and CMake rejects both options being on.

vcpkg features must be additive, so the per-transport features were rejected in microsoft/vcpkg#54568. The 0.7.0 port is TCP/IP only. It passes `-DKRPC_COMMUNICATION_TCP=ON` and patches `communication.h` to define the same thing, so the installed headers match the library. The port copy in `client/cnano/vcpkg-port/` still carries the old features.

**Proposal.** `krpc_connection_t` becomes a small struct holding a transport table and a handle:

```c
typedef struct {
  krpc_error_t (*read)(uintptr_t handle, uint8_t* buf, size_t count);
  krpc_error_t (*write)(uintptr_t handle, const uint8_t* buf, size_t count);
  krpc_error_t (*close)(uintptr_t handle);
  bool resumable;
} krpc_transport_t;

typedef struct {
  const krpc_transport_t* transport;
  uintptr_t handle;
} krpc_connection_t;
```

Each transport gets its own opener, all declared together:

```c
krpc_error_t krpc_open_serial(krpc_connection_t* connection, const char* port);
krpc_error_t krpc_open_tcp(krpc_connection_t* connection, const char* address, uint16_t port);
krpc_error_t krpc_open_localsocket(krpc_connection_t* connection, const char* path);
```

* The connection is still passed by value, so the generated stubs and every RPC call site are unchanged. It is 4 bytes on AVR.
* `krpc_read`, `krpc_write` and `krpc_close` call through the table. `KRPC_RESUMABLE` becomes `transport->resumable`, and its `#ifdef` branches in `krpc.c` become `if`s.
* The platform decides which openers exist. Socket openers are compiled wherever sockets exist (Windows and POSIX). Arduino keeps a serial opener taking a `HardwareSerial*`, speed and config.
* A custom transport is a `krpc_transport_t` filled in by the program. `KRPC_COMMUNICATION_CUSTOM` is removed, along with the link-time `krpc_open` and its sibling functions.
* An unused transport costs no flash. Only its opener refers to its table, so section garbage collection drops the whole transport.

**Builds.**

* vcpkg: no features and no transport options. The `communication.h` patch is dropped, and the port always links `ws2_32` on Windows. The local socket needs Windows SDK 10.0.17134 or later for `afunix.h`.
* CMake: `KRPC_COMMUNICATION_TCP` and `KRPC_COMMUNICATION_LOCALSOCKET` are removed.
* Bazel: `krpc_cnano_serialio`, `krpc_cnano_tcpip` and `krpc_cnano_localsocket` become one library. The client tests choose the opener from `RPC_PORT` or `RPC_PATH`.
* `test-vcpkg-{linux,windows}.sh`, `test-cmake-*.sh` and `test-consumer/main.c` become one scenario that opens each transport against a dead endpoint.
* `doc/src/cnano/client.rst`, `INSTALL.txt`, the benchmark and the conformance testee move to the new openers.

**Compatibility.** This is a hard break, with one `**Breaking:**` changelog entry. Every `krpc_open` call and every build passing a transport define changes. A shim would have to keep the define-driven types this change removes. Each read and write costs one extra indirect call, which is negligible next to a system call or a serial byte.

Stack it on the single connection work, which already reworks `krpc_close` and adds `krpc_disconnect`, so the close path changes once. Update microsoft/vcpkg's `krpc-cnano` port to 0.8.0 once this is released.
