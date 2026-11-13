# SpaceCenter: setting `Camera.Mode` to IVA fails silently, and leaves the IVA when already in it

Setting `Camera.Mode` to `CameraMode.IVA` calls `CameraManager.SetCameraIVA ()` and ignores what it returns. Two cases give the wrong mode with no error:

* **Straight after a launch.** `SetCameraIVA ()` picks the first crew member whose `KerbalRef` is spawned, and returns `false` when none is. KSP spawns the kerbals a moment after the vessel loads, so the call does nothing. A script that launches and switches to IVA stays in the flight camera.
* **Already in the IVA.** `SetCameraIVA (kerbal, ...)` calls `SetCameraFlight ()` when `kerbal` is the active IVA kerbal, as the camera key toggles. Setting the mode to IVA a second time leaves the IVA.

The Raster Prop Monitor tests met both. Their IVA setup retries the setter until `Camera.Mode` reads IVA, and sets it only while it does not.

Proposed fix, in `Camera.Mode`'s setter:

* Do nothing when the mode is already IVA.
* When `SetCameraIVA ()` returns `false` with crew aboard, yield to the next tick and retry, up to a timeout. Throw an exception for a vessel with no crew, or one that never enters the IVA.

Tests: set the IVA mode in the same tick as a launch and read it back, and set it twice and check it stays IVA. Then drop the retry loop from the Raster Prop Monitor tests.

Labels: `bug`, `service`, `ksp`. Milestone: `ksp-v0.8.0`.
