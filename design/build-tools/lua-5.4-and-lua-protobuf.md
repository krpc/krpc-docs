# Lua 5.4 and lua-protobuf for the Lua client

**Status:** done, merged as [PR #1142](https://github.com/krpc/krpc/pull/1142). Left after release: archive the
`djungelorm/protobuf-lua` fork and its LuaRocks entry.

## Problem

The Lua client is pinned to Lua 5.1 by its protobuf runtime.

| Item | Today | Consequence |
|---|---|---|
| Protobuf runtime | `djungelorm/protobuf-lua` v1.1.2 (`@protoc_lua`), a fork of protoc-gen-lua | Unmaintained. Every runtime file opens with `module "protobuf.x"`, which Lua 5.2 keeps only behind a compat flag and 5.3+ removes. |
| 64-bit values | `pb.c` pushes every 64-bit varint and fixed64 with `lua_pushnumber` | A value above 2^53 loses precision, and on 5.3+ it is a float. |
| Rockspec | `"lua >= 5.1, < 5.3"` | `luarocks install krpc` refuses on 5.3 and 5.4, the version most distros ship. |
| Hermetic interpreter | Lua 5.1.5 (`@lua` in `MODULE.bazel`) | The client is never run on a current Lua. |

## Goal

 * Replace the fork with [lua-protobuf](https://github.com/starwing/lua-protobuf) **0.5.3**
   (`starwing`, rock `lua-protobuf`), the latest release. It is maintained, has a C core, and
   supports Lua 5.1-5.4 and LuaJIT.
 * Support Lua 5.1-5.4 and LuaJIT. Build and test against Lua 5.4 only.
 * Decode `int64` and `uint64` to native 64-bit integers where the Lua version has them.
 * Breaking changes are acceptable.

5.5 is out of scope. lua-protobuf's rockspec has no upper bound, but its README lists 5.4 as the
newest version.

## Design

### Schema loading

lua-protobuf loads schemas at run time, and messages are plain Lua tables. The protoc-gen-lua
plugin and `//tools/build/protobuf:lua.bzl` go away.

`protoc --descriptor_set_out` compiles `krpc.proto`, and a genrule wraps the bytes as a string
literal in `krpc/schema/KRPC.lua`. This keeps the module path, so the packaging `path_map` in
`client/lua/BUILD.bazel` changes only its source. The descriptor set is a few kilobytes and loads
with no parser at run time.

### Private pb state

lua-protobuf keeps loaded types and its options in a state object, stored once per Lua state in
the registry. `pb.state(s)` swaps it and returns the previous one.

kRPC loads `krpc.proto` into a state of its own, and swaps it in around each `pb` call:

```lua
local old = pb.state(nil)
assert(pb.load(DESCRIPTOR_SET))
pb.option('enum_as_value')
-- ...
local state = pb.state(old)
```

 * A user script that loads other schemas or sets other options leaves the client unaffected, and
   the client leaves the script unaffected.
 * The 64-bit mode lives in the state too, and `pb.slice` reads it. So the raw decoders swap the
   state as well.
 * The cost is two registry writes per call. Phase 1 measures it with `//tools/benchmarks:lua`.
   If it shows, the swap moves out to one per message instead of one per value.

### Options

Set once on the private state:

| Option | Why |
|---|---|
| `enum_as_value` | `ConnectionResponse.status` and `Type.code` are compared to numbers. Default is names. |
| `no_default_values` | Absent fields decode to `nil`, which is what the `HasField` sites test. The default for proto3 copies defaults in. proto3 does not encode an empty string, so `nil` and "unset" agree. |
| `int64_as_number` (default) | On 5.3+ with a 64-bit `lua_Integer`, pushes a native integer. Otherwise a number. |

### 64-bit integers

On 5.3+ the decoded values are exact:

| Type | Decodes to | Notes |
|---|---|---|
| `sint64` | integer | Full range. |
| `uint64` | integer | Above 2^63 - 1 it wraps to a negative integer, as Lua has no unsigned type. `math.ult` compares two of them. |

5.1 and LuaJIT have no 64-bit integer type, so there a 64-bit value stays a double, as today.
The client picks the number model once, by whether `math.type` exists.

The encoder changes to match:

 * `_encode_varint` rejects negative values today. On 5.3+, a negative `uint64` integer is a
   wrapped value above 2^63 and encodes as its bits. The check stays for `uint32`, and for every
   value on 5.1.
 * On 5.3+, a float argument for a 64-bit parameter is converted with `math.tointeger` or
   rejected. The `math.huge` special case stays for 5.1.
 * `limits.lua`: on 5.3+, `SINT64_MIN`/`SINT64_MAX` are `math.mininteger`/`math.maxinteger`,
   and `UINT64_MAX` is `-1`, the all-ones bit pattern. On 5.1 they stay the rounded doubles. The
   "Numeric Limits" section of `doc/src/lua/client.rst` describes both models.

### Client call sites

| Today (protoc-gen-lua) | With lua-protobuf | Where |
|---|---|---|
| `schema.Response()`, `message:ParseFromString(data)` | `pb.decode('krpc.schema.Response', data)` | `decoder.lua`, `client.lua` |
| `message:SerializeToString()` | `pb.encode(type_name, table)` | `encoder.lua` |
| `msg:HasField('error')` | `msg.error ~= nil` | `client.lua`, `service.lua` |
| `protobuf_type.types:add()` | table insert | `types.lua` |
| `schema.TYPE_TYPECODE_DOUBLE_ENUM.number` | `pb.enum('krpc.schema.Type.TypeCode', 'DOUBLE')`, resolved once into `Types` | `types.lua`, `init.lua` |
| `pb.varint_encoder`, `pb.zig_zag_encode*`, `pb.struct_pack` | `pb.buffer` `pack` with `v`, `j`/`J`, `f`/`F` | `encoder.lua` |
| `pb.varint_decoder`, `pb.zig_zag_decode*`, `pb.struct_unpack` | `pb.slice` `unpack` with `v`, `j`/`J`, `U`, `f`/`F`, and `@`/`*` for the cursor | `decoder.lua` |

The encoder and decoder hot paths use the raw functions, so this is the bulk of the rewrite. It
keeps the small-varint cache and the position arithmetic in `decoder.lua` intact.
`MessageType.lua_type` changes from a generated class to a message type name.

### Toolchain

| File | Change |
|---|---|
| `MODULE.bazel` | `@lua` -> latest 5.4.x. Drop `@protoc_lua`, add `@lua_protobuf` at 0.5.3. |
| `tools/build/lua/lua.BUILD` | 5.4 source layout. Same exclusions minus `print.c`. Keep `LUA_USE_POSIX`. |
| `tools/build/lua/linit.c` | Rewrite against 5.4's `linit.c`: `luaL_requiref` for the standard libraries, and `LUA_PRELOAD_TABLE` from the registry in place of `LUA_GLOBALSINDEX`. Preload `pb` in place of `protobuf.pb`. |
| `tools/build/lua/protobuf_lua.BUILD`, `protobuf_lua_endian.patch` | Removed. New `lua_protobuf.BUILD`: one `cc_library` for `pb.c`. `protoc.lua` is not needed. |
| `//protobuf:lua` | Descriptor-set genrule in place of `protobuf_lua`. |
| `.luacheckrc` | `std = "min"`, the globals common to 5.1-5.4 and LuaJIT. See [Version support](#version-support). |
| `client/lua/rockspec.tmpl` | `"lua >= 5.1, < 5.5"`, and `"lua-protobuf >= 0.5.3"` in place of `"protobuf"`. |

luasocket 3.1, LuaFileSystem 1.9, penlight, luaunit and luacheck already support 5.4.

### Version support

The client supports 5.1-5.4 and LuaJIT, but the build tests only 5.4. The client has few users,
so a 5.1 or LuaJIT bug is fixed when it is reported. LuaJIT implements the Lua 5.1 language, so
code that runs on 5.1 runs on LuaJIT.

The version-specific code is kept small, and lint checks it:

 * luacheck's `min` std allows only globals common to every supported version. It flags `unpack`,
   `loadstring` and `math.type` used on their own.
 * The shims live in one place, `krpc/compat.lua`: `table.unpack or unpack`, a `load` that falls
   back to `loadstring`, and the number-model flag. The module is the one luacheck exception.
 * Everything else uses only what 5.1 and 5.4 share.

## Phases

### Phase 1: lua-protobuf on 5.1

Swap the runtime and the schema rule, add the private state, and rewrite the call sites. The
interpreter stays 5.1, so 64-bit values stay doubles.

Done when `//client/lua:test` passes, and `//tools/benchmarks:lua` shows no regression from the
state swap. This phase stands alone if the rest stalls: it removes the unmaintained fork.

### Phase 2: Lua 5.4

Interpreter, `linit.c`, `krpc/compat.lua`, native 64-bit integers, `limits.lua` and the doc,
the luacheck std, and the rockspec range.

Done when `//client/lua:test` passes on 5.4, with tests for `sint64` and `uint64` at their
extremes. `luarocks make` on a stock 5.4 install connects to a TestServer. Before merging, run
the unit tests once by hand on 5.1, the last time the 5.1.5 build is available.

## Changelog impact

 * Phase 1: an entry for the dependency change from `protobuf` to `lua-protobuf`, which luarocks
   users see.
 * Phase 2: "Supports Lua 5.3 and 5.4", and a `**Breaking:**` entry for 64-bit values decoding to
   integers on 5.3+, with `uint64` above 2^63 - 1 as negative.

## Open questions

 * lua-protobuf has fixes on master since 0.5.3, including a recursion depth limit for message
   decoding. Pin a commit in Bazel if one of them matters, and bump to the next release when it is
   tagged.
 * Archive the `djungelorm/protobuf-lua` fork and its luarocks entry after Phase 1 ships.
