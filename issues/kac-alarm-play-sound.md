# `KerbalAlarmClock.Alarm.PlaySound` has no effect

**Status:** draft issue, not filed. The bug shipped in 0.6.0. Labels: `bug`,
`service:kerbal-alarm-clock`.

`Alarm.PlaySound` binds the `PlaySound` field of the mod's `KACAlarm` class
(`service/KerbalAlarmClock/src/KACWrapper.cs`). That field is persisted but never read. When an
alarm fires, KAC reads `KACAlarm.Actions.PlaySound`, a field of the nested `AlarmActions` object.

Setting the property changes a value that KAC does not use. The getter does not report whether the
alarm plays a sound.

The in-game test only round-trips the value (`test_kerbalalarmclock.py`), so it passes.

## Evidence

From an `ikdasm` disassembly of KerbalAlarmClock 3.14.2.7, the version pinned in `MODULE.bazel`:

* No instruction loads `KACAlarm::PlaySound`.
* Every read in the alarm-firing path is `ldfld bool KerbalAlarmClock.AlarmActions::PlaySound`,
  reached through `ldfld ... KACAlarm::Actions`.

## Fix

Bind the `Actions` field, then `PlaySound` on its `AlarmActions` value. Add a changelog entry,
since the bug shipped in 0.6.0.

The other `AlarmActions` fields (warp, message, delete when done) are the phase 3 alarm-action
model in [kac-remotetech-tests-and-api.md](../design/services/kac-remotetech-tests-and-api.md).
They can follow the same binding.
