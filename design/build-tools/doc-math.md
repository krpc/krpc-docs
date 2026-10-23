# Math and units in service documentation

**Status:** done, merged as [PR #1169](https://github.com/krpc/krpc/pull/1169), for 0.8.

## Problem

`<math>` content in the service XML docs is raw LaTeX, and every target copies it through:

| Target | Today |
|---|---|
| rst (docgen) | `:math:`, so units come out in math italic |
| Python stubs | ``` ``m/s^2`` ```; `\frac` became a form feed in the docstring |
| C++ / C nano / Java | raw `\frac`, `\mbox` in Doxygen and Javadoc comments |
| C# stubs | XML copied verbatim; `<math>` is unknown to IntelliSense |
| Python runtime docstrings | raw LaTeX |

## Audit

### Existing `<math>` uses

All 70 are in `service/SpaceCenter/src/Services/`:

| Content | Count | Kind |
|---|---|---|
| `m/s^2`, `kg/m^3`, `rad/s^2`, `N.m`, `m^3`, `kg.m^2`, `m/s`, `kg/l`, `N`, `m^2`, `g`, `N(m/kg)^2`, `m^3s^{-2}` | 52 | units |
| `(x, y, z, w)`, `(0, 0, 0)`, `(0, 0, 0, 1)` | 15 | tuples |
| `Q` | 1 | symbol |
| `\frac{1}{2} . \mbox{air density} . \mbox{velocity}^2` | 1 | formula |

### Math removed earlier

From `git log -G '<math>'`:

| Commit | Removed | Action |
|---|---|---|
| "Replace LaTeX math in two SpaceCenter doc comments with plain text" | `2\pi` in `CelestialBody.RotationAngle`/`InitialRotation`, the dynamic pressure formula | re-add `2\pi`; "Rewrite the XML documentation comments" already restored the formula |
| "Remove incomplete functionality" | `N.m` on deleted RPCs | none |

### Candidates in the current docs

These are exported docs only, from the generated service definitions.

| Pattern | Count | Becomes |
|---|---|---|
| plain symbols: `in kg`, `in m/s`, `in rad/s` | 23 | `<unit>` |
| worded compound units: meters per second, newton meters, radians per second, degrees per second, joules per kilogram, ... | about 75 | `<unit>` |
| single named units: "in meters", "in degrees", "in newtons", "in seconds" | about 330 | unchanged |
| "between 0 and pi" (`StdLib`), "2 pi" (`CelestialBody`) | 5 | `<math>` |
| `Orbit.SpecificEnergy`, `CelestialBody.GravitationalParameter` | 2 | add a formula |
| tuples: `(pitch, yaw, roll)`, `(x, y)` | 3 | `<c>` |
| relations written with `<see cref>` ("`Thrust` divided by `Mass`") | many | unchanged; `<math>` cannot hold a cref |

## Design

| Tag | For | rst | Clients |
|---|---|---|---|
| `<unit>m/s^2</unit>` | compound units and unit symbols | ``:math:`\mathrm{m/s^{2}}` `` | `m/s²` |
| `<math>\frac{1}{2} \rho v^2</math>` | formulas and symbols | ``:math:`\frac{1}{2} \rho v^{2}` `` | `½ ρ v²` |
| `<c>(x, y, z, w)</c>` | tuples, component orders, literals | ``` ``(x, y, z, w)`` ``` | as now |

 * A `.` in a unit joins factors: `N.m` gives `N \cdot m` and `N·m`.
 * Clients get Unicode text, the same in every language and in the Python runtime docstrings.
 * One parser, `client/python/krpc/docmath.py`, serves docgen, clientgen and the Python client.

### Subset

| Syntax | Unicode |
|---|---|
| letters, digits, `+ - = ( ) , / . < >` | as is |
| `^x`, `^{...}`, `_x`, `_{...}` | super/subscript characters |
| `\frac{a}{b}` | a vulgar fraction such as `½`, else `a/b` |
| `\sqrt{x}`, `\text{...}` | `√x`, the text |
| `\cdot \times \pm \le \ge \approx \infty \degree` | `· × ± ≤ ≥ ≈ ∞ °` |
| Greek letters | `α` ... `ω` |

Extending the subset is one entry per renderer, plus a test.

### Invalid markup

Invalid markup is a command outside the subset, a script character with no Unicode form (`^q`),
unbalanced braces, or an unknown XML tag.

 * **docgen** raises, naming the problem and the documentation text, so the doc build fails. Every
   kRPC service goes through docgen in the build.
 * **clientgen** prints a warning on stderr, and still writes the stubs. Invalid math falls back to
   its source with the backslashes dropped, and an unknown tag renders as its content. C# copies
   unknown tags through, as it cannot tell them from standard C# tags.
 * **The Python client** uses the same fallback without a warning. Its users cannot fix a
   service's docs, and a third-party service with bad markup still gets docstrings.

## Phases

1. Parser, docgen, clientgen and Python client support, with tests and goldens.
2. Rewrite the existing `<math>` uses.
3. Convert the worded and plain-symbol units, and add the formulas.
4. Document the tags in `doc/src/extending.rst` and the writing guide.
