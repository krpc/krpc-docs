# Build and test tools

**Status:** proposal, 2026-10-26. Part of [kRPC for KSA](README.md). The `--reference-dir` option
of `krpc-servicedefs` is in review for #1228, PR to open.

Most tools are already game-agnostic. The in-game test harness and the service lists are the two
that assume KSP.

| Tool | Game coupling now | Change |
| --- | --- | --- |
| `tools/krpctest` | Installs mods into GameData, launches KSP, loads a save | Split into a shared core and a backend per game |
| `//:test-ingame` | KSP | `//ksp:test-ingame` and `//ksa:test-ingame` |
| `//:run-ksp` | KSP | Stays, plus `//ksa:run-ksa` |
| `krpc-servicedefs` | Copies the KSP assemblies | Takes the game's reference directory |
| `tools/krpctools/services.bzl` | One list, KSP services included | A shared list plus one list per game |
| clientgen, docgen | none | none |
| `experimental/ksa/grpc/protogen.py` | KSA | A Bazel target writing the `.proto` from the service definitions |
| `TestServer`, conformance suite | none | none |
| `experimental/ksa/*.sh`, `*.bat` | KSA | Replaced by Bazel targets and the release scripts |

## In-game test harness

`krpctest` today mixes three things: pytest integration, assertions and waits, and KSP launch and
install. The KSA prototype has its own `ksatest.py` with the same shape.

| Layer | Contents | Shared |
| --- | --- | --- |
| Core | pytest plugin, connection fixture, assertions, `wait_for` helpers, stage logging | yes |
| Backend | install, launch, load a save, stop, log path | one per game |
| Fixtures | saves, craft, test vehicles, `TestingTools` service | one per game |

| Backend | Install | Launch | Notes |
| --- | --- | --- | --- |
| KSP | GameData reconciled to the declared `mods` | `KSP.x86_64` / `KSP_x64.exe` | As now |
| KSA | the mod folder and its `manifest.toml` entry | StarMap under `dotnet` (Linux), StarMap (Windows) | The game shows a "Configuration" window unless "Always Show" is unticked |

* **`--no-launch` and test selection work the same** for both games.
* **KSA has no mod sets yet.** Its backend installs StarMap and kRPC only.
* **`krpctest` is not published.** It installs the mod by building it with Bazel, so it runs only
  from a kRPC checkout. Moving it into `krpctools`, configured per game, is drafted in
  [krpctest-in-krpctools.md](../../issues/krpctest-in-krpctools.md).

## Service lists

`services.bzl` lists every service the clients are generated for, SpaceCenter and the KSP mod
services included.

| List | Services | Used by |
| --- | --- | --- |
| Shared | `KRPC`, `StdLib`, `TestService` | every client, the client tests |
| KSP | `SpaceCenter`, `Drawing`, `UI`, mod services | the KSP stub packages, KSP docs |
| KSA | `KSA` | the KSA stub packages, KSA docs |

See [releases.md](releases.md) for where each list's stubs ship.

## Service definitions

`krpc-servicedefs` loads a service assembly by reflection and needs the game assemblies to resolve
its types. Stub assemblies are enough, since nothing runs. It gains a repeatable `--reference-dir`
option in place of the KSP directory argument (#1228). The prototype already calls the
`ServiceDefinitions` binary with `--reference-dir`, and moves to `krpc-servicedefs` when it builds
against krpctools 0.8.
