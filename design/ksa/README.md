# kRPC for KSA

**Status:** in progress. The prototype, under `experimental/ksa/`, merged as
[PR #1190](https://github.com/krpc/krpc/pull/1190) and released as `ksa-v0.1.0` against the kRPC
0.7.0 release. The server window, manual controls, gRPC server and Borea archive layout are built, not yet in a PR.

kRPC for Kitten Space Agency (KSA) shares the protocol, `core`, the clients and the tools with kRPC
for KSP. The repo, its build, CI, releases and docs all assume KSP is the only game. These docs plan
the KSA mod and how KSA becomes a peer of KSP in the same repo.

KSP is mature, and most new work after 1.0 is expected to be KSA APIs. The plan keeps KSP cheap to
carry, and keeps a KSA change from paying for KSP work it does not touch.

## Docs

| Doc | Covers |
| --- | --- |
| [server.md](server.md) | The StarMap mod: tick hook, settings file, server window, `core` workarounds |
| [api-coverage.md](api-coverage.md) | The `KSA` service: its rules, gaps against KSP's services, and the phases that fill them |
| [grpc.md](grpc.md) | An in-process gRPC server, unary calls now and streams after 0.8 |
| [repo-layout.md](repo-layout.md) | Monorepo or split, the directory layout, the Bazel build of the KSA mod |
| [build-and-test-tools.md](build-and-test-tools.md) | In-game test harness, `run-<game>`, servicedefs, clientgen and docgen service lists |
| [ci.md](ci.md) | What CI checks for each game, with no new jobs |
| [releases.md](releases.md) | Release trains, per-game client stubs, tags, channels |
| [docs-website.md](docs-website.md) | One source, one site build per game |
| [borea.md](borea.md) | Listing the KSA mod on the Borea mod manager, from `ksa-v0.2.0` |

Related, outside this folder:

* [protocol/protocol-version.md](../protocol/protocol-version.md): only the protocol version decides
  client and server compatibility, so release versions can move apart. Services are not versioned.
* [protocol/procedure-ids.md](../protocol/procedure-ids.md): procedure ids derived from names, in
  0.8. It lets C-nano stubs work across server builds, which [releases.md](releases.md) relies on.
* [protocol/grpc-support.md](../protocol/grpc-support.md): gRPC for KSP, through an external bridge.

## Background

* KSA runs on .NET 10, on Rocketwerkz's BRUTAL framework, with no Unity.
* KSA has no official modding API. Code mods load through the community
  [StarMap](https://forums.ahwoo.com/threads/how-to-use-starmap-mod-loader.398/) loader, whose API
  has changed shape at least once.
* The game is pre-alpha. Its builds change often, and internals can move between builds.
* The nearest mods are [KittenRemoteControl](https://spacedock.info/mod/4049/KittenRemoteControl)
  (REST, out of date) and [Kitten Proto-Link](https://forums.ahwoo.com/threads/kitten-proto-link.684/)
  (protobuf telemetry for hardware). Neither offers multiple clients, streams, events or server-side
  functions.

## Decisions

| Question | Decision |
| --- | --- |
| Name | kRPC for KSA. Mod id and folder `kRPC` from 0.2.0 (`kRPC.KSA` in 0.1.0), assemblies `KRPC.KSA.*` |
| Service | A `KSA` service in KSA's terms, not a `SpaceCenter` subset ([api-coverage.md](api-coverage.md)) |
| `core` | The latest kRPC release (0.7.0 now), until phase 1 builds against HEAD |
| gRPC | An in-process server beside the kRPC protocol, never a replacement ([grpc.md](grpc.md)) |
| One repo or several | One repo. Shared code changes and their game consequences land in one commit and one CI run |
| Layout | `ksp/` and `ksa/` side by side, shared code at the top level |
| Versions | Three release trains: clients and tools, the KSP mod, the KSA mod. The protocol version is a handshake field |
| Client stubs | KSP stubs stay bundled in the clients. KSA stubs ship with the KSA mod while its API churns |
| CI | KSA targets join the existing jobs. In-game tests stay local for both games |
| Docs | One source tree, built once per game, at `/ksp/` and `/ksa/` |
| License | LGPL v3, like the clients its stubs compile into |

## Progress

| Work | State |
| --- | --- |
| Prototype: server, `KSA` service, tests, docs, release scripts | Merged in PR #1190, released as `ksa-v0.1.0` |
| Server window ([server.md](server.md)) | Built and checked in game, not yet in a PR |
| Manual rotation and translation inputs ([api-coverage.md](api-coverage.md)) | Built and tested in game, not yet in a PR |
| Unary gRPC server ([grpc.md](grpc.md)) | Built and tested in game on Linux, not yet in a PR |
| Archive layout for Borea ([borea.md](borea.md)) | Built, not yet in a PR. Untested in a Borea instance |

## Phases

Each phase merges on its own. All of them follow kRPC 1.0, except procedure ids, which are in 0.8.

| | Phase | Done when |
| --- | --- | --- |
| 0 | Prototype in `experimental/ksa/`, released as `ksa-v0.1.0` against kRPC 0.7.0 | Done, PR #1190 |
| 1 | Layout: `ksp/` and `ksa/`, the KSA mod built by Bazel against `//core` at HEAD, `@ksa` stub assemblies | `bazel build //...` builds both mods |
| 2 | CI: KSA targets in the existing jobs | A KSA change is checked with no new jobs |
| 3 | Tools: shared in-game harness, `//ksa:test-ingame` | KSA in-game tests run through Bazel |
| 4 | Release trains: per-train versions, tags and release scripts | A KSA release leaves the KSP and client versions alone |
| 5 | Docs: per-game builds from one source | `/ksa/` has the full client guides with KSA examples |

## Open Questions

* **Can the KSA stub assemblies be published?** KSP's come from the `krpc/ksp-lib` repo. KSA is
  closed source and pre-alpha, so its terms need checking before `@ksa` can download stubs. Without
  them, CI cannot build the KSA mod. Asked on the forum, with no reply yet:
  [Reference assemblies for code mods](https://forums.ahwoo.com/forums/kitten-space-agency/feedback/reference-assemblies-for-code-mods-so-mods-can-be-built-automatically.1465/).
* **KSA and StarMap churn.** Each KSA update can break the service. Each release names the KSA and
  StarMap builds it was tested against.
