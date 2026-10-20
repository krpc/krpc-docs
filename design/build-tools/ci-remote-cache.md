# CI: shared Bazel remote cache

**Status:** negative result, 2026-10-14. Not built. The GitHub Actions cache is already over its
10 GB limit, so a cache needs an external service or server to run. A warm cache would cut a run
from 11-16 minutes to about 6-7, which does not justify that upkeep for a single maintainer.
Revisit if the project gains regular contributors.
**Scope:** `.github/workflows/ci.yml`, the `build-setup` and `bazel-fetch-windows` actions, and a
cache backend with its credentials. No change to BUILD files or local developer builds.
**Related:** [CI lite and merge queue](ci-lite-merge-queue.md). A cache makes most of its path
filtering unnecessary, see [below](#relation-to-ci-lite).

## Problem

Every CI job builds and tests from cold. The existing caches cover downloads only:

| Cache | Contents | Size |
|---|---|---|
| `bazel-repo-cache-<os>-<bazel>-<hash>` | the repository cache's `content_addressable/`, i.e. the downloaded archives | 1.2 GB per OS |
| `vcpkg-<hash>` | vcpkg binary packages for the cmake and vcpkg jobs | 150 MB |
| `ccache-<hash>` | the cmake jobs' compiler cache | 14 MB |

Bazel action outputs and test results are cached nowhere. A one-line change to the Lua client
recompiles the server, every service and every other client, then reruns all their tests.

Step times from a recent full run (`38532990806`), in seconds:

| Job | Container | Setup | Build | Test |
|---|---|---|---|---|
| `linux-build-docs-examples` | 43 | 27 | 368 | |
| `linux-test-client-python` | 37 | 21 | 66 | 147 |
| `linux-test-client-cpp` | 49 | 17 | 41 | 140 |
| `linux-test-service` | 40 | 15 | | 58 |
| `windows-build-docs-examples` | | 21 | 505 | |
| `windows-test-service` | | 16 | | 309 |
| `windows-test-client-cpp` | | 16 | 170 | 240 |

A full run takes 11-16 minutes of wall time. The build and test steps are the part a cache removes.
The roughly one minute of container start and setup per job stays.

## Goals

1. Reuse action outputs and passing test results across runs, jobs and branches.
2. Fork PRs read the cache. Only trusted events write it.
3. A cache hit is exactly as correct as a local rebuild.
4. Every artifact keeps its build number, on PRs and on `main`, so dev builds stay properly
   versioned.
5. Developers need no new setup. The cache is CI-only, though a maintainer may opt in.

## Blocker: the build number busts every cache key

`build-setup` rewrites `version` in `config.bzl` to `0.7.0-<count>-<sha>` on every job except
`lint`. The version reaches `csharp_assembly_info` in `core` and `server`, and from there every C#
assembly. Every assembly then depends on it: services, `ServiceDefinitions`, clientgen output,
every client, and the docs. A new commit therefore invalidates almost every action, and a cache gets
no hits across commits.

**Fix: test with the plain version, package with the build number.** The artifacts need the build
number, but the tests do not. A job that uploads an artifact runs in two stages:

1. `build-setup` leaves `config.bzl` alone. The job runs its tests and any build with no artifact,
   reading and writing the cache.
2. A new `long-version` action, split out of `build-setup`, rewrites `config.bzl`. The job then
   builds its artifact targets with `--remote_upload_local_results=false` and uploads them.

Jobs with no artifact skip stage 2. Every artifact carries the build number, as today.

Stage 2 reruns only the actions whose inputs contain the version: the C# assemblies, the
packaging steps, and Sphinx for the docs. Bazel keys an action on the digests of its inputs, so an
output that comes out byte-identical stops the rebuild there. If `ServiceDefinitions` output carries
no version, for example, clientgen is cached in stage 2 too. Stage 2 never uploads, because its
entries are unique to the commit and would only fill the cache.

Bazel stamping (`--stamp` with a `--workspace_status_command`) is the native form of stage 2. It
would need every packaging rule, the Python package metadata and the output file names reworked to
read the status file. Phase 4 revisits it if stage 2 proves slow.

## Design

### Backend

The GitHub Actions cache is the zero-infrastructure option. It is already full: 10.7 GB in use
against the 10 GB default, with the stale Bazel 9.1.1 repository caches still in it. A Bazel disk
cache in it would also restore and re-save the whole directory, several GB per job, in each of 44
jobs. Action outputs need a remote cache that serves single blobs on demand.

Local `bazel-out/k8-fastbuild/bin` is 3.5 GB, so plan for 5-10 GB per platform and image version.

| Option | Ops | Cost | Notes |
|---|---|---|---|
| Hosted cache with an open-source free tier, e.g. BuildBuddy | none | free within the tier's limits | Check the transfer limit against the measured traffic |
| `bazel-remote` on a small VPS | a server to run and patch | fixed monthly | VPS plans include a monthly transfer allowance, usually a TB or more. `bazel-remote` evicts by LRU at a size cap |
| GCS bucket as the HTTP cache | none | storage plus egress per GB | Bazel supports it natively. Egress to the Azure-hosted runners is billed per GB and grows with each run |

**Recommendation:** a hosted free tier if phase 1's measured transfer fits within it, else
`bazel-remote` on a VPS. Both expose the same `--remote_cache` endpoint, so switching changes
only the URL and the credentials.

### Configuration

Set in the rc files the CI actions already write, never in the repository's `.bazelrc`:

```
build --remote_cache=<endpoint>
build --remote_instance_name=<namespace>
build --remote_upload_local_results=<true on trusted events, false otherwise>
build --remote_download_toplevel
```

* **Namespace per toolchain.** The Linux jobs compile with the system LLVM in the buildenv image.
  The Windows jobs use the runner image's MSVC. Neither toolchain is part of Bazel's action key, so
  the namespace carries it: `buildenv-3.12.0` on Linux and `$ImageOS-$ImageVersion` on Windows. A new
  image starts an empty namespace. The Windows runner image changes about weekly, and each change
  costs one cold run.
  For a backend that ignores `--remote_instance_name`, put the namespace in the URL path.
* **Writes.** Trusted events hold the write credential: pushes to `main` and same-repository PR
  branches. Fork PRs get no secrets, so they read anonymously and upload nothing. Reads need no
  credential, or a read-only one.
* **Test results.** Bazel caches passing results and reruns a test only when its inputs change. It
  never caches a failure, so a flaky test stays visible.
* **Build without the bytes.** `--remote_download_toplevel` fetches only the requested outputs, not
  every intermediate output. The jobs that upload artifacts need their top-level outputs, which this
  mode downloads.

### Correctness

The Linux jobs run with `--spawn_strategy=standalone`, i.e. with no sandbox. An action that reads an
undeclared input still builds locally, but its cache key misses that input, and a later hit can
serve a stale output. Phase 1 guards against this:

* Build the same commit twice, each against an empty namespace, with `--execution_log_compact_file`.
  Diff the action keys. A key that differs between the two runs marks a nondeterministic action, the
  main cause of cache misses.
* Run the sandboxed strategy for one full CI run to surface undeclared inputs, then return to
  standalone if it is slower.
* Check `--incompatible_strict_action_env`, so that `PATH` and the other inherited variables cannot
  vary the keys between runner images.

## Phases

| Phase | Change | Mergeable alone |
|---|---|---|
| 0 | Split `long-version` out of `build-setup`, and run it only before the artifact build in the jobs that upload. Delete the stale repository caches. | yes, with no speedup on its own |
| 1 | Remote cache on the Linux jobs. Measure hit rate, bytes transferred, and job times, then pick the backend. | yes |
| 2 | Remote cache on the Windows jobs, namespaced by runner image. | yes |
| 3 | Revisit the repository-cache keys and the vcpkg and ccache entries against the GHA cache limit. | yes |
| 4 | If stage 2 dominates, move the build number into Bazel stamping so that only packaging depends on it. | yes |

## Expected effect

With a warm cache and a change confined to one client:

* Unaffected test-only jobs drop to container plus setup plus cache checks, about 1.5 minutes.
* Artifact jobs add stage 2, the version-dependent rebuild. For the C# chain, this is at most the
  94 s `build-krpc` build step, and less with early cutoff.
* The docs html and pdf builds rerun Sphinx in stage 2 on every commit, about 5 minutes each. They
  set the floor on wall time, at around 6-7 minutes, down from 11-16.

A change to `core`, `protobuf` or the server still rebuilds nearly everything, as it does today.
Phase 1 confirms these estimates.

## Relation to CI lite

The [CI lite](ci-lite-merge-queue.md) design selects jobs from the build graph so that unaffected
jobs skip their build and test steps. A remote cache gives the same selection per action, with no
workflow logic, on every event including pushes to `main`. A skipped job and a fully cached job cost
about the same: a runner and `build-setup`.

With a cache in place, lite mode would only skip Windows. Revisit that design once phase 2 lands.

## Rejected alternatives

1. **Bazel disk cache in the GHA cache.** The GHA cache is already over its limit. Restoring and
   saving the whole directory per job moves several GB, and immutable entries need a new key per
   save.
2. **Keep the build number in every step.** Every commit changes `AssemblyVersion`, which leaves
   cross-commit hits at near zero.
3. **Build every artifact with the plain version, plus one numbered dev build job on `main`.**
   Cheapest to cache, but PR artifacts would lose their build number.
4. **Remote execution.** Faster again, but it moves the toolchains onto someone else's workers,
   including the Windows MSVC builds. The cache alone removes most of the wasted work.
