# Lua: pre-generated type hints

The Lua client builds its services at connect, from `GetServices`. An editor or language server sees none of the API, and a misspelled member is found only when the script runs.

`clientgen` gains a Lua backend that writes a module per service, as the Python client's declarations do (#<python-declarations>). The client keeps building every service from the server's definitions:

1. **Annotations.** Each module carries [LuaCATS](https://luals.github.io/wiki/annotations/) annotations (`---@class`, `---@field`, `---@param`, `---@return`) and the service documentation. The rock ships the modules for the bundled services. lua-language-server then gives completion, hover documentation and type checks. Classes and services are declarations only, and the runtime is unchanged.
2. **Enumerations and structures with no connection.** The modules load with `require`, and their enumerations and structures are real values: `require('krpc.services.spacecenter').SASMode.prograde`. At connect, the client uses the module's enumeration or structure where the server's definition matches, so `==` works on a required value. Otherwise it builds its own, as it does today.

Notes:

- A mod's members work at run time, and a module out of date with the server affects only type checking.
- The annotations are comments, so the modules load on Lua 5.1 to 5.4 and LuaJIT.
- `clientgen` gains `clientgen-*-lua.txt` golden files, as for the other languages.
- The planned JavaScript client takes the same approach.
- Related: #1182 gives the built classes their documentation, for interactive help. #1202 moves the Lua API docs to sphinx-lua-ls, which can also read these annotations.

Design: `design/python-declarations.md` in the planning repo.
