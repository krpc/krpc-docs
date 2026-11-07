# Import the C# NuGet packages with rules_dotnet's NuGet rules

Each C# library the build uses is a NuGet package downloaded as a plain `http_archive` in `MODULE.bazel`, then imported with `import_dll` from one `lib/<tfm>/` folder picked by hand. The packages are Google.Protobuf, System.Memory, System.Runtime.CompilerServices.Unsafe, System.IO.Ports, Moq, Castle.Core, Newtonsoft.Json, NDesk.Options and Microsoft.CodeAnalysis.NetAnalyzers.

This has two costs:

- A package used from two target frameworks needs one import per framework. `//tools/build/dotnet` has `Google.Protobuf` (`net8.0`) and `Google.Protobuf.netstandard2.0`, and a target must name the one matching its framework.
- A package's own dependencies are listed by hand. `KRPC.Client` names System.Memory and Unsafe, which NuGet would add through Google.Protobuf.

rules_dotnet's `nuget_repo` gives one `import_library` per package. It selects the assets and the dependencies for the target framework of each target that uses it. `paket2bazel` generates the package list from `paket.dependencies` and `paket.lock`, as rules_dotnet does for its own packages.

Proposal:

- Declare the packages in `paket.dependencies`, lock them, and generate the `nuget_repo` with `paket2bazel`, behind a module extension.
- Replace the imports in `//tools/build/dotnet` with the generated targets. Each package becomes one label, whatever the framework of the target using it.
- Drop the hand-listed transitive dependencies.
- Keep the `//tools/build/ksp` imports, which match the assemblies KSP ships, unless a pinned package version covers them.
- A bazel target that regenerates the lock and the package list, alongside `//tools/build/python:requirements.update`.

`KRPC.Client` compiles against Protobuf's `netstandard2.0` asset, while its .NET 10 tests must load the `net8.0` one, as a NuGet consumer does. Check the tests' `deps.json` after the switch. #1230 keeps this right with an `import_library` that splits the compile-time and run-time assets.

Follows #1230, which moves `KRPC.Client` to `netstandard2.0`, so that both the client and its .NET 10 tests import Google.Protobuf.

## Implementation Notes

A trial of this proposal builds and passes `//:test` on Linux. It departs from the proposal in these places:

- **`KRPC.Client` keeps the split import.** A `@paket.main//google.protobuf` label gave the client's .NET 10 tests the `netstandard2.0` asset, plus System.Memory, System.Buffers, System.Numerics.Vectors and Unsafe. rules_dotnet resolves a package at the framework of the target that depends on it, and `deps.json` keeps the first entry per name and version. It has no compile-only dependency. `Google.Protobuf.netstandard2.0` therefore stays, and takes its files from the `@nuget.*` repos. With it, the client tests' `deps.json` matches the one before the switch.
- **System.Memory and Unsafe stay hand-listed for the client.** They are `refs` of that import, so the second cost above remains for this one target. Every other hand-listed dependency is gone, such as Castle.Core under Moq.
- **NDesk.Options stays an `http_archive` and an `import_dll`.** Its assembly sits directly under `lib/`, which `nuget_archive` skips, so the generated target has no assembly. The `.csproj` hint paths and `tools/release/genfiles.py` keep their paths as a result. A follow-up replaces NDesk.Options with System.CommandLine, which `nuget_repo` handles, and that removes this exception. The same follow-up replaces Newtonsoft.Json with System.Text.Json.
- **rules_dotnet needs a patch.** `_create_rid_native_select` keeps the `_._` placeholders that the TFM selects drop. Each `runtime.*.System.IO.Ports` package holds one per RID, so a binary fails with conflicting actions on `runtimes/<rid>/native/_._`. The fix is one line, applied with `single_version_override`.

Other details from the trial:

- **The lock uses `strategy: min`.** NuGet takes a dependency's lowest allowed version, and Paket takes the highest by default.
- **Moq and System.IO.Ports are restricted to `net10.0`.** Without that, Moq's dependencies raise Unsafe to 6.1.2 for `netstandard2.0`. `KRPC.Client` still references System.Memory 4.0.1.1 with the restriction, the version a .NET Framework program gets from NuGet.
- **Paket comes from a `tools` group in the same file.** It is 10.0.0-alpha011, the version rules_dotnet's `paket2bazel` builds on. `//tools/build/dotnet:update` runs it and `paket2bazel` on Bazel's .NET toolchain. Two runs in a row give identical files.
- **`deps.json` changes are small.** `KRPC.Core.Test` gains System.Diagnostics.EventLog through Castle.Core. Binaries using System.IO.Ports gain empty entries for the native packages.
- **The native shim no longer depends on one hand-written RID.** The old import selected only `linux-x64`. Only `linux-x64` has been run.

## Open Questions

- **Is the split import acceptable, or worth fixing upstream?** Removing it needs a compile-only dependency in rules_dotnet, or asset selection at the framework of the binary. A local wrapper rule was rejected: an empty runtime entry for Protobuf would win the first-entry rule in `deps.json`.
- **How should Protobuf's version stay in step?** Settled: `//tools/build/dotnet:versions-test` checks each hand-written version against the lock, and the build docs list them. The `.csproj` versions are [csproj-package-versions.md](csproj-package-versions.md).
- **Should the two rules_dotnet problems be reported upstream?** The patch can go once a release has the fix. The `lib/` behavior may be intended.
- **Should a test check the generated files against `paket.lock`?** No check catches a hand edit or a missed regeneration, unlike `:requirements_test` for Python. The check needs network access, or a comparison that does not run Paket.
- **Is an alpha Paket acceptable?** It only runs on an update, and nothing it produces ships beyond the lock file.
- **Does Windows work?** This has not been run on Windows. Check the path lengths of repos such as `+main_extension+nuget.runtime.maccatalyst-arm64.runtime.native.system.io.ports.v10.0.14`, and that the `win-x64` tools get the Windows build of `System.IO.Ports.dll`. `//tools/build/dotnet:update` has only run on Linux.
- **Should the `//tools/build/ksp` Protobuf move too?** It stays an `http_archive` at 3.10.1, as proposed. A second Paket group could hold it, which has not been tried.
