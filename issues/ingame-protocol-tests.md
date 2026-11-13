# In-game tests for every communication protocol

The in-game tests are service tests, and they all connect with the Python client over TCP. Websockets, serial IO and local sockets are never run in the game. A release can ship with one of them broken in the game and every test passing.

Add a small in-game suite that connects over each protocol. It covers what `TestServer`, the conformance tests and the core unit tests cannot reach, and does not repeat what they check.

## What only the game reaches

`TestServer` and the core unit tests run on .NET 10, against the net10 `KRPC.Core`. The mod runs the net472 build on KSP's Mono, so the two differ in runtime, in libraries and in how servers are created.

| Only in the game | Why it can break there | Covered today |
|---|---|---|
| The net472 transports on KSP's Mono: `System.Net.Sockets`, the websockets handshake, unix sockets | Mono's class libraries, not .NET's. For example, Mono leaves a socket file behind when a bound unix socket closes, and .NET removes it | TCP only |
| Serial IO through `KRPC.IO.Ports` and KSP's `libMonoPosixHelper` | A separate implementation from the `System.IO.Ports` package that `TestServer` uses, with native calls into KSP's own helper | None |
| `ConfigurationFile` loading `settings.cfg`, then `Configuration.Server.Create` | `TestServer` builds its servers directly from its command line, so the settings keys and their parsing are unused | TCP only |
| `Addon` auto-starting several servers and accepting clients | `TestServer` has its own loop and always accepts. `Core.StartAll` stops at the first server that fails, so one bad server blocks the ones listed after it | One server |
| Servers across scene changes, and `NoGameAddon` stopping them at the main menu | Sockets are stopped and bound again on Mono, in game scene order | Scene changes, over TCP only |

## Out of scope

 * Protocol behavior: framing, malformed input, handshake errors, fragmentation and timeouts. The core unit tests and `client/conformance/` cover these, and they are the same code on both builds.
 * Streams over websockets. The conformance tests lack these as well, and [conformance-coverage-gaps.md](conformance-coverage-gaps.md) tracks that.
 * The server window and `EditServer`, which need UI automation.
 * Real serial hardware. The tests use a socat pty.
 * KSA, which runs the net10 build and has its own test suite.

## Plan

### Phase 1: run every server in the test game

 * Add a websockets server, a local socket server and a serial server to `tools/settings.cfg`, after the TCP server. `krpctest` connects to the TCP server as it does now.
 * List the serial server last, so that a missing port cannot stop the others from starting. Without its port it fails to auto-start and logs an error at each scene change. Nothing in `krpctest` fails on that error.
 * Add a session fixture that starts socat, with a pty at the path in `settings.cfg`, then changes scene so that `Addon` auto-starts the serial server. It reuses `start_socat` from `tools/build/serverprocess.py`, adapted to give the fixed path. socat stays up for the whole run, so the serial server never loses its port during a run.

The ports and paths are fixed, as `settings.cfg` is a static file. If the serial error at each scene change proves a nuisance, `install.py` can add the serial entry only when socat is available.

### Phase 2: a client for each protocol

 * **Local socket:** `krpc.connect_local`.
 * **Serial IO:** the Python client has no serial transport. Have socat link the pty to a unix socket, and connect with `krpc.connect_local`. This needs no client code, and should work if the serial server takes the same connection request. Confirm that first. If it does not, use the C-nano conformance testee, the only client with serial IO.
 * **Websockets:** a helper of about 20 lines in the test file, using `websocket-client`, that sends a `Request` and decodes the `Response`. The base is the testee in `client/websockets/conformance`. `krpctest` gains the dependency.

### Phase 3: the tests

These go in `server/test/test_protocols.py`, and `pytest.ini` gains `server/test` in `testpaths`. Each runs once per protocol, except the two marked as all protocols.

| Test | Checks |
|---|---|
| Call a procedure | An RPC that reads game state, such as `SpaceCenter.UT`, runs in the game over this transport |
| Large response | `KRPC.GetServices` arrives whole, as its size crosses websockets frame and serial buffer sizes |
| Stream | A stream delivers two updates. Local socket and serial IO only, as the websockets helper has no streams |
| Reconnect | A second client connects after the first disconnects |
| Scene change | A client stays connected across a scene change, and its next call succeeds. All protocols, one connection each |
| Stop and restart | After the main menu and loading the save again, every server accepts a client. This binds again on Mono, over the stale socket file. All protocols. It needs a way back to the main menu, added to `TestingTools` if none exists, and must drop the connection `krpctest` caches |

Serial accepts one client at a time, so its tests run in sequence and each closes its client.

### Phase 4: other platforms

 * Skip the serial tests on Windows, which has no socat, or when socat is missing. A paired virtual port such as com0com would be needed to test `WinSerialStream`, so that stays a manual check.
 * Check whether the local socket tests run on Windows, where KSP's Mono may not support them. Skip them there if not.

## Verification

 * Each new test fails when its server entry is removed from `settings.cfg`, as a negative control.
 * The suite passes on Linux with `bazel run //:test-ingame -- server/test/test_protocols.py`, and with `--no-launch` against a game from `//:run-ksp`.
 * The suite adds about a minute or less, not counting the game launch, and the service tests still pass with the extra servers running.
 * Windows run through the Windows session.

## Related

[core-serial-ports.md](core-serial-ports.md) moves `KRPC.IO.Ports` into `KRPC.Core`. Landing this suite first gives that move a test of its behavior in the game. It also needs to settle the socat question that issue raises: the stock serial class is expected to fail on a pty, and this suite would show it.

[conformance-driver.md](conformance-driver.md) has an open question about what a serial client must wait for, and the serial tests here may hit the same wait.
