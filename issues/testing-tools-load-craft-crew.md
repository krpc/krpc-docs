# Testing tools: `--load-craft` launches the craft with no crew

`krpc-game run --load-craft=NAME` launches the craft through `SpaceCenter.LaunchVesselCoroutine`, with an empty crew list (`AutoSwitchVessel.LaunchCraftCoroutine`). `LaunchVessel` treats an empty list as "launch with no crew", so a crewed craft with no probe core comes up uncontrollable. A stock Kerbal X launched this way could not fly the MechJeb ascent example until it was relaunched from a client with the default crew.

Proposed fix: pass `null`, so the craft gets its default crew assignments, as in the VAB. A `--load-crew` option can follow if a test needs a named crew or none.

Tests: launch a crewed craft with `--load-craft` and check its crew count.

Labels: `bug`, `tools`, `ksp`. Milestone: none on the PR, as repo tooling.
