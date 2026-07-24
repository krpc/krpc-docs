# Client testing standard and the shared TestService

**Status:** reference (as of 2026-07-24). A living standard, not a single-PR proposal. It
defines the coverage every kRPC client's test suite is expected to meet, records the current
per-client coverage from an audit, and specifies the shared `TestService` surface that makes
that coverage possible. Use it when adding a new client, when extending an existing client's
tests, or when growing `TestService`. Grew out of the nullable-values work
([issue #843](https://github.com/krpc/krpc/issues/843)); the audit below was taken right after
that landed.

## Purpose and scope

kRPC ships several clients (Python, C#, C++, Java, Lua, C-nano) that all speak one protocol. This
document is the full guide to what a client must test and how — both the **comms tests** run
against a shared game-less server (`TestService`) and the **unit tests** (codec round-trips, the
type system, name parsing, …). It answers:

1. **What must a client test?** — the [coverage rubric](#coverage-rubric).
2. **How is it tested?** — the [test layers](#test-layers) (comms plus several unit-test kinds).
3. **What must the test service expose so a client *can* test it?** — the
   [TestService specification](#testservice-specification).
4. **How well does each client test it today?** — the [coverage matrix](#current-coverage).

The six clients above all speak **protobuf over TCP/IP**. Two additional, bare-bones *test-only*
clients — `client/websockets` and `client/serialio` — exist so the server's **websockets** and
**serial** transports are exercised too (no shipping client uses them). They connect to
`TestServer` and run just enough comms tests to prove the server speaks those protocols; they do
**not** implement the full rubric or any code generation. Except where noted, the rest of this
document is about the six full clients.

Out of scope: in-game integration tests (`service/*/test/`, which need a real KSP install) and
the game services themselves. This is about protocol-surface conformance for the clients.

## Test layers

A complete client test suite spans several layers. The [rubric](#coverage-rubric) is the *what*;
this section is the *how* — which layer verifies which part of it. Each layer is realized by a
canonical set of test files, enumerated in [test structure](#test-structure); every client mirrors
that layout, adapting file and function names to its language.

**The harness.** `tools/TestServer` runs the real `KRPC.Core` server without KSP (`Program.cs`
pumps `core.Update()` at 60 FPS and auto-allows connections) and serves every transport —
protobuf over TCP, websockets, websockets-echo, and serial. It exposes one hand-written service,
`tools/TestServer/src/TestService.cs` (id 9999), that every client tests against.

- **Layer 1 — Comms tests (the full rubric A–I, against `TestServer`).** The client calls
  `TestService` over a live connection and asserts behavior. This is the primary layer and where
  most of the rubric is verified. Mature suites add robustness tests here too —
  unknown-exception-type degradation, blocking/`YieldException` procedures, deferred ("…Later")
  stream exceptions, thread safety, line-ending round-tripping, and member-roster assertions —
  recommended but not required for a first pass.
- **Layer 2 — Codec round-trip unit tests (Section B, no server).** Encode and decode every
  Section-B type in isolation, asserting the **exact wire bytes** as well as the round-tripped
  value; plus message framing, size prefixes, and GUID decoding. This pins the wire format
  precisely and without a server — a finer-grained check than Layer 1, which asserts values but
  not their byte encoding. Every Section-B type is covered here, in both directions.
- **Layer 3 — Type-system unit tests (no server).** Construct each kind of type (value, class,
  enum, message, list, set, dictionary, tuple) and exercise the client's coercion rules (e.g.
  coercing a plain container to the typed collection, or a value to its declared type). Underpins
  A8/A9 (type representation) and the Section-B types.
- **Layer 4 — Name & attribute parsing unit tests (no server).** The client maps wire member
  names to its own conventions and classifies them (procedure vs property accessor vs class
  member; extracting service/class/member names). Test the name conversion and the classifier; the
  target naming convention is language-specific (e.g. Python's snake_case).
- **Layer 5 — Golden fixtures (generated code and docs).**
  `tools/krpctools/krpctools/test/clientgen-TestService-<lang>.txt` pins the generated client —
  every member, the `T?`/`std::optional`/boxed signatures, default values, and the Section-I
  deprecation markers; the docgen fixtures pin the generated documentation. Both are checked by
  `//tools/krpctools:test`; regenerate them when the generator or `TestService` changes. (Dynamic
  clients — Lua — have no clientgen fixture.)
- **Layer 6 — Connection & transport (TCP).** Connection setup/teardown, wrong-port /
  wrong-server detection, and message framing, plus platform helpers such as hexlify and float
  conversions (language-specific — N/A where the platform provides them). (The server's non-TCP
  transports are covered separately by the `websockets`/`serialio` test-clients — see
  [Purpose and scope](#purpose-and-scope).)

## Coverage rubric

The rubric below is the *what to test*; the [test layers](#test-layers) are the *how*. It is
covered in full by the Layer 1 comms tests, and Section B is additionally round-tripped by the
Layer 2 codec unit tests. Every client should cover each leaf id, or mark it *N/A* with a reason
(the feature is not supported or not expressible in that language). The
[matrix](#current-coverage) and the [TestService specification](#testservice-specification)
reference these ids.

**A. Member kinds**
- A1 service procedure
- A2a service property getter · A2b service property setter
- A3 class instance method
- A4 class static method
- A5a class property getter · A5b class property setter
- A6 custom exception
- A7a `ArgumentException` · A7b `InvalidOperationException` · A7c `ArgumentNullException` · A7d `ArgumentOutOfRangeException`
  — these four are the **complete** set of standard exceptions kRPC maps to typed protocol
  exceptions (declared in `core/src/Service/KRPC/`). Any other exception a service throws (e.g.
  `NullReferenceException`) is **not** mapped and reaches the client as a generic `RPCException`
  carrying the message. That generic path is exercised separately — by the null-rejection tests
  (D5/E5, whose server error is an untyped `RPCException`) and the recommended
  unknown-exception-type test (a Layer 1 robustness test) — so it needs no dedicated A-row.
- A8 enumeration type and its values are represented in the client — the generated enum type
  with its named members. This is the enum *declaration* (distinct from `B4`, which passes an
  enum *value* to/from a procedure over the wire).
- A9 class (remote-object) type is represented in the client — the generated handle type and
  its identity/equality semantics (two handles to the same server object compare equal). This
  is the class *declaration* (distinct from `B5`, which passes an object over the wire, and from
  A3–A5, which call the class's members).

**B. Types** — every type is tested in two directions: as a procedure **argument** (id prefixed
`Ba`) and as a **return** value (id prefixed `Bb`). The prefix is followed by the type id below,
so `Ba1a` is a `double` argument and `Bb1a` a `double` return; `Ba3`/`Bb3` are a `bytes`
argument/return. Per-direction coverage is in the [type-coverage table](#type-coverage-section-b).
- 1a `double` · 1b `float` · 1c `sint32` · 1d `sint64` · 1e `uint32` · 1f `uint64` · 1g `bool`
- 2 `string` · 3 `bytes`
- 4 enumeration · 5 class object
- collections of scalars: 6 list · 7 set · 8 dictionary · 9 tuple · 10 nested collection
- collections of class objects: 11a list · 11b set · 11c dictionary · 11d tuple

**C. Default arguments** — a parameter may declare a default (via `= value` or
`[KRPCDefaultValue]`), applied when the caller omits the argument. A default value is
encoded/decoded like any value of its type, so the per-type handling is already covered by
Section B; these rows test the default *mechanism* for each *kind* of default — hence one
representative scalar rather than one row per scalar type.
- C1a scalar default · C1b string default · C1c bytes default
- non-empty collection defaults: C2a list · C2b set · C2c dictionary · C2d tuple
- C2e empty-collection default — an empty collection is a valid default, distinguishable on the
  wire (`has_default_value` set, empty `default_value`) from having no default (the #824 case)
- C3 null default — a parameter whose declared default *is* null (`default_value_is_null` set),
  so omitting the argument yields null. This checks the client reads the default-presence
  metadata and applies a null default; it is distinct from Section D, which passes null as an
  *explicit* argument value. Applies to any nullable parameter (the TestService example happens
  to be a class one; a nullable collection or string could default to null too).
- C4 enum default

Beyond the default *value*, the argument-passing *mechanism* itself needs testing — a callable with
optional parameters invoked with only a subset of its arguments. This is verified on each callable
kind that takes arguments **individually**: a **service procedure**, a **class instance method**,
and a **class static method** (the vehicle is one shared four-parameter signature per kind, whose
*non-trailing* default means an omission leaves a gap in the wire argument positions).
- C5a trailing omission — supply a leading subset of arguments; the rest take their defaults.
  Applies wherever default arguments do.
- C5b named and non-contiguous arguments — supply arguments by name and/or omit a *non-trailing*
  defaulted argument (producing gapped argument positions on the wire), plus the associated errors
  (too many arguments, a duplicate, an unknown name). Applies only to clients with named-argument
  support.

**D. Nullable arguments**
- D1 nullable value type
- D2 nullable string
- D3a nullable list · D3b nullable set · D3c nullable dictionary · D3d nullable tuple
- D4 nullable class
- D5 a null argument to a **non-nullable** parameter is rejected — an integration check that the
  client sends null out-of-band (rather than rejecting it locally) and surfaces the server's
  rejection as its RPC-error type. The enforcement itself is server-side (covered by core unit
  tests); this row verifies the client half of that round-trip.

**E. Return values**
- E1 nullable value-type return
- E2 nullable string return
- E3a nullable list return · E3b nullable set return · E3c nullable dictionary return · E3d nullable tuple return
- E4 nullable class return
- E5 a null return from a **non-nullable** procedure raises an error — like D5, an integration
  check that the client surfaces the server's error (enforcement is server-side)
- E6 void return (a procedure that returns nothing completes normally)

**F. Nullable properties**
- F1 a nullable property (getter may return null, setter accepts null): F1a getter returns null · F1b setter accepts null
- F2 nullable-for-reads property whose setter rejects null (guarded)

**G. Streams** — a stream repeatedly evaluates a value-returning call. Rather than re-enumerate
member kinds and value types, G reuses A and E: which calls can be streamed (the value-returning
members of A), what a stream delivers (return values per E/B), plus the stream-only lifecycle.
- G1 a stream can be created for each value-returning member kind: G1a procedure · G1b service
  property getter · G1c class method · G1d static method · G1e class property getter (the
  returning members of Section A; setters and void procedures are not streamable)
- G2 stream delivery: G2a values decoded exactly like return values (Sections E/B, including a
  null value) · G2b a server error surfaced when the streamed call fails
- G3 lifecycle (stream-only): G3a start · G3b rate · G3c wait/condition · G3d callbacks · G3e remove · G3f freeze/thaw

**H. Events** — an event is a server-created condition (internally a stream of a boolean that
fires when the condition becomes true), surfaced through the client's Event API. As with F, the
members that create one are just procedures/properties returning an `Event`; the event-only
surface is creation and waiting.
- H1 event creation: H1a from a member that returns an `Event` (e.g. `OnTimer`,
  `OnTimerUsingLambda`) · H1b a custom event built client-side from an expression over existing
  members
- H2 event lifecycle: H2a wait until it fires · H2b wait with a timeout · H2c callbacks (added,
  invoked on fire, and removed)

**I. Deprecation** — a deprecated member is surfaced over the wire (since #904) and the client
should flag it. This is mostly a codegen concern: the generated stubs carry the language's
deprecation marker (C# `[Obsolete]`, C++ `[[deprecated]]`, Java `@Deprecated`, C-nano
`KRPC_DEPRECATED`, Python a docstring note), verified by the golden fixtures
(`//tools/krpctools:test`); a client that can signal deprecation at call time also does so
(Python raises a `DeprecationWarning`). Each deprecatable kind should be flagged:
- I1 deprecated procedure — I1a with a reason · I1b without a reason
- I2 deprecated property
- I3 deprecated class
- I4 deprecated class method
- I5 deprecated enumeration — I5a the type · I5b a member
- I6 deprecated exception

## TestService specification

This is the reusable part: the complete set of members `TestService` should expose so that every
rubric row is testable by every client. Signatures are shown C#-style (the service is written in
C#), and every member is labeled with the rubric id(s) it covers — the labels live here in the
tables, not as comments in the source. **Status** is one of:

- `existing` — present in `tools/TestServer/src/TestService.cs` today.
- `proposed` — a new member that closes a coverage gap.
- `edit` — an existing member renamed or re-scoped (its old rubric duties move elsewhere).
- `remove` — an existing member to delete; its coverage is subsumed by another member.

The **target surface** is every `existing` and `proposed` member minus the `remove` ones. A client
is "fully tested" once its suite exercises every target member relevant to its capabilities. Any
add, rename or removal regenerates the golden fixtures (`//tools/krpctools:test`) and touches every
client comms test that referenced the member — the [change summary](#summary-of-proposed-changes)
lists what moves.

Attribute shorthand: `[N]` = `[KRPCNullable]` on a parameter; `Nullable=true` on the procedure
marks the return nullable; `[KRPCDefaultValue]` supplies a default the C# `= value` syntax cannot
express.

### Testing values — conversion, transform, echo

Three patterns prove a value crossed the wire intact. Each member below uses the strongest one its
type allows:

- **Conversion** (scalars, `bytes`, enum) — `<T>ToString` in the argument direction, `StringTo<T>`
  in the return direction, routing through a string (or hex string, or enum name): an *independent*
  representation. This proves the server received the value the client sent and the client received
  the value the server produced, and — unlike a same-type `Echo<T>` — cannot be fooled by a symmetric
  encoder/decoder bug that corrupts a value identically in both directions.
- **Transform** (collections) — `Increment…` / `AddTo…` / `Swap…`: the server decodes every element,
  operates on it, and returns the result. A transform is the collection analog of conversion — it
  proves the elements actually arrived, which a straight echo of the container would not.
- **Echo** (nullables, object handles, defaults) — `Echo…` / `…Default`: a same-type round-trip, used
  where the test targets a *mechanism*, not a value — the nullable wire flag (`is_null`), object-handle
  identity, or default application. The value's codec is already pinned by Section B and the Layer-2
  unit tests, so echo keeps the actual thing on the wire (a real `null` sent and returned, the same
  handle round-tripped) rather than a stand-in. A nullable *could* instead be converted — map `null`
  to a `"null"` string — but that would exercise string handling of a sentinel, not the `is_null`
  encoding these rows exist to check.

### Summary of proposed changes

**Add** (`proposed`):
- Missing scalar arguments and every scalar return: `UInt32ToString`, `UInt64ToString`,
  `StringToDouble`, `StringToFloat`, `StringToInt64`, `StringToUInt32`, `StringToUInt64`,
  `StringToBool`, `HexStringToBytes` (`Ba1e`/`Ba1f`, `Bb1a`/`Bb1b`/`Bb1d`–`Bb1g`, `Bb3`).
- Object collections beyond list: `AddToObjectSet`, `AddToObjectDictionary`, `SwapObjectTuple`
  (`Ba`/`Bb` 11b–d).
- Nullable completeness: `EchoNullableFloat`, `EchoNullableBool`, `EchoNullableEnum`,
  `EchoNullableSet`, `EchoNullableDictionary`, `EchoNullableTuple` (D1/E1, D3b–d/E3b–d).
- A uniform default family: `ScalarDefault` (C1a), `StringDefault` (C1b), `NullDefault` (C3),
  `BytesDefault` (C1c).
- Enum conversion pair: `EnumToString`, `StringToEnum` (`Ba4`, `Bb4`).
- `TestClass.StaticOptionalArguments` — a class *static* method with the `OptionalArguments`
  signature, so partial/named argument passing (C5) is testable on a static method as well as on a
  service procedure and an instance method (see [partial and named arguments](#partial-and-named-arguments)).

**Edit**:
- `EnumDefaultArg` → `EnumDefault` — naming consistency with the `*Default` family.
- `BlockingProcedure` keeps its signature but drops its C1a label: its `sum=0` accumulator is an
  implementation detail, not a defaults test, and C1a moves to `ScalarDefault`.

**Remove**:
- `AddMultipleValues` — multi-argument ordering is covered by the `OptionalArguments` members, and
  its per-type coverage duplicates the `<T>ToString` family.
- `EnumEcho`, `EnumReturn` — subsumed by the `EnumToString`/`StringToEnum` conversion pair.

The service-level `OptionalArguments` is **kept** (not removed): its individual C1b/C3 default
*values* are now owned by `StringDefault`/`NullDefault`, but it is the service-procedure vehicle for
partial/named argument passing (C5), alongside the instance and new static methods.

Each removal deletes the member from `TestService.cs`, regenerates the fixtures, and requires
updating any client comms test that called it.

### Scalars, strings and bytes

Argument direction — every scalar (and `bytes`) to its string form:

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `FloatToString` | `(float) → string` | A1, Ba1b, Bb2 | existing |
| `DoubleToString` | `(double) → string` | Ba1a, Bb2 | existing |
| `Int32ToString` | `(int) → string` | Ba1c, Bb2 | existing |
| `Int64ToString` | `(long) → string` | Ba1d, Bb2 | existing |
| `UInt32ToString` | `(uint) → string` | Ba1e, Bb2 | proposed |
| `UInt64ToString` | `(ulong) → string` | Ba1f, Bb2 | proposed |
| `BoolToString` | `(bool) → string` | Ba1g, Bb2 | existing |
| `BytesToHexString` | `(byte[]) → string` | Ba3, Bb2 | existing |

Return direction — a string parsed back to every scalar (and `bytes`):

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `StringToDouble` | `(string) → double` | Ba2, Bb1a | proposed |
| `StringToFloat` | `(string) → float` | Ba2, Bb1b | proposed |
| `StringToInt32` | `(string) → int` | Ba2, Bb1c | existing |
| `StringToInt64` | `(string) → long` | Ba2, Bb1d | proposed |
| `StringToUInt32` | `(string) → uint` | Ba2, Bb1e | proposed |
| `StringToUInt64` | `(string) → ulong` | Ba2, Bb1f | proposed |
| `StringToBool` | `(string) → bool` | Ba2, Bb1g | proposed |
| `HexStringToBytes` | `(string) → byte[]` | Ba2, Bb3 | proposed |

The `string` type itself (type 2) needs no dedicated member: `Ba2` is exercised by every
`StringTo<T>` argument, `Bb2` by every `<T>ToString` return, and `StringProperty` covers it as a
property. The two tables together give live coverage of every Section-B scalar in both directions —
one consistent matrix that closes the `Bb1*` return gaps and the `Ba1e`/`Ba1f` argument gaps.
`AddMultipleValues` is removed: multi-argument ordering is covered by the `OptionalArguments`
members (which concatenate their arguments in order — see
[partial and named arguments](#partial-and-named-arguments)), and its per-type coverage duplicates
this matrix.

### Collections of scalars

Each is a **transform** — the server increments every element, so a passing result proves the
elements decoded, not merely that the container arrived:

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `IncrementList` | `(IList<int>) → IList<int>` | Ba6, Bb6 | existing |
| `IncrementSet` | `(HashSet<int>) → HashSet<int>` | Ba7, Bb7 | existing |
| `IncrementDictionary` | `(IDictionary<string,int>) → …` | Ba8, Bb8 | existing |
| `IncrementTuple` | `(Tuple<int,long>) → …` | Ba9, Bb9, Ba1d/Bb1d (sint64 element) | existing |
| `IncrementNestedCollection` | `(IDictionary<string,IList<int>>) → …` | Ba10, Bb10 | existing |

### Collections of class objects

The transform pattern applied to object handles: `AddTo…` appends a fresh handle and returns the
collection; `SwapObjectTuple` reverses the pair (a tuple is fixed-arity, so it cannot be appended
to). Each proves the server decoded the incoming handles.

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `AddToObjectList` | `(IList<TestClass>, string) → IList<TestClass>` | Ba11a, Bb11a | existing |
| `AddToObjectSet` | `(HashSet<TestClass>, string) → HashSet<TestClass>` | Ba11b, Bb11b | proposed |
| `AddToObjectDictionary` | `(IDictionary<string,TestClass>, string key, string value) → …` | Ba11c, Bb11c | proposed |
| `SwapObjectTuple` | `(Tuple<TestClass,TestClass>) → Tuple<TestClass,TestClass>` | Ba11d, Bb11d | proposed |

### Default arguments

A uniform `<Kind>Default` family, one member per kind of default, each returning its (possibly
defaulted) argument so the client can assert the applied value. The value originates server-side, so
returning it is a valid **echo** — its codec is covered in Section B; these rows test the default
*mechanism*. The family exercises both ways to declare a default: the C# literal `= value` and the
`[KRPCDefaultValue]` attribute (which collections require).

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `ScalarDefault` | `(int x = 42) → int` | C1a | proposed |
| `StringDefault` | `(string x = "foo") → string` | C1b | proposed |
| `BytesDefault` | `([KRPCDefaultValue] byte[] x) → byte[]` | C1c | proposed |
| `ListDefault` | `([KRPCDefaultValue] IList<int>) → …` (`{1,2,3}`) | C2a | existing |
| `SetDefault` | `([KRPCDefaultValue] HashSet<int>) → …` (`{1,2,3}`) | C2b | existing |
| `DictionaryDefault` | `([KRPCDefaultValue] IDictionary<int,bool>) → …` (`{1:false,2:true}`) | C2c, Ba1g (bool element) | existing |
| `TupleDefault` | `([KRPCDefaultValue] Tuple<int,bool>) → …` (`(1,false)`) | C2d | existing |
| `EmptyListDefault` | `([KRPCDefaultValue] IList<string>) → …` (empty) | C2e (empty-collection default) | existing |
| `NullDefault` | `([N] TestClass obj = null) → TestClass` (`Nullable=true`) | C3 (null default) | proposed |
| `EnumDefault` | `(TestEnum x = ValueC) → TestEnum` | C4 | edit (rename of `EnumDefaultArg`) |

`ScalarDefault`, `StringDefault` and `NullDefault` replace the C1a/C1b/C3 default-*value* coverage
that previously hid inside `BlockingProcedure` and the `OptionalArguments` members, so each default
kind has one obvious owner. The `OptionalArguments` members are retained for a different job — the
argument-passing mechanism below.

### Partial and named arguments

The three `OptionalArguments` members share one signature —
`(string x, string y="foo", string z="bar", [N] TestClass obj=null) → string`, returning
`x+y+z+obj` — so the same partial- and named-argument behavior (Section C5) is verified on each
callable kind that takes arguments. The *non-trailing* default `z` is the point: omitting it while
supplying `obj` leaves a gap in the wire argument positions, which a client's argument encoder must
handle.

| Member | Kind | Rubric | Status |
|---|---|---|---|
| `OptionalArguments` | service procedure | A1, C5a, C5b | existing |
| `TestClass.OptionalArguments` | class instance method | A3, C3, C5a, C5b | existing |
| `TestClass.StaticOptionalArguments` | class static method | A4, C5a, C5b | proposed |

C5a (trailing omission) applies wherever default arguments do; C5b (supplying a later argument by
name while omitting `z`, plus the arity/duplicate/unknown-name errors) applies only to clients with
named-argument support. Ordering of a fully-supplied multi-argument call (A1) is verified here too,
and by the multi-parameter members elsewhere (e.g. `AddToObjectDictionary`).

### Nullable arguments and returns

Nullable members are **echo** (`T? → T?`, or `Nullable=true` on the return): a same-type round-trip
keeps an actual `null` on the wire in both directions, directly exercising the protocol's `is_null`
encoding — where converting through a `"null"` sentinel string would test string handling instead.
Each covers its type as both a nullable argument (Section D) and a nullable return (Section E).

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `EchoNullableInt` | `(int?) → int?` | D1, E1 | existing |
| `EchoNullableFloat` | `(float?) → float?` | D1, E1 | proposed |
| `EchoNullableBool` | `(bool?) → bool?` | D1, E1 | proposed |
| `EchoNullableEnum` | `(TestEnum?) → TestEnum?` | D1, E1 | proposed |
| `EchoNullableString` | `([N] string) → string` (`Nullable=true`) | D2, E2 | existing |
| `EchoNullableList` | `([N] IList<int>) → …` (`Nullable=true`) | D3a, E3a | existing |
| `EchoNullableSet` | `([N] HashSet<int>) → …` (`Nullable=true`) | D3b, E3b | proposed |
| `EchoNullableDictionary` | `([N] IDictionary<string,int>) → …` (`Nullable=true`) | D3c, E3c | proposed |
| `EchoNullableTuple` | `([N] Tuple<int,long>) → …` (`Nullable=true`) | D3d, E3d | proposed |
| `EchoTestObject` | `([N] TestClass) → TestClass` (`Nullable=true`) | Ba5, Bb5, D4, E4 | existing |
| `NotNullableObject` | `(TestClass) → TestClass` | Ba5, Bb5, D5 (rejects null arg) | existing |
| `ReturnNullWhenNotAllowed` | `() → TestClass` (returns null, **not** nullable) | E5 (rejects null return) | existing |
| `CreateTestObject` | `(string) → TestClass` | A1, Bb5 (object creation) | existing |

> The nullable scalars/enum and the nullable set/dict/tuple are completeness additions: they travel
> the same encoder/decoder and `is_null` paths as the covered `EchoNullableInt` and `EchoNullableList`,
> so they rank below the E5 client gap and the scalar/bytes/object-collection additions.
> `EchoTestObject` gives the object type its nullable `Ba5`/`Bb5`/D4/E4 round-trip; `NotNullableObject`
> and `ReturnNullWhenNotAllowed` give the D5/E5 rejection round-trips.

### Enumerations

The conversion pair gives the enum strict argument and return coverage by routing through the enum
*name*; `EnumDefault` (in [defaults](#default-arguments)) covers C4, and the `TestEnum` declaration
itself covers A8.

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `EnumToString` | `(TestEnum) → string` | Ba4, Bb2 | proposed |
| `StringToEnum` | `(string) → TestEnum` | Ba2, Bb4 | proposed |

These replace `EnumEcho` (`(TestEnum) → TestEnum`) and `EnumReturn` (`() → TestEnum`), which are
removed: going through the name makes Ba4/Bb4 independent, where the echo/return pair shared the
symmetric-bug weakness that motivates conversion everywhere else.

### Exceptions and blocking

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `ThrowArgumentException` | `() → int` (throws) | A7a | existing |
| `ThrowInvalidOperationException` | `() → int` (throws) | A7b | existing |
| `ThrowArgumentNullException` | `(string) → int` (throws) | A7c | existing |
| `ThrowArgumentOutOfRangeException` | `(int) → int` (throws) | A7d | existing |
| `ThrowCustomException` | `() → int` (throws `CustomException`) | A6 | existing |
| `ThrowInvalidOperationExceptionLater` / `ResetInvalidOperationExceptionLater` | deferred throw; `Reset` returns `void` | G2b (errored stream), E6 (void return) | existing |
| `ThrowCustomExceptionLater` / `ResetCustomExceptionLater` | deferred throw for streams | G2b (errored stream) | existing |
| `BlockingProcedure` | `(int n, int sum=0) → int` (uses `YieldException`) | blocking/yield robustness | existing |

`BlockingProcedure` no longer carries C1a — its `sum=0` accumulator is an implementation detail, and
the scalar default now lives in `ScalarDefault`. The `void`-returning `Reset…` members cover E6.

### Streams and events

Streams (Section G) and events (Section H) add no value members — G streams the value-returning
members of Sections A/E, and H2 exercises the client's Event API over the members below. `Counter`
gives a stream something that changes each poll (G1a) at a controllable rate (G3b); the `…Later`
throwers above give a stream that eventually errors (G2b). The other streamable member kinds reuse
Section A — a service property getter (`StringProperty`), a class method (`GetValue`), a static
method (`StaticMethod`) and a class property getter (`IntProperty`) cover G1b–G1e.

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `Counter` | `(string id="", int divisor=1) → int` (per-client count) | G1a, G3b (rate) | existing |
| `OnTimer` | `(uint milliseconds, uint repeats=1) → Event` | H1a | existing |
| `OnTimerUsingLambda` | `(uint milliseconds) → Event` | H1a | existing |

`OnTimer` and `OnTimerUsingLambda` exercise H1a (an event from a returned `Event`) and, through the
client Event API, all of H2; H1b (a custom event) is built client-side from an expression over
existing members, so it needs no dedicated member.

### Service properties

| Member | Accessors | Rubric | Status |
|---|---|---|---|
| `StringProperty` | get + set | A2a, A2b, Ba2, Bb2 | existing |
| `StringPropertyPrivateGet` | set only (public) | A2b, asymmetric accessor | existing |
| `StringPropertyPrivateSet` | get only (public) | A2a, asymmetric accessor | existing |
| `ObjectProperty` | get + set, `Nullable=true` | A2a, A2b, F1a, F1b | existing |
| `NullableObject` | get + set, `Nullable=true`, setter throws on null | F2 (guarded setter) | existing |

### Class `TestClass`

| Member | Signature | Rubric | Status |
|---|---|---|---|
| `GetValue` | `() → string` | A3 | existing |
| `FloatToString` | `(float) → string` | A3, Ba1b, Bb2 | existing |
| `ObjectToString` | `([N] TestClass) → string` | A3, Ba5, D4 | existing |
| `EchoNullableObject` | `([N] TestClass) → TestClass` (`Nullable=true`) | A3, Ba5, Bb5, D4, E4 | existing |
| `StaticMethod` | `static (string a="", string b="") → string` | A4, C1b | existing |
| `StaticNullableObject` | `static ([N] TestClass) → TestClass` (`Nullable=true`) | A4, Ba5, Bb5, D4, E4 | existing |
| `IntProperty` | get + set | A5a, A5b, Ba1c, Bb1c | existing |
| `ObjectProperty` | get + set, `Nullable=true` | A5a, A5b, F1a, F1b | existing |
| `StringPropertyPrivateGet` / `StringPropertyPrivateSet` | asymmetric accessors | A5a, A5b | existing |

The instance `OptionalArguments` and the new static `StaticOptionalArguments` are the class-member
vehicles for partial/named argument passing — listed under
[partial and named arguments](#partial-and-named-arguments).

### Types, enums and exceptions

| Item | Definition | Rubric | Status |
|---|---|---|---|
| `TestClass` | remote class, `Equals`/`GetHashCode` for identity tests | A9 (representation), A3–A5b (members) | existing |
| `TestEnum` | `{ ValueA, ValueB, ValueC }` | A8 (representation), Ba4, Bb4 (wire) | existing |
| `CustomException` | `[KRPCException]` | A6 | existing |

### Deprecation levers (Section I)

These members carry no behavior — they exist purely as levers for the generators and the docs. Each
is a different deprecatable kind, marked `[Obsolete]` in C#; the golden fixtures
([Layer 5](#test-layers)) assert that every client generator emits the language's deprecation marker
for it, which makes Section I primarily a codegen check rather than a comms one.

| Member | Deprecated kind | Rubric | Status |
|---|---|---|---|
| `DeprecatedProcedure` | procedure, with a reason | I1a | existing |
| `DeprecatedProcedureNoMessage` | procedure, no reason | I1b | existing |
| `DeprecatedProperty` | property | I2 | existing |
| `DeprecatedClass` | class | I3 | existing |
| `DeprecatedClass.DeprecatedMethod` | class method | I4 | existing |
| `DeprecatedEnum` | enumeration type | I5a | existing |
| `DeprecatedEnum.ValueB` | enumeration member | I5b | existing |
| `DeprecatedException` | exception | I6 | existing |

The docgen fixtures additionally check the deprecation notice in the rendered docs, and the Python
client raises a runtime `DeprecationWarning` at call time (`test_deprecated_procedure_warns`).

### Documentation fixtures (docgen only, not in the rubric)

One documented member of each kind carries an XML `<summary>` (and every deprecated member carries
its own) purely to exercise docgen: the service, one procedure (`FloatToString`), one property
(`StringProperty`), the class `TestClass` with one method (`GetValue`) and one class property
(`IntProperty`), and the enum `TestEnum` with its members. The docgen golden fixtures pin the
rendered output for each, so a change to a generator's documentation handling — or to one of these
`<summary>` strings — surfaces as a fixture diff. Checked by `//tools/krpctools:test`, not the
client comms suites.

## Test structure

This is the target test suite for a **fully implemented** `TestService` (every
[specification](#testservice-specification) member present): a canonical set of files, roughly one
cluster per [layer](#test-layers), whose tests together cover every rubric leaf id. Each client
mirrors the layout, adapting file and function names to its language (Python `test_encoder.py`, C++
`test_encoder.cpp`, C# `EncoderTest.cs`, Java `EncoderTest.java`). The function names below are
descriptive, not prescriptive — what is fixed is the grouping and the coverage. Every line notes the
rubric id(s) it covers and the driving member; a client marks a test *N/A* only for a genuine
language limit (called out per file), and every non-N/A leaf id is exercised by at least one line.

**Layer 1 — comms tests** (require a running `TestServer`):

```text
test_client — the RPC surface (Sections A–F, plus Section B live)
    # scalars, strings, bytes — value round-trips (Section B, both directions)
    test_scalar_arguments          # every scalar -> string via <T>ToString    (Ba1a-Ba1g, Bb2)
    test_scalar_returns            # string -> every scalar via StringTo<T>     (Ba2, Bb1a-Bb1g)
    test_bytes                     # BytesToHexString / HexStringToBytes        (Ba3, Bb3)
    # service procedures & properties (Section A)
    test_procedure                 # a plain service procedure call             (A1)
    test_service_property          # StringProperty get/set + write-only/read-only accessors  (A2a, A2b)
    # enums (Section B4; the A8 declaration is exercised in test_types)
    test_enum                      # EnumToString / StringToEnum                (Ba4, Bb4)
    test_invalid_enum              # out-of-range value rejected
    # collections of scalars (Section B6-B10)
    test_collections               # Increment{List,Set,Dictionary,Tuple}       (Ba6-Ba9, Bb6-Bb9)
    test_nested_collection         # IncrementNestedCollection                  (Ba10, Bb10)
    # collections of class objects (Section B11)
    test_object_collections        # AddToObject{List,Set,Dictionary}, SwapObjectTuple  (Ba11a-d, Bb11a-d)
    # remote objects (Section B5; class members A3-A5)
    test_object_round_trip         # CreateTestObject, EchoTestObject           (Ba5, Bb5)
    test_class_method              # instance method (GetValue, ObjectToString) (A3)
    test_class_static_method       # StaticMethod                               (A4)
    test_class_property            # IntProperty get/set + asymmetric accessors (A5a, A5b)
    # default arguments (Section C) -- N/A for Java, C-nano (no default-argument support)
    test_scalar_defaults           # ScalarDefault, StringDefault, BytesDefault (C1a, C1b, C1c)
    test_collection_defaults       # List/Set/Dictionary/Tuple/EmptyList Default (C2a-C2e)
    test_null_default              # NullDefault                                (C3)
    test_enum_default              # EnumDefault                                (C4)
    # partial & named argument passing, on each callable kind individually (Section C5) -- N/A Java, C-nano
    test_partial_arguments_procedure     # trailing omission, service procedure          (C5a)
    test_partial_arguments_method        # trailing omission, class instance method      (C5a)
    test_partial_arguments_static_method # trailing omission, class static method        (C5a)
    test_named_arguments_procedure       # named/non-contiguous + arity errors, procedure  (C5b) -- named-arg clients only
    test_named_arguments_method          # ... class instance method                     (C5b) -- named-arg clients only
    test_named_arguments_static_method   # ... class static method                       (C5b) -- named-arg clients only
    # nullable arguments & returns (Sections D, E)
    test_nullable_values           # EchoNullable{Int,Float,Bool,Enum}          (D1, E1)
    test_nullable_string           # EchoNullableString                         (D2, E2)
    test_nullable_collections      # EchoNullable{List,Set,Dictionary,Tuple}    (D3a-d, E3a-d)
    test_nullable_object           # EchoTestObject, EchoNullableObject, StaticNullableObject  (D4, E4)
    test_null_argument_rejected    # NotNullableObject(null) raises             (D5)
    test_null_return_rejected      # ReturnNullWhenNotAllowed() raises          (E5)
    test_void_return               # a void procedure completes normally        (E6)
    # nullable properties (Section F)
    test_nullable_property         # ObjectProperty get -> null, set <- null    (F1a, F1b)
    test_guarded_nullable_property # NullableObject setter rejects null          (F2)
    # exceptions (Sections A6, A7)
    test_standard_exceptions       # Argument / InvalidOperation / ArgumentNull / ArgumentOutOfRange  (A7a-A7d)
    test_custom_exception          # ThrowCustomException                       (A6)
    test_unknown_exception_type    # unmapped exception -> generic RPC error    (robustness)
    # robustness (recommended; not rubric leaves)
    test_blocking_procedure        # BlockingProcedure (YieldException)
    test_member_rosters            # service/class/enum member lists match
    test_line_endings              # CR/LF survive a string round-trip
    test_multiple_connections      # objects/types across separate connections

test_stream — streams (Section G) -- N/A for Lua, C-nano (no stream support)
    test_stream_procedure          # stream a procedure                         (G1a)
    test_stream_service_property   # stream a service property getter           (G1b)
    test_stream_class_method       # stream an instance method                  (G1c)
    test_stream_static_method      # stream a static method                     (G1d)
    test_stream_class_property     # stream a class property getter             (G1e)
    test_stream_rejects_setters    # setters and void procedures are not streamable
    test_stream_values             # streamed values decode as returns do (per E/B)  (G2a)
    test_stream_null_value         # a stream delivers null                     (G2a)
    test_stream_error              # a streamed call throws, immediate and deferred  (G2b)
    test_stream_start              # a new stream begins delivering             (G3a)
    test_stream_rate               # Counter at a controlled rate               (G3b)
    test_stream_wait               # wait for a condition, with and without a timeout  (G3c)
    test_stream_callbacks          # callback added, invoked, removed           (G3d)
    test_stream_remove             # a removed stream stops                     (G3e)
    test_stream_freeze_thaw        # freeze/thaw a connection's streams          (G3f) -- C++ only

test_event — events (Section H) -- N/A for Lua, C-nano (no event support)
    test_event                     # OnTimer / OnTimerUsingLambda -> an Event   (H1a)
    test_custom_event              # event built client-side from an expression (H1b)
    test_event_wait                # wait until it fires                        (H2a)
    test_event_wait_timeout        # wait with a timeout                        (H2b)
    test_event_callbacks           # callback added, invoked on fire, removed   (H2c)

test_objects — remote-object representation (Section A9)
    test_object_equality           # two handles to one object compare equal    (A9)
    test_object_inequality         # handles to different objects differ
    test_object_hash               # hashable/orderable by identity

test_threading — thread safety (robustness)
    test_thread_safe_connection    # concurrent calls on one connection
    test_concurrent_streams        # streams update safely under load
```

**Layer 2 — codec round-trip** (no server) — pins the exact wire bytes for every Section-B type:

```text
test_encoder — value -> bytes, and framing
    test_encode_value              # each scalar/string/bytes to exact bytes
    test_encode_message            # a protobuf message
    test_encode_size_prefix        # length-delimited framing
    test_encode_object             # a remote-object handle
    test_encode_tuple_wrong_arity  # arity mismatch raises

test_decoder — bytes -> value, and framing
    test_decode_value
    test_decode_message
    test_decode_size_prefix
    test_decode_object
    test_decode_guid               # remote-object GUID

test_encodedecode — round-trip every Section-B type, asserting exact bytes both ways
    test_double test_float test_sint32 test_sint64 test_uint32 test_uint64 test_bool   # (B1a-g)
    test_string test_bytes                                                             # (B2, B3)
    test_enum test_object                                                              # (B4, B5)
    test_list test_set test_dictionary test_tuple test_nested                          # (B6-B10)
    test_object_list test_object_set test_object_dictionary test_object_tuple          # (B11a-d)
```

**Layer 3 — type system** (no server) — the type model behind A8/A9 and Section B:

```text
test_types
    test_value_types               # each value type constructs and coerces
    test_class_types               # remote-object handle type                  (A9)
    test_enumeration_types         # generated enum type and its members         (A8)
    test_message_types
    test_list_types test_set_types test_dictionary_types test_tuple_types
    test_none_type                 # the null/none representation
    test_coercion                  # a plain value/container -> its declared type
```

**Layer 4 — name & attribute parsing** (no server):

```text
test_attributes — classify a wire member and extract names
    test_is_procedure
    test_is_property_accessor / _getter / _setter
    test_is_class_member / _method / _static_method
    test_is_class_property_accessor / _getter / _setter
    test_get_service_name / test_get_class_name / test_get_member_name

test_name_conversion — wire name -> the client's convention (language-specific; e.g. snake_case)
    test_examples
    test_edge_cases
```

**Layer 5 — golden fixtures** (no comms) — where **Section I** and the documentation are verified,
by `//tools/krpctools:test` rather than a comms test (a dynamic client with no codegen, e.g. Lua,
has no clientgen fixture and so does not flag Section I):

```text
clientgen-TestService-<lang>       # the generated client, pinned verbatim
    - every member, its nullable (T? / optional / boxed) signature and default values
    - the deprecation marker for each deprecated kind:
        DeprecatedProcedure / ...NoMessage       (I1a, I1b)
        DeprecatedProperty                        (I2)
        DeprecatedClass / .DeprecatedMethod       (I3, I4)
        DeprecatedEnum / .ValueB                  (I5a, I5b)
        DeprecatedException                       (I6)
docgen-TestService-<lang>          # the generated documentation, pinned
    - the rendered <summary> for each documented member (service, procedure, property,
      class, method, class property, enum + members)
    - the deprecation notice on each deprecated member
```

A client that also signals deprecation at call time (e.g. Python's `DeprecationWarning`) or exposes
docs at runtime adds a small comms test for it; otherwise Section I needs no comms test:

```text
test_documentation                 # optional, language-dependent
    test_doc_string                # a member exposes its <summary>
    test_deprecation_signal        # calling a deprecated member warns          (I, runtime)
```

**Layer 6 — connection & transport** (TCP):

```text
test_connection — setup, teardown, framing
    test_connect / test_disconnect
    test_wrong_port / test_wrong_server         # a misconnection is detected
    test_send_receive / test_partial_receive    # message framing over the socket
    test_closed_connection                      # reads/writes on a closed connection fail cleanly

test_platform — language-specific byte/hex helpers (N/A where the platform provides them)
    test_byte_length test_hexlify test_unhexlify
```

A `test_performance` throughput benchmark may also exist; it is not part of conformance.

## Checklist for a new (or newly extended) client

Work through the [test layers](#test-layers):

1. **Golden fixtures (Layer 5)** — generate the client for `TestService`, add its fixture
   `clientgen-TestService-<lang>.txt`, and ensure `//tools/krpctools:test` passes. This also
   checks the Section-I deprecation markers and the generated documentation.
2. **Comms tests (Layer 1)** — wire up a test that launches `TestServer` (see an existing
   client's `BUILD.bazel` `client_test` target) and connects over the default transport, then
   **cover every rubric row (A–I)** that applies, using the members in the
   [TestService specification](#testservice-specification). Mark rows *N/A* only for genuine
   language/feature limits (no default-argument support, no streams, …), and say why. **Do not
   forget E5** (`ReturnNullWhenNotAllowed` → assert the client's RPC-error type) — the row most
   often missed.
3. **Codec round-trip unit tests (Layer 2)** — round-trip every Section-B type through the
   encoder/decoder in both directions, asserting the exact wire bytes, plus message framing/size
   and GUID decoding.
4. **Type-system and name-parsing unit tests (Layers 3–4)** — the type model and coercion rules,
   and the member-name conversion/classification.
5. **Connection & transport (Layer 6)** — connection setup and wrong-port/wrong-server handling.

(A new full client speaks protobuf over TCP; the `websockets`/`serialio` transport test-clients
are separate and only need the Layer 1 comms tests — no code generation, no full rubric.)

## Current coverage

Audit taken 2026-07-24. Legend: **✓** tested live · **◐** codec/unit-test only (no live
round-trip) · **✗** surface exists but untested (client gap) · **∅** no `TestService` surface
yet (needs a service addition — see the [TestService specification](#testservice-specification)) · **—** N/A
in this client, by design. Uniformly-covered leaf ids are collapsed into one row; rows with any
non-✓ cell are broken out. **Section B (types)** is identical across all clients — the same
`TestService` procedures and the same per-scalar codec unit tests everywhere — so it is broken
out by direction in the separate [type-coverage table](#type-coverage-section-b); this matrix
covers Sections A and C–H.

| Dimension (rubric ids) | Python | C# | C++ | Java | Lua | C-nano |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Member kinds & type representation (A1–A9) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Default arguments except bytes (C1a, C1b, C2a–e, C3, C4) | ✓ | ✓ | ✓ | — | ✓ | — |
| `bytes` default (C1c) | ∅ | ∅ | ∅ | — | ∅ | — |
| Partial arguments, procedure — trailing omission (C5a, procedure) | ✓ | ✓ | ✓ | — | ✗ | — |
| Partial/named on method & static method, and by-name (C5a method/static, C5b) | ✗ | ✗ | ✗ | — | ✗ | — |
| Nullable value/string/list/class args + rejection (D1, D2, D3a, D4, D5) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Nullable set / dict / tuple args (D3b–D3d) | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| Nullable value/string/list/class returns (E1, E2, E3a, E4) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Nullable set / dict / tuple returns (E3b–E3d) | ∅ | ∅ | ∅ | ∅ | ∅ | ∅ |
| Null return from non-nullable errors (E5) | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Void return (E6) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Nullable properties (F1a, F1b, F2) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Streams: members + delivery + lifecycle ex. freeze/thaw (G1a–e, G2a–b, G3a–e) | ✓ | ✓ | ✓ | ✓ | — | — |
| Stream freeze/thaw (G3f) | — | — | ✓ | — | — | — |
| Events (H1a–H2c) | ✓ | ✓ | ✓ | ✓ | — | — |
| Deprecation flagged (I1–I6) | ✓ | ✓ | ✓ | ✓ | — | ✓ |

By-design **—** cells: the Java and C-nano clients have no default-argument support (all
arguments are required, so both defaults and partial/named arguments C5 are N/A); the Lua and
C-nano clients have no stream or event support; freeze/thaw exists only in the C++ client API
(G3f); and the Lua client, being dynamic with no code generation, has no deprecation-flagging
mechanism (Section I). C5b (named / non-contiguous arguments) additionally needs named-argument
support, which only Python and C# have — it is N/A for C++ and Lua even though they support
trailing defaults.

### Type coverage (Section B)

Argument (`Ba…`) and return (`Bb…`) coverage per type. Identical across all six clients, so it
is shown once rather than per client. **✓** live round-trip · **◐** exercised only by codec unit
tests (no live procedure in that direction) · **∅** not exercised at all.

| Type | Argument (`Ba`) | Return (`Bb`) |
|---|:--:|:--:|
| `double` (1a) | ✓ | ◐ |
| `float` (1b) | ✓ | ◐ |
| `sint32` (1c) | ✓ | ✓ |
| `sint64` (1d) | ✓ | ◐ |
| `uint32` (1e) | ✓ | ◐ |
| `uint64` (1f) | ◐ | ◐ |
| `bool` (1g) | ✓ | ◐ |
| `string` (2) | ✓ | ✓ |
| `bytes` (3) | ✓ | ◐ |
| enumeration (4) | ✓ | ✓ |
| class object (5) | ✓ | ✓ |
| list of scalars (6) | ✓ | ✓ |
| set of scalars (7) | ✓ | ✓ |
| dictionary of scalars (8) | ✓ | ✓ |
| tuple of scalars (9) | ✓ | ✓ |
| nested collection (10) | ✓ | ✓ |
| list of objects (11a) | ✓ | ✓ |
| set of objects (11b) | ∅ | ∅ |
| dictionary of objects (11c) | ∅ | ∅ |
| tuple of objects (11d) | ∅ | ∅ |

The **◐ returns** are a surface limitation, not a client gap: no procedure returns a top-level
`float`/`double`/`sint64`/`uint32`/`uint64`/`bool`/`bytes`, so those decode paths run live only
as elements inside a returned collection or tuple (e.g. `sint64` inside `IncrementTuple`) and
directly only in codec unit tests. `uint64` has no live member in either direction. The **∅**
rows have no `TestService` member at all. See [surface gaps](#surface-gaps) and the
[TestService specification](#testservice-specification) for the additions that close these.

### Client gaps (surface exists — a client should add the test)

- **E5 — the one consistent client gap.** `TestService.ReturnNullWhenNotAllowed()` (a
  non-nullable procedure that returns null server-side) is exercised only by Python. C#, C++,
  Java, Lua and C-nano each have the generated stub but never call it to assert the client
  raises. It is the return-side mirror of D5, which every client covers. Fix per client:

  | Client | Test to add |
  |---|---|
  | C# | call `ReturnNullWhenNotAllowed()`, assert `RPCException` |
  | C++ | call `return_null_when_not_allowed()`, assert `krpc::RPCError` |
  | Java | call `returnNullWhenNotAllowed()`, assert `RPCException` |
  | Lua | call `return_null_when_not_allowed()`, assert an error is raised |
  | C-nano | call `krpc_TestService_ReturnNullWhenNotAllowed(...)`, assert `KRPC_ERROR_RPC_FAILED` |

- **Partial/named arguments (C5) — mostly untested outside Python.** C# and C++ test only trailing
  omission on the *service procedure* (`OptionalArguments`, C5a·procedure); Python additionally
  covers the instance method and the named / non-contiguous form (C5a·method, C5b). No client tests
  a class *static* method — that needs new surface (see below). Per client: C#, C++ and Lua should
  add C5a on the instance method (`TestClass.OptionalArguments` already exists); Python and C# should
  add C5b on both (C5b is N/A for C++/Lua — no named arguments); every default-capable client picks
  up the static-method cases once `StaticOptionalArguments` lands.

### Surface gaps (∅ — limits of `TestService` itself)

These affect every client equally: the service exposes no member to exercise them, so no client
can test them until it is extended (see the [TestService specification](#testservice-specification)).
<a id="surface-gaps"></a>

- **`uint64`/`ulong` never round-trips live** (`Ba1f`, `Bb1f`) — covered only by codec unit
  tests; no member takes or returns it.
- **No member returns `bytes`** (`Bb3`) — `bytes` is only ever an argument (`Ba3`, via
  `BytesToHexString`), so the bytes decode path runs live only in codec tests.
- **No parameter declares a `bytes` default** (C1c) — representable via `[KRPCDefaultValue]` (a
  `Create()` returning a `byte[]`), but no member uses one.
- **No class *static* method takes optional arguments** (C5 on a static method) — the instance
  `TestClass.OptionalArguments` and the service `OptionalArguments` exist, but no static equivalent,
  so partial/named argument passing cannot be tested on a static method. Closed by the proposed
  `TestClass.StaticOptionalArguments`.
- **Non-string scalar returns are untested live** (`Bb1a`, `Bb1b`, `Bb1d`, `Bb1e`, `Bb1f`,
  `Bb1g`) — no procedure returns a top-level `float`, `double`, `long`, `uint`, `ulong` or
  `bool`; only `sint32` (`Bb1c`) and `string` (`Bb2`) are returned live.
- **Object collections are list-only** — a list of objects exists (`Ba11a`/`Bb11a`), but no set,
  dictionary or tuple of class objects (11b–11d) in either direction.
- **Nullable collections are list-only** — only `EchoNullableList` exists, so nullable set,
  dictionary and tuple arguments/returns (D3b–D3d, E3b–E3d) are unexercised.
- **Nullable value types are `int?`-only** — `EchoNullableInt` is the sole nullable value-type
  member; `float?`, `bool?` and `TestEnum?` are unexercised (D1/E1). *Lower priority: these
  travel the same encoder/decoder path as `int?`, and nullable set/dict/tuple travel the same
  reference-type `is_null` path as the covered nullable list — the representatives already prove
  the mechanism. Add them for completeness, not because a distinct code path is untested.*

### Stream freeze/thaw parity (not a test gap)

Freeze/thaw is implemented and tested only in the C++ client (G3f). The Python, C#, and Java
clients do not expose it at all. This is a client-API parity question — decide whether the
asymmetry is intended before treating it as a gap.

## Open items

- **Close the E5 gap** in C#, C++, Java, Lua and C-nano (small, no service change). Highest
  value — it is the only place the surface exists but a client omits the test.
- **Land the consistency reorganization** — the `edit`/`remove` rows in the
  [change summary](#summary-of-proposed-changes): rename `EnumDefaultArg` → `EnumDefault`, break the
  `*Default` family out of `BlockingProcedure`/`OptionalArguments`, replace `EnumEcho`/`EnumReturn`
  with `EnumToString`/`StringToEnum`, and remove `AddMultipleValues` (the `OptionalArguments`
  members are kept, now as the C5 vehicles). No new coverage — pure surface cleanup; do it in the
  same pass as the additions so the fixtures regenerate and the client tests move once.
- **Add the higher-value `proposed` members** — `UInt32ToString`/`UInt64ToString` for the missing
  scalar arguments (`Ba1e`/`Ba1f`), the `StringTo<T>` family and `HexStringToBytes` for the
  non-string scalar and `bytes` returns (`Bb1a`/`Bb1b`/`Bb1d`–`Bb1g`, `Bb3`), and object
  set/dict/tuple (`Ba11b`–`Ba11d`/`Bb11b`–`Bb11d`) —
  then regenerate the golden fixtures and add a round-trip test per client.
- **Cover partial/named arguments (C5)** — add `TestClass.StaticOptionalArguments`, then test C5a
  (and C5b where the client has named arguments) on the service procedure, the instance method and
  the static method individually. Mostly a client-test gap today: only Python exercises the method
  and named/non-contiguous forms; C#/C++ cover just the procedure's trailing omission.
- **Add the completeness `proposed` members** — nullable set/dict/tuple (D3b–D3d, E3b–E3d), the
  other nullable scalars/enum (D1/E1), and a `bytes` default (C1c) — if we want every leaf id
  green; lower priority since they re-exercise paths the existing representatives already prove.
- **Decide stream freeze/thaw parity** — expose it in all stream-capable clients or remove it
  from C++ — then align the tests (G3f) to that decision.
