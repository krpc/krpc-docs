# Deprecate the LIDAR service in favor of `SpaceCenter.RaycastDistance`

The service binds to `LiDAR.API`, a reflection-loaded class that exists only in nullprofile's `LiDAR` mod. That mod has no release, so `Available` is false for every player.

The `LiDAR` mod is separate from LaserDist, not a patch. Its `LiDARModule` casts a fixed fan of 8 rays from the part each physics tick and buffers the hit points for `Laser.Cloud`. `SpaceCenter.RaycastDistance` gives the same capability. A function stream casts a fan of rays in one physics tick, so no batch RPC is needed. kRPC does not ship parts, and a new LIDAR mod is not worth maintaining for one beam pattern.

## Deprecate, then remove

* Mark the `LIDAR` service and `Laser` with `[Obsolete]`, with a message pointing to `SpaceCenter.RaycastDistance`. The behavior stays as is for one release cycle, then the service is removed.
* Rewrite the `doc/api/lidar.tmpl` intro as a deprecation note followed by the replacement example. Python and C# get a function stream over a captured list of directions in `part.reference_frame`. The other clients get a loop of `raycast_distance` calls. Examples in `doc/src/scripts/api/lidar/`.
* Fold in #1181: the docstrings name LaserDist. Reword them as part of the deprecation.
* Changelog (LIDAR): **Deprecated:** the `LIDAR` service, use `SpaceCenter.RaycastDistance` instead.

## Raycasts ignore trigger colliders

`RaycastDistance` and `RaycastPart` call `Physics.Raycast` with the default query settings, so they hit trigger volumes. An example is the DLC robotic arm scanner's trigger (LaserDist #30). Pass `QueryTriggerInteraction.Ignore` to both, so the replacement for LIDAR measures the surface.

* Behavior change, so the changelog (SpaceCenter) gets an entry: raycasts ignore trigger colliders.
* In-game test: a ray through a trigger volume hits the surface behind it.

With #<dockingcam-public-release>, supersedes #674. Folds in #1181.

Design: [dockingcam-lidar-tests.md](https://github.com/krpc/krpc-docs/blob/main/design/services/dockingcam-lidar-tests.md), option 4.
