# TestService and ConformanceService

The game-less server surface the suite calls. `TestService` (`tools/TestServer/src/TestService.cs`,
id 9999) stays the surface for calls and values. A new `ConformanceService` adds the control
`TestService` lacks. Surveyed on the single connection branch.

## Testing values

Each member uses the strongest pattern its type allows:

| Pattern | Used for | Why |
| --- | --- | --- |
| **Conversion**: `<T>ToString`, `StringTo<T>` | Scalars, bytes, enums | An independent representation. A symmetric encoder and decoder bug cannot pass. |
| **Transform**: `Increment...`, `AddTo...`, `Swap...` | Collections | The server decodes and changes every element, so the elements arrived. |
| **Echo**: `Echo...`, `...Default` | Nullables, handles, defaults | The test is of a mechanism: the null encoding, handle identity, default application. The codec vectors pin the value encoding. |

## Current surface

| Group | Members | Spec |
| --- | --- | --- |
| Scalar arguments | `FloatToString`, `DoubleToString`, `Int32ToString`, `Int64ToString`, `BoolToString`, `BytesToHexString` | `values-scalar-arguments`, `values-bytes` |
| Scalar returns | `StringToInt32` only | `values-scalar-returns` |
| Properties | `StringProperty`, `StringPropertyPrivateGet`, `StringPropertyPrivateSet`, `ObjectProperty` (nullable), `NullableObject` (setter rejects null) | `calls-service-property`, `errors-guarded-nullable-property` |
| Objects | `CreateTestObject`, `EchoTestObject`, `NotNullableObject`, `ReturnNullWhenNotAllowed` | `values-nullable-object`, `errors-null-argument-rejected`, `errors-null-return-rejected` |
| `TestClass` | `GetValue`, `FloatToString`, `ObjectToString`, `EchoNullableObject`, `OptionalArguments`, `IntProperty`, `ObjectProperty`, asymmetric string properties; static `StaticMethod(a="", b="")`, `StaticNullableObject` | `calls-class-*` |
| Extensions | `TestServiceExtensions`: `ExtensionMethod`, `ExtensionMethodReturningClassFromOtherService` (returns `TestService2.TestClass2`), `ExtensionProperty`, `ExtensionReadWriteProperty` | `calls-extension-members`, `streams-extension-member` |
| Arguments | `OptionalArguments(x, y="foo", z="bar", obj=null)`, `AddMultipleValues(float, int, long)` | `calls-partial-arguments`, `calls-named-arguments` |
| Enums | `TestEnum {ValueA, ValueB, ValueC}`, `EnumReturn`, `EnumEcho`, `EnumDefaultArg(x=ValueC)` | `values-enums`, `calls-enum-default` |
| Nullables | `EchoNullableInt`, `EchoNullableString`, `EchoNullableList` | `values-nullable-*` |
| Structs | `TestStruct`, `TestNestedStruct`, `TestNullableStruct`, `TestNestedNullableStruct`; `StructEcho`, `NullableStructEcho`, `NestedStructEcho`, `IncrementListOfStructs`, `StructDefault`, `StructEchoNullable`, `CounterStruct` | `values-structs`, `values-nullable-struct-fields`, `calls-struct-default`, `streams-struct-value` |
| Nullable positions | `EchoNestedNullableStruct`, `EchoListOfNullableInts`, `EchoListOfNullableObjects`, `EchoDictionaryOfNullableObjects`, `EchoTupleWithANullableObject`, `EchoNestedListOfNullableObjects` | `values-nullable-elements` |
| Collections | `IncrementList`, `IncrementSet`, `IncrementDictionary`, `IncrementTuple`, `IncrementNestedCollection`, `AddToObjectList` | `values-collections`, `values-nested-collections`, `values-collections-of-objects` |
| Defaults | `ListDefault`, `SetDefault`, `DictionaryDefault`, `TupleDefault`, `EnumListDefault`, `EmptyListDefault` | `calls-collection-defaults` |
| Special defaults | `DoubleSpecialDefaults`, `FloatSpecialDefaults` (with a finite `0.1f`), `Int32SpecialDefaults`, `Int64SpecialDefaults`, `Uint32SpecialDefaults`, `Uint64SpecialDefaults` | `calls-special-defaults` |
| Exceptions | `ThrowArgumentException`, `ThrowInvalidOperationException`, `ThrowArgumentNullException`, `ThrowArgumentOutOfRangeException`, `ThrowCustomException`, `CustomException`; `Throw...Later` and `Reset...Later` for InvalidOperation and Custom | `errors-*`, `streams-exception-*` |
| Blocking | `BlockingProcedure(n, sum=0)`, by `YieldException` | `calls-blocking-procedure`, `streams-yield-exception` |
| Streams | `Counter(id="", divisor=1)`, counted per client | `streams-*` |
| Events | `OnTimer(ms, repeats=1)`, `OnTimerUsingLambda(ms)`, `RemoveEventAfter(ms)` | `events-*` |
| Functions | `DumpExpressionTree(Expression)` | builder tests, per client |
| Deprecation | `DeprecatedProcedure`, `DeprecatedProcedureNoMessage`, `DeprecatedProperty`, `DeprecatedClass.DeprecatedMethod`, `DeprecatedEnum.ValueB`, `DeprecatedStruct.OldValue`, `DeprecatedException` | goldens, `calls-deprecated-procedure-warns` |

Doc summaries on one member of each kind exist for the docgen goldens only.

## Changes

**Additions**, with the C3 and C4 tests that need them:

| Members | Closes |
| --- | --- |
| `UInt32ToString`, `UInt64ToString` | `values-scalar-arguments[uint32, uint64]`, today exercised only inside collections and special defaults |
| `StringToDouble`, `StringToFloat`, `StringToInt64`, `StringToUInt32`, `StringToUInt64`, `StringToBool`, `HexStringToBytes` | `values-scalar-returns`, `values-bytes`. No procedure returns these types at the top level |
| `EnumToString`, `StringToEnum` | `values-enums` by conversion |
| `AddToObjectSet`, `AddToObjectDictionary`, `SwapObjectTuple` | `values-collections-of-objects` beyond lists |
| `EchoNullableFloat`, `EchoNullableBool`, `EchoNullableEnum`, `EchoNullableSet`, `EchoNullableDictionary`, `EchoNullableTuple` | `values-nullable-*`. Low priority: the same paths as the covered int and list |
| `ScalarDefault(x=42)`, `StringDefault(x="foo")`, `BytesDefault`, `NullDefault(obj=null)` | `calls-scalar-defaults`, `calls-null-default`, one owner each |
| `TestClass.StaticOptionalArguments` | `calls-partial-arguments` and `calls-named-arguments` on a static method |
| `RemoveTestObject(obj)` | `errors-krpc-exceptions`: removes the object from the object store, so a later call on it raises `ObjectDestroyedException`. Added in C3 |

**In C6**, once the per-client comms tests are gone:

| Change | Why |
| --- | --- |
| `EnumDefaultArg` to `EnumDefault` | The `...Default` family's naming |
| Remove `EnumEcho`, `EnumReturn` | Replaced by the conversion pair |
| Remove `AddMultipleValues` | Argument order is covered by `OptionalArguments`, the types by the conversions |
| `BlockingProcedure` keeps `sum=0` | No longer counted as a defaults test |

## Invalid object ids

`errors-invalid-object-id` needs a handle the server never issued. Every generated handle type
allows one, e.g. Python `conn.test_service.TestClass(conn, 1000000)` or cnano
`krpc_TestService_TestClass_t obj = 1000000`. Pick an id far above any issued: ids are never
reused, so one below the next to be issued reads as destroyed (`ObjectDestroyedException`), not
unknown (`ArgumentException`). The destroyed case needs the game and is tested in
`service/SpaceCenter/test/test_object_lifetime.py`.

## ConformanceService

A new TestServer service with its own servicedefs JSON, so testees get stubs. `TestService` stays
the call and value surface. `ConformanceService` is driven by the `control` connection.

| Member | For |
| --- | --- |
| `TriggerEvent(id)`, `RemoveEvent(id)`, `CreateEvent() -> Event` | Firings and server-side endings on demand, in place of timers |
| `SetValue(name, value)`, `Value(name)` | A settable watched value to stream, so a test controls each update |
| `Block(ms)` | A call that holds its response for a set time, for interleaving and abandonment |
| `DisconnectClient(name, reason)` | A server-side `disconnect` with a given reason, to the client with that name. Each test connects with a unique client name, as no client exposes its server id |
| `FailValue(name, exception)` | Makes `Value(name)` throw a chosen exception, so a stream of it ends on demand |

The scripted server covers the wire cases this service cannot: malformed messages, unknown cases,
wrong-direction messages and stalls.
