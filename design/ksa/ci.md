# CI

**Status:** proposal, 2026-10-26. Part of [KSA as a first-class game](README.md).

## What CI checks for KSP today

CI has no game install. For KSP it checks:

| Check | Job (matrix entry) | Needs the game |
| --- | --- | --- |
| The mod builds against the `@ksp` stub assemblies | `build-krpc`, `linux-build-krpc` | no |
| In-game test sources pass ruff and pyright | `test-service` (`//service/...`) | no |
| Docs build, every RPC documented, spelling | `build-docs-html`, `build-docs-pdf`, `test-docs` | no |
| Doc examples compile against the KSP stubs | `build-docs-examples` | no |
| clientgen goldens | `test-tools` | no |
| The `.csproj` file lists | `linux-build-csharp-sln` | no |

The rest of CI is game-agnostic: `core`, every client against `TestServer`, the protocol harnesses,
the C and C++ package builds, and the build scripts. In-game tests are never run in CI. They are
run locally, and before a release.

## KSA in CI

KSA needs the same game-specific checks, and nothing more. Each goes into an existing job:

| Check | Joins |
| --- | --- |
| `//ksa:mod` builds against `@ksa` | `build-krpc` on Windows, `linux-build-krpc` |
| KSA in-game test sources lint | `test-service`, as `//ksp/... //ksa/...` |
| KSA docs build | `build-docs-html`, building both sites |
| KSA doc examples compile | `build-docs-examples` |
| KSA stubs generate and compile | `build-docs-examples`, as the examples compile against them |

* **No new jobs.** The job count stays where it is, and `all-checks-passed` needs no change.
* **Windows builds the KSA mod.** The StarMap release is win-x64, so Windows is the main KSA
  platform.
* **In-game tests stay local** for both games. `//ksa:test-ingame` is part of the KSA release
  checklist, as `//ksp:test-ingame` is for KSP.

## KSA changes and KSP work

A KSA-only change still runs the KSP checks. That costs little:

* **The game-specific checks are a small part of a run.** The client tests and package builds
  dominate the 11 to 16 minutes, and run for every change already.
* **The KSA additions are expected to add a minute or two** to the jobs they join. This is an
  estimate, to be measured in phase 2.
* **There is no persistent build cache**, so skipping KSP targets would need path filters.

Path filters are rejected for now. A `core` or protocol change affects both games, so a filter needs
a correct dependency map, and a wrong one skips checks silently. The required `all-checks-passed`
job would also need to treat skipped jobs as passed. Revisit only if KSA checks grow well past a few
minutes. [ci-remote-cache.md](../build-tools/ci-remote-cache.md) and
[ci-lite-merge-queue.md](../build-tools/ci-lite-merge-queue.md) record the same trade-off for the
whole run.

## Blocker

CI cannot build the KSA mod without downloadable `@ksa` stub assemblies. See the open questions in
[README.md](README.md).
