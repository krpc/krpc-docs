# Close the gaps in the auto-pilot test plan

Milestone: none · Labels: tools, service:space-center

The in-game auto-pilot tests from #882 leave these cases untested:

* `attenuation_angle`, the response with `auto_tune` off, and a purely radial nudge.
* The dynamic roll axis, a moving target, the `decel_lag_correction` A/B and the first tick transient.
* Overshoot assertions in `test_set_pitch` and `test_set_heading`.
* Clearing the integral at PRELAUNCH.
* More RCS on the `AutoPilotChatter` craft, and `recover_timeout` for `test_orbital_directions` on the flexible craft.

Design: [test-plan.md](https://github.com/krpc/krpc-docs/blob/main/design/autopilot/test-plan.md), section 11.
