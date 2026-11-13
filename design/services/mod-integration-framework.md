# Mod integration framework

**Status:** proposal (2026-11-12), for 0.8. Issue:
[mod-integration-framework.md](../../issues/mod-integration-framework.md).

The entry point for the shared machinery behind kRPC's mod integrations: the build, the binding to
the mod, the availability check, the in-game tests and the tested mod versions. It summarizes the
older detailed docs, records where they have gone stale, and orders the work into phases.
Refactoring comes before new behavior.

The doc assumes the Raster Prop Monitor service is on main, as the fourteenth integration.

| Detailed doc | Covers | State |
| --- | --- | --- |
| [server/partial-loading.md](../server/partial-loading.md), "Mod integrations" | `ModAPI`, `ModBinder`, `MemberBinder`, stubs, load at startup, a failed mod disables only its integration | Designed. Names 7 of the 14 integrations. Best-effort binding built for 4 of them, on an unpushed branch 283 commits behind main |
| [server/problem-reporting.md](../server/problem-reporting.md) | The popup and log for failed mods and scanner errors | Designed |
| [issues/requires-mod-attribute.md](../../issues/requires-mod-attribute.md) | `[RequiresMod]` in place of `CheckAPI` | Not started |
| [issues/trajectories-load-errors.md](../../issues/trajectories-load-errors.md) | Four errors in the log without Trajectories | Not started. Fixed by [phase 3](#phase-3-one-binding-layer) |
| [services/mod-compat-test-coverage.md](mod-compat-test-coverage.md) | In-game tests per integration | Done (#1319) |
| `KRPC.Utils.Accessor` (PR #1251, no design doc) | Compiled delegates for reflected members | Merged |
| [services/service-versioning.md](service-versioning.md) | Per-service API versions | Negative result. Unrelated to the mod versions in [phase 6](#phase-6-tested-mod-versions-in-the-docs) |

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
directory and docs pages, as Raster Prop Monitor did:

| File | Entries per service |
| --- | --- |
| `BUILD.bazel` | 5: the zip, the zip paths (3 lines), `csproj-srcs`, the test suite, the docs inputs |
| `doc/BUILD.bazel` | 2: changelog, service definitions |
| `tools/krpctools/services.bzl` | 1, the existing `SERVICES` registry |
| `tools/release/changelog.py`, `tools/release/publish-docs.py` | 1 each |
| `tools/krpctools/krpctools/clientgen/python.py` | 1, the Python module name |
| `CHANGELOG.md` | 1, the link to the service's changelog |
| `client/csharp/src/KRPC.Client.csproj`, `KRPC.sln` | 1 each |
| `doc/src/{cnano,cpp,csharp,java,lua,python}.rst` | 1 each, the API toctree |
| `doc/order.txt`, `doc/api/space-center.tmpl` | The member order, the Supported Mods list |
| `doc/src/krpc-development/building.rst` | The list of service targets |
| `tools/krpctools/krpctools/game/ksp/mods/__init__.py` | The mod pin |

### Two registries, neither in `service/`

* `SERVICES` in `tools/krpctools/services.bzl` holds the name, definitions, dependencies and game
  of each service. Only clientgen reads it.
* The mods live in `tools/krpctools/krpctools/game/ksp/mods/__init__.py`, one Python class each:
  the archive URL, hash, folders, dependencies and presence check. The in-game tests read them.
* Nothing links the two. The docs keep a third list, the Supported Mods section of
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

### Duplicated API

`ImageFormat`, an enum with `PNG` and `JPEG`, and its encoder are copied into DockingCamera
(#1317), SCANsat (#1328) and Raster Prop Monitor. All three are unreleased, so 0.8 is the last
release where merging them is not a breaking change.

### In-game tests

The tests run through `krpctools.game.ksp.TestCase`, but each mod service repeats the same setup:

* `setUpClass` creates a save, launches a craft, removes other vessels, connects, then reads the
  active vessel with `assert vessel is not None`. That assert appears 15 times.
* KER and MechJeb build a path to `service/SpaceCenter/test/craft` by hand.
* Seven services write their own `test_available`.
* DockingCamera, SCANsat, Raster Prop Monitor and Drawing each write the PNG signature. SCANsat
  and Raster Prop Monitor each define `png_size`.
* Nothing checks that a mod bound in full at its pinned version. A mod update that removes a member
  passes the tests that do not reach it.

### Tested mod versions

Each mod is pinned in krpctools, but the version exists only inside the download URL.
The docs do not name it. A player cannot tell which version of SCANsat or MechJeb kRPC was tested
with. The minimum versions in the C# code are a second, unrelated set.

## Phases

Each phase is one PR, mergeable on its own. Phases 1 to 3 change no RPC. Phases 1 and 2 are
independent of each other and of the rest.

| Phase | Kind | Depends on | Removes |
| --- | --- | --- | --- |
| 1. One registry in `service/`, and a build macro | Refactor | - | `services.bzl`, the mod data in krpctools, 90 lines per `BUILD.bazel`, most per-service edits |
| 2. Test helpers in krpctools | Refactor | - | Repeated setup, signatures, `test_available` |
| 3. One binding layer | Refactor, quieter logs | - | Four binding helper sets, the RemoteTech copy, the `ImageFormat` copies |
| 4. `ModAPI`, loaded at startup | Behavior | 3 | `Addon.cs`, `APILoader`, scattered version checks |
| 5. `RequiresMod` | Behavior | 4 | Every `CheckAPI` |
| 6. Tested mod versions in the docs | Docs | 1 | Versions only in URLs, hand-written mod links |
| 7. No stubs at the pinned version | Test | 4 | Silent breakage on a pin bump |

Scanner partial loading and the popup ([#1227](https://github.com/krpc/krpc/issues/1227)) are not
mod-specific, and follow this work.

### Phase 1: one registry in `service/`, and a build macro

`service/registry.bzl` is the one source of truth for the services and the mods they wrap or
support. Every other list is read from it, or checked against it:

```python
MODS = [
    mod(
        name = "SCANsat",
        title = "SCANsat",
        repo = "KSPModStewards/SCANsat",
        version = "22.1",
        source = "releases/download/v{version}/SCANsat-{version}.zip",
        sha256 = "34cabb87...",
        folders = ["SCANsat"],
        requires = ["KSPTextureLoader"],
        present = service_available("scan_sat"),
    ),
    ...
]

SERVICES = [
    ksp_service_entry(name = "ScanSat", mods = ["SCANsat"], deps = ["SpaceCenter"], id = 16),
    ...
]
```

* **`MODS`** holds every mod the in-game tests install: the wrapped mods, the SpaceCenter mods
  and their dependencies. Each has its GitHub repo, the pinned version, the archive and how the
  tests find it in the game.
* **Presence checks are data.** Every check today is one of four kinds: a service property, such
  as `scan_sat.available` or `space_center.far_available`, a part, a part module and an assembly
  version. Each kind is a constructor in the registry.
* **`SERVICES`** moves from `tools/krpctools/services.bzl` and gains the package, the changelog
  title, the Python module and the mods a service wraps. The conformance-only services stay with
  the testees.
* **Starlark, written out as JSON.** Bazel loads the `.bzl` directly. A rule writes
  `registry.json`, which the krpctools wheel ships as package data. krpctools builds its `Mod`
  objects from it, and keeps only the behavior: install, remove and the four presence checks.
* **Config overlays** stay in krpctools, as files under `mods/<folder>/`. They are test fixtures,
  keyed by the mod's name.

A `ksp_service` macro in `service/build.bzl` declares every target a mod service has today:

```python
ksp_service(
    name = "RasterPropMonitor",
    description = "Raster Prop Monitor API for kRPC",
    deps = ["//service/SpaceCenter:KRPC.SpaceCenter"],
    data = ["RasterPropMonitorDisplay.cfg"],
)
```

* It emits the `AssemblyInfo`, the library, the service definitions, the filegroup, the lint tests
  and `csproj-srcs`. `data` adds files to the mod zip, such as Raster Prop Monitor's display patch
  or IR's `LICENSE`.
* `BUILD.bazel`, `doc/BUILD.bazel` and clientgen build their lists from `SERVICES`.
* `changelog.py`, `publish-docs.py`, clientgen's Python module map and the client guide toctrees
  stay as they are. A test checks each against `registry.json`.
* SpaceCenter, Drawing and UI keep their own `BUILD.bazel`. The macro covers the mod services.

**Check:** `//:krpc` lists the same files before and after, and krpctools installs the same mods.

### Phase 2: test helpers in krpctools

Helpers in `krpctools.game.ksp`, used by every mod service's tests:

| Helper | Replaces |
| --- | --- |
| `launch(craft, service=None)`: new save, launch, remove other vessels, return the active vessel | The setup block and its `assert vessel is not None` |
| `craft_dir(service)` | The hand-built paths to another service's craft |
| `krpctools.game.images`: `assert_png`, `assert_jpeg`, `png_size`, `jpeg_size` | The copies in the DockingCamera, SCANsat, Raster Prop Monitor and Drawing tests |
| `ModServiceTestCase`, which tests the service's `available` property | Seven `test_available` methods |

`ModServiceTestCase` takes the service from the mod's registry entry, so a test class names its mod
once, in `mods`. Each service's in-game tests run once against the change.

### Phase 3: one binding layer

Rebase the best-effort binding branch onto main, and extend it to every integration:

* `MemberBinder` in core binds through `Accessor`. A missing member binds a stub that throws
  `MissingMemberException` naming the mod and member, and logs one warning at load.
* MechJeb, KER, SCANsat, Raster Prop Monitor, Trajectories, DockingCamera, RealAntennas and AGExt
  move to it. Their helper sets and `Value<T>` go. KAC, IR, FAR and RealFuels are on the branch
  already.
* The RemoteTech service uses SpaceCenter's binding, and its own copy goes.
* A mod that is not installed logs one info line, and nothing else. This fixes
  [trajectories-load-errors](../../issues/trajectories-load-errors.md).
* One `ImageFormat` enum, in StdLib beside `ColorRGB` and `ColorRGBA`, and one encoder in the KSP
  server's `Utils`. DockingCamera, SCANsat and Raster Prop Monitor take it, and add `StdLib` to
  their `deps` in `SERVICES`. See [Decisions](#decisions).
  * The enum is game-agnostic, and the encoder is not: it takes a Unity `Texture2D`. A KSA service
    with images uses the same enum, once KSA builds against a 0.8 core, with an encoder of its own.
  * It is StdLib's first enumeration. Each client's StdLib build generates only structs today, so
    the phase checks the generated StdLib code and docs in every client.

LIDAR is deprecated and keeps its code.

### Phase 4: `ModAPI`, loaded at startup

As [partial-loading.md](../server/partial-loading.md#the-integration-pattern) designs it: one
`ModAPI` subclass per integration, with its display name, assembly and minimum version.

* Core finds every `ModAPI`, checks the assembly and version, and runs each `Bind` in its own `try`
  when kRPC loads. A failure disables that integration only.
* The `Addon.cs` of each service and `APILoader` go. The minimum versions sit in one place per
  integration.
* KAC and IR replace their vendored wrappers with a `ModAPI`, binding at startup and reading their
  live object per scene. These two are the largest part of the phase.
* MechJeb's `Bind` reports an installed KRPC.MechJeb, as partial-loading.md designs.

The partial-loading.md table of integrations predates MechJeb, KER, SCANsat, Raster Prop Monitor,
Trajectories, DockingCamera and RealAntennas. Each is one more `ModAPI`. Raster Prop Monitor's
computers and monitors are part modules, found through the vessel, so it needs no per-scene binding.

### Phase 5: `RequiresMod`

As [requires-mod-attribute.md](../../issues/requires-mod-attribute.md) proposes, in its `ModAPI`
form from the start:

```csharp
[KRPCService (Id = 16)]
[RequiresMod (typeof (ScanSatAPI))]
public static class ScanSat
```

* The server checks the mod before each call, server side functions included, with one message:
  "SCANsat is not available: <reason>".
* Every `CheckAPI` goes. Trajectories gains the check it lacks, and class members gain one.
* SpaceCenter tags the members that need FAR or RealAntennas. Members with a stock fallback keep
  their branch.

### Phase 6: tested mod versions in the docs

* The docs build reads `registry.json`. Each mod service's page names its mod with a link to its
  repo and "Tested with SCANsat 22.1".
* The Supported Mods list in `space-center.tmpl` takes each mod's link and tested version from the
  registry. Its prose about what each mod adds stays in the template.
* The C# minimum versions stay separate. They state what loads, and the docs state what was tested.

Bumping a pin in the registry updates the tests and the docs in the same commit.

### Phase 7: no stubs at the pinned version

An in-game test per mod service checks that its `ModAPI` bound with no stub and no failure,
through a `TestingTools` procedure that reads `ServiceProblems.Mods`. It goes in
`ModServiceTestCase`, so each service gets it with no code. A pin bump that removes a member then
fails in CI, before a player sees it.

## Adding a mod service, after the phases

| Step | Today | After |
| --- | --- | --- |
| `BUILD.bazel` | Copy 97 lines | One `ksp_service` call |
| Registration | 19 other files | A `SERVICES` and a `MODS` entry in `service/registry.bzl`, the `.csproj` and `.sln`, the docs pages. The checks name each list it is missing from |
| Binding | Write a loader and helpers, or copy one | One `ModAPI` |
| Availability | A `CheckAPI` per RPC | `[RequiresMod]` on the service |
| Tests | Copy the setup | `ModServiceTestCase`, `launch` |
| Tested version | Not recorded | The mod's `version` in the registry, shown in the docs |

The KSA server builds against the released `KRPC.Core`
([ksa/README.md](../ksa/README.md)). It gets `MemberBinder`, `ModAPI` and `RequiresMod` once it
moves to a 0.8 core, ahead of its first mod integration
([ksa/kitten-engineer-redux.md](../ksa/kitten-engineer-redux.md)).

## Decisions

| Question | Proposal |
| --- | --- |
| One `ImageFormat` for every service, or one per service | One, in StdLib, the game-agnostic home of `ColorRGB` and `ColorRGBA`, so KSA services can use it too. It must land before 0.8 ships, as the copies are unreleased |
| `ModAPI` and `RequiresMod` public in core | Yes: a third-party service author uses them as kRPC's own services do. The extending docs gain a page in phase 5 |
| Keep the vendored IR and KAC wrappers | No, phase 4 replaces them. They bind lazily, and fail differently from every other integration |
| The registry's format | Starlark, written out as JSON. Bazel cannot read JSON or TOML in a `BUILD` file without a module extension, and Starlark keeps comments on the pins. Python reads the JSON |
| The C# minimum versions in the registry | No. They are part of each binding, beside the members it needs. The registry holds the tested version |
| Generate the Python lists and client toctrees from `SERVICES` | No, check them in a test. Generated Python files make the tools harder to read and run outside Bazel |
