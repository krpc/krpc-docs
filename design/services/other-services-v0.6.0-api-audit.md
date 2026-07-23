# Other services public API audit — v0.5.4 → v0.6.0

**Status:** audit — public RPC surface of every service *except* SpaceCenter, `v0.5.4` → `v0.6.0`
development HEAD, for release-note preparation. No standalone issue. Companion to the
[SpaceCenter audit](spacecenter-v0.6.0-api-audit.md), which discharges follow-up 3 of that
document (confirm the same audit for the other services on the release train).

Covers the core **KRPC** service plus the mod services **DockingCamera**, **Drawing**,
**InfernalRobotics**, **KerbalAlarmClock**, **LiDAR**, **RemoteTech** and **UI**. Same two goals as
the SpaceCenter audit: (1) enumerate breaking changes and deprecations, and (2) confirm nothing was
removed that could instead have been deprecated.

## Method

Diffed the full attributed RPC surface (`[KRPCService]`, `[KRPCProcedure]`, `[KRPCMethod]`,
`[KRPCProperty]`/`[KRPCField]`, `[KRPCClass]`, `[KRPCEnum]` + enum members, and property setter
status) between the `v0.5.4` tag and HEAD for each service. The 0.5.4 baseline was cross-checked
against the generated client bundled in-tree at
`assets/files/krpc-genfiles-0.5.4/bazel-bin/client/csharp/Services/`, and findings against each
service's `CHANGES.txt`.

## Headline results

* **Removals: none.** Across all seven services, no procedure, method, property, class, enum, or
  enum value was removed or renamed off the wire. Every enum changed this cycle was *appended to*
  only — no member was reordered or removed — so wire encodings stay compatible.
* **Signature / type breaks: none.** Unlike SpaceCenter (which had three), none of these services
  changed a parameter list, return type, or property setter status of an existing member. Every
  surface change is purely additive.
* **Deprecations: one** — `KRPC.CurrentGameScene`, renamed to `KRPC.GameScene` but retained as an
  `[Obsolete]` read-only alias, so the old procedure key still resolves (#897, #904).
* Several **behavioral** changes (same signature, different result or availability) worth a
  release-note line, listed at the end.

## Per-service summary

| Service | Removals / renames | Sig/type breaks | Deprecations | Additive | Behavioral |
|---|---|---|---|---|---|
| **KRPC** (core) | none | none | `CurrentGameScene` → `GameScene` alias | settable `GameScene`, 5 new `GameScene` values, wire `Deprecated` metadata | scene values 5–9 now returned; `GetServices` reports game scenes |
| **InfernalRobotics** | none | none | none | `ServoMode` enum, 24 new `Servo` members, 6 new `ServoGroup` members | `Min/MaxPosition` now report tweak-menu limits; `Move*` speed fix (#941); works off the active vessel (#943) |
| **KerbalAlarmClock** | none | none | none | `AlarmType.ScienceLab`, `AlarmAction.Custom`/`Converted`, 5 new `Alarm` properties | `Alarm.Remaining` cast fix; alarm equality by ID |
| **Drawing** | none | none | none | none | client-drawn objects removed on disconnect |
| **UI** | none | none | none | none | client UI removed on disconnect; `Message` locale fix |
| **DockingCamera** | none | none | none | none | now loads in all game scenes |
| **LiDAR** | none | none | none | none | now loads in all game scenes |
| **RemoteTech** | none | none | none | none | now loads in all game scenes |

## Notable findings

### KRPC (core) — the only deprecation on the release train

* `KRPC.CurrentGameScene` is renamed to `KRPC.GameScene`. The old name is kept as an `[Obsolete]`
  read-only alias that forwards to the new property, so `get_CurrentGameScene` still resolves over
  the wire — a **deprecation, not a break** (#897).
* `KRPC.GameScene` gains a **setter** (a *new* property name, so it adds surface rather than
  changing existing surface): setting it switches scene or opens/closes a facility (#897).
* The `GameScene` enum gains five members — `MissionBuilder`(5), `AstronautComplex`(6),
  `MissionControl`(7), `ResearchAndDevelopment`(8), `Administration`(9). Existing members 0–4 keep
  their order and values, so the change is **append-only and wire-safe**. One behavioral
  consequence: old clients reading the scene can now receive values 5–9 their generated enum does
  not recognize.
* `[Obsolete]` is now surfaced over the wire — `GetServices` populates `Deprecated` /
  `DeprecatedReason` for services, procedures, classes, enums, enum values and exceptions (#904).
  This is the mechanism behind every `**Deprecated:**` changelog entry this cycle (including
  SpaceCenter's), and it updates the SpaceCenter audit's note that "kRPC has no
  `[Obsolete]`/deprecation attribute" — as of #904 it does.

### InfernalRobotics — large additive expansion

No removals or signature breaks despite being the biggest diff. New `[KRPCEnum] ServoMode`
(`Servo`=1, `Rotor`=2); 24 new `Servo` members (e.g. `UID`, `Mode`, `TargetPosition`, `MaxForce`,
`ForceLimit`, `PresetPositions`, `AddPreset`/`RemovePresetAt`/`SortPresets`); and 6 new `ServoGroup`
members (`Vessel`, `MovingDirection`, `ElectricChargeRequired`, `AdvancedMode`, `BuildAid`,
`IKActive`). Two behavioral changes sit behind unchanged signatures — see below.

### KerbalAlarmClock — additive only

Two enums extended by appending (`AlarmType.ScienceLab`=18; `AlarmAction.Custom`=6,
`Converted`=7 — existing members unchanged) and five new `Alarm` properties (`Enabled`, `PlaySound`,
`Triggered`, `SupportsRepeat`, `SupportsRepeatPeriod`). No surface removed or re-signed.

## Behavioral changes (same signature, different result)

These don't break compilation but change results or availability for existing clients, and are
worth a release-note line:

* **InfernalRobotics `Servo.MinPosition` / `MaxPosition`** now return/set the tweak-menu position
  *limits* rather than the fixed part-config range — values differ for existing callers. `Move*`
  now pass the servo's default speed to IR-Next (#941), and the service works off the active vessel
  (#943).
* **KerbalAlarmClock `Alarm.Remaining`** is recomputed from `AlarmTime - UT` (fixes an
  always-failing invalid cast); alarm equality now compares IDs; accessing a removed alarm now
  throws instead of silently reading a detached alarm.
* **Drawing / UI** now remove a client's drawn objects / UI elements when that client disconnects
  (client-owned-object cleanup), documented in each service's `<remarks>`. **UI `Message`** no
  longer emits a literal size tag under comma-decimal locales.
* **DockingCamera / LiDAR / RemoteTech (and InfernalRobotics)** now load in all game scenes rather
  than Flight only, widening where their procedures are callable — a migration to the shared
  `LoadOnceAddon` base. Additive (nothing previously callable stops working).

## CHANGES.txt coverage

Every finding above is already documented in the respective service's `CHANGES.txt`, correctly
tagged: the one deprecation carries `**Deprecated:**` (`core/CHANGES.txt`), and no `**Breaking:**`
marker is missing because — consistent with the headline — **there are no removals or
signature/type breaks in any of these services**. (Drawing has no v0.6.0 changelog block at all,
which is correct: it has no user-visible RPC changes.) No changelog action is required for these
services; the only release-note additions worth considering are grouped behavioral notes for the
InfernalRobotics `Min/MaxPosition` semantic change, mirroring recommendation 2 of the SpaceCenter
audit.
