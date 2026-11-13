# `ModAPI`: one class per integration, loaded at startup

**Status:** proposal (2026-11-12), phase 4 of the [mod integration framework](README.md), for 0.8.
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
* **Vendored wrappers.** `KACWrapper` (719 lines) and `IRWrapper` (1322 lines) are copies of the
  mods' own wrappers, with lazy binding and failure handling of their own.

## Design

### The integration pattern

An integration is one class. Its fields are bound in `Bind` and read by its RPCs:

```csharp
sealed class ScanSatAPI : ModAPI
{
    // The name and assembly, generated from the registry
    public ScanSatAPI () : base (ServiceInfo.Mods.SCANsat) { }

    internal static Func<double, double, CelestialBody, int, bool> IsCovered;
    internal static Func<object> SettingsInstance;

    protected override void Bind (ModBinder mod)
    {
        var util = mod.Require.Type ("SCANsat.SCANUtil");
        IsCovered = util.Require.Method<Func<double, double, CelestialBody, int, bool>> ("isCovered");
        SettingsInstance = mod.Type ("SCANsat.SCAN_Settings_Config").StaticGetter<object> ("Instance");
    }
}
```

* **`ModAPI`** takes the display name, the assembly name and an optional minimum version. Core
  checks the assembly and the version before `Bind`. The name and the assembly come from the
  registry, generated into the service's `ServiceInfo.cs` as its id is
  ([phase 1d](README.md#1d-available-and-modversion)). The minimum version stays in the C#.
  * `IsAvailable` is set by core. A service's `Available` RPC returns it, or SpaceCenter's
    `<Mod>Available`.
  * `Version` is the installed version string, read by core from the assembly. A service's
    `ModVersion` RPC returns it, or SpaceCenter's `<Mod>ModVersion`.
  * `CheckAvailable ()` throws `InvalidOperationException`: "SCANsat is not available: <reason>".
    [`RequiresMod`](requires-mod.md) calls it.
  * One instance per integration, found by the load pass, and reached by
    `ModAPI.Get<ScanSatAPI> ()`.
* **`ModBinder`** moves to core. `Require.Type` and `MemberBinder.Require` throw in place of
  binding a stub, so the essential members read as such where they are bound.
* **`Statics (typeof (API), "RemoteTech.API.API")`** binds every delegate property of the first
  type to the static method of the same name in the second. It replaces `APILoader` for RemoteTech
  and Trajectories.
* **No null checks.** `Bind` has no `if` on a lookup. The only test an integration writes is
  `Accessor.IsMissing`, where it has a fallback.

### Load every mod API at startup

Core finds each `ModAPI` subclass in the service assemblies, as the scanner finds services. The
load pass runs beside the service scan, before any scene. Member binding needs only the mod's
types, which exist once the game has loaded the assemblies.

Two integrations also need a live object that exists only in some scenes. They bind a getter for it
at startup and call it per scene. A null result means "not ready", which is not a failure:

| Integration | Per scene |
| --- | --- |
| Kerbal Alarm Clock | The `APIInstance` object and its alarm list. The KAC addon runs in every scene |
| Infernal Robotics | `Controller.Instance`, which exists in flight only |
| Every other integration | Nothing. Raster Prop Monitor's computers and monitors are part modules, found through the vessel |

`ModAPI.Ready` is a virtual property, true by default. KAC and IR override it with the per-scene
object, and `CheckAvailable` reports "not ready" when it is false.

### `IModAssemblies`

Core finds a mod's assembly through an interface each server implements:

| Server | Implementation |
| --- | --- |
| KSP | Over `AssemblyLoader.loadedAssemblies`, with the `KSPAssembly` versions and each assembly's path |
| KSA | Over its mod list, once KSA builds against a 0.8 core |

The path lets an integration tell its mod from a same-named assembly elsewhere, as
[MechJeb](#a-mod-a-service-replaces) needs.

### A failed load disables that mod only

A load fails when the mod is installed but kRPC cannot use it: a type not found, a version too
old, or an essential member missing.

* Core runs each `Bind` in its own `try`. Any exception marks that integration unavailable and
  records the reason.
* The failing integration's RPCs throw "not available", with the reason. Other integrations, other
  services and the rest of kRPC keep running.
* An integration inside SpaceCenter, such as FAR, RealFuels or AGExt, is disabled, and SpaceCenter
  falls back to the stock behavior.

### Exceptions

Core classifies a failure by its exception type, in `KRPC.Utils`:

| Exception | Raised by | Integration |
| --- | --- | --- |
| `ModNotInstalledException` | Core, assembly not found | Unavailable |
| `ModVersionException` : `ModIncompatibleException` | Core, version below the minimum | Disabled |
| `ModTypeMissingException` : `ModIncompatibleException` | `Require.Type` | Disabled |
| `ModMemberMissingException` : `MissingMemberException` | `Require` at load, or a stub at a call | Disabled at load. One RPC fails at a call |
| `ModConflictException` : `ModIncompatibleException` | A `Bind`, on a conflicting mod | Disabled, with the integration's message |
| Any other exception from `Bind` | A bug in the integration | Disabled |

`ModMemberMissingException` keeps the stubs' exception type for clients, and carries `Mod` and
`Member`, so core logs it without parsing the message.

### A mod a service replaces

The MechJeb service is a port of the standalone KRPC.MechJeb mod. A player who updates kRPC with
the old mod still installed has two services named `MechJeb`.

`MechJebAPI.Bind` looks for a `KRPC.MechJeb` assembly outside kRPC's folder, and throws
`ModConflictException`: "remove GameData/KRPC.MechJeb, kRPC now includes the MechJeb service". Both
DLLs are named `KRPC.MechJeb.dll`, so the check matches by path. One in-game run with the old mod
installed checks how KSP loads the two.

The two services also clash in the scanner. Until [partial loading](../../server/partial-loading.md)
lands, that clash still disables kRPC, and the conflict message is in the log.

### Reporting

* Core records each failure in `ServiceProblems.Mods`, which the popup of
  [problem reporting](../../server/problem-reporting.md) lists once #1227 lands.
* The log takes each failure at the level problem reporting gives it: info for a mod not
  installed, an error for any other failure.
* `APILoader` and its popup go. Until the problem popup lands, a failed mod is reported in the log
  and by its RPCs' error.

## Changes

| Area | Change |
| --- | --- |
| `core` | `ModAPI`, the load pass, `ModBinder` with `Require` and `Statics`, `IModAssemblies`, the exceptions, `ServiceProblems.Mods` |
| `server` (KSP) | `IModAssemblies` over `AssemblyLoader`. `APILoader` and `ExternalAPIAddon` go |
| Every mod service | One `ModAPI`. `Addon.cs` goes |
| KAC, IR | `KACWrapper` and `IRWrapper` replaced by a `ModAPI` binding at startup, with `Ready` per scene. These two are most of the phase |
| MechJeb | The KRPC.MechJeb conflict check |
| SpaceCenter | FAR, RealFuels, AGExt, RealAntennas and RemoteTech each become a `ModAPI` |

## Tests

* `core/test`: a fake `IModAssemblies` and a test assembly drive the load pass through each row of
  the exceptions table.
* In game: every integration's tests. A run with KRPC.MechJeb installed checks the conflict.
* [Phase 7](README.md#phase-7-no-stubs-at-the-pinned-version) checks each integration binds with no
  stub at its pinned version.

## Changelog

* Server: a mod kRPC cannot use disables only its own integration, and its RPCs give the reason.
* None for the KRPC.MechJeb conflict. The MechJeb service is new in 0.8.

## Alternatives

**Keep the vendored KAC and IR wrappers.** Rejected. They bind lazily, so a broken member shows up
on first use in a scene, and they fail differently from every other integration.
