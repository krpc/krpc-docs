# C-nano on Arduino: board support and a build test

**Status:** proposal. Depends on [#1176](https://github.com/krpc/krpc/issues/1176) (C-nano
transport chosen at run time), which lands first. No GitHub issue yet.

## Problem

The Arduino library in the Library Manager has not compiled since 0.5.4. No build compiles it with
an Arduino toolchain, so nothing caught it. The findings below are from 2026-11-04, with
arduino-cli 1.5.1 and the official cores.

**Broken includes.** `tools/release/63-release-arduino.py` puts the nanopb headers in
`src/krpc_cnano/`, as the kRPC headers include `<krpc_cnano/pb.h>`. The nanopb sources sit in `src/`
and include `"pb_common.h"` by bare name. Every sketch fails:

```
src/pb_common.cpp:6:10: fatal error: pb_common.h: No such file or directory
```

The Arduino builder resolves a missing header from any other installed library. A user with the
Nanopb library installed gets a working build, which hid the bug.

**Boards.** The Arduino transport holds a `HardwareSerial*` and calls `begin(speed, config)`:

| Board | Core | Result with the includes fixed |
| --- | --- | --- |
| Uno, Mega | `arduino:avr` | builds |
| MKR Zero | `arduino:samd` | fails: `HardwareSerial` is in `namespace arduino`; including `<Arduino.h>` fixes it |
| Uno R4 Minima | `arduino:renesas_uno` | as MKR Zero |
| Due | `arduino:sam` | fails: `HardwareSerial` declares only `begin(unsigned long)`, since #487 |
| Leonardo, Micro | `arduino:avr` | `Serial` is `Serial_ : Stream`, not a `HardwareSerial`, so `&Serial` does not convert |

 * The `config` argument of `begin` has a different type on each core: `uint8_t` on AVR, `uint16_t`
   in ArduinoCore-API (SAMD, Renesas, mbed), `UARTModes` on SAM's `UARTClass`.
 * `Stream` is the base class of every serial port on every core: hardware UARTs, USB CDC `Serial_`
   and `SoftwareSerial`.
 * `krpc_open` waits with `while (!*connection)`, which tests the pointer, not the port. A USB port
   is never waited for.

## Phase 1: Arduino transport on #1176

#1176 makes `krpc_connection_t` a `{transport table, handle}` pair, with one opener per transport.
It proposes an Arduino serial opener taking a `HardwareSerial*`, speed and config. This phase
refines that opener, and #1176 is updated to match.

| Part | Arduino transport |
| --- | --- |
| Handle | `Stream*` |
| Read | `Stream::readBytes`, as today; EOF when the serial timeout passes with no byte |
| Write | `Stream::write` |
| Close | nothing, as `Stream` has no `end()` |
| Resumable | true |

Two openers. Arduino builds are C++, so `krpc_open_serial` is a template over the port's class:

```cpp
// A stream the sketch has started, e.g. after Serial.begin(115200, SERIAL_8E1)
krpc_error_t krpc_open_stream(krpc_connection_t* connection, Stream* stream);

// Starts the port with 8N1 framing and waits for it to be ready
template <typename Port>
krpc_error_t krpc_open_serial(krpc_connection_t* connection, Port* port, uint32_t speed);
```

 * `begin(speed)` exists on every serial class. The config argument is dropped, as its type differs
   on each core. Other framing is `begin` called by the sketch, then `krpc_open_stream`.
 * The readiness wait is `while (!*port)`. `#ifdef ARDUINO_ARCH_*` branches appear only where a core
   differs, and the compile matrix in phase 2 finds them. The known case is a class without
   `operator bool`, such as SAM's `HardwareSerial`.
 * `communication.h` includes `<Arduino.h>`, not `<HardwareSerial.h>`.
 * Any `Stream` works, so `Serial1`, `SoftwareSerial` and the USB ports of the Leonardo, Micro and
   Due all open.
 * The host test `//client/cnano:communication-arduino` builds against a stand-in `test/Arduino.h`,
   with a `Stream` and a port class. It covers both openers and the readiness wait.
 * `doc/src/cnano.rst`, the `KRPC_COMMUNICATION_ARDUINO` reference text and
   `doc/src/scripts/cnano/ConnectingArduino.ino` move to `krpc_open_serial`, plus a short
   `krpc_open_stream` example with custom framing.
 * Changelog: the API change folds into #1176's breaking entries. New entries: support for the
   Leonardo, Micro, Due, MKR and Uno R4 boards, and for `Serial1` and `SoftwareSerial`.

## Phase 2: packaging in Bazel, and an arduino-cli build test

The library is packaged by Bazel and compiled in CI, as the C-nano CMake and vcpkg builds are
(`client/cnano/test-cmake-linux.sh`, `test-vcpkg-linux.sh`).

**Package.** `//client/cnano:arduino` builds `bazel-bin/client/cnano/krpc-arduino-<version>.zip`:

| Path in the zip | From |
| --- | --- |
| `kRPC/library.properties` | `client/cnano/arduino/library.properties.tmpl`, `%VERSION%` substituted as `:cmake` does |
| `kRPC/src/krpc_cnano/` | the C-nano headers, the generated service headers and `krpc.pb.h`, plus the nanopb headers |
| `kRPC/src/*.cpp` | the C-nano and nanopb `.c` sources, renamed |
| `kRPC/examples/Connecting/Connecting.ino` | `doc/src/scripts/cnano/ConnectingArduino.ino` |
| `kRPC/LICENSE`, `kRPC/COPYING` | as the C-nano archive |

A genrule over `@c_nanopb//:srcs` carries out the steps the release script does today:

 * Rewrite the nanopb sources' `#include "pb*.h"` to `#include "krpc_cnano/pb*.h"`. This is the fix
   for the broken includes.
 * Rename `.c` to `.cpp`, as the Arduino backend in `communication.c` is C++.
 * Prepend `#define PB_NO_ERRMSG` to `pb.h`, to save flash.

`pkg_zip` (`tools/build/pkg.bzl`) assembles the zip with a `path_map`. The `client-cnano` CI
artifact carries it.

**Test script.** `client/cnano/test-arduino.sh ARCHIVE [BOARD]`, shaped like
`test-cmake-linux.sh`. With no board, it runs every board.

 * Unzip into a fresh `ARDUINO_DIRECTORIES_USER`, so no other library can supply a header.
 * Install the cores pinned in `client/cnano/arduino-cores.txt`, one `core@version` per line.
 * `arduino-cli compile --fqbn <board>` each sketch in `client/cnano/test-arduino/`:

| Sketch | Covers |
| --- | --- |
| The library's example | the client guide's code |
| `AllHeaders`, generated from `src/krpc_cnano/services/` | every service header, compiled for the board |
| `Ports` | `Serial`, `Serial1` where the variant has it, `SoftwareSerial` on AVR, `krpc_open_stream` |

Boards, from the official cores only. Each is confirmed locally before it joins the list:

| Core | Boards |
| --- | --- |
| `arduino:avr` | `uno`, `leonardo`, `mega` |
| `arduino:megaavr` | `nona4809` (Nano Every) |
| `arduino:sam` | `arduino_due_x` |
| `arduino:samd` | `mkrzero` |
| `arduino:renesas_uno` | `minima` |
| `arduino:mbed_nano` | `nano33ble` |
| `arduino:mbed_rp2040` | `pico` |

**CI.** The job `linux-build-client-cnano-arduino` is a sibling of
`linux-build-client-cnano-vcpkg`, with the same `needs` and push-skip conditions.

 * Download a pinned `arduino-cli` release and check its SHA-256.
 * Cache `~/.arduino15`, keyed on `arduino-cores.txt` and the `arduino-cli` version.
 * One step per board: `test-arduino.sh krpc-arduino-*.zip <fqbn>`.
 * `CI-Guide.md` gets the job and its cache row.

**Release.** `63-release-arduino.py` builds `//client/cnano:arduino` and runs `test-arduino.sh` on
it. It then replaces the `krpc-arduino` working copy's tree with the zip's, keeping `.git` and
`README.md`, and commits and tags as today.

**Local runs.** The Arduino IDE 2 AppImage bundles `arduino-cli`:

```bash
./arduino-ide_*.AppImage --appimage-extract resources/app/lib/backend/resources/arduino-cli
```

The AppImage itself needs `--no-sandbox` on Ubuntu with
`kernel.apparmor_restrict_unprivileged_userns=1`.

## Release

A fix reaches users only through a new tag of `krpc/krpc-arduino`, which the Library Manager
indexes. #1176 is a hard break for 0.8.0, so the first tag with the new transport is 0.8.0.

A 0.7.1 tag is an option: 0.7.0 with only the include rewrite. It fixes the Uno and Mega for
current users.

## Verification

 * Negative control: with the include rewrite removed, `test-arduino.sh` fails on `pb_common.h`.
 * The zip installs in the IDE (Sketch > Include Library > Add .ZIP Library) and the example
   verifies.
 * A sketch on hardware, connected to KSP over serial, for each board family to hand.

## Prior attempt

A branch made before #1176 fixed the includes in the release script, included `<Arduino.h>`, and
added a release step compiling sketches with arduino-cli. It confirmed the include rewrite and the
`<Arduino.h>` fix: the guide sketch and one including every service header built for Uno, MKR Zero
and Uno R4 Minima. The branch was dropped, as this design supersedes it.
