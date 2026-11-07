# MicroPython client

Add a client for MicroPython, for boards such as the Raspberry Pi Pico. A program on the board reads
switches and drives displays in Python, over a serial link or Wi-Fi.

C-nano is the only client for microcontrollers today, and it needs C. The Python client needs a full
CPython, which a Raspberry Pi 4 or 5 has and a Pico does not.

## Why the Python Client Does Not Fit

| Limit | Python client | Pico |
| --- | --- | --- |
| Protobuf | Depends on `google.protobuf` | MicroPython does not have it |
| Service loading | Calls `GetServices` at connect and builds every stub. The bundled services have 2198 procedures, about 1.7 MB of definitions as JSON | 264 KB of RAM on a Pico, 520 KB on a Pico 2 |
| Standard library | `typing`, `ast`, `enum`, `weakref`, `threading`, `queue` and others | Missing or partial |
| Size | About 13,500 lines, 588 KB of source, before stubs | 2 MB or 4 MB of flash |

The Python client was not tried on a board. These limits come from reading its imports and its
connect path.

## Approaches

| Approach | For | Against |
| --- | --- | --- |
| **A. Pure MicroPython, generated stubs** | Installs with `mip` or by copying files. Python all the way down. Works on any MicroPython board | A new encoder, decoder and `clientgen` target to maintain. Slowest to run, and stubs may not fit |
| **B. Native module wrapping C-nano** | Reuses a tested protocol implementation. Smaller and faster per call | Built per firmware and architecture. Hard to install. C-nano's generated C stubs still need a Python binding layer |
| **C. Trim the Python client** | Shares code | Rejected: the dynamic stubs and protobuf are its core |
| **D. No new client: C-nano from C on the Pico** | No new work, if it works | Not Python. Pico support is only proposed so far, in [cnano-arduino.md](../design/cnano-arduino.md) |

A is the recommendation, if the stubs fit. B is the fallback.

## Design for A

| Decision | Choice | Reason |
| --- | --- | --- |
| Calls | By id | Strings cost scarce memory and link time, as in C-nano. [The benchmark that kept names in other clients](../analysis/procedure-ids-vs-names.md) measured desktop transports |
| Stubs | From `clientgen`, for the services a program selects | No `GetServices` at connect |
| Distribution | `.mpy` bytecode from `mpy-cross` | Code runs from flash in place of RAM. The bytecode version has to match the firmware |
| Encoding | A small hand-written encoder and decoder | The Lua client already hand-encodes its call messages |
| Threads | None: a call writes its request and reads its response | `_thread` is limited on these boards. Lua and C-nano already work this way |
| Transports | Serial first (`machine.UART`, USB CDC), then TCP on a Pico W | See below |

Serial carries no streams or events, so the client leaves out those profiles there, as C-nano does.
The server's serial default is 9600 baud. At 115200 a call already falls to one per server update, as
[the serial table](../analysis/procedure-ids-vs-names.md#serial-links) shows.

## To Check First

**Whether the stubs fit.** This decides between A and B, so it comes before any other work. Generate
`SpaceCenter` stubs, compile them with `mpy-cross`, and load them on a real Pico and Pico 2. Then
record the flash used, the RAM after import, and the time for one call over serial.

`SpaceCenter` alone may be too large. Selecting single classes or procedures would then need a new
`clientgen` option, and the set of classes a stub needs has to be worked out from its signatures.

## Tests

* A testee on MicroPython's Unix port, so the conformance suite runs in CI with no board. The suite's
  serial setup has to be checked against it.
* A build check that the stubs compile with `mpy-cross`.
* A manual run on a Pico before each release, as CI has no board.

## Documentation

A guide page, a design page and a row in the shared comparison table, as for any client. The
conformance `unsupported.txt` lists what the language cannot carry out.
