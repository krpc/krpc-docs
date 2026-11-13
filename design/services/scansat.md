# SCANsat service

**Status:** in progress, phase 1. From the [mod integrations index](../../issues/mod-integrations-index.md).

## Context

SCANsat (22.1, assembly `SCANsat`, needs KSPTextureLoader) scans bodies from orbit. A scan
fills a 360 by 180 grid of one-degree cells per body, one bit per scan type. The maps and
readouts show terrain, biomes, anomalies and resources only where the matching bit is set.

| SCANsat member | Gives | Access |
| --- | --- | --- |
| `SCANUtil.isCovered`, `GetCoverage` | Coverage of a cell, and of a body in percent | Public API region |
| `SCANUtil.instantResourceScanEnabled` and three more | Resource settings | Public API region |
| `SCAN_Settings_Config.Instance` | Every setting, such as `BackgroundScanning`, `DaylightCheck` | Public |
| `SCANdata.Anomalies` | Anomaly names and positions, with `Known` and `Detail` from coverage | Public |
| `SCANUtil.getElevation`, `getBiomeName`, `ResourceOverlay` | The values the maps show | Internal |
| `SCANsat` part module, and `ModuleSCANresourceScanner` derived from it | Sensor type mask, FOV, altitudes, `startScan`/`stopScan` | Public |
| `SCANcontroller.getSensorStatus` | Per vessel and type: in range, best range, in darkness | Internal |
| `SCANmap` | The map renderer, GPU composite since 22.0 | Internal |

The `SCANcontroller` scenario runs in flight, the space center and the tracking station.

## Decisions

* **Service `ScanSat`**, in `service/ScanSat/`, no id. `SCANsat` would snake-case to
  `sca_nsat`; `ScanSat` gives `scan_sat`. `Available` works in every scene. Body procedures
  work in the three scenes of the scenario, the scanner class in flight.
* **`ScanType` is a flags enumeration** (on the flags enumerations branch): the nine scan
  types, `None`, and the unions `Altimetry`, `Visual`, `Anomalies`, `Resources` and `All`. A
  scanner's sensor mask is one value. `Coverage` of a combination is the mean of its types, and
  `IsCovered` is true when any of them covers the cell, as in SCANsat. Both reject `None`.
* **Coverage as a fraction**, `GetCoverage / 100`. SCANsat caps an incomplete body at 99.9%.
* **Readouts gated by coverage, nullable**, as the big map's mouse-over readout. Each returns
  null where its scan has not covered the cell:

  | Readout | Needs | Low resolution only |
  | --- | --- | --- |
  | `Elevation` | Either altimetry | Truncated to a multiple of 500 m |
  | `Slope` | Hi-res altimetry | - |
  | `Biome` | Biome | - |
  | `ResourceAbundance` | Either resource scan | Floored to a multiple of 0.05 |
* **Anomalies** are the known ones only. The name is null until the anomaly detail scan covers it.
* **`Scanner` wraps a part** with a `SCANsat` module, as DockingCamera's `Camera` does.
  `Scanning` sets through `startScan`/`stopScan`, the part's own events. A resource scanner
  starts through its `startResourceScanAction`, which does nothing while the stock survey fills
  the resource scans. Range and darkness come from the controller's sensor status, the value
  background scanning uses.
* **Map image from a map of our own.** `Map (body, type, width, projection, color, resource)`
  returns a PNG. The service builds an `SCANmap` with the RPM source, the source made for many
  independent maps, pumps `getPartialMap` once per frame and yields until `isMapComplete`. The
  build runs under SCANsat's per-frame budget, so the game stays responsive. The PNG is read
  back from `VisualRenderTexture`, as SCANsat's own export does. Each call builds and destroys
  its map. The RPM source has one texture claim, so destroying the map can release the
  `SCANSAT_BODY_TEXTURES` of an RPM screen showing the same body. That screen falls back to the
  scaled space textures until it next sets its body. Stock bodies have no such textures.
* **Binding by reflection** with `Accessor`. `Available` is false when a member is missing.
  `Accessor.Constructor` is added to core for `SCANmap`'s internal constructor.

## API

| Member | Kind |
| --- | --- |
| `Available` | Property |
| `Coverage (body, type)` | Procedure, fraction |
| `IsCovered (body, latitude, longitude, type)` | Procedure |
| `Elevation`, `Slope`, `Biome`, `ResourceAbundance (body, [resource,] latitude, longitude)` | Procedures, nullable |
| `Anomalies (body)` | List of `Anomaly`: `Name`, `Latitude`, `Longitude` |
| `Resources` | Names of the resources SCANsat maps |
| `BackgroundScanning`, `DaylightCheck`, `InstantResourceScan`, `StockResourceScan`, `BiomeLock`, `RequireNarrowBand` | Settings, read only |
| `Scanner (part)`, `Scanners (vessel)` | `Scanner`: `Part`, `ScanTypes`, `FieldOfView`, `MinAltitude`, `MaxAltitude`, `BestAltitude`, `RequiresLight`, `Scanning` (get, set), `InRange`, `InBestRange`, `InDarkness` |
| `Map (body, type, width, projection, color, resource)` | PNG; `MapType` Altimetry, Slope, Biome, Visual; `MapProjection` Rectangular, KavrayskiyVII, Polar |

## Phases

1. Everything above.
2. `SCANexperiment` science (analyze data), the vessels scanning in the background, Breaking
   Ground surface features (`SCANdata.ROCS`) and survey waypoints.
