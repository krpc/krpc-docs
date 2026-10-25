# DockingCamera on the public release, deprecate LIDAR

Both services bind to a reflection-loaded `API` class that exists only in nullprofile's forks of the mods. Neither fork has a release. With the public mods installed, `Available` is false.

## DockingCamera: bind to Docking Camera (KURS) 1.3.9

Use linuxgurugamer's [1.3.9](https://github.com/linuxgurugamer/DockingCam/releases/tag/1.3.9) release (KSP 1.12, also on SpaceDock and CKAN) unchanged, and move the fork's bridge into the kRPC service.

| | nullprofile fork | 1.3.9 |
| --- | --- | --- |
| Assembly | `DockingCamKURS_` | `DockingCamKURS` |
| Bridge | `OLDD_camera_.API.GetImage(Part)` | none |
| `BaseCamera.GetPic` | takes a resolution | reads it from `dcm`, a `DockingCameraModule` that is null on a `PartCameraModule`, so it throws |

The fork is 2 commits on a March 2022 base, 5 behind upstream. Its only functional change is the bridge plus the `GetPic` resolution parameter. Everything else is a rename and whitespace.

`Camera.Image` reimplements `GetPic` by reflection:

1. Find the part's `OLDD_camera.Modules.PartCameraModule` and read its private `_camera` field, a `PartCamera`.
2. Read the protected `BaseCamera.AllCameras` list.
3. Render those cameras into a kRPC-owned `RenderTexture`, then `ReadPixels` and `EncodeToPNG`. The fork used 256x256.

Details:

* `API.Load` checks for assembly `DockingCamKURS` and the fields it reads. A field missing in a later release makes `Available` false, and the log names the field.
* `AllCameras` exists only while the camera is on. The mod's persistent `Camera` field toggles it and opens the mod's window. Decide whether `Image` throws while the camera is off, or kRPC switches it on.
* Rendering runs on the main thread in flight only.
* Fold in #1180: drop the per-read `Debug.Log` lines.
* Test in game: pin 1.3.9 in `MODULE.bazel` (sha256 in [dockingcam-lidar-tests.md](https://github.com/krpc/krpc-docs/blob/main/design/services/dockingcam-lidar-tests.md)) and add it to `MODS`. A craft with the `OnboardCamera` part gives `available`, the factory, and an `image` that decodes as a PNG.
* Changelog (DockingCamera): support the public Docking Camera (KURS) release.

## LIDAR: deprecate, then remove

The fork's `LiDARModule` is a different mod from LaserDist, not a patch. It casts a fixed fan of 8 rays from the part each physics tick and buffers the hit points for `Laser.Cloud`. `SpaceCenter.RaycastDistance` gives the same capability. A function stream casts a fan of rays in one physics tick, so no batch RPC is needed. kRPC does not ship parts, and a new LIDAR mod is not worth maintaining for one beam pattern.

* Mark the `LIDAR` service and `Laser` with `[Obsolete]`, with a message pointing to `SpaceCenter.RaycastDistance`. The behavior stays as is for one release cycle, then the service is removed.
* Rewrite the `doc/api/lidar.tmpl` intro as a deprecation note followed by the replacement example. Python and C# get a function stream over a captured list of directions in `part.reference_frame`. The other clients get a loop of `raycast_distance` calls. Examples in `doc/src/scripts/api/lidar/`.
* Fold in #1181: the docstrings name LaserDist. Reword them as part of the deprecation.
* Changelog (LIDAR): **Deprecated:** the `LIDAR` service, use `SpaceCenter.RaycastDistance` instead.

## Raycasts ignore trigger colliders

`RaycastDistance` and `RaycastPart` call `Physics.Raycast` with the default query settings, so they hit trigger volumes. An example is the DLC robotic arm scanner's trigger (LaserDist #30). Pass `QueryTriggerInteraction.Ignore` to both.

* Behavior change, so the changelog (SpaceCenter) gets an entry: raycasts ignore trigger colliders.
* In-game test: a ray through a trigger volume hits the surface behind it.

Supersedes #674. Folds in #1180 and #1181.

Design: [dockingcam-lidar-tests.md](https://github.com/krpc/krpc-docs/blob/main/design/services/dockingcam-lidar-tests.md), option 4.
