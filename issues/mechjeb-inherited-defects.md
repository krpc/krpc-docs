# MechJeb: defects inherited from KRPC.MechJeb, and settings MechJeb 2.15 gates

The MechJeb service is a port of Genhis' KRPC.MechJeb 0.7.1 to MechJeb 2.15.4.0. A review of the
port found these defects in the original code. The port keeps each one as it was.

| Member | Defect | Failure |
| --- | --- | --- |
| `LandingAutopilot.LandAtPositionTarget` | No check of `TargetController.PositionTargetExists` or of a landed vessel. MechJeb's own button is disabled in both cases | With no position target, the vessel deorbits toward 0°N 0°E, or toward an earlier target, and no error is returned |
| `Operation.MakeNodes` | Calls MechJeb's `MakeNodesImpl` directly, which skips the `ErrorMessage = ""` reset in MechJeb's `MakeNodes` | A warning from one call, such as Lan's low inclination warning, stays in `ErrorMessage` after later calls. In 2.15 the operations are static and shared by every vessel, so the stale warning also follows a vessel switch |
| `Operation.MakeNodes` | Plans from `vessel.orbit` at the current time. MechJeb's planner window plans from the last node's `nextPatch` at that node's time | With a node already on the vessel, a new node's burn is computed on the orbit before that node. Example: Apoapsis, then Circularize, gives a wrong second burn |
| `Operation.MakeNodes` | A failure in `PlaceManeuverNode` escapes unwrapped | Nodes placed earlier in the same call stay on the vessel. MechJeb's window behaves the same way |
| `TargetController.CanAlign`, `Position`, `Distance`, `RelativePosition`, `RelativeVelocity`, `DockingAxis`, `TargetOrbit` | No target check | With nothing targeted, the client gets a `NullReferenceException` or `ArgumentNullException` |
| `SmartASS.ForcePitch`, `ForceYaw`, and `ForceRoll` in the surface modes | MechJeb passes these to `SetAxisControl` only while its Smart A.S.S. window is drawn. `Engage` controls all three axes | With the window closed, `ForcePitch = False` then `Update(False)` in Surface mode still controls pitch. A fix binds `MechJebModuleAttitudeController.SetAxisControl` and calls it after `Engage` |
| `AscentAutopilot.CorrectiveSteering`, `CorrectiveSteeringGain` | Undocumented: only the classic path reads them | A script on the PVG path sets them, with no effect |
| `ThrustController.ManageIntakes` | Undocumented: MechJeb reads it only when `LimitToPreventFlameout` is on. Its siblings carry a "Requires" remark | A script sets `ManageIntakes` alone, with no effect |
| `NodeExecutor.ExecuteOneNode`, `ExecuteAllNodes` | No check for a maneuver node | With no node, MechJeb's `Init` throws `ArgumentOutOfRangeException` after the module is enabled. `Enabled` reads true until MechJeb's next `OnFixedUpdate` aborts it |

## Settings MechJeb 2.15 gates

MechJeb 2.15 reads these settings only under a condition the API cannot set. With older MechJeb,
0.7.1 set them with effect.

| Member | Defect | Failure |
| --- | --- | --- |
| `AscentAutopilot.LimitAoA`, `MaxAoA`, `AoALimitFadeoutPressure` | MechJeb applies the AoA limiter only when `LimitQaEnabled` is off. It defaults to on, and only MechJeb's ascent windows set it, to `AscentType == PVG` | A script on the classic path, with no ascent window ever drawn for the craft, gets the PVG Qα limiter. `MaxAoA` has no effect, and `LimitAoA = False` does not turn limiting off |
| `AscentPVG.FixedCoast`, `FixedCoastLength` | MechJeb reads them only when a coast stage is set (`CoastStageFlag`), which the API does not expose | A script sets a fixed coast with no effect |

## Proposal

* Throw an `MJServiceException` with a clear message when the target or node is missing, on
  each member above. Document each throw with "Throws an exception if ...".
* Clear `ErrorMessage` before calling `MakeNodesImpl`. Bind the protected field for this.
* Plan from the last node's next patch when the vessel has nodes, as the planner window does.
* Set `LimitQaEnabled` to `AscentType == PVG` in the `AscentPathIndex` setter and on enabling the
  ascent autopilot, as MechJeb's ascent window does.
* Document that `FixedCoast` needs a coast stage, set in MechJeb's PVG settings window.
* Apply the Smart A.S.S. axis settings after `Engage`, and add the missing "Requires" remarks.
* Add a test case for each fix to `service/MechJeb/test/test_mechjeb.py`.

None of these changes the API.
