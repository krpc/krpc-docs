# Pin luasocket to a release that builds socket.unix on Windows

The Lua client's `connect_local` uses luasocket's `socket.unix`, which luasocket builds on Windows only with [lunarmodules/luasocket#469](https://github.com/lunarmodules/luasocket/pull/469), still unmerged. The test build pins `@lua_luasocket` in `MODULE.bazel` to that PR's head (#1142). The released client depends on stock `luasocket >= 3.0`, and its docs tell Windows users to connect over TCP/IP.

Blocked on a luasocket release that includes #469. Then pin the release tag, raise the rockspec bound, and remove the Windows note under `connect_local` in `doc/src/lua/client.rst`.
