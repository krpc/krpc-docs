# Service definition ordering

**Status:** proposal (2026-08-09), no issue filed yet. Prerequisite for
[struct-types.md](struct-types.md), which cannot be implemented cleanly until this
lands.

## Context

Everything that reads a service definition builds its type objects in whatever order
the definitions happen to arrive. That is fine while a consumer only needs a type's
*name*, which is all a class reference or a return type annotation requires. It stops
being fine the moment a consumer needs a type's *contents*.

Exactly one kind of type has contents a consumer needs today, and it needs them in
exactly one place: an enumeration, when decoding a parameter's default value. So the
whole problem is currently visible only through a cross-service enum default, which
nothing in kRPC happens to use.

| Consumer | Reads | Order of construction | Order-safe? |
| --- | --- | --- | --- |
| Python dynamic client | `KRPC.GetServices` reply | one service at a time; within a service, classes, enums, exceptions, then procedures | **no** |
| Lua dynamic client | same | same | **no** |
| clientgen `generator.py` | one service's JSON | classes, enums, exceptions, then procedures | only by accident, see below |
| docgen `nodes.py` | merged JSON of every service | **procedures first**, then classes, enums, exceptions | only by accident, see below |
| C#, C++, Java, cnano | nothing at runtime | n/a | yes |

### The dynamic clients genuinely break

Reproduced against `client/python` with a hand-built two-service `Services` message
where `ServiceA.Frob(mode = ServiceB.Mode.Fast)`, created in each order:

```
ServiceB then ServiceA:  OK
ServiceA then ServiceB:  TypeError: 'NoneType' object is not callable
```

`Decoder.decode` handles an `EnumerationType` as `typ.python_type(value)`, and
`python_type` stays `None` until `set_values` runs from `_add_service_enumeration`.
Procedure defaults are decoded eagerly while the service is built, so a service created
before the one defining the enum decodes against an unpopulated type. `client.lua` and
`decoder.lua` fail identically at `typ.lua_type(...)`.

Python already recognizes this hazard in one narrow case: `client.py` registers the
class and enum types of pre-generated stubs in a first pass over every service, with a
comment saying it does so "so that class/enum types are loaded if a dynamic service
needs them". That is the right shape, applied to only one source of definitions.

### The tools dodge it rather than handle it

`krpctools/utils.py decode_default_value` skips the type system for enums altogether,
decoding the value as a plain sint32, with a comment that this is a workaround because
`set_values` has not been called. Order stops mattering because the definition is never
consulted. The cost is paid in the output, which names a raw integer where it should
name a member:

```
.. staticmethod:: enum_default_arg([x = TestEnum(2)])
```

and in the generated Python client, `def enum_default_arg(self, x: TestEnum = TestEnum(2))`.

Two consequences. First, this is a visible defect in generated clients and published
documentation for every enum-valued default. Second, an ordering test written against
krpctools today would pass without exercising anything, so the workaround has to go for
enums to be a meaningful test vehicle.

Removing it exposes a same-service ordering bug too, with no cross-service definition
needed: `docgen/nodes.py Service.__init__` builds its procedures, and therefore its
`Parameter` objects and their decoded defaults, before it builds `self.enumerations`.
`TestService.EnumDefaultArg` alone is enough to fail it.

### Two smaller hazards found while tracing this

- **clientgen is handed one service.** `clientgen/__init__.py` loads the definitions of
  every service, then constructs the generator with `defs[args.service]`. A definition
  belonging to any other service is not merely late, it is absent.
- **The type registries are class attributes.** `Generator.types` and
  `nodes.Appendable.types` are both a single `Types()` shared by every instance in the
  process, and `EnumerationType.set_values` asserts `self._python_type is None`.
  Registering the same enumeration twice therefore raises `AssertionError` rather than
  being a no-op, which the krpctools test suite would hit as soon as registration is
  real, since it generates several definition sets in one process.

## Decisions

- **Two phases in every consumer.** Phase one walks every service and registers every
  definition it declares. Phase two builds procedures, parameters and default values.
  No consumer may depend on the order services arrive in, nor on the order of sections
  within a service.
- **Remove the enum sint32 workaround** in `decode_default_value`, and decode an enum
  default through its registered type like any other value. This is what makes the
  ordering machinery real rather than decorative, and it corrects the generated output:
  defaults render as named members. Each language's `parse_default_value` gains the
  rendering (`TestEnum.value_c` in Python, `TestEnum::kValueC` in C++, and so on),
  replacing the integer cast.
- **Pass clientgen the complete definitions.** `clientgen/__init__.py` hands the
  generator every service's definitions; the generated *output* still covers one
  service. Phase one then has everything it needs regardless of which service is being
  generated.
- **Registration is per run, not per process.** `Generator.types` and
  `Appendable.types` become instance state owned by a single generation run. This keeps
  a run's registrations isolated and sidesteps the `set_values` assertion instead of
  weakening it. Within a docgen run every service still shares one registry, which is
  what cross-service references need.
- **A missing definition is a named error.** If a type is referenced and no service in
  the input defines it, fail with a message naming the service and type. The present
  failure mode is a `NoneType` error from inside a decoder, several frames from the
  cause.
- **Defaults stay eagerly decoded.** Deferring the decode to first use would also fix
  the ordering, by making it impossible to decode too early, but it moves work into
  every call and hides definition errors until a user trips over them. A complete phase
  one makes eager decoding correct.
- **Scope.** The server is unchanged: it already emits complete definitions and does not
  consume them. The static clients are unchanged: everything is resolved when their
  stubs are generated.

## Phases

1. **Python dynamic client.** Register the class and enum types of every service before
   creating any service, extending the pre-generated-stub pass in `client.py` to cover
   dynamic services too.
2. **Lua dynamic client.** The same change to `client.lua`.
3. **krpctools registration.** Phase one in `clientgen/generator.py` and
   `docgen/nodes.py`, the full definitions through `clientgen/__init__.py`, and the
   registries moved off the class. Ordering fixtures. No output change yet, so the
   golden files are untouched and the diff stays about the mechanism.
4. **Retire the enum workaround.** Drop the sint32 special case, render enum defaults as
   named members in each `lang/*.py` and in the `docgen/csharp.py` and `docgen/cpp.py`
   overrides, and reorder `docgen/nodes.py` so definitions precede procedures.
   Regenerate every golden fixture.
5. **Changelogs**, as a single commit before the branch is pushed.

Phases 3 and 4 are separable and worth separating: phase 3 is pure mechanism with no
output change, phase 4 is entirely output change. Reviewing them together would mean
reading a large fixture diff and a structural change at once.

## Tests

- **Dynamic clients**: build a two-service definition where one service's procedure
  defaults to the other's enum member, and construct the services in both orders. Both
  must yield a usable service whose default is the right enum member. A list-of-enums
  default covers the recursive case, where the enum sits inside a collection type.
- **krpctools**: a hand-written multi-service ordering fixture beside `Empty.json`,
  generating the dependent service, for both clientgen and docgen. The hostile order
  must produce output identical to the friendly order.
- **Regression on the existing fixtures**: after phase 4, `TestService`'s
  `EnumDefaultArg` renders a named member in all five clientgen languages and all six
  docgen languages. This also pins the `docgen/nodes.py` reordering, since it fails
  without it.
- **Repeated registration**: generating two definition sets in one process must not
  raise, covering the `set_values` assertion.

## Effect on structs

[struct-types.md](struct-types.md) records this as its gotcha 4, because a struct's
field list is contents a consumer needs, exactly like an enumeration's values, and it is
needed far more often than only for defaults: it is the decoder. Once this lands, struct
definitions register in phase one along with classes and enumerations, struct-typed
default values need no special rule, and that gotcha and the ordering work listed under
its *Default values* section can be deleted rather than implemented.

The reverse dependency does not hold. Nothing here needs structs, and everything here is
testable with enumerations alone.

## Open questions

1. **Naming of the registration entry point.** The dynamic clients, clientgen and docgen
   each have their own definition-walking code; whether phase one is genuinely shared
   code or the same shape written three times is worth deciding when the Python and Lua
   changes are written.
2. **Enum member rendering for values with no name.** An enum default whose integer does
   not correspond to a declared value cannot render as a member. The scanner should not
   be able to produce one, but the tools should decide between failing and falling back
   to the cast rather than doing so by accident.
