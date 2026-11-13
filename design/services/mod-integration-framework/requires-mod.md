# `RequiresMod`: the server checks a service's mod

**Status:** proposal (2026-11-12), phase 5 of the [mod integration framework](README.md), for 0.8.
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
[RequiresMod (typeof (ScanSatAPI))]
public static class ScanSat
```

* **Inherited** from a service to its classes and members, as `GameScene` is. The nearest
  attribute applies.
* **Bound by the scanner.** The type must be a `ModAPI` subclass, or the member is a scanner error.
  The scanner stores the `ModAPI` instance with each procedure.
* **The check** is the integration's `CheckAvailable`: "SCANsat is not available: <reason>", or
  "not ready" when its per-scene object is missing ([mod-api.md](mod-api.md#load-every-mod-api-at-startup)).
  `Invoke`, `ExecuteCallInto` and `CheckExpressionGameScene` call it, so server side functions are
  covered. It runs before the game scene check, as the missing mod is the more useful error.
* **Evaluated per call.** KAC and IR become ready and unready as scenes change.
* **`Available` is exempt.** A static property named `Available` skips the check, as it reports
  whether the mod is present. The in-game tests rely on this name.
* **Member level.** SpaceCenter tags the members that fail without FAR or RealAntennas. Members
  with a stock fallback, such as the FAR branches in `Flight.cs`, keep their own code.

Clients and the wire protocol do not change. The exception stays `InvalidOperationException`.

## Changes

| Area | Change |
| --- | --- |
| `core` | `RequiresModAttribute`, the scanner binding and the check in the call paths |
| Every mod service | `[RequiresMod]` on the service. Every `CheckAPI` and `CheckAvailable` goes |
| Trajectories | Gains the check, with the attribute |
| SpaceCenter | The attribute on each member that needs FAR or RealAntennas |
| Docs | The extending pages gain a section on wrapping another mod: `ModAPI` and `RequiresMod` |

## Tests

* `core/test`: the scanner rejects a type that is not a `ModAPI`. A call to a tagged procedure, a
  class member and a server side function each fail with the message when the fake integration is
  unavailable. `Available` does not.
* In game: one test per mod service, run without its mod, checks one RPC's message. It goes in
  `ModServiceTestCase` ([phase 2](README.md#phase-2-test-helpers-in-krpctools)).

## Changelog

* Server: every RPC of a mod service, class members included, fails with "X is not available" and
  the reason when its mod is missing or cannot be used.

## Open

**Generated "Requires X." remarks.** Every member that needs a mod carries a hand-written
`<remarks>Requires X.</remarks>`. docgen could write it from the attribute, if the service
definitions carry the mod's name. Decide once the attribute exists.
