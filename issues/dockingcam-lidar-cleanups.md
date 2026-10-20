# DockingCamera and LiDAR: wrong docstrings and log spam

**Status:** draft issue, not filed. Small, after 0.7.0. Labels: `bug`, `service`.

Two cleanups from [dockingcam-lidar-tests.md](../design/services/dockingcam-lidar-tests.md).
Neither needs the mods installed.

## LiDAR docstrings name the wrong mod

`service/LiDAR/src/LiDAR.cs` and `Laser.cs` describe a "LaserDist service", the "LaserDist API",
a "LaserDist part" and a "LaserDist laser". The service binds to the `LiDAR` assembly and its
`LiDARModule`. That is nullprofile's point-cloud fork, not mainline LaserDist, which is a
single-beam distance meter with no kRPC API.

These docstrings generate the API reference. Name the LiDAR mod, and link the fork.

## DockingCamera logs every image read

`Camera.Image` in `service/DockingCamera/src/Camera.cs` calls `Debug.Log` on every read:

* `"CAMERA IMAGE: OK"` on success.
* The exception message and stack trace on failure.
* `"CAMERA IMAGE: FAILED"` when the API is unavailable.

A client streaming the image writes a line to `KSP.log` every update. Remove the success line.
Route the two failure lines through `KRPC.Utils.Logger`, or remove them as well.

## Changelog impact

DockingCamera: one entry for the log spam. LiDAR: none, as docs only.
