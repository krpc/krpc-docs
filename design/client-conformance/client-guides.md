# Client guide rewrite

**Status:** done (2026-10-29). The client guides were rewritten against the spec. The open items it
found moved to the issues on 2026-11-09: the client defects issues, such as
[client-design-shared-defects.md](../../issues/client-design-shared-defects.md), and
[client-api-reference-autodoc.md](../../issues/client-api-reference-autodoc.md),
[lua-platform-sleep.md](../../issues/lua-platform-sleep.md) and
[#1230](https://github.com/krpc/krpc/issues/1230).

## Decisions

* **A guide describes the spec behavior where the API exists,** even where the client still fails
  the test, so the guide needs no change once the client is fixed. A feature that needs a new API is
  left out, and added with the API.
* **Lua and C-nano text kept although it touches expected failures:**
  - Lua: the Numeric Limits note that `UINT64_MAX` is `-1` and a uint64 wraps
    (`test_integers[uint64]`, `test_default_values[uint64-extremes]`). It describes a limit of
    Lua's integers.
  - C-nano: `krpc_connect` and the Arduino example retry by hand after 3 seconds on a serial line
    (`test_serialio_no_answer[*]`). It is the only way to recover a serial session.
  - C-nano: `krpc_get_error_message` is cut to `KRPC_ERROR_MESSAGE_LENGTH`
    (`test_whole_message[*]`). The library is built on that fixed-size buffer.
* **C-nano guide order.** Serial comes first, as it is the default build. TCP/IP and local socket
  follow.

## Doc examples run

The Python client guide examples ran against KSP, through [test_doc_examples.py](test_doc_examples.py):
a Basic craft in a 100 km Kerbin orbit, and on the pad for the stream endings. Run it with
`bazel run //:test-ingame -- <path> -v -s`, with a `craft` link beside it to
`service/SpaceCenter/test/craft`. The other clients' examples were compared with the Python ones by
reading.

* Python: every example does what its script says. `ConnectingLocal.py` was not run, as the test
  server listens on TCP/IP only, and `Connecting2.py` names a made-up address.
* C++, C#, Java, Lua and C-nano match Python, apart from the Lua error position prefix and the
  C-nano Arduino port wait. Output formats differ, and that is left: C++ prints bools as `0`/`1`,
  Java as `true`, and Java tuples as `[x, y, z]`. The C# and Java `NotLoadedStream` print the
  stream's value.
