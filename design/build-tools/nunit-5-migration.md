# Move the C# test suites to NUnit 5

**Status:** proposal, not started. Tests only, can land in any release. Issue drafted in
[issues/nunit-5-migration.md](../../issues/nunit-5-migration.md).

The headless C# suites use NUnit 3.14.0:

* `core/test/KRPC.Core.Test.csproj`
* `client/csharp/test/KRPC.Client.Test.csproj`

NUnit 3 is no longer the maintained line. We skip 4.x and target the latest versions:

| Package | Version | Notes |
| --- | --- | --- |
| NUnit | 5.0.0 | Released 2026-09-27. Targets net462, net8.0 and net10.0 |
| NUnitLite | 5.0.0 | Runner for the Bazel targets |
| NUnit.Analyzers | 4.15.0 | Code fixes for the assertion rewrite |

## Bazel pins NUnit through rules_dotnet

`csharp_nunit_test` in rules_dotnet 0.22.2 appends its own
`@paket.rules_dotnet_nuget_packages//nunit` and `//nunitlite`, both 3.14. It also adds a `shim.cs`
entry point, `new NUnitLite.AutoRun().Execute(args)`. The rule's own source marks this "TODO: This
should be user configurable".

So upgrading only the `PackageReference` changes the `KRPC.sln` build and leaves the Bazel build
on NUnit 3. The fix:

* `MODULE.bazel`: `http_archive`s for NUnit and NUnitLite, like the Moq one.
* `tools/build/dotnet/BUILD.bazel`: an `import_dll` for each, from `lib/net10.0/`.
* `tools/build/dotnet/NUnitShim.cs`: a copy of the rules_dotnet shim.
* `tools/build/csharp.bzl`: `csharp_nunit_test` wraps `csharp_test` and appends the shim and the
  two DLLs. The macro name is kept, so the five call sites are untouched.

Pin 3.14.0 at first, so this step is a no-op with unchanged test counts.

The NUnit 5 package also ships `nunit.framework.legacy.dll`. Leave it unimported, so that a classic
assert fails to compile.

## Assertions

The classic assertions moved to `NUnit.Framework.Legacy`. The two suites hold about 3,300 classic
calls in 83 files:

| API | core | client |
| --- | --- | --- |
| `Assert.AreEqual` | 1,426 | 461 |
| `Assert.IsTrue`/`IsFalse`/`True`/`False` | 680 | 193 |
| `StringAssert.*` | 122 | 42 |
| `CollectionAssert.*` | 85 | 88 |
| Other classic `Assert.*` | 143 | 83 |

`Assert.Throws`, `Catch`, `DoesNotThrow`, `Fail`, `Ignore` and `That` are unchanged.

Convert to the constraint model, `Assert.That (actual, Is.EqualTo (expected))`. This also clears
the `AreEqual (expected, actual)` argument order trap. `MessageAssert` in `core/test` is our own
helper class, and stays.

The NUnit.Analyzers code fixes do most of the work:

```bash
bazel build //:csproj
dotnet format analyzers KRPC.sln --severity info --include core/test/ --diagnostics <ids>
```

* The IDs are the classic-model rules: NUnit2001-2006, 2015, 2018, 2019, 2027-2036, 2048
  (`StringAssert`) and 2049 (`CollectionAssert`). Confirm the list against the analyzer docs.
* The fixes emit `Is.EqualTo(y)`. House style is `Is.EqualTo (y)`, so restore the space in a
  post-pass over the changed lines.
* Check the diff for doubles compared with a delta (`.Within`) and for `IsEmpty` on strings.

## NUnit 5 breaks

| Change | Impact |
| --- | --- |
| `TestDelegate` removed | Becomes `Action` in `core/test/Service/KRPC/ExpressionTest.Collections.cs` |
| `ThrowsAsync` and friends return a `Task` | Unused |
| `Platform ("NET")` now means modern .NET | Unused. `[Platform ("Win")]` is unaffected |
| `Order` deprecated | Unused |
| `Is.SameAs` drops its `object?` overload | Check the converted `AreSame` calls |

## Sequence

Each step is a commit, and each keeps the test counts equal to the baseline. The constraint model
compiles on NUnit 3, so the conversion lands before the bump.

1. Record the baseline counts and runner version from the five `csharp_nunit_test` logs.
2. Own the pin in Bazel, at 3.14.0.
3. Add NUnit.Analyzers to both builds: an `import_library` in `csharp_nunit_test`, and a
   `PackageReference` with `PrivateAssets="all"`. Fix any warning-level findings, since CI builds
   `KRPC.sln` with `-warnaserror`.
4. Convert `core/test`.
5. Convert `client/csharp/test`.
6. Bump to 5.0.0 in both builds. Fix `TestDelegate`, and delete the stale `packages.config` files
   in both test dirs (they list NUnit 3.13.3, net45).

Verify with `//:test`, a clean `bazel build //...`, `//:csproj-test`, and the Debug and Release
`KRPC.sln` builds with `-warnaserror`. The logs should show NUnitLite 5.0.0.

## Changelog impact

None, as tests only.
