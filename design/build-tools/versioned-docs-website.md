# Versioned documentation website

**Status:** done — merged to `main` as [PR #951](https://github.com/krpc/krpc/pull/951) and
[PR #952](https://github.com/krpc/krpc/pull/952) (2026-07-16). The site is live on the `gh-pages`
branch with `0.5.4/` (stable) and `dev/` deployed and a working `switcher.json`. This doc records
the **original design**; the implementation diverged from it in one major way (see *Divergence*
below), so read the design sections as history — the code and PR history are the source of truth.
**Issue:** none was filed; the PRs are the record.

**Scope:** docs build + publish only — no change to any service/client runtime code.

Delivered in two phases:

* **Phase 1 — versioned website.** Each release built once and frozen under `gh-pages/<version>/`,
  a `dev` build tracking `main`, and a runtime version switcher reading `switcher.json` from a
  stable absolute URL so frozen builds surface newer versions without rebuilding.
* **Phase 2 — changelog page + breaking-change convention.** A unified changelog page generated
  from the per-component `CHANGES.txt` files, with `**Breaking:**` / `**Deprecated:**` item markers
  hoisted into callouts. The marker convention is documented in [`CLAUDE.md`](../../CLAUDE.md).

## Divergence from the design

The design below keeps `sphinx_rtd_theme` and adds a ~50-line hand-rolled runtime switcher shim (it
explicitly rejects pydata for that — see *Rejected alternatives* #1). **What shipped instead
switched to `pydata-sphinx-theme` 0.20.0** and used its built-in version switcher — the same
runtime-fetch design adopted here — so `doc/src/_static/version-switcher.js` and
`doc/src/_templates/layout.html` were never needed and do not exist. Versus the design:

* The switcher is configured via `html_theme_options['switcher']` (`json_url` + `version_match`),
  with `check_switcher` off (no network in the `-W` build); the old-version banner comes from
  `show_version_warning_banner`. GA and the new-tab-links script are plain static files
  (`analytics.js`, `external-links.js`), dropping `sphinxcontrib.jquery`. `doc/gen_docs_index.py`
  emits the pydata entry format: a `name` display field (`"0.5.4 (stable)"`) and absolute URLs.
* **0.5.4 was rebuilt from source** on an archive branch — grafting only the doc content inputs
  (`doc/src`, `doc/api`, `doc/order.txt`, the eight `service/*/src` trees + `core/src/Service/KRPC`,
  with `config.bzl:version` pinned to `0.5.4`) onto the current toolchain, while `core`/`server`
  stay current as build-only toolchain. This replaces the design's §4 plan of injecting the shim
  into the already-built live-site HTML: after the theme switch a frozen RTD-themed 0.5.4 would have
  been the only switcher-less version on the site. `//doc:check-documented` (with `order.txt` pinned
  to the tag) guards that the graft reproduces the 0.5.4 API faithfully.
* The subpath is selected with `--define docs_channel=dev` (a `config_setting` + `select()`) — a
  clean binary between the frozen-release default (subpath = `config.bzl` version) and rolling `dev`.
* Phase 2's changelog page covers only the 16 components on the kRPC release-version train
  (`server`, `core`, the eight `service/*`, the six `client/*`, `tools/krpctools`); `tools/krpctest`
  and `tools/buildenv` are excluded because their independent versioning corrupts the merged
  newest-first ordering.

## Problem

The docs site is **single-version**. `.github/workflows/docs.yml` triggers on a push to the `docs`
branch, builds `//doc:html` (Sphinx 9.1.0 + `sphinx_rtd_theme` → `html.zip`), unzips it into
`github-pages/`, and publishes it flat to `https://krpc.github.io/krpc` via the official
`actions/upload-pages-artifact@v3` + `actions/deploy-pages@v4`. Each deploy **fully replaces** the
site, so only the newest release is ever online. There is no `html_baseurl`, no version dropdown, and
no per-version archive.

We want, instead:

1. Docs for **every release from 0.5.4 onward** kept online, each at its own URL, plus a **`dev`**
   build tracking `main`.
2. A **version dropdown at the top of every page**; the site root defaults to the newest released
   version.
3. The site updated **whenever a PR merges to `main`** (refreshes `dev`), and a **frozen** per-version
   build produced on each release.
4. A hard constraint from the maintainer: **never rebuild old versions from source.** Sphinx and its
   extensions move on (the version is pinned in `MODULE.bazel` and updated periodically); an already
   released 0.5.4 build must not have to survive a future Sphinx upgrade to stay published or to show
   newer versions in its dropdown.

### Why the obvious approaches don't satisfy constraint 4

* **Rebuild-all tools** (`sphinx-multiversion`, `sphinxcontrib-versioning`) check out every tag and
  re-run Sphinx on each publish. That is exactly the "keep old sources buildable forever" burden we
  want to avoid.
* **The RTD theme's native version menu** is populated from `html_context['versions']` **at build
  time**. A page frozen at 0.5.4 has that list baked in and can never show a version released later —
  which would force a rebuild of 0.5.4 every time a new version ships.

## How other projects solve this

The durable pattern (mike for MkDocs, the PyData Sphinx theme's version switcher, Read the Docs) is
**build once, freeze, and switch at runtime**:

* Each version's HTML is generated **exactly once**, at release time, with whatever Sphinx is current
  then, copied into a persistent location under `/<version>/`, and never rebuilt.
* The dropdown is **not** baked into pages. Every page loads a small JS shim that fetches a **single
  `switcher.json` from a stable, absolute URL at runtime**. Regenerating that one file when a new
  version ships makes the new entry appear in the dropdown of **every already-frozen page**, with no
  rebuild.

mike states the goal directly: "once you've generated your docs for a particular version, you should
never need to touch that version again … you never have to worry about breaking changes in MkDocs."
The PyData theme documents the same requirement for its switcher: the JSON "needs to be at a stable,
persistent, fully-resolved URL (i.e., not specified as a path relative to the sphinx root of the
current doc build)," so older builds pick up newer versions.

We adopt this model, keeping `sphinx_rtd_theme` and adding our own runtime shim (the RTD theme has no
runtime switcher of its own).

## Design

### Persistent `gh-pages` branch as the archive of record

Publish via an incremental **`gh-pages` branch** (GitHub Pages set to "deploy from a branch"), not
the whole-site artifact deploy. Each deploy touches only its own subdirectory; every other version is
left byte-for-byte untouched.

```
gh-pages/
  switcher.json     <- regenerated every deploy; single source of truth for the dropdown
  index.html        <- root redirect (meta-refresh) -> newest released version
  .nojekyll
  dev/              <- rebuilt on every push to main (overwritten each time)
  0.5.4/            <- frozen at release, never rebuilt
  0.6.0/            <- frozen at release
  .../              <- one dir per release
```

Served at `https://krpc.github.io/krpc/<version>/`. `switcher.json` (fetched by the shim at the
absolute URL `https://krpc.github.io/krpc/switcher.json`) lists every version dir plus `dev`, newest
release marked preferred:

```json
[
  { "version": "0.6.0", "url": "/krpc/0.6.0/", "preferred": true },
  { "version": "0.5.4", "url": "/krpc/0.5.4/" },
  { "version": "dev",   "url": "/krpc/dev/" }
]
```

This mirrors the retired `tools/update-docs.sh`, which already knew how to check out a branch, wipe a
scope, unzip `html.zip`, and commit — we move that logic into CI and make it incremental (per-subdir)
instead of wholesale.

### Runtime dropdown

A new `doc/src/_static/version-switcher.js`, loaded on every page, does three things on load:

1. `fetch('https://krpc.github.io/krpc/switcher.json')` — **absolute** URL, never relative to the
   current build, so frozen builds always read the live list. (Known constraint, per the PyData docs:
   the fetch is blocked over `file://`; it only works when served over http. Fine for the live site
   and for `tools/serve-docs.sh`, which serves over http.)
2. Render a `<select>` at the top of the RTD content area, current version preselected.
3. On change, navigate to the **same page path** under the chosen version, falling back to that
   version's index if a `HEAD` check shows the page is absent there (renamed/removed pages across
   versions).

The current version is rendered into a `data-` attribute by `layout.html` from a new
`html_context['current_version']`, so the shim knows which entry to preselect without another fetch.

**Graceful degradation (required).** If the `switcher.json` fetch fails — offline, CORS, wrong host,
or a 404 — the shim must **not** error or show a broken control. It falls back to a **single-choice
dropdown showing only `current_version`** (or hides the control entirely). This is the normal path
for local `serve-docs.sh` (see below) and for any preview served somewhere other than
`krpc.github.io`, and it also hardens production against a transiently-missing JSON.

### `tools/serve-docs.sh` is unaffected

`serve-docs.sh` bypasses `//doc:html` — it builds `//doc:srcs` (which already includes the generated
`conf.py`) and runs `sphinx-autobuild -W -n` on the staged tree. It stays a plain **single-version**
live-reload build: the generated `conf.py` carries the genrule-baked `%VERSION%`/`%BASEURL%` defaults,
and the shim, unable to reach the live `switcher.json`, renders the single-entry fallback above. Two
consequences the implementation must honor:

* **`version-switcher.js` must be added to the `//doc:srcs` `stage_files` list** (next to
  `_static/custom.css`). serve-docs builds with `-W`, so a `html_js_files` entry with no staged file
  present would fail the build. This is not optional.
* No multi-version machinery runs locally — no archive branch, no `switcher.json` regeneration; just
  the current docs, exactly as today plus one inert `<select>`.

### Base-URL-aware build

`conf.py.tmpl` gains `html_baseurl` (for correct canonical `<link>`s per subpath) and
`html_context['current_version']`, both fed from a new build parameter alongside the existing
`%VERSION%`. `doc/BUILD.bazel` currently hardcodes `opts = {"version": version}` on `//doc:html`
(line 102) and substitutes only `%VERSION%` in the `:conf` genrule (line 94); both are parameterized
so CI can select `dev` vs a release subpath. Because `html_baseurl`/`current_version` only affect the
canonical link and a JS-readable value, a slightly-off subpath is non-fatal.

## Changes

### 1. Sphinx config — `doc/conf.py.tmpl`, `doc/BUILD.bazel`

* `conf.py.tmpl`: add `html_baseurl = '%BASEURL%'`, `html_context = {'current_version': '%VERSION%'}`,
  and `html_js_files = ['version-switcher.js']` (next to the existing `html_css_files`).
* `doc/BUILD.bazel`: extend the `:conf` genrule and the `//doc:html` `opts` to carry the subpath
  (`dev` or `<version>`) in addition to `version`. CI passes the subpath; the version itself keeps
  flowing from `config.bzl` (the tag checkout carries the right `config.bzl:version`).

### 2. Dropdown UI — `doc/src/_templates/layout.html`, `doc/src/_static/version-switcher.js` (new), `doc/src/_static/custom.css`

* `version-switcher.js` (**new**): runtime fetch of the absolute `switcher.json`, builds the
  `<select>`, path-preserving navigation with index fallback; single-entry/hidden fallback when the
  fetch fails. **Add it to the `//doc:srcs` `stage_files` list** so both the Bazel `//doc:html` build
  and `serve-docs.sh` (which builds `//doc:srcs` with `-W`) find it.
* `layout.html`: extend the existing `extrahead`/`footer` blocks (which already inject scripts) to
  emit the `current_version` data attribute. Keep the existing GA + external-link snippets.
* `custom.css`: style the dropdown at the top of the content area.

### 3. Deploy workflow — rewrite `.github/workflows/docs.yml`

Two triggers, both committing incrementally into `gh-pages` with plain git (no third-party actions),
inside the existing `buildenv` container via the `build-setup` action:

* **`on: push: branches: [main]`** → build with subpath `dev`, replace `gh-pages/dev/`.
* **`on: push: tags: ['v*']`** → build with subpath `<version>` (from the tag), write
  `gh-pages/<version>/` (frozen).
* Drop the `docs`-branch trigger.

Shared steps: `build-setup` → `bazel build //doc:html` (subpath opt set) → checkout `gh-pages` into a
worktree → `rm -rf gh-pages/<target>` and unzip `html.zip` into `gh-pages/<target>/` (siblings
untouched) → regenerate `switcher.json` (list version subdirs, semver-sort desc, mark newest release
preferred, append `dev`) and `index.html` root redirect → ensure `.nojekyll` → commit + push (skip if
no diff, as `update-docs.sh` did).

Permissions change: drop OIDC `id-token`/`pages`; the job needs `contents: write` to push the branch.
**One-time maintainer setting:** switch repo Pages source from "GitHub Actions" to
"Deploy from a branch → `gh-pages` / root".

### 4. One-time bootstrap of the 0.5.4 archive

0.5.4 is already released and predates the switcher/baseurl changes. Bootstrap once: branch from tag
`v0.5.4`, apply the `conf.py.tmpl` + `layout.html` + `version-switcher.js` + `custom.css` changes,
`bazel build //doc:html` with subpath `0.5.4`, and hand-place the output into `gh-pages/0.5.4/`. Also
build an initial `dev` and seed `switcher.json` + root redirect so the site has content on day one.
From 0.6.0 onward this is fully automatic via the tag trigger.

### 5. Process/docs

* `Release-Guide.md` step 19: replace "merge into the `docs` branch" with "push the `vx.x.x` tag; the
  docs workflow builds and freezes `/<version>/` and updates the dropdown," and note that `main`
  merges auto-refresh `/dev/`.
* Delete `tools/update-docs.sh` (superseded) and the `docs` branch (maintainer).

## Phase 2 — Changelog page + breaking-change convention

Add a **single, unified changelog page** to the docs site, generated from the per-component
`CHANGES.txt` files, and refactor how those files mark breaking changes so the page can highlight
them. Independent of Phase 1; can ship in a separate PR.

### The source files

There are 20 `CHANGES.txt` files (server, core, each `service/*`, each `client/*`, and
`tools/{buildenv,krpctest,krpctools}`). They share one simple line format — **not** rendered
markdown, so we parse rather than pass through:

```
v0.6.0
 * Fix server version reported to clients ...
 * Add Module.AllFieldsById to expose all part module field values, including those not
   visible in the UI (#858)      <- continuation lines are indented, no leading "*"

v0.5.4
 * Fix memory leaks when switching game scene (#779)
```

i.e. a `vX.Y.Z[-pre]` header line, then ` * ` bullets, with wrapped continuation lines indented and
no bullet. Issue/PR references appear inline as `(#NNN)`.

### Generator

A new generator under `tools/krpctools` (alongside `docgen`), invoked from `doc/BUILD.bazel` exactly
like the `docgen_multiple` rules that already emit `src/<lang>/*.rst` into `//doc:srcs`. It:

1. Takes the 20 `CHANGES.txt` as Bazel inputs (a `defs`-style label list) plus a path→display-name
   map (`server` → "Server", `core` → "Core", `service/SpaceCenter` → "SpaceCenter service",
   `client/python` → "Python client", `tools/krpctools` → "krpctools", …).
2. Parses each file into `component → {version → [items], with a breaking flag per item}`
   (handling the indented continuation lines).
3. Emits one `src/changelog.rst`, merged **by version, newest first** (semver-sorted, pre-releases
   ordered correctly); within each version, grouped **by component**, listing only components that
   changed in that version.
4. Escapes RST specials in item text, and converts each `(#NNN)` into a GitHub link using the
   already-enabled `sphinx.ext.extlinks` extension (add an `issue`/`pr` role to `conf.py.tmpl`) so
   references are clickable.

Wire-up mirrors the API docs: add the rule's output to the `:srcs` `stage_files` list and add
`changelog` to the `index.rst` `toctree`. Because Phase 1 freezes each version's build, a frozen
`0.5.4` site shows the changelog **as of 0.5.4** (its checkout's `CHANGES.txt`), while `dev`/latest
shows the full current history — automatically, with no special handling.

### Item markers: `**Breaking:**` and `**Deprecated:**`

Introduce two **inline markers** on changelog items, used from **v0.5.4 onward** (older entries left
exactly as-is):

```
v0.6.0
 * **Breaking:** Remove SpaceCenter.LoadSpaceCenter, superseded by setting KRPC.GameScene (#897)
 * **Deprecated:** SpaceCenter string-dict Module.Fields/Events/Actions, superseded by
   FieldList/EventList/ActionList (#859)
 * Fix server version reported to clients ...
```

* **`**Breaking:**`** — an incompatible change users must react to. The generator strips the prefix
  and **hoists** the item into a highlighted "Breaking changes" callout (a Sphinx `.. warning::`) at
  the **top of that version's section**, tagged with its component.
* **`**Deprecated:**`** — an RPC/member that still exists but should be avoided. Hoisted the same way
  into a separate, lower-severity **"Deprecated" callout** (a Sphinx `.. note::` / distinctly-styled
  admonition) just below the breaking callout. This is purely a **changelog annotation**; marking the
  RPC itself as deprecated in the API reference (a `[KRPCDeprecated]`-style attribute flowing into
  docgen and clients) is out of scope here — it's separate future work with its own GitHub issue.

Both markers keep the item **in context** in its per-component list as well, so it's both prominent
(callout at the top) and discoverable where it belongs. An item may not carry both markers; if a
change is both breaking and deprecating something, write it as `**Breaking:**` and mention the
deprecation in the text.

Absence of any marker means an ordinary entry, so every pre-0.5.4 entry renders exactly as before —
the "leave prior versions unchanged" requirement is satisfied by simply not retro-annotating them.

Document both markers in **[`CLAUDE.md`](../../CLAUDE.md)**'s changelog guidance (the existing "add entries under the
current version header" rule), so future PRs use them. This is a pure convention change — no tooling
enforces it beyond the generator's rendering.

### Phase 2 rejected alternatives

* **A `Breaking:` sub-block header per version** (group breaking items under a nested header in the
  raw file) instead of an inline per-item marker. Rejected: restructures every version block, widens
  the merge-conflict surface on files that already conflict constantly, and fights the repo rule of
  one changelog commit per PR. The inline marker keeps items in place and diff-friendly.
* **Render `CHANGES.txt` through a markdown/MyST parser and `.. include::` it verbatim.** Rejected:
  the files aren't real markdown, there's no cross-component merge or version sorting, and breaking
  changes couldn't be hoisted/highlighted.
* **A hand-maintained `changelog.rst`.** Rejected: duplicates the `CHANGES.txt` content that the
  release process already maintains, and would drift.

## Verification

1. **Shim, local static build:** `tools/serve-docs.sh`, hand-place a `switcher.json` at the served
   root; confirm the dropdown renders at the top, lists the entries, preselects the current version,
   and navigation preserves the page path (index fallback for a missing page).
2. **Build parameterization:** `bazel build //doc:html` with subpath `dev`, then `0.5.4`; unzip and
   confirm `html_baseurl`, the `current_version` data attribute, and the shim `<script>` differ/appear
   per build.
3. **Workflow dry-run (fork/branch):** push to `main`, confirm `gh-pages/dev/` updates while existing
   `/<version>/` dirs are untouched; push a throwaway `v0.0.0-test` tag, confirm a frozen
   `/0.0.0-test/` dir appears, `switcher.json` gains the entry, and the root redirect points at the
   newest release. Load two frozen versions and confirm each one's dropdown lists the full set —
   proving runtime fetch works with no rebuild.
4. **Regression:** `bazel test //doc:test` (check-documented, spelling, lint) still passes; content is
   unchanged apart from the added dropdown.
5. **`serve-docs.sh`:** `tools/serve-docs.sh` starts, the `-W -n` build succeeds (proving
   `version-switcher.js` is staged), and the page shows a single-entry (or hidden) dropdown with no
   console errors when the live `switcher.json` is unreachable.
6. **Phase 2 — changelog:** build the docs and open the generated `changelog` page; confirm versions
   are newest-first, each version groups its components, `(#NNN)` refs link to GitHub, an item marked
   `**Breaking:**` appears in the breaking callout and one marked `**Deprecated:**` in the deprecated
   callout at the top of its version (each also still inline), and pre-0.5.4 sections are
   byte-identical in wording to their `CHANGES.txt`. The `-W` build must stay clean (no RST warnings
   from generated content).

## Docs fixups

A released version's frozen build is occasionally wrong in a way worth correcting after the fact — a
typo, or a rendering bug that lives in the sources (0.5.4 shipped a number of bullet and numbered
lists indented by a single space, which the theme boxes into a greyed-out block quote). Constraint 4
forbids *routinely* rebuilding old versions, but a deliberate, maintainer-run correction is a different
thing from making every publish re-run Sphinx on every tag. So fixups are an **explicit, manual**
maintenance action, never wired into `docs.yml`.

The mechanism reuses the archive-build graft the bootstrap already relied on (see *Divergence* — 0.5.4
was rebuilt by grafting the release's doc *content* onto the current toolchain). Two pieces:

* **A `v<version>-docs` branch**, based off the `v<version>` tag, holding *only* corrections to
  the documentation **content** — the handwritten sources (`doc/src`), the API templates (`doc/api`)
  and `doc/order.txt`. It never touches the theme, the doc generators or the build rules, so
  `git diff v<version>..v<version>-docs` is a clean, reviewable list of "corrections to the frozen
  docs" and the version's API surface and prose stay otherwise frozen. The branch is created only when
  a correction is actually needed.

* **`tools/release/publish-docs.py <version>`** (in the `krpc` repo) builds the frozen site by grafting
  the content from `v<version>-docs` — or, if no such branch exists, straight from the `v<version>`
  tag, reproducing the original freeze — onto the **current** checkout's toolchain and theme. It pins
  `config.bzl:version`, drops the changelog page (as the bootstrap did), treats `doc/src/_static` and
  `doc/src/_templates` as toolchain assets restored from the current checkout (so an old theme's
  `custom.css`/`layout.html` is replaced by the current theme and footer template), carries the guarded
  `KRPC.Service.KRPC.GameScene` compile shim for grafting a pre-#897 API onto current `core`, and
  verifies the graft with `//doc:check-documented`. With `--publish <gh-pages-dir>` it replaces
  `<gh-pages-dir>/<version>/`, regenerates `switcher.json` and the root redirect via
  `doc/gen_docs_index.py`, and commits — leaving the push for the maintainer after reviewing the diff.

This splits the two kinds of staleness cleanly. **Toolchain and theme fixes** (a changed logo string, a
doc-generator rendering fix) land on the rebuilt version for free, because the build always uses the
current toolchain — no per-version work. **Content fixes** (typos, source indentation) are the commits
on the fixup branch. Rebuilding therefore picks up *every* rendering fix made since the version was
frozen, without having to enumerate them.

`tools/release/publish-docs.py` **subsumes the one-off `create-docs-0.5.4-branch.sh`** bootstrap script:
run for 0.5.4 with no fixup branch it reproduces the original freeze, and with the `v0.5.4-docs`
branch it adds the list-indentation corrections. The bootstrap script is retired.

## Trade-offs and notes

* **`gh-pages` branch grows over time.** Each release adds a frozen tree. Pruning is a documented,
  manual `git rm` of an old `/<version>/` dir. Acceptable; releases are infrequent and trees are
  static.
* **Switcher needs the live JSON to populate.** When `switcher.json` is unreachable — a `file://`
  open, offline, or any host other than `krpc.github.io` including local `serve-docs.sh` — the shim
  shows the single-entry fallback rather than the full version list. This is the intended local-dev
  behavior, not a bug.
* **Pages source change is maintainer-side.** The one-time switch to branch deploy and the initial
  bootstrap commit must be done by a maintainer with push rights.
* **`dev` is intentionally mutable.** Only `dev` is ever overwritten; all `<version>` dirs are
  write-once.

## Rejected alternatives

1. **Migrate to `pydata-sphinx-theme`** for its built-in runtime switcher. Would remove the need for a
   custom shim, but requires reworking `layout.html`/`custom.css`, re-verifying every C#/Java/Lua
   domain renders under a new theme, and a full visual redesign. Rejected: keeping `sphinx_rtd_theme`
   + a ~50-line shim is far less disruptive for the same runtime-switcher outcome. **(Reversed
   during implementation — the project switched to `pydata-sphinx-theme` after all; see
   *Divergence* at the top.)**
2. **`sphinx-multiversion` / `sphinxcontrib-versioning` (rebuild all tags on publish).** Directly
   violates constraint 4 — every publish re-runs Sphinx on every historical tag, so old sources must
   stay buildable forever. Rejected.
3. **Keep the official `upload-pages-artifact` + `deploy-pages` deploy**, reconstructing the full site
   tree from an archive branch each run (checkout archive → splice new subdir → upload whole tree).
   Preserves OIDC deploy but re-uploads the entire multi-version site on every deploy and adds moving
   parts. Rejected in favor of the simpler incremental `gh-pages` branch (maintainer preference).
4. **`peaceiris/actions-gh-pages` with `keep_files`/`destination_dir`.** Does incremental subdir
   deploys out of the box, but adds a third-party action to a repo that currently uses only official
   actions + plain scripts. Rejected: the same result is achievable with a few lines of git, matching
   the existing `update-docs.sh` idiom.
5. **Bake the version list into each build (RTD native `html_context['versions']`).** No runtime JS,
   but a frozen page can never show a version released after it was built — forcing rebuilds of old
   versions. Rejected: fails the core constraint.
