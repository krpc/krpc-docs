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

Follows #1230, which moves `KRPC.Client` to `netstandard2.0`, so that both the client and its .NET 10 tests import Google.Protobuf.
