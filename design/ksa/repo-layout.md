# Repository layout

**Status:** proposal, 2026-10-26. Part of [kRPC for KSA](README.md).

## One repo

The repo stays a monorepo.

| Shared by both games | Game-specific |
| --- | --- |
| `protobuf/`, `core/`, `client/`, `conformance/`, `tools/krpctools`, `tools/TestServer`, `doc/` | The server plugin, the services, the in-game tests, the game assemblies |

* **The shared parts are where the changes happen.** A protocol or `core` change and its KSA
  consequence land in one commit and one CI run. Separate repos would need a `core` release and a
  pin bump between the two.
* **A quiet KSP costs little to carry.** A frozen `ksp/` tree adds build time and nothing else.
* **The prototype already depends on the shared parts.** It builds against the kRPC 0.7.0 PyPI
  packages. Phase 1 turns that pin into a Bazel dependency on `//core:KRPC.Core.net10`, which
  already exists.

A split is worth revisiting only if KSP is fully frozen. Even then, archiving `ksp/` in place is
simpler than moving it out.

## Layout

```
protobuf/      wire protocol
core/          KRPC.Core, net472 for KSP and net10.0 for KSA
client/        one dir per language
conformance/   client conformance suite
tools/         krpctools, TestServer, the in-game test harness, build rules
doc/           one docs source, built per game
ksp/
  server/      KSP plugin (was server/)
  service/     SpaceCenter, Drawing, UI, ... (was service/)
  test/        harness backend for KSP, saves and craft
ksa/
  server/      StarMap entry point (was experimental/ksa/server/)
  service/     KSA service
  grpc/        gRPC server and .proto generator
  testing/     TestingTools service and test vehicles
  test/        in-game tests and the harness backend for KSA
  examples/    client scripts
```

* **The two games are symmetric.** With KSP alone at the top level, `server/` reads as the server
  and KSA as an add-on.
* **The move is one mechanical commit**, done at a quiet point. It touches Bazel labels, the
  `.csproj` paths, `tools/krpctools/services.bzl`, the doc includes and CI. Git follows the
  renames.
* **The release archive keeps its layout.** `GameData/kRPC/` is unchanged for KSP users.
* The `ksa` label on GitHub already tracks KSA issues.

## Building the KSA mod with Bazel

The prototype builds with `dotnet` and shell scripts against a local KSA install. Phase 1 moves it
into Bazel next to the KSP mod.

| Piece | Now | In Bazel |
| --- | --- | --- |
| `KRPC.Core` | the 0.7.0 `krpctools` package | `//core:KRPC.Core.net10` |
| Game assemblies | `KSA_DIR` | `@ksa`, stub assemblies, as `@ksp` comes from `krpc/ksp-lib` |
| StarMap API, Harmony, grpc-dotnet | NuGet | NuGet through `rules_dotnet`, like the existing packages |
| ASP.NET Core runtime packs | NuGet download in `build.sh` | `http_archive` pins, one per platform ([grpc.md](grpc.md)) |
| C# rules | `.csproj` | `csharp_library` from `//tools/build:csharp.bzl`, so the culture analyzers run |
| KSA version pin | `versions.sh` | `config.bzl`, beside `ksp_version_*` |
| Targets | `build.sh` | `//ksa:mod`, beside `//ksp:mod` (was `//:krpc`) |

* **`core` keeps building for both runtimes.** It must stay within the net472 API, which the
  net472 build enforces.
* **`core` fixes found on KSA land in `core`.** Once KSA builds against HEAD, each workaround in
  [server.md](server.md) is replaced by its fix in `core`, such as the disconnect
  `NullReferenceException` ([#1189](https://github.com/krpc/krpc/issues/1189)).
* **`kRPC.sln` holds both games.** `//:csproj` stages the generated sources and stub assemblies for
  each.
* **KSA is pre-alpha**, so the `@ksa` pin moves often. Each bump is one commit to `MODULE.bazel`
  and `config.bzl`.
