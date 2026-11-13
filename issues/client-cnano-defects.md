# C-nano: defects found writing the design doc

Writing the client's design doc turned up these defects. Paths are relative to `client/cnano/`, and known conformance failures are in `conformance/expected-failures.txt`.

* **The Arduino library does not build.** `rebuild_source` in `tools/release/63-release-arduino.py` puts the nanopb headers in `src/krpc_cnano/` and leaves `#include "pb_common.h"` in the sources beside them, so `pb_common.cpp` fails to compile. The guide still sends users to the Library Manager, and no CI job compiles the library with an Arduino toolchain.
* **Reusing a result variable overflows the heap.** `krpc_decode_string` writes into a non-`NULL` pointer with no size check. The generated list, set and dictionary decoders set capacity 0 for a non-`NULL` array, so they never grow it.
* **Returned bytes do not report their length.** `krpc_decode_bytes` keeps a caller's `size` when it uses the caller's buffer. The caller sees the capacity, as does a later call on decoded bytes. A longer value fails with `KRPC_ERROR_BUFFER_TOO_SMALL`. An empty value sets `size` to 0 and keeps `data`, so the next decode allocates a new buffer and leaks the old one. The `result` of `krpc_run_function` in `include/krpc_cnano/functions.h` (#1267) decodes this way, and its documentation asks for an empty buffer.
* **A stub leaks its result on a failure.** The `return` macro in `cnano.tmpl` returns from `KRPC_CHECK` before `krpc_free_result`. Each `KRPC_ERROR_BUFFER_TOO_SMALL` or decode failure leaks the encoded value, as does a failed `krpc_invoke` after the value was read. `krpc_run_function` in `include/krpc_cnano/functions.h` (#1267) is written the same way.
* **Allocation failure crashes the client.** `krpc_return_value_decoder`, `krpc_decode_string`, the collection decoders and `krpc_recalloc` do not check for `NULL`. A failed allocation in the first segfaults when the value decodes. Only `krpc_decode_bytes` checks.
* **A refused argument ends the session.** `krpc_invoke` sets `krpc_session_ended` on any `krpc_send_message` error. A `krpc_bytes_t` with a size and a `NULL` `data` sends no bytes, and each later call then returns `KRPC_ERROR_CONNECTION_FAILED`. A call message from a `_call` function with an argument not filled in does the same (#1267).
* **A malformed `Error` is reported as a server error.** `krpc_decode_callback_error` in `src/krpc.c` returns `KRPC_ERROR_DECODING_FAILED` from a `bool` callback, which reads as `true`. The call returns `KRPC_ERROR_RPC_FAILED`, and the session continues.
* **A closed connection can be closed and used again.** A connection is a value, so nothing marks it closed. A second `krpc_disconnect` calls the transport's close again, which can close a reused file descriptor. After `krpc_close`, `krpc_invoke` still writes to the handle.
* **The POSIX serial transport fails on a signal.** `krpc_serial_read` and `krpc_serial_write` in `src/serial.c` report `EINTR` and a partial write as `KRPC_ERROR_IO`, which ends the session. The socket transport resumes both.
* **`krpc_open_serial` leaves the POSIX terminal mode alone.** In a terminal's default mode, the line discipline turns a written `0x0A` into `0x0D 0x0A` and a read `0x0D` into `0x0A`. The guide mentions only baud rate and framing, and the conformance tests use a raw `socat` port.
* **A `krpc_error_handler` that returns reports success.** The stub carries on after each `KRPC_CHECK`, so a failed call runs the handler twice and returns `KRPC_OK`. An `assert` under `NDEBUG` behaves the same, read from the macro.
* **Two error options fail to build.** `error.h` uses `assert` without including `<assert.h>`, so `KRPC_ERROR_CHECK_ASSERT` fails to compile as C++ and to link as C. `KRPC_PRINT_ERRORS_TO_STDERR` with `PB_NO_ERRMSG`, the Arduino default, fails on `errmsg`.
* **Library options cannot apply to a prebuilt library.** `krpc_error_handler` and `krpc_get_error_message` exist only if the library was compiled with their macro, and the CMake build and vcpkg port have no option for it. A vcpkg user defining either gets a link error.
* **A refusal's text never reaches the program.** `krpc_connect` ignores the message of a `connection_response`, and `krpc_get_error_message` holds server call errors only. The reason on `test_handshake_refused` in `conformance/expected-failures.txt` says the status is in a message.
* **`krpc_float64_to_float32` returns NaN for some finite values.** A value from `2^128` up to `2^129`, such as `4e38`, keeps its mantissa with the infinity exponent. A value below `2^-127` stays a subnormal, where the comment in `src/utils.c` says it rounds to zero. Only AVR calls this.
* **Stale text.** The header of `benchmark/benchmark.c` says the transport is picked with a macro, with one program per transport. `INSTALL.txt` links `cnano/client.html`, and the page is `cnano.html`.

## From the parity audit and the client guide rewrite

Still open from the client API parity audit (2026-07-21) and the client guide rewrite (2026-10-29), re-checked against `main` on 2026-11-09.

* **No timed read,** so there is no handshake or stall timeout (`test_handshake_timeout[none]`, `test_stall`). A serial session cannot retry silently either: a `MALFORMED_MESSAGE` or `TIMEOUT` answer to a resumed handshake returns an error for the program to retry (`test_serialio_no_answer[*]`). The guide keeps the retry by hand, after 3 seconds, until the API exists.
* **`krpc_disconnect` sends the `disconnect` and closes, with no half-close or drain** (`test_close`). By design in the single connection, but the spec makes the drain a MUST.
* **A refusal's status, an unknown status's message and a disconnect's reason are not reported as fields** (`test_handshake_refused[DENIED]`, `test_handshake_unknown_status`, `test_handshake_disconnect`).
* **`krpc_get_error_message` is cut to `KRPC_ERROR_MESSAGE_LENGTH`**, 256, which cuts the stack trace (`test_whole_message[*]`). The library is built on that fixed buffer, and the guide says so.

## Decoder tests patch

Native tests for "Reusing a result variable" and "Returned bytes do not report their length", written 2026-10-29 and held back until the fixes. Both fail on the current code: `size` stays at the buffer's 8, and the second list decode overwrites the guard bytes. A test allocator, through `KRPC_CUSTOM_MEMORY_ALLOC`, puts guard bytes after every block. With the fixes, drop the `DISABLED_` prefixes. It applies with `git apply` from the root of the `krpc` repo.

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
