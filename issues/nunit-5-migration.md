# Move the C# test suites to NUnit 5

The core and C# client test suites use NUnit 3.14. NUnit 5.0.0 is out, and moves the classic assertions to `NUnit.Framework.Legacy`. About 3,300 classic assertions convert to the constraint model, mostly through the NUnit.Analyzers code fixes. `csharp_nunit_test` in rules_dotnet appends its own NUnit 3.14, so the Bazel build has to own the NUnit pin first.

Design: [nunit-5-migration.md](https://github.com/krpc/krpc-docs/blob/main/design/build-tools/nunit-5-migration.md)
