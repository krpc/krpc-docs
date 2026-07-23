# Move the NameTag PartModule into KSPCommunityPartModules

**Status:** in progress — implemented across all three repos and verified in-game; three PRs open,
awaiting the KSPCommunityPartModules 0.5.0 release before the two dependents can merge.

**Issue:** [krpc/krpc#829](https://github.com/krpc/krpc/issues/829) — "KOSNameTag PartModule should
probably not be duplicated to avoid issues with KOS". This work also subsumes the previously-planned
NameTag editor click-through fix.

- KSPCommunityPartModules:
  [KSPModdingLibs/KSPCommunityPartModules#23](https://github.com/KSPModdingLibs/KSPCommunityPartModules/pull/23)
  — the shared `ModuleNameTag` module, editor-bug fixes, and the
  Harmony migration shim.
- kRPC: [krpc/krpc#965](https://github.com/krpc/krpc/pull/965) (draft, targets `main`).
- kOS: [KSP-KOS/KOS#3197](https://github.com/KSP-KOS/KOS/pull/3197) (draft, targets `develop`).

Verified: `service/SpaceCenter/test/test_parts_part.py` 31/31 in-game (against a local build of the
KSPCommunityPartModules branch), including loading craft that still carry old `KOSNameTag` nodes, which
exercises the migration shim. kOS + KSPCPM compile-checked.

Remaining before the dependents can merge:
- Settle the GPLv3→MIT licensing of the imported file (raised on KSPCPM #23).
- Cut a KSPCommunityPartModules **0.5.0** release (the first with `ModuleNameTag`); bump its
  `KSPAssembly` version and add the README entry (both intentionally left out of #23 for the maintainer).
- Fill the real `sha256`/URL for that release into kRPC's `MODULE.bazel` (currently a placeholder).
- Add the CKAN `depends` on KSPCommunityPartModules to kRPC and kOS (in the NetKAN meta-repo).

## Problem

kRPC and kOS **each** ship their own `KOSNameTag : PartModule` — an identical part module holding a
persistent `public string nameTag` field plus a "Change Name Tag" IMGUI editor window. kRPC's copy
(`service/SpaceCenter/src/NameTag/`) is itself an adaptation of kOS's
(`src/kOS/Module/KOSNameTag.cs` + `src/kOS/Screen/KOSNameTagWindow.cs`).

Two loaded assemblies defining the same simple type name `KOSNameTag` is only safe by luck: KSP
resolves a type-by-name lookup against `loadedAssemblies` in load order, and kOS currently sorts
before kRPC alphabetically, so the "right" one wins. A recent KSPCommunityFixes change
(KSPModdingLibs/KSPCommunityFixes#307) demonstrated that this breaks the moment anything perturbs load
order (e.g. kOS gaining a new dependency). JonnyOThan (a KSPCommunityPartModules maintainer) proposed
the fix in the issue: define the module **once** in the shared **KSPCommunityPartModules (KSPCPM)**
mod and have both kRPC and kOS depend on it.

While relocating, we also fix two long-standing editor bugs in the window (inherited by both copies):

1. **Click-through** — the window locks editor input with
   `EditorLogic.fetch.Lock(false, false, false, "KOSNameTagLock")`, whose all-`false` flags never lock
   part pick/place, so clicking Accept/Cancel drags whatever part sits behind the button.
2. **Lock-ID collision** — the editor lock ID is a fixed string, so with two name-tag windows open,
   closing one releases the lock for both.

## Goals / non-goals

- **Critical:** existing craft/saves tagged with the old module keep their tags after the switch.
- **Nice-to-have only:** the reverse direction (a craft saved by the new mods, loaded in an old
  kRPC/kOS) — accepted as lossy.
- Fix the two editor bugs in the single shared copy.
- Both kRPC and kOS take a **hard dependency** on KSPCPM.

## Decisions

1. **Shared class = `KSPCommunityPartModules.Modules.ModuleNameTag`** — a generic name following
   KSPCPM's `Module*` convention (not the kOS-specific `KOSNameTag`). The persistent field keeps its
   current name **`nameTag`**: it is the save key and the access target for both consumers, so there is
   no reason to churn it.
2. **Migration shim** (KSPCPM, Harmony): because the class is renamed, a saved
   `MODULE { name = KOSNameTag, nameTag = "..." }` node would no longer match the `ModuleNameTag`
   prefab and the tag would be lost. A Harmony patch rewrites the legacy module name to `ModuleNameTag`
   on the part-module load path, so old data binds to the new module. The field name is unchanged, so
   `nameTag` binds directly.
3. **The ModuleManager "add to every part" patch stays in kOS and kRPC** (each ships its own, guarded
   with `:HAS[!ModuleNameTag]` to dedup when both are installed). KSPCPM ships the module class only,
   preserving its "no effects on its own" philosophy. A player with only one of the two still gets tags.
4. **Import from kOS verbatim first.** kOS is the source of truth. PR-A's first commit copies kOS's
   files unchanged, and subsequent focused commits evolve them, so the git history separates "imported"
   from "changed".

## Save-format / compatibility contract

- Old saves: `MODULE { name = KOSNameTag, nameTag = "..." }`; new prefab module: `ModuleNameTag`.
- KSP matches a saved MODULE node to a prefab module by the node's `name`. The migration shim rewrites
  `KOSNameTag` → `ModuleNameTag` before that match, so the value binds; `nameTag` is unchanged.
- New saves write `name = ModuleNameTag`; an old kRPC/kOS looking up `KOSNameTag` won't find it — the
  accepted nice-to-have-only loss in the reverse direction.

## Licensing

kOS is **GPLv3**; KSPCPM is **MIT**. Importing kOS's nametag source into KSPCPM cannot silently
relicense it. This must be resolved before the verbatim-import commit lands — either the original kOS
nametag author agrees to relicense that file under MIT, or the file is carried under GPLv3 within
KSPCPM with an explicit per-file header and a LICENSE note. The import commit message states the
provenance and the chosen license either way. Decision belongs to the KSPCPM maintainer.

## Work breakdown

Three coordinated PRs, one per repo — kRPC [#965](https://github.com/krpc/krpc/pull/965),
kOS [#3197](https://github.com/KSP-KOS/KOS/pull/3197), KSPCPM
[#23](https://github.com/KSPModdingLibs/KSPCommunityPartModules/pull/23).

### PR-A — KSPCommunityPartModules (add the shared module)

Focused commits, in order:

1. **Import verbatim** — copy kOS's `KOSNameTag.cs`, `KOSNameTagWindow.cs`, and the helpers they
   reference (`Utils.GetCurrentCamera`, `Career.CanTagInEditor`) into `Source/Modules/`, unchanged.
2. **Make it build in KSPCPM** — namespace to `KSPCommunityPartModules.Modules`; drop kOS-only deps
   (`SafeHouse.Logger` → `Debug.Log` with a `[{MODULENAME}]` prefix; `kOS.Safe.*` usings); add the
   files to the (non-globbed) `Source/KSPCommunityPartModules.csproj`; apply KSPCPM header-comment /
   `MODULENAME` conventions. Class name stays `KOSNameTag` for now.
3. **Rename to `ModuleNameTag`** — rename the class and the window's `attachedModule` type; keep the
   `nameTag` field; neutralize UI strings (window title → "Name tag").
4. **Fix the editor bugs** — replace the no-op `EditorLogic.Lock` with
   `InputLockManager.SetControlLock(ControlTypes.EDITOR_LOCK, lockId)` in `OnGUI` and
   `RemoveControlLock(lockId)` in `Close()`; make `lockId` per-instance
   (`"NameTagLock" + GetInstanceID()`). Keep the `e.Use()` suppression as defense-in-depth.
5. **Simplify for shared use** — keep kOS's `OnAwake()` duplicate-removal guard (kOS#2764: EVA/DLC
   parts double-add the module); remove the `KOSNameTagActivationManager` `isEnabled` PAW
   micro-optimization and set `guiActive=true` directly.
6. **Migration shim** — `Source/HarmonyPatches/NameTagMigrationPatch.cs`: rewrite legacy `KOSNameTag`
   MODULE-node names to `ModuleNameTag` on the load path. Verify the hook against the KSP disassembly;
   `Part.LoadModule(ConfigNode, ref int)` is the likely target (covers editor `.craft` and flight
   `ProtoPartSnapshot` load). Guard against clobbering a real `KOSNameTag` type if the retired
   standalone NameTag mod is present.
7. **Packaging** — bump `KSPAssembly` version `0.4` → `0.5`; add ModuleNameTag to `README.md`;
   optionally localize the `guiName`.

### PR-B — kRPC (drop own module, depend on KSPCPM)

kRPC reaches the module purely by reflection on a module-name string, so no compile-time reference is
needed.

- Delete `service/SpaceCenter/src/NameTag/` (4 files); remove the 4 `<Compile Include="NameTag\...">`
  entries from `KRPC.SpaceCenter.csproj` (the Bazel `glob` needs no change).
- Retarget `Part.Tag` (`service/SpaceCenter/src/Services/Parts/Part.cs`): change the two
  `Module("KOSNameTag")` lookups to `"ModuleNameTag"`; update the XML `<remarks>` (shared via
  KSPCommunityPartModules, kept compatible with kOS).
- `module-manager.cfg` → `@PART[*]:FOR[kRPC]:HAS[!ModuleNameTag] { MODULE { name = ModuleNameTag } }`.
- Hard dependency: a one-line assembly-attribute file with
  `[assembly: KSPAssemblyDependency("KSPCommunityPartModules", 0, 5)]`.
- Remove the NameTag provenance block from `LICENSE`.
- **Test harness:** with the assembly dependency, no in-game test loads SpaceCenter unless KSPCPM is in
  GameData. Install a pinned KSPCPM release as an always-on managed mod (reuse the RealChute/AGExt
  plumbing: `MODULE.bazel` archive + `tools/mods` install + root `BUILD.bazel` GameData layout). Do not
  bundle KSPCPM in the release — dependency via CKAN + the assembly attribute.
- Update the ~25 `"KOSNameTag"` module-list assertions in `test/test_parts_part.py` to
  `"ModuleNameTag"`; leave `test/craft/*.craft` as-is so loading them exercises the migration shim.
- Changelog (final pre-merge commit only) under `v0.6.0`.

### PR-C — kOS (drop own module, depend on KSPCPM)

kOS uses the module by compile-time type (`OfType<KOSNameTag>()`), so it needs a real reference to
KSPCPM.dll.

- Delete `src/kOS/Module/KOSNameTag.cs` (module + `KOSNameTagActivationManager`) and
  `src/kOS/Screen/KOSNameTagWindow.cs`; remove `src/kOS/Suffixed/Career.cs` if it has no other callers.
- Retarget references from `kOS.Module.KOSNameTag` to `KSPCommunityPartModules.Modules.ModuleNameTag`
  (`.nameTag` access unchanged): `src/kOS/Suffixed/Part/PartValue.cs` (TAG suffix +
  PARTSTAGGED/PARTSDUBBED/ALLTAGGEDPARTS), `src/kOS/Module/kOSProcessor.cs`, and the display reads in
  `TelnetWelcomeMenu.cs`, `TermWindow.cs`, `KOSToolbarWindow.cs`.
- Add a `<Reference>` to KSPCPM.dll in `kOS.csproj` (mirroring the ICSharpCode reference,
  `<Private>false</Private>`) plus `[assembly: KSPAssemblyDependency("KSPCommunityPartModules", 0, 5)]`.
- `kOS-module-manager.cfg` → `@PART[*]:FOR[kOS]:HAS[!ModuleNameTag] { MODULE { name = ModuleNameTag } }`.
- Update `CHANGELOG.md` (module moved to KSPCommunityPartModules, now a required dependency).

### Out-of-repo

- **CKAN**: add `KSPCommunityPartModules` to kRPC's and kOS's CKAN `depends` in the NetKAN meta-repo
  (neither repo carries its own netkan). Call this out in the PR descriptions.

## Verification

- KSPCPM builds standalone (KSPBuildTools) and produces `KSPCommunityPartModules.dll` with
  `ModuleNameTag` + the migration patch.
- kRPC in-game tests, with KSPCPM installed:
  `bazel run //:test-ingame -- service/SpaceCenter/test/test_parts_part.py -v`. Confirm module-list
  assertions see `ModuleNameTag` and `Part.Tag` round-trips; the existing craft (old `KOSNameTag`
  nodes) loading green proves the migration shim end-to-end.
- Backwards-compat spot check (manual): load a pre-existing tagged craft/save in new kRPC+KSPCPM;
  confirm the tag persists.
- Click-through (manual, VAB): a part directly behind Accept/Cancel is not dragged when clicked; typing
  + Accept still saves; the lock releases on close; two open windows don't unlock each other.
- kOS builds against KSPCPM.dll; `part:TAG`, `PARTSTAGGED`/`PARTSDUBBED` still resolve tags.
