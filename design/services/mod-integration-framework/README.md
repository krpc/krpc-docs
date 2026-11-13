# Mod integration framework

**Status:** implemented, for 0.8. All seven phases are built and checked in game, not yet merged.
The design dates from 2026-11-12, and each phase records where it diverged. Issue:
[mod-integration-framework.md](../../../issues/mod-integration-framework.md).

The entry point for the shared machinery behind kRPC's mod integrations: the build, the binding to
the mod, the availability check, the in-game tests and the tested mod versions. It states the
problems and orders the work into phases. Refactoring comes before new behavior.

The doc assumes the Raster Prop Monitor service is on main, as the fourteenth integration.

| Doc | Covers |
| --- | --- |
| This page | The problems, the phases, and the detail of phases 1, 2, 6 and 7 |
| [binding.md](binding.md) | Phase 3: `MemberBinder`, stubs for missing members, one binding per mod |
| [mod-api.md](mod-api.md) | Phase 4: `ModAPI`, loaded at startup, a failed mod disables only its integration |
| [requires-mod.md](requires-mod.md) | Phase 5: `[RequiresMod]` in place of `CheckAPI` |

Related:

* [Partial loading](../../server/partial-loading.md) and
  [problem reporting](../../server/problem-reporting.md) (#1227): scanner errors disable only the
  broken members, and one popup lists them with the failed mods. They follow this work.
* `KRPC.Utils.Accessor` (PR #1251) and [mod-compat-test-coverage.md](../mod-compat-test-coverage.md)
  (done, #1319) are what this work builds on.
* [service-versioning.md](../service-versioning.md) is a negative result about per-service API
  versions, unrelated to the mod versions in [phase 6](#phase-6-tested-mod-versions-in-the-docs).

## Inventory

| Integration | Where | Binding today | Availability check |
| --- | --- | --- | --- |
| Infernal Robotics | `service/InfernalRobotics` | `IRWrapper` (1322 lines, a vendored wrapper), binds on entering flight | `CheckAvailable`, "is not installed." |
| Kerbal Alarm Clock | `service/KerbalAlarmClock` | `KACWrapper` (719 lines, vendored), own version check, binds on the first alarm | `CheckAPI` on `KACWrapper.APIReady` |
| RemoteTech | `service/RemoteTech` | `APILoader` | `CheckAPI` |
| Docking Camera (KURS) | `service/DockingCamera` | Own `API.Load` | `CheckAPI` |
| LIDAR (deprecated) | `service/LiDAR` | Own `API.Load` | `CheckAPI` |
| Trajectories | `service/Trajectories` | `APILoader` per type, plus hand-rolled type lookups that log errors | **None** on 24 RPCs |
| MechJeb | `service/MechJeb` | `Reflection.cs`: own missing list and a `Value<T>` stub that throws on use | `CheckAPI` on `Loaded` |
| Kerbal Engineer Redux | `service/KerbalEngineerRedux` | Own `missing` list and helpers | `CheckAPI` |
| SCANsat | `service/ScanSat` | Own `missing` list and helpers, a copy of KER's | `CheckAPI` |
| Raster Prop Monitor | `service/RasterPropMonitor` | Own `missing` list and helpers, a third copy | `CheckAPI` |
| FAR, RealFuels, AGExt, RealAntennas | `SpaceCenter/src/ExternalAPI` | One loader each | `IsAvailable` branches, with stock fallbacks |
| RemoteTech (again) | `SpaceCenter/src/ExternalAPI/RemoteTech.cs` | A copy of `service/RemoteTech/src/API.cs` | `IsAvailable` branches |
| Part mods: RealChute, DMagic, Procedural Fairings, Firespitter, KerbalActuators, B9PartSwitch, Near Future Solar, TweakScale | SpaceCenter, by module name | String-named modules | None needed |

The part mods need no binding code and are out of scope, except for the
[tested versions](#phase-6-tested-mod-versions-in-the-docs).

## Problems

### Build and registration

Each service's `BUILD.bazel` is about 97 lines. Diffed against KER's with the service name
replaced, they differ in two to four lines. A new service also edits 19 files outside its own
directory and docs pages, as Raster Prop Monitor did. After [phase 1](#phase-1-one-registry-in-service-and-a-build-macro),
the registry generates each list or a test checks it:

| File | Entries per service | After phase 1 |
| --- | --- | --- |
| `BUILD.bazel` | 5: the zip, the zip paths (3 lines), `csproj-srcs`, the test suite, the docs inputs | Generated |
| `doc/BUILD.bazel` | 2: changelog, service definitions | Generated |
| `tools/krpctools/services.bzl` | 1, the existing `SERVICES` registry | Moves into the registry |
| `tools/release/changelog.py` | 1, the component name | Checked |
| `tools/release/publish-docs.py` | 1, the sources to restore | Generated |
| `tools/krpctools/krpctools/clientgen/python.py` | 1, the Python module name | Checked already, against the modules the client ships |
| `CHANGELOG.md` | 1, the link to the service's changelog | Checked |
| `client/csharp/src/KRPC.Client.csproj`, `KRPC.sln` | 1 each | Checked. `KRPC.Client.csproj` is checked already |
| `doc/src/{cnano,cpp,csharp,java,lua,python}.rst` | 1 each, the API toctree | Generated |
| `doc/order.txt`, `doc/api/space-center.tmpl` | The member order, the Supported Mods list | The member order stays. The list is generated in phase 6 |
| `doc/src/krpc-development/building.rst` | The list of service targets | Replaced by the pattern |
| `tools/krpctools/krpctools/game/ksp/mods/__init__.py` | The mod pin | Moves into the registry |

### Two registries, neither in `service/`

* `SERVICES` in `tools/krpctools/services.bzl` holds the name, definitions, dependencies and game
  of each service. Only clientgen reads it.
* The mods live in `tools/krpctools/krpctools/game/ksp/mods/__init__.py`, one Python class each:
  the archive URL, hash, folders, dependencies and presence check. The in-game tests read them.
* Nothing links the two, and a mod has one version. A second version of KSPCommunityPartModules
  is a second class with its own name.
* The docs keep a third list, the Supported Mods section of
  `space-center.tmpl`, with each mod's GitHub link written by hand.

### Binding to the mod

Seven binding styles for one job. Each logs a missing member in its own words, and decides on its
own whether a missing member disables the service:

* KER, SCANsat, Raster Prop Monitor and MechJeb each carry a `missing` list and
  `Name`/`Getter`/`Method` helpers over `Accessor`, copied from one another.
* MechJeb's `Value<T>` is a stub that throws on use, the idea of `MemberBinder` built a second time.
* `APILoader` binds delegate properties, and shows a popup of its own.
* IR and KAC vendor the mods' own wrappers, with their own version checks and lazy binding.
* `RemoteTech.API` exists twice, in SpaceCenter and in the RemoteTech service.
* Trajectories logs four errors when the mod is absent.

Each service also has an `Addon.cs`, a 19-line `LoadOnceAddon` that calls `API.Load`. The
minimum mod versions are spread over `APILoader` calls, `KACWrapper` and comments.

### The availability check

Every RPC of a service calls `CheckAPI ()` first. The helper is written once per service, with
two wordings: "X is not available", and IR's "Infernal Robotics is not installed." Class members
have no check, and rely on their instance coming from a checked RPC. Trajectories has no check at
all, so a call without the mod throws `NullReferenceException`.

The services also report their mods unevenly. MechJeb has `APIReady`, which works in flight only
and also needs a MechJeb part on the active vessel. SpaceCenter reports FAR, RealFuels and
RealAntennas, and none of the part mods it supports. So the tests tell each mod loaded with checks
of their own: a part, a part module or an assembly version.

### Duplicated API

`ImageFormat`, an enum with `PNG` and `JPEG`, and its encoder are copied into DockingCamera
(#1317), SCANsat (#1328) and Raster Prop Monitor. All three are unreleased, so 0.8 is the last
release where merging them is not a breaking change.

### In-game tests

The tests run through `krpctools.game.ksp.TestCase`, but each test class repeats the same setup:

* `setUpClass` creates a save, launches a craft, removes other vessels, connects, then reads the
  active vessel, in some classes with `assert vessel is not None`. The block is in about 100 test
  classes, mod services and SpaceCenter alike.
* Eight services write their own `test_available`, as do the RealFuels and RealAntennas tests.
  Each repeats the presence check the test framework runs before the class starts. Infernal
  Robotics combines it with `ready`, in `test_available_and_ready`.
* DockingCamera, SCANsat, Raster Prop Monitor and Drawing each write the PNG signature. SCANsat
  and Raster Prop Monitor each define `png_size`.
* Nothing checks that a mod bound in full at its pinned version. A mod update that removes a member
  passes the tests that do not reach it.

### Tested mod versions

Each mod is pinned in krpctools, but the version exists only inside the download URL.
The docs do not name it. A player cannot tell which version of SCANsat or MechJeb kRPC was tested
with. The minimum versions in the C# code are a second, unrelated set.

## Phases

Each phase is one part, except phase 1, which is four, and phase 2, which is two. A part is a
unit of review, with its own branch in the stack. Parts can merge alone or together. Phases 1 to 3
change no RPC, except for the availability properties part 1d adds. Phases 1 and 3 are
independent of each other.

Each part checks CI against the targets it adds and removes. CI names its targets by hand in
`.github/workflows/ci.yml`, so a new test or build target needs a job that runs it, and a removed
one leaves no job naming it. A generated file the projects build from also needs to be in the
archive `tools/release/genfiles.py` collects, which CI builds `KRPC.sln` from.

| Phase | Kind | Depends on | Removes |
| --- | --- | --- | --- |
| 1. One registry in `service/`, a build macro, and availability properties (1a to 1d) | Refactor | - | `services.bzl`, the mod classes in krpctools, 90 lines per `BUILD.bazel`, the hand-kept service lists, the tests' own mod checks |
| 2. Test helpers (2a, 2b) | Refactor | 1d | Repeated setup, image signatures, availability tests |
| 3. One binding layer | Refactor, quieter logs | - | Four binding helper sets, the RemoteTech copy, the `ImageFormat` copies |
| 4. `ModAPI`, loaded at startup | Behavior | 3 | `Addon.cs`, `APILoader`, scattered version checks |
| 5. `RequiresMod` | Behavior | 4 | Every `CheckAPI` |
| 6. Tested mod versions in the docs | Docs | 1d | Versions only in URLs, hand-written mod links |
| 7. No stubs at the pinned version | Test | 4 | Silent breakage on a pin bump |

Scanner partial loading and the popup ([#1227](https://github.com/krpc/krpc/issues/1227)) are not
mod-specific, and follow this work. They report the mod failures phase 4 records.

### Phase 1: one registry in `service/`, a build macro, and availability properties

`service/registry.bzl` is the one source of truth for the KSP services and the mods they wrap or
support. Every list in the repo is generated from it where it can be, and checked against it where
it must stay hand-written. Each mod then reports whether it is installed, through a property a
client and the tests both read. The phase is four parts:

| Part | Change | Risk | State |
| --- | --- | --- | --- |
| 1a | The `ksp_service` macro. Every service under `service/` uses it. No registry yet | Low. `//:krpc` lists the same files before and after | Implemented as designed, not yet merged. The service targets and the mod zip are unchanged |
| 1b | `SERVICES` moves into the registry and drives the build, the docs, clientgen and the release tools. Service ids are generated | Medium: touches clientgen and every service's C# | Implemented, not yet merged. The mod zip and the generated client code are unchanged |
| 1c | `MODS` moves into the registry. krpctools reads `registry.json` | Medium: a comparison shows the old and new mods match before the Python classes go | Implemented, not yet merged. Every mod installs and checks as before |
| 1d | `Available` for every mod, on its service or on SpaceCenter. krpctools checks each mod through it and the installed assembly, and the presence checks leave the registry | Medium: new RPCs on SpaceCenter, and a changed check for every mod | Implemented, not yet merged |

The registry is internal, so it can change shape later. KSA is not in it. A registry spanning both
games is 1.0 work, and its shape should not assume one game where that costs nothing now.

#### 1a: the `ksp_service` macro

Every service under `service/`, SpaceCenter, Drawing, UI and Debug included, has the same
`BUILD.bazel`:

```python
ksp_service(
    name = "RasterPropMonitor",
    description = "Raster Prop Monitor API for kRPC",
    deps = ["SpaceCenter"],
    data = ["RasterPropMonitorDisplay.cfg"],
)
```

* The macro emits the `AssemblyInfo`, the library, the service definitions, the filegroup, the
  lint tests and `csproj-srcs`.
* Its arguments cover the variations of today's files: `copyright` (MechJeb credits Genhis),
  `license` (IR, SpaceCenter and Debug ship a `LICENSE`, renamed `LICENSE.KRPC.<name>` in the
  zip), `data` (Raster Prop Monitor's display patch, SpaceCenter's Module Manager config),
  `internals_visible_to` (SpaceCenter, for TestingTools) and the lint test sizes.
* `deps` names services. The macro maps them to the libraries and to the assemblies the service
  definitions load.
* 1b moves the description and dependencies into the registry, and the call shrinks to the name
  and the build-only options, such as `data`.
* LIDAR keeps its own `BUILD.bazel`. See [Decisions](#decisions).

#### 1b: `SERVICES` in the registry

```python
SERVICES = [
    service(
        name = "ScanSat",
        id = 16,
        title = "SCANsat",
        description = "SCANsat API for kRPC",
        doc = "scansat",
        deps = ["SpaceCenter"],
    ),
    service(
        name = "LIDAR",
        id = 10,
        ...,
        package = "LiDAR",
    ),
    ...
]
```

* **Every service under `service/`** has an entry, in the order the clients, the docs and the
  changelog list them. The core services (`KRPC`, `StdLib`) and the test services stay in
  `tools/krpctools/services.bzl`, which adds them to the registry's list for clientgen. Core does
  not depend on `service/`.
* **The fields.** `title` is the name in the changelog. `doc` names the API page,
  `doc/api/<doc>.tmpl`. `package` is the directory, where it differs from the name, as for LIDAR.
  The Python module is not a field: it is `krpc.<game>.<name in lower case>`, as the client's
  build already derives it.
* **One `deps` list** names the services whose assemblies or types a service uses. The build maps
  each to its assembly, and leaves out the core's, which every service has. Clientgen takes the
  list as is. Today's two lists differ only by a core service or by a dependency the other side
  ignores, such as UI's on SpaceCenter, so the generated code is unchanged.
* **Service ids are generated.** The macro writes a `ServiceInfo.cs` per service, and the source
  reads it: `[KRPCService (Id = ServiceInfo.Id)]`. The `.csproj` compiles it from
  `$(bazel-bin)`, as it compiles `AssemblyInfo.cs` today. `bazel build //:csproj` stages it, and
  `genfiles.py` ships it in the generated sources archive, so the projects build outside Bazel.
* **`registry.json`.** `//service:registry` writes the registry out as JSON, which the Python
  tools read.
* **Generated from the registry:** the root `BUILD.bazel` lists (zip, zip paths, `csproj-srcs`,
  test suite, `//:csproj`), `doc/BUILD.bazel`, clientgen's targets, and the API toctrees of the
  six client guides, through a generated include, `<language>/api.inc`. `building.rst` names the
  pattern `//service/<name>` in place of a list.
* **`publish-docs.py`** builds `//service:registry.json` in its worktree, and restores the
  sources of each service that the content ref has. A service added since keeps the toolchain's
  sources, and the ref's docs do not include its pages.
* **Checked against the registry** by `//service:registry-test`, as they must stay hand-written:
  each service's `.csproj` (the `ServiceInfo.cs` item, and a project reference per dependency),
  the `KRPCService` attribute's id, `KRPC.sln`, the root `CHANGELOG.md` index, and the services
  in `COMPONENTS` in `changelog.py`, by title and order. The changelog-hints workflow imports
  `changelog.py` with no Bazel build, so `COMPONENTS` stays a literal. `KRPC.Client.csproj` and
  clientgen's Python module map are checked already, by their own tests.

#### 1c: `MODS` in the registry

Each mod is one entry, keyed by a common name, with a sub-entry per version kRPC tests:

```python
MODS = [
    mod(
        name = "SCANsat",
        repo = "KSPModStewards/SCANsat",
        assembly = "SCANsat",
        present = service_property("scan_sat"),
        versions = [
            version(
                "22.1",
                source = "releases/download/v{version}/SCANsat-{version}.zip",
                sha256 = "34cabb87...",
                folders = ["SCANsat"],
                requires = ["KSPTextureLoader"],
            ),
        ],
    ),
    mod(
        name = "KSPCommunityPartModules",
        repo = "KSPModdingLibs/KSPCommunityPartModules",
        assembly = "KSPCommunityPartModules",
        present = assembly_version(),
        versions = [
            version("0.5.1", assembly_version = "0.5", ...),
            # Predates ModuleNameTag, to test that kRPC still loads with it
            version("0.4.0", assembly_version = "0.4", ...),
        ],
    ),
    mod(
        name = "ModularFlightIntegrator",
        versions = [version("0.16.1.2", archive = "FAR", folders = ["ModularFlightIntegrator"])],
    ),
]
```

* **The key is the mod's name.** GameData folders and files are install data of a version, read
  by the installer. They are never a key.
* **Versions, as in pip.** A test asks for `"KSPCommunityPartModules"` and gets the first version
  listed, the latest. `"KSPCommunityPartModules==0.4.0"` gets that one. The same form works in
  `requires`.
* **`assembly`** names the mod's main assembly, for each mod a service wraps or supports. The
  assembly version check reads it. In 1d, the build generates it into the C#, and each version
  gains the SHA-256 of its `<assembly>.dll`.
* **`version`** is the release, used in the URL and shown in the docs. **`assembly_version`** is
  what an assembly presence check compares against. These are separate fields: TweakScale
  Rescaled is release 3.3.2.1 and assembly 3.3.
* **A shared archive.** `archive = "FAR"` takes the archive of FAR's version of the same number.
  ModularFlightIntegrator has no release of its own.
* **Presence checks are data, until 1d.** Each check is one of the four kinds the Python classes
  used, each a constructor: a service property (`service_property("scan_sat")` for `available`,
  `service_property("space_center", "far_available")`), a part, a part module and an assembly
  version. A mod with no check, such as a dependency or Trajectories, counts as loaded when a test
  requires it. 1d replaces them with the availability properties.
* **Config overlays** move to `mods/<mod name>/<folder>/` in krpctools, keyed by the mod.
* **Each service names the mods it wraps**, in a `mods` field of its `SERVICES` entry, such as
  `mods = ["SCANsat"]`. A service that wraps no mod, SpaceCenter among them, has `mods = []`.
  LIDAR's mod is an entry with no versions, as it has no pin, so the tests cannot install it. 1d
  adds `supports`, for the mods SpaceCenter supports. `//service:registry-test` resolves each name, and each mod's
  `requires` and `archive`.
* **krpctools** ships `registry.json` in its wheel, as it ships the service definitions. It builds
  a `Mod` for each version from the file, and keeps only the behavior: install, remove and the
  presence checks. It keys each version by `name==version`, and rejects a request for two
  versions of one mod.

**Check:** before the Python mod classes went, a script built the mods both ways and compared
every field: URL, hash, folders, files, dependencies, presence check and overlays.

#### 1d: `Available` for every mod

Every mod a service wraps or supports reports whether it is installed:

```python
>>> conn.scan_sat.available
True
>>> conn.space_center.real_chute_available
True
```

| Service | Property |
| --- | --- |
| Each mod service | `Available`, whether its mod is installed and works |
| SpaceCenter | `<Mod>Available` for each mod it supports, such as `FARAvailable` and `RealChuteAvailable` |

* **`Available` is about the mod, not the vessel.** It works in every game scene, MechJeb's
  included. MechJeb also has `Ready`: whether the active vessel has a MechJeb core. MechJeb's
  `APIReady` is renamed `Ready`, as the service is unreleased. Infernal Robotics' `Ready` goes in
  [phase 4](mod-api.md#infernal-robotics-without-ready).
* **No version property.** A mod's version as players know it is its release, the number GitHub,
  CKAN and SpaceDock list. Nothing in an install carries it for every mod. The assembly's
  attributes often stay at an old number: Near Future Solar 1.3.3 has file version 0.4.0.0, and
  Firespitter 7.17 has only an assembly version, 7.3.7660.26532. The KSP-AVC `.version` file is
  closest, but MechJeb, DMagic and KSPCommunityPartModules ship none, and TweakScale Rescaled
  3.3.2.1 says 3.3.2.0. CKAN records its installs outside GameData, and only for the installs it
  manages. A version property would misreport some mods, so there is none.
* **SpaceCenter's `<Mod>Available`** is the existing binding's state for the mods it binds to
  (FAR, Action Groups Extended, RealFuels and RealAntennas), and whether the game loaded the mod's
  assembly for the part mods, through a server helper, `ModAssembly`.
* **The names come from the registry.** `<Mod>` is the mod's name in `MODS`, with its first letter
  upper case, as in `KOSAvailable`. Each mod's name and `assembly` are generated into the
  service's `ServiceInfo.cs`, as its id is, as `ServiceInfo.Mods.SCANsat.Assembly`.
* **SpaceCenter lists the mods it supports**, in a `supports` field of its `SERVICES` entry. A mod
  in no service's `mods` or `supports` is a dependency, such as Harmony, and has no property.
* **krpctools checks every mod the same way.** It reads each mod's `Available` once. For a loaded
  mod, the SHA-256 of the installed `<assembly>.dll` tells the version: the registry records it
  per version as `assembly_sha256`, and krpctools reads GameData directly, as it installed the
  files. The required version is tried first, and the others only when it does not match. A DLL
  matching no version counts as "<name> (another version)", which fails the check with that name.
  A local build given with `--mod` is hashed from its own files. The presence-check constructors
  leave the registry.
* **The hash is checked at install.** Installing a pinned version fails when its
  `<assembly>.dll` does not have the registry's `assembly_sha256`, so a pin bump cannot leave a
  stale hash.
* **The version check covers every mod.** A game left running with a stale install, which
  `--no-launch` reuses, fails before a test runs against the wrong version.
* **Phase 4** reads `Available` from each integration's `ModAPI`, in one line.

### Phase 2: test helpers

Every in-game test sets up the same way, through the same helpers. The phase is two parts with
one form, so the tests read alike at the end:

| Part | Covers | State |
| --- | --- | --- |
| 2a | The helpers, and every test file with a class that requires a mod: the mod services, and SpaceCenter's tests of FAR, RealFuels, the part mods and the rest | Implemented, not yet merged |
| 2b | The other in-game tests, and the benchmarks | Implemented, not yet merged |

Both parts ran in game on 2026-11-12: one test per changed class, every test of the files whose test bodies changed, and an autopilot subset. 296 tests passed.

A part takes whole files, as a mod test class often extends a stock one in the same file.

The helpers, in krpctools:

| Helper | Replaces |
| --- | --- |
| `TestCase.launch(craft, directory, editor, crew, save, always_load)`: new save, launch, remove other vessels, return the active vessel. Its options are what the setups vary by: the craft directory, the editor, the crew, the save and whether it always reloads. The orbit stays a separate call, as its arguments vary | The setup block and its `assert vessel is not None` |
| `krpctools.game.images`: `assert_png` and `assert_jpeg`, each with an optional size, `png_size`, `jpeg_size`, and `png`, which writes an image of one color or of a function of the pixel | The copies in the DockingCamera, SCANsat, Raster Prop Monitor and Drawing tests |

* **No availability tests.** Before a test class starts, `ensure()` checks each mod it requires
  through its `Available` and its installed assembly ([1d](#1d-available-for-every-mod)), and
  fails the class when a mod is not loaded at the requested version. So the `test_available` methods go. The
  `ready` of Infernal Robotics and MechJeb stays, as a test of its own, and Infernal Robotics'
  `test_available_and_ready` becomes `test_ready`.
* **Crewed by default.** The craft takes its default crew, as from the VAB, and its crew become
  pilots for full control. `crew` names the Kerbals in place of the default, and an empty list
  launches with none. `krpc-game run --load-craft` launched with an empty list, and 2a changes it
  to the default crew too ([testing-tools-load-craft-crew.md](../../../issues/testing-tools-load-craft-crew.md)).
* **The current save.** `save=None` launches without loading a save: a launch per test, after
  leaving the editor, or after creating the Kerbals of a named crew, which a new save would drop.
* **The existing methods stay.** `launch` calls `new_save`, `_stage_craft`, `launch_vessel` and
  `remove_other_vessels`. Other mods' tests call them, as do the classes that create a save
  without launching a craft, or launch a second vessel beside the first.
* **Tests of a launch RPC call it.** The crew test and the IVA-after-launch camera test call
  `launch_vessel` directly. `launch` runs further RPCs after the launch, which give the game time
  to seat the crew.
* **One launch, unconditionally.** Some setups launched only when the active vessel had another
  name. `new_save` loads a new save unless the active vessel is the save's own pod, so the
  condition always held, and these become one `launch` call.
* **`launch` is the base method's name.** The camera and crew tests' helpers of that name go.
  The autopilot's started the engines, and becomes `lift_off`.
* **krpctools stays generic.** It is a published package for the tests of other mods, so it knows
  nothing of kRPC's repository layout. A test that launches another service's craft passes its
  directory, as the KER and MechJeb tests do.
* **Docs and changelog.** 2a shows `launch` in `doc/src/extending/testing.rst` and its example
  script. `krpctools.game` is unreleased, so the changelog entry that adds it covers the helpers,
  and the parts add none.
* **Testing.** Each part runs the in-game tests it changes, one game per mod set.

### Phase 3: one binding layer

Every integration binds through `MemberBinder`, and a missing member binds a stub that fails only
the calls that use it. The RemoteTech copy goes, and Trajectories logs nothing when its mod is
absent. Design: [binding.md](binding.md).

The phase also merges the `ImageFormat` copies:

* One `ImageFormat` enum, in StdLib beside `ColorRGB` and `ColorRGBA`, and one encoder in the KSP
  server's `Utils`. DockingCamera, SCANsat and Raster Prop Monitor take it, and add `StdLib` to
  their `deps` in `SERVICES`. See [Decisions](#decisions).
* The enum is game-agnostic, and the encoder is not: it takes a Unity `Texture2D`. A KSA service
  with images uses the same enum, once KSA builds against a 0.8 core, with an encoder of its own.
* It is StdLib's first enumeration. Every client generates and builds it as any service's enum,
  and the docs list it with StdLib's structs.

Implemented on branch `mod-binding`, not yet merged. Checked in game on 2026-11-12: every integration's tests at its pinned version, 337 passed, with no stub warning in the logs. The negative control, one misspelled member in each of the 13 integrations, failed only the tests that use those members, each with the stub's message, and logged one warning per member.

### Phase 4: `ModAPI`, loaded at startup

One `ModAPI` class per integration, bound when kRPC loads. A failed mod disables only its own
integration, and is recorded for reporting. `Addon.cs`, `APILoader`, the minimum versions and the
vendored KAC and IR wrappers go, and so does Infernal Robotics' `Ready`. Design:
[mod-api.md](mod-api.md).

Implemented on branch `mod-api`, not yet merged. Checked in game on 2026-11-12: every integration's tests at its pinned version, 335 passed, with each mod loaded at startup and no stub warning in the logs.

### Phase 5: `RequiresMod`

```csharp
[KRPCService (Id = 16)]
[RequiresMod (typeof (API))]
public static class ScanSat
```

The server checks the mod before each call, class members and server side functions included.
Every `CheckAPI` goes, and Trajectories gains the check it lacks. Design:
[requires-mod.md](requires-mod.md).

Implemented on branch `requires-mod`, not yet merged. Checked in game on 2026-11-13: 367 passed.

### Phase 6: tested mod versions in the docs

* The docs build reads `registry.json`. Each mod service's page names its mod with a link to its
  repo and "Tested with SCANsat 22.1".
* A mod with several versions lists each: "Tested with KSPCommunityPartModules 0.5.1 and 0.4.0".
* The Supported Mods list in `space-center.tmpl` takes its mods from SpaceCenter's `supports`, with
  each mod's link and tested versions. Its prose about what each mod adds stays in the template.

Bumping a pin in the registry updates the tests and the docs in the same commit.

Implemented on branch `tested-mod-versions`, not yet merged. Where it diverged:

* docgen is unchanged. `doc/mods.bzl` writes rst include files from the registry in Starlark: a
  link target and a `|<title> tested|` substitution per mod, and two tables for SpaceCenter.
* Each mod has a `title`, its name in the docs, such as "Ferram Aerospace Research" for FAR.
* The Supported Mods list keeps its prose bullets. A generated table after it gives each supported
  mod's tested versions, and a second one each mod service's. A mod with no pinned version (LiDAR)
  gets a link and no table row.

### Phase 7: no stubs at the pinned version

After the presence checks, `ensure()` checks that each required mod's `ModAPI` bound with no stub
and no failure, through a `TestingTools` procedure that reads `ServiceProblems.Mods`. Every test
class that requires a mod gets the check with no code. A pin bump that removes a member then fails
in CI, before a player sees it.

Implemented on branch `no-stubs-check`, not yet merged. The procedure is
`TestingTools.ModProblems`, a map from mod name to the problem. A required mod is matched to its
integration by name. A failed check leaves the game running, and each later class with the same
mods checks again. Checked in game on 2026-11-13: SCANsat and KAC, 36 passed. A misspelled SCANsat
member failed each SCANsat class in `ensure()` with the member named, after one launch.

## Adding a mod service, after the phases

| Step | Today | After |
| --- | --- | --- |
| `BUILD.bazel` | Copy 97 lines | `ksp_service (name = ...)` |
| Registration | 19 other files | A `SERVICES` and a `MODS` entry in `service/registry.bzl`, plus the hand-written files the checks name: the `.csproj`, `KRPC.sln`, `KRPC.Client.csproj`, the `CHANGELOG.md` index, `COMPONENTS` in `changelog.py` and clientgen's Python module map. Then the docs pages |
| Binding | Write a loader and helpers, or copy one | One `ModAPI` |
| Availability | A `CheckAPI` per RPC | `[RequiresMod]` on the service |
| Tests | Copy the setup and `test_available` | `launch`. The test framework checks `Available`, the installed assembly and the binding in place of `test_available` |
| Service id | A literal in the C# attribute | The registry's `id`, generated into `ServiceInfo.cs` |
| Tested version | Not recorded | The mod's versions in the registry, shown in the docs |

The KSA server builds against the released `KRPC.Core`
([ksa/README.md](../../ksa/README.md)). It gets `MemberBinder`, `ModAPI` and `RequiresMod` once it
moves to a 0.8 core, ahead of its first mod integration
([ksa/kitten-engineer-redux.md](../../ksa/kitten-engineer-redux.md)).

## Decisions

| Question | Proposal |
| --- | --- |
| One `ImageFormat` for every service, or one per service | One, in StdLib, the game-agnostic home of `ColorRGB` and `ColorRGBA`, so KSA services can use it too. It must land before 0.8 ships, as the copies are unreleased |
| `ModAPI` and `RequiresMod` public in core | Yes: a third-party service author uses them as kRPC's own services do. The extending docs gain a page in phase 5 |
| The registry's format | Starlark, written out as JSON. Bazel cannot read JSON or TOML in a `BUILD` file without a module extension, and Starlark keeps comments on the pins. Python reads the JSON |
| Minimum mod versions | None. Each binding names the members it needs, and a missing one fails only the RPCs that use it. A version cut-off would disable a mod that mostly works. The registry holds the tested versions, and the docs show them |
| Generate or check the lists | Generate from the registry wherever the consumer can read it: Bazel, the docs build, the Python tools run after a build. Check the files read with no build: the `.csproj` files and `KRPC.sln`, the root `CHANGELOG.md`, which GitHub renders, `COMPONENTS` in `changelog.py`, which the changelog-hints workflow imports, and clientgen's Python module map, which ships in the krpctools wheel |
| Service ids | Generated into a `ServiceInfo.cs` per service, compiled from `$(bazel-bin)` as `AssemblyInfo.cs` is, and shipped in the generated sources archive |
| LIDAR | Keep its `BUILD.bazel`, with a registry entry so the generated lists include it. Its binding becomes a `ModAPI` in phase 4, so `APILoader` can go. It was deprecated in 0.8 (#1263), so the deprecation policy removes it in 1.0. The alternative is to drop it in 0.8 as a hard break, with no release in which it is deprecated first |
| How the tests tell a mod loaded | Through the `Available` property clients read too, and the version by the SHA-256 of the installed assembly, which the registry records per version. The registry holds no presence checks |
| A mod version property | None. No source in an install gives every mod's release version, and a property that misreports some mods is worse than none |
| When a stock fallback runs | Only when the mod is not installed. A player with FAR installed gets FAR's values or an error, as a stock value in their place is wrong without notice. A missing member or a failed load makes the RPC throw |
| A registry for both games | Not in 0.8. The registry is internal, and a 1.0 refactor can add KSA |
