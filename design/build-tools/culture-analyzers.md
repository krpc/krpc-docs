# Re-enable the culture analyzers for the C# projects

**Status:** in progress. Split out of the [locale hardening](../locale-hardening.md) work
([PR #993](https://github.com/krpc/krpc/pull/993)); the config itself is not yet merged, sitting on
top of that work. No issue or PR filed yet.

## Rationale

The C# projects have no static analysis at all, so nothing stops the ambient culture from leaking back
into values that leave the process — exactly the class of bug PR #993 fixed by hand. The intended
guard is a root `Directory.Build.props` enabling the .NET analyzers with `AnalysisMode=None`, plus an
`.editorconfig` turning on **only** the culture rules, so that enabling any further rule stays a
deliberate act rather than something a toolchain update decides.

## Rules to enable

| Rule | Concern |
|---|---|
| `CA1304` | `IFormatProvider` (culture) |
| `CA1305` | `IFormatProvider` (culture) |
| `CA1307` | `StringComparison` |
| `CA1310` | `StringComparison` |
| `CA1311` | `ToUpperInvariant` / `ToLowerInvariant` |

## Why it was held back from #993

The analyzers report violations well beyond what that PR fixed. CI builds with
`dotnet build KRPC.sln -warnaserror`, so every one of those becomes a build failure. Each site needs
triaging into a real fix or a justified suppression.

Sites flagged: `AutoPilotInfoWindow`, `PartField`, `Stage`, `Experiment`, the KAC/IR `LogFormatted`
wrappers, `APILoader`, `ModuleWheelDeploymentExtensions`, the server UI windows, `TestServer`.

**`Sensor.Value` is deliberately ambient** — it reproduces the game's own readout, which the game
formats with the player's culture — so it wants a suppression with that rationale, not a fix.

## Prefer driving this from Bazel rather than from the project files

As drafted the config only gates the `build-csharp-sln` CI job, because that is the only build that
runs the analyzers — the Bazel build globs sources and never reads `Directory.Build.props`. That
leaves the guard invisible to every local `bazel build`/`bazel test`, the same split that already
makes a missing `.csproj` `Compile Include` fail only in CI. Running the analyzers as part of the
Bazel C# compile (or as a dedicated `//:lint` target) would make the check apply wherever the code is
built, and would remove the dependency on the `.csproj` files staying in sync.

## Trap: SDK skew when triaging

The local dotnet SDK 10 analyzers flag ~30 pre-existing `CA1305`/`CA1307` sites in
`KRPC.SpaceCenter` that CI's dotnet-sdk-8.0 (buildenv container) does not, because
`AnalysisLevel=latest` resolves to a different rule set per SDK. `dotnet build -warnaserror` therefore
fails locally on files CI accepts. Pinning `AnalysisLevel` to a fixed version would make the two
agree; a Bazel-driven check would pin the toolchain anyway. Moving to
[.NET 10](../../issues/dotnet-10-migration.md) first removes the skew entirely, so the analyzer triage is done
against the rule set CI will actually run.

## Changelog impact

None for the analyzer config itself — dev tooling only. Any real ambient-culture leak it turns up in
shipped behavior gets an entry for its component.
