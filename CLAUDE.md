# CLAUDE.md

`krpc-docs` — developer planning repo for [kRPC](https://github.com/krpc/krpc): design docs
and planning notes that do not ship with the mod.

 * Nothing that ships in `krpc` may reference this repo. `krpc` code, comments and docs stand alone.

## Layout

 * `design/` — one doc per feature/issue, filed by area: `autopilot/`, `protocol/`, `services/`,
   `build-tools/`. Docs spanning all areas (audits, sweeps) sit in `design/` itself.
 * `PLANNED_WORK.md`, `COMPLETED_WORK.md` — the work index.

## Planned and completed work

 * Group `PLANNED_WORK.md` items by target release, where possible.
 * Link a GitHub issue or PR (`krpc/krpc`) on every item.
 * GitHub issues should point to the relevant design doc if there is one.
 * On completion, move the section to `COMPLETED_WORK.md`, condensed to one line: what was done,
   the PR, and the design doc if there is one. Newest first.

## Writing docs here

These are **design** docs — how a feature is meant to work, decided before it is built.

 * Give each doc a status line near the top: proposal, in progress, done (with the PR), or negative
   result.
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