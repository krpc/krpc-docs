# Partial loading

**Status:** in progress, for 0.8. Issue: [#1227](https://github.com/krpc/krpc/issues/1227). A first
implementation of the scanner part (2026-10-31, never a PR) predates the best-effort binding of mod
members, and is stale. Best-effort binding is implemented with no PR yet. The rest is designed.

What kRPC does when part of it cannot load: a service definition that breaks a
[service definition rule](../protocol/service-definition-rules.md), including a name clash, or a mod
integration that cannot bind to its mod after a game or mod update. kRPC disables as little as
possible and keeps running. How the player and the mod author learn of it is in
[problem reporting](problem-reporting.md).

| Part | State |
| --- | --- |
| Scanner: partial load, type cascade, duplicates and clashes | Designed; first implementation stale |
| Mod integrations: bind at load, disable only the failing mod | Designed. Best-effort binding implemented, no PR |
| Call to a disabled member returns its error | Dropped, see below |

## Problem

The scanner checks every service, class, procedure, enumeration, struct and exception when the
server starts. One bad member, in any installed mod, takes all of kRPC down:

| Server | What a scanner error does today |
| --- | --- |
| KSP | `ServicesChecker` disables kRPC entirely. The popup says "plugin has been disabled. See the log for more information" and lists nothing. |
| KSA | `Services.Instance` calls `Scanner.GetServices ()` with no error list, so the first error throws out of the server's startup. |

The player sees kRPC gone, or the game failing to load. The cause is often a third-party mod the
player cannot fix. A KSP or KSA update that breaks one service member breaks every service.

The scanner already does most of the work for a gentler outcome. Given an error list, it catches each
member's error, records it and moves on, leaving the member out. Neither server uses that partial
result.

## Design

kRPC loads every member that scans cleanly and every integration that binds, and disables the rest.
The game keeps loading.

### Errors and warnings

| Kind | Examples | Effect |
| --- | --- | --- |
| **Error** | Invalid parameter or return type, a procedure outside a service, a struct containing itself, a [clash](#clashes) | The member is disabled: absent from `KRPC.GetServices` and not callable |
| **Warning** | Extension members in a class that is not public | kRPC keeps running, and the class's extension members are skipped, as before |

`Scanner.GetServices` takes an error list and a warning list. A null warning list makes warnings
errors, and a null error list makes the first problem throw, which `tools/ServiceDefinitions` relies
on. The public `ServiceProblems` class gives the server the lists from the scan `Services` ran.

### What an error disables

The unit disabled is the smallest one that leaves a consistent service definition:

| Failure | Disabled |
| --- | --- |
| A procedure, method or property | That member |
| A class, enumeration, struct or exception | That type, and every member whose parameter, return type or struct field refers to it |
| A service (invalid attribute, not public static) | The service, its types, and extension members that target it |
| The `KRPC` service, or a scanner exception outside the per-member handlers | kRPC as a whole, as today. Clients cannot connect usefully without `KRPC`. |

**The type cascade runs to a fixed point.** `TypeUtils.IsAValidType` checks a type's attribute, not
whether the type scanned. A procedure returning a class whose scan failed would otherwise reach
clients pointing at a class that does not exist. Disabling a struct can disable a member that takes a
class, which can disable a struct field. So the pass repeats until nothing changes.

**A removed class takes its static methods with it.** They have no parameter of the class type, so
the cascade also checks each procedure's declaring `KRPCClass`.

### Clashes

Every [service definition rule](../protocol/service-definition-rules.md) that compares two names
leaves out each name of a clashing pair, exact duplicates included. Keeping the first one scanned
would make the outcome depend on assembly load order, so adding a member could remove an existing
one.

The one exception is an extension member that clashes with a member of the class itself. The
extension member is left out, and the class keeps its own. The class's members are always scanned
first, so the outcome is fixed, and a mod cannot remove a member of another service by declaring a
clashing extension.

| Clash | Left out |
| --- | --- |
| Two members of a scope that share a [member key](../protocol/service-definition-rules.md#member-keys) or a helper key | Both members |
| Two types of a service, compared case-insensitively | Both types, and the cascade |
| Two services, compared case-insensitively | Both services, their types, and extension members that target them |
| A type named as its service | That type, and the cascade |
| Two parameters of a procedure, or a parameter name that breaks the rule | That procedure |
| An enumeration value name that breaks the rule | The enumeration, and the cascade |
| A shared or 0 id | Both members, see [procedure ids](../protocol/procedure-ids.md#collisions) |

Two classes that declare one service name exactly still merge into one service, as they always have.

### Calling a disabled member

Dropped. A member that fails validation never gets a procedure name, so only the cascade and the
duplicate removals could report one. A call to a disabled member gets "procedure not found", and the
popup and the log give the reason.

## Mod integrations

The scanner checks kRPC's own definitions. A second failure class comes from the services that wrap
other mods: KAC, Infernal Robotics, FAR, RealFuels, AGExt and RemoteTech. These reach the mod's
members by name at run time, so a mod update can remove a member that kRPC uses.

### Baseline: best-effort binding

This design builds on the best-effort binding of mod members (a follow-up to
[#1251](https://github.com/krpc/krpc/pull/1251)):

* `MemberBinder` binds a mod's members through `Accessor`. A missing member gets a delegate that
  throws `MissingMemberException`, such as "Kerbal Alarm Clock: KACAlarm.PlaySound is not available
  in the installed version", and a warning in the log.
* `APILoader` loads an API whose type is found, and stubs each missing method the same way.
* `Accessor.IsMissing` tests for a stub, where a caller has a fallback. FAR's Mach number falls back
  to the stock value this way.

### Load every mod API at startup

Every integration binds its mod's types and members once, when kRPC loads, in the same pass that
scans the services. The scan and the mod loads then finish before any scene, and are reported
together.

The pass finds each integration as a subclass of `ModAPI` in the service assemblies, as the scanner
finds services ([Implementation](#implementation)). A failed load is recorded in `ServiceProblems`,
beside the scan's errors and warnings.

Member binding needs only the mod's types, and those exist once KSP has loaded the assemblies. Two
integrations also need a live object that exists only in some scenes. That object is read through a
bound delegate each scene, and its absence is not a failure:

| Integration | Bound at startup | Per scene |
| --- | --- | --- |
| FAR, RealFuels, AGExt, RemoteTech | Every member (static APIs and part module types) | Nothing |
| Kerbal Alarm Clock | `KerbalAlarmClock` and `KACAlarm` members, `APIInstance`, `APIReady`, `alarms` | The `APIInstance` object and its alarm list. The KAC addon runs in every game scene |
| Infernal Robotics | Controller, servo group and servo members | `Controller.Instance`, which exists in flight only |

Today KAC binds its alarm members on the first alarm wrapped, IR binds on entering flight, and the
`ExternalAPI` loaders run in the first scene. All of them move to startup. No integration needs a
scene to bind.

### A failed load disables that mod only

A loader fails when the mod is installed but kRPC cannot use it. The cases are a type not found, a
version too old, or an essential member missing:

* **Essential members.** These are the members without which no RPC of the integration works, e.g.
  KAC `APIInstance`, `APIReady` and `alarms`, and IR `Controller.Instance`. The integration binds each
  one through `Require`, which throws at load in place of returning a stub.
* **Caught per mod.** Core runs each integration's `Bind` in its own `try`. Any exception marks that
  integration unavailable and records the message.
* **Scope.** The failing mod's integration is disabled. Its RPCs throw the existing "not available"
  error (`KerbalAlarmClock.Available` is false). Another mod's integration, another service and the
  rest of kRPC keep running. For an integration inside SpaceCenter (FAR, RealFuels, AGExt), the
  integration is disabled and SpaceCenter falls back to the stock behavior.
* **Reported** in the popup, in a group of its own, see
  [problem reporting](problem-reporting.md#mod-failures).

### Run-time failures

A missing member that is not essential binds as a stub, and its integration stays available. A call
to an RPC that uses it throws `MissingMemberException` with the stub's message. How each failure
reaches the player is in [problem reporting](problem-reporting.md#what-is-reported).

| | Scanner error | Mod failed to load | Missing non-essential member |
| --- | --- | --- | --- |
| Found | At startup, by the scan | At startup, by the mod's loader | At startup, by `MemberBinder` |
| Effect | Member removed from `KRPC.GetServices` | The integration's RPCs throw "not available" | The RPCs using the member throw `MissingMemberException` |

The call-time error dropped for scanner errors ([Calling a disabled member](#calling-a-disabled-member))
comes free for mod members. The stub carries the message.

## Implementation

### Everything shared lives in core

The KSP and KSA servers share one implementation in `core`. An integration declares what it binds,
and nothing else:

| Concern | Owner |
| --- | --- |
| Finding integrations, running each `Bind` in a `try`, classifying the failure | `core`: `ModAPIs` |
| Binding types and members, stubs, `Require` | `core`: `ModBinder`, `MemberBinder`, `Accessor` |
| Availability, and the "not available" error its RPCs throw | `core`: `ModAPI` base class |
| The list of failed integrations | `core`: `ServiceProblems.Mods` |
| Finding a mod's assembly and version | The server, through `IModAssemblies` |
| Reporting the problems | The server, see [problem reporting](problem-reporting.md) |
| Which members to bind, and which are essential | The integration |

The KSP server implements `IModAssemblies` over `AssemblyLoader.loadedAssemblies`, which carries the
`KSPAssembly` versions. KSA implements it over its own mod list. `APILoader` leaves the server, and
its delegate-property binding becomes `ModBinder.Statics`.

### The integration pattern

An integration is one class. Its fields are bound in `Bind` and read by its RPCs:

```csharp
sealed class KerbalAlarmClockAPI : ModAPI
{
    public KerbalAlarmClockAPI () : base ("Kerbal Alarm Clock", "KerbalAlarmClock", new Version (3, 0, 0, 5)) { }

    internal static Func<bool> APIReady;
    internal static Func<object, string> AlarmName;

    protected override void Bind (ModBinder mod)
    {
        var kac = mod.Type ("KerbalAlarmClock.KerbalAlarmClock");
        APIReady = kac.Require.StaticGetter<bool> ("APIReady");
        var alarm = mod.Type ("KerbalAlarmClock.KACAlarm");
        AlarmName = alarm.Getter<object, string> ("Name");
    }
}
```

* **`ModAPI`** takes the display name, the assembly name and an optional minimum version. Core
  checks the assembly and version before `Bind`.
  * `IsAvailable` is set by core.
  * `CheckAvailable ()` throws "Kerbal Alarm Clock is not available: <reason>".
  * One instance per integration, found by the load pass.
* **`ModBinder`** is the mod's assembly:
  * `Type (name)` gives a `MemberBinder` for a type, and a binder of stubs if the type is missing.
  * `Require.Type (name)` throws instead.
  * `Statics (typeof (FAR), "FerramAerospaceResearch.FARAPI")` binds every delegate property of the
    first type to the static method of the same name in the second.
* **`MemberBinder.Require`** is the same binder with throwing semantics. The essential members read
  as such where they are bound.
* **No null checks.** `Bind` contains no `if` on a lookup. A missing optional member is a stub, and a
  missing essential member throws. The only test an integration writes is `Accessor.IsMissing`,
  where it has a fallback.
* **Per-scene objects** are bound as essential getters at load and called each scene. A null result
  means not ready.

### Exceptions

Core classifies a failure by its exception type. The type decides whether the integration is disabled,
and how the failure is [reported](problem-reporting.md#mod-failures):

| Exception (`KRPC.Utils`) | Raised by | Integration |
| --- | --- | --- |
| `ModNotInstalledException` | Core, assembly not found | Unavailable |
| `ModVersionException` : `ModIncompatibleException` | Core, version below the minimum | Disabled |
| `ModTypeMissingException` : `ModIncompatibleException` | `Require.Type` | Disabled |
| `ModMemberMissingException` : `MissingMemberException` | `Require`, at load; a stub, at a call | Disabled at load; one RPC fails at a call |
| Any other exception from `Bind` | A bug in the integration | Disabled |

`ModMemberMissingException` derives from `MissingMemberException`, so the stubs keep their current
type for clients. It carries `Mod` and `Member`, so core logs and lists it without parsing the message.

### Tests

* `core/test/Service/ScannerTest.cs` gains a test per row of the cascade and clash tables.
* `core/test`: a fake `IModAssemblies` and a test assembly drive `ModAPIs` through each row of the
  exceptions table.
* One in-game test checks that every integration bound against its pinned mod version with no
  stub. A mod update that removes a member then fails the pin bump, before a player sees it.

## Changes

One PR, after procedure ids, which adds the first warnings, and the best-effort binding of mod
members. [Problem reporting](problem-reporting.md#changes) lands with it.

| Area | Change |
| --- | --- |
| `core` scanner | Errors and warnings with a severity; the type cascade; the clash removals; a whole-kRPC failure flag |
| `core` `Services` | Built from the partial scan; services without an id left out of `ServicesById`; public `ServiceProblems`, with the failed mods |
| `core` mods | `ModAPI`, `ModAPIs`, `ModBinder`, `MemberBinder.Require`, `IModAssemblies`, the mod exceptions, `ServiceProblems.Mods` |
| Mod integrations | KAC, IR, FAR, RealFuels, AGExt and RemoteTech each become one `ModAPI`. KAC and IR look up their live object per scene. `APILoader` is removed |
| `server` (KSP) | `ServicesChecker` checks at startup and disables kRPC only on a whole-kRPC failure |
| `tools/ServiceDefinitions` | Unchanged: it passes no lists, so it fails on any error or warning |
| Changelogs | Server: a broken service member disables that member, and a mod that fails to load disables only its integration |

## Alternatives

**Disable a whole service on any of its errors.** Simpler, with no cascade. Rejected: one bad
SpaceCenter member, e.g. after a KSP or KSA update, would take out SpaceCenter, which nearly every
script uses.

**Keep the hard failure, improve only the popup.** Rejected: it still leaves the player with no kRPC
over a mod they cannot fix.
