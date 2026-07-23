# LiDAR & DockingCamera services — integration tests (blocked on mod sourcing)

**Status:** proposal — investigated 2026-07-16; full real-API coverage blocked on mod sourcing, the
lightweight tests (option 3) are unblocked and recommended. No GitHub issue yet — one should be
filed. Two sibling services, `service/LiDAR/` and `service/DockingCamera/`, have shipped since v0.5.0
with **zero tests** — no `test/` directory, no lint or integration coverage, and both are absent from
the top-level `//:test` and `//:lint` suites (they appear in `BUILD.bazel` only in the release
filegroup/packaging). The goal was "add tests for the whole service(s)"; this doc records why that is
not straightforward and what the realistic paths are.

Both are thin **bridge services**: a static service class with an `Available` flag and a factory that
wraps a part, plus a wrapper class exposing one real feature read from a third-party mod through a
reflection-loaded `API` type. They share the same structure, the same blocker, and the same options —
hence one doc.

## The service surfaces

**LiDAR** (id 10):
* `LiDAR.Available` — `API.IsAvailable`.
* `LiDAR.Laser(Part)` → `Laser` — throws `InvalidOperationException("LiDAR is not available")` via
  `CheckAPI()` when the mod is absent; else constructs a `Laser`, which throws
  `ArgumentException("Part is not a LiDAR")` unless the part has a `LiDARModule`.
* `Laser.Part`; `Laser.Cloud` (`IList<double>`) — a point cloud via `API.GetCloud(part)`, empty list
  when unavailable; equality/hash on `Part`.
* Binds via `APILoader.Load(typeof(API), "LiDAR", "LiDAR.API")` — assembly `LiDAR`, type `LiDAR.API`.

**DockingCamera** (id 11):
* `DockingCamera.Available` — `API.IsAvailable`.
* `DockingCamera.Camera(Part)` → `Camera` — throws `InvalidOperationException("Camera is not
  available")` when absent; else constructs a `Camera`, which throws `ArgumentException("Part is not
  a Camera")` unless the part has a `PartCameraModule`.
* `Camera.Part`; `Camera.Image` (`byte[]`) — a captured image via `API.GetImage(part)`, empty array
  on any failure (the getter catches and logs); equality/hash on `Part`.
* Binds via `APILoader.Load(typeof(API), "DockingCamKURS_", "OLDD_camera_.API")` — assembly
  `DockingCamKURS_`, type `OLDD_camera_.API`.

`API.Load()` in each uses `APILoader`, which finds a **loaded KSP assembly by exact name**, pulls the
named static type, and wires the delegate(s) (`GetCloud` / `GetImage`) by reflection. `Available` is
true iff that exact assembly is present with that exact type and method.

## The blocker: both bind to bespoke bridge builds, not the public mods

Each service's `Available` requires a mod DLL that exposes a **kRPC-specific bridge type** (`LiDAR.API`
with `GetCloud`, or `OLDD_camera_.API` with `GetImage`). Neither bridge exists in the mods' public
releases — they were compiled against custom/forked builds.

### LiDAR → nullprofile's LaserDist fork (unreleased, unpinnable)

The docstrings say "LaserDist" and the docs link `github.com/nullprofile/LaserDist`, but the code
binds to assembly `LiDAR` / `LiDAR.API` / module `LiDARModule` — none of which exist in mainline
LaserDist.

* **Mainline [Dunbaratu/LaserDist](https://github.com/Dunbaratu/LaserDist)** (latest v1.4.0, 2021):
  a single-beam *distance meter*. Assembly `LaserDist`, module `LaserDistModule`, distance via
  KSPFields; **no point cloud and no kRPC API assembly.** Cleanly pinnable (`LaserDist_v1.4.zip`,
  sha256 `45228b19a5c9e2544c7aa0748bb07503394ef3abdd1ef045072866126a50a048`) but does not satisfy the
  service.
* **[nullprofile/LaserDist](https://github.com/nullprofile/LaserDist)** (fork, master @ `f8a385cf…`,
  2022-04-18): rewrites the part into a multi-beam LiDAR — `LiDARModule` accumulates an 8-beam
  `cloudData`, and `src/LaserDist/{LiDAR,API}.cs` add `LiDAR.API.GetCloud(Part)` built as assembly
  `LiDAR`. This is what the service targets. **But it has no releases, and its repo has no
  install-ready `GameData`** (only `LaserDist.version`; no compiled `LiDAR.dll`; parts/models
  scattered under `src/` and `UnityModel/…/Assets/`). Nothing pinnable — building a working GameData
  means compiling the C# against KSP assemblies *and* producing the Unity `.mu` assets.

### DockingCamera → Docking Camera (KURS): mod released, bridge API not in it

The base mod **is** real, maintained, and cleanly pinnable — unlike LiDAR's fork — but the *bridge
build* the service needs is not published.

* Base mod: **[Docking Camera (KURS)](https://spacedock.info/mod/1542)** by DennyTX, re-adopted by
  linuxgurugamer. Latest **v1.3.9** (KSP 1.12.5) on SpaceDock, install-ready GameData with a prebuilt
  DLL. Version-pinned download:
  `https://spacedock.info/mod/1542/Docking%20camera%20(KURS)/download/1.3.9`
  (sha256 `b2f6d153edc65d0e39049c2d1da8ad818d51705d66e1c1413f9a3f0520974413`). Also on CKAN and
  archive.org.
* **But** the released DLL's assembly is `DockingCamKURS` and its namespace is `OLDD_camera` — **no
  trailing underscores** — and it contains **no `API` type and no `GetImage` method** (verified with
  `monodis --typedef/--method` on v1.3.9 and v1.3.8.3; the module class is
  `OLDD_camera.Modules.PartCameraModule`). The service binds to `DockingCamKURS_` / `OLDD_camera_.API`
  (both underscored) — a bespoke kRPC-integration build. So installing even the latest public release
  leaves `DockingCamera.Available == False`.
* The KSP-side module name `PartCameraModule` *does* match `Camera.Is()`, so wrapper construction
  would work once `Available` were true. The mod's ModuleManager patch adds a *different* module
  (`DockingCameraModule`) to every stock docking port, which the kRPC `PartCameraModule` check does
  **not** match — kRPC cameras only bind to the standalone `OnboardCamera` part.

## Options (apply to both services)

1. **Author supplies the built bridge DLL(s).** djungelorm (service author) provides the custom mod
   builds that expose `LiDAR.API.GetCloud` / `OLDD_camera_.API.GetImage`, as install-ready `GameData`.
   Wire each as a managed mod (mirror the four registration points used by RemoteTech/IR/KAC:
   `MODULE.bazel` `http_archive`, `tools/mods/BUILD.bazel`,
   `tools/krpctest/krpctest/install.py` `MODS`, `game.py` `_MOD_SERVICES`), add craft fixtures (a
   `PartsLiDAR.craft` with a LiDAR part; a `PartsDockingCamera.craft` with an `OnboardCamera`), and
   write full real-API tests: `available == True`, factory, `part`, `cloud`/`image`, equality. Each
   needs an in-game run to validate. **Cleanest full coverage — but only if a stable, pinnable build
   can be hosted** (a kRPC-owned mirror release is the robust form; `http_archive` needs a URL +
   sha256). For DockingCamera the base assets already exist publicly; only the bridge DLL is missing.
2. **Pin fork/base source at a commit and build in-tree.** Compile the bridge DLL from source against
   the KSP stub assemblies and stage GameData. Heaviest; reproducibility of the prebuilt Unity `.mu`
   assets is uncertain (LiDAR fork especially). Not recommended unless option 1 is impossible.
3. **Lightweight tests now, defer the mod (recommended first step).** Ship the no-mod path for each —
   the only thing runnable without a bespoke build, and it still covers the guard logic:
   * `available == False`
   * `laser(part)` / `camera(part)` raises `RuntimeError: LiDAR is not available` / `Camera is not
     available`

   plus `service/<svc>/test/{test_<svc>.py,pylint.rc}`, a `test`/`lint`/`pylint` suite in each
   `service/<svc>/BUILD.bazel`, and `//service/LiDAR:test`/`:lint` + `//service/DockingCamera:test`/
   `:lint` added to the top-level `BUILD.bazel` suites. Structure the test files so a
   `mods = ["LiDAR"]` / `mods = ["DockingCamera"]` real-API `TestCase` slots in later. File an issue
   for the real-API tests.
4. **Modernize the services against the public mods (separate track).** Re-point each service at a
   currently-released mod's real API. For DockingCamera this is the most viable — the base mod is
   maintained; but it exposes no image bridge, so this means either persuading upstream to add a kRPC
   API or capturing the image in kRPC itself (reading the camera's `RenderTexture`), i.e. a service
   redesign, not a test task. For LiDAR, mainline LaserDist has no point cloud, so the `Cloud` feature
   would have to be dropped. Breaking; out of scope here; worth its own issue if depending on bespoke
   builds is judged too fragile.

## Recommendation

Do **option 3 now** for both services (unblocked, real value, closes the `//:test`/`//:lint` gap and
establishes the wiring), and file an issue capturing options 1/2/4 for real-API coverage. Prefer
**option 1** for the eventual full tests *if* stable pinnable builds can be hosted — most tractable
for DockingCamera, where only the bridge DLL is missing atop an already-public mod. Revisit **option
4** only if maintaining bespoke-build dependencies is judged not worth it.

## Incidental cleanups to fold in

* **Misleading docstrings.** LiDAR's `LiDAR.cs`/`Laser.cs` describe a "LaserDist service"/"LaserDist
  API"/"LaserDist part"/"LaserDist laser" while binding to the `LiDAR` assembly and `LiDARModule`.
  Reword to "LiDAR mod" and note the mainline-vs-fork distinction so readers aren't sent to the wrong
  mod. (DockingCamera's docstrings are generic — "Camera service" — and are fine.)
* **DockingCamera debug spam.** `Camera.Image` logs `Debug.Log("CAMERA IMAGE: OK"/"FAILED"/…)` on
  every access — noisy per-frame logging that should be dropped or gated to a debug level.
* Both services are missing from `//:test` and `//:lint` regardless of mod availability — the lint
  wiring alone (option 3) closes that gap.
