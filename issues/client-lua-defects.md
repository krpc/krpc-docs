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
* `krpc.platform.sleep` spins on `os.time()`, holds a CPU core and rounds to whole seconds. The Lua doc scripts use it with fractions such as `0.1`. Read from code. Fixed by PR #1323.

## From the parity audit and the client guide rewrite

Still open from the client API parity audit (2026-07-21) and the client guide rewrite (2026-10-29), re-checked against `main` on 2026-11-09.

* **The encoder does not check a value against its parameter.** An enumeration takes any number (`test_undeclared_enum_value`), a number out of its type's range is sent (`test_out_of_range[...]`), and arguments past the last parameter are dropped (`test_too_many_arguments[...]`).
* **A `uint64` above the `sint64` range reads as negative** (`test_default_values[uint64-extremes]`), as Lua integers are signed 64-bit. This is a limit of the language, so it belongs in `unsupported.txt`, not `expected-failures.txt`. The guide's Numeric Limits note describes it.
* **No stall timeout** (`test_stall`). The guide leaves it out until the API exists.
* **A refusal's status and a disconnect's reason are only in the message** (`test_handshake_refused[*]`, `test_handshake_disconnect[known]`), and RPC errors carry only a message (`test_exception_name`). The guide already describes the fixed behavior.

## From the client errors review

Found reviewing the `client-errors` branch (2026-11-11). Each predates it.

* **A structure defined twice in the service definitions is accepted** (`test_malformed_definitions[structure-twice]`). Python raises the connection error at connect.
* **A failed transport connect leaves the socket open.** `connect_using` in `krpc/init.lua` closes the transport when the handshake fails, but not when `transport:connect()` fails, so the socket lasts until the garbage collector finalizes it.
* **The reason for `test_undefined_type[enumeration-default]` in `conformance/expected-failures.txt` is stale.** It says connecting raises the connection error, and with `--runxfail` the test fails as the member using the undefined enumeration is exposed.
