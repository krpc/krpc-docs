# SpaceCenter: `Vessel.Name` returns a localization key for stock craft

`Vessel.Name` returns `Vessel.vesselName`. A stock craft keeps its name as a localization tag, so a launched Kerbal X reports `#autoLOC_501232` in place of "Kerbal X". The game shows the name through `Vessel.GetDisplayName ()`, which formats the tag.

Proposed fix: return the localized name from the getter. The setter keeps writing `vesselName`. Check the other names the service returns from game data for the same tag, such as craft names in the editor and the launchable vessel lists.

Tests: launch a stock craft and check `Vessel.Name` is its display name.

Labels: `bug`, `service`, `ksp`. Milestone: `ksp-v0.8.0`.
