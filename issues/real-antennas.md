# Support RealAntennas

RealAntennas replaces CommNet's range model with a link budget. It subclasses the stock antenna module and CommNet types, so `Antenna`, `Comms` and `CommLink` already return its objects. Its values (gain, transmit power, band, data rate) have no members, and the stock range members (`Antenna.Power`, `Comms.Power`) do not apply under it.

* Pin the mod for the in-game tests, and test the existing members under it.
* Add the link budget members to `Antenna`, and the data rates to `CommLink`.
* Antenna targeting comes later.

Design: [real-antennas.md](https://github.com/krpc/krpc-docs/blob/main/design/services/real-antennas.md)
