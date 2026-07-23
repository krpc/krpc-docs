# Locale hardening

**Status:** done — merged to `main` as [PR #993](https://github.com/krpc/krpc/pull/993). One piece
was split out and did **not** ship in #993: the .NET culture-analyzer config (`Directory.Build.props`
+ `.editorconfig`; *Structural immunity* #2 / item 4 below), which is not yet merged and is tracked in
[`design/build-tools/culture-analyzers.md`](build-tools/culture-analyzers.md). This doc is a
historical record of the design.

Audit and remediation plan for locale-dependent behavior across kRPC. Baselined against the part
deployment-state consolidation ([PR #986](https://github.com/krpc/krpc/pull/986)).

## Problem

kRPC has two independent locale exposures, and they fail in different ways.

**1. KSP's UI language.** Players run KSP in Spanish, Russian, Japanese, Chinese, German. Several
kRPC part wrappers identify a `PartModule` event, action or field by its *display name*, which the
game translates. Those code paths silently do nothing, or silently report a wrong value, for every
non-English player. This is the more serious class: it is invisible in testing (the English
rendering matches the hardcoded literal exactly, which is why it was never noticed) and it produces
wrong answers rather than errors.

**2. The CLR / OS culture.** kRPC never pins a culture, so `CurrentCulture` follows the player's OS
locale. Numbers formatted into RPC return values pick up a decimal comma under `de-DE`/`fr-FR`, and
`ToUpper()` on an ASCII identifier picks up a dotted capital I under `tr-TR`.

A third, smaller exposure sits in the build and code-generation toolchain, where the developer's
locale can affect generated output and file decoding.

## Evidence

The KSP-side facts were established by disassembling the real `Assembly-CSharp.dll`
(`monodis`, 2.89M lines of CIL) and cross-checking `GameData/Squad/Localization/dictionary.cfg`.

`GameDatabase.translateLoadedNodes()` calls `Localizer.TranslateBranch` over every loaded config
node *before* any `PartModule` is constructed, and `TranslateBranch` replaces each config value with
`Localizer.Format(...)`. So any `KSPField`/`KSPEvent` string whose config value or attribute default
is a `#autoLOC_` tag is already translated by the time kRPC reads it.

What is translated:

 * `BaseEvent.guiName`, `BaseField.guiName`, `BaseAction.guiName` — all three setters call
   `Localizer.Format`.
 * `AvailablePart.title`, `ScienceExperiment.experimentTitle`, `BaseConverter.ConverterName`,
   `ModuleAnimateGeneric.status`, `BaseConverter.status`, `ModuleAnimateGeneric.startEventGUIName`.

What is invariant, and is therefore the correct thing to match on:

 * `BaseEvent.name`, `BaseField.name`, `BaseAction.name` — these equal the C# member name.
 * `AvailablePart.name`, `PartModule.moduleName`, `CelestialBody.name`.
 * `ModuleDockingNode.state` — KerbalFSM state names are hardcoded English literals, no `Localizer`.
 * `CBAttributeMapSO.MapAttribute.name` — biomes. kRPC correctly calls `ScienceUtil.GetExperimentBiome`
   (reads `name`) and not `GetExperimentBiomeLocalized` (reads `displayname`).

KSP's own `Events[...]`, `Fields[...]` and `Actions[...]` indexers are all **name**-keyed:
`BaseEventList` hashes the string and compares `BaseEvent.id`, which the constructor sets from
`name.GetHashCode()`. So the invariant lookup is also the more direct one.

The specific tags involved:

| Tag | English rendering | Invariant member name |
|---|---|---|
| `#autoLOC_6001445` | `Undock` | `Undock` |
| `#autoLOC_6001446` | `Decouple Node` | `Decouple` |
| `#autoLOC_6002396` | `Deploy` | `DeployFairing` |
| `#autoLOC_215506` | `Moving...` | use `ModuleAnimateGeneric.aniState` |

Note `Part.TriggerVisibleEvent` / `HasVisibleEvent` are **not** KSP APIs — they are kRPC's own
`internal` helpers on `Services.Parts.Module`, and they match on `guiName`. That is the root cause
of most of class 1.

## Class 1 — KSP-language bugs

| Site | Symptom for a non-English player |
|---|---|
| `DockingPort.cs:134` `InvokeEvent("Undock")` | `Undock()` is a silent no-op; ports stuck permanently |
| `Fairing.cs:73,95` `"Deploy"` | `Jettison()` no-op; `Jettisoned` always `true` |
| `ResourceConverter.cs:130-140` parses `status` | `MissingResource`/`StorageFull`/`Capacity` unreachable |
| `DockingPort.cs:352` `status.StartsWith("Moving")` | Shielded port mid-animation reports `Shielded`, never `Moving` |
| `CargoBay.cs` `guiName == "Open"/"Close"` | `Open` setter no-op; `State` misreports `Deploying`/`Retracting` |
| `RoboticController.cs:157,185,214` | Requires the *translated* PAW label |
| `Parts.cs:101` `WithTitle` | Returns empty for an English title |

`RoboticController` is additionally self-inconsistent: `Axes()` returns the invariant
`AxisField.name`, so its own output cannot be fed back into `AddKeyFrame`/`ClearAxis`. Fixing it to
match `name` makes the API round-trip, which is the stronger argument than the locale one.

`Parts.WithTitle` is not really fixable — matching a localized display title is the *point* of the
method. Document it as locale-dependent and steer users to `WithName`.

`Parachute.cs` (RealChute) matches English `guiName`s. Disassembling `RealChute.dll` shows it
contains no `Localizer` or `autoLOC` references at all, so it is safe in practice today, but it
rides the same fragile mechanism and should move to `name` matching for consistency. PR #960 already
fixed a *casing* bug here, which shows how brittle display-name matching is even within one language.

### Fix

`Services/Parts/Module.cs` already carries both flavors of the public API — `HasEvent`/`TriggerEvent`
(guiName-keyed) and `HasEventWithId`/`TriggerEventById` (name-keyed) — all four `[Obsolete]` in
favor of the `EventList`/`PartEvent` object API added by #859. That is the right template and needs
no redesign.

The bug is that the three `internal` helpers `VisibleEventNames`, `HasVisibleEvent` and
`TriggerVisibleEvent` are guiName-based and serve *two* different callers:

 * the deprecated guiName-keyed public API — where guiName matching is the documented contract, and
   is correct;
 * kRPC's own part wrappers (`Fairing`, `Parachute`) — where it is a bug.

So: add name-keyed `internal` siblings, move the part wrappers onto them, and leave the guiName
helpers serving only the deprecated public API. Similarly, `PartModuleExtensions.InvokeEvent` should
match `name`; every one of its call sites wants the invariant id.

`DockingPort` shield state moves from parsing `status` to reading the `ModuleAnimateGeneric.aniState`
enum — `UpdateAnimSwitch` sets `aniState = MOVING` on the instruction immediately before writing
`status`, so the two are exactly equivalent.

`ResourceConverter` is the awkward one: there is no clean numeric backing field for the three failure
states. Resolved by asking the game to translate the same `#autoLOC` messages it builds the status
from, formatting them with an empty placeholder argument to leave just their fixed part, and matching
that against the status. Comparison there is deliberately culture-sensitive — both sides are text the
game has translated, which is the one place that is correct. Structural derivation from the part's
`resHandler` would be cleaner still but is a larger change; this keeps the fix proportionate.

The tags are `#autoLOC_261263`/`#autoLOC_261304` (missing resource), `#autoLOC_258451`/
`#autoLOC_259933` (insufficient power), `#autoLOC_261334` (storage full) and `#autoLOC_261332`
(output cap). The residual risk is a language whose translation strips to a fragment short enough to
match an unrelated status; the fragments are guarded against being empty, but not against being
short.

## Class 2 — CLR culture

| Site | Failure |
|---|---|
| `Module.cs:186,201,220,265,276`, `PartField.cs:129` | `GetValue(module).ToString()` on a boxed float → `"92,5"` under `de-DE`; every client's float parse throws |
| `Sensor.cs:91,99,103,108` | Same, on an RPC return value |
| `TypeUtils.cs:629` `snakeCase.ToUpper()` | Turkish-I. Feeds the type `code` field into `GetServices`, the wire, and the generated service-definitions JSON — a hard protocol break under `tr-TR` |
| `UI.cs:85` `size.ToString()` | Unity rich-text parser is invariant-only; `<size=20,5>` renders as literal text |
| `TypeUtils.cs:105`, `Expression.cs:522`, `DockingPort.cs:342,352`, `WaypointManager.cs:96` | `StringComparison.CurrentCulture` where `Ordinal` is meant |

`PartField.cs:144-192`'s `Convert.ToBoolean/ToInt32/ToSingle/ToDouble` are **safe** — the boxed
operand is already numeric, so `IConvertible` never consults the culture. Only the `ToString()`
direction is affected. Likewise `Configuration.cs`'s `uint.TryParse` with `NumberStyles.Integer`
rejects group separators.

`Sensor.Value` was initially flagged here as a wire bug and is **not** one. It deliberately calls
`Localizer.Format` to reproduce the in-game readout, and disassembly shows `ModuleEnviroSensor`
formats the number with `ToString("0.##")` and friends under the ambient culture — the identical
format strings kRPC uses. So kRPC currently matches the game exactly in every locale, and making the
number invariant would make it diverge for the first time, defeating the property the code was
written to have. Left as-is; the docstring now says it is for display rather than parsing and points
at the numeric alternatives.

## Class 3 — toolchain

 * `tools/krpctools/krpctools/servicedefs/__init__.py:46,105` — `open()` with no `encoding=` on the
   .NET-emitted UTF-8 JSON. Reproduced: `LC_ALL=C` gives `UnicodeDecodeError`, because 17 service
   `.cs` files contain non-ASCII (`°`, `×`, em-dash) in their XML doc comments. Sibling modules in
   `clientgen` and `docgen` all pass `encoding="utf-8"`, so this is an oversight. Bazel invokes the
   C# binary directly, so CI never exercises it — only the shipped `krpc-clientgen --ksp` CLI breaks.
 * `tools/krpctools/krpctools/clientgen/__init__.py:94` — same, on the output side.
 * `client/lua/krpc/service.lua:22` — `:lower()` in `to_snake_case` is libc `tolower`, driven by
   `LC_CTYPE`, and mangles every method name users call. Conditional: bites under single-byte Turkish
   charsets, probably not under `tr_TR.UTF-8`. Not empirically verified — no Turkish locale installed.
 * **No locale is pinned anywhere.** Zero hits for `LC_ALL`/`LANG=`/`setlocale` across `.bazelrc`,
   the workflows and the buildenv Dockerfile. CI runs implicitly POSIX/C, developers run `$LANG`, and
   nothing enforces the match.
 * `tools/build/sphinx.bzl:70`, `tools/build/image.bzl:10` — `use_default_shell_env = True` inherits
   the user's environment, and env vars set that way are not part of the action key, so Bazel can
   cache divergent artifacts under the same key.

## Structural immunity

The individual fixes above are cleanup. Three changes prevent the classes from recurring:

 1. **Name-keyed event/field lookup helpers**, with the guiName ones confined to the deprecated
    public API. Kills class 1 at the source.
 2. **Enable the .NET culture analyzers.** The repo currently has *no* C# static analysis — no
    `.editorconfig`, no `Directory.Build.props`, and all projects target `net472` where the CA rules
    are off by default, so CA1304/CA1305/CA1307/CA1310/CA1311 are all inactive. A root
    `Directory.Build.props` plus an `.editorconfig` promoting them to warnings catches every class 2
    finding. Caveat: only CI's `build-csharp-sln` job builds from the `.csproj` files, so this gates
    CI but not local Bazel builds — the same asymmetry [`CLAUDE.md`](../CLAUDE.md) already documents for missing
    `<Compile Include>` entries.
 3. **Pin `LC_ALL=C.UTF-8`** in the root `.bazelrc` (`--action_env`/`--test_env`), the workflows and
    the buildenv image, and replace the two `use_default_shell_env` uses with explicit `env`.

## Changelog

Entries are on the branch, in a single final commit. Five components changed and were given entries:
`service/SpaceCenter`, `service/UI`, `core`, `client/lua` and `tools/krpctools`. `service/UI` had no
`v0.6.0` header yet, so one was created.

One entry carries a `**Breaking:**` marker:

 * `RoboticController.AddAxis`, `AddKeyFrame` and `ClearAxis` now take the axis field's name rather
   than the label shown in the part's menu. `RoboticController` shipped in v0.5.0 and has been in
   every release since, so this changes behavior for existing callers — English ones included, who
   were previously passing `"Target Angle"` and must now pass `"targetAngle"`. The upside is that
   the names now round trip through `Axes()`, which always returned the field name and so could
   never be fed back in. `test_parts_robotic.py` asserts both the round trip and that the display
   name is rejected.

Two changed components were deliberately left without entries, since neither changes behavior
relative to v0.5.4:

 * `client/csharp` — `Encoder` now formats the small non-negative integers it splices into tuple type
   names (`System.Tuple\`2`, `Item1`) with the invariant culture. No culture in use formats those
   differently, so the fix is hardening against a latent hazard, not a behavior change. It is
   covered by the analyzer commit.
 * `tools/build`, `.bazelrc`, `Directory.Build.props`, `.editorconfig`, `tools/TestServer` — build
   and test infrastructure, none of it on the release version train.

Everything else in this work either fixes behavior that was already broken for non-English
players (no API change) or is internal.

## Public API contract

Separate from the bugs: some RPCs return localized strings, with no invariant alternative exposed.
Changing these is breaking, so they are called out rather than fixed.

 * `Part.Title`, `Experiment.Title` — localized, but each has an invariant `Name` counterpart. Fine;
   needs a docstring note only.
 * `ScienceSubject.Title` — fully localized, and `ScienceSubject` exposes **no** invariant id, unlike
   `Experiment`. Worth adding an `Id` member returning the `subjectId` kRPC already builds at
   `Experiment.cs:245`.
 * `ResourceConverter.Name(index)` — `ConverterName` is `#autoLOC_502026` in stock configs, so this
   is localized with no invariant alternative. Clients that key converters by name break across
   locales.
 * `ResourceConverter.StatusInfo(index)`, `Sensor.Value` — documented as returning the in-game UI
   string, so localized by design. Correct as-is.
 * `Part.Config` returns `partInfo.partConfig`, which `translateLoadedNodes` has already mutated in
   place, so `Config.GetValue("title")` returns translated text. Docstring note.
 * `Contract.Title/Description/Notes/Synopsis`, `Waypoint.Name` — narrative text, localized by
   nature, no invariant form exists.

## Out of scope

 * Translating kRPC's own output. This is about locale *independence*, not localization.
 * `Parts.WithTitle` semantics.
 * The incidental non-locale bugs found in passing: `clientgen/__init__.py:150`'s
   `"".join(fp.readlines()).decode("utf-8")` raises `AttributeError` unconditionally on Python 3
   (dead `load_generator` path), and line 147's `rstrip(".py")` is a character-set strip, not a
   suffix strip, so a generator named `mypy.py` becomes `m`. Worth their own issue.

## Status

Eight changes in total. Seven merged to `main` in
[PR #993](https://github.com/krpc/krpc/pull/993); item 4 (the analyzer config) was split out and is
not yet merged — see the note at the top.

 1. Identify part module events by id rather than display name — `Module.cs` name-keyed helpers,
    `PartModuleExtensions.InvokeEvent`, `DockingPort` (undock, shield toggle, shield state via
    `aniState`), `Fairing`, `CargoBay`, `RoboticController`.
 2. Use the invariant culture for values crossing the wire — `BaseFieldExtensions.GetValueString`,
    `TypeUtils` type code, HTTP/websocket protocol tokens, ordinal comparisons.
 3. Make the build and the code generators locale independent — generator encodings, Lua ASCII fold,
    `LC_ALL` pin in `.bazelrc` and the two `use_default_shell_env` actions.
 4. Report culture dependent calls as build warnings — `Directory.Build.props` + `.editorconfig`,
    plus the calls they found in `Logger`, `TCPServer` and the C# client's `Encoder`. **The analyzer
    config itself was split out of #993 and is not yet merged; the culture
    fixes it surfaced (`Logger`/`TCPServer`/`Encoder`) did merge.**
 5. Recognize converter status by message rather than English text.
 6. Report cargo bay state from the direction of its animation — `State`, `Open` and the setter all
    read the animation, and `ClosedAndLocked` is no longer consulted. See below.
 7. Name robotic controller axes by field name in the tests.
 8. Add changelog entries.

### The cargo bay state getter

Both the ramp defect and the `test_service_bay` flake turned out to be the same root cause, and are
fixed together.

`CargoBay.State` asked `ModuleCargoBay.ClosedAndLocked()` first, and only then whether the animation
was moving. That predicate is `IAirstreamShield.ClosedAndLocked` — it answers "are the parts inside
sheltered", not "are the doors shut". Disassembly shows it requires `SelfClosedAndLocked` on this bay
*and* on every entry of `connectedCargoBays`, and `SelfClosedAndLocked` in turn requires `EndCapped()`,
which returns false whenever an outer attach node has nothing attached to it or the attachment does
not fit.

So a bay whose open end is unobstructed is never closed-and-locked, and a shut Mk3 Cargo Ramp
reported `Deployed`. That is what made the `Open` setter a no-op once it stopped reading the button
label.

Getting from there to a getter that does not race took two attempts, and the failures are worth
recording because both were the same mistake in different clothes: **deriving a resting state from a
quantity that settles asynchronously.**

 * Ordering the checks so `ClosedAndLocked()` came first meant that any moment where that bookkeeping
   read true while the doors were traveling made `Retracted` win over `Retracting` — the
   `test_service_bay` signature.
 * Checking `IsMoving()` first and then comparing the animation scalar against `closedPosition`
   moved the race rather than removing it. `IsMoving()` goes false a frame before the scalar lands
   exactly on its end, so a bay that had just finished shutting reported `Deployed` until the last
   frame arrived. This surfaced as `test_cargo_ramp` reading `deployed` where `retracted` was
   expected. No epsilon fixes this honestly; the scalar is simply the wrong signal.

What works is reading the *direction* instead of the position. `animSwitch` says which end the
animation is traveling to, and a bay that is not moving is sitting at the end it last traveled to,
so a single expression answers for both:

    OpeningOrOpen  ==  !animSwitch == (closedPosition < 0.5)

`State` is then `Deploying`/`Retracting` when `IsMoving()`, and `Deployed`/`Retracted` when not, off
that one predicate; `Open` is the predicate itself. Getter, setter and `State` can no longer disagree,
and nothing depends on a value that settles a frame late. Checked against all eight
(part, animSwitch, closedPosition, situation) combinations captured from in-game instrumentation,
including a service bay that was never toggled — which is the evidence that `animSwitch` is
initialized correctly at load and not only after a toggle.

Nothing is lost by dropping `ClosedAndLocked`: airstream shielding is already exposed separately as
`Part.Shielded`.

The test's `wait_while` carried a comment describing the lock-lag window as something to be waited
out. That window no longer exists, so the wait now simply waits for the close to finish.

Not done, and deliberately so: the ProceduralFairings jettison path still matches display names,
because that mod is not installed here and its method names could not be verified; `Parts.WithTitle`
is unchanged; and the public-API contract items below are untouched.

Verification: `0 Warning(s)` from `dotnet build KRPC.sln -warnaserror` across every project that
compiles in this environment (`core/test` fails on a missing `Moq` external, which predates this
work and resolves in CI). `//core:test`, `//client/lua:test`, `//tools/krpctools:test` and the lint
targets pass under the pinned locale.

## Validation

`test_parts_docking_port.py`, `test_parts_fairing.py`, `test_parts_cargo_bay.py`,
`test_parts_robotic.py` and `test_parts_resource_converter.py` cover the changed paths and must pass
in-game. They run in English, so they verify no regression but cannot prove the locale fix — for
that, the argument is the disassembly evidence above plus the fact that name-keyed lookup is what
KSP's own indexers do.
