# Move the Lua API docs to sphinx-lua-ls

**Status:** draft issue, not filed. Docs only, can land in any release. Labels: `documentation`,
`tools`, `client:lua`.

The Lua API reference uses `sphinxcontrib.luadomain` (`doc/conf.py.tmpl`), pinned
`sphinxcontrib-luadomain==1.2.0` in `tools/build/python/requirements.in`. It replaced the
djungelorm/sphinx-lua fork in 0c7bea1fd (2023-02). The fork has had no commits since 2018 and
should be archived.

## Options

| Package | Latest | Notes |
| --- | --- | --- |
| [sphinxcontrib-luadomain](https://pypi.org/project/sphinxcontrib-luadomain/) | 1.2.0, 2026-08-29 | What we use. One maintainer, first release after a 6-year gap. Hand-written domain only |
| [sphinx-lua-ls](https://github.com/sphinx-contrib/lua-ls) | 3.12.1, 2026-09-08 | sphinx-contrib org, active. Sphinx 8–9. Full domain plus optional autodoc via EmmyLua/LuaLS |
| [sphinx-lua](https://pypi.org/project/sphinx-lua/) | 1.2.1 | Autodoc layer over sphinxcontrib-luadomain. Not relevant, since we generate the RST ourselves |

We should not write a new domain. sphinx-lua-ls already covers everything krpc needs, so any gaps
belong upstream.

## sphinx-lua-ls with the analyzer off

`lua_ls_backend = "disable"` turns it into a plain hand-written domain, with no language server
download. Directives: `module`, `currentmodule`, `class`, `method`, `classmethod`,
`staticmethod`, `function`, `attribute`, `data`, `const`, `table`, `alias`, `enum`. Roles:
`obj`, `func`, `meth`, `attr`, `class`, `mod`, `data`, `const`, `alias`, `enum`. The package
also pulls in `PyGithub` and `requests`, which the analyzer's auto-download needs.

## Migration

* `requirements.in`: swap the pin and re-lock. Update `@krpc_pypi//sphinxcontrib_luadomain` in
  `doc/BUILD.bazel`.
* `doc/conf.py.tmpl`: use the `sphinx_lua_ls` extension, set `lua_ls_backend = "disable"`, and keep
  the `lua:class` `nitpick_ignore` entries.
* Check the directive and role names the Lua docgen emits against sphinx-lua-ls's names. Rewrite the
  hand-written `:lua:attr:`/`:lua:meth:` references in `doc/src` if needed.
* Verify: nitpicky docs build, `:check-documented-lua`, and a visual diff of `src/lua/` pages.

## Not urgent

luadomain 1.2.0 works today. Do the migration when it breaks on a Sphinx bump, or when we want
`enum`/`alias` support.
