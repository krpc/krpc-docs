# Clients: a manual sanitizer run for C++ and C-nano

The repo has no sanitizer setup. C++ and C-nano are the only clients we compile to native code, so they are the two that benefit. Python, C#, Java and Lua run on managed runtimes, and a sanitizer there would mostly check the runtime.

Add a run for a developer to start by hand: when changing the C++ reference rules or threads, and before a release. CI can come later, as the cost is low.

## Cost

Measured once on Linux, 2026-11-06. Each sanitizer build took under two minutes, about 600 compile actions, and a later run reuses it.

| Test | Normal | ASan and UBSan | TSan |
|---|---|---|---|
| `//client/cpp:conformance-tcpip` | 49 s | 65-67 s | 69-70 s |
| `//client/cpp:client-tcpip` | 4.4 s | 5.2 s | 5.2 s |
| `//client/cnano:conformance-tcpip` | 42 s | 44 s | not run |

The slowdown is small, probably because these tests spend most of their time in waits. This was not measured.

The commands used, with `--platform_suffix` keeping the outputs apart from the normal build:

```bash
bazel test --platform_suffix=asan --cache_test_results=no \
  --copt=-fsanitize=address,undefined --cxxopt=-fsanitize=address,undefined \
  --copt=-fno-omit-frame-pointer --linkopt=-fsanitize=address,undefined \
  --test_env=ASAN_OPTIONS=log_path=$REPORTS/asan --test_env=UBSAN_OPTIONS=log_path=$REPORTS/ubsan \
  --test_env=LSAN_OPTIONS=log_path=$REPORTS/lsan \
  //client/cpp:client-tcpip //client/cpp:conformance-tcpip \
  //client/cnano:client-tcpip //client/cnano:conformance-tcpip

bazel test --platform_suffix=tsan --cache_test_results=no \
  --copt=-fsanitize=thread --copt=-fno-omit-frame-pointer --linkopt=-fsanitize=thread \
  --test_env=TSAN_OPTIONS=log_path=$REPORTS/tsan \
  //client/cpp:client-tcpip //client/cpp:conformance-tcpip
```

## A passing test can hide a report

A conformance run passes with sanitizer reports in it. `Testee.stop` ignores the testee's exit code, and pytest captures its standard error for a test that passes. A crash in an expected failure also goes unseen, as the harness starts a new testee.

`log_path` gets around both, by writing each report to a file. The run fails if `$REPORTS` holds a file.

## TSan false positives

TSan reports correct code on this toolchain, as libc++ and libc++abi are not instrumented. It reports `free` of a `shared_ptr` control block or an exception object against an earlier read, when only the reference count orders the two. A kRPC-free test, a detached thread dropping the last `shared_ptr` or `exception_ptr`, reproduces both. The C++ client now reaches this, as the last release of a stream can run on a dispatcher thread that nothing joins, so `//client/cpp:client-tcpip` exits non-zero under TSan.

The run needs a suppression for these two shapes, or an instrumented libc++. Until then, read each report: all frames that raced should be `free` under `__on_zero_shared_weak` or `__cxa_decrement_exception_refcount`.

## Findings from the first run

C++ had no reports under ASan, UBSan or TSan. The TSan result has no control: no deliberate race was run to show that a report reaches the file.

All of the reports are from the C-nano testee:

| Report | Location | Status |
|---|---|---|
| Null argument to `strlen`, then a SEGV, in two testee processes | `client/cnano/src/encoder.c:357` | Known: `test_null_in_non_nullable_slot[dictionary-key]` is an expected failure for this crash |
| Enum load of value 99 | `client/cnano/conformance/dispatch_values.hpp:211` | Known: the C-nano enum behind `test_undeclared_enum_result`. Here the cast is in the testee |
| 97 bytes leaked in 6 allocations, in one testee process | Not symbolized | Not attributed. The testee allocates with `krpc_malloc` itself, so this may be the testee and not the client |

## Work

 * Add `asan` and `tsan` configs to `.bazelrc`, holding the flags above.
 * Add a script that runs both configs and fails on a report file. Linux only.
 * Add the rest of the C-nano and C++ targets: `unit`, the `communication-*` tests and the other transports. These were not run, apart from `//client/cpp:unit`, which passed under both.
 * Run a deliberate race and a deliberate leak once, to confirm that each kind of report fails the script.
 * Attribute the leak, then fix it or add a suppression. Add suppressions for the two known reports, each naming its expected failure.
 * Document the run in `doc/src/krpc-development/testing.rst`, and add it to the release checks.
