# Editor API for Part Introspection

**Status:** proposal — external PR, not yet merged: [PR #788](https://github.com/krpc/krpc/pull/788)
(open since 2024-04-07).

No tracking issue exists for this — the PR itself is the reference.

## Summary

Adds a new `SpaceCenter.Editor` / `EditorShip` / `EditorParts` surface for introspecting vessels in
the VAB/SPH (part list, resources, etc.), aimed at external tools that assist vehicle design.

## Files

New files:

- `service/SpaceCenter/src/Services/Editor.cs`
- `service/SpaceCenter/src/Services/EditorShip.cs`
- `service/SpaceCenter/src/Services/Parts/EditorParts.cs`

Touches:

- `service/SpaceCenter/src/Services/Parts/Part.cs`
- `service/SpaceCenter/src/Services/Resource.cs`
- `service/SpaceCenter/src/Services/Resources.cs`
- `service/SpaceCenter/src/Services/SpaceCenter.cs`
- doc/order.txt entries

## Review discussion

- The maintainer's review comment on the PR flagged it as a good general approach but deferred
  fleshing it out.
- The author's own follow-up comment suggested generalizing `Parts` to work over both `Vessel` and
  editor craft via `IShipConstruct` (implemented by both `ShipConstruct` and `Vessel`) rather than
  duplicating part-wrapping logic.

## Open question

The `IShipConstruct` generalization (share part-wrapping logic between `Vessel` and editor craft
rather than duplicating it) is still open.
