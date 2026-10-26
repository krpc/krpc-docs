# KSA as a first-class game

**Status:** proposal, 2026-10-26. The prototype is [PR #1190](https://github.com/krpc/krpc/pull/1190),
under `experimental/ksa/`, built against the kRPC 0.7.0 release.

kRPC for Kitten Space Agency (KSA) shares the protocol, `core`, the clients and the tools with kRPC
for KSP. The repo, its build, CI, releases and docs all assume KSP is the only game. These docs plan
how KSA becomes a peer of KSP in the same repo.

KSP is mature, and most new work after 1.0 is expected to be KSA APIs. The plan keeps KSP cheap to
carry, and keeps a KSA change from paying for KSP work it does not touch.

## Docs

| Doc | Covers |
| --- | --- |
| [repo-layout.md](repo-layout.md) | Monorepo or split, the directory layout, the Bazel build of the KSA mod |
| [build-and-test-tools.md](build-and-test-tools.md) | In-game test harness, `run-<game>`, servicedefs, clientgen and docgen service lists |
| [ci.md](ci.md) | What CI checks for each game, with no new jobs |
| [releases.md](releases.md) | Release trains, per-game client stubs, tags, channels |
| [docs-website.md](docs-website.md) | One source, one site build per game |
| [borea.md](borea.md) | Listing the KSA mod on the Borea mod manager, from `ksa-v0.2.0` |

Related, outside this folder:

* [protocol/procedure-ids.md](../protocol/procedure-ids.md): procedure ids derived from names, in
  0.8. It lets C-nano stubs work across server builds, which [releases.md](releases.md) relies on.
* [protocol/protocol-version.md](../protocol/protocol-version.md): only the protocol version decides
  client and server compatibility, so release versions can move apart.
* `krpc-for-ksa/DESIGN.md`, beside the repos and in neither: the original proposal. Its service
  design is superseded by the `KSA` service in PR #1190. Its layout and versioning sections are
  superseded by these docs.

## Decisions

| Question | Decision |
| --- | --- |
| One repo or several | One repo. Shared code changes and their game consequences land in one commit and one CI run |
| Layout | `ksp/` and `ksa/` side by side, shared code at the top level |
| Versions | Three release trains: clients and tools, the KSP mod, the KSA mod. The protocol version is a handshake field |
| Client stubs | KSP stubs stay bundled in the clients. KSA stubs ship with the KSA mod while its API churns |
| CI | KSA targets join the existing jobs. In-game tests stay local for both games |
| Docs | One source tree, built once per game, at `/ksp/` and `/ksa/` |

## Phases

Each phase merges on its own. All of them follow kRPC 1.0, except procedure ids, which are in 0.8.

| | Phase | Done when |
| --- | --- | --- |
| 0 | Prototype in `experimental/ksa/`, released as `ksa-v0.1.0` against kRPC 0.7.0 | PR #1190 merged, on SpaceDock |
| 1 | Layout: `ksp/` and `ksa/`, the KSA mod built by Bazel against `//core` at HEAD, `@ksa` stub assemblies | `bazel build //...` builds both mods |
| 2 | CI: KSA targets in the existing jobs | A KSA change is checked with no new jobs |
| 3 | Tools: shared in-game harness, `//ksa:test-ingame` | KSA in-game tests run through Bazel |
| 4 | Release trains: per-train versions, tags and release scripts | A KSA release leaves the KSP and client versions alone |
| 5 | Docs: per-game builds from one source | `/ksa/` has the full client guides with KSA examples |

## Open questions

* **Can the KSA stub assemblies be published?** KSP's come from the `krpc/ksp-lib` repo. KSA is
  closed source and pre-alpha, so its terms need checking before `@ksa` can download stubs. Without
  them, CI cannot build the KSA mod.
* **The KSA mod's license.** The prototype is LGPL v3, like the clients its stubs compile into.
