# In-game tests for untested mod integrations

Milestone: none · Labels: tools, mod-compatibility

Several mod integrations have no in-game tests:

* Procedural Fairings.
* The Firespitter and WBI thrust reversers, and the stock TF1 and TF2 reversers.
* DockingCamera and LIDAR, which have no `test/` directory and are absent from `//:test` and `//:lint`. Tests without the mods installed (`Available` is false, the factories throw) need no mod sourcing.

Designs: [mod-compat-test-coverage.md](https://github.com/krpc/krpc-docs/blob/main/design/services/mod-compat-test-coverage.md), [dockingcam-lidar-tests.md](https://github.com/krpc/krpc-docs/blob/main/design/services/dockingcam-lidar-tests.md)
