# apidoc warning when the backend is disabled and no apidoc roots are set

<!-- For https://github.com/sphinx-contrib/lua-ls. kRPC disconnects run_apidoc in doc/conf.py.tmpl
until a release fixes it; drop that workaround then. -->

With `lua_ls_backend = "disable"` and no `lua_ls_apidoc_roots`, every build prints:

```
WARNING: apidoc requested, but the language server backend is disabled [lua-ls]
```

No apidoc was requested. The warning fails a build run with `-W`. It can only be silenced with
`suppress_warnings = ["lua-ls"]`, which also hides the useful `lua-ls` warnings, such as a
reference that resolves to an object of an unexpected type.

## Reproduction

sphinx-lua-ls 3.12.1, Sphinx 9.1.1, Python 3.12.

`conf.py`:

```python
extensions = ["sphinx_lua_ls"]
lua_ls_backend = "disable"
```

`index.rst`:

```rst
.. lua:function:: f(x: number): string
```

`sphinx-build -W -b html . _build` fails with the warning above.

## Cause

`run_apidoc` in `sphinx_lua_ls/__init__.py` runs on every `builder-inited`. It checks the backend
before it looks at the roots:

```python
def run_apidoc(app):
    domain = _t.cast(sphinx_lua_ls.domain.LuaDomain, app.env.get_domain("lua"))
    if domain.config.backend == "disable":
        logger.warning(
            "apidoc requested, but the language server backend is disabled",
            type="lua-ls",
        )
        return
    for name, params in domain.config.apidoc_roots.items():
        ...
```

`domain.config.apidoc_roots` is an empty dict when `lua_ls_apidoc_roots` is not set.

## Suggested fix

Return before the backend check when there are no apidoc roots:

```python
    if not domain.config.apidoc_roots:
        return
    if domain.config.backend == "disable":
        ...
```

A build with roots configured and the backend disabled still gets the warning.
