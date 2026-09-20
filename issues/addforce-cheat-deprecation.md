# Part.AddForce — reconsider as a "cheat"

**Status:** proposal — no issue filed yet.

Related: [#466](https://github.com/krpc/krpc/issues/466) (support for debug cheats, milestone
0.7.0) and [PR #826](https://github.com/krpc/krpc/pull/826) (DebugTools). Surfaced while
investigating [#511](https://github.com/krpc/krpc/issues/511) (orbital decay while the server is
running), whose leading candidate cause — forces left applied by a client that disconnected without
calling `Force.Remove()` — is fixed by the shared client-disconnect cleanup component
([PR #934](https://github.com/krpc/krpc/pull/934), design in
[`client-disconnect-cleanup.md`](../design/protocol/client-disconnect-cleanup.md)).

## Files

- `service/SpaceCenter/src/Services/Parts/Part.cs` (`AddForce` / `InstantaneousForce`)
- `service/SpaceCenter/src/Services/Parts/Force.cs`
- `service/SpaceCenter/src/PartForcesAddon.cs`

## Rationale

Applying an arbitrary force to a part with no equal-and-opposite reaction is free momentum —
physically a cheat, on par with the debug-menu items in #466 and the teleport/cheat surface in
PR #826's DebugTools.

## Proposal

- **Deprecate** `Part.AddForce` / `InstantaneousForce` on the main SpaceCenter API (the
  `[Obsolete]` mechanism from [#904](https://github.com/krpc/krpc/pull/904) is now on `main`).
- **Relocate** the capability behind an opt-in debug/testing surface — `tools/TestingTools/`
  (already the home for test-only cheats like `OrbitTools.cs`) or the DebugTools service from
  PR #826 — gated the same way as #466's cheats (enabled on the KSP side, so it can't be used
  accidentally).
