# Mod binding

**Status:** proposal (2026-11-12), phase 3 of the [mod integration framework](README.md), for 0.8.
Issue: [mod-integration-framework.md](../../../issues/mod-integration-framework.md). `MemberBinder`
and the stubs are built for KAC, IR, FAR and RealFuels on an unpushed branch from 2026-11-03, in
three commits. This phase rebases them onto main and extends them to every integration.

## Problem

The integrations bind to their mods in [seven ways](README.md#binding-to-the-mod), and a missing
member has a different effect in each:

| Integrations | A missing member |
| --- | --- |
| KER, SCANsat, Raster Prop Monitor | Makes `IsAvailable` false, which disables the whole service |
| RemoteTech, Trajectories (`APILoader`) | Disables the whole API, with a popup |
| MechJeb | Binds a `Value<T>` that throws on use, and one warning lists every missing member |
| KAC, IR, FAR, RealFuels, AGExt, RealAntennas, DockingCamera | Leaves a null delegate, which throws `NullReferenceException` on use |

A mod update that removes one member a player never uses can take out a whole service. Each
integration also finds the mod's assembly by its own loop over `AssemblyLoader.loadedAssemblies`.

## Design

A missing member fails only the calls that use it, with a message naming the mod and the member.
Every integration binds through the same two classes.

### Stubs

`Accessor` gains two helpers:

* `Accessor.Missing<TDelegate> (message)` builds a delegate that throws `MissingMemberException`
  with the message.
* `Accessor.IsMissing (d)` is true for a null delegate or a stub. An integration with a fallback
  tests it, e.g. FAR's Mach number falls back to the stock value.

### `MemberBinder`

`MemberBinder` in core binds the members of one type of a mod through `Accessor`:

```csharp
var util = mod.Type ("SCANsat.SCANUtil");
IsCovered = util.Method<Func<double, double, CelestialBody, int, bool>> ("isCovered");
GetCoverage = util.Method<Func<int, CelestialBody, double>> ("GetCoverage");
var settings = mod.Type ("SCANsat.SCAN_Settings_Config");
Settings.Instance = settings.StaticGetter<object> ("Instance");
```

* `Getter`, `StaticGetter`, `Setter`, `Field` and `Method` match the `Accessor` helpers of the
  same names. `For` gives a binder for another type of the same mod.
* A member that is not found binds a stub, and logs one warning: "SCANsat: SCANUtil.isCovered is
  not available in the installed version".
* A binder for a missing type binds a stub for every member, so `Bind` code has no null checks.

### `ModBinder`

`ModBinder` in the KSP server finds a mod's assembly by name, and gives a `MemberBinder` per type:

* `ModBinder.Find ("SCANsat")` returns null when the assembly is not loaded.
* `Type (fullName)` returns a `MemberBinder`, and logs a warning when the type is missing.

It replaces the per-integration loops over `AssemblyLoader.loadedAssemblies`. Phase 4 moves it to
core, behind an interface each server implements ([mod-api.md](mod-api.md#imodassemblies)).

### Availability until phase 4

Each integration keeps its `IsAvailable`, now true when the assembly is found and the version
suffices. A missing member no longer makes it false. A member without which no RPC works, such as
KAC's `APIInstance`, is tested with `IsMissing` and keeps the integration unavailable. Phase 4
replaces these tests with `Require` ([mod-api.md](mod-api.md#a-failed-load-disables-that-mod-only)).

`APILoader` stubs each missing method in place of giving up on the API. It stays until phase 4.

### Logging

| Case | Log |
| --- | --- |
| Mod not installed | One info line. Nothing else, so Trajectories logs no errors when absent |
| Mod installed | One info line with its version |
| Missing type or member | One warning each, at load |

## Changes per integration

| Integration | Change |
| --- | --- |
| KAC, IR, FAR, RealFuels | From the branch: bind through `MemberBinder`. Dead bindings the warnings exposed are removed |
| KER, SCANsat, Raster Prop Monitor | The `missing` list and helper sets go. `ModBinder` and `MemberBinder` bind every member |
| MechJeb | `Reflection.cs` and `Value<T>` go. `Field` gives the same getter and setter, and stubs throw on use as before |
| Trajectories | The nested type lookups go. Skips every loader when the assembly is missing |
| DockingCamera, AGExt, RealAntennas | Their loaders bind through `MemberBinder` |
| RemoteTech service | Uses SpaceCenter's `RemoteTech` binding, made public. Its own copy goes |
| LIDAR | Unchanged, as it is deprecated |

## Tests

* `core/test`: `MemberBinderTest` and the `Accessor` stub tests, from the branch.
* In game: each integration's tests at its pinned version, with no stub warning in `KSP.log`.
* A negative control per integration: a misspelled member fails only the tests that use it, with
  the stub's message. It is run once by hand, and not committed.

## Changelog

* Server: a mod update that removes a member fails only the RPCs that use it, with a message naming
  the member.
* None for Trajectories' log errors. The service is new in 0.8.
