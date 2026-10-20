# `KerbalAlarmClock.Alarm.PlaySound` has no effect

Milestone: 0.8.0 · Labels: bug, service:kerbal-alarm-clock

`Alarm.PlaySound` binds the `PlaySound` field of KAC's `KACAlarm` class (`service/KerbalAlarmClock/src/KACWrapper.cs`). KAC persists that field but never reads it. When an alarm fires, KAC reads `KACAlarm.Actions.PlaySound`, a field of the nested `AlarmActions` object. Setting the property has no effect, and the getter does not report whether the alarm plays a sound.

Fix: bind `Actions`, then `PlaySound` on its value. The in-game test only round-trips the value, so it should also check `Actions`. The bug shipped in 0.6.0, so it needs a changelog entry.
