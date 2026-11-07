# Move krpctest into krpctools, as a game-agnostic in-game test runner

`krpctest` runs kRPC's service tests against a live game. It launches the game, installs the mod
and the test add-on, connects, and gives tests a `TestCase` with game helpers. No release has
published it. As written, it cannot work outside a kRPC checkout, so a published package would
fail on first use.

Design: [build-and-test-tools.md](https://github.com/krpc/krpc-docs/blob/main/design/ksa/build-and-test-tools.md), "In-game test harness"

The goal is one package, `krpctools`, that holds every kRPC tool and is versioned with the
release. `krpctest` moves into it, split into a game-agnostic core and one extension per game.
Everything stays Python: a game, a mod and a test suite's setup are classes, with no
configuration files.

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

Three parts, all Python. The core defines base classes, and each game extends them in code. A
game can need logic a configuration file cannot express: KSP finds mods by GameData folder and
Module Manager, KSA launches through StarMap and saves on first load.

| Part | Holds |
|---|---|
| Core, `krpctools.game` | `Game` and `Mod` base classes. Launch, connect, wait for the server, stop. Reconcile the installed mods. `TestCase` with the assertions and wait helpers. The pytest plugin, opt-in |
| KSP, `krpctools.game.ksp` | `KSP(Game)`: executable, `KSP.log`, GameData, the `--krpctest-load-*` arguments, the blank saves. `Mod` subclasses for the supported mods. A KSP `TestCase` with the helpers (`launch_vessel_from_vab`, `set_orbit`, ...). TestingTools |
| KSA, `krpctools.game.ksa` | `KSA(Game)`: StarMap launch, `ksa.log`, the save on first load. Its `TestCase` and test add-on |

The KSA part comes at 1.0 (see [Later](#later)). The core is designed with it in mind, so it
fits without changes to the core.

- **`Game`** is a base class whose methods a game overrides: the command to launch, the log to
  follow, the ready check, how to load a save or vessel, where mods install, and how to tell a
  mod is present in the running game.
- **`Mod`** is a base class with a source and an install. The source is a path, an archive or a
  URL. The install and the presence check default to the game's, and a mod overrides either one.
- **Each game fetches kRPC from its own release channel.** Its `Game` subclass knows the
  channel, as the channels differ by game. By default it installs the newest release on the
  game's train. `--krpc-version 1.0.3` pins a release on that train, so a mod author's CI holds
  still when kRPC releases. `--krpc path/to/krpc.zip` installs a local zip in place of either:
  a Bazel build, or a custom version.
  - KSP takes the newest `ksp-v*` release from GitHub, the archive CKAN also points at.
  - KSA takes the newest `ksa-v*` release from GitHub, the archive Borea and SpaceDock also list.
  - The newest tag on the train, never `releases/latest`, which spans every train
    ([releases.md](https://github.com/krpc/krpc-docs/blob/main/design/releases.md)).
- **The supported third-party mods ship in krpctools**, in `krpctools/game/ksp/mods.py`. Each
  definition holds its archive URLs and hashes, its dependencies and its presence check, so a mod
  author testing against FAR writes none of it.
  - `--mod FAR=path/to/FAR.zip` installs a local archive in place of the pinned one. It takes no
    version option: a definition and its pins change together.
  - A mod's config overlays ship with its definition, as the blank saves do with `KSP`. They
    are the small files a mod needs to run under test, such as the part that uses the DMagic
    code.
  - Downloads go to a user cache keyed by hash, shared by kRPC and the mods.
  - `mods.py` is the one list of pins. Bazel no longer fetches the mods, so their `http_archive`
    entries leave `MODULE.bazel`, and `tools/mods` goes. The in-game tests run outside CI, so
    Bazel's repository cache gains little there.
- **A test suite chooses its game in code.** Its `conftest.py` builds the game object, with the
  sources for kRPC, the test add-on and each mod, and registers it with the plugin. Command line
  options (`--game`, `--game-dir`, `--no-launch`) override what that object sets.
  - kRPC's own suite subclasses `KSP` to take the sources from Bazel outputs. `bazel run
    //:test-ingame` and `//:run-ksp` behave as they do now.
  - A mod author's suite uses `KSP` with a kRPC release and adds a `Mod` for their own mod.
- **Each game's binaries ship in its subpackage.** The test add-on is the server half of the
  game's Python code, and the two change together: TestingTools for KSP, and its counterpart for
  KSA. The blank saves give a fresh install a save to load.
  - krpctools takes its own release train after 1.0, so a game update means a new krpctools
    release.
  - One package holds every game. Few people use krpctools, so a package per game costs more
    than it saves.

### Commands

`krpc-game` replaces `krpc-run-ksp` and `krpc-install`. Tests run under pytest, with the plugin
loaded.

| Command | Does |
|---|---|
| `krpc-game install` | Installs kRPC, the test add-on and the requested mods, and removes any others |
| `krpc-game run` | Installs, launches, loads a save or vessel, and follows the log |
| `krpc-game stop` | Stops a game that `run` launched |

`--game` selects the game object, for `krpc-game` and for the pytest plugin:

- **A name**, `--game ksp` or `--game ksa`, takes a built-in game with its defaults. Options such
  as `--krpc path/to/krpc.zip` override the sources. This covers mod authors.
- **A reference**, `--game module:object`, takes a game object from Python code. kRPC's
  repository passes its Bazel-sourced `KSP` subclass this way, and `//:run-ksp` wraps the call.
  A suite's `conftest.py` and `krpc-game` then share one definition.

### Layout

```
krpctools/
  clientgen/, docgen/, servicedefs/, testserver/, conformance/   unchanged
  game/
    __init__.py         Game, Mod
    launch.py           launch, wait for the server, stop
    install.py          reconcile the installed mods
    testcase.py         TestCase, connection cache, wait helpers
    assertions.py, geometry.py, diagnostics.py
    pytest_plugin.py    opt-in: -p krpctools.game.pytest_plugin
    cli.py              krpc-game
    ksp/
      __init__.py       KSP(Game), the KSP TestCase and its helpers
      mods.py           Mod subclasses for the supported mods
      mods/             their config overlays
      saves/            the blank saves
      addon/            TestingTools.dll
    ksa/
      __init__.py       KSA(Game), the KSA TestCase
      addon/            the KSA test add-on
```

## Options considered

| Option | Third parties | Size |
|---|---|---|
| Game-agnostic core and game extensions, in krpctools (above) | Usable by mod authors, for KSP and KSA | Largest: design pass, then phases |
| Fold into krpctools as-is, repository-only | Nothing gained; no console scripts published | Small |
| Keep it separate and internal | Nothing gained | Smallest |

The first is the direction.

## Phases

1. Make the pytest plugin opt-in.
2. Split the game-agnostic core from the KSP specifics inside `krpctest`, with no change in
   behavior.
3. Extract `Game` and `Mod` from the KSP code, with `KSP` as the first subclass. kRPC's suite
   builds its `KSP` object from Bazel outputs, and reproduces today's runs.
4. Move the package into krpctools as `krpctools.game`. Ship TestingTools, the saves and the
   mod overlays, and publish `krpc-game`.

## Later

- **KSA, at 1.0.** Add `krpctools.game.ksa` with `KSA(Game)` and its test add-on, and port
  `experimental/ksa/test/ksatest.py` onto it.
