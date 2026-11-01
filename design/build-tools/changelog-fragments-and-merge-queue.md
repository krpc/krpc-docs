# Changelog fragments and a merge queue

**Status:** proposal, 2026-11-01.
**Scope:** the changelog tooling (`doc/changeloggen.py`, `doc/changelog.bzl`, `tools/release/`), the
changelog rules in the `krpc` `CLAUDE.md`, `.github/workflows/ci.yml`, and the branch protection
settings of `main`.
**Related:** [CI lite and merge queue](ci-lite-merge-queue.md), a negative result that kept full CI
on every PR. This doc adds a merge queue without changing what a PR run covers.

## Problem

Two things serialize merging. With a full CI run of 10-15 minutes, each PR waits on the one before.

| Cause | Effect |
| --- | --- |
| Every PR edits the unreleased section of the same `CHANGELOG.md` files | Most open PRs conflict once one merges. Each needs a rebase, a new changelog commit and a new CI run |
| Branch protection on `main` has `strict: true` ("Require branches to be up to date") | A PR with no conflict still needs an update and a new CI run after every merge |

The changelog rules themselves are worth keeping:

* An entry lands with its change, so `main` always carries a current changelog.
* The dev docs site (`/dev/changelog.html`) shows it to users of dev builds.
* The text is reviewed in the PR.

## Goals

1. Open PRs never conflict over the changelog.
2. Entries still land with their PR, and the dev docs show them as soon as it merges.
3. Several PRs can be queued at once. They are tested and merged without further attention, and a
   failing PR is dropped from the queue.
4. Released `CHANGELOG.md` files keep their current format.

## Design

### Fragments

A PR adds one new file to a flat directory at the repository root, `changelog.d/`, named after its
PR number and branch:

```
changelog.d/1219-single-connection.md
```

```markdown
## client/python

- Connections
  - **Breaking:** Connect over one connection, removing the `stream_port` and `stream_path`
    parameters of `connect` and `connect_local`
  - Add `handshake_timeout` and `stall_timeout` parameters to `connect` and `connect_local`
- Fix `Stream.wait` returning before the timeout on Windows

## server

- Accept clients over one connection
```

* **Component:** a `## <dir>` heading, where `<dir>/CHANGELOG.md` exists. One fragment covers every
  component the PR touches.
* **Entries:** the `CHANGELOG.md` bullet syntax, markers and wrapping rules, unchanged.
* **Topics:** a top-level bullet with sub-items is a topic, as in `CHANGELOG.md` today. Topics with
  the same text merge across fragments.
* **PR number:** taken from the file name and appended as `(#NNN)` to each entry that does not
  already end with an issue reference. A wrong prediction is fixed by renaming the file.

Two PRs only ever add different files, so fragments cannot conflict. Stacked PRs each carry their
own fragment. A PR with no user-facing change adds none.

The PR number is predicted as today, one more than the highest existing number. The fragment can
be committed with the change it describes. The final consolidated changelog commit is no longer
needed.

### Rendering unreleased entries

The unreleased section of a component is its `CHANGELOG.md` unreleased section followed by its
fragments, in PR number order.

* `doc/changeloggen.py` merges the fragments, so the dev docs show each entry once its PR merges.
  `doc/changelog.bzl` takes the fragments as one more input, through a `glob(["changelog.d/*.md"])`
  filegroup.
* `tools/release/changes.py` merges them too, so release notes previewed before folding are
  complete.
* A component with fragments and no unreleased header gets one, `## [vX.Y.Z] - unreleased`.
* Existing unreleased entries stay in `CHANGELOG.md`. Nothing is migrated.

The fragment parser and the merge live in one Python module shared by `changeloggen.py`,
`changes.py` and the fold script.

### Folding at release

A new script, `tools/release/fold-changelogs.py`, writes the fragments into the `CHANGELOG.md`
files, deletes them and strips `- unreleased` from the headers. Its output goes through a release
preparation PR, where the merged entries can be reordered and edited before tagging. The tag then
lands on a commit the queue has tested, and the release pushes no commit to `main`.

| Script | Change |
| --- | --- |
| `fold-changelogs.py` | New. Folds every fragment into its component's section, and marks the section released |
| `10-preflight.py` | Fails while `changelog.d/` holds a fragment, or a header still reads `- unreleased` |
| `30-tag.py` | Tags `main` and pushes the tag only. The finalize commit, the push of `main` and the wait for its CI run are removed |
| `publish-docs.py` | Removes `changelog.d/` from the grafted worktree, as a frozen version has no unreleased entries |

### Fragment checks

A `py_test` in `//:test` checks every file in `changelog.d/`, not only the `*.md` ones, so a
misnamed file such as `fix-wait.md` or `1240-fix.MD` cannot sit there unread:

* the name matches `^[0-9]+-[a-z0-9._-]+\.md$`
* each `##` heading names a directory with a `CHANGELOG.md`
* the body parses, with no text outside a component section

A `ci.yml` step on `pull_request` checks that fragments the PR adds carry its PR number. A wrong
prediction then fails the PR run before the PR can enter the queue.

### Failure handling

The parser is strict everywhere. A bad fragment fails with its file, line and the expected form,
and is never skipped, as a skipped fragment drops its entries from the release without notice.

| Where a bad fragment is caught | Effect |
| --- | --- |
| The PR run: the fragment test and `//doc:html` | `all-checks-passed` fails, so the PR cannot enter the queue |
| The queue run | The PR is removed from the queue. This only happens for a fragment edited by a PR ahead of it |
| `main`, after a direct push edits a fragment | The docs workflow fails, and the dev docs stop updating until a follow-up PR fixes the fragment |
| `fold-changelogs.py` and `10-preflight.py` | The release stops before tagging |

An external contributor's PR fails the same check, with the message pointing at the format in
`CONTRIBUTING.md`. As `CONTRIBUTING.md` already says for a missing entry, a maintainer may instead
push the fix to the contributor's branch. Usually that is a rename to the PR number.

### Changelog hints

The checks cannot judge whether a change is user-facing. A workflow posts hints on the PR as a
comment instead. The hints never fail CI.

| Hint | Posted when |
| --- | --- |
| No fragment. Check whether the change needs an entry | The PR changes files under a component with a `CHANGELOG.md` and adds no fragment |
| `<component>` has changes but no entry | The PR's fragment has no section for a changed component |
| `<component>` has an entry but no changes | The fragment has a section for a component the PR does not touch |
| Use a fragment in place of `CHANGELOG.md` | The PR edits a `CHANGELOG.md` and deletes no fragment. A fold PR deletes fragments, so it gets no hint |

* **One comment per PR**, found by a hidden marker (`<!-- changelog-hints -->`). Each push edits it,
  and deletes it once no hint applies.
* **A `no-changelog` label** removes the comment, for a PR that has been checked and needs no entry.
* **Changed files under a component's `test/` directory** do not count as changes to the component.

The workflow runs on `pull_request_target`, as the token of a `pull_request` run from a fork cannot
comment. It checks out the base branch only, and reads the PR's file list and fragment through the
API as data. It runs no code from the PR.

```yaml
on:
  pull_request_target:
    types: [opened, synchronize, reopened, labeled, unlabeled]
permissions:
  contents: read
  pull-requests: write
```

The logic sits in `tools/ci/changelog_hints.py`, which uses `gh` and the shared fragment parser. A
`py_test` in `//:test` covers the rules with canned file lists.

### Merge queue

GitHub's merge queue lands PRs in order:

1. A PR's own CI run passes, and it is added to the queue ("Merge when ready").
2. The queue builds a temporary branch from `main`, the PRs ahead of it, and the PR. CI runs on it
   as a `merge_group` event.
3. When that run passes, the queue fast-forwards `main` to it.
4. When it fails, the queue removes the PR, notifies its author, and rebuilds the entries behind it
   without the PR.

The queue run tests the combined tree, so two PRs that pass alone but break together are caught
before `main`. The queue also replaces the `strict` setting, as the queue run tests against the
current `main`.

`ci.yml` gains the trigger. The concurrency group already gives a `merge_group` run its own group,
as it has no `head_ref`.

```yaml
on:
  pull_request:
    branches: [main]
  merge_group:
  push:
    branches: [main]  # cache refresh only, see below
```

### No second run on `main`

The queue fast-forwards `main` to the commit its run tested, so a full run on the `push` is the same
test on the same tree. The `push` run is cut down to refreshing the shared caches.

A run restores caches saved on its own ref or on `main`. A cache saved by a `merge_group` run is
scoped to the queue's temporary branch and lost with it. Only a run on `main` can save a cache that
later PR and queue runs restore.

| Event | Jobs |
| --- | --- |
| `pull_request`, `merge_group` | All, as today |
| `push` to `main` | Each cache-saving job checks its key with `lookup-only`. On a miss it builds what fills the cache and saves it. Every other job is skipped |

The cache-saving jobs are those that use `bazel-fetch`, `bazel-fetch-windows`, the vcpkg actions
and the C++ disk cache. Most pushes hit every key, so the `push` run takes a minute or two. A key
changes with a dependency or toolchain update, and the next `push` run fills the new cache once.

A direct push to `main` gets no CI. Direct pushes are kept to files no build or test reads, such
as `README.md` and `CLAUDE.md`. A change to code always goes through a PR.

Repository settings, on `main`:

| Setting | Value |
| --- | --- |
| Require status checks to pass | `all-checks-passed`, unchanged |
| Require branches to be up to date (`strict`) | off |
| Require merge queue | on |
| Merge method | merge commit, the only one the repository allows |
| Build concurrency | 1 to start, see [Cost](#cost) |
| Status check timeout | 60 minutes |

### Cost

Each PR now takes two full runs, its own and its queue run. The organization is on the Free plan,
which allows 20 concurrent jobs. A run has 44 jobs, so one run already fills the runners, and a
build concurrency above 1 mostly queues jobs.

Throughput comes from batching instead. The merge limits let one passing run merge several queued
PRs. The size of a batch and its effect on cost are measured during [validation](#validation)
before settling on the limits.

Skipping the Windows jobs on PR runs, phase 1 of [CI lite](ci-lite-merge-queue.md#phases), halves
the cost of the PR run. It is a separate decision, revisited once the queue is in use.

## Phases

1. **Fragments.** The shared module, `changeloggen.py`, `changes.py`, `fold-changelogs.py`,
   `10-preflight.py`, `publish-docs.py`, the fragment checks and the PR number check. The changelog
   rules in the `krpc` `CLAUDE.md` change to: add a fragment, named `<PR>-<branch>.md`, with entries
   that omit `(#NNN)`. The consolidated final commit and its amend-after-push rule are removed.
   `CONTRIBUTING.md` gains the fragment format.
2. **Changelog hints.** The workflow, `changelog_hints.py`, its test and the `no-changelog` label.
3. **Merge queue.** The `merge_group` trigger, the cache-only `push` run, `30-tag.py`, then the
   repository settings. Fragments land first, as a changelog conflict would eject a PR from the
   queue.

## Validation

Phase 1:

* `//doc:html` with two fragments that share a topic and a component, plus existing unreleased
  entries → one merged section, topics merged, PR numbers from the file names.
* `fold-changelogs.py` on the same tree → the `CHANGELOG.md` files match the rendered page, and
  `changelog.d/` is empty.
* `publish-docs.py` for a released version with fragments present → no unreleased section.
* A misnamed fragment, a file without the `.md` extension, a fragment with an unknown component,
  and one that does not parse → the test and `//doc:html` both fail, naming the file and line.

Phase 2, on a fork, as `pull_request_target` runs the workflow from the base branch:

* A PR from another fork changing `service/SpaceCenter/src` with no fragment → one comment with the
  no-fragment hint.
* A push adding a fragment for `service/SpaceCenter` → the comment is deleted.
* A fragment for `server` only → the missing-section and no-changes hints.
* An edit to `client/python/CHANGELOG.md` → the fragment hint. A fold PR → no comment.
* The `no-changelog` label → the comment is deleted.

Phase 3, on a fork with the same settings:

* Queue three PRs → all merge without further action.
* Queue three PRs, the middle one failing → it is removed, the other two merge.
* Queue two PRs that pass alone but conflict semantically → the second is removed.
* Record the number of runs and the wall time for a batch of three, and set the merge limits from
  it.
* A merge with unchanged cache keys → the `push` run skips every build and finishes in minutes.
* A merge that changes `MODULE.bazel` → the `push` run saves the new repository cache, and the
  next PR run restores it.

## Trade-offs

* **Topic order follows PR order.** A topic first appears with the lowest-numbered fragment that
  uses it. The release preparation PR is where the order is curated.
* **The PR number is still predicted.** A wrong guess costs a rename and a push, caught by the PR
  run before the queue.
* **Editing an entry from another PR** means editing its fragment. That edit can conflict, though
  rarely.
* **Two CI runs per PR.** The second run is unattended, and it catches breakage between PRs.

## Rejected alternatives

| Alternative | Rejected because |
| --- | --- |
| A fragment directory per component, or a subdirectory per topic | One PR would write several files. A flat directory with one file per PR mirrors the PR |
| A random or branch-only fragment name, with the number added after the PR opens | A second commit and push after opening the PR. The prediction is usually right |
| `merge=union` in `.gitattributes` for `CHANGELOG.md` | GitHub's PR merge is not known to honor merge drivers (unverified), and a union merge can mangle the topic sub-lists |
| Changelog entries written by a bot from the PR description after merge | The text is no longer reviewed in the PR, and a bot commits to `main` |
| `strict` off with auto-merge, and no queue | Cheaper, one run per PR, and equally hands-off. Breakage between PRs reaches `main` and is fixed by a follow-up PR. Kept as the fallback if the queue's second run proves too slow |
| Changelog hints as a failing check | A change with no user-facing effect is common, and would need an override on every such PR |
| Danger or a GitHub App for the hints | An extra dependency or a hosted service. A workflow and a short script cover four rules |
| Towncrier or changesets | Their formats and per-type sections differ from the existing files. The custom parser already exists, and the change is small |
