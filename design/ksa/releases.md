# Releases and versioning

**Status:** proposal, 2026-10-26, revised 2026-10-31 (stub packages and their dependencies, milestones, labels, `core` changelog). Part of
[kRPC for KSA](README.md).

## Problem

`config.bzl` holds one version, and every component releases under it. With two games, a KSA
release would bump the KSP mod and every client, and a KSP fix would bump KSA.

Compatibility no longer depends on release versions. Since 0.7, client and server agree on a
protocol version in the handshake ([protocol-version.md](../protocol/protocol-version.md)), so
release versions are free to move apart.

## Release trains

| Train | Contents | Tag | Channels |
| --- | --- | --- | --- |
| Clients and tools | every client runtime, with the `KRPC` and `StdLib` stubs; `krpctools`; `krpctest`; the `TestServer` image | `clients-v1.2.0` | GitHub (Java), PyPI, NuGet, vcpkg, Arduino, LuaRocks, ghcr.io |
| KSP | the KSP mod and its services, the KSP stub package for each client, KSP API docs | `ksp-v1.0.3` | GitHub, CKAN, and the client channels for the stubs |
| KSA | the KSA mod and its services, the KSA stub package for each client, `KSA.proto`, KSA API docs | `ksa-v0.2.0` | GitHub, SpaceDock, Borea ([borea.md](borea.md)), and the client channels for the stubs |
| Protocol | an integer in the handshake | none | none |

* **The clients release in lockstep.** They share the protocol version. One version per language
  would mean about eight release pipelines for little gain. A language can split out later if one
  really diverges.
* **Stub packages release with their game.** KSP stubs `1.0.3` are generated from KSP mod `1.0.3`.
* **`core` is not a train, and has no version.** Each mod builds in `core` as it stands on `main`
  when that mod is released. `krpctools` ships `core` for third-party servers in the same way, as it
  stands at the clients release.
* **A `core` change reaches a game in that game's next release.** It gets a KSP patch release only
  when KSP users would notice it.
* **A breaking protocol change bumps all three trains**, since every client and both servers move to
  the new version.
* The docs gain a compatibility table keyed on protocol version: which client, KSP and KSA releases
  speak each one.

## Client packages

Each client splits into three packages:

| Package | Contents | Version | Example (Python) |
| --- | --- | --- | --- |
| Client | the runtime, with the `KRPC` and `StdLib` stubs | clients train | `krpc` |
| KSP stubs | the KSP service stubs | KSP train | `krpc-ksp` |
| KSA stubs | the KSA service stubs | KSA train | `krpc-ksa` |

* **Which clients have stubs.** C#, C++, C-nano and Java compile against generated stubs. Python
  loads its generated stubs when present and builds the other services at connect time, so its stub
  packages add types and IDE completion. Lua builds every service at connect time, and gains stub
  packages if pre-generated Lua stubs land ([#1201](https://github.com/krpc/krpc/issues/1201)).
* **A new game API reaches users the day the mod ships**, with no client release.
* **C-nano stubs work across server builds**, since procedure ids come from names
  ([procedure-ids.md](../protocol/procedure-ids.md), 0.8).
* **Stubs and server can be out of step.** A stub for a procedure the server lacks fails at call
  time with an error, as a name-based call does.
* **`KSA.proto` for gRPC** stays in the KSA release archive. It is generated from the same service
  definitions ([grpc.md](grpc.md)).
* **Until the split**, the client packages bundle the KSP stubs as now
  (`tools/krpctools/services.bzl`), and the KSA stubs ship in the KSA release archive, as the
  prototype does.

### Stub package dependencies

A stub package depends on the client package, with a version range:

```toml
# krpc-ksp/pyproject.toml
[project]
name = "krpc-ksp"
version = "1.0.3"
dependencies = ["krpc>=1.2,<2"]
```

`pip install krpc-ksp` then installs the stubs and a client recent enough for them. A user never
installs the client package by hand.

* **The lower bound is the client release the stubs were generated against**, the latest clients
  release when the game is tagged.
* **The upper bound is the next client major version.** The interface between generated code and
  the client runtime stays stable within a client major version. A change to it is a breaking
  client release, and the next game releases regenerate their stubs against it.
* **A range, never an exact pin.** Client fixes reach users without a game release, and `krpc-ksp`
  and `krpc-ksa` installed together resolve to one client.
* **Generated code on `main` may need a client runtime change that is not released yet.** The
  clients train then releases before the game, so the lower bound names a published version.
* **Every channel expresses the same range:**

| Channel | Client | Dependency in the stub package |
| --- | --- | --- |
| PyPI | Python | `dependencies = ["krpc>=1.2,<2"]` |
| NuGet | C# | `<PackageReference Include="KRPC.Client" Version="[1.2,2.0)" />` |
| Maven Central, GitHub | Java | `<version>[1.2,2.0)</version>` |
| vcpkg | C++, C-nano | `"dependencies": [{"name": "krpc", "version>=": "1.2.0"}]`, no upper bound |
| Arduino | C-nano | `depends=kRPC (>=1.2.0)`, no upper bound |

* **vcpkg and Arduino have no upper bound.** A client major version release coincides with new
  stub releases of both games, so the gap only reaches users who upgrade the client alone.
* **The Python client finds stubs from a separate package.** Today `krpc/services/__init__.py`
  imports a fixed list of generated modules. A stub package installs its own top-level module, and
  registers it with the client under a `krpc.services` entry point group. The client loads every
  registered module, and builds the other services at connect time.
* **The other clients need no discovery.** A program names the stub types it uses, and the build
  links the stub package.

## Milestones and labels

### Milestones

One GitHub milestone per train release, e.g. `clients-1.2.0`, `ksp-1.0.1`, `ksa-0.2.0`.

| Pull request touches | Milestone |
| --- | --- |
| A client, `krpctools`, `krpctest`, `TestServer` | clients |
| KSP services, the KSP mod | KSP |
| KSA services, the KSA mod | KSA |
| `core`, CI, build rules, repo tooling | none, labeled `server` or `build` |

* **A pull request has one milestone.** `core` changes are rare, and reach every game's next
  release anyway, so they get none. The label marks them as triaged.
* **A pull request spanning trains is split** where it can be. A breaking protocol change cannot be,
  and takes the clients milestone.
* **Until the split**, KSA builds against the `KRPC.Core.dll` released in `krpctools`. A `core`
  change takes the KSP milestone, and a separate KSA pull request picks it up.

### Labels

An issue or pull request takes one kind, at least one component, and the game and language labels
that apply.

| Group | Labels | Rule |
| --- | --- | --- |
| Game | `ksp`, `ksa` | The game a change is specific to. A `core` change takes both. Client and tool changes take neither |
| Component | `server`, `protocol`, `service`, `client`, `tools`, `build`, `docs` | `server` covers `core` and each mod's server plugin. `client` is a change across clients |
| Kind | `feature`, `bug`, `tests`, `question`, `mod-compatibility`, `dependencies` | One per issue or pull request |
| Language | `python`, `cpp`, `cnano`, `csharp`, `java`, `lua` | The client a change is specific to |
| Triage | `needs-triage` | Set on new issues by the issue templates, removed once triaged |

* **`client` and `build` are kept** beyond the base set. Cross-client changes, such as the
  conformance suite, need a component, and CI and build rules carry no milestone, so need a label
  apart from `tools`.
* **`dependencies` is kept** because Dependabot applies it.
* **Per-service labels are dropped.** `ksp` with `service` covers SpaceCenter, and
  `mod-compatibility` covers the mod services.

### Label migration

A one-to-one rename keeps the label on its issues. A merge relabels them.

| Existing | New | How |
| --- | --- | --- |
| `enhancement` | `feature` | rename |
| `client:python`, `client:cpp`, `client:cnano`, `client:csharp`, `client:java`, `client:lua` | `python`, `cpp`, `cnano`, `csharp`, `java`, `lua` | rename |
| `build-scripts` | `build` | rename |
| `server:api`, `server:ui` | `server` | merge |
| `service:space-center`, `service:ui`, `service:drawing`, `service:debug` | `service`, `ksp` | merge |
| `service:infernal-robotics`, `service:kerbal-alarm-clock`, `service:remote-tech` | `service`, `ksp`, `mod-compatibility` | merge |
| `bug`, `question`, `docs`, `tools`, `protocol`, `server`, `service`, `client`, `mod-compatibility`, `dependencies`, `ksa`, `needs-triage` | unchanged | none |

* **`ksp` is not added to older issues** apart from the former service labels. Before KSA, every
  issue was a KSP one.
* **References to update with the migration:** the issue templates (`enhancement`), the pull
  request labeling rule in the `krpc` `CLAUDE.md`, and the labels column of
  [RELEASE_PLAN.md](../../RELEASE_PLAN.md).

## Changelogs

The per-component files stay. `doc/src/changelog.rst` groups them by train.

**`core` changes are logged in each game's Server section, at pull request time.** A `core` pull
request adds its user-facing entry to the Server changelog of each game, under that game's
unreleased header. Each game publishes the entry at its next release.

* **`core/CHANGELOG.md` is removed.** `core` does not appear in the release notes. A release page
  lists Server, then each service.
* **Until the split**, the `core` pull request adds the KSP entry, and the KSA pull request that
  picks up the new `core` adds the KSA one.

| Alternative | Rejected because |
| --- | --- |
| A `core` version train, with each game's notes appending the `core` sections it picked up | A fourth train to tag and bump, and `core` shown to users as a component |
| One entry in `core/CHANGELOG.md`, copied into each game's notes when that game is tagged | The tag script must track which entries each game has already released |
| Server entries written by hand just before each release | Depends on remembering `core` changes merged months earlier |

## Release scripts

| Area | Change |
| --- | --- |
| `config.bzl`, `tools/krpc-version.sh` | One version per train. `krpc-version.sh` takes the train |
| `tools/release/*` | Each script takes the train, and runs only the steps for its channels. The game trains publish their stub packages to the client channels |
| `30-tag.py`, `80-bump-version.py` | Tag and bump one train |
| `.github/workflows/docs.yml` | Triggers on the `ksp-v*` and `ksa-v*` tags, freezing that game's docs. It stops triggering on bare `v*` |

Releases before the split keep their `v*` tags.

## Versions at the split

| Train | First version |
| --- | --- |
| Clients and tools | 1.0, with kRPC 1.0 |
| KSP, and the KSP stub packages | 1.0, with kRPC 1.0 |
| KSA, and the KSA stub packages | continues from the prototype's 0.x |
