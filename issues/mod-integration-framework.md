# Mod integrations: one framework for the build, binding, checks, tests and tested versions

The mod services each repeat the same machinery in their own way:

* A 97-line `BUILD.bazel` copied per service, and 19 other files to register a new one.
* Seven ways to bind to a mod by reflection, each logging and failing differently. RemoteTech's
  binding exists twice, and Trajectories logs errors when its mod is absent.
* A hand-written `CheckAPI` call at the top of each RPC. Trajectories has none.
* `ImageFormat` and its encoder copied into DockingCamera, SCANsat and Raster Prop Monitor.
* The same `setUpClass`, image checks and `test_available` in each service's in-game tests.
* Services listed in `tools/krpctools/services.bzl` and mods in krpctools Python classes, with no
  link between them. Mod versions pinned only in the download URLs, and not shown in the docs.

Seven phases, refactoring first: one registry in `service/` for the services and mods, and a
build macro; test helpers in
krpctools; one binding layer with stubs; `ModAPI` loaded at startup; `RequiresMod` in place of
`CheckAPI`; tested mod versions in the docs; an in-game check that each mod binds in full at its
pinned version.

Absorbs [requires-mod-attribute.md](requires-mod-attribute.md) (phase 5) and
[trajectories-load-errors.md](trajectories-load-errors.md) (phase 3), and the mod part of
[#1227](https://github.com/krpc/krpc/issues/1227) (phases 3 and 4).

Labels: `enhancement`, `server`, `service`, `build`, `tools`, `docs`, `ksp`, `mods`, per phase.
Milestone: `ksp-v0.8.0`.

Design: [mod-integration-framework.md](https://github.com/krpc/krpc-docs/blob/main/design/services/mod-integration-framework.md)
