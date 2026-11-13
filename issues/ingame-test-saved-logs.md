# In-game tests: keep each game's log after the run

The game overwrites its log on each launch: `KSP.log` in the KSP folder. A test run that starts a game per mod set keeps only the last mod set's log. A binding warning or an exception from an earlier mod set is gone by the time the run ends. Checking the logs of a whole run needs a process that follows the log while the run goes, as the mod integration framework's phase 3 check did.

**Proposal.** krpctools copies the game's log when it stops or restarts a game it launched:

* One folder per run, `krpctools-logs/<timestamp>/` in the game folder, and one file per game launch, numbered in order and named by its mod set: `01-no-mods.log`, `02-SCANsat.log`. The folder is not `Logs/`, which KSP and other mods write to.
* The copy is taken after the game exits, so it holds the whole log. A run killed before cleanup keeps what it copied so far.
* The run prints the folder at the end, beside the pytest summary.
* The copy goes through `Game.log_path`, in the game-agnostic launch code, so KSA's tests get the same.
* The folder keeps the last 10 runs, and removes older ones when a run starts. `--keep-logs N` changes the count.
* `--no-launch` runs copy nothing, as the run does not own the game. `krpc-game run` copies the log when the game exits.

**Tests.** Unit tests in `tools/krpctools` for the folder naming, the file per launch and the pruning, with a fake game. An in-game run over two mod sets leaves two logs.

Labels: `enhancement`, `tools`. Milestone: none, as repo tooling.
