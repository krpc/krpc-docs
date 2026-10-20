# CI: lite PR runs, full CI via the merge queue

**Status:** negative result, 2026-10-14. Not built. A full run takes 11-16 minutes, and nearly every
PR comes from one maintainer who runs `//:test` and `build //...` locally first. Lite runs would
add a run of about 9 minutes before the queue's full run, which slows each merge. The slowest Linux
job is nearly as long as the slowest Windows one. Revisit if the project gains regular
contributors. Follow-on to the [build system migration](build-system-migration.md).
**Scope:** `.github/workflows/ci.yml` and one new composite action, plus one-time repository
settings: the merge queue and the required check. No change to the Bazel build.

## Problem

`ci.yml` runs the same 44 jobs, plus the `all-checks-passed` gate, on every PR push and every push to
`main`. Every job builds cold, with no shared Bazel cache.

| Group | Jobs |
|---|---|
| `lint` | 1 |
| `linux` matrix | 15 |
| Linux standalone: `build-krpc`, `build-genfiles`, `build-csharp-sln`, cpp and cnano test plus cmake and vcpkg | 9 |
| `windows` matrix | 14 |
| Windows standalone: `build-csharp-sln`, cpp and cnano cmake and vcpkg | 5 |

The 19 Windows jobs are slower than their Linux twins and add little signal while iterating. Most
PRs touch one client or the docs, yet every push runs every job.

## Goals

1. Full CI runs before every commit lands on `main`, enforced by the merge queue.
2. Windows jobs run in full CI only.
3. PR pushes run only the Linux jobs whose Bazel targets depend on a changed file.
4. Job selection follows the build graph, with no hand-maintained dependency table.
5. `all-checks-passed` stays the single required check. Skipped jobs keep it green.

## Design

### Modes

| Event | Mode |
|---|---|
| `pull_request` | lite |
| `merge_group` | full, the pre-merge gate |
| `push` to `main` | full |

```yaml
on:
  pull_request:
    branches: [main]
  merge_group:
  push:
    branches: [main]
```

* **Merge queue.** A lite run turns `all-checks-passed` green and makes the PR eligible for the queue.
  The queue runs full CI on the prospective merge commit, and the commit lands only if that passes.
* **No manual full run.** The `workflow_dispatch` trigger is removed. Before queueing, a local
  `bazel test //:test` and `bazel build //...` cover most of what full CI adds on Linux.
* **`push` to `main` stays full.** It duplicates the queue run on the same tree. It is kept as the
  record on `main` and to cover a maintainer bypassing the queue.

### `setup` job

A plain `ubuntu-latest` job with no container. It decides the mode and lists the changed files.

```yaml
setup:
  runs-on: ubuntu-latest
  outputs:
    full: ${{ steps.mode.outputs.full }}
    changed: ${{ steps.mode.outputs.changed }}
  steps:
    # The PR checkout is the merge commit, so HEAD^1..HEAD is the PR's diff against the current base
    - if: github.event_name == 'pull_request'
      uses: actions/checkout@v7
      with:
        fetch-depth: 2
    - id: mode
      env:
        EVENT: ${{ github.event_name }}
      run: |
        if [[ "$EVENT" != pull_request ]]; then
          echo "full=true" >> "$GITHUB_OUTPUT"; exit 0
        fi
        changed=$(git diff --name-only --no-renames HEAD^1 HEAD)
        # CI and Bazel configuration that every job depends on outside the target graph
        if grep -qE '^(\.github/|tools/build/|tools/buildenv/|MODULE\.bazel|\.bazelrc$|\.bazelversion$|maven_install\.json$)' <<< "$changed"; then
          echo "full=true" >> "$GITHUB_OUTPUT"; exit 0
        fi
        echo "full=false" >> "$GITHUB_OUTPUT"
        echo "changed=$(jq -cRn '[inputs]' <<< "$changed")" >> "$GITHUB_OUTPUT"
```

The forced-full list is short and stable: the workflow and its actions, the Bazel module and
toolchain config, and the build image. Every other path is judged by the target graph.

### `scope` action: each job decides from its own targets

`.github/actions/scope` takes the setup outputs and the job's Bazel targets, and outputs `run`. It
runs in the buildenv container after `build-setup`.

1. Full mode → `run=true`, no query.
2. Query `kind('source file', deps(T)) + buildfiles(deps(T))` and keep the `//` labels.
3. Convert each label to a path (`//client/cpp:src/x.cpp` → `client/cpp/src/x.cpp`).
4. `run=true` if a changed file is one of those paths, or sits in the same directory as one of them.
   At the repository root, only exact files match.
5. A failed query → `run=true`.

**Directory matching** covers three cases that exact matching misses:

* a file deleted from a glob, which the head graph no longer contains
* non-Bazel inputs next to the sources, e.g. `client/cpp/test-cmake-linux.sh` and the CMake files
* a new file in a directory with existing dependencies

`query` resolves every `select()` branch, so the dependency set is a superset of any one
configuration. The query errs toward running a job, never toward skipping one.

**Matrix entries** scope themselves from their own `build` and `test` fields. Nothing new is
declared per entry:

```yaml
linux:
  needs: setup
  steps:
    - uses: actions/checkout@v7
    - uses: ./.github/actions/build-setup
    - id: scope
      uses: ./.github/actions/scope
      with:
        full: ${{ needs.setup.outputs.full }}
        changed: ${{ needs.setup.outputs.changed }}
        targets: ${{ matrix.build }} ${{ matrix.test }}
    - if: matrix.build && steps.scope.outputs.run == 'true'
      run: bazel build ${{ matrix.build }}
    # test and upload-artifact gain the same condition
```

A job-level `if:` cannot read `matrix`, so the matrix entries skip at the step level. A skipped
entry still starts a runner and runs `build-setup`, in parallel with the others.

**Standalone jobs** pass their targets explicitly and export `run`, so a downstream job can follow:

```yaml
linux-test-client-cpp:
  needs: setup
  outputs:
    run: ${{ steps.scope.outputs.run }}
  steps:
    # checkout, build-setup
    - id: scope
      uses: ./.github/actions/scope
      with:
        full: ${{ needs.setup.outputs.full }}
        changed: ${{ needs.setup.outputs.changed }}
        targets: //client/cpp:cpp //client/cpp:test
    # build, test and upload gated on steps.scope.outputs.run

linux-build-client-cpp-cmake:
  needs: linux-test-client-cpp
  if: needs.linux-test-client-cpp.outputs.run == 'true'
```

| Job | Scope |
|---|---|
| `lint` | always runs, no scope step |
| `linux` matrix | `matrix.build matrix.test` |
| `linux-build-krpc` | the targets it builds |
| `linux-build-genfiles` | `//:csproj //:csproj-test`, plus the paths `tools/release/genfiles.py`, `KRPC.sln`, `Directory.Build.props` |
| `linux-build-csharp-sln` | follows `linux-build-genfiles` via its `run` output |
| `linux-test-client-{cpp,cnano}` | their build and test targets |
| `linux-build-client-{cpp,cnano}-{cmake,vcpkg}` | follow their parent via its `run` output |
| `windows` matrix, all `windows-*` jobs | `if: needs.setup.outputs.full == 'true'` |

`scope` takes an optional `paths` input for the few non-Bazel inputs outside their targets'
directories. The `genfiles` row is the only current use.

**Fail-safes.** A job without a scope step always runs, so a new job runs on every PR until someone
scopes it. A failed query also runs the job. The residual risk is a non-Bazel input that is missing
from `paths` and does not sit next to a dependency. The merge queue catches that case.

### Gate

`all-checks-passed` adds `setup` to its `needs` and keeps `if: always()` plus the failure or
cancelled check. Skipped jobs report `skipped`, so a lite run passes. The gate runs on every event,
including `merge_group`, so it remains the single required check.

### Repository settings

A one-time step, outside the workflow:

Branch protection on `main`: require `all-checks-passed`, enable "Require merge queue".

## What lite saves

`bazel query` over each Linux job's targets on 2026-10-14 gives the Linux jobs below for each change.
`lint` always runs, and Windows jobs never run in lite mode. "Docs" is the four docs jobs: html,
pdf, examples and test.

| Change under | Linux jobs that run |
|---|---|
| `client/serialio`, `client/websockets` | own test |
| `doc` | docs |
| `client/lua` | own test, docs except examples, benchmarks |
| `client/{cpp,cnano,java}` | own test and cmake and vcpkg, docs, benchmarks |
| `client/csharp` | own test, docs, benchmarks, `build-krpc`, genfiles and sln |
| `tools/krpctest` | `test-service`, `test-tools`, benchmarks |
| `service/*`, `client/python`, `tools/krpctools` | all except `test-core`, lua, build scripts |
| `core`, `protobuf`, `tools/ServiceDefinitions` | all except build scripts |

Path filtering pays off for client and doc PRs. A service or Python client PR runs nearly every
Linux job, because clientgen is Python and every client embeds the service stubs. For those PRs, the
gain comes from skipping Windows.

## Phases

1. **Merge queue and Windows in full only.** Add `setup` with the mode only, `merge_group`, the
   Windows `if:` conditions and the repository settings. No path filtering. This alone removes 19
   jobs from every PR push.
2. **Scope action.** Add `changed` to `setup`, the `scope` action, and the scope steps and
   conditions on the Linux jobs.

## Validation

Before requiring the merge queue:

* Push the phase 1 branch to `main` of a fork → every job runs and the gate passes.
* Phase 1 PR → no Windows job runs, and every Linux job runs.
* Phase 2 PRs, compared against the table above:
  * `client/lua` only
  * `doc` only
  * `service/SpaceCenter` only
  * `core` only
  * a file deleted from a glob
* Measure the scope step on a skipped entry: a cold `build-setup` plus the query. If the query
  fetches external repositories beyond the repository cache, record it here.

After enabling the queue, a `merge_group` run executes the full suite, and a red Windows job blocks
the merge.

## Trade-offs

* **Lite is best effort.** It follows the target graph, and so it misses effects outside the graph,
  e.g. a Windows-only failure. The merge queue is the backstop.
* **A green PR means only that the affected jobs passed.** The full matrix is proven in the queue.
* **A skipped matrix entry is not free.** It costs a runner and `build-setup`. That cost is parallel
  and small next to a build.
* **This does not make an individual job faster.** A shared Bazel disk or remote cache is the
  separate lever for cold builds.

## Rejected alternatives

1. **Hand-maintained path filters** (`dorny/paths-filter` with one boolean per component). The
   previous revision of this doc. Checking it against `bazel query` showed the hand-drawn edges were
   wrong in six places, e.g. every client depends on `service/*` and `client/python` through
   clientgen. A hand-drawn table drifts with every BUILD change.
2. **A scope table computed centrally in `setup`.** Accurate, but `setup` would need a second copy
   of every job's targets. The per-job action reads the targets where they are already written.
3. **A dynamic matrix** built by `setup` with `fromJSON`. The matrix definition would move into a
   script, and an empty matrix fails the job. Step-level skips keep the matrix as written.
4. **Draft PRs or a label as the full CI trigger.** Depends on discipline and enforces nothing.
5. **A manual full run on a PR**, by label or `workflow_dispatch`. The queue runs full CI before
   every merge, and a failure there only sends the PR back.
