# KerbalAlarmClock & RemoteTech — test coverage and API completion

**Status:** in progress — Phases 0 & 1 and the KAC half of Phase 2 done and merged as
[PR #982 "KerbalAlarmClock test coverage and Alarm API completion"](https://github.com/krpc/krpc/pull/982)
and [PR #981 "Add RemoteTech availability and antenna negative-path tests"](https://github.com/krpc/krpc/pull/981)
(2026-07-19, in-game validated: KAC 16/16, RemoteTech 12/12); the RemoteTech API bindings remain.
No GitHub issue yet — one should be filed. Two implementation notes that supersede the text below:
the mod *does* have a per-alarm fired flag — `KACAlarm.Triggered`, internal, which this doc missed
because it only surveyed the public surface — so the alarm-fired "event" shipped as a reflected
pollable `Alarm.Triggered` getter (clients observe firing via the existing expression-event/stream
mechanism) instead of wiring `onAlarmStateChanged` into a bespoke event RPC; and the KAC-authored
wrapper's `Remaining` has always thrown (it unboxes the mod's `KSPTimeSpan` as a double) — kRPC's
`Alarm.Remaining` is now computed from the alarm time instead.
Two kRPC services that wrap third-party KSP mods — **KerbalAlarmClock**
(KAC, service id 5) and **RemoteTech** (id 6) — have thin test coverage and expose only part of the
underlying mod API. This doc records the gaps found (including a genuine correctness bug), and the
plan to close them in two phases: (1) bring test coverage and build wiring up to par, (2) surface the
unexposed mod API.

Investigation disassembled the shipped mod DLLs with `ikdasm` (both live in the Bazel repo cache,
fetched from the `@kerbal_alarm_clock` / `@remotetech` `http_archive`s in `MODULE.bazel`:
**KAC v3.14.0.0**, **RemoteTech 1.9.12**). Reproducible:

```bash
KAC=$(find ~/.cache/bazel -path '*GameData/TriggerTech/KerbalAlarmClock/KerbalAlarmClock.dll' | head -1)
RT=$(find ~/.cache/bazel  -path '*GameData/RemoteTech/Plugins/RemoteTech.dll'                | head -1)
ikdasm "$KAC" > kac.il   # type KerbalAlarmClock.KACAlarm, KerbalAlarmClock.KerbalAlarmClock
ikdasm "$RT"  > rt.il    # type RemoteTech.API.API
```

Both are integration-tested manually against a live KSP with the mod installed (the `krpctest`
framework installs each managed mod and launches a craft); Bazel only *lints* the Python tests. This
is the same convention as SpaceCenter/InfernalRobotics/RemoteTech today.

---

## Phase 0 — correctness fixes (do first; they change the enum surface the tests assert)

* **`AlarmType` is missing `ScienceLab`.** The mod's `AlarmTypeEnum` has 19 values; kRPC's
  `service/KerbalAlarmClock/src/AlarmType.cs` has 18 (no `ScienceLab`). Both arms of
  `src/ExtensionMethods/AlarmTypeExtensions.cs` (`ToAlarmType`/`FromAlarmType`) end in
  `default: throw new ArgumentException(...)`, so **`Alarm.Type` throws on any science-lab alarm** and
  `AlarmsWithType(science_lab)` can't be expressed. Fix = add `ScienceLab` to the enum + both switch
  arms. This is user-visible (new enum value; a getter stops throwing) → changelog entry.
* **`AlarmAction` can't represent `Custom`/`Converted`.** The KAC-authored wrapper's `AlarmActionEnum`
  stops at `PauseGame` (6 values); the mod's has 8 (`Custom` = 6, `Converted` = 7). Because
  `AlarmActionExtensions.ToAlarmAction()` also `default: throw`s, **the `Action` getter throws for an
  alarm whose action is either of those**. Add both to `src/AlarmAction.cs` and both switch arms.
  Lower-frequency than `ScienceLab` but the same class of latent throw.

---

## Phase 1 — test coverage and build wiring

### KAC tests — rewrite `service/KerbalAlarmClock/test/test_kerbalalarmclock.py`

Today it has three trivial empty-state checks and a literal `# TODO: expand the KAC tests`; it never
calls `CreateAlarm`, so no `Alarm` object is ever constructed and the whole `Alarm` class is
untested. Rewrite modeled on `service/SpaceCenter/test/test_alarm.py` (the stock AlarmManager suite —
create/remove/`tearDown`/negative-path style).

* **Craft:** add one minimal stock craft `service/KerbalAlarmClock/test/craft/KerbalAlarmClock.craft`
  (bare probe core + battery — KAC alarms don't reference mod parts). Needed only because
  `Alarm.Vessel`'s getter does `FlightGlobals.Vessels.First(x => x.id.ToString() == alarm.VesselID)`
  and throws unless a matching vessel exists — so round-tripping `Vessel` requires a launched vessel.
  `XferOriginBody`/`XferTargetBody` hit `FlightGlobals.Bodies` and need no craft. Craft files are
  finicky and need in-game validation; adapt a simple existing craft under
  `service/SpaceCenter/test/craft/`.
* **`setUpClass`:** `new_save()` → `launch_vessel_from_vab("KerbalAlarmClock")` →
  `remove_other_vessels()` → connect `kerbal_alarm_clock` + `space_center`.
* **`tearDown`:** `for alarm in list(self.kac.alarms): alarm.remove()`.
* **Methods:** `test_available`; `test_create_alarm`; `test_alarms_reflects_created`;
  `test_alarm_with_name` (found + `None` for missing); `test_alarms_with_type` (raw vs maneuver
  filter); `test_property_action` (every `AlarmAction` value); set→get round-trips for
  `margin`/`time`/`name`/`notes`/`repeat`/`repeat_period`; `test_property_type_readonly`;
  `test_property_xfer_bodies` (Kerbin/Duna); `test_property_vessel` (set to active vessel, read back);
  `test_enum_values` (pins the `AlarmType`/`AlarmAction` member sets — where the new `ScienceLab` /
  `Custom` / `Converted` values are asserted); `test_remove`; and `test_access_after_remove_raises` /
  `test_remove_twice_raises` (enabled by the Remove-guard fix below).

### RemoteTech tests — extend existing files (don't add new ones)

Comms and Antenna happy paths are already well covered (`test_comms.py`, `test_antenna.py`). Gaps:

* `test_remotetech.py`: add `test_available` → `assertTrue(self.rt.available)` (never asserted today).
* `test_antenna.py` (already launches the `RemoteTech` craft + antenna fixture) — add negative paths
  (kRPC maps server exceptions to client `RuntimeError`):
  * `test_target_invalid_setter_raises` — `target = Target.celestial_body` raises (`Antenna.cs:86`).
  * `test_target_body_getter_wrong_type_raises` (`:97`),
    `test_target_ground_station_getter_wrong_type_raises` (`:112`),
    `test_target_vessel_getter_wrong_type_raises` (`:129`) — read the typed getter while
    `target == none`.
  * `test_unknown_ground_station_setter_raises` — `target_ground_station = "Nowhere"` (`:117`).
* Add tests for the new Phase 2 members alongside these.

### Build wiring — KAC is orphaned

`service/KerbalAlarmClock/BUILD.bazel` has **no test/lint rules at all**, and KAC is **absent from the
top-level `//:test` and `//:lint`** (RemoteTech and InfernalRobotics are present). So the KAC test is
neither run nor linted by any Bazel target.

* Add `load("//tools/build:python.bzl", "py_lint_test")` and the RemoteTech-style trio to
  `service/KerbalAlarmClock/BUILD.bazel`: `test_suite(name="test", tests=[":lint"])`,
  `test_suite(name="lint", tests=[":pylint"])`, and
  `py_lint_test(name="pylint", size="small", srcs=glob(["test/*.py"]),
  pylint_config="test/pylint.rc", deps=["//client/python:krpc_lib", "//tools/krpctest:krpctest_lib"])`.
* Add `service/KerbalAlarmClock/test/pylint.rc` — copy of `service/RemoteTech/test/pylint.rc`.
* In root `BUILD.bazel`, insert `"//service/KerbalAlarmClock:test"` into the `//:test` list and
  `"//service/KerbalAlarmClock:lint"` into the `//:lint` list (alphabetically, just before the
  RemoteTech entries).

---

## Phase 2 — API completion

Architecture: KAC additions touch **both** the vendored reflection shim
`service/KerbalAlarmClock/src/KACWrapper.cs` (add the reflected field/property) **and** `Alarm.cs`
(expose it). RemoteTech additions touch `service/RemoteTech/src/API.cs` (bind the delegate) **and**
`Comms.cs`/`Antenna.cs`/`RemoteTech.cs`. Every new member needs an integration test and a client-stub
regeneration; all are user-visible → changelog entries.

### KAC alarm-fired event — the headline gap

KAC alarms have **no `Triggered`/`Actioned` field** (unlike stock SpaceCenter alarms), so the only way
to observe an alarm firing is the mod's `onAlarmStateChanged` event
(`AlarmStateChangedEventArgs{alarm, eventType}`, enum
`AlarmStateEventsEnum{Created, Triggered, Closed, Deleted}`). The KAC-authored wrapper already
**declares** this event (currently unused by kRPC). Surface it as a kRPC event/stream:

* Expose `AlarmStateEventsEnum` as a new `[KRPCEnum]`.
* Subscribe in `Addon.cs` (or the service) and expose either a `KerbalAlarmClock`-level event RPC or a
  pollable state — **decide by matching kRPC's existing event mechanism** (before implementing, study
  a service that already returns a `KRPC.Service.Event` / how streams back events, e.g. in
  SpaceCenter). This is the highest-risk item — needs in-game validation (create alarm → time-warp to
  fire → observe delivery).

### KAC alarm fields (wrapper omits; low effort)

* `Alarm.Enabled` (bool, get/set) — mod `KACAlarm.Enabled`; per-alarm enable/disable.
* `Alarm.PlaySound` (bool, get/set) — mod `KACAlarm.PlaySound`.
* `Alarm.SupportsRepeat` / `SupportsRepeatPeriod` (bool, get) — let clients gate the `Repeat` /
  `RepeatPeriod` setters.
* Skip (redundant/internal/GUI): `PauseGame`/`HaltWarp`/`ShowMessage` derived flags, `ManNodes`
  (would need `Node` wrapping — defer), `ContractGUID`/`ContractAlarmType` (niche — defer), all
  `AlarmWindow*`/`AlarmLine*` GUI fields.

### `Alarm.Remove()` object-cleanup guard

`Alarm.cs` `Remove()` calls `KACWrapper.KAC.DeleteAlarm(alarm.ID)` but leaves the `alarm` field
non-null (it carries a `// TODO: delete this object`). After removal, getters still read the orphaned
wrapper object — stale data or an unhelpful reflection error, instead of the clean "does not exist"
signal SpaceCenter gives. `service/SpaceCenter/src/Services/Alarm.cs` is the parity model: its
`Remove()` nulls the internal reference and a guard throws
`InvalidOperationException("Alarm does not exist")` on any later access, which
`service/SpaceCenter/test/test_alarm.py` asserts (`test_access_after_remove_raises`,
`test_remove_twice_raises`; client sees `RuntimeError`).

Fix (≈15 lines): make `alarm` non-`readonly`; in `Remove()` set it `null` after `DeleteAlarm`; add a
private `CheckExists()` throwing `InvalidOperationException("Alarm does not exist")` and call it at the
top of every getter/setter and `Remove()`. (kRPC server proxies are client-lifecycle-managed, so the
server can't evict the proxy handle itself — the meaningful in-scope fix is this SpaceCenter-parity
guard, not object-registry surgery.) This is what makes the two new access-after-remove tests
meaningful. Not user-visible behavior worth a changelog on its own (it corrects a never-released dev
surface), but ships with the test additions.

### RemoteTech — bind unexposed `RemoteTech.API.API` methods

`RemoteTech.API.API` exposes ~34 public static methods; the hand-written wrapper
`service/RemoteTech/src/API.cs` binds 17. The unbound remainder, best value first:

| Mod method (unbound) | Suggested kRPC shape |
|---|---|
| `GetControlPath(Guid)→Guid[]` | `Comms.ControlPath` — read-only list, the full signal route |
| `HasDirectGroundStation(Guid)→bool` | `Comms.HasDirectGroundStationConnection` (distinct from `HasConnectionToKSC`) |
| `GetClosestDirectGroundStation(Guid)→string` | `Comms.ClosestDirectGroundStation` |
| `GetFirstHopToKSC(Guid)→string` | `Comms.FirstHopToKSC` |
| `Get/SetRadioBlackoutGuid` | `Comms.RadioBlackout` (get/set bool) |
| `Get/SetPowerDownGuid` | `Comms.PowerDown` (get/set bool) |
| `GetMaxRangeDistance` / `GetRangeDistance(a,b)` | `Antenna`/`Comms` range-math methods |
| `AddGroundStation` / `RemoveGroundStation` / `ChangeGroundStationRange` | service-level `RemoteTech` methods (ground-station management) |
| `IsRemoteTechEnabled()→bool` | `RemoteTech.Enabled` (RT enabled in difficulty; distinct from `Available`, which only checks assembly load) |

Skip internal/complex: `EnableInSPC`, `GetName`, `QueueCommandToFlightComputer`,
`InvokeOriginalEvent`. `AddSanctionedPilot`/`RemoveSanctionedPilot` stay internal — SpaceCenter's
`PilotAddon` consumes them; they are not user-facing RPCs. Ground-station add/remove tests need a
`tearDown` restoring the default station set.

---

## Phase 3 — KAC alarm-action model

`Alarm.Action` is a thin mirror of the mod's `AlarmActionEnum`, which in KAC v3.14 is itself only a
backwards-compatibility shim. The mod's live model is the `AlarmActions` object on `KACAlarm`:

* `Warp` — `DoNothing` / `KillWarp` / `PauseGame`
* `Message` — `No` / `Yes` / `YesIfOtherVessel`
* `DeleteWhenDone` — bool
* `PlaySound` — bool

The legacy enum survives only as the `KACAlarm.AlarmActionConvert` property kRPC binds. Its **setter**
expands each enum value to one fixed preset; its **getter** pattern-matches the four components back,
returning `Custom` for any combination that is not one of the six presets:

| `AlarmActionEnum` value | Components set |
|---|---|
| `KillWarpOnly` | `Warp=KillWarp, Message=No` |
| `KillWarp` | `Warp=KillWarp, Message=Yes` |
| `MessageOnly` | `Warp=DoNothing, Message=Yes` |
| `PauseGame` | `Warp=PauseGame, Message=Yes` |
| `DoNothingDeleteWhenPassed` | `DeleteWhenDone=true` |

So kRPC can express only six of the 36 reachable component combinations. Notably *kill warp **and**
delete when done*, *pause without a message*, and the `YesIfOtherVessel` message mode are all
unreachable, and writing `Custom`/`Converted` is silently ignored (both switch arms are no-ops in the
mod).

**Fix:** expose the components as their own properties — `WarpAction`, `MessageAction`,
`DeleteWhenDone` — with two new `[KRPCEnum]`s (`WarpAction`, `MessageAction`), keeping `Action` as a
preset shortcut over them. Additive, except that `Action`'s getter would keep returning `Custom` once a
script sets a non-preset combination — worth a docstring note rather than a `**Breaking:**` marker.

Two traps found while confirming the above, both to be handled by this phase:

* **`Alarm.PlaySound` (shipped in Phase 2) is a no-op.** It binds `KACAlarm.PlaySound`, which is
  `[Persistent]` — so it round-trips through the getter and survives save/load (which is why the Phase 1
  round-trip test passes) — but is read by *no* code path in `KerbalAlarmClock.dll` (verified by
  `ikdasm`: zero `ldfld`/`ldflda` sites). The field KAC actually honors is `Actions.PlaySound`.
  Rebinding it is a user-visible behavior fix and needs a changelog entry.
* **Writing `Action` clobbers sibling state.** Every `AlarmActionConvert` preset also assigns
  `DeleteWhenDone` and `Actions.PlaySound` (all six set `PlaySound=false`), so setting `Action` after a
  corrected `PlaySound` would silently reset it. Ordering matters, and the component properties above
  are the real fix.

---

## Recommendation / sequencing

Phase 0 and Phase 1 (fixes + tests + wiring) are low-risk and unblock CI lint coverage for KAC — do
them first, in that order (Phase 0 changes the enum surface the Phase 1 `test_enum_values` asserts).
Phase 2's field additions and the RemoteTech bindings are mechanical (wrapper delegate + property +
test each). The KAC alarm-fired **event** is the one genuinely uncertain piece (kRPC event plumbing)
and should be validated in-game before the changelog commit. All Phase 0/2 API changes are additive —
no member removals, no enum reordering — so no `**Breaking:**` markers are expected (adding enum values
at the end preserves existing wire values).

## Critical files

* KAC: `service/KerbalAlarmClock/src/{AlarmType.cs,AlarmAction.cs,Alarm.cs,KerbalAlarmClock.cs,
  Addon.cs,KACWrapper.cs}`, `src/ExtensionMethods/{AlarmTypeExtensions.cs,AlarmActionExtensions.cs}`,
  `test/test_kerbalalarmclock.py` (+ `test/craft/KerbalAlarmClock.craft`, `test/pylint.rc`),
  `BUILD.bazel`.
* RemoteTech: `service/RemoteTech/src/{API.cs,Comms.cs,Antenna.cs,RemoteTech.cs}`,
  `test/{test_remotetech.py,test_comms.py,test_antenna.py}`.
* Root `BUILD.bazel` (`//:test`/`//:lint` lists).
* References: `service/SpaceCenter/test/test_alarm.py` (test style),
  `service/SpaceCenter/src/Services/Alarm.cs` (Remove-guard pattern),
  `service/RemoteTech/{BUILD.bazel,test/pylint.rc}` (BUILD mirror).

## Changelogs

`service/KerbalAlarmClock/CHANGES.txt` and `service/RemoteTech/CHANGES.txt` under `v0.6.0`, plus the
touched `client/*/CHANGES.txt` for the new RPC surface — in the dedicated final pre-merge commit only
(per CLAUDE.md). Entries: the `ScienceLab`/`AlarmAction` enum fixes, the new KAC alarm fields + event,
and the new RemoteTech members. The Remove-guard fix and all test/BUILD changes are not user-visible
relative to v0.5.4 and get no entry.
