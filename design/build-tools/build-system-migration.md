# Build system migration: custom `tools/build/` rules → upstream Bazel rulesets

**Status:** done — merged to `main` as [PR #948](https://github.com/krpc/krpc/pull/948) (plus
follow-on commits). All ten phases shipped, Windows enablement included. This doc is a historical
record of the design; the PR history and the code are the source of truth for what was built.
**Issue:** [krpc/krpc#694](https://github.com/krpc/krpc/issues/694)

The custom `tools/build/` rules were replaced with upstream Bazel rulesets. Mono is gone from the
build, the release and packaging paths, and the CI image; C# compiles on the hermetic dotnet SDK,
the `build-csharp-sln` job builds `KRPC.sln` with `dotnet build`, and the Windows protoc `select()`
now keys on the target OS. As-built details diverge from the phase notes below in places (e.g. the
buildenv landed as `3.9.x`, not the `3.10.0` some notes cite) — read them as design history.

### Follow-up hardening, after the ten phases

 * The KSP assemblies the mod builds against moved into a Bazel `@ksp` http_archive (auto-fetched
   from the ksp-lib repo), removing the manual `lib/ksp` setup, the `lib/` directory and the CI
   `ksp-lib` download. The integration tests now require `KSP_DIR` / `--ksp-dir` for the game install.
 * The last two mono users outside the build: the release script `tools/dist/nuget.sh` (now
   `dotnet nuget push`) and the TestServer docker image (now the .NET 8 runtime).
 * Compiler-warning suppressions; `static inline` C-nano codegen; a `Development-Guide.md` refresh;
   removal of the orphan `.black-format` file.

## Motivation

kRPC's entire build is driven by hand-rolled Starlark rules in `tools/build/` that shell out to
host-system tools:

 * C# is compiled with the system `mcs` (`-noconfig -nostdlib`, referencing checked-in mono 4.5
   DLLs from `lib/mono-4.5/`), and executables/tests run under a hard-coded `/usr/bin/mono`.
 * Python actions use the system `python3`, creating a venv per action and pip-installing from
   pre-downloaded sdists; `py_sdist` and `py_test` additionally pip-install hatchling/pytest **from
   the network at action time** (a PEP 668 workaround).
 * `nuget_package` disables the sandbox entirely (`execution_requirements = {"local": "1"}`)
   because `nuget.exe` under mono doesn't work inside it.
 * protoc, luarocks, lua5.1, zip, make, sed, awk, rsvg-convert, socat, cppcheck all come from the
   host, and nearly every rule is a bash `run_shell` that hand-builds `.runfiles/_main` symlink
   trees.

Consequences: no Windows builds, weak hermeticity/reproducibility, and a hard tie to an outdated
mono toolchain that upstream distributions are slowly dropping.

**Goal:** replace as much of `tools/build/` as possible with maintained upstream rulesets.
Priorities, in order:

 1. **Off mono** — compile C# with the hermetic dotnet SDK (Roslyn) via `rules_dotnet`, and run
    the standalone tools/tests on modern .NET.
 2. **Kill sandbox escapes and system-tool dependencies** — hermetic Python toolchain + pip lock
    via `rules_python`; hermetic protoc; hermetic packaging.
 3. **Windows support** — falls out of 1–2 for the C#/Python/proto/Java graph; the remaining
    Linux-only targets get tagged.

**Hard constraint:** the migration is incremental. Every phase (and sub-step within a phase where
noted) lands independently with `bazel build //...` and `bazel test //:test` green (`//:test`
already includes `//:lint`).

## Decisions

 * Shipped mod DLLs and the `KRPC.Client` NuGet package move from net45-era references to
   **net472**, the community-standard TFM for KSP 1.8+ mods (KSP 1.12 = Unity 2019.4, .NET 4.x
   scripting runtime). rules_dotnet ships hermetic `Microsoft.NETFramework.ReferenceAssemblies`
   targeting packs for net40–net481, so no custom work is needed.
 * NuGet dependencies stay **explicitly pinned**: each `.nupkg` `http_archive` in `MODULE.bazel`
   becomes a rules_dotnet `nuget_archive` repo (same id/version/sha pinning). No paket2bazel — a
   resolver would fight the deliberately-old Google.Protobuf 3.10.1 pin required by Unity, and the
   dep set is small and hand-curated. (krpc2 used a rules_dotnet fork + paket on Bazel 6; that
   precedent is superseded by upstream rules_dotnet 0.22.x on bzlmod.)
 * Standalone tools (TestServer, ServiceDefinitions, NUnit test suites) run on **net8.0 LTS**.

## Current state (inventory)

Bazel 9.1.1, bzlmod only. `MODULE.bazel` declares `platforms`, `bazel_skylib`, `rules_cc`,
`rules_pkg`, `rules_python`, `rules_java`, `protobuf` — but **`rules_python` and `rules_pkg` are
entirely unused**; only `rules_cc` (C++/cnano clients) and `rules_java` (Java client) are used
natively. Everything else is custom:

| File | Defines | Replacement |
|---|---|---|
| `tools/build/csharp.bzl` | `CSharpInfo`, `csharp_reference/library/binary/nunit_test/assembly_info`, `nuget_package` | `rules_dotnet` (+ small `assembly_info.bzl` kept) |
| `tools/build/python.bzl` | `py_sdist`, `py_script`, `py_test`, `py_lint_test` (system python + venv + pip) | `rules_python` hermetic toolchain + pip hub; `py_sdist` kept custom but hermetic |
| `tools/build/protobuf/*.bzl` | `protobuf_{csharp,py,cpp,java,lua,nanopb}` + venv helpers | `proto_library` + upstream `py/cc/java_proto_library` + `toolchains_protoc`; C#/lua/nanopb stay custom but hermetic |
| `tools/build/pkg.bzl` | `stage_files`, `pkg_zip` (system `zip`) | `rules_pkg` |
| `tools/build/maven.bzl` | `maven_jar` repo rule (~20 uses) | `rules_jvm_external` |
| `tools/build/mono-4.5/` + `lib/mono-4.5/` | mono BCL/facade `csharp_reference`s | deleted — rules_dotnet targeting packs |
| `tools/build/ksp/` | KSP/Unity DLL `csharp_reference`s | `import_library` over the same `lib/ksp` DLLs |
| `tools/build/{cpp,java,lua,sphinx,image,client_test}.bzl` | lint/test/doc/image/integration wrappers | stay custom; rebased on hermetic toolchains |
| `tools/ServiceDefinitions/build.bzl`, `tools/krpctools/{clientgen,docgen}.bzl` | project-specific codegen | stay custom (consume JSON, insulated from the C# migration) |

Usage that anchors the sequencing: `csharp_library` ×17 (core, server, 8 services, TestingTools,
TestServer, ServiceDefinitions, client/csharp + test libs), `csharp_reference` ×~35,
`csharp_binary` ×4, `csharp_nunit_test` ×2, `service_definitions` ×10, `clientgen_*` ×~50,
`py_sdist`/`py_test` ×6 each, `py_lint_test` ×11, `pkg_zip` ×8 (incl. the root `//:krpc` release
zip), `client_test` ×9.

Two structural facts make the migration tractable:

 * **clientgen and docgen never see DLLs.** They consume the service-definitions JSON emitted by
   `service_definitions`, so the ~50 generated-client targets are insulated from the C# migration.
 * **The custom rules read C# deps through one accessor.** `csharp.bzl` and
   `tools/ServiceDefinitions/build.bzl` only use `dep[CSharpInfo].lib`, which enables the provider
   bridge below.

## Provider bridge (the incrementality mechanism)

rules_dotnet rules cannot depend on custom `CSharpInfo` targets (their `deps` require
`DotnetAssemblyCompileInfo`/`DotnetAssemblyRuntimeInfo`), but the custom rules can trivially accept
rules_dotnet deps:

```starlark
load("@rules_dotnet//dotnet/private:providers.bzl", "DotnetAssemblyRuntimeInfo")

def _dep_lib(dep):
    if CSharpInfo in dep:
        return dep[CSharpInfo].lib
    return dep[DotnetAssemblyRuntimeInfo].libs[0]
```

applied in `_lib_impl`/`_bin_impl` (and `service_definitions`), with the `deps` attribute relaxed
to accept either provider set. Both compilers emit standard IL, so an mcs-compiled library
referencing a Roslyn-compiled net472 dependency links fine. This forces a **bottom-up** migration
order: references → core → server → services → tools → client/csharp, each target converting
individually while its not-yet-converted consumers keep building through the bridge.

## Phases

### Phase 1 — rules_dotnet compilation (mcs → Roslyn); mono becomes runtime-only

Goal: every C# compile action uses the hermetic dotnet SDK; `lib/mono-4.5/` and
`tools/build/mono-4.5/` are deleted; mono survives only as the launcher for TestServer,
ServiceDefinitions and the NUnit runs.

Landable sub-steps:

 1. `MODULE.bazel`: `bazel_dep(name = "rules_dotnet", version = "0.22.1")` (or latest), dotnet
    extension + toolchain registration (`dotnet.toolchain(...)`, `register_toolchains`). Add the
    provider bridge to `csharp.bzl` and `tools/ServiceDefinitions/build.bzl`. Pure no-op landing.
 2. References: `tools/build/ksp/BUILD.bazel` `csharp_reference` → `import_library` (KSP/Unity
    DLLs from `lib/ksp`, KRPC.IO.Ports, Google.Protobuf 3.10.1); nupkg `http_archive`s →
    `nuget_archive` repos (Newtonsoft.Json, NDesk.Options, Moq, Castle.Core, System.Memory chain,
    Google.Protobuf 3.35.1, NUnit).
 3. Convert `csharp_library` targets bottom-up to rules_dotnet
    `csharp_library(target_frameworks = ["net472"])`: `//core:KRPC.Core` → `//server:KRPC` → the 8
    service DLLs → `//tools/ServiceDefinitions:KRPC.Core` → TestServer libs → `//client/csharp`.
    `csharp_assembly_info` outputs keep feeding `srcs` unchanged. Mono facade deps drop per-target
    (the targeting pack supplies the BCL).
 4. The 4 `csharp_binary` and 2 `csharp_nunit_test` targets stay on the custom rules via the
    bridge until Phase 2 (less churn than converting their launchers twice).

Deleted: `tools/build/mono-4.5/`, `lib/mono-4.5/**`, the nupkg `http_archive`s,
`csharp_reference`/`_lib_impl` from `csharp.bzl`.

Verification: `bazel build //...` + `bazel test //:test`; `unzip -l` diff of `krpc-*.zip` against
main; `monodis`/`ikdasm` spot-check that shipped DLLs reference `mscorlib 4.0.0.0` and nothing
above net472; **in-game smoke test (required gate, see below)** — the Roslyn-compiled DLLs must be
proven to load and serve RPCs inside KSP before the phase is considered done.

Risks: Roslyn is stricter than mcs under `-warnaserror` (expect a few `nowarn` additions);
System.Memory assembly unification may need `targeting_pack_overrides`; rules_dotnet does not
propagate transitive compile deps (MSBuild-style), so some previously-implicit deps must become
explicit.

#### Phase 1 implementation notes (July 2026)

Implemented. Deviations from the design above:

 * The pinned nupkg `http_archive`s were kept as-is and wrapped with `import_dll` targets (in
   `tools/build/ksp` and `tools/build/mono-4.5`, same labels as before) rather than converted to
   `nuget_archive` repos — even less churn, same pinning. `nuget_archive` remains an option later.
 * `lib/mono-4.5` and the six BCL `csharp_reference` targets could NOT be deleted in Phase 1: the
   four remaining mcs binaries (ServiceDefinitions, TestServer ×2, doc example exes) still compile
   against them, and the TestServer zip / krpctools sdist ship the mono BCL DLLs as runtime
   payload. They are deleted in Phases 2–3 instead. What was deleted: the custom `csharp_library`
   rule, the KSP BCL reference targets (`ksp_net_libs`), and all mono-facade deps from libraries.
 * The doc example *libraries* (`csharp_library_multiple`) also moved to rules_dotnet;
   only `csharp_binary_multiple` remains on mcs.
 * `copy_file` targets (e.g. `//tools/build/ksp:Google.Protobuf.dll`) reproduce the old
   `csharp_reference` output paths for packaging, since `import_dll` exposes no files in
   `DefaultInfo`.
 * `tools/install.sh` now installs from the built `krpc-<version>.zip` (plus a cquery-resolved
   TestingTools) instead of cherry-picking `bazel-bin` paths — rules_dotnet outputs live in a
   transition-hashed config directory not reachable via the `bazel-bin` symlink.
 * Only one new warning suppression was needed: CS1702 (System.Memory unification in
   KRPC.Client, suppressed by default in MSBuild). Everything else compiled clean under
   `warning_level = 4` + `treat_warnings_as_errors`.

Verification performed: `bazel build //...` green except the pre-existing sphinx/system-python
failure (confirmed present on the base commit); `bazel test //:test` 33/35 with the same sphinx
failure plus one flaky C++ client timeout that passes on re-run; `krpc-*.zip` and
`TestServer-*.zip` file lists byte-identical to main; C# client zip changed `net45/` → `net472/`
as agreed; assembly refs verified (`mscorlib 4.0.0.0`, Google.Protobuf 3.10.1 mod-side / 3.35.1
client-side); in-game smoke test passed (server 0.5.4 in KSP 1.12: get_status, bodies/vessels
object refs, streams, vector returns).

### Phase 2 — TestServer + NUnit tests on net8.0 (first real de-mono)

Multi-target `//core:KRPC.Core`, `//tools/ServiceDefinitions:KRPC.Core` and the TestServer libs
with `target_frameworks = ["net472", "net8.0"]`, with per-TFM `select()`ed deps:

 * Google.Protobuf 3.10.1 (net472/Unity) ↔ 3.35.1 (net8.0) — wire-compatible.
 * KRPC.IO.Ports ↔ the official `System.IO.Ports` package. Mono's SerialPort P/Invokes
   `MonoPosixHelper`, which does not exist on CoreCLR, so the net8.0 branch must switch libraries
   (small `#if NET` shims in `core/src` where APIs differ).

TestServer becomes a rules_dotnet `csharp_binary` (net8.0); `publish_binary` output feeds
`TestServer-*.zip`. The two NUnit suites (`//core`, `//client/csharp`) become rules_dotnet
`csharp_nunit_test` (NUnitLite self-hosted executable — no nunit3-console, no mono); the NUnit
console-runner pins are deleted. `tools/build/client_test.bzl` is patched for the new TestServer
binary path/runfiles shape.

Gate: the full `bazel test //:test`, with `//client/serialio:test` (drives TestServer's serial
port over a socat PTY) as the phase's key risk gate. Before starting:
`grep -rn "AppDomain\|Remoting" core/src server/src` to surface net4x-only API use early.

Fallback: keep the mono TestServer target around (unregistered from `//:test`) for one release as
a bisect aid.

#### Phase 2 implementation notes (July 2026)

Implemented. Deviations and findings:

 * **Separate net8 targets instead of multi-targeting.** `target_frameworks = ["net472", "net8.0"]`
   would make the *default* (untransitioned) flavor net8.0 — which is what filegroups and `pkg_zip`
   consume, so the mod zip would silently ship net8 DLLs. Instead `//core:KRPC.Core.net8` and
   `//client/csharp:KRPC.Client.net8` (with `out` set to keep the assembly identity) sit alongside
   the net472 targets. The shipped targets stay net472-only.
 * New pins: `System.IO.Ports` 8.0.0 + its linux-x64 native shim (`import_library` with separate
   compile ref / unix runtime lib / native .so, in the new `//tools/build/dotnet` package alongside
   net8 imports of Google.Protobuf (net5.0 asset), Moq, Castle.Core, Newtonsoft.Json (net6.0
   assets) — all from the already-pinned archives). Serial shims are `#if NET` conditional usings;
   rules_dotnet sets the MSBuild-style preprocessor symbols automatically.
 * The NUnit suites are single `csharp_nunit_test` targets (compile + NUnitLite self-hosted run on
   net8.0, in the sandbox — the old `local` tag workaround for nunit3-console is gone). rules_dotnet
   pins NUnit 3.14.0, the same version the repo used, so no test API changes. The NUnit console
   runner pins and the custom `csharp_nunit_test` rule are deleted.
 * TestServer/TestServer.Debug are rules_dotnet `csharp_binary` (net8.0); the archive is built from
   `publish_binary` output (framework-dependent, linux-x64 apphost; needs the .NET 8 runtime — the
   mono BCL payload is gone from the zip). `client_test.bzl` needed two fixes: the bash runfiles
   library merged into the test runfiles + `RUNFILES_DIR` exported (the rules_dotnet launcher
   resolves the dotnet runtime through it), and the server now runs directly from the test's
   runfiles tree instead of a hand-staged copy (the dotnet host's relative `additionalProbingPaths`
   resolve deps.json's runfiles-root-relative assembly paths against the working directory; this
   also dropped ~4k `ln -s` calls per test).
 * Real net8 incompatibilities found and fixed in shared sources (all fixes are also valid on
   net472/mono): `Thread.Abort()` in `TCPServer.Start`'s timeout path → `tcpListener.Stop()` (the
   same mechanism `Stop()` already used); `SHA1CryptoServiceProvider` → `SHA1.Create()`;
   serialization constructors in client exception classes and the clientgen C# template wrapped in
   `#if !NET` (SYSLIB0051).
 * Runtime behavior differences fixed in test expectations across all clients (cpp, java, python,
   lua, csharp): exception parameter-name formatting (`Parameter name: foo` → `(Parameter 'foo')`)
   and `double.ToString()` now producing shortest round-trippable strings.
 * KRPC.IO.Ports survives for the net472/KSP build only; NDesk.Options' net2.0-era assembly loads
   fine on .NET 8 and was kept.

Verification: `bazel build //...` green except the pre-existing sphinx/system-python failure;
`bazel test //:test` 34/35 (only that same sphinx failure) — all 9 client integration suites pass
against the net8 TestServer, including `//client/serialio:test` (System.IO.Ports over a socat PTY),
the phase's key risk gate. The mod release zip file list is unchanged. mono is now used only by
the ServiceDefinitions build action and the doc example exes (Phase 3).

### Phase 3 — ServiceDefinitions off mono + nupkg without nuget.exe; delete csharp.bzl

The riskiest phase; deliberately isolated so it can slip without blocking Phases 4–6.

**ServiceDefinitions** → net8.0 `csharp_binary`. It currently `Assembly.Load`s each service DLL
(which references UnityEngine/Assembly-CSharp) under mono to reflect out service metadata.

 * Plan A: `AssemblyLoadContext.LoadFromAssemblyPath` with a resolver over the KSP DLL runfiles.
   CoreCLR loads net4x IL and assembly loading is lazy; reflection that only touches KRPC
   attributes/types may never fault in Unity internals.
 * Plan B (if A faults): rewrite the reflection on `MetadataLoadContext` — fully robust (no code
   execution), but attribute access becomes `CustomAttributeData` and `typeof` comparisons become
   name-based; a real but contained rewrite of `tools/ServiceDefinitions/src`.
 * Acceptance gate (cheap and total): the emitted JSON must be **byte-identical** to mono's output
   for all 9 services — add a temporary diff test during the transition.
 * Fallback: keep a mono launcher for only this one action until A or B lands.

**`nuget_package`** → generate the `.nuspec` via `expand_template`, add the static OPC boilerplate
(`[Content_Types].xml`, `_rels/.rels`, core-properties `.psmdcp`), and zip with rules_pkg
`pkg_zip` — a `.nupkg` is a zip. This removes the `local = 1` sandbox escape and the
`@csharp_nuget` nuget.exe pin. Fallback if nuget.org rejects the hand-built package: a hermetic
`dotnet pack /p:NuspecFile=…` action. Validate against a local feed before the first release.

Then delete `tools/build/csharp.bzl` entirely, moving `csharp_assembly_info` to a small
`tools/build/assembly_info.bzl`. Mono leaves the CI images.

#### Phase 3 implementation notes (July 2026)

Implemented. The riskiest item of the migration resolved cleanly:

 * **Plan A (AssemblyLoadContext) worked** — no MetadataLoadContext rewrite needed. The tool loads
   the target assemblies with `AssemblyLoadContext.Default.LoadFromAssemblyPath` and a `Resolving`
   handler that probes `--reference-dir` directories (new option), the directories of the scanned
   assemblies, and the app base directory. Modern .NET does not auto-resolve assemblies outside
   the app's deps.json, so the handler is required for the UnityEngine/KSP references. The
   `service_definitions` rule passes the KSP DLL directories via `--reference-dir` (they are no
   longer deps of the tool binary itself — important because krpctools must not redistribute KSP
   DLLs; it copies them from the user's install at runtime, resolved via the app-dir probe).
 * **Byte-diff gate passed outright**: all 10 service definition JSONs (9 services + TestService)
   produced by the net8 tool are byte-identical to the mono tool's output — reflection order and
   Newtonsoft formatting are stable across runtimes.
 * krpctools now bundles the `publish_binary` layout of the tool in `krpctools/bin` and runs the
   apphost (`ServiceDefinitions`, not `mono ServiceDefinitions.exe`); requires the .NET 8 runtime.
   The mono BCL payload is gone from the sdist.
 * `nuget_package` now writes the nuspec + OPC boilerplate ([Content_Types].xml, _rels/.rels,
   psmdcp) and zips them — no nuget.exe, no mono, and the `local = 1` sandbox escape is gone
   (the last one in the repo). Validated by `dotnet restore` of the produced nupkg from a local
   feed into a net472 project.
 * The doc example scripts are now compiled as rules_dotnet *libraries* (compile-only checks that
   were never executed), so the last mcs binaries are gone.
 * Deleted: `tools/build/csharp.bzl` (assembly_info moved to `tools/build/assembly_info.bzl`,
   nuget_package to `tools/build/nuget.bzl`), the whole `tools/build/mono-4.5/` package, the
   `lib/mono-4.5` exports, and the nuget.exe pin. Surviving net4x NuGet imports moved to
   `//tools/build/dotnet`. **mono is no longer used anywhere in the build.**

Verification: all 10 JSONs byte-identical; `bazel build //...` and `bazel test //:test` green
except the pre-existing sphinx/system-python failure; the mod release zip is unchanged; nupkg
restore-validated. (The buildenv's mono install is now only needed by older branches — Phase 9.)

### Phase 4 — rules_python: hermetic toolchain + pip hub

Kills the system python dependency, per-action venvs, and the two action-time network installs.

`MODULE.bazel` (rules_python is already a dep; bump while touching it):

```starlark
python = use_extension("@rules_python//python/extensions:python.bzl", "python")
python.toolchain(python_version = "3.12", is_default = True)  # package floor stays 3.10

pip = use_extension("@rules_python//python/extensions:pip.bzl", "pip")
pip.parse(
    hub_name = "pypi",
    python_version = "3.12",
    requirements_lock = "//tools/build/python:requirements_lock.txt",
)
use_repo(pip, "pypi")
```

One `requirements.in` covering runtime deps (protobuf, websocket-client, pyserial, jinja2, …),
tooling (black, pylint, pycodestyle, cpplint, hatchling, pytest) and the sphinx tree, locked with
`compile_pip_requirements` (gives a `:requirements.update` run target + diff test). The lock's
transitive resolution removes the `--no-deps` hand-maintenance documented in krpc's
`Development-Guide.md` and replaces ~60 `http_file` pins.

 * `py_script` uses → `py_console_script_binary` (black/pylint/pycodestyle/cpplint/sphinx-build);
   clientgen/docgen → plain `py_binary` over a `py_library` of `tools/krpctools` sources (no sdist
   round-trip).
 * `py_test`/`py_lint_test` → native `py_test` with `@pypi//pytest`, `@pypi//pylint`, etc.
 * `py_sdist` stays custom (upstream has no sdist rule) but its action runs hatchling from the hub
   on the hermetic interpreter — no venv, no network.
 * `sphinx.bzl` html/spelling/linkcheck run the hub sphinx-build; latex/pdf stays Linux-only.

Acceptance test: everything green with `--sandbox_default_allow_network=false`.

Risks: lock resolution bumping transitives vs today's hand pins (pin troublemakers in the `.in`,
sphinx tree especially); C-extension deps (protobuf) need the hub's platform wheels.

#### Phase 4 implementation notes (July 2026)

Implemented, as designed, with these specifics:

 * rules_python stayed at the already-declared 2.0.3 (2.2.0 was released the day of implementation;
   bumping is orthogonal). Hermetic toolchain is python 3.12; the hub is `@pypi`, locked from
   `tools/build/python/requirements.in` (top-level deps pinned to the previously hand-pinned
   versions). The S3-hosted javasphinx/javalang custom sdists went into the lock as PEP 508 direct
   URL references — worked without issue; `roman-numerals` and the rest of the transitive tree
   resolve automatically. 52 `http_file` pins deleted (`python_protobuf` survives for the protoc
   lua/nanopb plugin envs until Phase 5).
 * `py_test`/`py_lint_test` became macros over the native py_test: tests extract the built sdist
   and run pytest/black/pylint from the hub against it — the "install the sdist into a venv"
   step is gone, tests now run sandboxed (no more `local` tags) and are much faster (krpctools
   tests: 28s → 1.6s). One subtlety: the py_test parameters are baked into a generated main file
   because the client_test harness invokes test executables directly and bazel-runner `args`
   never arrive.
 * New `py_library` targets (`krpc_lib`/`krpc_base_lib`, `krpctest_lib`, `krpctools_lib`) replace
   sdist-install dependency chains; clientgen/docgen are plain `py_binary` targets (no sdist
   round-trip). `krpc_base_lib` (without generated services) breaks the clientgen ↔ krpc cycle,
   mirroring the old `python_base` sdist.
 * `py_sdist` keeps its staging/dereference logic but runs hatchling from the hub
   (`py_console_script_binary`) — no venv, no PEP 668 workaround, no action-time network.
 * sphinx-build is a `py_console_script_binary`; the spelling/linkcheck tests dropped their manual
   runfile staging (proper runfiles merging instead). cpplint runs as a native py_test from the
   hub; pycodestyle was unused and is gone, as are the black/pylint/cpplint/pycodestyle `py_script`
   wrapper packages.

Verification: `bazel build //...` fully green — **including the sphinx doc build, which had been
failing on hosts with python != 3.12's requirements** (the system-python problem this phase set out
to fix); `bazel test //:test` 35/35 including `//doc:spelling`; suite green with
`--sandbox_default_allow_network=false` (the phase's acceptance test); sdist contents verified
(package modules, generated services, schema, version.py, PKG-INFO all present).

### Phase 5 — protobuf: hermetic prebuilt protoc toolchain + upstream codegen where it exists

Add `toolchains_protoc` and `--incompatible_enable_proto_toolchain_resolution` (prebuilt hermetic
protoc per OS, protobuf never compiled from source). `protobuf/BUILD.bazel` gains
`proto_library(name = "krpc_proto")` + upstream `py_proto_library`/`cc_proto_library`/
`java_proto_library` (killing the cpp `sed` include hack via `strip_import_prefix`). Delete the
tool-side `protoc_*` `http_archive`s.

Kept custom, deliberately: C# codegen (no upstream Bazel rule; tools-side uses the toolchain
protoc, and the **Unity protoc 3.10.1 pin stays** — generated code must match the Google.Protobuf
3.10.1 runtime that KSP/Unity can load); lua + nanopb wrappers, with their Python protoc plugins
becoming `py_binary`s from the Phase 4 hub (`--plugin=protoc-gen-X=$(execpath …)`) instead of
venv-tar contraptions.

Verification: diff generated sources (py/cc/java stubs byte-comparable modulo headers);
**in-game smoke test (required gate, see below)** — even though the Unity C# codegen path keeps
its 3.10.1 pin, the protoc/toolchain changes touch code that ships in the mod, so the mod must be
re-proven in KSP before the phase is considered done.

#### Phase 5 implementation notes (July 2026)

Implemented, with a **deliberate scope deviation**: the repo did
NOT switch to `proto_library` + upstream `py/cc/java_proto_library`, nor adopt `toolchains_protoc`.
During implementation it became clear the design's premise was off: the upstream rules produce
*compiled libraries* for in-build linking, but every consumer in this repo ships the *generated
source files* (the python sdists ship `KRPC_pb2.py`, the cpp/cnano client zips ship the generated
`.hpp/.cpp/.h/.c` for their CMake builds, the java client compiles the generated `KRPC.java` into
its released jar). The thin protoc wrapper rules are the right shape for that, and the per-platform
pinned protoc `http_archive`s (linux/osx/windows, v35.1 + the Unity v3.10.1 set) are already
hermetic — `toolchains_protoc` would add a dependency to manage the same thing. Revisit only if
the repo ever consumes protos as in-build libraries.

What did change — the actual hermeticity problem in this area:

 * The lua and nanopb protoc plugins ran inside per-action venvs built with the **system python3**
   and a pip-installed protobuf (the last system-python use in the build). They are now `py_binary`
   targets (`//tools/build/protobuf:protoc-gen-lua`/`:protoc-gen-nanopb`) on the hermetic toolchain
   with `@pypi//protobuf`, passed to protoc via `--plugin=protoc-gen-X=...`. Small wrappers
   (`runpy` + the runfiles library) execute the plugin scripts from `@protoc_lua`/`@protoc_nanopb`;
   the nanopb wrapper adds the generator's directory to `sys.path` for its bundled `proto` package.
 * The venv/tar helper rules (`protoc_lua_env`, `protoc_nanopb_env`) and the last python
   `http_file` pin (`python_protobuf`) are deleted. No `use_default_shell_env` remains in the
   protobuf rules' plugin paths.

Verification: `bazel build //...` green; `bazel test //:test` 35/35 — the lua and cnano client
integration tests exercise the regenerated code end-to-end.

### Phase 6 — rules_jvm_external + rules_pkg

 * `maven.bzl`'s ~20 `maven_jar` repos → `maven.install(artifacts = [...],
   lock_file = "//:maven_install.json")`. Checkstyle's dep tree is why `maven_jar` hurts today;
   the resolver + lockfile handles it. Targets move to `@maven//:...` labels.
 * `pkg.bzl` → rules_pkg: `path_map` → `pkg_files(prefix = ...)` + `renames`; `mode_map` →
   `pkg_attributes(mode = ...)`; `exclude` → `excludes`. rules_pkg's `pkg_zip` is a hermetic
   Python archiver — no system `zip`, deterministic output, Windows-capable. All 8 `pkg_zip` sites
   convert, including the root `//:krpc` release zip and `stage_files` in `doc/`.

Verification: `zipinfo -1` diff of every produced zip vs main (paths + modes) — mechanical and
total. Delete `maven.bzl` + `pkg.bzl`.

#### Phase 6 implementation notes (July 2026)

Implemented:

 * **rules_jvm_external 7.0**: the 18 hand-pinned `maven_jar` repos collapsed to 5 direct
   artifacts (protobuf-java, checkstyle, junit, hamcrest, javatuples) + a 42-artifact
   `maven_install.json` lockfile — the resolver owns checkstyle's dependency tree. Repin with
   `RULES_JVM_EXTERNAL_REPIN=1 bazel run @unpinned_maven//:pin`. Bootstrap gotcha: the lock file
   must exist with a `"version": "2"` stub before the extension will evaluate. `maven.bzl` deleted.
 * **pkg.bzl on rules_pkg, call sites unchanged** (deviation from the design's per-site
   `pkg_files` rewrite): `path_map`'s longest-prefix semantics need analysis-time file paths, so
   `pkg_zip` became a macro — the existing staging rule lays files out (now with an
   executable/regular split from `mode_map`), and rules_pkg's `pkg_files` + `pkg_zip` archive the
   staged tree (`strip_prefix.from_pkg`). No system `zip` for release archives; output timestamps
   are deterministic. `mode_map` now matches the *archive* path exactly (the old rule matched
   input short_path prefixes, so the TestServer apphost's `755` never applied — fixed).
 * **Pre-existing release bug found and fixed**: since the bzlmod migration renamed canonical repo
   names, the `path_map` keys for external files (`_main~_repo_rules~...`) matched nothing, and
   the old `zip -r`-from-staging-dir silently dropped files staged outside it —
   `krpc-<version>.zip` has been shipping **without `GameData/ModuleManager.4.2.3.dll` and
   `LICENSE.KRPC.IO.Ports`**. The keys are updated to the current canonical names, and the staging
   rule now hard-fails on unmapped external paths so this failure mode is loud. (These canonical
   names can change again on bazel/dependency upgrades — the error message says so.)

Verification: `zipinfo` diffs — all seven release archives file-for-file identical to before,
except `krpc-<version>.zip` which correctly gains the two previously-dropped files; TestServer
apphost is 0755 in the archive; `bazel build //...` green; `bazel test //:test` 35/35. Remaining
system tools in the build: `zip` only in the sphinx html rule, plus make/latex, rsvg-convert,
luarocks/lua, socat, cppcheck (cppcheck is replaced in Phase 7; the rest is Phase 8/9 scope).

### Phase 7 — hermetic LLVM toolchain + clang-tidy (replaces cppcheck)

Decided during implementation (July 2026), replacing the original plan's "tag cppcheck as
Linux-only": the cppcheck gate turned out to be a near no-op (it runs with `--check-config`, which
only validates include resolution — no analysis), cppcheck has no hermetic/cross-platform Bazel
story, and clang-tidy is the modern standard. Going all-in on LLVM also makes the C++ *compiler*
hermetic (the last host toolchain in the build) and coherent on Windows later.

Four commits:

 1. **Drop cppcheck**: delete `cpp_check_test` and its call sites (client/cpp, client/cnano);
    nothing of value is lost (see above).
 2. **Hermetic LLVM C++ toolchain**: add `toolchains_llvm` (BCR), register the clang toolchain as
    the C++ toolchain. client/cpp, client/cnano, the C++ protobuf/asio/googletest deps and the doc
    example compile checks must build and pass tests under clang; fix any warnings/flags fallout.
    This removes host gcc/g++ from the build.
 3. **clang-tidy**: add a checked-in `.clang-tidy` (start with a modest check set — `bugprone-*`,
    `performance-*`, `clang-analyzer-*`, plus `google-*`/`readability-*` to take over cpplint's
    non-formatting style checks) and a `cpp_lint` style test rule running the hermetic clang-tidy
    from the LLVM distribution over client/cpp and client/cnano; register in the lint suites.
    Cross-platform, so C++ static analysis does NOT go on the Windows exclusion list.
 4. **clang-format replaces cpplint**: add a checked-in `.clang-format` (Google preset,
    `ColumnLimit: 100` to match the cpplint line length) enforced by a `--dry-run -Werror` test
    rule using the LLVM distribution's clang-format; one-time mechanical reformat of the
    client/cpp and client/cnano sources; generated service headers are excluded (cpplint linted
    them with relaxed per-directory configs). Delete `cpp_lint_test`, the cpplint pip dependency
    and the `CPPLINT.cfg` files. Known minor losses vs cpplint (e.g. TODO comment format checks)
    are accepted.

#### Phase 7 implementation notes (July 2026)

Implemented, all four commits landed. Deviations from the design:

 * **Commit 2 (LLVM toolchain).** `toolchains_llvm` 1.8.0 / LLVM 20.1.3, registered as the C++
   toolchain (`.bazelrc` already pins `-std=c++17`; the C++ client links libc++). One source fix:
   clang rejects the cnano codegen's anonymous `typedef struct { ... } State;` inside
   external-linkage inline functions — gave the struct a block-scoped `State` tag in `cnano.tmpl`
   and regenerated the golden `clientgen-TestService-cnano.txt`. Two benign warning classes are
   left unfixed (no `-Werror`, non-fatal): `-Wunused-command-line-argument` for `-stdlib=libc++`
   on compile actions, and `-Wstatic-in-inline` in the generated cnano service headers.
 * **Commit 3 (clang-tidy) — the design's "run clang-tidy over the clients" needed a specific
   shape.** clang-tidy needs the full compile context, and the `CcInfo` include dirs + source
   paths are *exec-root* relative — so it cannot run from a test's runfiles. The `clang_tidy_test`
   rule (`tools/build/cpp.bzl`) instead runs clang-tidy as a **build action** (flags derived from
   the dep's `CcInfo` compilation context; builtin/libc++ headers from
   `@llvm_toolchain_llvm//:include`; `-stdlib=libc++` for the C++ client) that touches a stamp
   staged into the test's runfiles, so the "test" fails iff the action fails. Deviations from the
   design's suggested check set: **`clang-analyzer-*` dropped** (≈4 min per TU parsing the huge
   generated service headers, plus a false-positive leak on a `std::function` lambda) and
   **`google-*`/`readability-*` not adopted** — formatting-style checks move wholesale to
   clang-format in commit 4, so `bugprone-*` + `performance-*` is the modest high-signal set.
   clang-tidy runs over the **hand-written client library sources only**; the test sources were
   dropped (their test-only include dir + generated `test_service` header aren't in the library
   `CcInfo`, and the value was low). `HeaderFilterRegex` + `ExcludeHeaderFilterRegex` restrict
   diagnostics to hand-written headers (drop third-party + generated `*.pb.*` and
   `include/*/services/`, which share a `client/cpp/include/` path substring under `bazel-out/`).
   Five checks disabled for intentional idioms (documented in `.clang-tidy`). Real findings fixed
   in the client sources (const-ref range loops / value params; explicit narrowing casts);
   intentional empty `EncodingError` catches and the no-OOM `recalloc` carry documented `NOLINT`s.
   cnano's bare `:lint` cpplint target was renamed `:cpplint` under a new `:lint` test_suite,
   mirroring client/cpp.
 * **Commit 4 (clang-format).** `.clang-format` = Google + `ColumnLimit: 100`. `clang_format_test`
   mirrors the tidy rule (action + stamp; `--dry-run --Werror --style=file`). One-time reformat of
   the hand-written client sources (53 files; generated code untouched). Google's `SortIncludes`
   re-sorted `test_services.cpp`'s deliberately-ordered service includes and broke the build
   (`space_center.hpp` must precede `infernal_robotics.hpp`); wrapped that one block in
   `// clang-format off/on` rather than disabling sorting globally. Deleted `cpp_lint_test`,
   `run_cpplint.py`, the `cpplint` pip pin (lock regenerated) and the four `CPPLINT.cfg` files.

Verification: `bazel build //...` green under clang; `bazel test //:test` 35/35 (the two new
clangtidy + two new clangformat targets replace the two cpplint targets); cpp/cnano client
integration tests pass on the reformatted sources; the mod release zip is unchanged (no mod bits
touched). Remaining Windows blocker in the new rules: the `run_shell`/`#!/bin/sh` launcher (Phase 8).

### Phase 8 — Windows enablement

 * Tag Linux-only targets `target_compatible_with = ["@platforms//os:linux"]`: all 9 `client_test`
   suites (bash + socat), lua, sphinx latex/pdf (`make`), `image.bzl` (rsvg-convert).
 * Convert surviving custom rules' `run_shell` → `ctx.actions.run` (the bash dependence, not the
   tools, is the main Windows blocker in what remains).
 * `.bazelrc`: windows config with `startup --windows_enable_symlinks` and
   `build --enable_runfiles` (rules_dotnet requires both).
 * Windows CI job: `bazel build //...` (incompatible targets skip automatically) and
   `bazel test //core:test //client/csharp:test`.

Out of scope: making the `client_test` harness itself cross-platform.

#### Phase 8 implementation notes (July 2026)

Implemented, as a run of small commits. The guiding rule (per the
maintainer): only tag a target `target_compatible_with` linux when Windows support is genuinely
hard — otherwise make the rule OS-independent. Every custom rule that shelled out was reworked:

 * **Cross-platform python helpers replace shell orchestration**, each invoked via
   `ctx.actions.run`: `tools/build/run_and_stamp.py` (run a tool, stamp on success — the
   clang-tidy/clang-format rules, now wrapped in `bazel_skylib` `build_test` instead of a
   `#!/bin/sh` launcher); `tools/build/protobuf/run_protoc.py` (mkdir → stage inputs → protoc →
   copy generated file(s) → regex `#include` rewrite — replaces the six `protobuf_*` rules'
   mkdir/cp/sed/find, and drops a layer of nanopb `-Q/-L` escaping now that there's no shell);
   `tools/build/write_zip.py` (deterministic zip from a manifest — the `nuget_package` OPC archive
   and the sphinx **html** build, replacing system `zip`); `tools/build/build_sdist.py`
   (dereference the staged tree, run hatchling, copy the tarball — the `py_sdist` build).
 * **Staging uses `ctx.actions.symlink`** instead of shell `cp` (`pkg.bzl` `stage_files`, `py_sdist`
   inputs). rules_pkg / hatchling follow the symlinks; archive modes are still set by `pkg_files`.
 * **Genuinely Linux-only targets tagged** `target_compatible_with = ["@platforms//os:linux"]` so a
   Windows `//...` build/test skips them automatically: the 9 `client_test` suites (bash + socat
   harness, out of scope), `lua_test` (luarocks + system lua, no hermetic ruleset), `//doc:pdf`
   (make + texlive), `//doc:{spelling,linkcheck}` (generated bash test wrappers — convertible to
   python later), and `png_image` (rsvg-convert, no hermetic cross-platform rasterizer). The
   `client_test` and `lua_test` rules were wrapped in macros that apply the constraint centrally.
   Only two `run_shell` actions remain (sphinx-latex, png_image) and both sit behind these tags.
 * **`.bazelrc`**: `startup --windows_enable_symlinks` (no-op off Windows) + `common:windows
   --enable_runfiles`. **`ci.yml`**: a `build-windows` job (windows-latest, bazelisk) is added but
   left `continue-on-error` and out of the `all-checks-passed` gate — see the resume point for the
   protoc-`select` blocker that still needs a real Windows runner to resolve.

Verification: `bazel build //...` and `bazel test //:test` 35/35 green on Linux after every commit;
the release zips, nupkg (OPC structure), sdists and html docs were spot-checked to be unchanged.
Windows itself is unverified from the Linux dev environment — that is what the new CI job is for.

### Phase 9 — buildenv image cleanup

The CI image (`tools/buildenv/` → `ghcr.io/krpc/buildenv`, used by every job in `ci.yml` and
`docs.yml`) exists largely to provide the system tools the custom rules shell out to. Once the
preceding phases make those toolchains hermetic, the image shrinks substantially. This phase is
done as a single cleanup pass after all other phases have landed — the image is not bumped
piecemeal during the migration.

Droppable, with the phase that unlocks each:

 * **`mono-complete`** — mcs unused after Phase 1; the mono *runtime* is last used by
   ServiceDefinitions/TestServer/NUnit until Phases 2–3. Drop after Phase 3. (Also deletes the
   mono apt repo/GPG key setup — the image's slowest, flakiest step.)
 * **`dotnet-sdk-10.0` / `dotnet-runtime-10.0`** — rules_dotnet downloads its own hermetic SDK;
   the system install is unused by the Bazel build. Drop after Phase 1 (audit for stray uses
   first).
 * **`python3-dev`, `python3-pip`, `python3-venv`, `python-is-python3`, and the
   `pip3 install protobuf --break-system-packages` layer** — replaced by the hermetic
   rules_python toolchain + pip hub (the pip protobuf existed for the nanopb generator, which
   moves onto the hub in Phase 5). Drop after Phases 4–5. Keep bare `python3` only if an audit
   shows repo shell scripts still need it.
 * **`maven`, `openjdk-11-jdk`** — Bazel already uses `remotejdk_11` (`.bazelrc`) and
   `maven_jar`/`rules_jvm_external` download jars directly. Audit: likely only Java-client
   *publishing* needs maven, and not in these CI jobs. Drop after Phase 6 if the audit agrees.

Must stay (and why):

 * `gcc`/`g++`/`ccache` — droppable after Phase 7 (hermetic LLVM toolchain), if the CMake
   consumer-experience jobs don't need them (they likely do — audit).
 * `cmake`, `libasio-dev`, and the **from-source protobuf + nanopb installs** — these serve the
   CMake consumer-experience jobs (`client/cnano/test-cmake-linux.sh <zip> system`,
   `build-client-cpp-cmake-linux`), which test the released client zips against system-installed
   deps. Orthogonal to the Bazel migration.
 * `cppcheck` — droppable after Phase 7 (replaced by the hermetic clang-tidy).
 * `latexmk`/texlive/`libenchant` (sphinx pdf/spelling), `luarocks`, `socat`,
   `librsvg2-bin` — the deliberately-retained Linux-only custom rules from earlier phases.
 * bazelisk, `git`, `curl`/`ca-certificates`, buildifier.

Also in this phase:

 * Revisit `tools/buildenv/bazelrc`, which globally disables the sandbox
   (`--spawn_strategy=standalone`) on the assumption that the container provides isolation. With
   hermetic toolchains the standalone strategy no longer threatens reproducibility, but try
   re-enabling the linux-sandbox inside the container (needs user namespaces permitted by the
   runner); keep standalone as the documented fallback.
 * Bump `tools/buildenv/VERSION.txt`, add a `CHANGES.txt` entry (dedicated commit, per repo
   convention), rebuild/push via the `Makefile`, and update the image tag in `ci.yml`/`docs.yml`.

Verification: performed manually by the maintainer (image build, push, and CI validation are not
part of the automated migration work).

#### Phase 9 implementation notes (July 2026)

Implemented (as part of [PR #948](https://github.com/krpc/krpc/pull/948)) as a Dockerfile edit + version bump (`3.8.0` → `3.9.0`),
with the image tag updated across `ci.yml`/`docs.yml`. The audit before dropping each package
turned up **two consumers the original plan missed**, so those packages were kept:

 * **mono-complete kept** — *superseded by Phase 10*, which migrated the job below to `dotnet build`
   and dropped mono from the image (3.9.0 → 3.10.0). The `build-csharp-sln` CI job still builds the
   generated Visual Studio solution (`KRPC.sln`) with mono's `msbuild` — a consumer-experience check
   independent of the (now mono-free) Bazel build. The `build-setup` action's `lib/mono-4.5` symlink
   and the mono references in `tools/TestServer/src/TestServer.csproj` / `tools/msbuild/*.props`
   serve this same path. Dropping mono would require migrating that job off msbuild — out of scope
   for image cleanup.
 * **python3 + pip `protobuf` kept.** The system nanopb generator used by the C-nano CMake consumer
   jobs (`client/cnano/test-cmake-linux.sh`) imports `google.protobuf`. The design's "drop pip
   protobuf after Phase 5" only accounted for the Bazel-side generator (which did move to the
   hermetic hub).

Dropped: `dotnet-sdk-10.0` + `dotnet-runtime-10.0` (rules_dotnet hermetic), `cppcheck` (clang-tidy),
`maven` + `openjdk-11-jdk` (rules_jvm_external + remotejdk_11 + Bazel's embedded JDK), and
`python3-dev`/`python3-venv`/`python-is-python3`. Kept for the CMake consumer / Linux-only rules:
gcc/g++/ccache/cmake/libasio-dev + the from-source protobuf & nanopb, and
latex/luarocks/socat/librsvg2-bin. The `tools/buildenv/bazelrc` sandbox-disable
(`--spawn_strategy=standalone`) was left as-is: re-enabling the linux-sandbox needs a real container
runner to validate (the design's optional follow-up), so it stays the documented default.

Not done here (maintainer-side, per the phase's verification note): the actual `docker build`/`push`
of `buildenv:3.9.0` and the CI run that validates it — CI references the new tag but the image must
be pushed first. The system-dotnet removal is the drop most worth watching in that validation.

### Phase 10 — build the .NET solution with `dotnet`, not mono `msbuild` (removes mono entirely)

**Goal:** finish the "off mono" objective (migration Priority #1). After Phase 9, mono survives in
the buildenv for exactly one reason: the `build-csharp-sln` CI job builds the checked-in Visual
Studio solution `KRPC.sln` with mono's `msbuild`. This is the developer/IDE build path (independent
of Bazel — it's how contributors work in an IDE and the consumer-experience gate that the generated
projects still compile). Migrating that job to the .NET SDK's `dotnet build` removes the last mono
consumer, so `mono-complete` (and its slow, flaky mono apt-repo + GPG-keyring step — historically
the image's worst build step) can leave `tools/buildenv` for good.

**Current state (inventory).** 16 checked-in, **classic non-SDK** `.csproj`
(`ToolsVersion="4.0"`, the `.../developer/msbuild/2003` xmlns, `<TargetFrameworkVersion>v4.5.2`,
`<NoStdLib>true`, explicit `<Compile Include>` lists) tie together via `KRPC.sln`. Each:
 * imports `$(MSBuildBinPath)\Microsoft.CSharp.targets` (the full-framework/mono msbuild target
   path) plus `tools/msbuild/ksplibs.props` / `bazeldirs.props`;
 * references Bazel build outputs by `<HintPath>$(bazel-bin)\tools\build\ksp\Google.Protobuf.dll`,
   the KSP/Unity DLLs, `KRPC.IO.Ports.dll`, and pulls generated sources with
   `<Compile Include="$(bazel-bin)\...AssemblyInfo.cs">` / `KRPC_unity.cs` / `KRPC.cs`.
The `build-genfiles` job (`tools/dist/genfiles.sh`) produces those `bazel-bin` inputs as
`krpc-genfiles-*.zip`, extracted before the msbuild step; `build-setup/action.yml` symlinks
`lib/mono-4.5 → /usr/lib/mono/4.5`. Note `tools/TestServer/src/TestServer.csproj` still references
`$(bazel-bin)\tools\build\mono-4.5\Google.Protobuf.dll`, a path Phase 3 deleted — audit/repoint it
during this phase (it should use the `//tools/build/ksp` copy like the others).

**Why it isn't just a command swap.** `dotnet build` (the .NET SDK) can build .NET Framework
targets **without mono** by compiling against the `Microsoft.NETFramework.ReferenceAssemblies`
NuGet targeting packs (reference-only; the same packs rules_dotnet already uses). But the SDK does
not honor the classic `$(MSBuildBinPath)\Microsoft.CSharp.targets` import or the 2003-era project
format cleanly. So the projects need converting.

**Approach (recommended: SDK-style conversion).**

 1. Rewrite the 16 `.csproj` as SDK-style (`<Project Sdk="Microsoft.NET.Sdk">`) targeting
    **`net472`** — matching the shipped-DLL / `KRPC.Client` decision from Phase 1 (the classic
    projects still say v4.5.2; bumping to net472 keeps the IDE build consistent with what Bazel
    produces). Drop the `Microsoft.CSharp.targets` import (the SDK supplies it) and add
    `<PackageReference Include="Microsoft.NETFramework.ReferenceAssemblies" Version="…"
    PrivateAssets="all" />` so net472 resolves with no mono. Keep the `<Reference><HintPath>
    $(bazel-bin)…` items and the generated-source `<Compile Include="$(bazel-bin)…">`; disable
    default globbing (`<EnableDefaultCompileItems>false</EnableDefaultCompileItems>`) so the
    explicit compile lists (which pull in generated + repo sources but exclude `bin/`) keep working
    unchanged. This is mechanical across 16 files — script it or template it, then diff.
 2. Repoint the stale `TestServer.csproj` mono reference to `//tools/build/ksp`.
 3. **CI (`build-csharp-sln`)**: `dotnet build KRPC.sln -c Debug -warnaserror` and `-c Release
    -warnaserror` in place of the two `msbuild` lines. Remove the `lib/mono-4.5` symlink step from
    `build-setup/action.yml`.
 4. **buildenv (revisits Phase 9)**: **add a system `dotnet-sdk`** (Phase 9 dropped it because the
    Bazel build is hermetic; the `dotnet build KRPC.sln` command needs a host SDK) and **drop
    `mono-complete`** plus its GPG/apt-repo/keyring setup. Net image change: swap the flaky mono
    stack for a clean MS `dotnet-sdk` — and the migration is finally, fully off mono. Bump
    `VERSION.txt`, add the dedicated `CHANGES.txt` entry, rebuild/push, retag `ci.yml`/`docs.yml`.

**Risks / notes.**
 * Classic→SDK conversion ×16 is error-prone (compile-item globbing, generated-file includes,
   `DocumentationFile`/`DefineConstants` per-config, `NoStdLib`); the output isn't shipped (this is
   a compile-only gate) but it must build clean under `-warnaserror` in both configs.
 * net452→net472 is a superset bump; unlikely to surface source changes, but build both configs.
 * `dotnet build` restores `Microsoft.NETFramework.ReferenceAssemblies` from NuGet at CI time
   (network) — acceptable in this consumer-experience job, or pre-restore.
 * This phase **supersedes Phase 9's "mono-complete kept" decision** — once it lands, the Phase 9
   note and the buildenv mono layer are removed.

**Verification:** `dotnet build KRPC.sln -c Debug/-c Release -warnaserror` green in a buildenv image
with a system dotnet SDK and **no mono installed**; opening `KRPC.sln` in an IDE still builds; the
Bazel build and `bazel test //:test` are untouched (this phase only changes the IDE/solution path).

#### Phase 10 implementation notes (July 2026)

Implemented as designed (SDK-style conversion of all 16 projects to
net472 + `Microsoft.NETFramework.ReferenceAssemblies`), validated with a locally-installed .NET 8
SDK: `dotnet build KRPC.sln` in Debug and Release, both `-warnaserror`, **0 warnings / 0 errors**.
Findings and deviations:

 * **The `.sln`/msbuild path was already broken on the branch** — the migration (Phases 1–3) had
   deleted `tools/build/mono-4.5` and moved NUnit to rules_dotnet's nuget, but the classic csproj +
   `genfiles.sh` still referenced `mono-4.5/Google.Protobuf.dll` and the deleted `csharp_nunit`
   http_archive (and `genfiles.sh` uses `zip -MM`, which errors on the missing path). Phase 10 both
   repairs and migrates this path. Test/client external deps (NUnit, Moq, Google.Protobuf) moved to
   **`PackageReference`** (restored from nuget.org — cleaner and no fragile canonical-repo-name
   coupling); `genfiles.sh` now ships only the still-referenced externals (`csharp_json`,
   `csharp_moq`, `csharp_options`) + the ksp DLLs. `TestServer`'s Google.Protobuf repoints from the
   deleted `mono-4.5` copy to the ksp (3.10.1) copy, matching the KRPC.Core it links.
 * **BCL:** `ksplibs.props` no longer references KSP's Unity `mscorlib`/`System`/`System.Xml` (the
   old `NoStdLib` approach); the net472 targeting pack supplies them, `System.Xml` by simple name.
   Only the KSP/Unity-specific assemblies (UnityEngine\*, Assembly-CSharp\*) come from the game
   install. This matches how the Bazel build already compiled these (net472 packs, Phase 1).
 * **InternalsVisibleTo divergence:** the Bazel build injects IVT via rules_dotnet's
   `internals_visible_to` attr, so it is absent from the shared `AssemblyInfo.cs` the solution
   consumes. The two library assemblies that need it (KRPC.Core → KRPC.Core.Test, KRPC.Client →
   KRPC.Client.Test) plus KRPC.SpaceCenter → TestingTools get a small `InternalsVisibleTo.cs` placed
   **outside `src/`** (which Bazel globs) so Bazel does not double-inject the attribute; the csproj
   explicit compile lists include it. (server's Bazel IVT friends — `KRPC.Test`,
   `DynamicProxyGenAssembly2` — are a runtime/absent-project concern, not needed for the compile.)
 * **buildenv (revisits Phase 9):** `mono-complete` and its GPG/apt-repo step removed;
   `dotnet-sdk-8.0` added for `dotnet build`; `lib/mono-4.5` symlink dropped from `build-setup`.
   Image `3.9.0 → 3.10.0`. rules_dotnet still uses its own hermetic SDK for the Bazel build.

Not done here (unchanged from the other maintainer-side items): the buildenv image
build/push and the CI run that exercises `dotnet build KRPC.sln` in the container. (During
implementation the sandbox's Bazel cache repeatedly evicted large hermetic repos — LLVM, then the
python toolchain — under disk pressure, which is unrelated to these changes; the `dotnet` and Bazel
validations above were done before/around those evictions.)

## In-game smoke test (required gate after Phases 1 and 5)

Phases 1 and 5 change what actually ships inside the mod (Phase 1: every DLL is recompiled by a
different compiler against different reference assemblies; Phase 5: protoc/codegen changes touch
generated code linked into the mod). After each of these phases, before it is considered done:

 1. Build and install the mod into KSP and launch into a save:
    `tools/run-ksp.sh --krpc-auto-load-game=krpctest` (runs `tools/install.sh`, which copies the
    freshly built core/server/service DLLs into `$KSP_DIR/GameData/kRPC`).
 2. Confirm the server starts (kRPC lines in the KSP log, no exceptions on load) and accepts a
    connection: `krpc.connect()` from a Python client.
 3. Exercise a few RPCs end-to-end — at minimum `krpc.get_status()`, a SpaceCenter property read
    (e.g. active vessel name), and a stream — to prove protobuf serialization works in-game with
    the Unity Google.Protobuf 3.10.1 runtime.
 4. Preferably run a slice of the integration test suite against the live game (see krpc's
    `Development-Guide.md`) rather than just manual pokes.

Other phases don't ship different bits into the mod (Phases 2–4 and 6 change tools, tests,
Python, and packaging only), so `bazel test //:test` plus the phase-specific gates suffice there —
but re-running the smoke test after Phase 6 (repackaged `krpc-*.zip`) costs little and is
recommended.

## Risk register

| # | Risk | Phase | Mitigation / fallback |
|---|---|---|---|
| 1 | ServiceDefinitions reflection under CoreCLR | 3 | byte-diff JSON gate; MetadataLoadContext Plan B; mono retained for this one action |
| 2 | Serial port behavior under net8.0 TestServer | 2 | System.IO.Ports package; `//client/serialio:test` is the gate; mono TestServer kept unregistered for one release |
| 3 | net472 targeting pack vs mono facades (unification warnings, System.Memory) | 1 | `targeting_pack_overrides`; nowarn additions |
| 4 | Unity Google.Protobuf/protoc 3.10.1 coupling | all | pin preserved end-to-end; never resolver-managed |
| 5 | Hand-built nupkg OPC acceptance by nuget.org | 3 | validate on a local feed; `dotnet pack` fallback |
| 6 | Lock-file version drift vs hand pins (pip, maven) | 4, 6 | lockfiles reviewed in PR; regressions pinned in `.in`/artifact lists |

## What remains custom (and why)

`clientgen`/`docgen`/`service_definitions` (project-specific codegen), `client_test.bzl` (bespoke
integration harness), `lua_test` (no maintained Lua ruleset), the thin `sphinx.bzl` shell (on
hermetic python after Phase 4), `image.bzl`, `assembly_info`. All end up with hermetic inputs and
lose `run_shell` where feasible, but stay in-repo.
