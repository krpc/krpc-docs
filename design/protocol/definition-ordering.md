# Service definition ordering

**Status:** proposal (2026-08-09), no issue filed yet. Prerequisite for
[struct-types.md](struct-types.md), which cannot be implemented cleanly until this
lands.

## Context

Everything that reads a service definition builds its type objects in whatever order
the definitions happen to arrive. That is fine while a consumer only needs a type's
*name*, which is all a class reference or a return type annotation requires. It stops
being fine the moment a consumer needs a type's *contents*, and the failures come in
two shapes: a definition registered too late, and one never registered at all.

Exactly one kind of type has contents a consumer needs today, and it needs them in
exactly one place: an enumeration, when decoding a parameter's default value.

| Consumer | Reads | Order of construction | Safe? |
| --- | --- | --- | --- |
| Python dynamic client | `KRPC.GetServices` reply | one service at a time; within a service, classes, enums, exceptions, then procedures | **no**, across services |
| Lua dynamic client | same | same | **no**, across services |
| clientgen `generator.py` | one service's JSON | classes, enums, exceptions, then procedures | **no**, for an enum nested in a default |
| docgen `nodes.py` | merged JSON of every service | **procedures first**, then classes, enums, exceptions | **no**, for an enum nested in a default |
| C#, C++, Java, cnano libraries | nothing at runtime | n/a | yes |

The static clients are safe only in the sense that the generated library resolves
nothing at runtime. clientgen, which produces them, is a consumer like any other and is
**not** safe: see below, where it turns out to fail without any cross-service definition
at all.

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

### The tools dodge it rather than handle it, and only halfway

`krpctools/utils.py decode_default_value` skips the type system for enums altogether,
decoding the value as a plain sint32, with a comment that this is a workaround because
`set_values` has not been called. Order stops mattering because the definition is never
consulted. The cost is paid in the output, which names a raw integer where it should
name a member. In the shipped Python client:

```python
def message(self, content: str, duration: float = 1.0,
            position: MessagePosition = MessagePosition(1), ...)
```

and the same in the published documentation, for every enum-valued default.

The workaround also guards only the **top level** of the default's type:

```python
if not isinstance(typ, EnumerationType):
    return Decoder.decode(None, value, typ)
return Decoder.decode(None, value, Types().sint32_type)
```

A default whose type merely *contains* an enumeration, such as `IList<SomeEnum>`,
`Tuple<int,SomeEnum>` or `IDictionary<string,SomeEnum>`, takes the first branch and
decodes through the registry, where the enumeration is unpopulated. Confirmed against
`client/python`: decoding a list-of-enums default with an unregistered enumeration gives
`TypeError: 'NoneType' object is not callable`, the same failure as the dynamic clients.
This one needs no cross-service definition and no unlucky ordering; it fails within a
single service, always. It is latent purely because no service declares such a default
today. `UI.Message`'s `MessagePosition` parameter is a top-level enum, so it lands on
the workaround.

Three consequences. It is a visible defect in generated clients and published
documentation for every enum-valued default. It is a latent hard failure the first time
anyone writes a default over a collection of enumerations. And an ordering test written
against krpctools today would pass without exercising anything, so the workaround has to
go for enumerations to be a meaningful test vehicle.

Removing it exposes an ordering bug that likewise needs no cross-service definition:
`docgen/nodes.py Service.__init__` builds its procedures, and therefore its `Parameter`
objects and their decoded defaults, before it builds `self.enumerations`.
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

### There is already a topological sort in the tree

`clientgen/cnano.py build_collection_types` is a hand-rolled one, written for exactly
this reason. C requires a struct to be declared before it is used, so a
`krpc_list_tuple_int32_int32_t` cannot be emitted before the `krpc_tuple_int32_int32_t`
it contains. The function recurses into a type's element types, then appends the type
itself, deduping as it goes: a post-order depth-first traversal, which is a topological
sort:

```python
def build_collection_types(typ):
    if isinstance(typ, TupleType):
        for value_type in typ.value_types:
            build_collection_types(value_type)
    ...
    typ = self.parse_collection_type(typ)
    if typ not in context["collection_types"]:
        context["collection_types"].append(typ)
```

It is correct, it is confined to one backend, and it has no cycle detection, which is
safe only because collection types nest structurally and cannot refer back to
themselves. A struct can, so the same traversal over struct fields would recurse until
the stack runs out.

### What the dependency graph actually looks like

Worth being precise, because it decides how much machinery is justified.

| Definition | Depends on |
| --- | --- |
| `Enumeration` | nothing; `name`, values, docs |
| `Class` | nothing; `name` and docs only, its members are procedures |
| `Exception` | nothing; `name` and docs only |
| `Struct` (future) | every named type its fields mention, including other structs |
| Procedure | the types in its signature, and the *contents* of any type in a default |

So the named-definition graph has **no edges at all today**: every consumer's real
requirement is the two-layer one, all definitions before any procedure. The graph only
becomes interesting when structs arrive, and that is also when cycles become possible
and when a missing cycle check stops being harmless.

That does not argue against building the general thing now. It argues for building it
where a two-layer answer and a topologically sorted answer are the same answer, so the
sort can be introduced, tested and trusted before anything depends on it being subtle.

## Decisions

- **One shared analysis pass in krpctools, not two phases per consumer.** A new module
  takes the definitions of every service, resolves and orders them, and hands back a
  structure a consumer can walk front to back without thinking about ordering at all.
  clientgen and docgen consume that instead of each growing their own phase one. Details
  below.
- **Ordering is a topological sort with cycle detection.** Not a hardcoded
  definitions-then-procedures rule, even though that is all today's graph needs. The
  sort makes the guarantee explicit and testable, generalizes to struct fields without
  revisiting every consumer, and turns a cyclic definition into a named error instead of
  a stack overflow.
- **Remove the enum sint32 workaround** in `decode_default_value`, and decode an enum
  default through its registered type like any other value. This is what makes the
  ordering machinery real rather than decorative, and it corrects the generated output:
  defaults render as named members. Each language's `parse_default_value` gains the
  rendering (`TestEnum.value_c` in Python, `TestEnum::kValueC` in C++, and so on),
  replacing the integer cast.
- **Pass clientgen whatever the input contains.** `clientgen/__init__.py` hands the
  generator every service in the loaded definitions rather than `defs[args.service]`;
  the generated *output* still covers one service. Note this changes little in the real
  pipeline, where the ServiceDefinitions tool emits exactly one service per file, and is
  mostly about not discarding what a hand-written or future multi-service file provides.
  Where a referenced service is genuinely absent, that is reported as a missing input,
  not worked around.
- **Registration is per run, not per process.** `Generator.types` and
  `Appendable.types` stop being class attributes; the `Types` registry becomes state the
  shared analysis owns for one run. This keeps a run's registrations isolated and
  sidesteps the `set_values` assertion instead of weakening it. Within a docgen run
  every service still shares one registry, which is what cross-service references need.
- **The dynamic clients do not share this code.** `krpc` is what someone installs to
  write scripts against a running game; krpctools is what a client author installs to
  generate stubs and documentation. A player must never have to install client-author
  tooling in order to talk to the game, so `krpc` depends on nothing but `protobuf`,
  and the boundary is a product decision rather than a packaging accident. The
  packaging reflects it: the two are separate distributions, aimed at different
  audiences, under different licenses, LGPL for the client library and GPL for the
  tools. Nothing in `client/python` may import from krpctools.

  Two lesser reasons point the same way. The dynamic clients consume a protobuf
  `Services` message rather than the definitions JSON, and Lua shares no Python at all.
  Each therefore keeps its own registration pass, a short loop over every service
  before any is built.

  The reverse move stays available and stays subject to the same rule: a piece of this
  may go into `krpc/types.py`, which krpctools already depends on, **only if the client
  itself needs it**, never merely to give krpctools something to share. The struct
  ordering may qualify one day, since the dynamic client has to register struct fields
  in dependency order too. Sharing for its own sake would not.
- **A missing definition is a named error.** If a type is referenced and no service in
  the input defines it, fail with a message naming the service and type. The present
  failure mode is a `NoneType` error from inside a decoder, several frames from the
  cause.
- **An enum default that names no declared value is an error too**, on the same footing
  as a type that cannot be resolved. There is no fallback to the integer cast: a
  definition that says a parameter defaults to a value its own enumeration does not
  declare is malformed, and quietly emitting `static_cast<Mode>(7)` would bake the
  contradiction into generated code and published documentation. Python's `Enum`
  already supplies the check, raising `ValueError: 7 is not a valid Mode` when
  constructed with an undeclared value, so removing the sint32 workaround gets this for
  free; the work is to attach the service, procedure and parameter to the message and
  raise it as the `RuntimeError` that `clientgen/__init__.py main()` already catches and
  reports, rather than letting it surface as a traceback. Worth giving the existing
  unresolvable-type errors the same treatment while nearby, since they escape as
  tracebacks today.
- **Defaults stay eagerly decoded.** Deferring the decode to first use would also fix
  the ordering, by making it impossible to decode too early, but it moves work into
  every call and hides definition errors until a user trips over them. A complete phase
  one makes eager decoding correct.
- **Scope.** The server is unchanged: it already emits complete definitions and does not
  consume them. The static client *libraries* are unchanged, since they resolve nothing
  at runtime, but clientgen is squarely in scope, and is the consumer with the failure
  that needs no ordering at all to reproduce.

## The shared analysis

A new `krpctools/definitions.py`, sitting under clientgen and docgen alike. It is given
the parsed definitions of **every** service in the input, and is the only thing that
knows about ordering.

```
Definitions.load(services_info) -> Definitions

  .types                  a Types registry with every named definition registered
  .services               the definitions, unchanged, keyed by service name
  .ordered_definitions()  every named definition, dependency order, service-qualified
  .collection_types(...)  structural types innermost first, replacing cnano's copy
```

`load` does three things in order: collect every named definition across all services;
topologically sort them by the types they reference; then walk that order registering
each into a single `Types` registry, calling `set_values` for an enumeration and, later,
`set_fields` for a struct. What a consumer gets back is a registry in which every
`as_type` already resolves, so the ordering question never reaches consumer code.

Three errors, all naming what failed and where:

| Condition | Today | Proposed |
| --- | --- | --- |
| Referenced type defined by no service in the input | `TypeError: 'NoneType' object is not callable`, from inside a decoder | `RuntimeError` naming the referring service and the missing type |
| Cycle among definitions | not possible yet; unbounded recursion once structs land | `RuntimeError` listing the cycle |
| Default naming an undeclared enum value | silently rendered as an integer cast | `RuntimeError` naming service, procedure and parameter |

`clientgen/__init__.py` builds a `Definitions` from the whole file and passes it to the
generator along with the target service name, replacing today's `defs[args.service]`.
`docgen/__init__.py` builds one from its merged definition files before constructing any
`Service` node. Both then keep their existing traversals unchanged: this deliberately
does not touch how they build contexts or doc nodes, only what they can assume while
doing it. In particular `docgen/nodes.py` needs no reordering once registration has
already happened, so its procedures-before-enumerations order becomes harmless rather
than something to fix.

cnano's `build_collection_types` is replaced by the shared `collection_types` helper.
Same traversal, one copy, and it gains the cycle check it currently does without.

### Why not sort in the producer

Worth asking, because if the definitions arrived already in a valid order then no
consumer would need to sort at all. The answer is that the producer cannot promise it,
for four independent reasons, any one of which is enough.

**The ServiceDefinitions tool emits exactly one service.** After scanning, `Program.cs`
narrows the scanner's results to the requested service and throws the rest away, even
though the other services were loaded and found:

```csharp
var services = KRPC.Service.Scanner.Scanner.GetServices ();
services = new Dictionary<string, ServiceSignature> { { service, services [service] } };
```

Each JSON file therefore describes one service, and no invocation of the tool ever sees
the graph it would have to sort.

**Order across kinds is not something a producer can express.** The JSON has separate
`procedures`, `classes`, `enumerations` and `exceptions` keys, and the protobuf has
separate repeated fields. "Definitions before procedures" is not an ordering of a
sequence, it is a choice the consumer makes about which key to read first. No producer
can stop `docgen/nodes.py` reading `procedures` first, which is the failure that
actually bites.

**The dynamic clients never see this tool.** They get a `Services` message from
`KRPC.GetServices` on the running server. Sorting in ServiceDefinitions would do nothing
for them. Sorting in the scanner instead would cover both paths, but the two reasons
above still apply, and so does the fourth.

**Cycles between services are legal.** Drawing, UI and the SpaceCenter already form
cross-service references, with Drawing's `Line.ReferenceFrame` typed as a SpaceCenter
class. Nothing forbids the reverse direction as well, and two services referring to each
other's types is a reasonable thing to build. A topological sort over services would
have to reject it, so the server cannot promise a valid global order even in principle.

And even where a producer could establish an order, a consumer cannot rely on it.
krpctools reads hand-written definitions such as `Empty.json` and third-party service
assemblies it did not produce, and docgen merges its definition files with
`services_info.update(...)` in command-line argument order, which discards whatever
order each file arrived in.

What the producer *can* usefully do is emit each `structs` list in dependency order
within its own service, where the scanner has already proved acyclicity. That is worth
doing when structs land, as a nicety that makes the file easier to read. It does not
remove the consumer's sort, because the consumer still cannot trust input it did not
generate.

### A missing definition, not a late one

Following the tool's one-service output through has a consequence for the error story.
When clientgen generates Drawing, SpaceCenter's definitions are not late, they are
absent: the file contains Drawing alone. Cross-service references work today only
because a class reference needs nothing but `service` and `name`, which the `Type`
message carries. Generated code says `class_type("SpaceCenter", "ReferenceFrame")` and
never consults a SpaceCenter definition.

So a cross-service enum default is not resolvable by clientgen at whatever ordering, and
neither would a cross-service struct be, which needs its field list to generate a codec
at all. The shared pass must report that as the missing input it is, naming the service
whose definitions were not supplied. Making it work is a separate change with a choice
of two shapes, either ServiceDefinitions emitting the definitions of services it
references alongside the requested one, or clientgen accepting several definition files
the way docgen already does. Neither is needed for this design, and both are cheap to
add later.

### What is deliberately not shared

clientgen's `generate_context` and docgen's `Service.__init__`/`Class.__init__` both
classify procedures with the same `Attributes` predicates, into procedures, properties,
class methods, class static methods and class properties. That is a real duplication,
around a hundred lines each, and it is a tempting thing to fold into the same module.

It is a separate refactor and should stay separate. The two produce different outputs
for different purposes, a template context against documentation nodes, and merging them
would put a large behavioral change in the same PR as the ordering fix, with the golden
fixtures for eleven generated outputs as the only check on it. Worth doing on its own
afterwards, if at all.

## Phases

1. **Python dynamic client.** Register the class and enum types of every service before
   creating any service, extending the pre-generated-stub pass in `client.py` to cover
   dynamic services too.
2. **Lua dynamic client.** The same change to `client.lua`.
3. **`krpctools/definitions.py`**, with its own unit tests and no callers yet: the
   collection of named definitions, the topological sort, the cycle and
   unresolved-reference errors, and the registry population. Testable entirely on its
   own, which is most of the argument for landing it separately.
4. **Adopt it in clientgen and docgen.** The full definitions through
   `clientgen/__init__.py`, a `Definitions` built once in `docgen/__init__.py`, and the
   registries moved off the class. cnano's `build_collection_types` gives way to the
   shared helper. No output change yet, so the golden files are untouched and the diff
   stays about the mechanism.
5. **Retire the enum workaround.** Drop the sint32 special case and render enum defaults
   as named members in each `lang/*.py` and in the `docgen/csharp.py` and
   `docgen/cpp.py` overrides. The registry from phase 4 is what lets the default decode
   through its real type, which fixes the nested case in the same stroke. Regenerate
   every golden fixture.
6. **Changelogs**, as a single commit before the branch is pushed.

Phases 4 and 5 are separable and worth separating: phase 4 is pure mechanism with no
output change, phase 5 is entirely output change. Reviewing them together would mean
reading a large fixture diff and a structural change at once.

## Tests

- **Dynamic clients**: build a two-service definition where one service's procedure
  defaults to the other's enum member, and construct the services in both orders. Both
  must yield a usable service whose default is the right enum member. A list-of-enums
  default covers the recursive case, where the enum sits inside a collection type.
- **krpctools**: a multi-service ordering fixture beside `Empty.json`, generating the
  dependent service, for both clientgen and docgen. The hostile order must produce
  output identical to the friendly order. It has to be hand-written, since the
  ServiceDefinitions tool emits one service per file and can never produce one.
- **Missing service**: generating a service whose definitions reference an enumeration
  no supplied file defines must fail naming the absent service, rather than producing
  output with a hole in it.
- **Nested enum default**: a procedure whose parameter defaults to a collection or tuple
  containing an enumeration, which fails today in both clientgen and docgen with no
  ordering involved. Worth adding to `TestService` as well as to the fixture, so the
  combination is covered by the client suites and the golden files from then on.
- **Regression on the existing fixtures**: after phase 5, `TestService`'s
  `EnumDefaultArg` renders a named member in all five clientgen languages and all six
  docgen languages. This is also what pins the registry actually being populated, since
  `docgen/nodes.py` still builds procedures before enumerations and would fail without
  it.
- **Repeated registration**: generating two definition sets in one process must not
  raise, covering the `set_values` assertion.
- **`definitions.py` unit tests**, independent of any generator: a shuffled input
  produces the same order; a definition referencing an undefined type raises naming
  both; a cyclic definition raises listing the cycle; collection types come back
  innermost first, matching what cnano emits today. The cycle case needs a hand-written
  fixture until structs exist, since nothing the scanner can currently produce has an
  edge to cycle on.
- **Malformed enum default**: a fixture whose parameter defaults to an integer its
  enumeration does not declare must fail generation with a message naming the service,
  procedure and parameter, for both clientgen and docgen.

## Effect on structs

[struct-types.md](struct-types.md) records this as its gotcha 4, because a struct's
field list is contents a consumer needs, exactly like an enumeration's values, and it is
needed far more often than only for defaults: it is the decoder. Once this lands, adding
structs to krpctools means teaching `definitions.py` two things, that a struct
definition contributes edges to each type its fields mention and that registering one
means calling `set_fields`. Nothing in clientgen or docgen changes to accommodate the
ordering, struct-typed default values need no special rule, and the gotcha and the
ordering work under its *Default values* section can be deleted rather than
implemented.

Struct cycles are where the cycle check earns its place. The server rejects them at
scan time, but krpctools also generates from hand-written JSON and from third-party
service assemblies it did not validate, so it cannot assume the definitions it is given
are well formed.

The reverse dependency does not hold. Nothing here needs structs, and everything here is
testable with enumerations alone.

## Open questions

None outstanding. The question of whether the ordering pass is genuinely shared code is
settled above: shared between clientgen and docgen in `krpctools/definitions.py`, and
deliberately not shared with the dynamic clients, which sit below krpctools in the
dependency order and read a different representation.
