# Lua 5.1: `math.huge` stands for the largest integer

On Lua 5.1 and LuaJIT, a number is a double, and the Lua client works around the integers a double
cannot hold. One workaround uses `math.huge` as a sentinel for the largest value:

* The encoder writes `math.huge` as the varint of 2^63 - 1 (`_encode_varint` in
  `client/lua/krpc/encoder.lua`).
* The decoder reads that varint back as `math.huge` (`_decode_varint` in
  `client/lua/krpc/decoder.lua`).

The sentinel makes the largest value round trip, since a double cannot hold 2^63 - 1 exactly. Its
costs:

* **A real value of 2^63 - 1 reads as infinity.** This covers any `uint32` or `uint64` result, and an
  object id, that the server sends as 2^63 - 1. Arithmetic on it gives `inf`, and comparing it with
  another large id fails.
* **`math.huge` is accepted for any unsigned argument.** Passing it for a `uint32` parameter sends a
  value out of the parameter's range, with no error from the client.

The code is the client's own, not lua-protobuf's: the client encodes and decodes values itself. On
Lua 5.4, `compat.native_integers` is true and the sentinel is not used. The conformance suite and the
client's builds run on Lua 5.4, so nothing tests this path.

Decide what Lua 5.1 should do with 2^63 - 1, then make it consistent:

* Keep the sentinel, and document it in the Lua client guide, with the values it affects.
* Or drop it, and raise the encoding error for an integer a double cannot hold, as the spec asks of a
  value out of range.

Either way, test the 5.1 behavior in the client's native unit tests, run on Lua 5.1.
