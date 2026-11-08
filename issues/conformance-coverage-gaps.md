# Conformance: coverage gaps found writing the client design docs

Writing a design doc for each client turned up behavior the conformance suite does not check, including several real client defects it cannot see. Those defects are in the client defects drafts, such as [client-design-shared-defects.md](client-design-shared-defects.md). This issue covers the tests.

Each gap below was checked against `client/conformance/tests/`. Where a client is named, its behavior was reported from running it or reading its code. A new test that fails goes in that client's `expected-failures.txt`, with the fix tracked separately.

## Tests that check too little

| Test | Gap | Effect |
|---|---|---|
| `test_calls.py::test_abandoned_id`, `test_concurrency.py::test_interrupted_wait` | `error()` is called with no check of the kind | A wrong error type passes |
| `test_connection.py::test_close_twice` | Checks only that no error is raised | C-nano closes the descriptor twice and ignores `EBADF` |
| `test_values.py::test_structure_equality` | Lua lists the test with no parameters, for its enum field | The other fields go unchecked on Lua |
| `test_streams.py::test_undecodable_value` | The stream has a value before the bad update | A first value that fails to decode is untested. Python's `Stream.__call__` then blocks silently |
| `test_connection.py::test_malformed_size` | The prefix arrives alone | A malformed prefix after a buffered message is untested. Python's reader thread dies with the connection not failed |
| `test_streams.py::test_hash`, `test_equality`, and the same in `test_events.py` | They compare copies, and two adds on one connection | Equal stream ids on connections to two servers are untested. Java's `hashCode` and `equals` disagree there |
| `test_concurrency.py::test_blocked_callback`, `test_callbacks_run_off_the_caller` | Their text says a callback gets the latest value. `test_streams.py::test_callback` says no value is skipped | The requirement is stated both ways, and `test_blocked_callback` cannot tell them apart |

The Lua testee picks the `CONNECTION` kind from `conn._error` (`testee.lua`), as Lua errors are strings. An error kind on Lua therefore reflects the connection's state.

## Paths no test runs

| Path | Why | Fix |
|---|---|---|
| Streams and events over websockets | The websockets testee reports `core` only | Extend the testee, or wait for a websockets client |
| `test_concurrency.py::test_wait_holding_another` | `@skip` in C++, C#, Java and Python | Follows a fix for the stalled dispatcher thread |
| C-nano collections in `test_codec.py` | 9 expected failures are types the testee has no codec for | Add the types to the testee |
| Leaks in C-nano | The testee leaks what it allocates | Free results, then run under LSan |
| Failure while building a call in C-nano | A partly filled `krpc_schema_ProcedureCall`, a bad position and a failed allocation have native tests only, from #1267, as the testee has no way to make them fail | Add a testee command, or a failing allocator, and move the tests to the suite |
| Lua versions other than 5.4 | Conformance runs on 5.4 only, and the client supports 5.1 to 5.4 and LuaJIT | Run the suite on 5.1 |
| A serial port in a terminal's default mode | The harness's `socat` ports are `raw` | Add a cooked port case, or set the mode in the client |

## Requirements to add

These state behavior the spec already implies:

 * A very large finite timeout works. Java overflows `Duration.toNanos`.
 * A `Get` or `Wait` in a callback call other than the first, and across a connection failure. `test_first_call_waits` covers the first call only. C# hangs on `Get` in a callback that adds a stream.
 * A close while a callback waits on a user lock. `test_close_while_callback_waits` covers stream conditions only.
 * A response whose `Error` message fails to parse. C-nano reports `KRPC_ERROR_RPC_FAILED`.
 * An event nested in a returned value, with its first update sent alongside the response. Python drops that update.
 * Dictionary keys other than strings. `test_codec.py` and `test_values.py` use only string and null keys. Lua cannot sort enumeration, object or bool keys.
 * An interrupt that arrives during a close. `test_close_interrupted` has it pending before the close starts.
 * Which thread runs an end callback, beyond the fatal error tests.

## Native tests, outside this suite

These are one client's own API, so they belong in `client/<client>/test`:

 * C-nano: reusing a result variable, the length of bytes returned in a caller's buffer, the `KRPC_CHECK` modes, and a small `KRPC_BUFFER_SIZE`.
 * C#: a static method's exception types on a connection with no service object.

## Other Conformance Work

This issue also tracks the other open conformance work. Each item has its own issue:

| Issue | Work | Kind |
|---|---|---|
| [conformance-spec-rulings.md](conformance-spec-rulings.md) | Rule on the behavior clients differ on, then add the tests | Spec |
| [spec-callback-thread-per-connection.md](spec-callback-thread-per-connection.md) | Guarantee one callback thread per connection | Spec |
| [conformance-forced-races.md](conformance-forced-races.md) | Add race points to C# and Python, for their 11 expected failures each in the `races` profile | Clients |
| [conformance-settle-sleeps.md](conformance-settle-sleeps.md) | Replace guessed sleeps with forced orders | Tests and clients |
| [conformance-serial-settle-time.md](conformance-serial-settle-time.md) | Wait for the serial link instead of a fixed second | Driver |
| [conformance-wait-until-polls.md](conformance-wait-until-polls.md) | Wake waits on the testee's notifications | Driver |
| [conformance-self-removing-callback.md](conformance-self-removing-callback.md) | A driver helper for a callback that runs a command on itself | Driver |
| [conformance-skipped-arguments-get-call.md](conformance-skipped-arguments-get-call.md) | Skipped arguments in a call built for a server side function | Tests |
