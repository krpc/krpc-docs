# Add `EditorVessel.ReferenceFrame` and match the editor API to `Vessel` and `Flight`

**Status:** in progress, on a local branch, no PR yet. Due before the 0.7.0 tag, since changing
these signatures after release is breaking. Labels: `enhancement`, `service:space-center`.

Every `EditorVessel` member is new in 0.7.0, so all of the changes below are free until the tag.
The members came in with #1038, #1059 and #1103, and #1064 made the part frames work in the editor.

**Goal: parity with `Vessel` and `Flight` as far as possible**, so that a script written against
the editor vessel works on a vessel in flight. `Part` members that can work in the editor do.

## Problem

`Vessel` and `Part` follow one rule. Positions, directions and bounds take a reference frame. The
inertia members take none, and are documented against the object's own frame. `EditorVessel` breaks
the rule, and its names and classes differ from `Vessel` and `Flight`:

| Member | Frame today |
| --- | --- |
| `EditorVessel.CenterOfMass (ReferenceFrame)` | Given |
| `EditorVessel.CenterOfBuoyancy (ReferenceFrame)` | Given |
| `EditorVessel.BuoyantTorqueAt (..., ReferenceFrame)` | Given |
| `EditorVessel.MomentOfInertia` | Baked: about the CoM, in the axes of the root part's reference transform |
| `EditorVessel.InertiaTensor` | Baked: as above |
| `EditorVessel.Size` | Baked: editor world axes (the bounds `ShipConstruct.shipSize` is taken from) |

* **The inertia frame has no name.** The inertia code takes its axes from
  `root.GetReferenceTransform ()`. `Part.ReferenceFrame` uses `part.transform`, which differs for a
  root part with its own reference transform. So the inertia members cannot be compared with any
  position the API returns.
* **`Size` has no frame.** `Vessel.BoundingBox` takes one.
* **The names differ.** `Vessel.Position (ReferenceFrame)` is the center of mass, and `Vessel` has no
  `CenterOfMass`. `EditorVessel` has no `Rotation` or `Direction`.
* **The buoyancy members are on the wrong class.** Flight has them on `Flight`, with the output
  frame taken from the `Flight` object. `EditorVessel.CenterOfBuoyancy` is the fully submerged
  center, which flight calls `FullySubmergedCenterOfBuoyancy`. `Flight.CenterOfBuoyancy` is the
  center at the current waterline.
* **Part members are flight-only.** `Part.Direction`, `Part.Rotation` and `Part.BoundingBox` raise
  in the editor, although the part's transform and meshes are there.
* **`BuoyantTorqueAt` assumes the editor's vertical.** It passes `Vector3d.down` as the direction of
  gravity, so the torque is for the craft as displayed. No frame exposes that vertical, and a client
  cannot change it. A hull built nose-up in the vehicle assembly building gets gravity along its
  keel.

## Decision

**Add `EditorVessel.ReferenceFrame`**, the editor counterpart of `Vessel.ReferenceFrame`, backed by
a new `ReferenceFrameType.EditorVessel`:

* Origin at the vessel's center of mass (`ShipConstruct.WorldCenterOfMass ()`).
* Axes of the root part's reference transform (`ShipConstruct.VesselTransform ()`): x to the right,
  y forward, z out of the bottom, as `Vessel.ReferenceFrame` documents.
* Zero velocity and angular velocity.
* The vessel is looked up on each use, as `EditorVessel` does, so the frame survives loading another
  craft. Outside the editor it throws.

With the root part as the control point, this is the frame `Vessel.ReferenceFrame` gives at launch.

**Add `EditorVessel.SurfaceReferenceFrame`**, the counterpart of `Vessel.SurfaceReferenceFrame`.
It is backed by a new `ReferenceFrameType.EditorSurface`: origin at the center of mass, x along the
editor's world up, y and z horizontal with no north or east. This is the craft as displayed, and as
it stands at launch.

**Follow `Vessel` member for member.** Position, direction and bounds members take a required
frame, as on `Vessel`:

| Member | Change |
| --- | --- |
| `CenterOfMass (ReferenceFrame)` | Renamed `Position (ReferenceFrame)`, as on `Vessel` |
| `Rotation (ReferenceFrame)` | New, as on `Vessel`: the rotation of `ReferenceFrame` |
| `Direction (ReferenceFrame)` | New, as on `Vessel`: the y axis of `ReferenceFrame` |
| `Flight (ReferenceFrame = null)` | New, as on `Vessel`. Returns a `SimulatedFlight` |
| `SurfaceReferenceFrame` | New, as on `Vessel` |
| `Displacement`, `CenterOfBuoyancy`, `BuoyantForceAt`, `BuoyantTorqueAt` | Moved to `SimulatedFlight` |
| `MomentOfInertia` | Stays a property. Documented as in `ReferenceFrame`, as `Vessel.MomentOfInertia` is |
| `InertiaTensor` | Stays a property. Documented as in `ReferenceFrame`, as `Vessel.InertiaTensor` is |
| `Size` | Replaced by `BoundingBox (ReferenceFrame)`, matching `Vessel.BoundingBox` |

* The offset of the CoM from the root part is
  `vessel.position(vessel.parts.root.reference_frame)`. In `vessel.reference_frame` it is
  zero.
* Celestial body frames are accepted and left undocumented. With the planetarium paused and the
  floating origin on the space center, the result is stable but has no practical use. Drop the
  existing remark about them.
* `Part.MomentOfInertia` and `Part.InertiaTensor` stay as they are in both scenes. Their doc
  comments cite `Part.ReferenceFrame`, but the tensor is about the part's center of mass. Cite
  `Part.CenterOfMassReferenceFrame` instead.

**Add `SimulatedFlight`, the counterpart of `Flight`.** `EditorVessel` mirrors `Vessel`, and
`SimulatedFlight` mirrors `Flight`. `EditorVessel.Flight (ReferenceFrame = null)` returns one. With no frame given, the output
frame is the object's simulated `SurfaceReferenceFrame`, and follows it when it is set, as
`Vessel.Flight` defaults to the surface the vessel flies over. So
`v.flight().buoyant_torque_at(density, gravity)` reads the same in both scenes. In C#, C++ and Java
the types differ, so there the parity is in the names.

* **The simulated attitude is a settable `SimulatedFlight.SurfaceReferenceFrame`.** Its x axis is
  the simulated up, and gravity acts along -x. Only its rotation is used. It defaults to
  `EditorVessel.SurfaceReferenceFrame`.
* **The setting belongs to the object.** A `Flight` object already holds its vessel and frame. Each
  `SimulatedFlight` holds its own attitude, so two scripts can simulate different attitudes at once.
  The object store dedupes by `Equals`, so equality is by reference: each `Flight ()` call adds an
  entry, swept when the game leaves the editor. The surface frame is not part of the object's
  state, so a removed one raises on use rather than destroying the object.
* **The simulated attitude rotates the world, not the vessel.** The vessel stays as displayed, and
  the surface frame says where up is. Every member works as on `Flight`, from the vessel's rotation
  in the output frame. With the default output frame, setting the attitude makes the object read
  as a vessel flying that way: `Pitch` reads it back and `Direction` agrees.
* **The vessel is live.** The object reads the ship from the editor on each call, as `EditorVessel`
  does, so it follows every edit. Loading another craft keeps the attitude, and applies it to the
  new craft.
* A removed frame gives `ObjectDestroyedException` on the next call that reads it, as any removed
  frame does.

The buoyancy members move from `EditorVessel` to `SimulatedFlight`, under their `Flight` names and
signatures. Vectors are in the object's output frame, as on `Flight`:

| `SimulatedFlight` member | Was |
| --- | --- |
| `Displacement` | `EditorVessel.Displacement` |
| `FullySubmergedCenterOfBuoyancy` | `EditorVessel.CenterOfBuoyancy (ReferenceFrame)`. A nullable property, as on `Flight`. `Flight.CenterOfBuoyancy` is the vessel at its current waterline, so the editor uses the fully submerged name |
| `BuoyantForceAt (density, gravity)` | `EditorVessel.BuoyantForceAt` |
| `BuoyantTorqueAt (density, gravity)` | `EditorVessel.BuoyantTorqueAt (..., ReferenceFrame)`. Gravity now acts along -x of `SurfaceReferenceFrame`, in place of `Vector3d.down` |

`SimulatedFlight` also gets the orientation members of `Flight`, in its output frame as on
`Flight`:

| `SimulatedFlight` member | Notes |
| --- | --- |
| `CenterOfMass` | New |
| `Rotation` | New |
| `Direction` | New |
| `Pitch` | New. In the output frame, as on `Flight`. With the default output frame it reads back the attitude that was set |
| `Roll` | New. As `Pitch` |

`Heading` is left out. It needs north, and the editor has none.

Members that need a real environment, such as altitude, speed, the current waterline and
aerodynamics, have no counterpart. A later waterline simulation could add `CenterOfBuoyancy` with
its flight meaning.

A hull built nose-up that should float on its bottom:

```python
v = sc.editor.vessel
flight = v.flight(v.reference_frame)
# The vessel frame's z axis points out of the bottom, so up is its -z
q = quaternion_rotating((1, 0, 0), (0, 0, -1))  # placeholder: any rotation taking x to -z
flight.surface_reference_frame = ReferenceFrame.create_relative(v.reference_frame, rotation=q)
flight.buoyant_torque_at(density, gravity)
```

A relative frame on the vessel frame follows the hull as it is edited.

**Enable `Part.Direction`, `Part.Rotation` and `Part.BoundingBox` in the editor.** `Part.Velocity`
stays flight-only, as nothing in the editor moves.

**Defer a `SimulatedFlight` for a vessel in flight.** `Flight` already answers the simulated
questions with explicit arguments: `BuoyantTorqueAt`, `FullySubmergedCenterOfBuoyancy`, and
`SimulateAerodynamicForceAt` with a given rotation. Build `SimulatedFlight` on a source that yields
the parts and center of mass on each call, with the editor ship as the only source in 0.7.0. A
`Vessel` source is then a non-breaking addition, if one is asked for.

**Make `PartExtensions.GetBounds` correct in the editor.** Both `BoundingBox` members use it. It
seeds the box with `part.WCoM`, which the flight physics maintains. In the editor the seed is the
part's center of mass from `PartExtensions.CenterOfMass ()`, as for every other editor position.
Flight keeps `WCoM`.

**Include skinned meshes in `GetBounds`.** Found while testing the editor boxes: it collected only
`MeshFilter`s, so a part modeled as a skinned mesh got an empty box in both scenes. `MiniDrill` is
a single skinned mesh, and `launchClamp1` has one, its umbilical, beside five mesh filters.
Skinned meshes are baked in their current pose with `SkinnedMeshRenderer.BakeMesh`, so the box
follows the animation. The bind pose is wrong for the drill: its bones turn the mesh 90 degrees.
Both renderers have unit scale, so whether the baked vertices carry the renderer's scale is
untested. The code assumes they do, as in Unity 2019.4. A fix to released behavior, so it gets
its own changelog entry.

## Implementation

* `ReferenceFrameType.EditorVessel` and `ReferenceFrameType.EditorSurface`, with a case in every
  switch in `ReferenceFrame.cs`.
* `EditorVessel.SurfaceReferenceFrame`, and the `SimulatedFlight` class with its settable
  `SurfaceReferenceFrame`, buoyancy members and orientation members.
* `EditorVessel` members as in the table, and in-game tests in the editor test file.
* `GetBounds` seeded from the editor center of mass, with an editor test of `Part.BoundingBox` and
  `EditorVessel.BoundingBox` against the part meshes.
* `GameScene.Editor` on `Part.Direction`, `Part.Rotation` and `Part.BoundingBox`. Update the
  assertions in `test_editor_parts.py` that expect them to raise.
* `Part.MomentOfInertia` and `Part.InertiaTensor` doc comments.
* Changelog:
  * Rename `EditorVessel.CenterOfMass` to `Position` in the existing #1059 entry.
  * Move the #1103 editor members to `SimulatedFlight`, under their new names.
  * One entry adding `EditorVessel.ReferenceFrame`, `SurfaceReferenceFrame`, `BoundingBox`,
    `Rotation`, `Direction` and `Flight`, and the `SimulatedFlight` class. `Size` is new in 0.7.0
    and never named in the changelog, so its removal needs no entry.
  * Add `Part.Direction`, `Part.Rotation` and `Part.BoundingBox` to the #1064 entry listing the part
    members available in the editor.
* Docs: `doc/order.txt`, the `editor.tmpl` note on part members and the `SimulatedFlight`
  class, and an editor section in the buoyancy tutorial in place of its `EditorVessel` mentions.
* Port the editor tests in `test_parts_buoyancy.py` to `SimulatedFlight`.
* No goldens to regenerate: the krpctools goldens come from the test service, and no client
  stubs are checked in.

## Verified in game

* **Launch attitude.** The Staging and Rover craft point the same way in the editor surface frame
  as in their surface frame on the pad, to 0.01 in the vertical component of the direction.
* **Bounding boxes.** Every part box in the Parts craft surrounds the part's center of mass and is
  under 20 m. The vessel box matches flight in the vessel frame, within 10%. One Rover dimension
  differs by 0.12 m, most likely the wheels settling on the pad.
