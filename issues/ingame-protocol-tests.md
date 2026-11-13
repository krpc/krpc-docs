# In-game tests for local sockets and server restarts

The in-game tests are service tests, and they all connect with the Python client over TCP. Local sockets are never run in the game, and nor is a server stopping and starting again. A release can ship with either broken in the game and every test passing.

Add a small in-game suite for these. It covers what `TestServer`, the conformance tests and the core unit tests cannot reach, and does not repeat what they check.

## What only the game reaches

`TestServer` and the core unit tests run on .NET 10, against the net10 `KRPC.Core`. The mod runs the net472 build on KSP's Mono, so the two differ in runtime, in libraries and in how servers are created.

| Only in the game | Why it can break there | Covered today |
|---|---|---|
| The net472 transports on KSP's Mono: `System.Net.Sockets` and unix sockets | Mono's class libraries, not .NET's. For example, Mono leaves a socket file behind when a bound unix socket closes, and .NET removes it | TCP only |
| `ConfigurationFile` loading `settings.cfg`, then `Configuration.Server.Create` | `TestServer` builds its servers directly from its command line, so the settings keys and their parsing are unused | TCP only |
| `Addon` auto-starting several servers and accepting clients | `TestServer` has its own loop and always accepts. `Core.StartAll` stops at the first server that fails, so one bad server blocks the ones listed after it | One server |
| Servers across scene changes | `Addon` is created again at each scene change, and the servers it holds statically keep running | Over TCP only |
| `NoGameAddon` stopping the servers at the main menu, and `Addon` starting them on the next load | Each server stops and binds again on Mono. A local socket binds over its stale socket file | None |

## Out of scope

 * Websockets and serial IO. The Python client has neither transport, and a hand-written client in the tests would be a second client to maintain. They follow once the Python client can use them, through built-in transports or the custom transports of [client-custom-transports.md](client-custom-transports.md). Serial IO also has no streams until #1204.
 * Protocol behavior: framing, malformed input, handshake errors, fragmentation and timeouts. The core unit tests and `client/conformance/` cover these, and they are the same code on both builds.
 * The server window and `EditServer`, which need UI automation.
 * KSA, which runs the net10 build and has its own test suite.

## Plan

### Phase 1: `krpc-game` chooses the servers

`krpc-game` installs a fixed `settings.cfg` with one TCP server. `krpc-game` is used outside this repo too, so make the servers an option. For example, an author of a JavaScript client runs the game with a websockets server:

```
krpc-game run --server tcp --server websockets:port=50001
```

 * `--server PROTOCOL[:KEY=VALUE,...]`, repeated for each server, in `krpc-game` and the pytest plugin. The protocols are `tcp`, `websockets`, `local` and `serial`. Each key is a server setting without its protocol prefix, so `port` under `websockets` is `ws_port`.
 * The list replaces the default, which is one TCP server on `127.0.0.1:50000`, as now.
 * The list must hold a TCP or local socket server, as the framework connects to the game with the Python client to wait for it to load. The framework connects to the first one.
 * The KSP game writes the `servers` node of `settings.cfg` from the list. The rest of the file stays a static resource.
 * The game object exposes the list, so a test finds the address or path of each server.
 * `BazelKSP` defaults to a TCP server and a local socket server, so `test-ksp` and `run-ksp` agree for `--no-launch`.
 * A changelog entry under `tools/krpctools`, and the option in `doc/src/krpctools.rst` and `doc/src/extending/testing.rst`.

### Phase 2: the tests

These go in `server/test/test_protocols.py`, and `pytest.ini` gains `server/test` in `testpaths`. The local socket tests connect with `krpc.connect_local`.

| Test | Checks |
|---|---|
| Call a procedure | An RPC that reads game state, such as `SpaceCenter.UT`, runs in the game over a local socket |
| Large response | `KRPC.GetServices` arrives whole over a local socket, through Mono's socket writes |
| Stream | A stream delivers two updates over a local socket |
| Reconnect | A second client connects over a local socket after the first disconnects |
| Scene change | A client stays connected across a scene change, and its next call succeeds. TCP and local socket, one connection each |
| Stop and restart | After the main menu and loading the save again, every server accepts a client. This binds again on Mono, over the stale socket file. TCP and local socket. It uses the `TestingTools` procedure below, and drops the connection the test framework caches |

The stop and restart test needs a way out of the game and back. No server runs at the main menu, and `AutoLoadGame` loads the save once per process. Add a `TestingTools` procedure that goes to the main menu, then loads the save `AutoLoadGame` loaded. The call returns before the scene changes. The test reconnects until the servers are back, within a timeout.

### Phase 3: Windows

 * Check whether the local socket tests run on Windows, where KSP's Mono may not support them. Skip them there if not.

## Verification

 * Each new local socket test fails when run with `--server tcp` alone, as a negative control.
 * `krpc-game run --server tcp --server websockets:port=50001` starts both servers, and the conformance websockets testee connects to the second.
 * The suite passes on Linux with `bazel run //tools/game:test-ksp -- server/test/test_protocols.py`, and with `--no-launch` against a game from `//tools/game:run-ksp`.
 * The suite adds about a minute or less, not counting the game launch, and the service tests still pass with the extra server running.
 * Windows run through the Windows session.
