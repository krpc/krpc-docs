# Name tags from KSPCommunityPartModules or kOS (#829)

**Status:** implemented, PR not yet opened. Fixes #829 and supersedes PR #965. Labels: `bug`,
`mod-compatibility`, `service:space-center`.

kRPC shipped its own `KOSNameTag` part module, a copy of kOS's. With both mods installed, two
assemblies defined the same type name, and KSP picked one by load order (#829).

The shared module now ships in KSPCommunityPartModules (CPM) 0.5.0 and later as `ModuleNameTag`.
CPM also has a Harmony patch that renames `KOSNameTag` save nodes on load, but only when no
`KOSNameTag` type is loaded. The kOS change to use it (KSP-KOS/KOS#3197) is stalled, so released
kOS (1.6.0.1) still defines `KOSNameTag`.

PR #965 made CPM 0.5 a hard dependency and always added `ModuleNameTag`. That broke with old CPM,
and with released kOS it gave every part two tag modules.

## Behavior

kRPC ships no tag module. `Part.Tag` uses whichever of `ModuleNameTag` or `KOSNameTag` is on the
part:

| Install | Module on parts | `Part.Tag` |
| --- | --- | --- |
| kRPC + old CPM (or no CPM) | none | throws, naming CPM 0.5 or kOS |
| kRPC + new CPM | `ModuleNameTag` | works, and CPM migrates `KOSNameTag` craft and saves |
| kRPC + old CPM + kOS | `KOSNameTag` (kOS) | works |
| kRPC + new CPM + kOS | `KOSNameTag` (kOS) | works |
| kOS on CPM (after KOS#3197) | `ModuleNameTag` (kOS) | works, with no kRPC change |

## Design decisions

| Decision | Reason |
| --- | --- |
| ModuleManager only decides which module goes on parts | Detecting the C# class would need a loader or a marker assembly. CPM 0.4 and 0.5 have the same GameData, so `NEEDS` cannot tell them apart. |
| Patch: `@PART[*]:HAS[!MODULE[ModuleNameTag]]:NEEDS[KSPCommunityPartModules&!kOS&!NameTag]:FOR[kRPC]` | `!kOS` keeps one tag module per part with released kOS. PR #965's `HAS[!ModuleNameTag]` tested a key, not a module. |
| Old CPM without kOS: log spam accepted | The patch names a missing class. KSP logs an error per part and compiles the part without the module. |
| No kRPC fallback module | A fallback module would be the duplicate #829 removes. |
| Warn only when tags would be lost | A new addon scans a loaded save (`onGameStateLoad`) and editor craft (`ShipConstruction.ShipConfig`). It shows a popup with the count, and adds the install hint when no tag module exists. Users without tags see nothing. |

The warning also covers one leftover case: a save made with new CPM and later loaded with released
kOS. Its `ModuleNameTag` nodes match no module on the parts.

## Implementation

* `service/SpaceCenter/src/NameTag/` is deleted, along with its kOS clause in `LICENSE`.
* New `NameTag.cs` (tag module lookup) and `NameTagWarningAddon.cs`.
* Test mods: CPM 0.5.1, CPM 0.4.0 and kOS 1.6.0.1. A new `TestingTools.AssemblyVersion` tells
  the two CPM versions apart.
* All test craft and saves use `ModuleNameTag`. Only `PartsTagLegacy.craft` keeps `KOSNameTag`.
* SpaceCenter changelog: a `**Breaking:**` entry and a warning entry.

## Verification

* `test_parts_tag.py`: 12/12 over five mod sets (none, CPM 0.4, CPM 0.5, CPM 0.4 + kOS,
  CPM 0.5 + kOS), including migration of the legacy craft.
* `test_parts_part.py`: 29/29.
* Warning, by hand with a tagged save: warns with no mods (with the install hint) and with
  CPM + kOS, and is silent with CPM alone. The log line was checked, but the dialog was not looked
  at on screen.

## Follow-ups

* Close PR #965 when the PR is opened.
* Add a `recommends` for KSPCommunityPartModules to kRPC's NetKAN metadata (external to `krpc`).
