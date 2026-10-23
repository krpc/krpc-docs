# Complete the RemoteTech and KerbalAlarmClock APIs

* RemoteTech: bind the API methods the service leaves unbound, about 17. These include `ControlPath`, `HasDirectGroundStation`, `RadioBlackout`, `PowerDown`, ground station management and `Enabled`.
* KerbalAlarmClock: expose the alarm actions on `KACAlarm.Actions`: warp, message and delete when done. The binding is the same as the `PlaySound` fix in #1179.

Test coverage for both services landed in #981 and #982.

Design: [kac-remotetech-tests-and-api.md](https://github.com/krpc/krpc-docs/blob/main/design/services/kac-remotetech-tests-and-api.md), Phases 2 and 3.
