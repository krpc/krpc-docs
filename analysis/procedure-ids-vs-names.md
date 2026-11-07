# Procedure Ids Against Names

**Status:** negative result. Clients keep calling by name, and C-nano keeps calling by id.

Measured 2026-11-07 on `main` at the merge of #1288, after #1265 made procedure ids stable.

## Question

Every client but C-nano names its service and procedure with strings. Names were chosen when only
they were stable. Hashed ids are now stable too, so the choice rests on whether ids are faster.

## Result

Ids make no measurable difference to a round trip over TCP/IP or a local socket, in any client. The
one-argument round trip sends 29 bytes in place of 45, and takes the same time.

| Client | Sends in build A | B vs A | C vs A | A spread |
| --- | --- | ---: | ---: | ---: |
| C++ | Names | -0.4% | -0.7% | 0.5% |
| Java | Names | +0.1% | -1.1% | 0.7% |
| C# | Names | +0.9% | +0.6% | 1.4% |
| Python | Names | +1.1% | +0.3% | 1.7% |
| Lua (control) | Names | -0.2% | +0.4% | 1.1% |
| C-nano (control) | Ids | +0.2% | -0.7% | 1.1% |

Each figure is the mean over six measurements: three cases on two transports. A change compares the
best of two runs. A spread is the difference between the two runs of build A.

The controls moved as much as the patched clients. Of the 72 comparisons, one passed the suite's 3%
floor: Python, three arguments, local socket, build C, at +3.2%.

Bytes matter on a slow serial link, where C-nano's choice stands. See [Serial links](#serial-links).

## Builds

| Build | Change | Patch |
| --- | --- | --- |
| A | None: `main` | — |
| B | C++, C#, Java and Python stubs send ids. The server resolves an id to a name, then looks the name up as before | [ids.patch](procedure-ids-vs-names/ids.patch) |
| C | B, and the server looks a procedure up directly by service id and procedure id | [direct-lookup.patch](procedure-ids-vs-names/direct-lookup.patch) |

The patches are experiments, and only cover a plain call through a stub.

| Client | How build B sends ids |
| --- | --- |
| C++, C# | Generated stubs pass id constants to a new `invoke` overload |
| Java | As C++, and it keeps the names for its local return type lookup, so that lookup still costs what it did |
| Python | A table from name to id, filled at connect. Each call pays one dictionary lookup |
| Lua, C-nano | Client code unchanged, as controls. Both still see the server change in build C |

## Method

`//tools/benchmarks:clients` runs each client against its own `TestServer`, over each transport. The
server runs with frame pacing off, a receive timeout of 1000 us and a maximum of 5000 us per update.
A case settles, then takes nine timed loops of 200 ms, and reports the fastest.

The builds ran in the order A B C A B C, to spread drift evenly. The machine is an AMD Ryzen 9
7950X3D with 32 threads.

## Wire Check

`strace` on each client's sends against a `TestServer` confirmed the patches took effect. C# was
only checked on the ids build. The sizes include the framing.

| Client | Case | Build A | Build B |
| --- | --- | ---: | ---: |
| C++, Java, Python | One argument | 45 | 29 |
| C++, Java, Python | Three arguments | 63 | 43 |
| C++, Java, Python | List of 100 values | 382 | 366 |
| C# | One argument, three arguments, list | Not checked | 29, 43, 366 |
| C-nano (control) | One argument, three arguments, list | 29, 43, 366 | 29, 43, 366 |
| Lua (control) | One argument, three arguments, list | 47, 65, 385 | 47, 65, 385 |

These test names are short. `SpaceCenter.Flight_get_MeanAltitude` by name takes 50 bytes for its
request and by id 20, computed from the encoding.

## Limits

* The runs use `TestServer` on localhost, in place of the game.
* A server difference under about 0.3 us per call stays below the 3% floor. The lookup was not timed
  on its own.
* The report flagged two cases of the first run of build A as still settling: C# `round trip`, and
  Java `round trip, list of 100 values`. Both stayed within the floor.
* The figures hold for this machine and this session.

## Other Costs of Ids

* Generated stubs change in every client, and dynamic clients need an id table.
* Name calls stay in the protocol, as an id clash leaves the members callable by name only. See
  [protocol/procedure-ids.md](../design/protocol/procedure-ids.md).

## Serial Links

C-nano is the only client with a serial transport. Its reason for ids is flash and link speed on a
microcontroller. This section asks what ids would give any other client on a serial link, which is
hypothetical, as none has one.

The table is computed, not measured. It uses `SpaceCenter.Flight_get_MeanAltitude` with 10 bits per
byte: 67 bytes for the round trip by name, and 37 by id.

| Baud | Wire time, names | Wire time, ids | Saved per call | Effect on call rate |
| ---: | ---: | ---: | ---: | --- |
| 9600 | 69.8 ms | 38.5 ms | 31.3 ms | Real: at most 14 calls/s against 26 |
| 115200 | 5.8 ms | 3.2 ms | 2.6 ms | None: one call per update either way |
| 921600 | 0.73 ms | 0.40 ms | 0.33 ms | Possibly real: at most 1370 calls/s against 2490, if the client stays inside the receive timeout |

A client slower than the receive timeout gets one call per update, as
[server/recv-timeout-cliff.md](../design/server/recv-timeout-cliff.md) describes. At 115200 baud the
response alone takes about 1.5 ms, over the 1 ms timeout, so ids shorten each call by 2.6 ms and the
rate stays the same.

The 921600 row is an upper bound from wire time alone. Whether the server's receive path holds that
rate over a serial port is unknown. A client on such a link would be on a desktop machine, which
can use TCP/IP.

## Reproducing

[run.sh](procedure-ids-vs-names/run.sh) applies the patches to a clean `krpc` checkout and runs the
six benchmarks. Compare two runs with the suite's tool:

```bash
analysis/procedure-ids-vs-names/run.sh ../krpc results
bazel run //tools/benchmarks:compare -- A1.json B1.json --noise A1.json A2.json
```

The original result files are in [results/](procedure-ids-vs-names/results/). The patches apply to
`main` at the merge of #1288, and a later `main` may need them updated. They change the generated
code, so they are not expected to pass the clientgen golden tests.

## Full Results

Round trip time in microseconds, and each change on the best of two runs:

| Client | Transport | Case | A1 (us) | A2 (us) | B1 (us) | B2 (us) | C1 (us) | C2 (us) | A spread | B vs A | C vs A |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | TCP/IP | round trip | 17.28 | 17.20 | 17.46 | 17.19 | 17.45 | 17.09 | 0.5% | -0.1% | -0.6% |
| python | TCP/IP | round trip, 3 arguments | 18.99 | 18.63 | 19.10 | 18.84 | 18.98 | 18.51 | 1.9% | +1.1% | -0.6% |
| python | TCP/IP | round trip, list of 100 values | 57.14 | 58.12 | 59.24 | 57.14 | 57.68 | 57.59 | 1.7% | +0.0% | +0.8% |
| python | Local socket | round trip | 13.21 | 13.41 | 13.55 | 13.64 | 13.14 | 13.35 | 1.5% | +2.5% | -0.6% |
| python | Local socket | round trip, 3 arguments | 14.46 | 14.78 | 15.09 | 14.75 | 14.99 | 14.93 | 2.2% | +2.0% | +3.2% |
| python | Local socket | round trip, list of 100 values | 52.88 | 54.08 | 53.43 | 53.29 | 52.79 | 53.37 | 2.3% | +0.8% | -0.2% |
| cpp | TCP/IP | round trip | 12.00 | 12.00 | 11.86 | 12.03 | 11.73 | 11.86 | 0.0% | -1.1% | -2.2% |
| cpp | TCP/IP | round trip, 3 arguments | 12.39 | 12.37 | 12.21 | 12.40 | 12.16 | 12.35 | 0.1% | -1.3% | -1.7% |
| cpp | TCP/IP | round trip, list of 100 values | 26.84 | 26.85 | 26.77 | 26.88 | 26.65 | 26.70 | 0.0% | -0.3% | -0.7% |
| cpp | Local socket | round trip | 9.22 | 9.11 | 9.14 | 9.48 | 9.06 | 9.37 | 1.2% | +0.4% | -0.6% |
| cpp | Local socket | round trip, 3 arguments | 9.40 | 9.38 | 9.32 | 9.54 | 9.30 | 9.61 | 0.2% | -0.6% | -0.8% |
| cpp | Local socket | round trip, list of 100 values | 23.94 | 23.56 | 23.68 | 24.09 | 24.25 | 23.97 | 1.6% | +0.5% | +1.8% |
| java | TCP/IP | round trip | 12.94 | 13.05 | 13.15 | 13.24 | 12.86 | 13.14 | 0.9% | +1.6% | -0.6% |
| java | TCP/IP | round trip, 3 arguments | 13.59 | 13.71 | 13.80 | 13.78 | 13.43 | 13.50 | 0.8% | +1.4% | -1.2% |
| java | TCP/IP | round trip, list of 100 values | 28.60 | 28.99 | 28.71 | 28.45 | 28.70 | 29.72 | 1.4% | -0.5% | +0.4% |
| java | Local socket | round trip | 9.67 | 9.68 | 9.62 | 9.70 | 9.49 | 9.68 | 0.2% | -0.4% | -1.8% |
| java | Local socket | round trip, 3 arguments | 9.73 | 9.67 | 9.64 | 9.64 | 9.48 | 9.61 | 0.6% | -0.3% | -1.9% |
| java | Local socket | round trip, list of 100 values | 25.26 | 25.13 | 25.24 | 24.88 | 25.06 | 24.82 | 0.5% | -1.0% | -1.3% |
| csharp | TCP/IP | round trip | 12.79 | 12.46 | 12.63 | 12.74 | 12.59 | 12.72 | 2.6% | +1.4% | +1.0% |
| csharp | TCP/IP | round trip, 3 arguments | 13.14 | 13.34 | 13.34 | 13.39 | 13.14 | 13.32 | 1.5% | +1.5% | -0.0% |
| csharp | TCP/IP | round trip, list of 100 values | 33.89 | 33.80 | 33.76 | 35.51 | 34.09 | 34.14 | 0.3% | -0.1% | +0.9% |
| csharp | Local socket | round trip | 9.99 | 9.97 | 10.17 | 10.35 | 10.02 | 10.31 | 0.2% | +2.0% | +0.6% |
| csharp | Local socket | round trip, 3 arguments | 10.46 | 10.32 | 10.34 | 10.32 | 10.32 | 10.34 | 1.3% | +0.0% | -0.0% |
| csharp | Local socket | round trip, list of 100 values | 31.04 | 31.77 | 31.50 | 31.30 | 31.43 | 31.36 | 2.3% | +0.8% | +1.0% |
| lua | TCP/IP | round trip | 21.87 | 22.31 | 21.91 | 21.90 | 22.10 | 22.09 | 2.0% | +0.1% | +1.0% |
| lua | TCP/IP | round trip, 3 arguments | 25.43 | 25.92 | 25.33 | 25.42 | 25.43 | 25.55 | 1.9% | -0.4% | +0.0% |
| lua | TCP/IP | round trip, list of 100 values | 212.20 | 215.29 | 211.17 | 211.57 | 215.90 | 214.55 | 1.5% | -0.5% | +1.1% |
| lua | Local socket | round trip | 18.00 | 17.94 | 18.06 | 18.07 | 17.90 | 18.01 | 0.3% | +0.6% | -0.3% |
| lua | Local socket | round trip, 3 arguments | 21.47 | 21.58 | 21.39 | 21.70 | 21.65 | 21.60 | 0.5% | -0.4% | +0.6% |
| lua | Local socket | round trip, list of 100 values | 209.14 | 208.42 | 207.32 | 210.21 | 207.77 | 208.84 | 0.3% | -0.5% | -0.3% |
| cnano | TCP/IP | round trip | 12.65 | 12.74 | 12.73 | 12.66 | 12.68 | 12.60 | 0.7% | +0.1% | -0.4% |
| cnano | TCP/IP | round trip, 3 arguments | 13.58 | 13.30 | 13.41 | 13.66 | 13.39 | 13.26 | 2.1% | +0.9% | -0.3% |
| cnano | TCP/IP | round trip, list of 100 values | 33.45 | 33.54 | 33.54 | 34.02 | 33.68 | 33.65 | 0.3% | +0.3% | +0.6% |
| cnano | Local socket | round trip | 9.96 | 10.17 | 9.96 | 10.07 | 9.85 | 10.05 | 2.1% | +0.0% | -1.1% |
| cnano | Local socket | round trip, 3 arguments | 10.30 | 10.38 | 10.22 | 10.32 | 10.32 | 10.07 | 0.7% | -0.8% | -2.2% |
| cnano | Local socket | round trip, list of 100 values | 30.63 | 30.83 | 30.85 | 31.12 | 30.38 | 31.85 | 0.7% | +0.7% | -0.8% |
