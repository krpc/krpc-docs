# In-game tests: fewer scene loads per test class

Each scene load in KSP takes about 10 seconds, and most test classes pay for two of them. Loads, not tests, make up much of an in-game run.

**Where the loads come from.**

* `TestCase.launch` calls `new_save`, then launches the craft. `new_save` keeps the current game only when it is the right save, in flight, with one vessel: the save's own one-part Basic pod. After any launch the active vessel is another craft. So the next class reloads the save (`TestingTools.LoadSave`, a flight scene load), then launches (a second flight scene load).
* `always_load=True` reloads even when the save already fits. Thirteen setups use it, besides the nine that load the career save, which always reload.
* Some classes launch in `setUp`, so every test pays for a launch: the autopilot launch and flight classes, `TestControl`, the IVA camera tests, the crew tests.
* Entering and leaving the editor adds two more scene changes to an editor class.

**Proposal.** Measure first: count the scene loads per class from `KSP.log` over a run of a few files, and the share of the run's time they take. Then, in order of likely gain:

1. **Launch without reloading the save.** `launch` reloads only when the save, the scene or the game state is wrong. It does not reload just because the active vessel is another craft. `launch_vessel` recovers the vessel on the launch site, and `remove_other_vessels` clears the rest, so one load per class remains. The risk is state carried between classes: UT, the Kerbal roster, contracts, funds, and settings a test changed. Each needs either a reset that costs no load or a class that asks for `always_load`.
2. **Review `always_load`.** Keep it only where a class needs a fresh game state, and say why in a comment.
3. **Per-test launches.** Where a test only needs the vessel back in its starting state, reset it in place (resources, orbit, controls) in place of relaunching. The autopilot launch tests need a fresh launch, and stay.

**Tests.** The measurement before and after. The in-game suite passes, run in its usual order and with each changed file run on its own, so a class does not depend on what the class before it left behind.

Labels: `enhancement`, `tools`, `ksp`. Milestone: none, as repo tooling.
