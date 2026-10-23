# Documentation structure

**Status:** done, merged as [PR #1170](https://github.com/krpc/krpc/pull/1170) for 0.8, fixing
[#1050](https://github.com/krpc/krpc/issues/1050).

## Problem

- The landing page toctree had 14 entries. pydata-sphinx-theme turns each into a header link, so
  Getting Started, Tutorials and six client languages filled the header. Extending, Protocols,
  Internals and the Changelog fell under "More".
- Each client language had its own header link, which gave the clients more weight than the game API.
- Client-agnostic behavior such as object lifetime, the auto-pilot, control loops and reference
  frames sat under Tutorials, but these pages are explanation.
- The home page was a blurb, a wall of links, then two paragraphs.

## Prior art

| Project | Theme | Header | Lesson |
|---|---|---|---|
| Apache Arrow | pydata 0.22 | Specifications, Development, Implementations | Every language sits under one entry |
| NumPy, pandas | pydata | User Guide, API reference, Development, Release notes | The theme's usual shape. The home page is an intro and a grid of section cards |
| pytest | Diataxis | Start here, How-to, Reference, Explanation | A tutorial walks through a script, while explanation describes behavior |

## Rulings

| Question | Ruling |
|---|---|
| Name of the concept section | User Guides. "Reference" is easily confused with the API reference |
| Where the API reference lives | Under each language, inside Clients |
| Name of the extending section | Developer Guide. It will later hold the client spec and be reworked internally |
| Redirects for moved pages | None. Each version is published under its own path |

## Structure

| Header | Pages |
|---|---|
| Getting Started | `getting-started` |
| User Guides | reference frames, object lifetime, auto-pilot, control loops, server side functions, boats and submarines, server performance (was `internals`) |
| Tutorials | sub-orbital flight, launch into orbit, pitch/heading/roll, parts, docking guidance, user interface, drawing |
| Clients | Python, C#, C++, C-nano, Java, Lua, other clients |
| Developer Guide | extending, communication protocols, compiling |
| Changelog | `changelog` |

- The user guide pages and their scripts move to `user-guide/` and `scripts/user-guide/`. Their
  `tutorial-` label prefix is dropped.
- The client and developer pages keep their paths, and only the toctree changes.
- The home page has a short intro and a six-language `Launch` example in tabs. Below it sit a 3x2
  card grid of the sections and a row of client cards. This adds the `sphinx-design` dependency.

## Open

- "Holding a Tick" is described in both `control-loops` and `server-performance`.
- The `parts` page moved to Tutorials, as its sections are worked examples.
