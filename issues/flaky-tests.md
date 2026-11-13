# Flaky tests seen in the 0.8 cycle

Three tests failed once and passed on a rerun, with no change in between. Each needs its cause found and fixed, or its wait made robust.

**SCANsat `TestScanSat::test_state_out_of_range`** (in-game). Failed in two full mod runs, on 2026-11-12 and 2026-11-13, and passed on rerun both times. It checks the scanner state after one fixed `wait()`, where its sibling `test_state` uses `wait_until`. Likely fix: wait until the state reads out of range, with a timeout.

**FAR `TestFlightAeroFAR::test_simulate_aerodynamic_wrench_reference_frames`** (in-game). Failed late in long runs on 2026-10-15 and 2026-11-13, and passed on rerun both times. On 2026-10-15 the force differed by about 65 kN between reference frames, against a tolerance of 55 N. The stock variant has not failed. Suspect FAR state carried over from earlier tests in the same game: run the class after the rest of the FAR tests, and compare.

**C++ `test_concurrency.py::test_wait_on_condition_object`** (client conformance, local socket). Failed once in `//:test` on 2026-11-13 with a `BrokenPipeError` as the driver wrote to the testee, and passed on rerun. Python lists the same test as `@flaky` for a dispatcher race, which may or may not be the C++ cause. Until it is fixed, it takes `@flaky` in `client/cpp/conformance/expected-failures.txt`.

**Tests.** Each fixed test passes in repeated runs: the in-game ones in a few full mod runs, and the conformance one under `--runs_per_test`.

Labels: `bug`, `tools`, plus `ksp` and `mods` for the in-game tests, and `client` and `cpp` for the conformance test. Milestone: none, as repo tooling.
