# `ModAPI`: one class per integration, loaded at startup

**Status:** implemented (2026-11-12), not yet merged, on branch `mod-api`. Checked in game.
Phase 4 of the [mod integration framework](README.md), for 0.8.
Issue: [mod-integration-framework.md](../../../issues/mod-integration-framework.md). Builds on
[mod binding](binding.md).

## Problem

After [phase 3](binding.md) every integration binds the same way, but each still decides when to
bind, what to check first and what a failure means:

* **When.** Most mod services carry an `Addon.cs`, a `LoadOnceAddon` that calls `API.Load` in the
  first scene. SpaceCenter has `ExternalAPIAddon`. KAC binds its alarm members on the first alarm
  wrapped, and IR binds on entering flight.
* **Version checks.** `APILoader` calls take a minimum version, `KACWrapper` checks its own, and
  the rest check none.
* **Failure.** An integration that cannot bind sets its own `IsAvailable`, logs in its own words,
  or shows `APILoader`'s popup. Nothing records which mods failed, so nothing can report them.
* **Vendored wrappers.** `KACWrapper` (721 lines) and `IRWrapper` (1302 lines) are copies of the
  mods' own wrappers, with lazy binding and failure handling of their own.
* **Readiness.** KAC's `Available` and IR's `Ready` each report on the mod's live object in their
  own way. KAC's `Available` is whether its instance exists in the scene. IR's `Ready` is whether
  IR's controller holds the active vessel's servo groups.

## Design

### The integration pattern

An integration is one class, named `API` in its service's namespace. `Bind` sets its static fields,
and its RPCs read them. Some integrations keep another name, where the service already uses `API`
or the class predates phase 4:

| Integration | Class |
| --- | --- |
| Trajectories | `TrajectoriesAPI`, as `API` holds the static delegates its `Statics` binds |
| MechJeb | `Bindings`, the binding class of [phase 3](binding.md) |
| FAR, AGExt, RealFuels, RealAntennas, RemoteTech | Named after the mod, in SpaceCenter's `ExternalAPI` namespace |

SCANsat's integration:

```csharp
sealed class API : ModAPI
{
    // The name and assembly, generated from the registry
    public API () : base (ServiceInfo.Mods.SCANsat.Name, ServiceInfo.Mods.SCANsat.Assembly) { }

    internal static Func<double, double, CelestialBody, int, bool> IsCovered;
    internal static Func<object> SettingsInstance;

    protected override void Bind (ModBinder mod)
    {
        var util = mod.Type ("SCANsat.SCANUtil");
        IsCovered = util.Method<Func<double, double, CelestialBody, int, bool>> ("isCovered");
        SettingsInstance = mod.Type ("SCANsat.SCAN_Settings_Config").StaticGetter<object> ("Instance");
    }
}
```

* **`ModAPI`** takes the display name and the assembly name. Core checks the assembly before
  `Bind`. Both names come from the registry, generated into the service's `ServiceInfo.cs` as its
  id is ([phase 1d](README.md#1d-available-for-every-mod)). The instance holds the integration's
  status, and the static fields hold its bindings.
  * `IsAvailable` is set by core. A service's `Available` RPC returns it, or SpaceCenter's
    `<Mod>Available`.
  * `IsInstalled` is true when core finds the assembly, whether or not the load succeeds.
  * `CheckInstalled ()` is for a stock fallback. It returns `IsInstalled`, and throws as
    `CheckAvailable` does for a mod that is installed and not available. The fallback runs only
    for a mod that is not installed.
  * `Reason` says why the integration is not available: "not installed", the missing required
    member, or the exception from `Bind`.
  * `MissingMembers` lists the members bound as stubs.
    [Phase 7](README.md#phase-7-no-stubs-at-the-pinned-version) reads it.
  * `CheckAvailable ()` throws `InvalidOperationException`: "SCANsat is not available: <reason>".
    [`RequiresMod`](requires-mod.md) calls it.
  * One instance per integration, created by the load pass, and reached by
    `ModAPI.Get<API> ()`.
* **No minimum version.** Each binding names the members it needs, and a missing one is a stub.
  A version cut-off would disable a mod that mostly works. The docs name the tested versions
  ([phase 6](README.md#phase-6-tested-mod-versions-in-the-docs)), and a popup for an untested
  version can follow.
* **`ModBinder`** moves to core. A missing type or member binds a stub, as in
  [phase 3](binding.md#stubs), so only the RPCs that use it fail. If `isCovered` is renamed, the
  coverage RPCs throw and the settings RPCs keep working. Each `MemberBinder` the `ModBinder`
  creates adds its stubs to the integration's `MissingMembers`.
* **`Require`** is for a member that every RPC of the integration goes through. `Require.Type`
  and `MemberBinder.Require` throw in place of binding a stub, and fail the load. Most
  integrations require nothing.
* **`Statics (typeof (RemoteTech), "RemoteTech.API.API")`** binds every static delegate property
  of the first type to the static method of the same name in the second. It replaces `APILoader`
  for RemoteTech, Trajectories, FAR, AGExt and LIDAR.
* **RemoteTech** has its `ModAPI` in SpaceCenter, as SpaceCenter's autopilot uses it and the
  RemoteTech service is optional. It names the mod directly, as SpaceCenter's registry entry does
  not list it. The autopilot calls `HasFlightComputer`, `AddSanctionedPilot` and
  `RemoveSanctionedPilot` every physics frame, so those are required. The RemoteTech service reads
  this `ModAPI`.
* **No null checks.** `Bind` has no `if` on a lookup.

### Load every mod API at startup

`ServicesChecker`, the KSP server's addon that runs as the game starts, calls the load pass with
the server's `IModAssemblies`. The load pass finds each `ModAPI` subclass, creates it and binds
it, before any scene. Member binding needs only the mod's types, which exist once the game has
loaded the assemblies.

* The pass searches only the assemblies that reference `KRPC.Core`. It catches
  `ReflectionTypeLoadException` from a broken mod, and takes the types that did load.
* An integration may override `NotReady`, which gives the reason the mod cannot serve a call
  yet, or null. `CheckAvailable`, and so each `[RequiresMod]` call, checks it once the
  integration is available. `Available` does not. Kerbal Alarm Clock uses it, as below. An RPC
  that needs a live object of the mod reads it when called:

| Integration | Live object |
| --- | --- |
| Kerbal Alarm Clock | `APIInstance` and its alarm list. KAC creates the instance in `Awake`, in flight, the space center, the tracking station and the editor. The KAC service is limited to every scene but the mission builder, apart from `Available`. The space center's facilities count as the space center. `NotReady` holds a call until the instance exists and KAC's `APIReady` is set, after it loads the save's alarms |
| Infernal Robotics | `Controller.Instance`, which exists for the whole flight scene. The service runs only in flight |
| Every other integration | None, or one found through the vessel, such as Raster Prop Monitor's computers and MechJeb's core |

### Infernal Robotics without `Ready`

IR's `Ready` property goes, in 0.8 with no deprecation, as 0.8 breaks the API in other places
too. The integration works for every vessel in flight: kRPC builds the servo groups of a vessel
that IR's controller does not hold.

Group state lives only in IR's controller: speed factor, expanded, advanced mode, presets and
keys. On a group kRPC builds, those members throw, with a message chosen by the group's vessel:

| Vessel | Message |
| --- | --- |
| The active vessel, before IR's controller holds its groups, shortly after a flight scene loads | "not available until Infernal Robotics has loaded the vessel's groups" |
| Any other vessel | "not available for a servo group on a non-active vessel", with the members such a group supports |

`test_servo_group` waits on one of those members in place of `ready`.

MechJeb keeps `Ready`, whether the active vessel has a MechJeb core. It is a fact about the vessel,
not the integration, and is the property a client waits on after a launch.

### `IModAssemblies`

Core finds a mod's assemblies through an interface each server implements:

| Server | Implementation |
| --- | --- |
| KSP | Over `AssemblyLoader.loadedAssemblies`, with each assembly's path |
| KSA | Over its mod list, once KSA builds against a 0.8 core |

The path gives `ModBinder` the assemblies beside the main one, such as MechJeb's `MechJebLib`.

### A failed load disables that mod only

A load fails when the mod is installed but kRPC cannot use any of it: a required member is missing,
or `Bind` throws. A missing member that is not required fails only the RPCs that use it, and the
integration stays available.

* Core runs each `Bind` in its own `try`. Any exception marks that integration unavailable and
  records the reason.
* The failing integration's RPCs throw "not available", with the reason. Other integrations, other
  services and the rest of kRPC keep running.
* An integration inside SpaceCenter, such as FAR, RealFuels or AGExt, is disabled the same way.
  Its RPCs throw with the reason, those with a stock fallback included, as the mod is installed.

### Exceptions

Core classifies a failure by its exception type, in `KRPC.Utils`:

| Exception | Raised by | Integration |
| --- | --- | --- |
| `ModTypeMissingException` | `Require.Type` | Disabled |
| `ModMemberMissingException` : `MissingMemberException` | `Require` at load, or a stub at a call | Disabled at load. One RPC fails at a call |
| Any other exception from `Bind` | A bug in the integration | Disabled |

A mod that is not installed is a state core records, with no exception. Its RPCs throw the
not available error.

`ModMemberMissingException` carries `Mod` and `Member`, so core logs it without parsing the
message. `MemberBinder` builds its stubs to throw it, and `Accessor.Missing` keeps throwing
`MissingMemberException` for other callers. Clients see the message in an `RPCError`, as for any
exception.

### The KRPC.MechJeb mod

The MechJeb service is a port of the standalone KRPC.MechJeb mod, and both DLLs are named
`KRPC.MechJeb.dll`. The game loads one assembly per file name, the one with the highest file
version. kRPC's 0.8.0.0 is above the old mod's 0.7.1, so a player who keeps the old mod gets kRPC's
service, and the old DLL is skipped. There is no conflict check.

### Reporting

* Phase 4 adds `ServiceProblems` to core, with only `Mods`: the integrations of installed mods
  that failed to load or bound a stub, each with its `Reason` and `MissingMembers`. [Partial loading](../../server/partial-loading.md) adds the scanner's lists,
  and the popup of [problem reporting](../../server/problem-reporting.md) lists them all once
  #1227 lands.
* The log takes each failure at the level problem reporting gives it: info for a mod not
  installed, an error for any other failure.
* `APILoader` and its popup go. Until the problem popup lands, a failed mod is reported in the log
  and by its RPCs' error.

## Changes

| Area | Change |
| --- | --- |
| `core` | `ModAPI`, the load pass, `ModBinder` with `Require` and `Statics`, `IModAssemblies`, the exceptions, `ServiceProblems.Mods`. `MemberBinder` stubs throw `ModMemberMissingException` |
| `server` (KSP) | `IModAssemblies` over `AssemblyLoader`. `ServicesChecker` runs the load pass. `APILoader`, `LoadOnceAddon`, `ModBinder` and `ExternalAPIAddon` go |
| Every mod service | One `ModAPI`. `Addon.cs` goes. Each `CheckAPI` calls `CheckAvailable`, and `Available` returns `IsAvailable`, until [phase 5](requires-mod.md) removes the checks |
| KAC | `KACWrapper` replaced by a `ModAPI`. `Available` no longer depends on the scene. The service is limited to every scene but the mission builder |
| IR | `IRWrapper` replaced by a `ModAPI`, with the servo and group adapters it uses. `Ready` goes, and the group state members give the errors above |
| LIDAR | Its `API.Load` becomes a `ModAPI` with `Statics`, so `APILoader` can go |
| SpaceCenter | FAR, RealFuels, AGExt, RealAntennas and RemoteTech each become a `ModAPI`. `<Mod>Available` returns `IsAvailable`. The FAR and AGExt fallbacks call `CheckInstalled` |
| RemoteTech | Uses SpaceCenter's RemoteTech `ModAPI` |

## Tests

* `core/test`: a fake `IModAssemblies` and a test assembly drive the load pass through each row of
  the exceptions table, and check `MissingMembers`.
* In game: every integration's tests.
* [Phase 7](README.md#phase-7-no-stubs-at-the-pinned-version) checks each integration binds with no
  stub at its pinned version.

## Changelog

* Server: a mod kRPC cannot use disables only its own integration, and its RPCs give the reason.
* Server: a mod loads whatever its version.
* Infernal Robotics: **Breaking:** remove `Ready`.
* Kerbal Alarm Clock: limit the service to the scenes KAC runs in, apart from `Available`.

## Alternatives

**Keep the vendored KAC and IR wrappers.** Rejected. They bind lazily, so a broken member shows up
on first use in a scene, and they fail differently from every other integration.

**Keep per-scene readiness in `ModAPI`.** First rejected, then adopted in review (2026-11-13) as
`NotReady`. KAC's list RPCs read its alarms in the frames before KAC has loaded them, so each KAC
call needs the check, and a hook in `ModAPI` runs it on every call with no code in the RPCs. IR's
group state stays per object, as it concerns one vessel's groups.
