# Move to .NET 10

**Status:** proposal. No issue filed yet.

The toolchain and every out-of-game component are pinned to .NET 8. .NET 8 is an LTS release whose
support window ends in November 2026; .NET 10 is the current LTS. Move the pins forward together.

## Pins to move

| Location | Current pin |
|---|---|
| `MODULE.bazel` | `dotnet.toolchain(dotnet_version = "8.0.422")` |
| `tools/buildenv/Dockerfile` | `dotnet-sdk-8.0` |
| `core/` (`KRPC.Core.net8`) | `net8.0` target framework |
| `client/csharp/` (`KRPC.Client.net8`, the unit-test build) | `net8.0` |
| `tools/TestServer/` | `net8.0` |
| `tools/ServiceDefinitions/` | `net8.0` |
| `tools/krpctools/` (packaged binaries) | `net8.0` |

Move the Bazel toolchain, the buildenv image, and the `target_frameworks`/`target_framework`
attributes in `core/`, `client/csharp/`, `tools/TestServer/`, `tools/ServiceDefinitions/` and
`tools/krpctools/`.

## In scope only the out-of-game components

**The in-game DLLs stay on `net472` and are out of scope.** The server, every service, and
`TestingTools` target the .NET Framework because KSP runs them on Unity's Mono runtime; that is fixed
by the game, not by our toolchain choice. Only the components that run outside the game move.

## Knock-on effects worth checking

* **Release assets.** `TestServer` ships framework-dependent `net8` linux-x64, so its runtime
  requirement changes for anyone running it standalone — a user-facing change needing a changelog
  entry and a note in the release guide.
* **`DOTNET_ROLL_FORWARD=LatestMajor`**, currently needed on this machine to run the net8 outputs
  under a locally installed SDK 10, stops being necessary once the two agree.
* **Analyzer SDK skew.** Local SDK 10 flags ~30 `CA1305`/`CA1307` sites in `KRPC.SpaceCenter` that
  CI's SDK 8 does not, because `AnalysisLevel=latest` resolves per SDK — this disappears once CI is
  also on 10. See [culture analyzers](../design/build-tools/culture-analyzers.md). **Sequence this item before that one**,
  so the analyzer triage is done against the rule set that CI will actually run.
* **CI location.** CI runs everything in the `buildenv` container, so the SDK bump lands there rather
  than in `ci.yml`; that image is also the subject of the Bazel-cache baking item.

## Changelog impact

An entry for `TestServer`'s runtime requirement if it changes; otherwise none, as the in-game mod
DLLs are unaffected.
