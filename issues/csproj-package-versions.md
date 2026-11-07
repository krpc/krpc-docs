# Keep the `.csproj` package versions in step with the Bazel lock files

The `.csproj` files name each NuGet package with a `<PackageReference>` and a version. They are used by the IDE solution (`kRPC.sln`, after `//:csproj`) and by the `dotnet build` that reproduces a CI compile failure. Bazel takes the same packages from `tools/build/dotnet/paket.lock`, after the `nuget_repo` import (see [csharp-nuget-repo.md](csharp-nuget-repo.md)).

Nothing ties the two. A package bump that updates `paket.dependencies` builds and passes `//:test`, while the `.csproj` files keep the old version. `//tools/build/dotnet:versions-test` checks the versions in the Bazel files only.

The references by source of their version:

| Package | `.csproj` files | Bazel source |
| --- | --- | --- |
| Google.Protobuf | `KRPC.Client`, `KRPC.Client.Test`, `KRPC.Core` | `paket.lock` |
| System.IO.Ports | `KRPC.Core` | `paket.lock` |
| Moq, Newtonsoft.Json | `KRPC.Core.Test`; Newtonsoft.Json also `ServiceDefinitions` | `paket.lock` |
| NUnit | `KRPC.Client.Test`, `KRPC.Core.Test` | rules_dotnet's own packages |
| Microsoft.NETFramework.ReferenceAssemblies | 14 `net472` projects | rules_dotnet's targeting packs |

The `experimental/ksa` projects are out of scope. They build with `dotnet` alone and pin their own versions. `KRPC.KSA` already differs, with System.IO.Ports 10.0.13.

Options:

- **Extend `versions-test` to the `.csproj` files.** Small, and it fails on a stale version. Versions stay in many files.
- **Central Package Management.** One `Directory.Packages.props` holds each version, and the `.csproj` files drop theirs. `versions-test` then checks one file. Generating it from `paket.lock` in `//tools/build/dotnet:update` removes the hand edit.

The NUnit and ReferenceAssemblies versions come from rules_dotnet, which changes them on a rules_dotnet bump. A check for them reads the rules_dotnet repository, or they stay out of scope.
