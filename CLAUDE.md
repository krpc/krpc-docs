# CLAUDE.md

`krpc-docs` — developer planning repo for [kRPC](https://github.com/krpc/krpc): design docs
and planning notes that do not ship with the mod.

 * Nothing that ships in `krpc` may reference this repo. `krpc` code, comments and docs stand alone.

## Layout

 * `design/` — one doc per feature/issue, filed by area: `autopilot/`, `protocol/`, `services/`,
   `build-tools/`. Docs spanning all areas (audits, sweeps) sit in `design/` itself.

## Tracking work

 * Work is tracked on GitHub — issues and pull requests on [`krpc/krpc`](https://github.com/krpc/krpc).
   This repo holds the design, not the status: there is no planned/completed work index here.
 * A GitHub issue should point to the relevant design doc if there is one, and each design doc should
   link its issue or PR.

## Writing docs here

These are **design** docs — how a feature is meant to work, decided before it is built.

 * Give each doc a status line near the top: proposal, in progress, done (with the PR), or negative
   result.
 * **Reference issues and PRs by number, never commit SHAs or branch names.** Branches are deleted
   after merge and SHAs vanish on squash/rebase, so both go stale fast; issue and PR numbers are
   stable. When a branch has landed, cite the PR that merged it, not the branch or its commits. If
   you must describe individual commits, use their messages, not their hashes.
 * Keep a doc in step with `krpc` while its feature is being built — say which parts landed, which
   are still open, and where the implementation diverged from the design.
 * Once a feature is fully implemented and merged, treat its doc as a **historical record of the
   design, not a description of the code**. The `krpc` docs and PR history are the source of truth;
   do not update a finished doc to track later changes, and do not cite one as current behavior.
 * Break large problems into phases, each implementable and mergeable on its own.
 * Favor summary tables and bullet lists over prose. Cut anything that does not change a decision.
 * Write cross-references as markdown links, relative to this repo — these files are read on GitHub.
 * Use American English spelling, matching `krpc`.

## Commits

 * One thing per commit.
 * Short message: single-line summary, then one or two short paragraphs.
 * No "Authored by" / `Co-Authored-By` lines.
 * Push directly to main — no PRs required.