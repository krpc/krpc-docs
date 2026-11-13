# RealAntennas support

**Status:** proposal (2026-11-10). Issue: [issues/real-antennas.md](../../issues/real-antennas.md).

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

## Open Questions

* Whether `TransmitPower` and `TechLevel` should also be settable in flight. The menu allows
  the editor only, and RealAntennas recomputes mass and cost from them there.
* Whether `Comms` gets a vessel-level best data rate, or scripts take it from the first link of
  `ControlPath`.
