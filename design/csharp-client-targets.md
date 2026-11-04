# C# client: target .NET Standard 2.0

**Status:** proposal. Issue [#1230](https://github.com/krpc/krpc/issues/1230).

## Problem

The `KRPC.Client` package ships one assembly, built for .NET Framework 4.7.2 (#948). A .NET 5+
project references it through the .NET Framework compatibility shim, and NuGet warns with NU1701.

The server needs .NET Framework because it loads into KSP's Mono. The client runs in the user's own
program, and has no such need.

## Current state

| Piece | Today |
| --- | --- |
| `//client/csharp:KRPC.Client` | `net472`, against `Google.Protobuf.netstandard2.0` and the `net462` `System.Memory` and `Unsafe` assets. The only assembly in the nupkg |
| `//client/csharp:KRPC.Client.net10` | the same sources for `net10.0`. Used by the unit tests, the conformance testee and the benchmark, never shipped |
| `nuget_package` (`tools/build/nuget.bzl`) | framework names for `net45` and `net472` only |
| `KRPC.Client.csproj` (sln) | `net472`, with `Microsoft.NETFramework.ReferenceAssemblies` |
| Doc examples (`compile-scripts-csharp-exes` in `doc/BUILD.bazel`) | compile against `KRPC.Client` plus `Google.Protobuf.netstandard2.0` |
| Tests of the shipped assembly | none. Every test and the testee use the net10 build |

rules_dotnet 0.22.2 has the `NETStandard.Library` 2.0.3 targeting pack. Google.Protobuf 3.36.2,
`System.Memory` and `System.Runtime.CompilerServices.Unsafe` all ship `netstandard2.0` assets.

## Design

The package ships one assembly, built for `netstandard2.0`. The tests run that same assembly.

**One target.** `netstandard2.0` loads on .NET Framework 4.7.2+, .NET Core 2.0+ and .NET 5+. A
.NET 5+ project references it directly, with no NU1701. NuGet resolves Google.Protobuf per
consuming project, so a .NET 10 program gets Protobuf's `net8.0` build.

**No `net10.0` assembly.** It would only swap `UnixEndPoint` for the runtime's
`UnixDomainSocketEndPoint`. `UnixEndPoint` already passes the `localsocket` conformance tests on
.NET 10, in today's net10 build. A `net10.0` assembly can be added later if the client needs an
API that `netstandard2.0` lacks. Adding it then does not break anyone.

**Not breaking.** A `net472` project resolves the `netstandard2.0` assembly. The public API is
unchanged.

**Runtimes tested.** The `dotnet` runtime only (.NET 10), on Linux and Windows. No test runs on
.NET Framework or Mono.

### Sources

No changes are expected. The sources compile for `net472` today, so they fit the `netstandard2.0`
API. `UnixEndPoint` and the `#if !NET` serialization constructors stay.

### Build

| Target | Change |
| --- | --- |
| `KRPC.Client` | `target_frameworks = ["netstandard2.0"]`. Deps move to the `netstandard2.0` assets of `System.Memory` and `Unsafe` (imports in `tools/build/dotnet/BUILD.bazel`) |
| `KRPC.Client.net10` | removed. The unit tests, testee and benchmark depend on `KRPC.Client` |
| `nuget_package` | `framework = "netstandard2.0"`, named `.NETStandard2.0` in the dependency group. No `<frameworkAssemblies>` when `framework_deps` is empty. Drop the unused `net45` entry |
| `KRPC.Client.csproj` | `<TargetFramework>netstandard2.0</TargetFramework>`, drop `Microsoft.NETFramework.ReferenceAssemblies` |
| `KRPC.Client.Test.csproj` | `net10.0` |

The release scripts (`40-build-assets.py`, `62-release-nuget.py`) use the same nupkg path, and
need no change.

**Two Google.Protobuf imports stay.** `KRPC.Client` must compile against the `netstandard2.0`
asset. Against the `net8.0` one, csc fails with CS1705: that build references `System.Runtime`
8.0.0.0, and `netstandard2.0` provides 4.1.2.0.

**To check in phase 1.** The net10 test targets then carry both copies: the `netstandard2.0` one
via `KRPC.Client`, and the `net8.0` one they reference themselves. rules_dotnet writes one
`deps.json` entry per assembly name and version, keeping the first it meets, so one copy loads.
Read the testee's `deps.json`. If it lists the `netstandard2.0` copy, reorder the deps so the
tests load the `net8.0` one, as a NuGet consumer on .NET 10 does.

### Tests

| Target | Change |
| --- | --- |
| `:conformance` | the testee runs on .NET 10 against the `netstandard2.0` assembly, the one that ships |
| `:unit`, `:test-KRPC.Client` | same: net10 tests against the `netstandard2.0` assembly. `UnixEndPointTest.cs` stays |
| `:benchmark` | against the `netstandard2.0` assembly |

The nupkg is checked by hand: `dotnet add package` from a local feed in a `net10.0` project, with
no NU1701 warning.

### Docs and changelog

- `doc/src/csharp.rst`: the requirement becomes .NET Standard 2.0: .NET 5 or later, .NET Core 2.0
  or later, or .NET Framework 4.7.2 or later.
- `tools/build/dotnet/BUILD.bazel`: the comment on which assets serve which build.
- Fragment `changelog.d/csharp-net-target.md`, `## client/csharp`: "Target .NET Standard 2.0, in
  place of .NET Framework 4.7.2 (#NNN)".

## Phases

Each phase is one commit on the branch. The PR carries both.

1. **Target and package.** `KRPC.Client` on `netstandard2.0`, `KRPC.Client.net10` removed, the
   test targets moved onto `KRPC.Client`, `nuget_package`, the `.csproj` files. Check the nupkg by
   hand.
2. **Docs and changelog.**

Milestone `ksp-v0.8.0`; labels `feature`, `client`, `csharp`.

## Follow-up: rules_dotnet's NuGet rules

Straight after this PR. Draft issue: [csharp-nuget-repo.md](../issues/csharp-nuget-repo.md).

Every C# package is an `http_archive` plus an `import_dll` of one hand-picked `lib/<tfm>/` folder,
with its own dependencies listed by hand. rules_dotnet's `nuget_repo`, generated by `paket2bazel`,
gives one `import_library` per package that selects the assets and dependencies per target
framework. `:Google.Protobuf.netstandard2.0` and the hand-listed `System.Memory` and `Unsafe` then
go away. The phase 1 `deps.json` check is repeated there, as both copies still reach the tests.

## Open questions

1. **Stated .NET Framework support.** No test runs on .NET Framework. `netstandard2.0` loads on
   4.6.1, but 4.6.1 to 4.7.1 need extra facades and binding redirects. The docs keep 4.7.2 as the
   floor. Should they name .NET Framework at all?
2. **Package test.** The nupkg is checked by hand. A Bazel test that consumes it needs NuGet
   restore, which is network access in a test. A check of its file list and nuspec needs none.
