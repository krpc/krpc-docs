# Lua client: socket.unix on Windows without our own rock

**Status:** done, merged in [PR #1142](https://github.com/krpc/krpc/pull/1142) with
[Lua 5.4 and lua-protobuf](lua-5.4-and-lua-protobuf.md). The test luasocket is pinned to the head of
[lunarmodules/luasocket#469](https://github.com/lunarmodules/luasocket/pull/469), which is open and
unmerged. Moving to a release is drafted in
[issues/luasocket-release-pin.md](../../issues/luasocket-release-pin.md).

## Problem

`krpc.connect_local` opens its socket through luasocket's `socket.unix` module. luasocket builds
that module on unix, macOS and Haiku only. Windows has had AF_UNIX since Windows 10 1803, and
luasocket#469 adds the Windows build, but it has not been merged or released.

To ship the feature on Windows anyway, the Lua client carries a stopgap. None of it has been
released yet.

| Item | Where | Purpose |
|---|---|---|
| `luasocket_windows_unix.patch` | `tools/build/lua/`, applied by `@lua_luasocket` in `MODULE.bazel` | The luasocket#469 change against luasocket 3.1.0, for the hermetic test interpreter. |
| `luasocket-unix-windows` rock | `tools/build/lua/luasocket-unix-windows.rockspec.tmpl` and its genrule | Builds only `socket.unix` for Windows, with the patch inline. Published by kRPC. |
| Rockspec dependency | `client/lua/rockspec.tmpl` | `luarocks install krpc` pulls in the rock on Windows. |
| CI build | `.github/workflows/ci.yml`, linux `test-client-lua` | Generates the rockspec. Nothing builds the rock itself. |
| Error message | `client/lua/krpc/localconnection.lua` | Names the rock when `socket.unix` is missing. |
| Docs and changelog | `doc/src/lua/client.rst`, `client/lua/CHANGELOG.md` | Tell Windows users to install the rock. |

Publishing and maintaining a luasocket rock is out of proportion for a client with few users.
Those users can connect over TCP/IP until luasocket releases the change. The rock is also not on
LuaRocks yet, so as things stand `luarocks install krpc` would fail on Windows.

## Goal

 * Release nothing luasocket-related. The released client depends on stock `luasocket` only.
 * Keep Windows CI running the Lua localsocket tests, `communication-localsocket` and the end to
   end `client-localsocket`.
 * When a luasocket release includes luasocket#469, `connect_local` works on Windows with no
   client change.

The last point already holds. `localconnection.lua` requires `socket.unix` lazily, on the first
`connect_local`, so a luasocket that provides the module is picked up when it is installed.

## Design

### Test interpreter: build luasocket from the PR

The released `krpc-lua-*.zip` holds the client's Lua sources, the schema, the license files and
the rockspec. The hermetic interpreter, with luasocket linked in, is test infrastructure only. A
patched luasocket there reaches no user.

Pin `@lua_luasocket` to the head commit of luasocket#469 in place of v3.1.0 plus the patch:

```python
# luasocket#469, which builds socket.unix on Windows. Return to a release tag once one
# includes it.
http_archive(
    name = "lua_luasocket",
    build_file = "//tools/build/lua:luasocket.BUILD",
    sha256 = "<sha256 of the archive>",
    strip_prefix = "luasocket-<PR head commit>",
    url = "https://github.com/lunarmodules/luasocket/archive/<PR head commit>.tar.gz",
)
```

 * Fetch from the upstream repo, not the fork. GitHub keeps PR commits reachable through
   `refs/pull/469/head`, so the pin survives deleting the fork branch.
 * `luasocket.BUILD` needs no change. Against v3.1.0 the PR head modifies existing `.c` files and
   adds none. Confirm the `UNIX_HAS_SUN_LEN` define on macOS still holds against the PR's
   `unix.h`.
 * `linit.c` keeps registering `socket.unix` on every platform.

Alternative considered: keep `luasocket_windows_unix.patch` against v3.1.0.

| | PR pin | Patch on 3.1.0 |
|---|---|---|
| Code tested | Exactly what luasocket would merge | 3.1.0 plus our copy of the change |
| Maintenance | Bump the pin when the PR is rebased | Keep the patch in step with the PR by hand |
| Drift from users | PR is based on `master`, 76 commits past 3.1.0 (`buffer.c`, `options.c`, `tcp.c`, `http.lua`, ...) | None besides the Windows change |
| Exit | Point the pin at the release tag | Delete the patch and bump the version |

Chosen: the PR pin. It removes the duplicated patch, and CI then validates the PR itself. The
client uses only TCP connect, send, receive, `tcp-nodelay` and `socket.unix`, so the risk from the
`master` drift is small.

### Remove the user-facing stopgap

| File | Change |
|---|---|
| `tools/build/lua/luasocket-unix-windows.rockspec.tmpl` | Delete. |
| `tools/build/lua/luasocket_windows_unix.patch` | Delete. |
| `tools/build/lua/BUILD.bazel` | Drop the `luasocket-unix-windows-rockspec` genrule, `luasocket_version`, and the two `exports_files` entries. |
| `MODULE.bazel` | `@lua_luasocket` as above; no `patches`. |
| `.github/workflows/ci.yml` | Drop `//tools/build/lua:luasocket-unix-windows-rockspec` from the linux `test-client-lua` build. |
| `client/lua/rockspec.tmpl` | Drop the `platforms = { windows = ... }` dependency. |
| `client/lua/krpc/localconnection.lua` | Error names no rock: this luasocket has no `socket.unix` module, connect with `krpc.connect` instead. Update the comment above `unix_socket`. |
| `doc/src/lua/client.rst` | Replace the rock sentence under `krpc.connect_local` with a `.. note::`: luasocket does not yet build `socket.unix` on Windows, so connect with `krpc.connect` there. |
| `client/lua/CHANGELOG.md` | Drop the rock clause from the `connect_local` entry. Unreleased, so only its wording changes. |

### Caveat

Windows CI passes the localsocket tests for a feature Windows users cannot use yet. The tested
interpreter carries luasocket#469 and a user's luasocket does not. The comment on
`@lua_luasocket` and the docs note record this.

## Follow-up

When a luasocket release includes luasocket#469:

 * Point `@lua_luasocket` at the release tag.
 * Drop the Windows note from `doc/src/lua/client.rst`, and raise the rockspec's `luasocket`
   lower bound to that release if `connect_local` on Windows should be guaranteed.

If luasocket#469 is rebased before then, bump the pin to the new head commit.
