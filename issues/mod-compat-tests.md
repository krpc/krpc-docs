# In-game tests for Procedural Fairings

`Fairing` wraps the Procedural Fairings `ProceduralFairingDecoupler` module as well as the stock
`ModuleProceduralFairing`. `test_parts_fairing.py` covers only stock fairings.

* Register the mod in `krpctools.game` (`ksp/mods/__init__.py`), detected by one of its parts.
* Add a craft with a Procedural Fairings fairing, and a test class with `mods = ["ProceduralFairings"]`
  covering the fairing's state and jettison.

Every other mod integration in scope has in-game tests. The thrust reversers matched by animation
name are left untested on purpose.

Design: [mod-compat-test-coverage.md](https://github.com/krpc/krpc-docs/blob/main/design/services/mod-compat-test-coverage.md)
