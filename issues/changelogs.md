# Clean up and restructure the 0.7.0 changelogs

**Status:** draft issue, not filed. Due before the 0.7.0 tag. Labels: `docs`.

The 0.7.0 sections have grown to about 480 entries across 19 components. Most are flat lists in
merge order, newest first. Related entries end up scattered, and one PR's entries are split by
later ones. Only `service/SpaceCenter` is grouped, as its 0.6.0 section was.

| Component | Entries | Shape now |
| --- | --- | --- |
| SpaceCenter | ~130 | Grouped, but `Parts` holds ~30 and #1051 is spread over 15 groups |
| core | 75 | Flat. Server side functions (#1124) alone is ~45 |
| python, cpp, csharp, java | 28-40 each | Flat. Stream entries (#1122) are split from earlier stream fixes |
| UI | 30 | Flat, all #1040 and #1051 |
| krpctools | 20 | Flat |
| Drawing, lua, cnano, server | 11-15 each | Flat |
| the rest | 1-4 each | Fine as is |

## Restructure

Group every component over about 12 entries under `- Group` headings with nested entries, as
SpaceCenter 0.6.0 does. Within a group, put **Breaking** entries first, then additions, then
fixes.

| Component | Suggested groups |
| --- | --- |
| core | Server side functions; Errors and exceptions; Streams and events; Types and nullability (#1017, #1091, #1066, #1077); Physics ticks (#1070); Object lifetime (#1051, #1019, #1020, #1119, #1120); Communication (#1065, #1035); Game scenes |
| Clients | Dependencies; Connecting (`connect_local`, `timeout`); Types (nullable, structures, hashing); Streams and events; Errors; Server side functions; Performance (#1056) |
| SpaceCenter | Split `Parts` into RCS and thrusters, Control surfaces, Engines (RealFuels), Decouplers, Part modules, Science, Bounding boxes. Add an Object lifetime group for #1051 and #1072, as 0.6.0 did with Client disconnect cleanup and Localization. Move the #1043 control entries out of Space center into Control, #1114 into Alarms, and #1071 into a Performance group |
| UI | Breaking changes; Scenes; New elements (Toggle, Slider, Dropdown, Image, ScrollView); Layout; Panels; Control properties; Object lifetime |
| Drawing | New shapes; Styling (arrows, colors, dashes, labels); Map view and editor; Object lifetime |
| krpctools | Python stubs; Default values (#1044, #1045); Generated documentation (#1094); Structures and nullable values |

## Cleanup

Merge entries that list one PR's additions piecemeal:

 * core #1124: the six "Allow a function to ..." entries and the six `KRPC.Expression` addition
   entries become two or three.
 * python #1127, csharp #1128: the "Compile ..." entries become one.
 * SpaceCenter #1103: the three `Part.*` lists and the split `EditorVessel.*` and `Flight.*`
   lists become one per class.
 * core and krpctools #1017: "Support for nullable values across all types" duplicates the
   **Breaking** entry beside it.

Remove entries that the rules exclude:

 * SpaceCenter: `Part.Mass` and `Part.DryMass` no longer report 1000 kg for every part in the
   editor (#1059). Parts became reachable in the editor this cycle with #1038, so this fixes
   unreleased behavior. The #1038 `EditorVessel.Parts` entry already covers the mass.
 * SpaceCenter: the #1051 entry for parts of the vessel under construction describes a feature
   new in #1038. Fold it into the editor entries.
 * Audit the client "Fix ..." entries from #1122 and #1134 for bugs that existed only during
   this cycle.

Make the markers and wording consistent:

 * `Stream.wait` and `Event.wait` returning a bool is **Breaking** in csharp and java, and
   unmarked in cpp and python. All four returned `void` or `None` in 0.6.0. Decide once and
   apply to all four.
 * The same stream and event changes are worded differently in each client. Use one wording,
   with the client's names substituted.

Shorten entries over 30 words: `SpaceCenter.LaunchVessel` crew (#1017), RealFuels (#1039),
`ControlSurface.Deployed` (#1088), UI `Visible` (#1040), krpctools special default values
(#1045). The detail is in the PR. Rephrase "no longer" and "rather than" entries positively.

## Outside the 0.7.0 sections

 * The root `CHANGELOG.md` index omits the Debug service.
 * `changeloggen` in `doc/BUILD.bazel` omits krpctest and buildenv. Probably deliberate, since
   neither ships to users. Confirm and leave it.
 * Released sections stay as released, apart from typos such as "Modernise" in cpp 0.6.0.

## Process

One changelog commit, as the changelog rules require, on a branch that touches nothing else. Check the rendered
`doc/src/changelog.rst` with `bazel build //doc:html` and `//doc:spelling`.
