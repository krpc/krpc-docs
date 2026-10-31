# DockingCamera: support the public Docking Camera (KURS) release

The service binds to a reflection-loaded `API` class that exists only in nullprofile's fork of Docking Camera (KURS). The fork has no release. With the public mod installed, `Available` is false.

## Change

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
* `Image` returns an empty array when the image fails, and logs the exception at Debug. Decide whether it throws instead.
* Test in game: pin 1.3.9 in `MODULE.bazel` (sha256 in [dockingcam-lidar-tests.md](https://github.com/krpc/krpc-docs/blob/main/design/services/dockingcam-lidar-tests.md)) and add it to `MODS`. A craft with the `OnboardCamera` part gives `available`, the factory, and an `image` that decodes as a PNG.
* Changelog (DockingCamera): support the public Docking Camera (KURS) release.

With #<lidar-deprecation>, supersedes #674.

Design: [dockingcam-lidar-tests.md](https://github.com/krpc/krpc-docs/blob/main/design/services/dockingcam-lidar-tests.md), option 4.
