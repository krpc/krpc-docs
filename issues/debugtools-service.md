# DebugTools service ("actual cheating")

**Status:** proposal — external PR, not yet merged:
[PR #826](https://github.com/krpc/krpc/pull/826) (Benjamin Chung, open since 2024-12-12).

The PR fixes issue [#799](https://github.com/krpc/krpc/issues/799) (setting/teleporting vessel
position), and is related to [#145](https://github.com/krpc/krpc/issues/145) (DebugTools service:
physics range, vessel position/velocity, etc.) and [#466](https://github.com/krpc/krpc/issues/466)
(support for debug cheats).

## Summary

New `service/DebugTools/` service (`DebugTools.cs`) implementing:

- **Three teleportation mechanisms** via different KSP APIs.
- A **game-pause mechanism** the author isn't happy with — the pause dialog doesn't display
  properly, and the author is looking for suggestions on it.

## Review discussion

- Maintainer review comment noted it's very similar to the existing `TestingTools` service already
  used by the integration tests — worth comparing/consolidating before merging.
