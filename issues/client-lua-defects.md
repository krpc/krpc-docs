# Lua: defects found writing the design doc

Writing the client's design doc turned up these defects. Paths are relative to `client/lua/`, and known conformance failures are in `conformance/expected-failures.txt`.

Each was confirmed by running it against a TestServer, except where marked as read from code.

* `Client:_receive_response` treats a `stream_update` as a protocol error. A public procedure returning an `Event`, such as `TestService.OnTimer` or one in a mod's service, ends the connection at the first update.
* `Types.Enum` has no `__eq`, and the decoder builds a new instance per value. A returned enumeration value never equals the named constant, a structure holding one never equals its copy, and a set of them never finds a member. `test_enum_equality` and `test_structure_equality` record the first two.
* `class.properties` stores a value on the table when a member has no setter. `vessel.met = 5` raises no error, sends nothing, and every later read returns the stored 5.
* `encoder.encode` orders dictionary keys with `tablex.sort`. Two or more enumeration, object or bool keys, or a null key beside a string, raise `attempt to compare`.
* `Client:_build_request` coerces only an argument that is not already a `List`. `List{{1, 2}}` for a list of lists raises `attempt to call a nil value (method 'iter')` in `encoder.encode`.
* `Client` has no `__close`, so `local conn <close> = krpc.connect()` raises on Lua 5.4. A program that omits `close()` ends with no `disconnect`, unlike the last release in the C++ client.
* `Connection:receive_message_data` tests `timeout < math.huge`. A NaN handshake timeout has no deadline, and blocks forever against a silent server. `doc/src/lua.rst` says a timeout that is not positive raises an error.
* `doc/src/lua.rst` says a server error starts with the server's exception. The message starts with the source position, `.../krpc/client.lua:153:`, as `Client:_invoke` raises with `error(msg)`.
* `compat.tointeger` returns its argument on Lua 5.1 and 5.2. A fractional value for an integer parameter is truncated and sent, where 5.3 and 5.4 raise an error. Confirmed on Lua 5.1.
* On Lua 5.1, `_encode_varint` writes `math.huge` as 2^63 - 1 for any unsigned parameter, and `_decode_varint` reads a real 2^63 - 1 as `inf`. Confirmed on Lua 5.1.
* A `__gc` finalizer that makes a call can run between the write and the read of another call. The finalizer's call reads the wrong response, and the connection ends with `Response with an unknown id`. Confirmed with a collection forced at that point.
* `krpc.platform.sleep` spins on `os.time()`, holds a CPU core and rounds to whole seconds. The Lua doc scripts use it with fractions such as `0.1`. Read from code.
