# Move the Lua API docs to sphinx-lua-ls

Milestone: none · Labels: docs, tools, client:lua

The Lua API reference uses `sphinxcontrib-luadomain` 1.2.0, a one-maintainer package with a hand-written domain only. [sphinx-lua-ls](https://github.com/sphinx-contrib/lua-ls) is maintained in the sphinx-contrib org and supports Sphinx 8 and 9. With `lua_ls_backend = "disable"` it is a plain domain with no language server, which is all kRPC needs, since docgen writes the RST.

Swap the pin in `requirements.in` and `doc/conf.py.tmpl`, check the directive and role names docgen emits, and compare the rendered `src/lua/` pages. Low priority: luadomain works today, so do this when it breaks on a Sphinx bump.
