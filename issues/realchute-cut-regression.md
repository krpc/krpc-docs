# RealChute parachute no longer reaches the cut state in the in-game tests

`TestPartsRealChute::test_deploy_and_cut` fails with the mod integration framework, and passes on main. The parachute deploys. `Parachute.Cut` returns without error, but `Parachute.State` never reads `cut`, and the test times out after 30 s waiting for it. `test_state_on_ground` and `test_arm_by_staging` pass.

**Bisect.** It fails in every run from the framework's commit "Add RequiresMod, checked before each call" on: three runs at the tip of `requires-mod`, and once at that commit. It passes on main and at every earlier commit tried, the tip of `mod-api` included. That commit changes the scanner, which attaches a mod requirement to each procedure, the check before each call, and how `ModAPI` instances are created. `Parachute` has no `RequiresMod`, and no part of the call path the test uses changed in a way found by reading.

**Next.** Watch it in game: launch the `PartsRealChute` craft with RealChute, deploy, then cut, and print the visible event names of the parachute's `RealChuteModule` after each step, on main and on the framework. `Cut` triggers the "Cut main chute" event. `State` reads `cut` once no event naming "Cut" or "Deploy" is visible.

**Tests.** `test_parts_realchute.py` passes in game.

Labels: `bug`, `service`, `ksp`, `mods`. Milestone: `ksp-v0.8.0`.
