# Conformance: run Python's `:conformance-base` with no stubs

`:conformance-base` is meant to run the Python client with no stubs, but it loads them. The driver in `client/conformance/BUILD.bazel` depends on `//client/python:krpc_lib`, and the testee runs from the same runfiles tree, so `krpc/services/*.py` is there to import. `test_exposed_members[services]` shows this: the base run reports `ui`, `debug` and `docking_camera` as services.

Pointing the driver at `krpc_base_lib` removes the stubs. The control connection still works, and the run on TCP/IP gives 3 failed, 588 passed, 57 skipped and 78 xfailed.

## Work

 * Move the driver to `krpc_base_lib`.
 * `test_unique_ids`, `test_match_by_id` and `test_abandoned_id` call `TestService` on a scripted server given only the `KRPC` definitions. With stubs, the call succeeds because the stub needs no definition. Without stubs, `conn.test_service` is `None`. The likely fix is to add `TestService` to the definitions these tests pass.

`test_exposed_members[services]` stays an expected failure in both runs, for different reasons. With stubs, every shipped service is attached. Without stubs, the testee's `is_service` recognizes a class deriving from `ServiceBase`, but `create_service` returns an instance, whose class is in the module `krpc.service`, so the testee reports no services. Fixing `is_service` here would make the test pass in one run only, and the runs share one `expected-failures.txt`, where a listed test that passes fails the run. Update the line's comment now, and fix `is_service` when #<python-declarations> removes the stubs.

This is the first phase of #<python-declarations>, which leaves Python with one conformance run. It gives that work a stubless run to check against while the stubs still exist.
