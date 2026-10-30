# The KSA Server

**Status:** in progress. Part of [kRPC for KSA](README.md). The mod merged in
[PR #1190](https://github.com/krpc/krpc/pull/1190). The server window is built and checked in game,
not yet in a PR.

The mod is a StarMap code mod, `experimental/ksa/server/`, built against the KRPC.Core 0.7.0
release. It does the jobs kRPC's KSP addon does:

| Job | KSP (`server/src/Addon.cs`) | KSA |
| --- | --- | --- |
| Start and stop the server | `KSPAddon` lifecycle | StarMap `[StarMapAllModsLoaded]` and `[StarMapUnload]` |
| Run RPCs on the main thread | `FixedUpdate` calls `core.Update()` | A Harmony prefix on `Universe.ExecuteNextVehicleSolvers` |
| Run while paused | `Update` calls `FixedUpdate` when paused | `[StarMapAfterOnFrame]` updates after a frame that skipped the solver step |
| Settings | `PluginData/settings.cfg` | `settings.toml` in the mod folder |
| Window | Unity IMGUI | ImGui, in KSA's console window style |
| Logging | `KSP.log` | KSA's log, through a `KRPC.Utils.Logger` sink |

## Tick Hook

StarMap 0.4.8 offers lifecycle attributes only, with no per-tick hook, so the hook is a Harmony
patch. The prefix runs after the frame's vehicle solver results are applied and before the next
solver step is queued:

* **Reads are settled.** Vehicle state is the result of the last step.
* **Writes take effect next step.** Control inputs and flight computer settings feed the queued
  step. The flight computer copies its settings in and out around the solver, and this point lies
  between the two.
* **Loading a save runs after the frame**, through `Addon.RunAfterFrame`, where the game's own menus
  load saves. A loaded save starts paused, so engine performance reads 0 until the first step.

## Settings File

`settings.toml` holds every setting of `KRPC.Configuration` plus a `[[servers]]` table per server.
It loads into `Configuration.Instance`, so rate control settings take effect. The server window
writes changes back to it.

* **The mod reads it from its own folder**, via the assembly location, so it is instance-safe for
  Borea ([borea.md](borea.md)).
* **The release ships `settings.toml`.** A reinstall restoring working defaults is acceptable in an
  alpha.
* **Server keys are unprefixed** (`address`, `rpc_port`, `port`), as the 0.7.0
  `Configuration.Server.Create` reads them. `port` is a device name for serial IO and a number for
  gRPC, so the edit form drops it on a switch between the two.
* **On a 0.8 core the keys take the protocol prefixes:** `tcpip_`, `ws_`, `serialio_`,
  `localsocket_` and `grpc_`. The `port` workaround then goes.

## Server Window

A kRPC menu in the game's menu bar opens a server window and an info window. They follow the KSP
ones:

* Start and stop, per-server details and connected clients.
* Add, remove and edit servers, including a protocol switch, and the advanced settings.
* A prompt for new clients when `auto_accept_connections` is off, and a disconnect confirmation.
* Window positions and visibility persist in `settings.toml`.

Game constraints the windows meet:

| Constraint | Handling |
| --- | --- |
| The `ImGuiWindow` constructor registers only `IStaticWindow` instances for drawing | Windows subclass `ImGuiWindow` and implement `IStaticWindow`, built in a `[StarMapBeforeGui]` hook |
| Console windows open at a large minimum size | A transpiler on `OnDrawUiConsole` gives kRPC windows their own default size |
| `ConsoleWidgets.TextLine` commits only on Enter | Form fields use `ImGui.InputText` directly |
| Prompts | Subclass `KSA.Popup`, as `ConfirmActionPopup` does |

The test build installs `testing/settings.toml`, which opens the window at the left, clear of the
windows the tests open.

## Workarounds for `core`

Each workaround goes once the KSA mod builds against a `core` with the fix
([repo-layout.md](repo-layout.md)).

| Problem | Workaround | Fix in `core` |
| --- | --- | --- |
| On .NET, `TcpClient.Close` nulls the socket, so `TCPClient.Connected` throws for a client that disconnects during a yielding call, and the server stops | Harmony finalizer returning not connected | [#1189](https://github.com/krpc/krpc/issues/1189) |
| Adaptive rate control overwrites `Configuration.MaxTimePerUpdate`, so the window shows the live value | None | Issue to file |
| Server keys collide between protocols | The `port` drop above | The 0.8 key prefixes |
| No public seam for a gRPC server | Publicized internals ([grpc.md](grpc.md)) | A public seam |
