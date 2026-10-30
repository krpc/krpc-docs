# Releases and versioning

**Status:** proposal, 2026-10-26. Part of [kRPC for KSA](README.md).

## Problem

`config.bzl` holds one version, and every component releases under it. With two games, a KSA
release would bump the KSP mod and every client, and a KSP fix would bump KSA.

Compatibility no longer depends on release versions. Since 0.7, client and server agree on a
protocol version in the handshake ([protocol-version.md](../protocol/protocol-version.md)), so
release versions are free to move apart.

## Release trains

| Train | Contents | Tag | Channels |
| --- | --- | --- | --- |
| Clients and tools | every client runtime, KSP stubs bundled; `krpctools`; `krpctest`; the `TestServer` image | `clients-v1.2.0` | GitHub (Java), PyPI, NuGet, vcpkg, Arduino, LuaRocks, ghcr.io |
| KSP | the KSP mod and its services, KSP API docs | `ksp-v1.0.3` | GitHub, CKAN |
| KSA | the KSA mod, the KSA stubs archive, KSA API docs | `ksa-v0.2.0` | GitHub, SpaceDock, Borea ([borea.md](borea.md)) |
| Protocol | an integer in the handshake | none | none |

* **The clients release in lockstep.** They share the protocol version. One version per language
  would mean about eight release pipelines for little gain. A language can split out later if one
  really diverges.
* **`core` is not a train.** Each mod ships the `core` it was built with, and `krpctools` ships it
  for third-party servers.
* **A `core` change reaches a game in that game's next release.** It gets a KSP patch release only
  when KSP users would notice it.
* **A breaking protocol change bumps all three trains**, since every client and both servers move to
  the new version.
* The docs gain a compatibility table keyed on protocol version: which client, KSP and KSA releases
  speak each one.

## Client stubs

The C#, C++, C-nano and Java clients compile against generated service stubs. Today the client
packages bundle the stubs for every KSP service (`tools/krpctools/services.bzl`). Python and Lua
build their services when they connect, and need no stubs.

| Stubs | Ship in | Why |
| --- | --- | --- |
| `KRPC`, `StdLib` | every client | part of the protocol |
| KSP services | the client packages, as now | KSP changes rarely, so client releases for KSP are rare. Users keep one package |
| `KSA` | the KSA release archive, as the prototype does | KSA is pre-alpha. Bundling would tie client releases on every channel to KSA's pace |
| `KSA.proto` for gRPC | the KSA release archive, beside the stubs | Generated from the same service definitions ([grpc.md](grpc.md)) |

* **A new KSA API reaches C#, C++, C-nano and Java users** the day the KSA mod ships.
* **KSA stubs can fold into the client packages** once the KSA API settles.
* **C-nano stubs match one exact server build** until procedure ids come from names
  ([procedure-ids.md](../protocol/procedure-ids.md), 0.8). After that, bundled C-nano stubs work
  across releases, like the others.
* **Stubs and server can be out of step.** A stub for a procedure the server lacks fails at call
  time with an error, as a name-based call does.

## Release scripts

| Area | Change |
| --- | --- |
| `config.bzl`, `tools/krpc-version.sh` | One version per train. `krpc-version.sh` takes the train |
| `tools/release/*` | Each script takes the train, and runs only the steps for its channels |
| `30-tag.py`, `80-bump-version.py` | Tag and bump one train |
| `.github/workflows/docs.yml` | Triggers on the `ksp-v*` and `ksa-v*` tags, freezing that game's docs. It stops triggering on bare `v*` |
| Changelogs | The per-component files stay. `doc/src/changelog.rst` groups them by train |
| Milestones | One GitHub milestone per train release, e.g. `ksp-1.0.1`, `ksa-0.2.0` |

Releases before the split keep their `v*` tags.

## Versions at the split

| Train | First version |
| --- | --- |
| Clients and tools | 1.0, with kRPC 1.0 |
| KSP | 1.0, with kRPC 1.0 |
| KSA | continues from the prototype's 0.x |
