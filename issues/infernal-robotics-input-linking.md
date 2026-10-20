# InfernalRobotics: servo input linking and sun tracking

Milestone: none · Labels: enhancement, service:infernal-robotics

IR-Next's `IServo` can drive a servo from the vessel's control axes, or point it at the sun. #985 left this cluster out of the servo API. It is about 18 members: an `InputMode` enum and `LinkInput ()`, the per-axis control and speed values (pitch, roll, yaw, throttle, X, Y, Z, plus `BaseSpeed`), `TrackSun`, `TrackAngle`, `ControlDeflectionRange` and `ControlNeutralPosition`.

Testing needs a servo configured in a linked or tracking input mode, or at least a round trip of the settable values.

Design: [infernal-robotics-input-linking.md](https://github.com/krpc/krpc-docs/blob/main/design/services/infernal-robotics-input-linking.md)
