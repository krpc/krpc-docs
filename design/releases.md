# Releases and versioning

**Status:** proposal, 2026-10-26, revised 2026-10-31 (stub packages, labels, `core` changelog, CKAN
and KSP-AVC, version strings; label migration done apart from the service labels) and 2026-11-05 (a
train per client, one `krpctools` train, no milestones, no latest release, release workflows,
a docs site per train). Covers every component. Started for [kRPC for KSA](ksa/README.md).

## Problem

`config.bzl` holds one version, and every component releases under it:

* **Two games.** A KSA release would bump the KSP mod and every client, and a KSP fix would bump KSA.
* **A new client starts at the shared version.** A Go client added when the others reach 2.4.1
  would start at 2.4.1.
* **A fix in one client releases every client**, most of them unchanged.
* **The clients lack feature parity.** Bringing the others up to Python's level would bump Python's
  version with no change to Python.
* **A release takes an evening.** Every channel is published in one sitting.

Compatibility no longer depends on release versions. Since 0.7, client and server agree on a
protocol version in the handshake ([protocol-version.md](protocol/protocol-version.md)), so
release versions are free to move apart.

## Release trains

One train per game mod, one per client, and one for the tools:

| Train | Contents | Tag | Channels |
| --- | --- | --- | --- |
| KSP | the KSP mod and its services, the KSP stub package of each client, KSP API docs | `ksp-v1.0.3` | GitHub, CKAN, and each client's channel for its stubs |
| KSA | the KSA mod and its services, the KSA stub package of each client, `KSA.proto`, KSA API docs | `ksa-v0.2.0` | GitHub, SpaceDock, Borea ([borea.md](ksa/borea.md)), and each client's channel for its stubs |
| Python | the Python client | `python-v1.4.2` | PyPI |
| C# | the C# client | `csharp-v1.1.0` | NuGet |
| Java | the Java client | `java-v1.0.1` | Maven Central, GitHub |
| C++ | the C++ client | `cpp-v1.2.0` | vcpkg (`krpc`), GitHub |
| C-nano | the C-nano client and the Arduino library built from it | `cnano-v1.0.2` | vcpkg (`krpc-cnano`), Arduino, GitHub |
| Lua | the Lua client | `lua-v1.0.0` | LuaRocks, GitHub |
| Tools | `krpctools`: `clientgen`, `docgen`, `servicedefs`, the `TestServer` and `krpctest` | `krpctools-v1.1.0` | PyPI |
| Protocol | an integer in the handshake | none | none |

* **A client runtime carries the `KRPC` and `StdLib` stubs.** Each game's stubs are a separate
  package, versioned with the game (see [Client packages](#client-packages)).
* **A new client starts at its own version**, e.g. a Go client at `go-v0.1.0`.
* **`krpctools` is one package.** The `TestServer` is already bundled in it, and `krpctest` moves
  into it. `clientgen` serves every client, so the tools cannot belong to one client's train.
* **`core` is not a train, and has no version.** Each mod builds in `core` as it stands on `main`
  when that mod is released. `krpctools` ships `core` for third-party servers in the same way, as
  it stands at the tools release.
* **A `core` change reaches a game in that game's next release.** It gets a KSP patch release only
  when KSP users would notice it.
* **A breaking protocol change bumps every client's major version and both games**, since every
  client and both servers move to the new version.
* **The docs gain a compatibility table keyed on protocol version**, with one row per client: which
  releases of each client, KSP and KSA speak each version.
* **Feature parity is tracked by the conformance results**, not by version numbers. The table can
  show the conformance profiles each client release passes.

## Version strings

**A version people read carries a `v`: `v1.2.3`.** A version in a field whose format is a bare
number stays bare: `1.2.3`.

| Form | Where |
| --- | --- |
| `v1.2.3` | Tags (after the train prefix), release titles, changelog headers, archive and file names we choose, docs URL paths and switcher labels, in-game window titles and messages, the CKAN version |
| `1.2.3` | `config.bzl` and `tools/krpc-version.sh`, assembly versions, the KSP-AVC `VERSION` fields, the version the server reports to clients, and package versions on PyPI, NuGet, Maven, vcpkg, LuaRocks and Arduino |
| Not ours | Borea reads `ksa-v0.2.0` through `tag_prefix = "ksa-v"` and shows `0.2.0` |

Package files keep their ecosystem's name: `krpc-1.2.3.tar.gz`, `KRPC.Client.1.2.3.nupkg`,
`krpc-java-1.2.3.jar`, `krpc-1.2.3-0.rockspec`.

* **Release titles name the train**: "kRPC for KSP v1.0.3", "kRPC for KSA v0.2.0", "kRPC Python
  client v1.4.2", "krpctools v1.1.0".
* **No release is marked latest.** Each release is created with `--latest=false`, since GitHub picks
  one latest release across all trains. Links point at a train's tag, never at `releases/latest`.

### Inconsistencies today

| Place | Today | Consistent |
| --- | --- | --- |
| KSP mod archive (`BUILD.bazel`) | `krpc-0.7.0.zip` | `krpc-ksp-v1.0.0.zip` |
| KSA mod archive (`experimental/ksa/release.sh`) | `kRPC-KSA-0.1.0.zip`, then `krpc-ksa-0.2.0.zip` | `krpc-ksa-v1.0.0.zip` |
| Other release assets | `krpc-cpp-0.7.0.zip`, `krpc-cnano-0.7.0.zip`, `krpc-lua-0.7.0.zip`, `krpc-genfiles-0.7.0.zip`, `krpc-doc-0.7.0.pdf`, `SHA256SUMS-0.7.0.txt` | `v1.2.3` in each, on its own train's release |
| Docs URL paths | `/0.5.4/`, `/0.7.0/` | `/ksp/v1.0.0/`, `/ksa/v0.2.0/`, as [docs-website.md](ksa/docs-website.md) plans. Old snapshots stay |
| KSA release readme and docs (`@VERSION@`) | "kRPC for KSA 0.2.0" | "kRPC for KSA v0.2.0", as the release title |
| KSA compatibility popup | "kRPC 0.2.0 was built for KSA ..." | "kRPC v0.2.0 ..." |
| `krpc` `CLAUDE.md` | The changelog header form `## [X.Y.Z]` | `## [vX.Y.Z]` |
| README and docs links | `releases/latest` | the train's tag |

Already consistent: the GitHub release titles ("kRPC v0.7.0", "kRPC for KSA v0.2.0"), the changelog
headers, the KSP server window title, the `v<version>-docs` branches, and the CKAN version.

## Client packages

Each client has a runtime package, plus a stub package per game:

| Package | Contents | Version | Example (Python) |
| --- | --- | --- | --- |
| Client | the runtime, with the `KRPC` and `StdLib` stubs | the client's train | `krpc` |
| KSP stubs | the KSP service stubs for this client | KSP train | `krpc-ksp` |
| KSA stubs | the KSA service stubs for this client | KSA train | `krpc-ksa` |

**The `KRPC` and `StdLib` stubs ship in the client runtime**, since both services are part of the
protocol ([protocol-version.md](protocol/protocol-version.md#what-is-versioned)). A breaking change
to either bumps the protocol version. An addition the runtime relies on is a handshake feature, so
a client released before a game, or after it, still connects.

* **Which clients have stubs.** C#, C++, C-nano and Java compile against generated stubs. Python
  loads its generated stubs when present and builds the other services at connect time, so its stub
  packages add types and IDE completion. Lua builds every service at connect time, and gains stub
  packages if pre-generated Lua stubs land ([#1201](https://github.com/krpc/krpc/issues/1201)).
* **A new game API reaches users the day the mod ships**, with no client release.
* **A game release publishes every client's stubs**, under the game's version. A language whose
  stubs did not change still gets the new version.
* **C-nano stubs work across server builds**, since procedure ids come from names
  ([procedure-ids.md](protocol/procedure-ids.md), 0.8).
* **Stubs and server can be out of step.** A stub for a procedure the server lacks fails at call
  time with an error, as a name-based call does.
* **`KSA.proto` for gRPC** stays in the KSA release archive. It is generated from the same service
  definitions ([grpc.md](ksa/grpc.md)).
* **Until the split**, the client packages bundle the KSP stubs as now
  (`tools/krpctools/services.bzl`), and the KSA stubs ship in the KSA release archive, as the
  prototype does.

### Stub package dependencies

A stub package depends on its own client's package, with a version range:

```toml
# krpc-ksp/pyproject.toml
[project]
name = "krpc-ksp"
version = "1.0.3"
dependencies = ["krpc>=1.4,<2"]
```

`pip install krpc-ksp` then installs the stubs and a client recent enough for them. A user never
installs the client package by hand.

* **The lower bound is the client release the stubs were generated against**, that client's latest
  release when the game is tagged. Each language's stubs have their own bounds.
* **The upper bound is the client's next major version.** The interface between generated code and
  the client runtime stays stable within a client major version. A change to it is a breaking
  release of that client.
* **A range, never an exact pin.** Client fixes reach users without a game release, and `krpc-ksp`
  and `krpc-ksa` installed together resolve to one client.
* **Generated code on `main` may need a client runtime change that is not released yet.** That
  client then releases before the game, so the lower bound names a published version. The other
  clients are not involved.
* **Every channel expresses the same range:**

| Channel | Client | Dependency in the stub package |
| --- | --- | --- |
| PyPI | Python | `dependencies = ["krpc>=1.4,<2"]` |
| NuGet | C# | `<PackageReference Include="KRPC.Client" Version="[1.1,2.0)" />` |
| Maven Central, GitHub | Java | `<version>[1.0,2.0)</version>` |
| vcpkg | C++, C-nano | `"dependencies": [{"name": "krpc", "version>=": "1.2.0"}]`, no upper bound |
| Arduino | C-nano | `depends=kRPC (>=1.0.2)`, no upper bound |

* **vcpkg and Arduino have no upper bound.** The gap reaches users who upgrade the client to a new
  major without new stubs.
* **The Python client finds stubs from a separate package.** Today `krpc/services/__init__.py`
  imports a fixed list of generated modules. A stub package installs its own top-level module, and
  registers it with the client under a `krpc.services` entry point group. The client loads every
  registered module, and builds the other services at connect time.
* **The other clients need no discovery.** A program names the stub types it uses, and the build
  links the stub package.

### Client major versions

A client major release breaks that client's stubs for both games. The stubs carry the game's
version, so new stubs would take a game release with no change to the game. This is undesirable,
and no design avoids it outright.

* **A major bump is the last resort.** A client keeps accepting the previous generated interface
  where it can, and drops it at a later major.
* **Open: a stub-only revision.** The stubs could be regenerated against the game's released service
  definitions, published as a packaging revision of the game version. Each channel has a native
  form, but they differ and each needs checking:

| Channel | Game release | Stub revision |
| --- | --- | --- |
| PyPI | `1.0.3` | `1.0.3.post1` |
| NuGet | `1.0.3` | `1.0.3.1` |
| Maven Central | `1.0.3` | `1.0.3-1`, to check how it sorts |
| vcpkg | `1.0.3` | `1.0.3` with `port-version` 1 |
| Arduino | `1.0.3` | to check |

  The KSP and KSA releases would attach their service definitions, so a revision needs no checkout
  of the game tag. A revision has no tag of its own, and runs as a manual workflow taking the game
  version and the client.

## Planning without milestones

GitHub milestones are dropped. A pull request often touches several clients and the server at
once, so it fits no single train's milestone.

* **Labels mark what a pull request touches**, and the changelog fragments say what each train
  releases. A train's next release is everything in its unreleased changelog sections.
* **Version targets live in [RELEASE_PLAN.md](../RELEASE_PLAN.md)**, which lists the planned work
  by train and target version.
* **The existing milestones are closed.** The milestone rule in the `krpc` `CLAUDE.md` is replaced
  by the labels rule.

## Labels

An issue or pull request takes one kind, at least one component, and the other labels that apply.
The labels of each group share a color.

| Group | Labels | Rule | Color |
| --- | --- | --- | --- |
| Kind | `bug`, `feature`, `enhancement`, `question` | Exactly one. `feature` is a new capability. `enhancement` improves what exists, and covers dependency updates, refactoring, cleanup and maintenance | One mid-strength hue each |
| Component | `server`, `protocol`, `service`, `client`, `tools`, `build`, `docs` | `server` covers `core` and each mod's server plugin. `client` covers any client change | One pale green |
| Game | `ksp`, `ksa` | The game a change is specific to. `core`, client and tool changes take neither | Kerbal green and kitten ginger, white text |
| Language | `python`, `cpp`, `cnano`, `csharp`, `java`, `lua` | The client a change is specific to, with `client` | A pale tint of the language's GitHub color |
| Mods | `mod-compatibility` | Added to the kind for a change that concerns another mod | Pale teal |
| Dependencies | `dependencies` | Added to the kind for a dependency update. Dependabot sets it | Grey |
| Triage | `needs-triage` | Set on new issues by the issue templates, removed once triaged | Dark red |

* **`client` and `build` are kept** beyond the base set. Every client change needs a component, and
  CI and build rules need a label apart from `tools`.
* **The language labels map to the client trains.** A pull request carries one for each client it
  changes.
* **`enhancement` is a kind of its own**, added back on 2026-10-31. Labeling an improvement, a
  dependency update or a cleanup `feature` misleads, and leaving it without a kind hides it.
* **`dependencies` is kept** because Dependabot applies it. It goes with `enhancement`.
* **`mod-compatibility` goes with the kind**, marking a change that depends on another mod's work.
* **No `tests` kind.** A test change takes `enhancement`, or `bug` for a broken test. It can be added
  later if test work needs filtering.
* **Per-service labels are dropped.** `ksp` with `service` covers SpaceCenter, and
  `mod-compatibility` covers the mod services.

### Label migration

Done on 2026-10-31, apart from the `service:*` labels. Renames kept each label on its issues, and
the merges relabeled them.

| Existing | New | How | State |
| --- | --- | --- | --- |
| `enhancement` | `feature` | rename, then `enhancement` added back as its own kind | done |
| `client:python`, `client:cpp`, `client:cnano`, `client:csharp`, `client:java`, `client:lua` | `python`, `cpp`, `cnano`, `csharp`, `java`, `lua` | rename | done |
| `build-scripts` | `build` | rename | done |
| `server:api`, `server:ui` | `server` | merge | done |
| `service:space-center`, `service:ui`, `service:drawing`, `service:debug` | `service`, `ksp` | merge | open |
| `service:infernal-robotics`, `service:kerbal-alarm-clock`, `service:remote-tech` | `service`, `ksp`, `mod-compatibility` | merge | open |

* **`ksp` is not added to older issues** apart from the former service labels. Before KSA, every
  issue was a KSP one.
* **The renamed language labels lack `client`.** Issues carrying one still need `client` added.
* **References:** the pull request rule in the `krpc` `CLAUDE.md` and the labels column of
  [RELEASE_PLAN.md](../RELEASE_PLAN.md) are updated. The feature request issue template sets
  `feature`.


## Changelogs

The per-component files stay. Each train releases the components it owns: a client train its
`client/<language>` component, a game train its server and services, the tools train `tools/krpctools`.

* **A fragment can span trains.** A train's release folds only its own components' sections out of
  each fragment, and deletes a fragment once it is empty. `01-fold-changelogs.py` takes the train.
* **Release notes list one train's components.** Each game site's changelog lists that game's
  components. Each client site has its own changelog.

**`core` changes are logged in each game's Server section, at pull request time.** A `core` pull
request adds its user-facing entry to the Server changelog of each game, under that game's
unreleased header. Each game publishes the entry at its next release.

* **`core/CHANGELOG.md` is removed.** `core` does not appear in the release notes. A release page
  lists Server, then each service.
* **Until the split**, the `core` pull request adds the KSP entry, and the KSA pull request that
  picks up the new `core` adds the KSA one.

| Alternative | Rejected because |
| --- | --- |
| A `core` version train, with each game's notes appending the `core` sections it picked up | Another train to tag and bump, and `core` shown to users as a component |
| One entry in `core/CHANGELOG.md`, copied into each game's notes when that game is tagged | The tag script must track which entries each game has already released |
| Server entries written by hand just before each release | Depends on remembering `core` changes merged months earlier |

## Releasing

**A release is a release pull request, then a tag.** The pull request folds the train's changelog
sections and bumps its version. Pushing the tag runs that train's workflow, which builds, tests and
publishes.

* **Each release is small.** It covers one train and its channels, where today one release covers
  every channel in an evening.
* **Publishing runs in GitHub Actions**, from a `release` environment that holds the credentials and
  requires approval.
* **Trusted publishing where the channel offers it.** PyPI and NuGet accept a GitHub Actions identity,
  so no long-lived token is stored. The other channels keep their credentials as secrets in the
  environment.
* **A game release also publishes each client's stubs** to that client's channel, with the same
  credentials as the client's own release.

| Train | Publishes to | Credentials |
| --- | --- | --- |
| Python, Tools | PyPI | trusted publishing |
| C# | NuGet | trusted publishing |
| Java | Maven Central, GitHub | Central Portal token, GPG key |
| C++, C-nano | vcpkg pull request, GitHub; C-nano also the `krpc-arduino` repository | a GitHub token for the vcpkg fork and `krpc-arduino` |
| Lua | LuaRocks, S3 for the source archive, GitHub | LuaRocks API key, AWS keys |
| KSP | GitHub, then CKAN indexes it | `GITHUB_TOKEN` |
| KSA | GitHub, SpaceDock, Borea indexes it | SpaceDock credentials |

| Area | Change |
| --- | --- |
| `config.bzl`, `tools/krpc-version.sh` | One version per train. `krpc-version.sh` takes the train |
| `tools/release/*` | Split per train. The shared steps (fold, bump, tag) take the train, and each train has its own publish steps |
| `.github/workflows/` | A release workflow per train, triggered by its tag prefix |
| `50-release-github.py` | Creates the release with `--latest=false` |
| `.github/workflows/docs.yml` | A game tag freezes that game's site. A client or `krpctools` tag rebuilds that site's current major (see [Docs](#docs)). It stops triggering on bare `v*` |
| `BUILD.bazel`, `40-build-assets.py`, `70-announcements.py` | Assets per train. The mod archives are `krpc-ksp-v1.0.0.zip` and `krpc-ksa-v1.0.0.zip`, replacing `krpc-0.7.0.zip`. Announcements are for game releases |
| `tools/release/lib.py` | `TAG = "v" + VERSION` becomes one tag per train |
| `68-release-ckan.py` | Waits for `kRPC-v1.0.0.ckan`, named for the CKAN version (see below), not the tag |

Releases before the split keep their `v*` tags.

## Docs

**Each page belongs to one train, and each train's pages are versioned with it.** A version switcher
then lists the releases of exactly one train. A single game switcher over client pages would show
a client version that matches nothing in the dropdown.

| Site | Switcher | Contents |
| --- | --- | --- |
| `/` | none, built from `main` | Links to each game, client and the protocol, with their latest releases. kRPC development, third-party clients |
| `/ksp/` | KSP releases | Getting started, tutorials, user guides, the service API reference in each language, extending, the KSP changelog |
| `/ksa/` | KSA releases | The same for KSA |
| `/clients/<language>/` | that client's major versions | Installing, connecting, the client's own classes, its changelog |
| `/clients/krpctools/` | `krpctools` major versions | `clientgen`, `docgen`, `servicedefs`, the `TestServer`, `krpctest` |
| `/protocol/` | protocol versions | Communication protocols, the client spec, the compatibility table |

Each site has its own search.

**The top-level site is unversioned.** It holds the pages tied to no train, which always describe
`main`. Every push to `main` rebuilds it, and so does every release, to update the latest versions
it lists.

**The service API reference belongs to the game.** It is generated from the game's service
definitions, the same source as the stub packages. `/ksp/v1.0.0/` documents exactly what each
`ksp-v1.0.0` stub package contains. A later `docgen` change reaches the reference at the game's
next release.

**The user guides are written once and built per game**, as
[docs-website.md](ksa/docs-website.md) plans. Streams, events, control loops, server-side functions
and object lifetime are explained there, with an example per language in the game's API. These pages
take over the worked examples from today's client guides, which call `SpaceCenter` in 18 of 20
Python examples.

**A client site covers what does not depend on a game.** That is installing, connecting, the type
mapping, and the client's own classes, such as `Connection`, `Stream` and `Event`, and its errors.
Its examples call the `KRPC` service. A page that needs a real use links to the user guide of each
game.

**A client site keeps one snapshot per major version.** A `python-v1.4.2` tag rebuilds
`/clients/python/v1/` in place, and its footer states "Python client v1.4.2". `versionadded` and
`versionchanged` mark features added within a major. A new major freezes the previous one. `main`
builds `dev/` for each site.

**Links run from games to clients.** A game page links to `/clients/<language>/` for the latest
release. Each game snapshot states the minimum client versions its stubs require. A client page
never links into a game snapshot.

**The protocol site changes rarely.** A protocol version bump freezes `/protocol/v<n>/`. The
compatibility table and the conformance results are rebuilt by every client and game release.

| Today | Moves to |
| --- | --- |
| Getting started, tutorials, user guides | each game site |
| Client guides: install, connect, the client's classes | `/clients/<language>/` |
| Client guides: worked examples of streams, events and server-side functions | the user guides on each game site |
| Service API reference | each game site |
| Communication protocols, client spec | `/protocol/` |
| Extending | each game site, as [docs-website.md](ksa/docs-website.md) plans |
| `krpctools` | `/clients/krpctools/` |
| Third-party clients | `/` |
| kRPC development | `/` |

Other projects split their docs along release trains in the same way, as far as we recall without
checking the sites:

* **MongoDB** versions the server manual, and each driver's docs on their own, with a compatibility
  table of driver against server version.
* **Temporal** and **OpenTelemetry** have an unversioned concept site and a reference per SDK
  versioned by that SDK's releases. OpenTelemetry publishes a spec compliance matrix per language.
* **Elastic** moved from versioned guides per product to one site with version badges, since a
  snapshot per release across many products did not scale.

**Rejected: one site per game with client pages refreshed in place.** A game snapshot's switcher
shows the game version, and its client pages a newer client version. Each client release would have
to rewrite every game snapshot, or leave the older ones stale.

## CKAN and KSP-AVC

The KSP train's new tag and archive names break the CKAN indexing. The
[NetKAN entry](https://github.com/KSP-CKAN/NetKAN/blob/master/NetKAN/kRPC.netkan) needs a pull
request to KSP-CKAN/NetKAN, merged before the first `ksp-v` release:

```json
"$kref": "#/ckan/github/krpc/krpc/asset_match/^krpc-ksp-v[0-9]+\\.[0-9]+\\.[0-9]+\\.zip$",
"x_netkan_version_edit": "^ksp-(?<version>v.+)$",
```

* **The current `asset_match` misses the new archive.** `krpc-[0-9]+\.[0-9]+\.[0-9]+\.zip` needs a
  digit after `krpc-`. The indexer skips a release with no matching asset, so it would never index a
  `ksp-v` release.
* **The new pattern is anchored.** The old one would match a Lua `krpc-1.0.0.zip` on a client
  release. Neither `krpc-ksa-v` archives nor client archives match the new one.
* **The version needs its prefix stripped.** CKAN versions the mod from the tag, and takes only the
  KSP compatibility range from the `.version` file (`$vref: ksp-avc`). CKAN compares versions
  Debian-style, and `ksp-v1.0.0` sorts below `v0.7.0`, so CKAN would never offer the upgrade. The
  edit keeps the series going as `v1.0.0`.
* **`version_from_asset` does not help.** It gives `1.0.0`, which also sorts below `v0.7.0`.

KSP-AVC (`kRPC.version`, generated in `BUILD.bazel`):

* **`VERSION` and the `ksp-avc.cybutek.net` URL do not depend on the tag.** The manual bump on
  KSP-AVC online stays.
* **`DOWNLOAD` must name the release.** It points at `releases/latest`, and GitHub marks one release
  as latest across all trains. It becomes `https://github.com/krpc/krpc/releases/tag/ksp-v<version>`,
  generated from the KSP version.

## Versions at the split

| Train | First version |
| --- | --- |
| Clients and tools | 1.0, with kRPC 1.0 |
| KSP, and the KSP stub packages | 1.0, with kRPC 1.0 |
| KSA, and the KSA stub packages | continues from the prototype's 0.x |
