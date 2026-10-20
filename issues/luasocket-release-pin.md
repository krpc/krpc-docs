# Pin luasocket to a release once it builds socket.unix on Windows

**Status:** draft issue, not filed. Blocked on an upstream luasocket release. Labels: `tools`,
`client:lua`.

The Lua client's `connect_local` uses luasocket's `socket.unix`, which luasocket builds only on
unix, macOS and Haiku.
[lunarmodules/luasocket#469](https://github.com/lunarmodules/luasocket/pull/469) adds the Windows
build. It is open and unmerged. The latest luasocket release is v3.1.0, from July 2022.

The test build pins `@lua_luasocket` in `MODULE.bazel` to the PR's head commit, so the Windows CI
local socket tests run
([lua-socket-unix-on-windows.md](../design/build-tools/lua-socket-unix-on-windows.md)). The
released client depends on stock `luasocket >= 3.0`, and its docs tell Windows users to connect
over TCP/IP.

## Once a release includes #469

* Pin `@lua_luasocket` to the release tag and drop the PR comment.
* Raise the rockspec bound to that release.
* Remove the Windows note under `connect_local` in `doc/src/lua/client.rst`.

## Meanwhile

Bump the PR pin when the PR is rebased. A force-push to the PR branch does not break the pin.
GitHub keeps the commit reachable through `refs/pull/469/head`.

## Changelog impact

Lua client: one entry, "`connect_local` works on Windows with luasocket X.Y".
