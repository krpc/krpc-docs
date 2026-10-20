# DockingCamera log spam and LIDAR docstrings that name LaserDist

Milestone: 0.8.0 · Labels: bug, service

* `Camera.Image` in `service/DockingCamera/src/Camera.cs` calls `Debug.Log` on every read, so a client streaming the image writes a line to `KSP.log` every update. Remove the success line, and route the failure lines through `KRPC.Utils.Logger`.
* `service/LiDAR/src/LIDAR.cs` and `Laser.cs` describe a "LaserDist service" and "LaserDist part". The service binds to the `LiDAR` assembly, nullprofile's point-cloud fork, not mainline LaserDist. These docstrings generate the API reference, so they should name the LiDAR mod and link the fork.

Neither change needs the mods installed. Related to #674.
