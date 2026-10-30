# Listing on Borea

**Status:** in progress. Part of [kRPC for KSA](README.md). Target: the
`ksa-v0.2.0` release. `ksa-v0.1.0` is not listed.

[Borea](https://github.com/KSAModding/Borea) is the community mod manager for KSA. It installs
from the KSAModding content index: one authored TOML listing per mod in
[content-index](https://github.com/KSAModding/content-index), plus a watcher that stamps each new
release of a listed mod into
[content-index-releases](https://github.com/KSAModding/content-index-releases). The format is
RFC 0031 and RFC 0035 in
[content-manager-design](https://github.com/KSAModding/content-manager-design).

## Problem

The 0.1.0 archive nests the mod folder one level too deep:

```text
kRPC-KSA-0.1.0/
  kRPC.KSA/mod.toml
  stubs/  examples/  README.txt  COPYING ...
```

The stamper derives the install root as the one top-level directory that holds `mod.toml`, named
after the listing id. Run on the 0.1.0 zip, it fails with `the archive's top-level directory is
'kRPC-KSA-0.1.0', which does not match the id 'kRPC.KSA'`.

An authored `[install] root = "kRPC-KSA-0.1.0/kRPC.KSA"` passes, but the root carries the version.
Every release would need a listing edit merged before the watcher sees the tag, or the watcher opens
an error issue.

## Changes in krpc

| Area | Change |
| --- | --- |
| `experimental/ksa/release.sh` | Drop the `kRPC-KSA-<version>/` top folder. `kRPC/`, `stubs/`, `examples/`, the readme and licenses sit at the zip root |
| `experimental/ksa/release.sh` | Also copy `COPYING`, `COPYING.LESSER` and the third-party licenses into `kRPC/`, since Borea installs only that folder |
| `server/mod.toml`, the build scripts, the docs | Rename the mod id and folder from `kRPC.KSA` to `kRPC`, before the id becomes permanent. The docs say how to upgrade from 0.1.0 |
| `experimental/ksa/release/README.txt`, KSA install docs | Manual install says to copy `kRPC` into `mods`, and mention Borea |
| Before tagging | Start the mod once in a Borea instance, as Borea's [mod author guide](https://github.com/KSAModding/Borea/blob/main/docs/mod-authors.md) asks |

With `kRPC/` at the top, derivation finds it: `stubs/` and `examples/` hold no `mod.toml`, and
loose files at the root are ignored. The listing then needs no `[install]` section.

The mod is already instance-safe. It reads `settings.toml` from its own folder, via the assembly
location, and never builds the `Documents/My Games` path itself.

The server window writes the user's edits to that `settings.toml`. By default Borea links every
instance to one shared copy of the mod folder, so an edit in one instance would change the others.
The listing claims the file with `[install] manages`, which gives each instance its own copy. A
Borea update replaces the whole folder, file included, so an update restores the default
settings. Before 1.0 this is deliberate: a change to the settings format needs no migration.

## The listing

`listings/kRPC.toml` in content-index:

```toml
spec_version = 1
id = "kRPC"
type = "mod"
name = "kRPC for KSA"
authors = ["djungelorm"]
abstract = "Control Kitten Space Agency from your own scripts, over a network connection."
license = "LGPL-3.0-or-later"
tags = ["tools"]

[install]
manages = ["settings.toml"]

[releases]
github = "krpc/krpc"
tag_prefix = "ksa-v"

[links]
forums = "https://forums.ahwoo.com/threads/..."
repository = "https://github.com/krpc/krpc"
bugtracker = "https://github.com/krpc/krpc/issues"

[compatibility]
game_min = "2026.10.19.5638"

[loader]
id = "StarMap"
min = "0.4.8"
```

| Field | Note |
| --- | --- |
| `id` | The installed folder name, and permanent. A rename is a new listing plus deprecating the old one |
| `license` | `LGPL-3.0-or-later` matches "any later version" in the release `LICENSE` |
| `tags` | From `tags.toml`: parts, celestial, gameplay, user-interface, visual, audio, tools, library |
| `install.manages` | The server window rewrites `settings.toml`. The claim gives each instance its own copy of the mod folder |
| `tag_prefix` | Required: krpc/krpc also publishes the KSP `v*` releases. The watcher reads `ksa-v0.2.0` as `0.2.0`, and skips other `ksa-` tags such as a future `ksa-experimental-v0.3.0` |
| `links.forums` | Required for a mod. The KSA forum thread has to exist first |
| `game_min`, `loader.min` | The versions the release was tested against. Update when 0.2.0 is tested on newer ones |
| `description`, `[images]` | Optional. Images stay on our host, with sha256 and size records from `tools/image_record.py` |
| `spacedock`, `authority` | Only if the release is also on SpaceDock. `authority = "github"` keeps GitHub as the source |

## Ownership proof

krpc/krpc is owned by an organization, so the proof is the repo topic `ksa-index-djungelorm` on
krpc/krpc (RFC 0038). It covers every listing that points at the repo. A marker file,
`.github/ksa-content-index.toml`, also works, but would ship in krpc.

## Steps

1. Change `release.sh` and the install docs, as above. Done, not yet in a PR. The archive installs
   and runs in a Borea 0.5.2 instance on Linux, from a local index entry. TCP and gRPC clients
   connect.
2. Tag and release `ksa-v0.2.0`.
3. Post the KSA forum thread.
4. Add the topic to krpc/krpc.
5. Open the content-index PR with the listing. Run its local checks first (`check_layout.py`,
   `check_schema.py`, `check_index.py`, `check_license.py`, then `check_release.py` with
   content-index-releases checked out beside it). A green PR with verified ownership merges itself.
6. Later releases need nothing: the watcher stamps each new `ksa-v*` release.

## Open questions

* **SpaceDock.** Whether to upload there too, and which host is the authority.
