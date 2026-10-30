# Relicense kRPC to MIT

**Status:** proposal (2026-10-30). Target: 0.8.

kRPC moves from LGPLv3, with GPLv3 parts, to MIT. MIT is the most open of the common licenses, and
is the usual choice in the KSP and KSA communities. It keeps the one condition that matters here:
copies must carry the copyright notice. Releases up to 0.7 stay under their current licenses.

Two things stand in the way:

1. **Third-party GPL code** in the tree, which only a rewrite can remove.
2. **Other contributors' copyright**, which needs their consent, or a rewrite of their code.

## Why Parts Are GPL Today

| Part | Reason | Still applies? |
|---|---|---|
| Whole project (GPLv3, April 2014) | The first auto-pilot adapted steering and reference-frame code from MechJeb2, kOS and RemoteTech2. | No. That code was removed in July 2014 and August 2015. |
| `service/SpaceCenter` (GPL since the January 2016 LGPL split) | Issue #172: "contains some GPL'd autopilot code from MechJeb/RemoteTech". | No, the code named was already gone. Two later borrowings are below. |
| `service/Debug` | Its commit says it holds HyperEdit-derived orbit code. | Mostly no. One HyperEdit line remains. It also compiles against SpaceCenter. |
| `tools/krpctools` | No reason given. No GPL code or dependency found. | Choice only. |
| `tools/ServiceDefinitions` | No reason given. No GPL code or dependency found. | Choice only. |

kOS's NameTag code (GPLv3) shipped in SpaceCenter from 0.4 to 0.6.0. It was removed in #1155.

## Third-Party GPL Code to Rewrite

These need a clean-room rewrite whether or not the relicense goes ahead. Two of them sit in parts
of the tree that are LGPL today.

| Code | Source | Evidence | Size |
|---|---|---|---|
| `CelestialBody.cs`: the raycast surface height, in two places | kOS `GeoCoordinates.cs` (GPLv3) | Two comments copied word for word, and the same constants. From #524. | ~30 lines |
| `SpaceCenter.cs`: `WarpTo` and the rails and physics warp helpers | MechJeb2 `MechJebModuleWarpController.cs` (GPLv3) | Same method names, a 2 s change guard, the same defaults, the same altitude limit test and control flow. No attribution. | ~120 lines |
| `service/InfernalRobotics/src/IRWrapper.cs` | Infernal Robotics `IRWrapper` (GPLv3) | A vendored, modified copy, with no header. LGPL in kRPC today. | One file |
| `Debug.cs`: `WaitForLanded` velocity damping | HyperEdit `Lander.cs` (GPLv3) | Confirmed by an earlier code comment. | 1 line |
| `Debug.cs`: `SignedSemiMajorAxis` and the mean-anomaly wrap | HyperEdit `OrbitEditor.cs` | Weak: the same idea, written differently. Rewrite only to be safe. | ~20 lines |

Checked and not derived:

- **Inertia tensor:** written for kRPC by Lamont Granquist in 2016. kOS and MechJeb took the same
  code later.
- **The current auto-pilot:** no matches beyond generic math.
- **PID controller:** a textbook design. It links Brett Beauregard's blog, which can be replaced
  with a textbook reference.
- **Mod interop** (FAR, RemoteTech, AGExt, RealFuels, Firespitter): reflection only.

Kerbal Engineer Redux and RemoteTech2 were not compared directly.

## Permissive Third-Party Code

This code stays, with its notice:

- **`StockAerodynamics.cs`:** from KSPTrajectories, under MIT. Every matching span predates
  Trajectories' 2018 move to GPLv3.
- **`AutoLoadGame.cs`, `AutoSwitchVessel.cs` (TestingTools):** from AutoLoadGame, under MIT.
- **`KACWrapper.cs`:** from Kerbal Alarm Clock, under MIT.
- **`client/python/krpc/decoder.py`:** contains protobuf code, under BSD-3-Clause.

## Contributors

The audit covered 45 people (57 author names) on `main`. It counted each person's surviving lines
with `git blame -w -M -C -C`, and checked all 96 merged outside PRs for hidden authors.

| Contributor | Code lines surviving | Where | Plan |
|---|---|---|---|
| Dominique Archambault | ~2,340 | SpaceCenter (aero simulation, alarms, thrust reverser, trim, crew), tests, TestingTools, Debug | Ask. Too large to rewrite. |
| Strtus | ~700 | SpaceCenter (editor inertia, deflected surfaces), C# client expressions | Ask |
| Art Whaley | ~410 | SpaceCenter (robotics, harvesters, rendezvous, docking ports, resource drains) | Ask |
| JonnyOThan | ~290 | SpaceCenter (crew, launch sites, map filter, parachutes), server addon fix | Ask |
| bpengu1n (Benjamin Y) | ~225 | SpaceCenter Stage API and docs | Ask |
| nullprofile | ~170 | LiDAR and DockingCamera services, `RoboticController` | Ask, or rewrite |
| kylewill0725 | ~130 | krpctools Python stub generation | Ask, or rewrite |
| Sofie | ~110 | SpaceCenter camera | Ask, or rewrite |
| Jan Moeller | ~90 | SpaceCenter waypoints, science | Ask, or rewrite |
| jwvanderbeck, jpx, poisonbl, Lamont Granquist | 20-50 each | SpaceCenter wrappers and small features | Ask, or rewrite |
| ThePuzzlemaker, FumbieNumbie, Loran425, Andrej Smigala | 10-30 each | SpaceCenter, Java client | Ask, or rewrite. FumbieNumbie's raycast is rewritten anyway. |
| Gary | prose only | GitHub issue and PR templates | Ask, or rewrite |
| 13 others | 6 or fewer | One-liners | No action: trivial |
| 11 others | none | | No action |

Audit notes:

- About 100 lines blamed on nullprofile are Art Whaley's. They came in through #644, which includes
  Art's #612 and #614.
- Blame credits the owner with lines that were reformatted or moved. Surviving counts are a lower
  bound.

## Phases

1. **Rewrite the third-party GPL code.** One PR, independent of the relicense. Afterwards
   SpaceCenter has no third-party GPL code.
2. **Ask for consent.** Open one GitHub issue that explains the move to MIT, and @-mention each
   contributor marked "Ask". Each contributor replies with their agreement. Rewrite the code of
   anyone who declines or does not reply by a set date, if it is small enough.
3. **Relicense.** One PR:
   - Replace `LICENSE`, `COPYING` and `COPYING.LESSER` with MIT, keeping the third-party notices.
   - Replace the per-package license files with MIT.
   - Change the generated license texts in the root, krpctools and TestServer BUILD files.
   - Set the SPDX metadata to `MIT`: pyproject files, NuGet, the Lua rockspec and the vcpkg ports.
   - Add a changelog entry marked **Breaking:**.

**Fallback.** If Dominique Archambault does not consent, SpaceCenter cannot become MIT. It could
still become LGPL once phase 1 lands, if the SpaceCenter contributors agree to that instead.
