# Complete & harden stock robotics (Breaking Ground) support

**Status:** done — merged as [PR #985 "Complete the stock robotics API and expand InfernalRobotics to
IR-Next's core API"](https://github.com/krpc/krpc/pull/985) (2026-07-19). Historical design record.
The v0.5.0 changelog already advertised "Add support for stock robotic parts"; this work completed
that partial contribution and added the integration tests it never had.

## Motivation

Kerbal Space Program's Breaking Ground expansion adds stock robotic parts (hinges, rotation servos,
pistons, rotors, and a robotic controller). kRPC already exposes these as first-class part types —
but only partially. The five wrapper classes under `service/SpaceCenter/src/Services/Parts/`
(`RoboticController`, `RoboticHinge`, `RoboticPiston`, `RoboticRotation`, `RoboticRotor`) were an
external contribution (artwhaley, "Partial Support for Stock Robotics") shipped in **v0.5.0**. They
work, but the implementation is incomplete and has never had integration-test coverage. This design
brings them up to the standard of the other stock part types: fill the gaps, fix the rough edges,
add the members the partial contribution skipped, and add tests.

Scope is deliberately **additive/fix-up only** — no API redesign. The existing shape (a class per
servo type, `Target*`/`Current*`, `Rate`, `Damping`, `Locked`, `MotorEngaged`, `MoveHome`) is kept
where sound.

## What exists today

Each class follows the standard part-wrapper pattern: `[KRPCClass(Service = "SpaceCenter")]`, a
`readonly` KSP module field, a static `Is(Part)` via `part.InternalPart.HasModule<T>()`, a
constructor via `Module<T>()`, `Equals`/`GetHashCode`, and a `Part` back-reference. They are wired
into `Part.cs` (nullable accessors for all five) and documented in
`doc/api/space-center/parts.tmpl`. `Parts.cs` has vessel-wide collections for four of the five.

The wrapped `Expansions.Serenity` modules are compiled into stock `Assembly-CSharp.dll` (the
expansion ships no separate assembly), so these are **direct compile-time references** against the
KSP API stub — not the runtime-reflection wrapper that `service/InfernalRobotics/` uses for the
third-party IR mod. Reflection is used only to reach a handful of *private* Serenity members.

## KSP API surface (from the disassembly)

Verified with `monodis` against the real game `Assembly-CSharp.dll` and cross-checked against the
compile-target stub (`lib/ksp/KSP_Data/Managed/Assembly-CSharp.dll`). Every member proposed below is
**public in the stub** — so it needs no reflection — except `IsMoving`, which is protected.

* **`BaseServo`** (public): `servoIsLocked`, `servoIsMotorized`, `servoMotorIsEngaged`,
  `launchPosition`, `servoMotorLimit` (torque %), `maxMotorOutput`, `useLimits`, `hardMinMaxLimits`
  (`Vector2`), `traverseVelocityLimits` (`Vector2`), `CurrentVelocityLimit`,
  `GetSoftLimits`/`GetHardLimits`/`SetSoftLimits(string fieldName)`, `SetLaunchPosition`.
  `IsMoving()` is `family` (**protected**, overridden per derived type) — reflection only.
  `motorState` is a localized `#autoLOC_…` string, **not an enum**.
* **`ModuleRoboticServoHinge`**: `softMinMaxAngles` (`Vector2`), `currentAngle`, `modelInitialAngle`,
  `targetAngle`, `traverseVelocity`, `hingeDamping`.
* **`ModuleRoboticRotationServo`**: `allowFullRotation`, `softMinMaxAngles`, `currentAngle`,
  `targetAngle`, `traverseVelocity`, `hingeDamping`, `inverted`. No `modelInitialAngle` (its
  `MoveHome` uses `launchPosition`).
* **`ModuleRoboticServoPiston`**: `softMinMaxExtension` (`Vector2`), `currentExtension`,
  `targetExtension`.
* **`ModuleRoboticServoRotor`**: `rpmLimit` (target), `currentRPM`, `maxTorque` (kN), `inverted`,
  `rotateCounterClockwise`, `brakePercentage`, `rotorSpoolTime`. **No target position / no home** —
  confirming a rotor `MoveHome` is not applicable.
* **`ModuleRoboticController`**: `controllerEnabled`, `SequencePlay`/`SequenceStop`,
  `SequenceIsPlaying`, `SequencePosition`/`SetSequencePosition`, `SequenceLength`,
  `SequencePlaySpeed`, `ControlledAxes`.
* **`ExpansionsLoader`** (stub, public): static `Instance`; `IsExpansionInstalled(string)`;
  `supportedExpansions[]`, each with public `expansionName`.

**On a servo-state enum:** there is no clean KSP enum to mirror — only the localized `motorState`
string, the protected `IsMoving()`, and the `servoIsLocked`/`servoMotorIsEngaged` booleans. A boolean
`IsMoving` covers the need; a `MotorState`-style enum + `Extensions` converter is not worth adding.

## Design

### 1. Fix the existing classes

* **`RoboticRotation.cs`** — remove the leaked public non-RPC `InternalRotation` property (grep
  confirms zero references repo-wide; no sibling class has an equivalent).
* **`RoboticController.cs`** — `Equals` uses `controller == other.controller`; change to
  `controller.Equals(other.controller)` to match the servo classes.
* **`RoboticPiston.cs`** — `Rate` is documented "degrees per second"; a piston is linear →
  "meters per second".
* **Hinge/Piston/Rotation `MoveHome`** — docstring typo "it's built position" → "its".
* **`RoboticRotor.cs`** — do **not** add `MoveHome`: rotors are continuous, with no
  `launchPosition`/home target. Note this in the docs.

### 2. Add the missing collection

`Parts.cs` — add a `RoboticControllers` property
(`All.Where(RoboticController.Is).Select(part => new RoboticController(part)).ToList()`), mirroring
the existing `RoboticHinges`/`RoboticPistons`/`RoboticRotations`/`RoboticRotors`. The controller is
the only robotic type missing a vessel-wide collection.

### 3. Add completion members (each maps to a verified public field)

* **Hinge & Rotation**: `MinAngle`/`MaxAngle` ← `softMinMaxAngles.x/.y` (set via
  `SetSoftLimits("targetAngle", …)`).
* **Rotation**: `AllowFullRotation` ← `allowFullRotation`.
* **Piston**: `MinExtension`/`MaxExtension` ← `softMinMaxExtension`.
* **Rotor**: `MaxTorque` (kN) ← `maxTorque`; `BrakePercentage` ← `brakePercentage`.
* **All four servos**: `IsMoving` (bool) — reflection into the protected `BaseServo.IsMoving()`
  (verify in-game).
* **Controller** (optional, keeps the existing method-heavy shape): `Enabled` ← `controllerEnabled`;
  `Play()`/`Stop()` ← `SequencePlay`/`SequenceStop`; `Playing` ← `SequenceIsPlaying`; `Position`
  (get/set) ← `SequencePosition`/`SetSequencePosition`; `Length` ← `SequenceLength`; `PlaySpeed` ←
  `SequencePlaySpeed`.

### 4. Expansion detection

Breaking Ground is a stock **expansion**, not a Bazel-installable mod, and has no per-mod
`.available` service — so the test harness cannot gate on it the way `mods=[…]` does. Add a new
in-game query and skip cleanly when absent:

* **`SpaceCenter.cs`** — new `[KRPCProperty] static IList<string> Expansions`, returning installed
  expansion names from `ExpansionsLoader.Instance.supportedExpansions` filtered by
  `IsExpansionInstalled(expansionName)` (all stub-public). Placed near `GameMode`.
* **`tools/krpctest/krpctest/__init__.py`** — add an `expansions = []` class attribute on `TestCase`
  (parallel to `mods`). In `ensure_game`, after the mod set is satisfied and connected, if any
  required expansion is missing from `conn.space_center.expansions`, `raise unittest.SkipTest(…)`.
  **Skip, never relaunch/install** — expansions can't be installed via the Bazel mechanism, so the
  `mods` install/reconcile path is untouched.

Rejected alternative: probing `GameData/SquadExpansion/Serenity` on disk — fragile and
path-dependent when a clean in-game API exists.

### 5. Integration tests + craft

* **`service/SpaceCenter/test/test_parts_robotic.py`** (new) — subclass `krpctest.TestCase`, set
  `expansions = ["Serenity"]`, `setUpClass` → `new_save()` → `launch_vessel_from_vab("PartsRobotic")`
  → `remove_other_vessels()`. Follows `test_parts_leg.py` and `service/InfernalRobotics/test/
  test_servo.py` (use `wait_while(lambda: servo.is_moving)` loops). Assert per type: Part identity +
  `Equals`; Hinge/Rotation `TargetAngle`→`CurrentAngle` convergence, `Min/MaxAngle`, `Rate`,
  `Damping`, `Locked`, `MotorEngaged`, `MoveHome`; Rotation `AllowFullRotation`; Piston
  `TargetExtension`→`CurrentExtension`, `Min/MaxExtension`, `MoveHome`; Rotor `TargetRPM`→`CurrentRPM`
  ramp, `Inverted`, `TorqueLimit`, `MaxTorque` (no `MoveHome`); Controller `HasPart`/`AddAxis`/
  `AddKeyFrame`/`ClearAxis`/`Axes` and the new `parts.robotic_controllers` collection.
* **`service/SpaceCenter/test/craft/PartsRobotic.craft`** (+ `.loadmeta`, new) — a vessel with all
  five robotic part types plus a controller. **Must be authored in the VAB on the BG-enabled
  install** (the harness's target KSP copy has no `GameData/SquadExpansion`); capture the exact
  Serenity part internal names there.

### 6. Docs / changelog / build wiring

* **`KRPC.SpaceCenter.csproj`** — add `<Compile Include="…">` for any **new** `.cs` file (none
  planned unless an enum is added). The five existing robotic files are already listed; Bazel globs
  `src/**/*.cs`, so no BUILD change.
* **`doc/api/space-center/parts.tmpl`** — `RoboticControllers` renders through the existing `Parts`
  macro (no new block). Add a `SpaceCenter.Expansions` entry to the SpaceCenter service template.
* **`service/SpaceCenter/CHANGES.txt`** — v0.6.0 bullets for the completion members, the fixes, and
  the `Expansions` RPC + harness gating, in the **dedicated pre-merge changelog commit only**.

## To verify in-game

Cannot be confirmed from the stub DLL:

1. `IsMoving()` reflection — exact method name/visibility per derived servo type.
2. Whether the public `Hinge.currentAngle` field is reliable enough to drop the existing
   `currentTransformAngle` reflection in `RoboticHinge.CurrentAngle`.
3. Exact Serenity part internal names for the craft (author on the BG install).
4. That the soft-limit write path (`SetSoftLimits(…)` vs direct `softMinMaxAngles`/
   `softMinMaxExtension`) actually moves the PAW limits.

## Build & test commands

```
bazel build //service/SpaceCenter //service/SpaceCenter:ServiceDefinitions
bazel test  //service/SpaceCenter/... //doc/...          # lint + docgen

# rebuild the generated Python stubs so tests see the new RPCs
bazel build client/python tools/krpctest && \
  pip install bazel-bin/tools/krpctest/krpctest-0.5.4.tar.gz \
              bazel-bin/client/python/krpc-0.5.4.tar.gz --force-reinstall --no-deps

pytest service/SpaceCenter/test/test_parts_robotic.py -v  # on the BG-enabled install
```
