# Lua client — move to `starwing/lua-protobuf`

**Status:** proposal. No issue filed yet.

The Lua client's protobuf runtime is `djungelorm/protobuf-lua` 1.1.2, a self-maintained package pinned
as an `http_file` src.rock in `MODULE.bazel`, wired in as `@lua_protobuf//file` in
`client/lua/BUILD.bazel` and declared as the `protobuf` dependency in `client/lua/rockspec.tmpl`.
Maintaining a protobuf implementation is not core to this project;
[`starwing/lua-protobuf`](https://github.com/starwing/lua-protobuf) is the actively maintained option
and is on LuaRocks, so the pin becomes an ordinary dependency.

## This is a rewrite of the client's serialization layer, not a dependency swap

The two libraries have unrelated APIs:

* `encoder.lua` and `decoder.lua` `require 'protobuf.pb'`, `protobuf.encoder` and `protobuf.decoder`,
  and drive the low-level primitives directly — `pb.varint_encoder`, `pb.varint_decoder`,
  `pb.zig_zag_encode32/64`, `pb.zig_zag_decode32/64`. lua-protobuf exposes message-level
  `pb.encode`/`pb.decode` plus a `pb.buffer`/`pb.slice` API for the wire primitives; the mapping is
  not one-to-one and the varint framing kRPC does by hand needs rewriting against it.
* **The generated schema module changes shape.** `//protobuf:lua` generates `protobuf/KRPC.lua` as Lua
  source consumed by the old library's descriptor model, whereas lua-protobuf loads a compiled `.pb`
  descriptor at runtime (`pb.load`). That likely retires the Lua branch of the protobuf codegen in
  favor of shipping the descriptor as data — **decide this first**, since it determines whether
  `client/lua/BUILD.bazel` still needs a generation step at all.

## Two knock-on opportunities once off the old package

* **Widen the Lua version range.** The rockspec caps Lua at `>= 5.1, < 5.3`, a constraint inherited
  from the old library. lua-protobuf supports 5.1 through 5.4, so the cap can likely be lifted — a
  user-facing improvement worth a changelog entry, and worth testing across versions rather than
  assuming.
* **Compiler requirement.** lua-protobuf has a C core, so wheels/rock builds need a compiler where the
  pure-Lua package needed none. Check what this means for the Windows and macOS install paths before
  committing.

## Changelog impact

A `client/lua` entry — the dependency change is user-facing (installation), and more so if the
supported Lua range widens.
