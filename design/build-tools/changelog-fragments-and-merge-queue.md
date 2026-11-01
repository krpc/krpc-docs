# Changelog fragments and a merge queue

**Status:** in progress, 2026-11-01. Phases 1-3 are implemented locally, not yet pushed or
opened as pull requests. Open: the `no-changelog` label, the branch protection settings, and the
fork validation of phases 2 and 3.
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
branch:

```
changelog.d/single-connection.md
```

```markdown
## client/python

- Connections
  - **Breaking:** Connect over one connection, removing the `stream_port` and `stream_path`
    parameters of `connect` and `connect_local` (#1219)
  - Add `handshake_timeout` and `stall_timeout` parameters to `connect` and `connect_local`
    (#1219)
- Fix `Stream.wait` returning before the timeout on Windows (#1174)

## server

- Accept clients over one connection (#1219)
```

* **Component:** a `## <dir>` heading naming a release component, below. One fragment covers every
  component the PR touches.
* **Entries:** the `CHANGELOG.md` bullet syntax, markers and wrapping rules, unchanged.
* **Topics:** a top-level bullet with sub-items is a topic, as in `CHANGELOG.md` today. Topics with
  the same text merge across fragments.
* **Name:** the branch name, with `/` replaced by `-`. Any name unique among the fragments works.
  The name carries no meaning, so the PR number is not needed before the PR opens.
* **Issue references:** written in the entry, as in `CHANGELOG.md` today. An entry may cite the PR
  or the issue it fixes.

Two PRs add different files, so fragments do not conflict apart from a name clash, below. Stacked PRs each carry their
own fragment. A PR with no user-facing change adds none.

The fragment can be committed with the change it describes. The final consolidated changelog
commit is no longer needed.

Two PRs with the same branch name, such as the web editor's `patch-1`, add the same file. GitHub
shows the second as conflicting, and renaming its fragment resolves it. A fragment stays until the
release, so a branch name reused within a release cycle collides the same way.

### Components

Fragments are for the components on the kRPC release version, the ones whose `CHANGELOG.md` has a
`## [vX.Y.Z] - unreleased` header taken from `config.bzl`. The rule is the version a component
releases on, not whether its changelog is public.

| Component | Fragments | Changelog on the docs site |
| --- | --- | --- |
| `server`, `core`, `service/*`, `client/*`, `tools/krpctools` | Yes | Yes |
| `tools/krpctest` | Yes. It releases with kRPC, and its unreleased section conflicts the same way | No |
| `tools/buildenv` | No. Its own version in `VERSION.txt`, and a change edits `CHANGELOG.md` with the version bump | No |
| `experimental/ksa` | No. Its own process, until it joins the trains after 1.0 | No |

The list lives once, in the shared module, built from `lib.changelogs()` plus `tools/krpctest`, the
set `strip_unreleased()` already covers. The heading check, the hints and the fold read it.
`changeloggen` renders the subset its `doc/BUILD.bazel` dictionary names, as today, and
`changes.py` the subset in the release notes.

After 1.0, each train's components take fragments, and the list maps each component to its train.

### Rendering unreleased entries

The unreleased section of a component is its `CHANGELOG.md` unreleased section followed by its
fragments, sorted by their content alone:

1. Fragments citing an issue or PR, by the highest `#NNN` in the file. A PR is numbered after the
   issues it fixes, so the key is usually the PR number, which gives the order the PRs were opened.
2. Then fragments with no `#NNN`, by file name.

The order is approximate. The release preparation PR is where entries are reordered by hand.

* **Topics merge by text** with the topics already in the `CHANGELOG.md` unreleased section, and
  with each other. A fragment entry under an existing topic lands at the end of that topic.
* `doc/changeloggen.py` merges the fragments, so the dev docs show each entry once its PR merges.
  `doc/changelog.bzl` takes the fragments as one more input, through a filegroup in the root
  `BUILD.bazel`, as the `doc` package cannot glob outside itself.
* `tools/release/changes.py` merges them too, so release notes previewed before folding are
  complete.
* A component with fragments and no unreleased header gets one, `## [vX.Y.Z] - unreleased`.
* Existing unreleased entries stay in `CHANGELOG.md`. Nothing is migrated.

**No fragments is the normal state after a release.** Git does not track an empty directory, so
`changelog.d/` is absent until the next PR adds a fragment. Every tool treats a missing directory as
empty. The filegroup's glob sets `allow_empty = True`, as Bazel 9 rejects an empty glob by default.

The fragment parser and the merge live in one Python module shared by `changeloggen.py`,
`changes.py` and the fold script.

### Folding at release

One release preparation PR takes `main` from the in-development version to the next one. It holds
two commits:

1. **Fold.** A new script, `tools/release/fold-changelogs.py`, writes the fragments into the
   `CHANGELOG.md` files, deletes them and strips `- unreleased` from the headers. The merged entries
   are then reordered and edited by hand, in the same commit or in commits squashed into it.
2. **Bump.** `80-bump-version.py` sets `config.bzl` to the next version and commits.

Once the queue merges the PR, `30-tag.py` tags the fold commit. The repository merges with merge
commits only, so the fold commit is on `main`'s history. `main` itself never holds the folded
changelog with the released version, so a PR merged during the release lands on the next version's
`- unreleased` section, and the release pushes no commit to `main`.

The fold commit is never the head of a CI run, as the PR run and the queue run test the bump commit
above it. The two differ only in `config.bzl`, and `20-build-and-test.py` builds and tests the
tagged tree before anything is published.

| Script | Change |
| --- | --- |
| `fold-changelogs.py` | New. Folds every fragment into its component's section, and marks the section released |
| `10-preflight.py` | Checks the commit to be tagged in place of `HEAD` of `main`: it is on `origin/main`, `changelog.d/` holds no fragment, and no header reads `- unreleased` |
| `30-tag.py` | Tags the fold commit and pushes the tag only. The finalize commit, the push of `main` and the wait for its CI run are removed |
| `80-bump-version.py` | Commits on the release preparation branch, and pushes nothing. Runs before the tag, in place of after the announcements |
| `publish-docs.py` | Removes `changelog.d/` from the grafted worktree, as a frozen version has no unreleased entries |

**Release trains, after 1.0.** Until 1.0, the release scripts cover one version, and
`experimental/ksa` releases by its own process. Once the trains split ([KSA
releases](../ksa/releases.md)), `fold-changelogs.py` and `10-preflight.py` take a train. The fold
moves only that train's sections out of each fragment, and keeps a fragment that still has sections
for another train. Preflight checks only that train's components.

### Fragment checks

A `py_test` in `//:test` checks every file in `changelog.d/`, not only the `*.md` ones, so a
misnamed file such as `fix-wait.txt` or `fix-wait.MD` cannot sit there unread:

* the name matches `^[A-Za-z0-9._-]+\.md$`
* each `##` heading names a release component
* the body parses, with no text outside a component section

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
push the fix to the contributor's branch.

### Changelog hints

The checks cannot judge whether a change is user-facing. A workflow posts hints on the PR as a
comment instead. The hints never fail CI.

| Hint | Posted when |
| --- | --- |
| No fragment. Check whether the change needs an entry | The PR changes files under a release component and adds no fragment |
| `<component>` has changes but no entry | The PR's fragment has no section for a changed component |
| `<component>` has an entry but no changes | The fragment has a section for a component the PR does not touch |
| Add the PR or issue number | An entry in the PR's fragment has no `(#NNN)` |
| `#NNN` is not related to this PR | An entry the PR adds or changes cites a number that is neither the PR, a `#NNN` in its description, nor one of its linked issues. Catches a typo or a wrong prediction |
| Use a fragment in place of `CHANGELOG.md` | The PR edits a release component's `CHANGELOG.md` and deletes no fragment. A release preparation PR deletes fragments, so it gets no hint |

* **One comment per PR**, found by a hidden marker (`<!-- changelog-hints -->`). Each push edits it,
  and once no hint applies, says the changelog looks good. A PR with no hints from the start gets
  no comment.
* **A `no-changelog` label** marks a PR that has been checked and needs no entry. The comment then
  says so.
* **Changed files under a component's `test/` directory** do not count as changes to the component.
* **Related numbers** are the PR number, every `#NNN` in the description, and the linked issues
  from the GraphQL `closingIssuesReferences` field. Only the entries the PR's diff adds or changes
  are checked, so an older fragment edited in passing is left alone.

The workflow runs on `pull_request_target`, as the token of a `pull_request` run from a fork cannot
comment. It checks out the base branch only, and reads the PR's file list, diff, description,
linked issues and fragment through the API as data. It runs no code from the PR.

```yaml
on:
  pull_request_target:
    # edited: a new description can change the related numbers
    types: [opened, synchronize, reopened, edited, labeled, unlabeled]
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
| `push` to `main` | Each cache-saving job checks its key with `lookup-only`, except the Bazel repository cache, which is restored as the C++ disk cache key fetches repositories. On a miss it builds what fills the cache and saves it. The `copy-artifacts` job copies the build artifacts. Every other job is skipped |

The cache-saving jobs are those that use `bazel-fetch`, `bazel-fetch-windows`, the vcpkg actions
and the C++ disk cache. Most pushes hit every key, so the `push` run takes a minute or two. A key
changes with a dependency or toolchain update, and the next `push` run fills the new cache once.

**Build artifacts stay on `main`'s runs.** A `copy-artifacts` job runs on the `push` only. It
finds the successful `merge_group` run of `ci` for the pushed commit, downloads its artifacts with
`actions/download-artifact` (`run-id`, `github-token`, `actions: read`), and uploads them under the
same names. A `main` run then lists the same artifacts as today, with no second build. The
`build-setup` action stamps the version from the commit, as `0.8.0-<count>-g<sha>`, so the copied
builds carry the version a build on `main` would. The
artifacts are not advertised. They are for pointing someone at a fix before it is released.

```bash
gh run list --workflow ci --event merge_group --commit "$GITHUB_SHA" --status success \
  --limit 1 --json databaseId --jq '.[0].databaseId'
```

* **With batching**, `main` moves to the last commit of the batch, which the batch's run tested.
* **A direct push** has no matching run. The job prints a notice and passes, and that `main` run has
  no artifacts.

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

Implementation notes, where the code differs from or adds to the design:

* The shared module is `tools/release/changelog.py`, exposed to Bazel as `//:changelog`. It holds
  `COMPONENTS` as a written list, as the Bazel actions cannot glob the tree. `10-preflight.py`
  checks the list against the `service/*` and `client/*` directories.
* The release scripts stay numbered in the order a release runs them: the fold is
  `01-fold-changelogs.py`, and the bump is renumbered `02-bump-version.py`.
* A fragment must sit directly in `changelog.d/`. A file in a subdirectory fails the check.
* `fold-changelogs.py` refuses to run on `main`, and checks that the folded files parse back to the
  merged entries. `10-preflight.py` and `30-tag.py` also fail on a commit with no section for the
  version, which catches a run from the bump commit.
* The Windows C++ client job leaves the matrix, as it saves the C++ cache and so runs on a push.
  The Linux CMake jobs fill a missing ccache on a push from the merge queue run's archive.

1. **Fragments.** The shared module, `changeloggen.py`, `changes.py`, `fold-changelogs.py`,
   `10-preflight.py`, `30-tag.py`, `80-bump-version.py`, `publish-docs.py` and the fragment checks. The changelog rules in the `krpc` `CLAUDE.md` change to: add a fragment named after
   the branch. The consolidated final commit and its amend-after-push rule are removed, and the
   `(#NNN)` prediction stays for the entry text. `CONTRIBUTING.md` gains the fragment format.
2. **Changelog hints.** The workflow, `changelog_hints.py`, its test and the `no-changelog` label.
3. **Merge queue.** The `merge_group` trigger, the cache-only `push` run with `copy-artifacts`,
   then the repository settings. Fragments land first, as a changelog conflict would eject a PR
   from the queue.

## Validation

Phase 1:

* `//doc:html` with two fragments that share a topic and a component, plus existing unreleased
  entries under the same topic → one merged section, with one copy of the topic.
* Fragments citing `#1230`, `#1100` with `#1228`, and no number → `#1228`, then `#1230`, then the
  unnumbered one.
* `fold-changelogs.py` on the same tree → the `CHANGELOG.md` files match the rendered page, and
  `changelog.d/` is gone.
* `//doc:html`, `changes.py`, the fragment test and `10-preflight.py` with no `changelog.d/` → all
  pass.
* A dry run of the release preparation PR on a fork → `30-tag.py` tags the fold commit, and
  `config.bzl` at the tag names the released version.
* `publish-docs.py` for a released version with fragments present → no unreleased section.
* A misnamed fragment, a file without the `.md` extension, a fragment with an unknown component,
  one for `tools/buildenv`, and one that does not parse → the test and `//doc:html` both fail, naming the file and line.

Phase 2, on a fork, as `pull_request_target` runs the workflow from the base branch:

* A PR from another fork changing `service/SpaceCenter/src` with no fragment → one comment with the
  no-fragment hint.
* A push adding a fragment for `service/SpaceCenter` → the comment says the changelog looks good.
* A fragment for `server` only → the missing-section and no-changes hints.
* An edit to `client/python/CHANGELOG.md` → the fragment hint. A release preparation PR → no comment.
* A fragment entry without `(#NNN)` → the number hint.
* Entries citing the PR, an issue named in the description and a linked issue → no hint. An entry
  citing another number → the unrelated-number hint, which goes once the description names it.
* The `no-changelog` label → the comment says the PR needs no entry. Removing it restores the hints.

Phase 3, on a fork with the same settings:

* Queue three PRs → all merge without further action.
* Queue three PRs, the middle one failing → it is removed, the other two merge.
* Queue two PRs that pass alone but conflict semantically → the second is removed.
* Record the number of runs and the wall time for a batch of three, and set the merge limits from
  it.
* A merge with unchanged cache keys → the `push` run skips every build and finishes in minutes.
* A merge, and a batch of three → the `push` run on `main` lists the artifacts of the `merge_group`
  run for the same commit. A direct push → no artifacts, and the run passes.
* A merge that changes `MODULE.bazel` → the `push` run saves the new repository cache, and the
  next PR run restores it.

## Trade-offs

* **Order follows the highest `#NNN`.** A fragment citing only an old issue sorts early, and a
  topic first appears with the earliest fragment that uses it. The release preparation PR is where
  the order is curated.
* **The tagged commit is not the head of a CI run.** It differs from the tested bump commit only in
  `config.bzl`, and the release scripts build and test it before publishing.
* **The unrelated-number hint is best effort.** An entry may rightly cite an issue the PR does not
  mention, and the hint is then ignored. A wrong number that the description also cites passes.
* **Editing an entry from another PR** means editing its fragment. That edit can conflict, though
  rarely.
* **Two CI runs per PR.** The second run is unattended, and it catches breakage between PRs.

## Rejected alternatives

| Alternative | Rejected because |
| --- | --- |
| A fragment directory per component, or a subdirectory per topic | One PR would write several files. A flat directory with one file per PR mirrors the PR |
| The PR number in the fragment name, appended to entries by the generator | The number is unknown until the PR opens, so most outside contributions fail their first run |
| Order by the commit that added each fragment | The Bazel action has no git history. It needs stamping and a deeper checkout in the docs workflow, for an order the release preparation PR curates anyway |
| `merge=union` in `.gitattributes` for `CHANGELOG.md` | GitHub's PR merge is not known to honor merge drivers (unverified), and a union merge can mangle the topic sub-lists |
| Changelog entries written by a bot from the PR description after merge | The text is no longer reviewed in the PR, and a bot commits to `main` |
| `strict` off with auto-merge, and no queue | Cheaper, one run per PR, and equally hands-off. Breakage between PRs reaches `main` and is fixed by a follow-up PR. Kept as the fallback if the queue's second run proves too slow |
| Changelog hints as a failing check | A change with no user-facing effect is common, and would need an override on every such PR |
| Hints for the other contributor rules: entry style, labels, tests | The rules guide maintainers, and a contributor need not follow them. Entry style is tidied in the release preparation PR. Where a test belongs needs an understanding of the change |
| Danger or a GitHub App for the hints | An extra dependency or a hosted service. A workflow and a short script cover five rules |
| Towncrier or changesets | Their formats and per-type sections differ from the existing files. The custom parser already exists, and the change is small |
| A full build on the `push` to `main` for its artifacts | A third full run per PR, for a build identical to the queue run's |
| A rolling `dev` pre-release on GitHub, or nightly packages | Dev builds should stay unadvertised, so users run the latest tested release. Bazel builds from source for anyone who wants `main`, and the release trains make small fix releases easy |
