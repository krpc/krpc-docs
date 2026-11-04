# C-nano: pluggable transports, chosen at run time

**Status:** in review as [PR #1275](https://github.com/krpc/krpc/pull/1275). Issue [#1176](https://github.com/krpc/krpc/issues/1176). Folds in phase 1
of [cnano-arduino.md](cnano-arduino.md).

## Problem

The C-nano client picks its transport with a compile-time define. The define sets the type of
`krpc_connection_t`, the one `krpc_open` compiled, and `KRPC_RESUMABLE`.

 * Two transports cannot be built together. vcpkg features must be additive, so the 0.7.0 port
   ships TCP/IP only and patches `communication.h` to match (microsoft/vcpkg#54568).
 * A platform the client does not know falls through to the POSIX serial backend and fails to
   compile. A microcontroller outside Arduino (ESP-IDF, Pico SDK, STM32 HAL, Zephyr) needs
   `KRPC_COMMUNICATION_CUSTOM`, which replaces the link-time `krpc_open`, `krpc_read`,
   `krpc_write` and `krpc_close` and so cannot sit beside a built-in transport.
 * The Arduino backend takes a `HardwareSerial*`, which excludes the USB ports of the Leonardo,
   Micro and Due, `SoftwareSerial`, and fails to compile on several cores (see
   [cnano-arduino.md](cnano-arduino.md)).

## Design

A transport is a table of functions. A connection is the table plus a handle:

```c
typedef struct {
  krpc_error_t (*read)(uintptr_t handle, uint8_t* buf, size_t count);
  krpc_error_t (*write)(uintptr_t handle, const uint8_t* buf, size_t count);
  krpc_error_t (*close)(uintptr_t handle);  /* may be NULL */
  bool resumable;
} krpc_transport_t;

typedef struct {
  const krpc_transport_t* transport;
  uintptr_t handle;
} krpc_connection_t;
```

 * The connection is passed by value, so the generated stubs and every RPC call site are
   unchanged. It is 4 bytes on AVR.
 * `krpc_read`, `krpc_write` and `krpc_close` call through the table. `KRPC_RESUMABLE` becomes
   `transport->resumable`, and its `#ifdef`s in `krpc.c` become `if`s.
 * A custom transport is a `krpc_transport_t` the program fills in, plus a connection built from
   it. This is the route for any platform the client has no transport for. The handle holds a
   file descriptor, a socket or a pointer to the program's own state.

### Openers

| Platform, detected by | Openers | Table |
| --- | --- | --- |
| `ARDUINO` | `krpc_open_stream(conn, Stream*)`, `krpc_open_serial(conn, Port*, speed)` (C++ template) | `krpc_transport_stream` |
| `_WIN32` | `krpc_open_serial(conn, name)`, `krpc_open_tcp(conn, address, port)`, `krpc_open_localsocket(conn, path)` | `krpc_transport_serial`, `krpc_transport_socket` |
| `__unix__` or `__APPLE__` | as Windows | as Windows |
| anything else | none | none |

 * The built-in tables are public. A program wraps one to add logging or fault injection, which
   is how the conformance testee injects write faults. `KRPC_WRITE_FAULTS` is removed.
 * One source file per transport: `serial.c`, `socket.c`, `stream.c`, and `communication.c` for
   the dispatch. A static link pulls in only the objects a program references, so an unused
   transport costs no code size and, on Windows, needs no `ws2_32`.
 * The Arduino openers are phase 1 of [cnano-arduino.md](cnano-arduino.md): the handle is a
   `Stream*`, `begin(speed)` only, a readiness wait on the port, `<Arduino.h>` in place of
   `<HardwareSerial.h>`. Its close does nothing.
 * `KRPC_BUFFER_SIZE` defaults small under `ARDUINO`, keyed on that macro.
 * An opener clears the connection first, so a failed open leaves no transport. `krpc_connect`
   returns `KRPC_ERROR_IO` for it.
 * On Windows the local socket is built only where `__has_include(<afunix.h>)` holds. Without the
   header, `krpc_open_localsocket` is declared unavailable (`unavailable` on Clang, `error` on
   GCC, `deprecated` plus a link error on MSVC), and the other transports still build.

### Builds

| Build | Change |
| --- | --- |
| CMake | `KRPC_COMMUNICATION_TCP` and `KRPC_COMMUNICATION_LOCALSOCKET` removed. `ws2_32` always an interface link on Windows |
| vcpkg | No features. The `communication.h` patch is dropped. The local socket needs Windows SDK 10.0.17134 (`afunix.h`), and is left out without it |
| Bazel | `krpc_cnano_serialio`, `_tcpip`, `_localsocket` and the `_testee` variants become one library, plus one with `KRPC_ERROR_MESSAGES` for tests |
| Conformance | One testee announcing all three protocols |
| Benchmark | One program, the transport chosen from `KRPC_TEST_LOCALSOCKET_PATH` or `KRPC_TEST_TCPIP_PORT`. `--client-localsocket` removed from the runner |
| CMake and vcpkg test scripts | The transport axis dropped. The consumer opens each transport against a dead endpoint |

## Compatibility

A hard break for 0.8.0. Every `krpc_open` call and every build passing a transport define changes.

| 0.7 | 0.8 |
| --- | --- |
| `krpc_open(&c, "COM3")` | `krpc_open_serial(&c, "COM3")` |
| `-DKRPC_COMMUNICATION_TCP`, `krpc_open(&c, &config)` | `krpc_open_tcp(&c, "127.0.0.1", 50000)` |
| `-DKRPC_COMMUNICATION_LOCALSOCKET`, `krpc_open(&c, path)` | `krpc_open_localsocket(&c, path)` |
| Arduino: `conn = &Serial; krpc_open(&conn, &config)` | `krpc_open_serial(&conn, &Serial, 115200)` |
| `KRPC_COMMUNICATION_CUSTOM` and link-time functions | a `krpc_transport_t` |
| `krpc_connection_config_t` | removed |

Each read and write costs one extra indirect call, negligible next to a system call or a serial byte.

## Out of scope

 * Arduino packaging and the arduino-cli compile matrix: phase 2 of
   [cnano-arduino.md](cnano-arduino.md).
 * More than one open connection: session state stays in file statics.
