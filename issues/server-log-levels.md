# Routine server messages show in KSA's in-game console

The core `Logger` logs at Info and above by default, and each game's server routes the lines to the
game. KSP's server writes them to Unity's debug log, which only reaches `KSP.log`. KSA's server writes
them to the game's own log, and KSA's in-game console shows that log. Every Info line from the core is
then visible to a KSA player, which is how these were found.

## Object store sweep

`GameState.Sweep` (`core/src/Service/GameState.cs`) logs
`Removed N destroyed object(s) from the object store` at Info whenever a sweep removes an object. KSP
sweeps on scene changes only. The KSA service sweeps when the vehicles or their part counts change:
every save load, launch, decouple, dock, EVA and destroy. A player sees the line after routine
actions, and has nothing to do about it.

Fix: log it at Debug.

## Listener exceptions

When a listener thread stops on an exception, `TCPServer.cs` and `LocalSocketServer.cs` log an Error
line, then the exception type, message and stack trace as three more lines at Info.

Fix: one Error line holding the type, message and stack trace.

## Duplicate connection line in KSA

With connections auto-accepted, the KSA server logs `Accepting client connection (addr)`, then the
core logs `ProtocolBuffers: client connection accepted (addr)` for the same connection.

Fix: log the KSA line at Debug, and keep the core line, which names the protocol.

## Left at Info

* Client connected and disconnected, one line each per connection. These tell a player who is
  connected.
* Server added, started and stopped. Rare.

The tick hold messages already log at Debug, and the hold failures at Warning.

## Scope

The first two fixes are in the core, shared by the KSP and KSA servers, so they ship in a kRPC
release. KSP shows no change. The KSA server picks them up when it moves to that core release.
