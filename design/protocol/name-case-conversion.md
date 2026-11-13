# Name case conversion

**Status:** phases 1 and 2 done, on a local branch.

Clients and generators convert the names in a service definition, such as `ActiveVessel`, to their
own case: `active_vessel`, `activeVessel`, `ACTIVE_VESSEL`. [Client naming](client-naming.md) says
which case each client uses for each kind of name. This doc specifies how each conversion splits a
name into words, so every implementation gives the same, readable result.

Today there is no specification. There are six algorithms, and some give names no person would
write:

| Name | Today | Where |
| --- | --- | --- |
| `UInt64ToString` | `u_int64_to_string`, `uInt64ToString` | Python, Lua, C++; Java, JavaScript |
| `FoV` | `fo_v` | Python, Lua, C++ |
| `EVAs` | `ev_as`, `E_V_AS` | Python, Lua, C++; Java |
| `MSLNormal` | `mSLNormal` | Java |
| `RCSThrust` (field) | `rCSThrust` | Java, C# constructor parameters |
| `DEFAULT`, `AGL`, `SOIChange` (enum values) | `D_EFAULT`, `A_GL`, `S_OI_CHANGE` | Java. The Java docs show `DEFAULT`, `AGL`, `SOI_CHANGE` |

## Goals

- Each case style has one specified algorithm.
- Every implementation follows it, and tests it against shared test vectors. A client that builds
  its services at run time (Python, Lua, JavaScript) needs its own implementation, so there is no
  single implementation to share.
- The result reads as a person would write it, and is still derived from the C# name alone:
  `MyUInt64` is `my_uint64`, and `IsValidUTF8` is `is_valid_utf8`.

## Implementations today

| Implementation | Algorithm | Style | Used for |
| --- | --- | --- | --- |
| `client/python/krpc/utils.py` `snake_case` | Three regexes: double each `_`; `_` between a lower case letter or digit and a capital; `_` before the last capital of a run followed by a lower case letter or digit | snake | Python runtime, conformance driver, clientgen and docgen for Python, C++ and C-nano |
| `client/lua/krpc/service.lua` `to_snake_case` | Copy of the Python one | snake | Lua runtime |
| `tools/krpctools/clientgen.bzl` `_snake_case` | Starlark copy of the Python one | snake | C++ and C-nano header file names |
| `tools/krpctools/krpctools/utils.py` `lower_camel_case` | Lower cases the first letter only | lowerCamel | Java members, parameters, fields; C# constructor parameters |
| `tools/krpctools/krpctools/lang/java.py` `parse_const_name` | `snake_case(lower_camel_case(name)).upper()` | UPPER_SNAKE | Java enumeration constants. Java docgen uses `snake_case(name).upper()`, so the docs disagree with the code |
| `client/js/src/naming.ts` `camelCase` (JavaScript client branch) | Lower cases the leading run of capitals, less its last capital when a lower case letter follows. Copied in `lang/js.py` and the conformance driver | lowerCamel | JavaScript |
| `core/src/Service/TypeUtils.cs` | `_` between a lower case and an upper case letter, upper cased | UPPER_SNAKE | Type codes of protobuf message types, e.g. `PROCEDURE_CALL` |
| `experimental/ksa/grpc/protogen.py` `snake_case`, `upper_snake_case` | Own regexes, no acronym rule in `snake_case` | snake, UPPER_SNAKE | KSA gRPC protos |
| `str.lower()`, `str.upper()` in krpctools templates | No word split | lower, UPPER | Python module names, C-nano macros and enumeration constants |

No implementation has unit tests. The conformance suite checks the snake case of a table of names
(`NAMES` in `client/conformance/tests/test_calls.py`) through the Python and Lua testees.

## Specification

### Input

A name is a service, type, member, enumeration value, field or parameter name. The
[identifier rule](service-definition-rules.md#identifiers) limits it to letters and digits, starting
with a letter. A server that breaks the rule can still send a `_`, so the specification covers it:
the name is split at each `_`, each part is converted on its own, and the parts are joined as
[Styles](#styles) says.

### Words

A part is split into words from left to right. At each position, the first of these rules that
matches gives the next word:

| Rule | Matches | Examples |
| --- | --- | --- |
| 1. Compound word | A word from the [compound word list](#compound-words), not followed by a lower case letter | `UInt`64, Max`FoV` |
| 2. Plural acronym | Two or more capitals and an `s`, not followed by a lower case letter | `EVAs`, `IDs` |
| 3. Acronym | The longest run of capitals not followed by a lower case letter | `RCS`Thrust, `SAS`Mode, Mean Anomaly At `UT`, `DEFAULT` |
| 4. Word | An optional capital, then lower case letters | `Active` `Vessel`, `reset`PID |
| 5. Number | Digits, and the acronym after them by rule 3, if there is one | `32` To String, Vector `3D`, Get `2D` Position |
| 6. Other | Any other character, so a name outside the identifier rule loses no character | |

Rules 1 to 4 also take the digits that follow the word, unless an acronym follows the digits:
`UInt64`, `UTF8`, `Atan2`, `Axis01`, `Int32`, `UTF8`String. Digits followed by an acronym are a word
of their own by rule 5: `Vector3D` is `vector_3d`, and `Get2DPosition` is `get_2d_position`.

Rule 3 ends a run of capitals before its last capital when a lower case letter follows, as
that capital starts the next word: `RCSThrust` is `RCS`, `Thrust`.

As a regular expression, tried at each position in turn, where `D` stands for
`(?:[0-9]+(?![0-9])(?![A-Z]+(?![a-z])))?`, the digits a word takes:

```
(?:UInt|ULong|SInt|FoV)(?![a-z])D
|[A-Z]{2,}s(?![a-z])D
|[A-Z]+(?![a-z])D
|[A-Z]?[a-z]+D
|[0-9]+(?:[A-Z]+(?![a-z]))?
|.
```

The words joined give back the part. A conversion only changes case and inserts separators, so
two names that convert to one client name differ only in case. The
[service definition rules](service-definition-rules.md#identifiers) rely on this to rule out
clashes.

### Compound words

A compound word is a word that is written with more than one capital and that rules 2 to 4 would
split. The list is part of the specification, and every implementation holds the same list.

| Word | Meaning | Without it |
| --- | --- | --- |
| `UInt` | Unsigned integer | `u_int` |
| `ULong` | Unsigned long | `u_long` |
| `SInt` | Signed integer, the protobuf type | `s_int32` |
| `FoV` | Field of view | `fo_v` |

A service author who needs a new compound word adds it here and to every implementation, with a
test vector.

### Styles

| Style | From the words | Example: `UInt64ToString`, `RCSThrust`, `EVAs` | Parts joined by |
| --- | --- | --- | --- |
| snake | Lower case, joined by `_` | `uint64_to_string`, `rcs_thrust`, `evas` | `__` |
| UPPER_SNAKE | Upper case, joined by `_` | `UINT64_TO_STRING`, `RCS_THRUST`, `EVAS` | `__` |
| lowerCamel | The first word lower case, the others as written | `uint64ToString`, `rcsThrust`, `evas` | `_` |
| UpperCamel | The name unchanged | `UInt64ToString`, `RCSThrust`, `EVAs` | `_` |
| lower | The name lower case, no words | `uint64tostring` | `_` |
| UPPER | The name upper case, no words | `UINT64TOSTRING` | `_` |

- **lowerCamel keeps later words as written,** so acronyms stay in capitals: `meanAnomalyAtUT`,
  `isValidUTF8`. This keeps every Java and JavaScript name whose first word is not an acronym as it
  is today. The alternative, capitalizing only the first letter of each word (`meanAnomalyAtUt`),
  would rename far more and depart from the C# names.
- **A property accessor** is `get` or `set` and the UpperCamel name: `getRCSThrust`, `setSASMode`. Java builds it from the server's name, not from the lowerCamel member name, which would give `getRcsThrust`.
- **lower and UPPER need no words.** C-nano macros join several names with `_`, as in
  `KRPC_SPACECENTER_SASMODE_STABILITYASSIST`. UPPER_SNAKE there would make enumeration `FooBar`
  value `Baz` and enumeration `Foo` value `BarBaz` both `FOO_BAR_BAZ`.
- **Keyword escaping and helper names** come after the conversion, as [client
  naming](client-naming.md#the-contract) says.

### Which style each client uses

[Client naming](client-naming.md#mappings) gives an example of each name. This table gives the style:

| Name | C# | C++ | C-nano | Java | Python | Lua | JavaScript |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Service | UpperCamel | UpperCamel | UpperCamel, in function and type prefixes | UpperCamel | snake attribute, lower module | snake | lowerCamel |
| Service, in a file name | | snake header | snake header | | | | |
| Type | UpperCamel | UpperCamel | UpperCamel | UpperCamel | UpperCamel | UpperCamel | UpperCamel |
| Procedure or method | UpperCamel | snake | UpperCamel | lowerCamel | snake | snake | lowerCamel |
| Property | UpperCamel | snake, `set_` and snake | UpperCamel, `set_` and UpperCamel | accessors | snake | snake, stored as `get_` and `set_` and snake | accessors |
| Enumeration value | UpperCamel | snake | UPPER, in a macro | UPPER_SNAKE | snake | snake | lowerCamel |
| Structure field | UpperCamel, lowerCamel constructor parameter | snake | snake | lowerCamel, `get` and UpperCamel | snake | snake | lowerCamel |
| Parameter | As written | snake | As written | lowerCamel | snake | snake | lowerCamel |
| Exception | UpperCamel | UpperCamel | UPPER, in a macro | UpperCamel | UpperCamel | UpperCamel | UpperCamel |

A C-nano macro joins its names with `_`, as in `KRPC_SPACECENTER_SASMODE_STABILITYASSIST` and
`KRPC_EXCEPTION_KRPC_ARGUMENTEXCEPTION`. The server gives each protobuf message type an
UPPER_SNAKE type code, e.g. `PROCEDURE_CALL`.

Three implementations change to follow the table:

- **Java** enumeration constants are UPPER_SNAKE of the name, in place of UPPER_SNAKE of its
  lowerCamel form.
- **C#** structure constructor parameters are lowerCamel by this specification.
- **Server** `TypeUtils` type codes are UPPER_SNAKE by this specification. Every message type name
  gives the same code as today.

## Tests

- **Test vectors.** One file, `client/conformance/names.json`, holds names and their form in each
  style that splits words: snake, UPPER_SNAKE and lowerCamel. It covers every rule, the compound words, `_` parts and leading digits. The `NAMES` table in
  `test_calls.py` moves into it.
- **Runtime clients** (Python, Lua, JavaScript) are checked by the conformance suite, as `NAMES` is
  today. A scripted server defines members and enumeration values named after the vectors, and the
  test checks the names the client exposes.
- **Implementations without a testee** test themselves against the same file:
  - krpctools `snake_case`, `lower_camel_case` and the Java constant names, in a Python unit test;
  - `clientgen.bzl`, in a Starlark unit test, or by replacing it with names krpctools writes;
  - `TypeUtils`, in a `//core:test` case.
- **Every bundled name.** A krpctools test converts every name in the bundled service definitions
  to each style and compares the result with a checked-in golden file. A new RPC then shows its
  client names in the pull request diff, where a reviewer can spot one that reads badly.

## Audit

The rules applied to every name in the service definitions built in this repository: the core
`KRPC` and `StdLib` services, the bundled services and the `TestServer` services. This is 2196
distinct names. Two sets of names are left out:

- **MechJeb.** Its names came from another author, and a later renaming pass will bring them to the
  conventions of the other services, e.g. `CourseCorrectFinalPeA` to spell out the periapsis
  altitude. Its names convert by these rules meanwhile, as `course_correct_final_pe_a`.
- **The KSA services.** They build against the released core, and follow when they move to a 0.8
  core.

### Names that change

snake, in Python, Lua and C++; UPPER_SNAKE follows in Java:

| Name | Today | Proposed | Kind |
| --- | --- | --- | --- |
| `UInt`, `ULong` | `u_int`, `u_long` | `uint`, `ulong` | `KRPC.Type` static methods |
| `ConstantUInt`, `ConstantULong` | `constant_u_int`, `constant_u_long` | `constant_uint`, `constant_ulong` | `KRPC.Expression` static methods |
| `UInt32`, `UInt64`, `SInt32`, `SInt64` | `u_int32`, `u_int64`, `s_int32`, `s_int64` | `uint32`, `uint64`, `sint32`, `sint64` | `KRPC.TypeCode` values |
| `FoV`, `MinFoV`, `MaxFoV`, `DefaultFoV` | `fo_v`, `min_fo_v`, `max_fo_v`, `default_fo_v` | `fov`, `min_fov`, `max_fov`, `default_fov` | `SpaceCenter.Camera`, `RasterPropMonitor` properties |
| `EVAs` | `ev_as` | `evas` | `SpaceCenter.MapFilterType` value |
| `UInt32ToString`, `UInt64ToString`, `StringToUInt32`, `StringToUInt64`, `EchoNullableUInt`, `EchoNullableULong` | `u_int32_to_string`, ... | `uint32_to_string`, ... | `TestService` only |

lowerCamel, in Java members, parameters and fields, and C# constructor parameters:

| Name | Today | Proposed | Kind |
| --- | --- | --- | --- |
| `MSLNormal`, `MSLPosition`, `UTAtTrueAnomaly`, `EVA` | `mSLNormal`, `mSLPosition`, `uTAtTrueAnomaly`, `eVA` | `mslNormal`, `mslPosition`, `utAtTrueAnomaly`, `eva` | `SpaceCenter` and `Drawing` methods |
| `UInt`, `ULong` | `uInt`, `uLong` | `uint`, `ulong` | `KRPC.Type` static methods |
| `UT`, `TWR` | `uT`, `tWR` | `ut`, `twr` | `SpaceCenter`, `KerbalEngineerRedux` structure fields |
| `RCSThrust`, `RCSBurnTime`, `RCSSpecificImpulse`, `RCSStartDeltaV`, `RCSEndDeltaV`, `RCSStartTWR`, `RCSEndTWR` | `rCSThrust`, ... | `rcsThrust`, ... | `KerbalEngineerRedux` structure fields |
| `UInt32ToString`, `UInt64ToString` | `uInt32ToString`, `uInt64ToString` | `uint32ToString`, `uint64ToString` | `TestService` only |

UPPER_SNAKE, in Java enumeration constants. All of these are bugs today, and the proposed names
match the Java docs:

| Today | Proposed |
| --- | --- |
| `A_GL`, `A_SL`, `D_EFAULT` | `AGL`, `ASL`, `DEFAULT` |
| `E_VA`, `I_VA`, `E_V_AS` | `EVA`, `IVA`, `EVAS` |
| `J_PEG`, `P_NG` | `JPEG`, `PNG` |
| `K_SC`, `S_PH`, `V_AB` | `KSC`, `SPH`, `VAB` |
| `S_OI_CHANGE`, `S_OI_CHANGE_AUTO` | `SOI_CHANGE`, `SOI_CHANGE_AUTO` |
| `U_INT32`, `U_INT64`, `S_INT32`, `S_INT64` | `UINT32`, `UINT64`, `SINT32`, `SINT64` |

JavaScript, not yet released: `evAs`, `uInt`, `uLong`, `uInt32`, `uInt64`, `sInt32`, `sInt64`
become `evas`, `uint`, `ulong`, `uint32`, `uint64`, `sint32`, `sint64`.

C-nano and C# member names do not change.

### Names that stay, and read as written

Every other name converts as before. A sample of the harder ones:

| Name | snake | lowerCamel |
| --- | --- | --- |
| `SASMode`, `RCSThrust` | `sas_mode`, `rcs_thrust` | `sasMode`, `rcsThrust` |
| `MeanAnomalyAtUT`, `TrueAnomalyAtAN` | `mean_anomaly_at_ut`, `true_anomaly_at_an` | `meanAnomalyAtUT`, `trueAnomalyAtAN` |
| `APIReady`, `IKActive`, `UIVisible` | `api_ready`, `ik_active`, `ui_visible` | `apiReady`, `ikActive`, `uiVisible` |
| `ColorRGBA`, `ValueAB`, `KavrayskiyVII` | `color_rgba`, `value_ab`, `kavrayskiy_vii` | `colorRGBA`, `valueAB`, `kavrayskiyVII` |
| `GForce`, `EchoTupleWithANullableObject` | `g_force`, `echo_tuple_with_a_nullable_object` | `gForce`, `echoTupleWithANullableObject` |
| `DeltaVAltitude`, `AltimetryHiRes` | `delta_v_altitude`, `altimetry_hi_res` | `deltaVAltitude`, `altimetryHiRes` |
| `Atan2`, `Log10`, `CustomAxis01`, `Uint32SpecialDefaults` | `atan2`, `log10`, `custom_axis01`, `uint32_special_defaults` | `atan2`, `log10`, `customAxis01`, `uint32SpecialDefaults` |
| `resetPID` (parameter), `DEFAULT` | `reset_pid`, `default` | `resetPID`, `default` |

## Compatibility

The renames above break the Python, Lua, C++ and Java names they touch. They go in 0.8 with no
deprecated aliases, under the 0.8 clean break. Outside the `TestServer` services, they are 13 snake names and
32 Java names. Wire names do not change, as they are the C# names. The changelog lists them under
each client. No page in `doc/src` names an old form.

## Phases

1. **Specification and test vectors**: the specification on the docs site, in
   `doc/src/client-design.rst`, with a short note for service authors in `doc/src/extending/`;
   `names.json`; the conformance test reading it.
2. **Python, Lua and krpctools**: `snake_case`, `to_snake_case`, `clientgen.bzl`, `lower_camel_case`
   and the Java constant names, with their unit tests and the regenerated goldens. One pull request,
   as the conformance driver uses the Python implementation.
3. **Server**: `TypeUtils` type codes, with a `//core:test` case.
4. **Every bundled name**: the golden file of the converted names, and its test.
5. **JavaScript**: `naming.ts` and its two copies. The JavaScript client branch rebases onto
   phase 4 and takes this change before it is submitted.

Phases 1 and 2 can be one pull request.
