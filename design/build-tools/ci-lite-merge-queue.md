# CI: lite path-filtered PR runs, full CI via the merge queue

**Status:** proposal — design agreed 2026-07-16, no implementation. Build-infrastructure follow-on to
the completed build-system migration ([`build-system-migration.md`](build-system-migration.md)).
**Issue:** _none yet — needs filing (`krpc/krpc`)._
**Scope:** CI only — `.github/workflows/ci.yml` (plus one-time maintainer-side settings: enable the
merge queue, require `all-checks-passed` on `main`, and create a `full-ci` label). No change to
`MODULE.bazel`, the build rules, `BUILD.bazel` files, the buildenv image, or local developer
workflow.

## Problem

`ci.yml` runs the **same ~26-job matrix on every PR push and every push to `main`.** There is no
distinction between "iterating on a PR" and "ready to merge":

* Every job runs a **cold** Bazel build/test — there is no shared Bazel action/output cache, so each
  job recompiles from scratch.
* Several jobs run on `windows-latest`. The native Windows Bazel job (`build-windows`, ~15 min,
  `continue-on-error`, deliberately excluded from the `all-checks-passed` gate) is the single worst
  per-push drag.
* Most PRs touch **one sub-component** — a single service DLL, or one client language. Running the
  full client-language matrix, docs builds, and the Windows jobs on those iteration pushes is wasted
  work.

The goal: run a **lite** subset while iterating on a PR (only the jobs whose component's files
changed, plus a cheap always-on lint), and run the **full** suite as the hard pre-merge gate.

## Goals / constraints

Agreed with the maintainer:

1. PR pushes run a reduced, path-filtered set — skip jobs for components whose files did not change.
2. The full suite runs before anything lands on `main`, as an enforced gate (not
   discipline-dependent).
3. The slow native Windows job runs **only** in full CI, never on lite PR iteration.
4. Keep a single required status check for branch protection (`all-checks-passed`) — skipped jobs
   must not turn it red.
5. No correctness regression at merge time: lite mode may skip jobs that a change could actually
   affect (see the tradeoff below); the full pre-merge run is the backstop.

## Design

### Mode: `full` = not a PR, **or** the PR carries the `full-ci` label

`full` is true for every non-`pull_request` event (`merge_group`, `push`, `workflow_dispatch`), and
also for a `pull_request` that carries the **`full-ci`** label. So a plain PR runs lite; applying the
`full-ci` label opts that PR into the full suite on demand (see below); the merge queue always runs
full regardless of labels.

```yaml
on:
  pull_request:
    branches: [main]
    # 'labeled' so applying the 'full-ci' label immediately re-triggers CI (no push needed).
    types: [opened, synchronize, reopened, labeled]   # -> LITE, unless labelled 'full-ci'
  merge_group:           # -> FULL (the real pre-merge gate)
  push:
    branches: [main]     # -> FULL
  workflow_dispatch:     # -> FULL (manual "run full now" escape hatch)
```

**Full CI is enforced by GitHub's merge queue.** A PR push runs lite, `all-checks-passed` goes green
fast, and the PR becomes mergeable *into the queue*. Adding it to the queue fires a `merge_group`
event that runs the complete suite against the prospective merge commit; only if that passes does the
commit land on `main`. Nothing merges without a green full run.

### The `setup` job — compute mode + per-component change flags

A fast first job (plain `ubuntu-latest`, **no** buildenv container) emits job outputs consumed by
every other job's `if:`.

* `full` — a shell step: `false` on `pull_request`, else `true`.
* One boolean per component, via **`dorny/paths-filter`** (pinned by commit SHA), run only
  `if: github.event_name == 'pull_request'`. On full events the outputs are unused because
  `full == 'true'` short-circuits every condition.

```yaml
setup:
  runs-on: ubuntu-latest
  outputs:
    full:         ${{ steps.mode.outputs.full }}
    foundational: ${{ steps.filter.outputs.foundational }}
    service:      ${{ steps.filter.outputs.service }}
    docs:         ${{ steps.filter.outputs.docs }}
    tools:        ${{ steps.filter.outputs.tools }}
    python:       ${{ steps.filter.outputs.python }}
    csharp:       ${{ steps.filter.outputs.csharp }}
    java:         ${{ steps.filter.outputs.java }}
    lua:          ${{ steps.filter.outputs.lua }}
    cpp:          ${{ steps.filter.outputs.cpp }}
    cnano:        ${{ steps.filter.outputs.cnano }}
    serialio:     ${{ steps.filter.outputs.serialio }}
    websockets:   ${{ steps.filter.outputs.websockets }}
    anyclient:    ${{ steps.filter.outputs.anyclient }}
  steps:
    - id: mode
      # A non-PR event is always full; a PR is full only when it carries the 'full-ci'
      # label. `labels` is absent off pull_request events, where `contains(...)` over a
      # null is false — harmless, since the event-name test already sets full=true there.
      env:
        HAS_FULL_LABEL: ${{ contains(github.event.pull_request.labels.*.name, 'full-ci') }}
      run: |
        if [[ "${{ github.event_name }}" != "pull_request" || "$HAS_FULL_LABEL" == "true" ]]; then
          echo "full=true"  >> "$GITHUB_OUTPUT"
        else
          echo "full=false" >> "$GITHUB_OUTPUT"
        fi
    - if: github.event_name == 'pull_request'
      uses: actions/checkout@v6
    - id: filter
      if: github.event_name == 'pull_request'
      uses: dorny/paths-filter@<pinned-sha>   # v3.x
      with:
        filters: |
          foundational:
            - 'protobuf/**'
            - 'core/**'
            - 'server/**'
            - 'tools/build/**'
            - 'tools/buildenv/**'
            - 'MODULE.bazel'
            - '.bazelrc'
            - '.bazelversion'
            - 'config.bzl'
            - 'maven_install.json'
            - '.github/**'
          service:    ['service/**']
          docs:       ['doc/**']
          tools:      ['tools/krpctest/**','tools/krpctools/**','tools/TestServer/**','tools/ServiceDefinitions/**']
          python:     ['client/python/**']
          csharp:     ['client/csharp/**']
          java:       ['client/java/**']
          lua:        ['client/lua/**']
          cpp:        ['client/cpp/**']
          cnano:      ['client/cnano/**']
          serialio:   ['client/serialio/**']
          websockets: ['client/websockets/**']
          anyclient:  ['client/**']
```

**The `foundational` group forces every job even on a PR.** Those paths invalidate essentially the
whole Bazel graph: everything depends on `protobuf` and `core`; services layer on `core`+`server`;
`tools/build`, `.bazelrc`, `MODULE.bazel`, `config.bzl`, the buildenv image, and the CI workflow
itself affect all builds. A change touching any of them behaves like full even on a `pull_request`.

**Alternative to the third-party action:** replace `dorny/paths-filter` with a small
`git diff --name-only <merge-base>...HEAD` bash step that sets the same `$GITHUB_OUTPUT` booleans.
Recommended primary is `dorny/paths-filter` pinned by SHA — it handles the PR merge-base robustly and
matches the repo's existing use of pinned third-party actions (`actions/checkout`, `actions/cache`).

### Per-job gating

Every gated job adds `setup` to its `needs:` and an `if:` of the form
`needs.setup.outputs.full == 'true' || needs.setup.outputs.foundational == 'true' || <component>`.

| Job | Runs when (in addition to `full` / `foundational`) |
|---|---|
| `lint` | **always** — no `if`; buildifier over the repo is seconds, keep a fast signal every push |
| `test-core` | *(foundational only — a `core` change already forces everything)* |
| `build-krpc`, `build-genfiles`, `test-service` | `service` |
| `build-csharp-sln` | *(no `if`; `needs: build-genfiles`, auto-skips when genfiles skips)* |
| `test-tools` | `tools` \|\| `python` |
| `test-client-python` | `python` |
| `test-client-csharp` | `csharp` |
| `test-client-java` | `java` |
| `test-client-lua` | `lua` |
| `test-client-cpp` | `cpp` |
| `test-client-cnano` | `cnano` |
| `test-client-serialio` | `serialio` |
| `test-client-websockets` | `websockets` |
| `build-client-{cpp,cnano}-{cmake,vcpkg}-{linux,windows}` | *(no `if`; each `needs:` its parent `test-client-*`, auto-skips when the parent skips)* |
| `build-docs-html/pdf/examples`, `test-docs` | `docs` \|\| `service` \|\| `anyclient` (docs cross-reference all services/clients — e.g. `check-documented`) |
| `build-windows` | `full` **only** (`needs.setup.outputs.full == 'true'`); keep `continue-on-error`, stays out of the gate |

Two GitHub-Actions mechanics keep the diff minimal:

* **`needs`-skip propagation.** A job whose `needs:` dependency was skipped is itself skipped. So the
  eight downstream cmake/vcpkg jobs and `build-csharp-sln` need **no** `if` — they inherit their
  parent's decision for free. Only jobs that reference `needs.setup.outputs.*` add `setup` to
  `needs`.
* **`test-tools`** gains `|| python` because `//tools/krpctest` and `//tools/krpctools` depend on
  `//client/python:krpc_lib`.

### Gate (`all-checks-passed`) — unchanged in spirit

Add `setup` to its `needs:` list. Keep `if: always()` and the existing
`contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled')` check. Skipped jobs
report `skipped` (neither `failure` nor `cancelled`), so a lite run with most jobs skipped **passes**
the gate. Because `all-checks-passed` always runs, it always reports a status in both the
`pull_request` and `merge_group` contexts, so it remains the single required status check. As today,
`build-windows` stays out of the gate.

### On-demand full CI on a PR (`full-ci` label)

Sometimes a PR wants the whole matrix before it is ready to merge — a risky refactor, a change to
something lite mode would skip (e.g. a service change that could affect client codegen), or a final
pre-merge sanity check. Applying the **`full-ci`** label to the PR sets `full = true` for that PR, so
every job runs. Because `on.pull_request.types` includes `labeled`, adding the label **immediately
re-triggers CI** with no new push needed; removing it does not downgrade an in-flight run — the next
push runs lite again. `workflow_dispatch` remains an alternative one-off full run from the Actions
tab.

The label is **additive convenience, not the gate.** The merge queue (`merge_group`) still runs full
regardless of labels and is the only thing that enforces full CI before a commit lands — a PR cannot
be labeled into or out of the merge requirement. The only setup the label needs is creating a
`full-ci` label once (repo → Issues → Labels); no branch-protection change.

### Maintainer-side settings (one-time; cannot live in the workflow)

The merge queue is what turns "full CI before merge" into a hard guarantee:

1. **Settings → Branches → branch protection for `main`:** require the status check
   **`all-checks-passed`**, and enable **"Require merge queue."**
2. Merge-queue defaults are fine. On `merge_group`, `full == 'true'`, so the complete suite
   (including `build-windows`) runs before the commit lands.

## Changes

Single file: **`.github/workflows/ci.yml`.**

* Add `merge_group:` to `on:`.
* Add the `setup` job (mode step + `dorny/paths-filter`).
* Add `needs: setup` + an `if:` to each gated job per the table.
* Change `build-windows` to `if: needs.setup.outputs.full == 'true'`.
* Add `setup` to `all-checks-passed`'s `needs:`.

No `BUILD.bazel`, `.bazelrc`, composite-action, or `docs.yml` changes. (`docs.yml` is a separate
`docs`-branch Pages deploy — untouched.)

## Validation plan

Exercise the path selection on real PRs before requiring the merge queue in branch protection:

* PR touching only `client/lua/**` → the run shows **only** `setup`, `lint`, `test-client-lua`
  executed; all other test jobs `skipped`; `all-checks-passed` green.
* PR touching only `service/SpaceCenter/**` → `build-krpc`/`build-genfiles`/`build-csharp-sln`/
  `test-service`/docs run; **client test jobs skip**; `build-windows` skips.
* PR touching `core/**` (foundational) → essentially **everything** runs (lite behaves like full).
* PR touching only `doc/**` → only docs jobs + `lint` run.
* **`full-ci` label on a lite PR** → applying the label re-triggers CI and every job now runs
  (including `build-windows`); a subsequent lite-scoped push (label removed) returns to the reduced
  set.
* **`workflow_dispatch`** on the branch → every job runs, including `build-windows`, and the gate
  passes — exercises the `full == 'true'` path without needing the queue enabled yet.
* After the maintainer enables the merge queue → a `merge_group` run executes the full suite, a PR
  cannot merge until it is green, and `build-windows` runs but (being `continue-on-error`) does not
  block the merge.

## Trade-offs and notes

* **Lite mode is best-effort, not a correctness guarantee.** Client stubs are generated from each
  `service/*:ServiceDefinitions` (via `clientgen_*`), so a service-only change *can* break client
  codegen that lite mode skips. Docs (`check-documented`) similarly reference every service/client.
  The `merge_group` full run is the backstop that catches these before merge — this is the
  explicitly accepted tradeoff, and the reason the pre-merge gate must be enforced (constraint 2/5).
* **Green-on-PR ≠ fully tested.** During iteration, `all-checks-passed` going green means "the
  affected components passed," not "the whole matrix passed." That is the intended behavior; the
  queue is where the whole matrix is enforced.
* **Two ways to force full on a PR without waiting for the queue:** apply the **`full-ci`** label (it
  re-triggers CI immediately), or run **`workflow_dispatch`** from the Actions tab. Neither changes
  the merge gate — the queue always runs full.
* **Orthogonal to the cold-build cost.** This change reduces *how many* jobs run per push; it does
  not make an individual job faster. The complementary lever — a shared Bazel `--disk_cache` / remote
  cache so jobs stop building cold — is out of scope here and worth a separate item.

## Rejected alternatives (for the full-CI trigger)

1. **Draft-PR signal** — draft PRs run lite, marking "Ready for review" runs full. Zero repo-settings
   change, but relies on maintainer discipline to ensure a full run happened before merging, and does
   not *enforce* it. Rejected in favor of the merge queue's hard gate. (Still compatible as an
   add-on if wanted later.)
2. **A label as the *gate*** — merge only once a `full-ci` label is applied and its run is green.
   Rejected: a label is manual and unenforced, so it cannot guarantee a full run happened before
   merge the way the queue does. (The `full-ci` label *is* adopted, but as an **on-demand** full-run
   supplement — see "On-demand full CI on a PR" above — not as the merge gate.)
3. **Per-target affected-test selection** (`bazel query 'rdeps(//..., set(<changed>))'`) instead of
   coarse per-component job gating. More precise, but adds a change-detection/`bazel query`
   orchestration layer the repo does not have today, and the win over job-level path filtering is
   marginal for this component layout. Rejected as disproportionate; job-level gating is the right
   altitude for the maintainer's stated goal.
