# Move to NUnit 4.x

**Status:** proposal. No issue filed yet.

The two headless C# suites pin `NUnit` 3.14.0 — `core/test/KRPC.Core.Test.csproj` and
`client/csharp/test/KRPC.Client.Test.csproj`. NUnit 3 is no longer the maintained line; 4.x drops the
.NET Framework target and tightens the assertion model.

## The work is the assertion migration, not the version bump

NUnit 4 moves the classic assertions out of `Assert` into `ClassicAssert` (`NUnit.Framework.Legacy`),
and the two suites are almost entirely classic: **~1,190 classic calls against 9 `Assert.That`**, the
bulk of it 797 `Assert.AreEqual`, 186 `Assert.IsFalse` and 149 `Assert.IsTrue`.

Two routes:

* **Mechanical** — swap in `ClassicAssert` and add the `using`. Cheap and low-risk, but it preserves
  the argument-order footgun (`AreEqual(expected, actual)`) that the constraint model exists to fix.
* **Convert to the constraint model** — `Assert.That(actual, Is.EqualTo(expected))` throughout. NUnit
  ships a Roslyn analyzer with code fixes and there is an official NUnit3-to-NUnit4 converter, so most
  of the 1,190 sites are automatable, but the result needs reading rather than trusting.

**Prefer the constraint model, converting per-file so a bad automated rewrite is reviewable.**

## Both build paths must move together

The Bazel builds use `csharp_nunit_test` from `rules_dotnet` 0.22.1 (`core/BUILD.bazel`,
`client/csharp/BUILD.bazel`), which supplies its own NUnit independently of the `PackageReference`
versions the solution build uses — check what that rule pins before starting, since a mismatch shows
up only in one of the two builds.

## Scope

The headless C# tests only; the in-game suites are Python (`tools/krpctest`) and unaffected.
Test-only, no user-facing change.
