# Cut the CI time the client conformance tests add

The conformance tests from #1220 roughly double the C++ and C-nano CI test jobs. The job durations below are in minutes. The usual time is the median of six earlier runs, and #1220 is its two runs on 2026-10-30.

| Job | Usual | #1220 |
|---|---|---|
| windows-test-client-cpp | 7.0 | 15.3-16.6 |
| windows-test-client-cnano | 4.5 | 13.3 |
| linux-test-client-cpp | 5.6 | 11.5-13.2 |
| linux-test-client-cnano | 2.4 | 6.2-6.5 |
| windows-test-client-lua | 3.4 | 5.2-5.8 |
| linux-test-client-lua | 1.6 | 3.3-3.8 |

The other jobs are within about a minute of their usual times.

## Where the time goes

| Cause | Jobs | Cost |
|---|---|---|
| protoc and abseil built from source | C++ and C-nano | 4-7 minutes on Windows, less on Linux |
| Conformance test runs | C++, C-nano and Lua | Per protocol: C++ ~105 s, Lua ~75 s, C-nano 45-65 s |

**The protoc build.** The C++ and C-nano testees print JSON through `google/protobuf/util/json_util.h`, so they depend on the full `@protobuf` library rather than `protobuf_lite`. The full library has the well-known types as `cc_proto_library` targets. Building them needs a proto toolchain, and by default protobuf's toolchain compiles protoc from source in the exec configuration, along with most of abseil. Our own codegen rules already use the prebuilt protoc from `MODULE.bazel`, so main never paid for this. One Windows C++ run shows the difference:

| | main | #1220 |
|---|---|---|
| Test step | 226 s | 796 s |
| Local actions | 293 | 730 |
| Protobuf compiler sources compiled | 0 | 73 |
| Critical path | 79 s | 287 s |

## Change

- Use protobuf's prebuilt protoc toolchain, with `--incompatible_enable_proto_toolchain_resolution` and `--@protobuf//bazel/toolchains:prefer_prebuilt_protoc` in `.bazelrc`. Check the flag names against protobuf 36.2 first, and that the C++ test job then compiles no files under `src/google/protobuf/compiler`.
- If the toolchain flags cause trouble, give the testees a JSON printer of their own and depend on `protobuf_lite`, as the clients do.
- Measure again afterwards. If the test runs still dominate, look at splitting each conformance target into shards.

A shared Bazel remote cache would also cover the protoc build, but [build-tools/ci-remote-cache.md](../design/build-tools/ci-remote-cache.md) ruled it out.

## Not in scope: vcpkg rebuilds after a runner image update

The same day, `windows-build-client-cpp-vcpkg` took 19.2 minutes instead of 1.8. Between two runs, the Windows runner image moved from `win25-vs2026/20261021.278` to `20261030.294`. The new image brought new vcpkg ports (protobuf 6.33.4 to 7.36.2, asio 1.32.0 to 1.38.2) and cmake 4.4.4 to 4.4.5. Every package ABI hash changed, so all six packages rebuilt, protobuf alone in 14 minutes.

The vcpkg caches behave as designed here. They key on ABI hashes, so a new image costs one rebuild per branch until main saves the new cache. Pinning a vcpkg baseline would stop the rebuilds, but the job exists to test against the ports users install, so the versions should follow the image.

Related to #1220
