# Buoyancy and hydrodynamics

**Status:** in progress. All four phases are implemented and tested; no issue or PR filed yet.

kRPC exposes the aerodynamic half of KSP's flight model in full: `Part.Lift`, `Part.Drag`,
`Flight.AerodynamicForce`, `Flight.DynamicPressure`, `Flight.AtmosphereDensity`. The water half is
absent. A script can fly a rocket or a plane, and has nothing to work with for a boat or a
submarine.

A user asked for three things: part and vessel displacement, part and vessel center of buoyancy,
and part and vessel buoyant force. Trim tanks are adjusted so the center of buoyancy lines up with
the center of mass, otherwise the hull rotates. The buoyant force cannot be computed by hand
because KSP applies its own scalar. The user also asked for the force at a chosen density and
gravity.

## The game model

Established by disassembling `Assembly-CSharp.dll` from the 1.12.5 install. `PartBuoyancy` is a
`MonoBehaviour` on every part, reachable as the public field `part.partBuoyancy`. It carries public
fields and no properties, and it exists in the flight scene only. Its `FixedUpdate` returns early
when `!body.ocean`, when `vessel.terrainAltitude >= 20`, or when
`depth <= -PhysicsGlobals.BuoyancyRange`.

### Fields and their coordinate spaces

| Field | Space | Meaning |
| --- | --- | --- |
| `displacement` | scalar, m^3 | Volume displaced when fully submerged |
| `centerOfBuoyancy` | world | `transform.position + rotation * part.CenterOfBuoyancy`, then refined by the submersion geometry |
| `centerOfDisplacement` | world | `transform.position + rotation * part.CenterOfDisplacement`; the point `depth` is sampled at |
| `lastForcePosition` | world | The point the force is applied at |
| `depth`, `minDepth`, `maxDepth` | scalar, m | Positive below the waterline; min and max are over the 8 bounding box corners |
| `submergedPortion` | scalar, 0 to 1 | Fraction below the waterline |
| `buoyantGeeForce` | scalar, tonnes | Displaced mass after every multiplier |
| `effectiveForce`, `lastBuoyantForce` | world, kN | Buoyancy plus water drag and lift |
| `dragScalar`, `liftScalar` | scalar | Water drag and lift multipliers |

`part.CenterOfBuoyancy` and `part.CenterOfDisplacement` are **part-local** config offsets, both
defaulting to zero. The `PartBuoyancy` fields of the same name are the world space points built
from them. `Part` mirrors `submergedPortion`, `depth`, `minDepth`, `maxDepth`,
`submergedDragScalar`, `submergedLiftScalar`, `WaterContact`, `submergedDynamicPressurekPa` and
`waterAngularDragMultiplier` every `FixedUpdate`, so those are the cheap read path.

### Displaced volume

From `UpdateDisplacement`:

```
displacement = PhysicsGlobals.BuoyancyDefaultVolume
if (!part.DragCubes.None):
    size = overrideCube?.Size ?? part.DragCubes.WeightedSize      // part local
    area = overrideCube?.Area ?? part.DragCubes.WeightedArea
    displacement = size.x*size.y*size.z
    xPortion = area[0]/(size.y*size.z)
    yPortion = area[2]/(size.x*size.z)
    zPortion = area[4]/(size.x*size.y)
    if (xPortion+yPortion+zPortion is finite and > 0):
        xzPortion = (Min(xPortion,zPortion) + 2*xPortion*zPortion)/3
        displacement *= xzPortion * yPortion
else if (part.collider != null):
    displacement = product of part.collider.bounds.size * 0.75
```

`overrideCube` is the `DragCube` named by `part.buoyancyUseCubeNamed`.

### Buoyant force

From `FixedUpdate`:

```
buoyantGeeForce = displacement * submergedPortion * body.oceanDensity
                * (maxDepth >= PhysicsGlobals.BuoyancyScaleAboveDepth
                     ? 1 : maxDepth / PhysicsGlobals.BuoyancyScaleAboveDepth)
                * PhysicsGlobals.BuoyancyScalar
                * part.buoyancy

effectiveForce = -FlightGlobals.getGeeForceAtPosition(applyPoint) * buoyantGeeForce
               * vessel.gravityMultiplier * PhysicsGlobals.GraviticForceMultiplier
```

`applyPoint` starts as `centerOfBuoyancy` and, when `PhysicsGlobals.BuoyancyUseCoBOffset` is set,
is lerped toward the submerged centroid by `(1 - submergedPortion)`. `buoyantGeeForce` is a
displaced mass in tonnes, given `oceanDensity` in tonnes per cubic meter. `effectiveForce` is in
kilonewtons, in the scene's world space.

### Three facts that drive the design

 * **`effectiveForce` is not the buoyant force.** The water drag and lift branches later in
   `FixedUpdate` write over it three more times, and `lastBuoyantForce` is copied from it after
   that. The pure buoyant force is rebuilt from `buoyantGeeForce`, which is written once.
 * **Water drag and lift have no force vector.** KSP keeps `dragScalar`, `liftScalar` and a
   magnitude, never a separate vector, so the multipliers are what can be exposed.
 * **KSP has no vessel-level buoyancy.** `Vessel` carries `Splashed`, `waterOffset` and
   `gravityMultiplier` and nothing else. Every vessel figure is summed over parts.

### Static pressure

`FlightIntegrator` sets each part's static pressure every frame:

```
alt = FlightGlobals.getAltitudeAtPos(part.partTransform.position, body)
part.staticPressureAtm = body.GetPressure(alt)                          // kPa
if (body.ocean && alt < 0)
    part.staticPressureAtm += vessel.gravityTrue.magnitude * -alt * body.oceanDensity
part.staticPressureAtm *= 0.0098692                                     // to atm
```

`body.GetPressure` extrapolates the atmosphere curve below sea level. `vessel.staticPressurekPa`
is `body.GetPressure(altitude)` with no water term, so it reads about 111 kPa at 700 m depth.

`Part._CheckPartPressure` destroys a part when `staticPressureAtm * 101.325 + dynamicPressurekPa`
exceeds `maxPressure`, in kPa. The check is skipped for a part that is `ShieldedFromAirstream`, and
applies only with `AdvancedParams.PressurePartLimits` on. It is also skipped under
`CheatOptions.NoCrashDamage`, and it rolls against `presExplodeChance`.

### Ocean and physics settings

Ocean density is `CelestialBody.oceanDensity`, in tonnes per cubic meter, defaulting to 1. There is
no `waterDensity` and no `PhysicsGlobals.BuoyancyDensityOcean`. Stock
`PhysicsGlobals.BuoyancyScalar` is 1.2 and `BuoyancyScaleAboveDepth` is 0.2, both set in
`Physics.cfg`.

## API

Vessel-level values go on `Flight`, in that object's reference frame, next to `AerodynamicForce`
and `CenterOfMass`. The geometric values also work in the editor, so trim can be checked before
launch. Units follow the existing boundary conventions: tonnes to kilograms, kilonewtons to
newtons, kilopascals to pascals.

### `Part`

Geometric, `GameScene.Flight | GameScene.Editor`:

| Member | Type | Meaning |
| --- | --- | --- |
| `Displacement` | `double` | Volume displaced when fully submerged, m^3 |
| `BuoyancyMultiplier` | `float` | The multiplier applied to the part's buoyant force |
| `WaterAngularDragMultiplier` | `float` | The multiplier applied to the part's angular drag in water |
| `CenterOfBuoyancy (rf)` | `Tuple3` | The point the buoyant force acts at |
| `CenterOfDisplacement (rf)` | `Tuple3` | The point the depth of the part is measured at |
| `BuoyantForceAt (density, gravity)` | `double` | Buoyant force on the fully submerged part, N |

Live, `GameScene.Flight`:

| Member | Type | Meaning |
| --- | --- | --- |
| `Splashed` | `bool` | Whether the part is in contact with water |
| `SubmergedPortion` | `double` | Fraction below the waterline, 0 to 1 |
| `DisplacedVolume` | `double` | Volume being displaced now, m^3 |
| `Depth` | `double` | Depth of the center of displacement below the waterline, m |
| `MinDepth`, `MaxDepth` | `double` | Depth of the shallowest and deepest corners, m |
| `BuoyantForce (rf)` | `Tuple3` | The buoyant force on the part, N |
| `SubmergedDynamicPressure` | `float` | Dynamic pressure of the water on the part, Pa |
| `SubmergedDragMultiplier` | `double` | Drag multiplier applied to the submerged part |
| `SubmergedLiftMultiplier` | `double` | Lift multiplier applied to the submerged part |

`Depth` is positive below the waterline. `CenterOfBuoyancy` in the editor, and in flight for a part
clear of the water, is the configured point. In flight for a submerged part it is the application
point KSP uses.

### `Flight`

| Member | Type | Meaning |
| --- | --- | --- |
| `Displacement` | `double` | Volume displaced when fully submerged, m^3 |
| `DisplacedVolume` | `double` | Volume being displaced now, m^3 |
| `SubmergedPortion` | `double` | Displaced volume over displacement, 0 to 1 |
| `CenterOfBuoyancy` | `Tuple3` | The point the total buoyant force acts through; `null` when clear of the water |
| `BuoyantForce` | `Tuple3` | The total buoyant force on the vessel, N |
| `BuoyantAcceleration` | `Tuple3` | `BuoyantForce` over the vessel's mass, m/s^2 |
| `BuoyantTorque` | `Tuple3` | The torque of the buoyant forces about the center of mass, N m |
| `FullySubmergedCenterOfBuoyancy` | `Tuple3` | The point the buoyant force acts through, fully submerged; `null` when the vessel displaces nothing |
| `BuoyantForceAt (density, gravity)` | `double` | Buoyant force on the fully submerged vessel, N |
| `BuoyantTorqueAt (density, gravity)` | `Tuple3` | Torque about the center of mass, fully submerged, with gravity towards the body center, N m |
| `Depth` | `double` | Depth of the center of mass below the waterline, m |
| `SubmergedDynamicPressure` | `float` | Dynamic pressure of the water on the vessel, Pa |

`Flight.CenterOfBuoyancy` is `[KRPCProperty (Nullable = true)]`, and
`EditorVessel.CenterOfBuoyancy` is `[KRPCMethod (Nullable = true)]`.

### `EditorVessel`

| Member | Type | Meaning |
| --- | --- | --- |
| `Displacement` | `double` | Volume displaced when fully submerged, m^3 |
| `CenterOfBuoyancy (rf)` | `Tuple3` | The point the buoyant force acts through, fully submerged; `null` when the vessel displaces nothing |
| `BuoyantForceAt (density, gravity)` | `double` | Buoyant force on the fully submerged vessel, N |
| `BuoyantTorqueAt (density, gravity, rf)` | `Tuple3` | Torque about the center of mass, fully submerged, with gravity down the editor, N m |

These answer the trim question in the editor: compare `CenterOfBuoyancy` with the existing
`CenterOfMass` in the same reference frame, and compare `BuoyantForceAt` with the weight.
`BuoyantTorqueAt` is zero for a hull trimmed level.

The "At" members give fully submerged figures, which stay fixed while a hull rides the surface.
`BuoyantAcceleration` stays on `Flight` alone, next to `AerodynamicAcceleration`.

### Pressure

| Member | Type | Meaning |
| --- | --- | --- |
| `Part.StaticPressure` | `float` | Static pressure on the part, water included, Pa; flight only |
| `Part.MaxPressure` | `double` | The pressure the part survives, Pa |
| `Flight.StaticPressure` | `float` | Now includes the water above the center of mass |
| `CelestialBody.PressureAt (altitude)` | `double` | Now includes the water below sea level on an ocean body |

The two fixes add the water term the game adds per part. `PressureAt` takes gravity at the radius
of the altitude.

### `CelestialBody` and `SpaceCenter`

| Member | Type | Meaning |
| --- | --- | --- |
| `CelestialBody.HasOcean` | `bool` | Whether the body has an ocean |
| `CelestialBody.OceanDensity` | `double` | Density of the body's ocean, kg/m^3 |
| `SpaceCenter.BuoyancyScalar` | `double` | The multiplier the game applies to every buoyant force |

`BuoyancyScalar` goes next to `G`. It is what explains a force that is not textbook Archimedes.

## Aggregation

The total buoyant force acts through the force-magnitude-weighted mean of the per-part application
points:

```
CoB = sum(|F_i| * p_i) / sum(|F_i|)
```

This is the only point about which the buoyant forces exert no net torque. A hull at rest carries it
on the same vertical line as its center of mass, and the horizontal offset between the two is the
trim. Stability is set by the metacenter, which a surface hull carries above its center of mass
while its center of buoyancy sits below.

A displacement-weighted mean is wrong whenever parts sit at different depths. The shallow-water ramp
and the submerged portion both scale `F_i`, and neither scales `displacement_i`.

`Flight.CenterOfBuoyancy` returns `null` when `sum(|F_i|)` is zero, which covers every case where
the vessel is clear of the water. `EditorVessel.CenterOfBuoyancy` weights by
`displacement_i * buoyancy_i`, the fully submerged limit, and returns `null` on the same rule. No
stock part config sets `buoyancy = 0`, so a modded part is what reaches it.

The pure buoyant force is rebuilt rather than read from `lastBuoyantForce`:

```
F_world_kN = -getGeeForceAtPosition(applyPoint) * buoyantGeeForce
             * vessel.gravityMultiplier * PhysicsGlobals.GraviticForceMultiplier
```

`PartBuoyancy` does not exist outside flight, so `UpdateDisplacement` is reimplemented from
`part.DragCubes`. One implementation serves both scenes, so flight and editor cannot drift apart.

## Phases

| Phase | Contents |
| --- | --- |
| 1 | The readout helper `StockBuoyancy.cs`, `CelestialBody.HasOcean`, `CelestialBody.OceanDensity`, `SpaceCenter.BuoyancyScalar` |
| 2 | The `Part` members, which answer all three asks at the part level |
| 3 | The `Flight` and `EditorVessel` members |
| 4 | A boat and submarine section in the docs, with a trim-check example under `doc/src/scripts/` |

All four phases have landed. The in-game tests run against `Buoyancy.craft`, a vertical stack built
by hand that topples and floats on its side, and against `PartsParachute.craft` for the editor and
flight figures agreeing.

## Resolved questions

 * **Drag cubes in the editor.** The weighted cube is empty there, so the editor needs
   `DragCubeList.SetDragWeights` to build it. `ForceUpdate`, which is all `UpdateDisplacement` calls,
   only marks it stale; in flight the integrator builds it every frame. `StockBuoyancy.Displacement`
   calls both, and falls back to the collider bounds when the weighted size is still zero. The
   rebuild is gated to the editor scene, so a read in flight leaves the cube the integrator is
   flying the part on alone.
 * **Per-part iteration cost.** The `Flight` members walk `InternalVessel.Parts` and call
   `StockBuoyancy` directly, as the aerodynamic members in the same class do. A service object per
   part per call would resolve each one through `FlightGlobals.FindPartByID`, which scans every
   loaded vessel and every part. `SubmergedPortion` and `CenterOfBuoyancy` each take one pass, so a
   displaced volume and a center of buoyancy are computed once per part.
 * **`oceanDensity` units.** Tonnes per cubic meter, confirmed in game: `OceanDensity` reads 1000
   for Kerbin.
 * **The `terrainAltitude >= 20` cutoff.** `PartBuoyancy.FixedUpdate` takes its dry path there
   rather than returning, so `submergedPortion` and `splashed` are still zeroed. No note is needed.

## Divergences from the design

 * **Parachutes.** `PartBuoyancy.Start` writes `buoyancyUseCubeNamed = "PACKED"` onto a parachute
   that names no cube, and only runs in flight. `StockBuoyancy.OverrideCube` applies the same
   default itself, otherwise the editor and flight figures differ for every chute.
 * **`Flight.SubmergedDynamicPressure`.** Gated on a part being below the waterline. The water
   density is a constant, so an ungated figure reads high for a vessel flying over an ocean.
 * **The live water multipliers.** `Part.SubmergedDragMultiplier` and `SubmergedLiftMultiplier`
   read zero at a body with no ocean. `PartBuoyancy.Start` seeds `submergedDragScalar` with
   `BuoyancyWaterDragScalar` and `FixedUpdate` returns before touching it, so the raw field holds
   4.5 on the Mun.
 * **`Part.WaterAngularDragMultiplier`** is a part config value, not a live buoyancy field, so it is
   read unguarded and in the editor as well as in flight.

