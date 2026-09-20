# Release tooling — require an issue/PR reference on every changelog entry

**Status:** proposal. No issue filed yet.

Changelog entries reference their issue or PR inline as `(#NNN)`, and the changelog generator
(`tools/krpctools/krpctools/changelog/`) turns those into `:issue:` roles, so they render as links
on the docs changelog page. The convention is not enforced and is mostly not followed.

## Problem

Of the **245 v0.6.0 entries across all `CHANGES.txt` files, 186 carry no reference**. Excluding
`krpctest` and `buildenv`, which are independently versioned and off the changelog page, that is 173
of 232. It is worst where the volume is — SpaceCenter is 95 of 134 — and some components have none at
all:

| Component | Referenced / total |
|---|---|
| SpaceCenter | 39 / 134 |
| InfernalRobotics | 0 / 6 |
| KerbalAlarmClock | 0 / 7 |
| RemoteTech | 0 / 7 |
| Lua | 0 / 2 |

## Two halves

* **Gate it.** `check_changelogs` in `tools/release/10-preflight.py` already walks exactly the right
  set of files — its `changelogs()` helper is the release-train components, matching what feeds the
  docs page — and currently only reports whether each has a section for the release tag. Extend it to
  also report entries in that section with no `#NNN`. Start as a warning listing the offenders rather
  than a hard failure: an entry legitimately has no reference when the change predates the PR workflow
  or when one entry summarizes several PRs, and a preflight that cannot be satisfied gets ignored.
* **Backfill.** Every unreferenced entry that does have a PR should get one. This is mechanical rather
  than a judgment call: `git log`/`git blame` on the entry's line in `CHANGES.txt` gives the commit
  that added it, and `gh pr list --search <sha>` gives the PR that carried it. Entries with genuinely
  no PR (direct commits to `main`) stay bare — which is also the argument for the gate being a warning
  rather than a failure.

## Open decision

Decide whether the gate applies only to the version being released or to the whole file. Only the
current version is worth enforcing; historical entries are frozen and backfilling them has no
audience.
