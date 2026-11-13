# `RequiresMod`: the server checks a service's mod

**Status:** implemented (2026-11-13), not yet merged, on branch `requires-mod`. Not yet run in
game. Phase 5 of the [mod integration framework](README.md), for 0.8.
Issue: [mod-integration-framework.md](../../../issues/mod-integration-framework.md). Builds on
[`ModAPI`](mod-api.md).

## Problem

Each RPC of a mod service checks its mod by hand:

```csharp
[KRPCProcedure]
public static Comms Comms (SpaceCenter.Services.Vessel vessel)
{
    CheckAPI ();
    return new Comms (vessel);
}
```

* A forgotten call reaches the mod's unbound delegates. Trajectories has no check on any of its 24
  RPCs, so a call without the mod throws `NullReferenceException`.
* Each service writes its own helper, with its own message. IR says "is not installed.", the rest
  "is not available".
* Members of `KRPCClass` types have no check. They rely on their instance coming from a checked
  RPC.

## Design

An attribute names the integration a service, class or member needs:

```csharp
[KRPCService (Id = 16)]
[RequiresMod (typeof (API))]
public static class ScanSat
```

* **All of a list, any of several attributes.** The types in one attribute must all be
  available. Several attributes on one member mean any one of them will do. `Part.Tag` takes
  `[RequiresMod (typeof (KSPCommunityPartModules))]` and `[RequiresMod (typeof (KOS))]`, two
  integrations with nothing to bind. The scanner stores the alternatives as a `ModRequirement`.
  The message names the unavailable integrations: "KSPCommunityPartModules or kOS is not
  available: not installed". Predicates were rejected: an attribute cannot hold a delegate, and a
  predicate defeats the scanner check, generated docs and the shared message.
* **Inherited** from a service to its classes and members, as `GameScene` is. The nearest
  attribute applies. An extension member takes it from the member, then the static class that
  declares it, then the class it extends.
* **Bound by the scanner.** The type must be a concrete `ModAPI` subclass, or the member is a
  scanner error. The scanner stores the `ModAPI` instance with each procedure, as
  `ProcedureSignature.RequiredMod`.
* **One instance per integration, created on first use.** `ModAPI.Get` creates the instance when
  the load pass has not, so the scanner can bind it in any order, and in tools with no load pass.
  The load pass binds the existing instance. `Get` no longer throws "has not been loaded".
* **The check** is the integration's `CheckAvailable`: "SCANsat is not available: <reason>"
  ([mod-api.md](mod-api.md#a-failed-load-disables-that-mod-only)).
  `Invoke`, `ExecuteCallInto` and the server side function check call it. It runs before the game
  scene check, as the missing mod is the more useful error. The function check, which now covers
  both, is renamed from `CheckExpressionGameScene` to `CheckExpressionAvailable`.
* **One field read per call.** An integration's availability is fixed once the load pass has run.
* **`Available` is exempt.** A static property of that name skips the check, as it reports
  whether the mod is present. The in-game tests rely on this name. MechJeb's `Ready` keeps the check.
* **Member level.** SpaceCenter tags the members that fail without FAR, RealAntennas or
  RealFuels. RealFuels was left out of the proposal: its members also fail without the mod.
  The guards that report whether a part is the mod's, such as `HasRealFuels`, stay untagged.
  Members with a stock fallback, such as the FAR branches in `Flight.cs`, keep their own code.
  They take the fallback when `CheckInstalled` returns false.
* **MechJeb's `Ready`** throws without MechJeb, and reports whether the active vessel has MechJeb.

Clients and the wire protocol do not change. The exception stays `InvalidOperationException`.

## Changes

| Area | Change |
| --- | --- |
| `core` | `RequiresModAttribute`, the scanner binding and the check in the call paths |
| Every mod service | `[RequiresMod]` on the service. Every `CheckAPI` and `CheckAvailable` goes |
| Trajectories | Gains the check, with the attribute |
| SpaceCenter | The attribute on each member that needs FAR, RealAntennas or RealFuels. The RealAntennas module and link checks say the part or link is not the mod's |
| Docs | A new extending page, *Wrapping Another Mod*: `ModAPI` and `RequiresMod` |

## Tests

* `core/test`: the scanner rejects a type that is not a `ModAPI`. A call to a tagged procedure, a
  class member and a server side function each fail with the message when the fake integration is
  unavailable. `Available` does not.
* In game: one test per mod service, in a class that requires no mods, calls one RPC and checks
  its message. LiDAR is deprecated, so it gets none. SpaceCenter's FAR, RealAntennas and
  RealFuels members get one each, in `test_supported_mods.py`.

## Changelog

* Server: the class members of a mod service fail with the reason when the mod is missing or
  failed to load. Phase 4's entry already covers the service's own RPCs.
* SpaceCenter: the FAR and RealFuels members do the same. RealAntennas support is unreleased, so it
  takes no entry.

## Open

**Generated "Requires X." remarks.** Every member that needs a mod carries a hand-written
`<remarks>Requires X.</remarks>`. docgen could write it from the attribute, if the service
definitions carry the mod's name. Decide once the attribute exists.
