# Conformance: skipped arguments in a call built for a server side function

`test_calls.py::test_skipped_arguments` checks skipped arguments in ordinary calls only. No test skips an argument in a call built for `KRPC.Expression.Call`, which is what Lua's `Client:get_call` builds from #1267.

`get_call` shares its argument encoding with ordinary calls, so this is a gap in coverage with no known defect. The testee has to keep the skipped positions when it passes arguments to `get_call`, and no test checks that either.

Add a test under the `functions` and `skipped-arguments` profiles, for each of a procedure, a method and a static method:

* `OptionalArguments` called with `a, skip, c`, through `call_function` and `run_function`, returns `afoocnull`.
* Skipping `x`, which has no default and cannot hold null, raises the argument error when the call is built.

`call_function` passes `values.skipped()` through as it stands. Lua is the only client with the `skipped-arguments` profile.

Related: [conformance-coverage-gaps.md](conformance-coverage-gaps.md).
