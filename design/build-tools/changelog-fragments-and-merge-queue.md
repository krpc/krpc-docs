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
files and deletes them. Its output goes through a release preparation PR, where the merged entries
can be reordered and edited before tagging.

| Script | Change |
| --- | --- |
| `fold-changelogs.py` | New. Folds every fragment into its component's unreleased section |
| `10-preflight.py` | Fails while `changelog.d/` holds a fragment |
| `30-tag.py` | Unchanged. Strips `- unreleased` from the folded files |
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
| `main`, after an administrator bypasses the queue | The `push` run and the docs workflow fail, and the dev docs stop updating until a follow-up PR fixes the fragment |
| `fold-changelogs.py` and `10-preflight.py` | The release stops before tagging |

An external contributor's PR fails the same check, with the message pointing at the format in
`CONTRIBUTING.md`. As `CONTRIBUTING.md` already says for a missing entry, a maintainer may instead
push the fix to the contributor's branch. Usually that is a rename to the PR number.

The checks cannot catch three mistakes, which are left to review:

* a user-facing change with no fragment
* an entry under the wrong component
* an entry added to `CHANGELOG.md` out of habit. It still renders, but it can conflict again

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
    branches: [main]
```

Repository settings, on `main`:

| Setting | Value |
| --- | --- |
| Require status checks to pass | `all-checks-passed`, unchanged |
| Require branches to be up to date (`strict`) | off |
| Require merge queue | on |
| Merge method | merge commit, the only one the repository allows |
| Build concurrency | 1 to start, see [Cost](#cost) |
| Status check timeout | 60 minutes |

The `push` run on `main` stays. It repeats the queue run on the same tree, and covers a merge by an
administrator who bypasses the queue.

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
2. **Merge queue.** The `merge_group` trigger, then the repository settings. Fragments land first,
   as a changelog conflict would eject a PR from the queue.

## Validation

Phase 1:

* `//doc:html` with two fragments that share a topic and a component, plus existing unreleased
  entries → one merged section, topics merged, PR numbers from the file names.
* `fold-changelogs.py` on the same tree → the `CHANGELOG.md` files match the rendered page, and
  `changelog.d/` is empty.
* `publish-docs.py` for a released version with fragments present → no unreleased section.
* A misnamed fragment, a file without the `.md` extension, a fragment with an unknown component,
  and one that does not parse → the test and `//doc:html` both fail, naming the file and line.

Phase 2, on a fork with the same settings:

* Queue three PRs → all merge without further action.
* Queue three PRs, the middle one failing → it is removed, the other two merge.
* Queue two PRs that pass alone but conflict semantically → the second is removed.
* Record the number of runs and the wall time for a batch of three, and set the merge limits from
  it.

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
| Towncrier or changesets | Their formats and per-type sections differ from the existing files. The custom parser already exists, and the change is small |
