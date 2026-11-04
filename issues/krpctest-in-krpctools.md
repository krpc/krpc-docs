# Move krpctest into krpctools, as a game-agnostic in-game test runner

`krpctest` runs kRPC's service tests against a live game. It launches the game, installs the mod
and the test add-on, connects, and gives tests a `TestCase` with game helpers. No release has
published it. As written, it cannot work outside a kRPC checkout, so a published package would
fail on first use.

Design: [build-and-test-tools.md](https://github.com/krpc/krpc-docs/blob/main/design/ksa/build-and-test-tools.md), "In-game test harness"

The goal is one package, `krpctools`, that holds every kRPC tool and is versioned with the
release. `krpctest` moves into it, and becomes game-agnostic. Today's behavior for kRPC's own
KSP tests then comes from configuration rather than from code.

## What ties krpctest to KSP and to the repository

| Part | Tied to | Today |
|---|---|---|
| `install.py` (`krpc-install`) | Repository | Runs `bazel build //:krpc //tools/TestingTools //tools/benchmarks:KRPC.Benchmark` at the repository root and copies GameData from the build tree |
| `install.py` `MODS` | Repository, KSP | Third-party mods come from archives pinned in `MODULE.bazel`, fetched by Bazel |
| `env.get_repo_root` | Repository | Finds the root from `BUILD_WORKSPACE_DIRECTORY` or `MODULE.bazel`, and fails without one |
| `game.ensure_game` | Both | `TestCase.setUpClass` auto-launches the game, which runs the Bazel install |
| `env.py`, `run_ksp.py` | KSP | `KSP.x86_64` / `KSP_x64.exe`, `KSP.log`, `KSP_DIR` |
| `game.py` `_MOD_*` tables | KSP | How to tell each mod is installed in the running game: its services, parts, modules, flags, assemblies |
| `krpctest.sfs`, `krpctest_career.sfs` | KSP | The blank saves tests start from |
| TestingTools add-on | KSP, repository | Loads a save, switches vessel or launches a craft from `--krpctest-load-*` arguments; built from `//tools/TestingTools` |
| `testcase.py` helpers | KSP | `launch_vessel_from_vab`, `set_orbit`, `enter_editor` and others, over SpaceCenter RPCs |
| `pytest_plugin.py` | Packaging | A `pytest11` entry point, so it loads into every pytest run where the package is installed, `krpc-conformance` included |

Game-agnostic as it stands: `assertions.py`, `geometry.py`, the connection cache, the
wait helpers (`wait_until`, `wait_while`) and ordering tests by their required mods.

KSA has its own harness, `experimental/ksa/test/ksatest.py`, that repeats the launch, connect and
save logic for StarMap. A game-agnostic runner would replace it.

## Direction

- **Core in krpctools.** Game-agnostic launch, connect, install and stop. A `TestCase` with the
  assertions and wait helpers, and opt-in pytest plugin loading (`-p krpctools...`, or from the
  test suite's `conftest.py`).
- **A game profile, from a configuration file.** It names the executable per platform, the log to
  follow, and the server-ready marker. It also names the mod install directory, and how to pass
  the save and vessel to load.
  - KSP and KSA each get a profile, shipped in krpctools or in the test suite.
  - Command line options override the file.
- **What to install, from configuration.** Paths or archives for the kRPC mod, the test add-on and
  each third-party mod, with the check that tells each mod is installed.
  - kRPC's repository configuration points them at Bazel outputs, keeping `bazel run
    //:test-ingame` and `//:run-ksp` as they are.
  - A mod author's configuration points at a kRPC release and their own mod.
- **Game helpers stay with the game.** The KSP helpers (`launch_vessel_from_vab`, `set_orbit` and
  the others) move into a KSP mixin or module, beside the KSP profile.
- **The test add-on ships with krpctools.** TestingTools for KSP, and its KSA counterpart, so
  saves and craft load the same way outside the repository.

## Options considered

| Option | Third parties | Size |
|---|---|---|
| Game-agnostic, configured, in krpctools (above) | Usable by mod authors, for KSP and KSA | Largest: design pass, then phases |
| Fold into krpctools as-is, repository-only | Nothing gained; no console scripts published | Small |
| Keep it separate and internal | Nothing gained | Smallest |

The first is the direction.

## Phases

1. Make the pytest plugin opt-in.
2. Split the game-agnostic core from the KSP specifics inside `krpctest`, with no change in
   behavior.
3. Move configuration out of code: the game profile and the install sources. kRPC's repository
   configuration reproduces today's runs.
4. Move the package into krpctools. Ship TestingTools, and publish the console scripts.
5. Port the KSA harness onto it.

## Open questions

- Whether `krpc-install` installs kRPC from the release zip, or checks for an install made through
  CKAN.
- Where game profiles live: in krpctools, or with each game's test suite.
- Whether the KSP helpers ship in krpctools, or stay in kRPC's test tree as an example.
