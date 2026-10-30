# Client open items

**Status:** open. Found while the client guides were rewritten (2026-10-29), for the client pass
after the spec lands.

Open issues found while rewriting the client guides (2026-10-29), apart from reviewing the guides
themselves. Each one is a client, spec or docs-build question. The guides describe the spec
behavior where the API exists, and leave out a feature that needs a new API. The section below lists
both.

## Decisions

1. **An infinite handshake timeout in C++ and Java.**
   - Both clients wait indefinitely only for a zero timeout. The spec makes zero an argument error
     (`connection-handshake-timeout-values`), and the fix was deferred.
   - The C++ guide tells readers to pass zero, as nothing else works.
   - The Java guide suggests a long timeout, such as `Duration.ofMinutes(5)`. A very large
     `Duration` overflows `toNanos`.
   - Still saying zero waits indefinitely: the 0.8.0 entry in `client/java/CHANGELOG.md`, and the
     Javadoc on the timeouts in `client/java/src/krpc/client/Connection.java`.
   - To decide: how each client spells an infinite timeout, then fix the code, the guides, the
     changelog and the Javadoc together.

2. **C++ registers the KRPC exception types only with a `krpc::services::KRPC` object.**
   - Without one, a KRPC exception is not thrown as its own type. About 40 expected failures say
     so (`test_errors.py::test_mapped_exceptions[...]` and others).
   - The guide's error bullets do not mention the condition, and its examples construct a KRPC
     object, so they work.
   - Proposed fix: register the throwers in the `Client` constructor.

3. **Lua and C-nano text kept although it touches expected failures.**
   - Lua: the Numeric Limits note that `UINT64_MAX` is `-1` and a uint64 wraps
     (`test_integers[uint64]`, `test_default_values[uint64-extremes]`). It describes a limit of
     Lua's integers.
   - C-nano: `krpc_connect` and the Arduino example retry by hand after 3 seconds on a serial line
     (`test_serialio_no_answer[*]`). It is the only way to recover a serial session today.
   - C-nano: `krpc_get_error_message` is cut to `KRPC_ERROR_MESSAGE_LENGTH`
     (`test_whole_message[*]`). The library is built on that fixed-size buffer.

4. **C-nano guide order.** Serial comes first, as it is the default build. TCP/IP and local socket
   follow.

## Left out of the guides until the API exists

The guides document each client as though its spec failures were fixed, where the API already
exists (2026-10-29 ruling). These need a new API first, so each guide leaves them out. Add them to
the guide with the API.

| Client | Feature left out | Spec requirement |
|---|---|---|
| C++ | An explicit close; close twice; close from another thread waking waiters | `connection-close`, `connection-close-twice`, `threading-close-with-a-call-in-flight` |
| C++, Java | A spelling for an infinite handshake or stall timeout (item 1) | `connection-handshake-timeout-values`, `connection-stall-timeout-values` |
| Java | The connection error after a close or failure. Calls declare only the checked `RPCException`, and `ConnectionException` is an `IOException`, so the exception types need a design first (item 7) | `connection-call-after-end`, `streams-read-after-close`, `streams-wake-waiter` |
| C#, Java | A scoped stream idiom, `using` or try-with-resources (item 12) | `streams-scoped-removal` |
| C#, Java | A connection-wide update wait and callback (item 11) | `threading-wait-for-update`, `streams-update-callback` |
| C# | Host names for the address (item 10) | `connection-unknown-host` |
| Lua | A stall timeout (item 13) | `connection-stall` |
| C-nano | Handshake and stall timeouts, which need a timed read, and so the automatic serial retry. The guide keeps the retry by hand (item 14) | `connection-handshake-timeout`, `connection-stall`, `connection-serialio-no-answer` |

Written as fixed, though the client still fails the test:

| Client | Guide text | Expected failure |
|---|---|---|
| Python, C#, Java | Dropping the last reference removes a stream or event | `test_streams.py::test_drop_last_handle`, `test_events.py::test_drop_last_handle` |
| C# | A call after `Dispose` throws `ConnectionException` | `test_connection.py::test_call_after_end[close]` |
| Java | `getObjectId(null)` throws `IllegalArgumentException`; objects order by unsigned id | `test_objects.py::test_get_object_id`, `test_objects.py::test_sorting` |
| Lua | Errors start with `Service.Name:`; refusals and disconnects name the status or reason | `test_errors.py::test_message_prefix[...]`, `test_handshake_refused[*]`, `test_handshake_disconnect[known]` |
| C++ | The KRPC exception types are thrown without a KRPC service object (item 2) | `test_errors.py::test_mapped_exceptions[...]` |
| Lua, Java | A zero (and for Lua, negative or NaN) handshake or stall timeout is an argument error | `test_connection.py::test_handshake_timeout_values[...]`, `test_stall_timeout_values[...]` |
| C# | `Run` and `AddStream` throw `ArgumentException` for a `TResult` that cannot hold the value | `test_functions.py::test_mismatched_type[...]` |
| C++ | `run` and a function stream throw `EncodingError` for a null without `std::optional` | `test_functions.py::test_null_for_non_nullable_type[double]`, `[TestClass]` |

## Client bugs and gaps

5. **C-nano `krpc_decode_string` writes past a caller's buffer.** Confirmed in
   `client/cnano/src/decoder.c:139`. A non-NULL `*value` receives `length` bytes and a terminator,
   with no size to check against. The guide tells readers to initialize strings to `NULL`, which
   avoids it. Fix by taking a buffer size, or by always allocating.

6. **C++ scoped streams in the testee.** Dropping the last copy of a C++ stream removes it, and
   the conformance test passes. `test_streams.py::test_scoped_removal` still fails, as the testee
   does not map `scoped` to a block-scoped stream. Mapping it would pass the test, and the guide
   could then show the block idiom.

7. **Java after a close or failure.** Calls, waits and end callbacks raise `RPCException` or
   `StreamException` instead of the connection error. The Java guide says nothing about the
   connection closing, so a fix lets that section come back. The expected failures:
   - `test_connection.py::test_call_after_end[close]`
   - `test_streams.py::test_wake_waiter[close]`
   - `test_streams.py::test_read_after_close[live]`
   - `test_events.py::test_end_callback[connection-failure]`

8. **C# after `Dispose`.** A call raises `ObjectDisposedException`, not the connection error
   (`test_connection.py::test_call_after_end[close]`). The guide mentions only a failed
   connection.

9. **C# type mismatches and nulls** raise `InvalidOperationException`, not the argument or
   encoding error:
   - `test_functions.py::test_mismatched_type[...]`
   - `test_functions.py::test_null_for_non_nullable_type[double]`

10. **C# has no host names.** The address is an `IPAddress` (`test_connection.py::test_unknown_host`).

11. **C# and Java have no connection-wide update wait or callback.** Python and C++ have both
    (`test_threading.py::test_wait_for_update`, `test_streams.py::test_update_callback`).

12. **Java and C# have no scoped stream idiom** (`test_streams.py::test_scoped_removal`). Python
    and C++ remove a stream at the end of a block.

13. **Lua has no stall timeout, refusal status or disconnect reason.** Lua errors are strings that
    start with the client's source position. The expected failures:
    - `test_stall`
    - `test_handshake_refused[*]`
    - `test_handshake_disconnect[known]`
    - `test_message_prefix[...]`

14. **C-nano has no timed read**, so it has no handshake or stall timeout. It also has no refusal
    status details.

20. **Found by the client API reference audit (2026-10-29).** Code bugs the reference now works
    around or leaves out. The handshake bugs have conformance tests, with the failures recorded as
    expected failures. The C-nano decoder bugs wait for the client pass, which fixes and tests
    them together.

    | Bug | Evidence | Test |
    |---|---|---|
    | A connection request whose write fails escapes the handshake unwrapped: `OSError` in Python, `std::runtime_error` in C++, `IOException` in C# and Java. C-nano returns `KRPC_ERROR_ENCODING_FAILED`. Lua passes | C-nano: `krpc.c:137-139` | `test_handshake_failed_write`, added. The C-nano fix returns the write's own error |
    | Java: a server that closes the socket during the handshake makes `newInstance` throw a bare `EOFException`, not `ConnectionException` | `handshake` catches only timeouts and parse errors (`Connection.java:505-519`); `MessageReader.read` throws `EOFException` (`MessageReader.java:151`) | `test_handshake_lost`, added. Every other client passes |
    | C-nano: decoding bytes into a caller's `KRPC_BYTES` buffer never writes the received length into `size` | `decoder.c:160-164` | Native `DISABLED_test_bytes_into_buffer_sets_size` in the [patch](#c-nano-decoder-tests-patch). The reference documents `KRPC_BYTES` for arguments only until fixed |
    | C-nano: a decoded collection passed into a second call is decoded with capacity 0 and writes past its allocation | `cnano.tmpl:390-398`, `456-463` | Native `DISABLED_test_list_into_decoded_list` in the [patch](#c-nano-decoder-tests-patch). Same class as item 5. The guide says to initialize before each call until fixed |

    Also from the audit, and not bugs:
    - C-nano: `KRPC_FREE_LIST` and friends free only the items array, so strings in a list leak
      unless freed first. That is the design, and the guide now says so.
    - Lua: `test_integers[uint64]` and `test_default_values[uint64-extremes]` describe a limit of
      Lua 5.3 integers, and arguably belong in `unsupported.txt`, not `expected-failures.txt`.

21. **Lua errors carry a position prefix.** `Client:_invoke` raises with
    `error(self:_error_message(result.error))` at level 1 (`client.lua:149`), so the message
    starts with `.../krpc/client.lua:149:`. `Errors.lua` prints
    `Failed to load the save: .../krpc/client.lua:149: KRPC.ArgumentException: Failed to load missing`.
    Raising at level 0 drops the prefix. Found reading the doc examples (2026-10-29).

22. **C-nano Arduino `krpc_open` never waits for the port.** `while (!*connection) {}`
    (`communication.c:300`) tests the `HardwareSerial*`, which is never null. The intent is
    `!**connection`, the port's `operator bool`. Found reading the doc examples (2026-10-29).

- **C++ server-ended event error.** An event the server ends raises an unnamed `RPCError`
  whose message starts `KRPC.StreamRemovedException:`, rather than the generated exception or
  the stream error. Listed as expected failures for `test_server_end`,
  `test_ended_without_firing` and `test_end_callback[server]` (2026-10-29).

## Docs and API

15. **Mapped exceptions are thrown two ways.** Python and C++ throw a generated class derived
    from the native type, such as `InvalidOperationException(RuntimeError)`. C# and Java throw
    the native type itself: `Connection.GetException` hard-codes the `System` types, and
    `java.tmpl` registers `exception.native` in place of the generated class. Java's
    `TimeoutException` is the exception, as it has no unchecked native type. So the C# and
    Java references document generated classes the clients never throw, on the KRPC page and
    in every "Throws" reference. `test_mapped_exceptions` allows both forms.

    The plan is to throw the derived class everywhere, which breaks no program, as a catch of
    the native type still matches. In C#, clientgen gives each mapped exception its `System`
    base, and `GetException` throws the registered types. None of the 11 is sealed. In Java,
    the generated class extends the native type and is registered. `test_mapped_exceptions`
    then requires the client's own type, with the native type among its bases. The docs need
    no change once the clients match them. A C# docgen fix linking references to the `System`
    types was tried and dropped (2026-10-29).

16. **Lua `platform.sleep` in the doc scripts.** Nothing in `client/lua` uses it. It appears only
    in doc scripts outside the client guide: the tutorials, the user guide, the home page and
    InfernalRobotics. Switching them to `socket.sleep` and deprecating `krpc.platform` is the fix
    in [lua-platform-sleep.md](../../issues/lua-platform-sleep.md).

17. **C-nano custom transport is undocumented.** `KRPC_COMMUNICATION_CUSTOM` does not say how a
    program supplies the `krpc_connection_t` and `krpc_connection_config_t` typedefs.

18. **C# target framework.** The guide keeps ".NET Framework 4.7.2 or later", and the package
    targets net472 only. [csharp-client-target-framework.md](../../issues/csharp-client-target-framework.md)
    covers this.

19. **Doc examples run (2026-10-29).** The Python client guide examples ran against KSP, through
    [test_doc_examples.py](test_doc_examples.py): a Basic craft in a 100 km Kerbin orbit, and on the
    pad for the stream endings. Run it with `bazel run //:test-ingame -- <path> -v -s`, with a
    `craft` link beside it to `service/SpaceCenter/test/craft`. The other clients' examples were
    compared with the Python ones by reading.

    - Python: every example does what its script says. `ConnectingLocal.py` was not run, as the
      test server listens on TCP/IP only, and `Connecting2.py` names a made-up address.
    - C++, C#, Java, Lua and C-nano match Python, apart from items 21 and 22. Output formats
      differ, and that is left: C++ prints bools as `0`/`1`, Java as `true`, and Java tuples as
      `[x, y, z]`. The C# and Java `NotLoadedStream` print the stream's value.

## Drafted issues

- [spec-callback-thread-per-connection.md](../../issues/spec-callback-thread-per-connection.md):
  guarantee one callback thread per connection.
- [client-api-reference-autodoc.md](../../issues/client-api-reference-autodoc.md): generate each
  client's API reference from its source.

The conformance review (2026-10-29) left four driver items, each drafted as an issue:

- [conformance-serial-settle-time.md](../../issues/conformance-serial-settle-time.md): wait for
  the serial link instead of a fixed second.
- [conformance-wait-until-polls.md](../../issues/conformance-wait-until-polls.md): wake waits on
  the testee's notifications.
- [conformance-queued-value-race-point.md](../../issues/conformance-queued-value-race-point.md):
  a race point for a value queued during a first call.
- [conformance-self-removing-callback.md](../../issues/conformance-self-removing-callback.md): a
  driver helper for a callback that runs a command on itself.


## C-nano Decoder Tests Patch

The native tests for the two C-nano decoder bugs in item 20, written 2026-10-29 and held back
until the fixes. Both fail on the current code: `size` stays at the buffer's 8, and the second
list decode overwrites the guard bytes. A test allocator, through `KRPC_CUSTOM_MEMORY_ALLOC`,
puts guard bytes after every block. With the fixes, drop the `DISABLED_` prefixes. It applies
with `git apply` from the root of the `krpc` repo.

```diff
diff --git a/client/cnano/BUILD.bazel b/client/cnano/BUILD.bazel
index 0ecbb853f..8e54ce4a3 100644
--- a/client/cnano/BUILD.bazel
+++ b/client/cnano/BUILD.bazel
@@ -76,6 +76,7 @@ test_suite(
         ":communication-serialio",
         ":communication-tcpip",
         ":conformance",
+        ":decoder",
         ":doxygen",
         ":lint",
     ],
@@ -184,6 +185,32 @@ cc_library(
     deps = ["@c_nanopb//:nanopb"],
 )
 
+# The decoder, with an allocator of the test's own that checks a decode stays within the blocks
+# it allocates
+cc_library(
+    name = "krpc_cnano_custom_alloc",
+    testonly = True,
+    srcs = srcs + [":protobuf"],
+    hdrs = hdrs + [":protobuf"],
+    defines = ["KRPC_CUSTOM_MEMORY_ALLOC"],
+    includes = ["include"],
+    deps = ["@c_nanopb//:nanopb"],
+)
+
+cc_test(
+    name = "decoder",
+    size = "small",
+    srcs = [
+        "test/test_decoder.cpp",
+        ":services-testservice",
+    ],
+    includes = ["test"],
+    deps = [
+        ":krpc_cnano_custom_alloc",
+        "@cpp_googletest//:gtest",
+    ],
+)
+
 # The communication backends, for what the conformance tests do not reach. Every one of them
 # runs against something that behaves as the thing it talks to does, so none needs the
 # hardware, port or server it is written for. The serial conformance tests run on Linux only,
diff --git a/client/cnano/test/test_decoder.cpp b/client/cnano/test/test_decoder.cpp
new file mode 100644
index 000000000..ec7205bf8
--- /dev/null
+++ b/client/cnano/test/test_decoder.cpp
@@ -0,0 +1,115 @@
+#include <gtest/gtest.h>
+#include <krpc_cnano.h>
+#include <krpc_cnano/memory.h>
+#include <services/test_service.h>
+
+#include <cstdint>
+#include <cstdlib>
+#include <cstring>
+#include <map>
+#include <vector>
+
+// The library is built with KRPC_CUSTOM_MEMORY_ALLOC, and these allocate each block with guard
+// bytes after it, so a test can check that a decode stayed within its allocations
+static const size_t GUARD_SIZE = 64;
+static const uint8_t GUARD = 0xab;
+static std::map<void*, size_t> blocks;
+
+extern "C" {
+
+void* krpc_malloc(size_t size) {
+  auto* block = static_cast<uint8_t*>(std::malloc(size + GUARD_SIZE));
+  std::memset(block + size, GUARD, GUARD_SIZE);
+  blocks[block] = size;
+  return block;
+}
+
+void* krpc_calloc(size_t num, size_t size) {
+  void* block = krpc_malloc(num * size);
+  std::memset(block, 0, num * size);
+  return block;
+}
+
+void krpc_free(void* ptr) {
+  if (ptr == nullptr) return;
+  blocks.erase(ptr);
+  std::free(ptr);
+}
+
+void* krpc_recalloc(void* ptr, size_t num, size_t inc, size_t size) {
+  void* block = krpc_calloc(num + inc, size);
+  std::memcpy(block, ptr, num * size);
+  krpc_free(ptr);
+  return block;
+}
+
+}  // extern "C"
+
+// Whether the guard bytes after every live block are intact
+static bool guards_intact() {
+  for (const auto& [block, size] : blocks) {
+    const auto* guard = static_cast<const uint8_t*>(block) + size;
+    for (size_t i = 0; i < GUARD_SIZE; i++)
+      if (guard[i] != GUARD) return false;
+  }
+  return true;
+}
+
+static std::vector<pb_byte_t> encode_list(const std::vector<int32_t>& values) {
+  std::vector<int32_t> items(values);
+  krpc_list_int32_t list = {items.size(), items.data()};
+  std::vector<pb_byte_t> data(1024);
+  pb_ostream_t stream = pb_ostream_from_buffer(data.data(), data.size());
+  EXPECT_EQ(KRPC_OK, krpc_encode_list_int32(&stream, &list));
+  data.resize(stream.bytes_written);
+  return data;
+}
+
+// The values 0 to n - 1
+static std::vector<int32_t> sequence(int32_t n) {
+  std::vector<int32_t> values;
+  for (int32_t i = 0; i < n; i++) values.push_back(i);
+  return values;
+}
+
+static krpc_error_t decode_list(const std::vector<pb_byte_t>& data, krpc_list_int32_t* list) {
+  pb_istream_t stream = pb_istream_from_buffer(data.data(), data.size());
+  return krpc_decode_list_int32(&stream, list);
+}
+
+// Note: fails until the decoder writes the received length into the caller's buffer
+TEST(test_decoder, DISABLED_test_bytes_into_buffer_sets_size) {
+  uint8_t sent_data[] = {1, 2, 3};
+  krpc_bytes_t sent = KRPC_BYTES_FROM_BUFFER(sent_data, sizeof(sent_data));
+  std::vector<pb_byte_t> data(64);
+  pb_ostream_t ostream = pb_ostream_from_buffer(data.data(), data.size());
+  ASSERT_EQ(KRPC_OK, krpc_encode_bytes(&ostream, sent));
+
+  KRPC_BYTES(received, 8);
+  pb_istream_t istream = pb_istream_from_buffer(data.data(), ostream.bytes_written);
+  ASSERT_EQ(KRPC_OK, krpc_decode_bytes(&istream, &received));
+  ASSERT_EQ(3, received.size);
+  ASSERT_EQ(0, std::memcmp(sent_data, received.data, 3));
+}
+
+// Note: fails until a list decoded into an earlier decoded list grows past its first block
+TEST(test_decoder, DISABLED_test_list_into_decoded_list) {
+  krpc_list_int32_t list = KRPC_NULL_LIST;
+  ASSERT_EQ(KRPC_OK, decode_list(encode_list({1}), &list));
+  auto values = sequence(3 * KRPC_ALLOC_BLOCK_SIZE);
+  ASSERT_EQ(KRPC_OK, decode_list(encode_list(values), &list));
+  EXPECT_TRUE(guards_intact());
+  ASSERT_EQ(values.size(), list.size);
+  for (size_t i = 0; i < values.size(); i++) ASSERT_EQ(values[i], list.items[i]);
+  krpc_free(list.items);
+}
+
+TEST(test_decoder, test_list_into_empty_list) {
+  auto values = sequence(3 * KRPC_ALLOC_BLOCK_SIZE);
+  krpc_list_int32_t list = KRPC_NULL_LIST;
+  ASSERT_EQ(KRPC_OK, decode_list(encode_list(values), &list));
+  EXPECT_TRUE(guards_intact());
+  ASSERT_EQ(values.size(), list.size);
+  for (size_t i = 0; i < values.size(); i++) ASSERT_EQ(values[i], list.items[i]);
+  krpc_free(list.items);
+}
```
