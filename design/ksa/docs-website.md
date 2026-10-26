# Documentation website

**Status:** proposal, 2026-10-26. Part of [KSA as a first-class game](README.md).

## Problem

The site documents KSP only. The KSA prototype has its own tree in `experimental/ksa/doc`, published
at `/experimental/ksa/`.

The game-agnostic pages are agnostic in prose only. Their examples call the KSP API:

| Pages | Examples using `space_center` |
| --- | --- |
| Python client guide | 18 of 20 |
| C++ client guide | 9 of 11 |
| Extending | 9 of 35 |
| Communication protocols | 0 of 7 |

The KSA client guides are short as a result. The Python one is 47 lines against KSP's 781, and has
no streams, events or server-side functions. Game-neutral examples are not an option, as the `KRPC`
service has nothing worth streaming.

## Design

One source tree, built once per game. Each game gets its own site:

| URL | Contents |
| --- | --- |
| `/` | Picks the game |
| `/ksp/dev/`, `/ksp/1.0.0/` | KSP build |
| `/ksa/dev/`, `/ksa/0.2.0/` | KSA build |

| Part | KSP build | KSA build |
| --- | --- | --- |
| Getting started, tutorials, user guides | KSP pages | KSA pages |
| Client guides | shared prose, KSP examples | shared prose, KSA examples |
| API reference | SpaceCenter and the mod services | `KSA` |
| Communication protocols | shared | shared |
| Extending | shared prose, KSP mod examples | shared prose, StarMap and Harmony specifics |
| Changelog | KSP, clients and tools | KSA, clients and tools |

* **The shared prose is written once.** Copying the KSP guides into a KSA tree would give two copies
  that drift apart.
* **Each build has its own search**, so a KSA reader gets no KSP results.
* **Rejected: one site with a game tab in each example.** Six language tabs become twelve, and each
  page still mixes two games.

## Mechanics

* **One flag per build.** Sphinx runs with `-t ksp` or `-t ksa`. `.. only::` covers small
  differences in prose, and a substitution gives the game's name.
* **An example directive.** `.. example:: client/Streaming1` resolves
  `scripts/<game>/client/Streaming1.*` and emits one tab per language. This also replaces the
  six-tab `literalinclude` block repeated on every page.
* **Examples are checked per game.** KSA examples compile and type-check against the KSA stubs, in
  the existing `//doc:compile-scripts`.
* **A shared page with no KSA example is left out of the KSA build.** It is never shown with KSP
  code. The KSA build can launch with a core set (connecting, calls, streams, events, server-side
  functions) and grow.
* **`//doc:html` builds both sites.** `//doc:spelling` and `//doc:check-documented` run on each.

## Versioning

* **Snapshots follow the release trains** ([releases.md](releases.md)): a `ksp-v*` tag freezes
  `/ksp/<version>/`, a `ksa-v*` tag freezes `/ksa/<version>/`. `main` updates both `dev/` builds.
* **Each snapshot carries the shared client guides as of its release.** They describe the protocol
  and client features, which are the same for both games.
* **The existing snapshots stay where they are** (`/0.5.4/`, `/0.7.0/`, ...). The version switcher
  lists them under KSP. `/experimental/ksa/` redirects to `/ksa/`.

This extends [versioned-docs-website.md](../build-tools/versioned-docs-website.md), which built the
current single-game switcher.

## Cost

The work is KSA versions of the examples in the shared pages. That is about 20 client-guide
examples per language, across six languages, plus the extending examples. The core set can go first.
