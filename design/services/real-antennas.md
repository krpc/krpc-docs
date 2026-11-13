# RealAntennas support

**Status:** implemented, PR not yet opened (2026-11-10). All four phases, verified in game. Issue: [issues/real-antennas.md](../../issues/real-antennas.md).

## Context

[RealAntennas](https://github.com/KSP-RO/RealAntennas) (KSP-RO fork, v2.12.0.0, assembly
`RealAntennas`) replaces CommNet's range model with a link budget: gain, transmit power, RF band,
tech level, data rate and pointing. Realism Overhaul installs it, and it ships a stock planet pack,
so it runs in a stock game.

It works by subclassing the stock types kRPC already wraps:

| Stock type | RealAntennas subclass | kRPC wrapper |
| --- | --- | --- |
| `ModuleDataTransmitter` | `ModuleRealAntenna` | `Parts.Antenna` |
| `CommNetVessel` | `RACommNetVessel` | `Comms` |
| `CommLink` | `RACommLink` | `CommLink` |
| `CommNode` | `RACommNode` | `CommNode` |
| `CommNetHome` | `RACommNetHome` (ground stations) | `CommNode.IsHome` |

A ModuleManager patch removes the stock transmitter from the stock antennas and adds
`ModuleRealAntenna`, and gives every command part one. So with the mod installed, every
`Antenna` kRPC returns is a RealAntenna, and the existing members keep working on it.

Each `ModuleRealAntenna` holds a `RealAntenna` (`RAAntenna`) with the link-budget values. Each
`RACommLink` holds the forward and reverse data rates and the antennas at each end.

## What the Existing Members Return

| Member | Under RealAntennas |
| --- | --- |
| `Antenna.State`, `Deployed`, `Transmit`, `Cancel`, `CanTransmit` | Unchanged. `CanTransmit` also requires the antenna to be enabled |
| `Antenna.PacketInterval`, `PacketSize`, `PacketResourceCost` | Set by RealAntennas from the data rate and power draw when a transmission starts |
| `Antenna.Power`, `Combinable`, `CombinableExponent`, `Comms.Power` | The stock range model, which RealAntennas does not use. To be checked in game: likely stale part config values |
| `Comms.CanCommunicate`, `SignalStrength`, `SignalDelay`, `ControlPath` | Computed by the RealAntennas network, read through the stock fields |
| `CommLink.SignalStrength`, `Type`, `Start`, `End` | Set by `RACommLink.Update` from the link budget |

## Decisions

* **Members on the existing classes**, as the RealFuels integration does: no new service. Each
  RealAntennas member carries "Requires RealAntennas." in its remarks and throws when the mod is
  absent. `SpaceCenter.RealAntennasAvailable` reports the mod, like `FARAvailable` and
  `RealFuelsAvailable`.
* **Bind through `KRPC.Utils.Accessor`** in `ExternalAPI/RealAntennas.cs`, with type names
  resolved at load. No compile-time reference.
* **Units as RealAntennas has them**: gain in dBi, transmit power in dBm, frequency in Hz, data
  rate in bits per second, beamwidth in degrees, power draw in watts.
* **Document the stock range members as not applicable** under RealAntennas, rather than
  recomputing them from the link budget.

## Phases

### 1. Compatibility and Tests

* Pin the mod in the `krpctools.game` registry: `RealAntennas` requires ClickThroughBlocker,
  KSPCommunityFixes and KSPBurst. The release archive has no `GameData/` root.
* In-game tests of the existing `Antenna`, `Comms` and `CommLink` members on a RealAntennas
  vessel on the launch pad, with a ground station link.
* Fix what does not hold, and note the stock range members in their remarks.

### 2. Antenna Link Budget

On `Parts.Antenna`, from `RAAntenna`:

| Member | Source |
| --- | --- |
| `Gain` | `Gain`, dBi |
| `TransmitPower` (get and set) | `ModuleRealAntenna.TxPower`, dBm, clamped to the part's `MaxTxPower` as the menu is. Editor only, as the menu is |
| `TechLevel` | `TechLevelInfo.Level`. Settable in the editor up to the part's maximum, as the menu is |
| `Band`, `Frequency` | `RFBand.name`, `RFBand.Frequency` |
| `DataRate` | `DataRate` |
| `Beamwidth` | `Beamwidth` |
| `ActivePowerDraw`, `IdlePowerDraw` | `PowerDrawLinear`, `IdlePowerDraw`, converted to watts |
| `Enabled` | `Condition == Enabled` in flight. Settable in the editor through the `_enabled` toggle, as the menu is. `DisablePermanently` calls the permanent shutdown event in flight |

### 3. Link Data Rates

On `CommLink`, from `RACommLink`: `ForwardDataRate` and `ReverseDataRate` (bits per second), and
the antenna at each end where it is a vessel part.

### 4. Targeting (Later)

Dish antennas point at a target: a vessel, a body's center, a latitude, longitude and altitude,
an azimuth and elevation, or orbit-relative. `AntennaTarget` is a `MonoBehaviour` with five
subclasses and its own config format. Reading the target is simple; setting it needs one method
per mode. Left until phases 1 to 3 are in use.

## As Built

* **Setters are editor only**, as the menu sets them. They go through `PartField`, so the
  module's `onFieldChanged` handlers recompute the link budget, mass and cost.
* **`MaxTechLevel`** is the smaller of the module's `maxTechLevel` (10 in sandbox) and the
  highest level the RealAntennas configs define (9 in the stock pack). RealAntennas clamps
  higher settings.
* **Targeting** reads and writes the mod's own `TARGET` node through `AntennaTarget.Save` and
  `LoadFromConfig`. Read back: `TargetMode` (None, Vessel, Body, Position, AzimuthElevation,
  OrbitRelative), `TargetVessel`, `TargetBody`, `TargetDirection`. A body's center is a
  position at the center, as the mod's window stores it. `TargetMode` reads it as `Body`
  within a tolerance relative to the radius: the altitude is saved as a float, which is off by
  up to 32 m for the RSS Sun.
* **Link antennas resolve to the exact module.** The mod supports several `ModuleRealAntenna`
  per part, so `Parts.Antennas` lists one entry per transmitter module and
  `CommLink.StartAntenna`/`EndAntenna` wrap the module carrying the link. `Part.Antenna` stays
  the first. No installed part has two, so this path has no game test.
* **An unloaded vessel's link antenna is `null`**, as for a ground station. The mod builds it
  from the module snapshot, with no part module behind it.
* **`CanTarget` is "is a dish"** (`Shape` is not `Omni`). The mod's own `CanTarget` also needs
  a target already set.
* **Phase 4 was done with the rest** rather than later.
* **`Comms`** gets no vessel-level data rate; scripts read the first link of `ControlPath`.
* **Dependencies:** RealAntennas needs ToolbarControl as well as ClickThroughBlocker, which
  fails to load without it.
* **Test craft must be saved with RealAntennas installed.** A craft without `ModuleRealAntenna`
  nodes launches with the module never configured: no default dish target, and link antennas
  with no part module. A quickload fixes it. This is how the mod behaves for any craft saved
  before it was installed.
