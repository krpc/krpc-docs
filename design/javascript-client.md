# JavaScript client for the browser

**Status:** in progress. Phases 1 to 6 are complete and implemented locally, with flags
enumerations, deprecation signals and a web browser control panel tutorial. Phase 7, the rest of
the 0.8 work, is in progress: links in the server forms and npm publishing are done, also local.
A first Windows CI run and the submission remain. The later phases are not scheduled. The
client's current design is on the docs site, in `doc/src/client-design/js.rst`, and the "as
built" sections below record how each phase landed.

## Goal

An official JavaScript client, published to npm under `@krpc-org`. Its target is the browser:
telemetry dashboards, mission control pages and other web tools. Node.js runs the same code, as
Node 22 has a global `WebSocket`.

It is the first official client on the [WebSockets protocol](https://krpc.github.io/krpc/communication-protocols/websockets.html).
A browser cannot open a raw TCP socket, so WebSockets is the one transport. Today the
`client/websockets` conformance testee covers the protocol, with no client API on top.

## Prior art

Third-party clients exist. Neither is maintained, and neither works with the 0.8 protocol:

| Client | Runtimes | Last update |
| --- | --- | --- |
| [eXigentCoder/krpc-node](https://github.com/eXigentCoder/krpc-node), npm `krpc-node` | Node.js | January 2023 |
| [lucaelin/krpc.js](https://github.com/lucaelin/krpc.js) | Node.js, browser build | December 2022 |

Both use separate RPC and stream connections, which the single connection (#1174) replaced. The
krpc-node author supports an official replacement. Once it ships, the krpc-node README points to
it, and `doc/src/third-party.rst` drops the krpc-node link.

## Decisions

### Language: TypeScript

The browser shapes the output, not the source language. The package ships ES modules either way,
compiled from source by `tsc`. The browser target sets these constraints on the library code:

- ES modules only, no CommonJS build.
- No Node.js built-ins: no `Buffer`, `net` or `events`. Bytes are `Uint8Array` and `DataView`,
  strings go through `TextEncoder` and `TextDecoder`.
- The global `WebSocket`, with `binaryType = "arraybuffer"`.
- No `eval` or `new Function`, so a page with a strict Content Security Policy can load it.

Given that, write it in TypeScript:

- `.d.ts` files come from the source, with no hand-kept copy to drift.
- The stubs phase generates TypeScript declarations, so the types of the core must exist anyway.
- The library's `tsconfig` sets `lib: ["ES2022", "DOM"]` and leaves out `@types/node`. A Node
  built-in used by mistake then fails the type check, which stands in for a browser test in
  phase 1.

### Protobuf library: `@bufbuild/protobuf`

The client needs protobuf twice. It decodes and encodes the messages in `krpc.proto`, and it
encodes argument and result values as protobuf wire scalars (varints, zigzag, fixed, length
delimited).

| | `@bufbuild/protobuf` (v2) | `protobufjs` |
| --- | --- | --- |
| 64-bit integers | `bigint` | `Long` objects, an extra dependency |
| Runtime code generation | none | `new Function` in the full build; CSP needs `unsafe-eval` |
| Module format | ES modules, tree-shakable | CommonJS first |
| Wire-level API for values | `BinaryReader`, `BinaryWriter` | `Reader`, `Writer` |
| Conformance | passes the protobuf conformance suite | partial |
| Messages from `krpc.proto` | `protoc-gen-es` at build time, or a descriptor at run time | `pbjs` static code, or reflection |

Use `@bufbuild/protobuf`. `bigint` decides it: a `uint64` above 2^53 round-trips, where the Lua
client fails `test_integers[uint64]`. The `BinaryReader` and `BinaryWriter` cover the value codec,
so the client has no hand-written varint code.

The `krpc.proto` messages come from `protoc-gen-es`, run in Bazel against `//protobuf`. The output
is a build product, not committed. The protocol examples in
`doc/src/scripts/communication-protocols/websockets/` keep `protobufjs`, as they show the protocol
and not this client.

### Packaging: one package

One client for every runtime. The runtimes differ only in transport, and two clients would mean
two codecs, two testees and two expected failure lists. The Node transports sit at a subpath
export:

```js
import { connect } from "@krpc-org/krpc";               // WebSockets, every runtime
import { tcp, localSocket } from "@krpc-org/krpc/node"; // imports node:net

const conn = await connect({ transport: tcp({ address: "127.0.0.1", port: 50000 }) });
```

- A browser bundle pulls in `node:net` only when a page imports `/node`.
- `node:net` covers TCP and Unix sockets, so the Node transports add no dependency.
- One set of type declarations for every runtime. Conditional exports, a build per runtime under
  one import, are not used.
- A separate `@krpc-org/krpc-node` package only if a transport ever needs a heavy dependency. The
  transport sits behind an interface, so that split moves files and changes no API.

Until the Node transports land, a Node user adds a WebSockets server in the kRPC server window, as
the default server is TCP. The client guide says so.

## Phases

Each phase is implementable and mergeable on its own. Phases 1 to 7 ship in 0.8. The later
phases are not scheduled, and the release plan lists them as one item.

| Phase | Adds | Conformance profiles | Release |
| --- | --- | --- | --- |
| 1 | Browser, WebSockets, unary calls, dynamic stubs | `core`, `dynamic`, `defaults`, `connections`, `concurrency`, `websockets` | 0.8 |
| 2 | Error types, named arguments. Structures become classes | `error-types`, `named-arguments` | 0.8 |
| 3 | Generated stubs with TypeScript declarations, docs API reference | — | 0.8 |
| 3b | Enumerations, structures and exceptions importable with no connection | — | 0.8 |
| 4 | Streams, events, callbacks | `streams`, `events`, `callbacks` | 0.8 |
| 5 | Server side functions built with the `KRPC.Expression` API: streams, events and runs | `functions` | 0.8 |
| 6 | A compiler from JavaScript functions to server side functions, in three steps | — | 0.8 |
| 7 | Release: links in the server forms, npm publishing, a first Windows CI run, phases 1 to 7 submitted as PRs | — | 0.8 |
| later | Browser test runs: a headless browser in Bazel | — | Not scheduled |
| later | Server: pages served by the mod, an origin check | — | Not scheduled |
| later | Server: TLS (`wss://`), with a user's certificate or a generated one | — | Not scheduled |
| later | Node.js transports (TCP, local socket) at `@krpc-org/krpc/node`, after checking the local socket on Windows | `tcpip`, `localsocket` | Not scheduled |
| later | Benchmarks: a JavaScript client in `//tools/benchmarks`, as each other client has | — | Not scheduled |

`races` and `ordering` stay out: see [Concurrency](#concurrency), and JavaScript has no ordering
of objects.

### Phase 1: browser, WebSockets, unary calls

The Lua client's feature set, on WebSockets:

- Connect with the handshake, then `KRPC.GetServices`, and build the services at run time.
- Unary request and response calls. No streams, events or batched calls.
- Every value type, nullable values, objects, structs, default arguments.
- Several connections open at once, sharing objects.
- Close with a disconnect and a close frame.
- `ws://` only, from a page served over `http://` or opened as a local file. No TLS.

The first step deletes `client/websockets/`. The JavaScript testee replaces it as the conformance
coverage of the WebSockets protocol.

#### API

Every call returns a `Promise`. The browser has no blocking call, so the client is asynchronous
throughout:

```js
import { connect } from "@krpc-org/krpc";

const conn = await connect({ name: "Dashboard", address: "127.0.0.1", port: 50000 });
const vessel = await conn.spaceCenter.getActiveVessel();
console.log(await vessel.getName());
const control = await vessel.getControl();
await control.setThrottle(1);
await conn.close();
```

| Item | Form |
| --- | --- |
| Services, members | camelCase: `conn.spaceCenter`, `vessel.getFlight()`, as Python's `conn.space_center` |
| Classes, enumerations | PascalCase: `conn.spaceCenter.VesselSituation.orbiting` |
| Properties | `getX()` and `setX(value)` methods, both returning a `Promise` |
| `sint32`, `uint32`, `float`, `double` | `number` |
| `sint64`, `uint64` | `bigint` results; arguments take `number` or `bigint` |
| `bytes` | `Uint8Array` |
| list, tuple | `Array` |
| set, dictionary | `Set`, `Map` |
| struct | a plain object with the struct's fields, frozen |
| null | `null` |

Properties are methods because a JavaScript setter cannot return a `Promise`. `vessel.name = "x"`
would drop the server's error, and leave the caller no way to wait for the call. A getter
returning a `Promise` alone (`await vessel.name`) reads well, but pairs badly with a setter method.

#### Concurrency

The client runs on one thread, and Web Workers cannot share a `WebSocket`. Several calls may still
be in flight at once. Each request carries its id (#1174), and the client matches each response to
its `Promise` by id.

- **`concurrency`: supported**, renamed from `threads`
  (#1270). Its tests check concurrent calls: unique
  request ids, responses in any order, a close while a call waits, a response after the
  disconnect. Promises raise each case. The testee maps each named task of the testee protocol to
  an async task chain. Commands on one
  chain run in order, and chains interleave. A test that needs a real thread, such as `Interrupt`
  or the thread a callback runs on, goes in `unsupported.txt`.
- **`races`: unsupported.** Its race points pause the update thread mid-step. JavaScript never
  preempts, so other code runs only at an `await`. The client keeps those windows closed by rule:
  the message handler, and `addCallback` from reading a value to calling the callback, hold no
  `await`. A comment in the code states the rule.

#### Objects and equality

`===` is identity, and a language cannot overload it. The client interns remote objects: one
JavaScript object per id per connection, held in a `Map` of `WeakRef`s and cleaned by a
`FinalizationRegistry`. Two results for one object are then `===`, and an object works as a `Map`
key or `Set` element. Struct and enumeration equality goes through the testee's `compare`, with
the client's own `equals` helper. The `hash` tests are unsupported, as JavaScript has no hash of a
value.

#### Timeouts

The `WebSocket` interface has no connect timeout. The client times the upgrade plus the handshake
with `setTimeout`, and closes the socket when it fires. The stall timeout uses the same timer,
reset on each message.

#### Conformance

- A testee in `client/js/conformance/`, a Node.js script reading commands on standard
  input. It drives the same library code a browser loads.
- `client/conformance/driver/conventions.py` gains a `camel` case. The conventions file sets
  `{"case": "camel", "accessors": true, "exceptions": false}`.
- A browser run of the suite waits for a later phase. It needs a headless browser in Bazel, and a
  bridge from the harness's standard input to the page.

#### Build

- Node.js and npm dependencies through `rules_nodejs` or `aspect_rules_js`, with a lockfile.
- Targets: the library, the testee, `//client/js:conformance`, a lint (ESLint or Biome),
  and an npm tarball in the release zip.
- A `client/js` component in `COMPONENTS`, with its `CHANGELOG.md`.

#### Docs

A client guide page under `doc/src/client-guides/`, with examples in
`doc/src/scripts/<page>/`. The docs build type-checks the TypeScript examples. The API reference
waits for the stubs in phase 3, as the other clients' references come from clientgen.

### Phase 1 as built

| Item | Decision |
| --- | --- |
| Directory | `client/js`, short like the other clients' directories. The language keeps its name, JavaScript, in prose |
| Bazel | `rules_nodejs` for Node 22, `aspect_rules_js` for the pnpm lock file, `aspect_rules_ts` with `tsc` |
| Lint | Biome, for formatting and lint, as the `lint` test |
| `krpc.proto` messages | `protoc-gen-es` in a Bazel rule, generated into the package, not committed |
| Package | `krpc-js-<version>.tgz`, the `npm pack` layout, a release asset like the other clients' packages. Not in the mod zip |
| Browser check | The library's `tsconfig` has no Node types. An esbuild bundle was checked by hand: 27 KB minified and gzipped |
| Docs | A `js.rst` guide. The examples are plain JavaScript, for the wider audience, and `tsc` type-checks them against the client in `//doc:check-scripts-js` |

Where it differs from the design above:

- **No stall timeout.** A WebSocket message arrives whole, so a partial message never stalls. The
  testee fails `test_stall_timeout_values` for the zero, negative and NaN cases, as expected
  failures.
- **Timeouts in milliseconds**, as JavaScript times everything. `handshakeTimeout` defaults to
  5000, and `Infinity` waits indefinitely.
- **Lower camel case** lower cases the leading run of capitals, except the last capital when a
  lower case letter follows: `HTTPServer` is `httpServer`, `MyHTTPServer` is `myHTTPServer`.
  Underscores stay. The driver's conventions file gained a `camel` case, and accessors are
  `getName`.
- **Structures** were frozen plain objects, made by a function the service exposes. Phase 2 made
  them classes.
- **Streams and events.** A member that returns a stream or an event exists, so the member lists
  match, and rejects when called, until phase 4.
- **The `client/websockets` testee is deleted.** The held-call tests in `test_calls.py` now define
  `TestService` on the scripted server, which a dynamic client needs to call it.
- **Unsupported**: interrupting a call (`test_abandoned_id`, `test_close_interrupted`), hashes, and
  a static method called through an object.

### Phase 2 as built

Named arguments are a plain object after the positional arguments, the usual JavaScript options
object:

```js
await conn.spaceCenter.launchVessel("VAB", "My Rocket", "LaunchPad", { recover: false });
```

- **Structures are classes**, so a plain object is never a value. Each structure is a class on its
  service, such as `conn.spaceCenter.BoundingBox`, extending `StructValue`. A value is frozen, made
  with `new` from an object of its fields. Decoded results are instances of it. The codec accepts
  a value of the structure of the same name from any connection, and `equals` compares one field
  by field.
- **Arguments by name** fill any parameter, including one before a positional default. A trailing
  plain object, with the prototype `Object.prototype` or `null`, holds them. Names are lower camel
  case. A name passed twice, or a name the procedure lacks, raises a `TypeError`. The object of a
  method has no name.
- **Each exception a service lists is a class** on the service, such as
  `conn.krpc.ObjectDestroyedException`. A mapped exception extends the matching JavaScript error:
  `TypeError` for `ArgumentException`, `ArgumentNullException` and `NullReferenceException`, and
  `RangeError` for `ArgumentOutOfRangeException`, `IndexOutOfRangeException`,
  `DivideByZeroException` and `OverflowException`. The others extend `RPCError`.
- **`instanceof RPCError` holds for every error from the server**, through a `Symbol.hasInstance`
  on `RPCError` alone. Each class carries `service`, `exception`, `description` and `stackTrace`.
- **Messages** of a typed error are the description and stack trace. An exception the client has
  no class for keeps the `Service.Name:` prefix.
- The classes are per connection, as the classes of objects are. The conventions file sets
  `exceptions: true` and lists the native types. The testee reports each built-in error
  constructor the error is an instance of.

### Phase 3 as built

The stubs are TypeScript declarations only. The client still builds each service at run time from
`KRPC.GetServices`, so it matches the server it connects to. clientgen's `js` language writes one
module per service into `src/services/`, which compiles to an empty module and its `.d.ts`:

```ts
export interface Service {
  getActiveVessel(): Promise<Vessel | null>;
  launchVessel(craftDirectory: string, name: string, launchSite: string, crew?: readonly string[] | null, recover?: boolean, flagUrl?: string): Promise<void>;
  launchVessel(craftDirectory: string, name: string, launchSite: string, options: { crew?: readonly string[] | null; recover?: boolean; flagUrl?: string }): Promise<void>;
  readonly Vessel: { [Symbol.hasInstance](value: unknown): value is Vessel };
  ...
}
export interface Vessel extends RemoteObject<"SpaceCenter.Vessel"> { ... }
export type VesselSituation = EnumValue<"SpaceCenter.VesselSituation">;
```

- **`Connection` holds the services.** An interface `Connection extends Services` merges with the
  class, and `connect()` returns `Promise<Connection>`. `Services` lists the services a release
  ships, written from `SERVICES` in `clientgen.bzl`. `DynamicConnection` types any other service as
  `any`.
- **Brands.** `RemoteObject`, `EnumValue` and `StructValue` take the type's name as a type parameter,
  through an optional property keyed by a symbol that exists in types only. Two classes with the
  same members, or two enumerations, do not mix.
- **Overloads.** A procedure with defaults has the positional signature, and the required arguments
  followed by an options object. Mixing the two, or naming a required argument, works at run time
  and is not typed.
- **Arguments are wider than results.** A 64-bit integer argument takes `number | bigint`, and a
  collection argument is read-only. A tuple argument is a tuple type, so an array held in a variable
  needs `as const` or a type annotation.
- **Value types** of a class, structure, enumeration or exception are object types on the service,
  with a `Symbol.hasInstance` predicate, so `instanceof conn.krpc.ArgumentException` narrows.
- **Imports** come from `@krpc-org/krpc`, the package's namespace exports (`SpaceCenter`, `schema`).
  The package's own build passes `--include=Service=./Service.js`, and maps the package name to its
  source with `paths`. A mod's generated module adds its service to `Services` with module
  augmentation, documented in `extending/clientgen.rst`.
- **Name collisions.** The client assumes member names are unique, as
  the [service definition rules](protocol/service-definition-rules.md#member-keys) ban clashes. The one clash in the
  bundled services, `ConfigNode.GetValues` and `GetNodes` beside the `Values` and `Nodes` properties,
  is removed on the branch below this one. Before that, the second `defineProperty` of `getValues`
  threw, so `connect()` failed against a real game.
- **Docs.** docgen's `js` domain uses Sphinx's built-in JavaScript domain: functions for service
  procedures, a class per class, enumeration, structure and exception, and a property as its two
  accessor signatures on one directive. Types are in `:type:` and `:rtype:` fields, written to
  contain a literal so Sphinx does not look them up. The 8 API examples have JavaScript versions,
  type-checked by `//doc:check-scripts-js`, which runs without `strictNullChecks` as the Python
  check ignores optional access.

### Flags and deprecation as built

Ported from main after the rebase of 2026-11-11, where every other client already had both.

- **Flags enumerations.** A flags value is a `FlagsValue`, a subclass of `EnumValue` with `union`,
  `intersection`, `difference` and `contains`, as JavaScript has no operator overloading. The
  `Enumeration` keeps each combination it makes, so combinations compare with `===`. A number
  with a flag the enumeration lacks is an `EncodingError`. clientgen types a flags enumeration
  as `FlagsValue`.
- **Deprecation signals.** A procedure warns when called. A service, class, enumeration,
  enumeration value, structure, structure field or exception is a getter that warns when read.
  The codec and `equals` read fields through `StructValue.fieldOf`, so decoding and encoding
  give no warning. Members inherit deprecation from their container, as in the other clients.
- **The warning** is `process.emitWarning(message, "DeprecationWarning")` when the runtime has it,
  and `console.warn` otherwise, once per member on a connection. clientgen adds `@deprecated` to
  procedures, methods and services too.

### Phase 3b: importable types

The generated modules follow the [Python declarations](python-declarations.md): enumerations,
structures and exceptions become real values, and classes and services stay declarations. A
default argument then needs no connection:

```js
import { SpaceCenter } from "@krpc-org/krpc";

function setMode(vessel, mode = SpaceCenter.SASMode.prograde) { ... }
```

- **Generated values.** Each module exports its enumerations, with their `EnumValue`s, and its
  structure and exception classes. The modules no longer compile to empty modules.
- **One class per type where the definitions match**, by the rule in
  [python-declarations.md](python-declarations.md#one-class-per-type-where-the-definitions-match).
  The connection uses the module's enumeration, structure or exception where the server's
  definition matches, so `===` and `instanceof` work on imported types. Otherwise it builds its
  own, and `equals` compares service, name and value.
- **Classes and services** are unchanged: declarations, built per connection.

### Phase 3b as built

- **Generated values.** Each enumeration, structure and exception is a type and a `const` of the
  same name, such as `export const SASMode = declareEnumeration<Service["SASMode"]>(...)`. The
  `const` takes its type from the service interface, so its values keep their documentation.
- **Registry.** `declareEnumeration`, `declareStruct` and `declareException` register each type by
  service and name. A later registration replaces an earlier one. The package exports the
  functions, for mods' modules.
- **Matching** follows Python: an enumeration on its flags, names and numbers, a structure on its
  field names in order, an exception on the JavaScript error it extends. A matched type is also
  the service's member, so `conn.spaceCenter.SASMode === SpaceCenter.SASMode`.
- **Structures** split into a `StructDeclaration` (field names, value class), which connections
  share, and a per-connection `Struct` with the field types from the server.
- **Differing definitions.** A generated enumeration value passes by its number, and `equals`
  compares by number. A structure passes only with the same field names.
- **Import path.** The package's own modules import `../declarations.js`, through a new clientgen
  option `--client-module`. Importing `@krpc-org/krpc` from inside the package would cycle through
  `index.ts`, and `tsc` does not rewrite `paths`. A mod's module imports from `@krpc-org/krpc`.
- **Deprecation.** Generated values warn once per process, as they belong to no connection.
- **Bundle size.** Every shipped service's values add 3.7 KB gzipped to a bundle of the client
  (28.7 KB to 32.4 KB with esbuild).
- **Conformance.** The testee joins the `declarations` profile, with the generated `TestService`
  module compiled into it.

### Phase 4 as built

```js
const altitude = await conn.addStream(() => flight.getMeanAltitude());
console.log(await altitude.get());
altitude.addCallback((x) => draw(x));
await altitude.remove();
```

| Item | Decision |
| --- | --- |
| Stream form | `conn.addStream(() => member(...))`, as C#'s lambda. The client runs the function in a capture mode: a member builds its call and returns a `Promise` that never settles. TypeScript infers `Stream<T>` from the member's `Promise<T>` |
| Reads | `await stream.get()` waits for the first value. The `value` getter reads the latest one at once, for a render loop, and throws a `StreamError` before the first value |
| Waits | `wait(timeout)` in milliseconds, resolving `false` at the deadline. An event's wait returns at once for a firing since the last wait on that `Event` |
| Rate | The `rate` getter, and `setRate(rate)`, which returns a `Promise` |
| Callbacks | Run in a microtask after the message handler. Each callback runs one call at a time: one that returns a `Promise` is busy until it settles, and a newer value replaces a waiting one. The first call is made before `addCallback` returns |
| End callbacks | A remove or a close calls them itself. A server ending waits for the value callbacks, so a value before the ending reaches them first. A failure calls them in a microtask |
| Callback errors | Reported with `reportError`, or `console.error`. No fatal kind, so the five fatal-error tests are unsupported |
| Registration | The session's `call` takes a function it runs on the result in the message handler, which registers the stream before its first update |
| Events | A procedure returning an event resolves with an `Event`. `KRPC.StreamRemovedException` is `StreamError`, at run time and in the generated module |
| Scoping | `Symbol.asyncDispose` on `Stream` and `Event`, for `await using` |
| Dropped handles | Leave the stream on the server, as in the other clients. A collection at no predictable time would stop a stream kept only for its callbacks. `test_drop_last_handle` is an expected failure |
| `conditions` | Left out. A run of reads with no `await` between them already sees one state |

- **Conformance.** The testee joins `streams`, `events` and `callbacks`: 592 pass, from 452.
  Hashes of handles and interrupted waits are unsupported, as for objects and calls.
- **Shipped services** have no procedure that returns an event. Events from conditions wait for
  the server side functions of phase 5, as `KRPC.AddEvent` is internal.

### Phase 5 as built

```js
const { Expression } = conn.krpc;
const altitude = await Expression.call(conn.getCall(() => flight.getMeanAltitude()));
const above = await Expression.greaterThan(altitude, await Expression.constantDouble(1000));
const event = await conn.addEvent(above);
console.log(await conn.run(above));
```

| Item | Decision |
| --- | --- |
| API | `getCall`, `compile`, `run(fn, ...args)` and `addEvent` on `Connection`, as the other clients. `addStream` takes a `KRPC.Expression` in place of a function |
| `getCall` | The capture of `addStream`, returning the `ProcedureCall`. Synchronous, as nothing is sent |
| Types | Read from the `KRPC.Expression` on the server, once per function, as in Lua. `run<T>` and `addStream<T>` name a type the client cannot check, as TypeScript erases it |
| `function-types` | Left out, as the client has no type a program names to check. As Python and Lua |
| Parameters | A stream or event of a function with parameters is a `TypeError` before the call |
| Messages | A protobuf message is a plain object, so `isMessage` keeps a trailing `ProcedureCall` from being read as named arguments |

- **Conformance.** The testee joins `functions`: 682 pass, from 592. A null at a type named
  without `nullable` is unsupported, as in Python and Lua.
- **Docs.** The server side functions guide gains a JavaScript tab beside each Lua one, the first
  JavaScript tabs on a shared page.

### Phase 6: function compiler

Compiles a JavaScript function into a server side function, as the Python and C# compilers do for
their languages. The client reads the function's source with `Function.prototype.toString()`,
parses it, and builds the `KRPC.Expression` nodes:

```js
const high = await conn.compile(
  ({ vessel, limit }) => vessel.flight().meanAltitude > limit,
  { vessel, limit: 70000 },
);
const event = await conn.addEvent(high);
```

The body is written as it would run on the server: properties read and assigned as properties,
and methods returning their values.

#### API

| Call | Takes |
| --- | --- |
| `compile(fn, captures?, parameters?)` | A function. Returns a `KRPC.Expression`, as `compile` of an `Expression` does |
| `run(fn, captures?)` | A function with no parameters, compiled and run once. A function with parameters is compiled first |
| `addStream(fn, captures)` | A function, streamed. `addStream(fn)` with no captures stays the call stream of phase 4 |
| `addEvent(fn, captures?)` | A function returning a `boolean` |

- **Captures.** The function's first parameter is an object pattern, and receives the captured
  values by key: `({ vessel, limit }) => ...` with `{ vessel, limit }`. The other parameters are
  the function's own, passed by `run`. A function with parameters and no captures takes `{}` first.
- **Parameter types.** `parameters` gives one type value per parameter after the first, as in
  `[types.double]`. An event or a stream takes no parameters.
- **Errors.** `CompilationError`, exported from the package, names the construct and its line
  and column in the function's source. It is raised before any node is built.
- **No cache of compiled functions.** Each `run`, `addStream` or `addEvent` of a function compiles
  it again, as its captures can differ per call. The parse is cached per function object, in a
  `WeakMap`. The guide says to compile once.
- **Function types.** The compiler knows the parameter and result types, and fills the cache of
  phase 5, so `run` reads no types from the server.

#### Captured values

JavaScript gives no access to a function's closure, and a minifier renames local names. Every name
the body reads is therefore a capture, a parameter, a local, or one of the builtin globals below.
Any other free name is a `CompilationError` that says to capture it.

An object pattern survives a minifier: the keys are property names, which it keeps, and it renames
each binding with its uses. A capture missing from the object is a `CompilationError`.

| Captured value | In the function |
| --- | --- |
| `number`, `bigint`, `string`, `boolean`, `null`, `Uint8Array` | A constant |
| An array, `Set`, `Map` or structure | A constant collection or structure. Its type comes from its values, or from where it is used when empty |
| A remote object | `ConstantObject` |
| A service, such as `conn.spaceCenter`, or the `Connection` | Member calls become embedded calls. `conn.spaceCenter` is read on the client |
| A generated module, such as `SpaceCenter`, or an enumeration, structure or exception class | Read on the client: `SpaceCenter.SASMode.prograde` is a constant |
| A plain object the body assigns a property of | A state variable per assigned property, as below |
| Another plain object | Its properties are read on the client, as constants |
| A `Stream`, `Event`, function or other object | A `CompilationError`. A stream read in a function would be read once |

The builtin globals are `Math`, `console`, `Number`, `String`, `Boolean`, `BigInt`, `Array`, `Set`,
`Map`, `Error`, `TypeError`, `RangeError`, `undefined`, `NaN` and `Infinity`, resolved by name. A
program that shadows one of them in an enclosing scope gets the builtin in the function.

**State variables.** A captured plain object whose property the body assigns keeps that property
on the server between evaluations, which is how the object behaves in JavaScript:

```js
const highest = await conn.addStream(({ vessel, state }) => {
  state.max = Math.max(state.max, vessel.flight().meanAltitude);
  return state.max;
}, { vessel, state: { max: 0 } });
```

The value starts as the property holds it at compile time, and takes its type from it. The client's
object keeps its value. This replaces Python's `nonlocal`.

#### Types

**Numbers are doubles, as in JavaScript.** A server value of type `float`, `double`, `sint32` or
`uint32` is a `number` in the client, and arithmetic on numbers converts its operands to `double`.
`7 / 2` is `3.5`, `%` is the CLR remainder, which matches JavaScript's for both integers and
doubles, and the bitwise operators convert to a 32-bit integer as JavaScript does. A number in a
position of an integer type is converted toward zero, and a constant there takes the exact type.

**A `bigint` is a 64-bit integer.** `sint64` and `uint64` values are `bigint` in the client, and
`bigint` arithmetic stays integer, so `7n / 2n` is `3n`, as on the server. Mixing a `number` and a
`bigint` is a `CompilationError`, as it is a `TypeError` in JavaScript.

**Type values.** A run parameter, and an empty collection with no use that types it, need a type at
run time:

| Type | Value |
| --- | --- |
| Scalars | `types.double`, `types.float`, `types.int32`, `types.uint32`, `types.int64`, `types.uint64`, `types.bool`, `types.string`, `types.bytes` |
| Collections | `types.list(T)`, `types.set(T)`, `types.map(K, V)`, `types.tuple(T, ...)` |
| Null | `types.nullable(T)` |
| Classes | The service's class, such as `conn.spaceCenter.Vessel` |
| Enumerations, structures | The generated value, such as `SpaceCenter.SASMode`, or the service's |

- **Null** takes its type from where it is used, as in Python: a parameter, the other branch of
  a `?:`, another assignment to the variable, or an argument. `undefined` is null.
- **An array** is a tuple where the position is a tuple, such as an argument for a vector, and a
  list otherwise.
- **An empty array, `Set` or `Map`** takes its element type from its first use that types it: a
  push, an element assignment, another assignment to the variable, or an argument.
- **`cast`** types a value no use types, such as a function's only `return []`, or a state
  variable that starts empty and is only read. Each type value has a `cast(value)` method, used
  with `types` captured. It covers empty collections and nulls alike, as Python's `typing.cast`
  does, and returns its argument on the client, so the code keeps its JavaScript meaning:

  ```js
  ({ engines, t }) => {
    if (engines.length === 0) return t.list(t.double).cast([]);
    ...
  }   // captures: { engines, t: types }
  ```

  An untyped value is a `CompilationError` that suggests this form. `types` is an import, which a
  minifier renames, so it is a capture and not a builtin global.
- **Truth** follows JavaScript: `false`, `0`, `NaN`, `""`, `0n` and null are false. An empty array
  is true.
- **Equality.** `===` and `!==` compare numbers, strings, booleans, enumeration values and remote
  objects, which the client caches so that one object is one JavaScript value. Collections and
  structures compare by identity in JavaScript, which the server cannot reproduce, so comparing
  them is a `CompilationError`. `==` and `!=` are `===` and `!==`, with operands of one type, and
  `x == null` is also true for `undefined`.

#### Constructs

| Area | Supported |
| --- | --- |
| Members | Property reads and assignments, method and static method calls, named arguments as an options object. A `KRPC` service call is an error, as in Python |
| Operators | Arithmetic, `**`, comparisons, `!`, `&&`, `\|\|`, `??`, `?.`, `?:`, bitwise operators on numbers and flags enumerations, template literals without tags |
| Strings | `length`, indexing, `at`, `slice`, `substring`, `toUpperCase`, `toLowerCase`, `trim`, `trimStart`, `trimEnd`, `split`, `includes`, `startsWith`, `endsWith`, `indexOf`, `replaceAll`, `String(x)`, `+` |
| Arrays | `length`, indexing, `at`, `map`, `filter`, `some`, `every`, `find`, `findIndex`, `includes`, `indexOf`, `reduce`, `slice`, `concat`, `join`, `toSorted`, `toReversed`, `push`, `pop`, assignment to an element, destructuring of tuples |
| Sets, maps | `new Set`, `new Map`, `has`, `add`, `get`, `set`, `delete`, `clear`, `size`, `keys`, `values`, `entries` |
| Structures | Field reads, and `new` of a captured structure class with an object of fields |
| Math | `Math` functions and constants to `StdLib` procedures. `Math.round` uses `StdLib.RoundHalfUp`, as it rounds a half toward positive infinity |
| Printing | `console.log` to `StdLib.Print`. A constant argument is formatted on the client, as `String` formats it |
| Statements | Blocks, `const`, `let`, `if`, `switch`, `while`, `do`, `for`, `for...of` over a collection, `break`, `continue`, `return`, `++`, `--`, compound assignment, destructuring assignment |
| Functions | Arrow functions passed to the collection methods, and local functions, as below |
| Exceptions | `throw new Error(m)`, `TypeError`, `RangeError` and captured service exception classes. `try`, `catch` and `finally` |

- **Local functions take their parameter types from their calls.** A local function is one
  `Lambda`, called with `Invoke`, as in Python. JavaScript has no annotations to type its
  parameters, and TypeScript's are erased, so each parameter takes the one type that fits the
  arguments of every call:

  ```js
  ({ vessel }) => {
    const ratio = (part, total) => part / total;
    return ratio(vessel.mass - vessel.dryMass, vessel.mass);
  };
  ```

  - Numbers are all doubles, so most parameters have one candidate type.
  - Null and a type `T` give a nullable `T`. An empty array takes the type of the other calls.
  - Types that do not fit, such as a string and a number, are a `CompilationError` naming both
    calls.
  - A function passed by name, as in `xs.map(ratio)`, is called by the collection method with the
    element type.
  - The function reads the enclosing variables when called, so every path to each call assigns
    them. A function no call reaches is not built. One defined in a nested block is called only
    in that block. Recursion is an error, as in Python.
  - Ruled out: a copy per set of argument types, which never fails but grows the function, and
    could follow if the errors prove common. Default values as types, which give no collection
    types and change the code's meaning.
- **`switch`** compiles to the server's `Switch`, with JavaScript's fall-through
  and `break`. The server node lands first, see
  [server-side-functions/switch.md](server-side-functions/switch.md).
- **Exceptions map through the client's own table.** `Error` raises `KRPC.Error`, `TypeError`
  raises `KRPC.ArgumentException` and `RangeError` `KRPC.ArgumentOutOfRangeException`. A handler
  that starts with `if (e instanceof RangeError)` catches each exception the client raises as a
  `RangeError`. `e.message` is the message, the only part of an exception a function exposes.
- **A function that returns a value** returns on every path, as in Python. A variable is read only
  after every path to the read assigns it.
- **Not supported:** `async`, `await`, generators, `this`, classes, `for...in`, labels,
  spread, tagged templates, regular expressions, and recursion. Each is a `CompilationError`
  naming it. A getter name such as `getMeanAltitude()` is an error that names
  the property form.

#### TypeScript

The body is typed by a second, synchronous set of declarations in each generated module. A class
`Vessel` gets a server form with a property per property, writable where it has a setter, and
methods returning their values. Each module adds its classes to an interface in the package by
declaration merging, keyed by the class name, so mods' modules join in:

```ts
declare module "@krpc-org/krpc" {
  interface ServerTypes { "SpaceCenter.Vessel": Server.Vessel; }
}
```

`OnServer<T>` maps a client type to its server form through that interface, and recurses into
arrays, sets, maps and tuples. `compile` infers the captures' type from its second argument:

```ts
compile<C extends object, P extends unknown[], R>(
  fn: (captures: OnServer<C>, ...parameters: OnServer<P>) => R,
  captures: C,
  parameters?: TypeValues<P>,
): Promise<ServerFunction<P, OnClient<R>>>;
```

`ServerFunction<P, R>` is a `KRPC.Expression` with the parameter and result types as phantom
types, so `run(fn, ...args)` checks the arguments and `addStream(fn)` gives a `Stream<R>`. A plain
JavaScript program gets the same compiler with no types.

#### Implementation

```
src/compiler/
  index.ts       compileFunction, loaded with import()
  parse.ts       acorn, and the function's node in its source
  scope.ts       captures, parameters, locals, globals, definite assignment
  ir.ts          the typed intermediate tree
  expressions.ts, statements.ts, builtins.ts, constants.ts
  emit.ts        the KRPC.Expression nodes from the tree
```

- **Packaging.** `compile`, `run`, `addStream` and `addEvent` load the compiler with `import()` the
  first time they get a function. Bundlers split it into its own chunk, so a program that never
  compiles carries none of it. acorn 8 is 33 KB minified and gzipped, more than the whole client.
- **Parser.** `acorn` (MIT, ES modules, no dependencies), parsing at `ecmaVersion: "latest"`. The
  source of a method shorthand, `f() {}`, parses after a prefix that makes it an object method.
- **Two stages.** The compiler first builds a typed tree on the client, with no calls. The types
  of nulls and empty collections resolve over the whole tree, and every `CompilationError` is
  raised before anything reaches the server. The second stage emits the nodes.
- **Concurrent emission.** The emitter builds the children of a node with `Promise.all`, so a
  compile takes about one round trip per level of the tree, where Python takes one per node. The
  batched tree construction proposal later plugs in here.
- **Procedures** come from the connection's service definitions, read at connect for the dynamic
  services, and named with `naming.ts`. The compiler needs no generated module.
- **Folding.** A sub-expression of constants only, such as `limit * 2`, is computed on the client
  by running the JavaScript operator or builtin, which gives JavaScript's exact result.

#### Testing

The compiler is per language, so it has no conformance profile, as Python's and C#'s have none.

- **Native tests**, `//client/js:compiler-test`, with `node:test` against a `TestServer`, as
  Python's `clienttest`. They take the cases of `test_functioncompiler.py` that have a JavaScript
  form.
- **Golden trees** through `TestService.DumpExpressionTree`, as `test_expressiontree.py`.
- **Types checked against the server.** Each test compiles through a check that the compiler's
  parameter and result types equal the server's, as Python's tests do.
- **Run on both sides.** A function of constants and parameters only also runs as JavaScript, and
  the test compares the two results. It covers numbers, truth and strings.
- **TypeScript.** A `tsc` test of typed examples, with `@ts-expect-error` lines for the errors.

#### Steps

Each step is mergeable on its own.

| Step | Adds |
| --- | --- |
| 6a | The API, captures, `types`, the two stages and the test harness. Expressions: constants, members, operators, numbers, truth, strings, `Math`, `console.log`. The guide's compiled examples that are single expressions gain JavaScript tabs |
| 6b | Collections, structures, statements, state variables, exceptions. The rest of the guide's compiled examples. Needs the server's switch nodes |
| 6c | The synchronous declarations from `clientgen`, `OnServer`, and the typed signatures |

#### Rules for programs

- **Target.** A transpiler targeting an older version rewrites `?.`, `??`, destructuring and arrow
  functions into code the compiler rejects. The guide asks for ES2020 or later.
- **Coverage.** A coverage tool that instruments the source, such as Istanbul, adds counters to the
  function's body. V8 coverage, as `c8` and Vitest use by default, changes no source.

#### Ruled out

- **Positional captures**, `(vessel, limit) => ...` with `[vessel, limit]`. Shorter, but a wrong
  order goes unnoticed.
- **A named object read by free names**, `() => vessel...` with `{ vessel }`. A minifier renames
  `vessel` in the body and leaves the key.
- **The client's asynchronous API in the body**, `(await vessel.getControl()).setThrottle(1)`. It
  needs no new declarations and runs on the client too, but is unreadable at any size.
- **Type strings**, such as `"list<int32>"`. Compact, but checked only when compiling.
- **Python's integer types for numbers.** JavaScript has one number type, and keeping server
  integers would make `7 / 2` and integer overflow differ from JavaScript.
- **Tracing**, calling the function with placeholder objects that record each operation.
  JavaScript cannot overload `>`, `+` or `?:`, which expressions need most.
- **Tagged templates**, `` conn.fn`vessel.flight().meanAltitude > ${limit}` ``. They capture
  values and survive minifiers, but an editor cannot check or complete the string.
- **Other forms of typed empty values.** `t.list(T).empty()` covers collections and not null. A
  `result` option on `compile` covers only the function's result. An empty array carrying its type
  in a hidden property types captures only, and a spread or `structuredClone` drops the property.
- **A separate entry point**, `@krpc-org/krpc/compiler`, passed to `connect`. `import()` gives the
  same split with no step for the program.

### Phase 6a as built

```js
const apex = await conn.run(
  ({ flight, gravity }) => flight.meanAltitude + flight.speed ** 2 / (2 * gravity),
  { flight, gravity: 9.81 },
);
const ratio = await conn.compile(({ vessel }, payload) => (vessel.mass + payload) / vessel.mass,
  { vessel }, [types.double]);
```

| Item | Decision |
| --- | --- |
| Bodies | One expression, or a block of one `return`. Statements are 6b |
| No captures | No parameters, or a first parameter that is a name the body does not read, such as `_`. Biome's recommended `noEmptyPattern` rejects `({}, x) =>` |
| `types` | `TypeValue` objects, exported from the package. A captured `types` builds types in the function, and `cast` gives a value a type, so `t.nullable(t.double).cast(null)` compiles now |
| Null receivers | A member of an object that can be null compiles, and the server raises a `TypeError` for null, as JavaScript does. Arithmetic on a number that can be null is a `CompilationError` that suggests `??`, as JavaScript would give `null + 1 === 1` |
| String indexing | `s[i]` and `s.at(i)` out of range raise on the server, where JavaScript gives `undefined` |
| String order | `<` on strings is a `CompilationError`. The server orders numbers only |
| Number strings | The server formats a number, as .NET does. Constants format on the client |
| Structures | Field reads move to 6b with structure construction. `GetField` takes the server's field name, which the client's `Struct` does not keep |
| Errors | `CompilationError` with `line` and `column`, both counting from 1, in the function's source. The message ends `(line 1, column 7 of the function)` |
| Value naming | `registry.ts` maps a service object, class, enumeration values object, structure class and exception class to what it names, so the compiler reads captured values without the generated modules |

- **Tests.** `//client/js:compiler-test`, in `//client/js:test`: 38 `node:test` cases against a
  `TestServer` over WebSockets, through `client_test`. Each compile checks the compiler's types
  against the server's. Arithmetic, bitwise operators, truth, strings and `Math` run on both
  sides. V8 computes some powers, such as `7 ** -2`, one bit from .NET's `Math.Pow`, so those
  cases are left out. Two golden trees.
- **Size.** esbuild with splitting, gzipped: a program that never compiles loads 36 KB, and the
  compiler chunk, with acorn, is 47 KB.
- **Docs.** The guide's single-expression compiled examples gain JavaScript tabs. The JavaScript
  guide leads its server side functions section with compiled functions, and keeps the
  expression API after them.

### Phase 6b as built

| Item | Decision |
| --- | --- |
| Later uses type values | An empty array, `Set` or `Map`, a `null`, a state variable that starts empty and a local function's parameters take their type from a later use. The use notes the type and the function compiles again, as in Python. A read of a variable holding `null` compiles as `null` until then, so `best === null` before `best = engine` types it |
| Variables | Numbers in variables are doubles. `var` is a `CompilationError` |
| Arrays | A literal or captured array is a tuple where a tuple goes and a list elsewhere, built where it is used. `Map.keys()` and the like give lists, so `Array.from` takes them |
| `for` and `do` | Lowered to `While`. With a `continue`, the update or test runs at the start of the body on every pass but the first, as the server's `Continue` jumps there |
| `switch` | Each clause is a case of `Switch`, an empty clause a no-op that falls through. A number discriminant compares as a double |
| Exceptions | A leading `if (e instanceof X)` chain dispatches by the class the client raises an exception as. Each branch catches its names, innermost first, and records a branch number, as Python's handlers do. An `else throw e` leaves the rest uncaught. `e.message` is the only member of `e` |
| State | A captured plain object's property that the function assigns, or changes with `push`, `add`, `set`, `delete`, `clear` or an element assignment |
| `toSorted` | Takes a comparator `(a, b) => K(a) - K(b)`, compiled to `OrderBy` on `K`, or `K(b) - K(a)` on its negation. With none, strings only |
| Map reads | `get` of a missing key gives `null`, as `undefined` in JavaScript |
| Not supported | `findIndex` and `indexOf` compile to a loop. Callbacks take one parameter, with no index. Mutating array methods (`sort`, `splice` and others) name their copying forms |

- **Tests.** `test/statements.test.ts`: 20 cases, 58 compiler tests in all, mostly run on both
  sides.
- **Docs.** Every compiled example in the shared guide has a JavaScript tab, and the state and
  control loop sections become tabs. Two examples type a callback's parameter with JSDoc until
  6c types the bodies.

### Phase 6c as built

```ts
const mass = await conn.run(({ vessel }) => vessel.mass, { vessel });   // number
const fn = await conn.compile(({ s }, x) => s.int32ToString(x), { s }, [types.int32]);
await conn.run(fn, 1);   // string; run(fn, "a") is a type error
```

| Item | Decision |
| --- | --- |
| Server forms | Each generated module declares `export declare namespace Server`, with `Service` and each class extending `ServerObject<"Svc.Class">`. A property is a property, readonly without a setter, and a method returns its value. Enumerations, structures and exceptions on the server form of a service are the client's, through a local `ClientService` alias |
| Registries | `ServerTypes` and `ClientTypes` in `src/server.ts`, which each module extends with `declare module "@krpc-org/krpc"`. `RemoteService` gained a brand, `RemoteService<"Svc">`, as `RemoteObject` has |
| `OnServer`, `OnClient` | `OnServer` maps objects and services through their brands, and collections and plain objects through their members. A method returning a `Promise` on a captured value, such as a class's static method, returns its value. Enumerations, structures and bytes pass through. `OnClient` maps back by the `ServerObject` brand |
| Parameters | `compile<C, R, const L extends readonly TypeLike[] = []>` infers the tuple of type values, and `ValuesOf<L>` gives the parameters' types. A union of type value forms would also infer from a class's static methods |
| `ServerFunction<P, R>` | A `KRPC.Expression` with phantom types. `run<R, P>` checks the arguments; `R` comes first so `run<number>(expr)` still compiles. `addStream` takes `ServerFunction<[], R>` |
| In-package paths | `tsconfig.json` maps `@krpc-org/krpc` to `./src/index` with no extension. With `.ts`, tsc 5.9 crashed resolving the augmentation from a project that has only `index.d.ts` |
| Docs comments | The server forms reuse the client's documentation, so a link to a property names its getter. Phase 7 fixed the links |

- **Tests.** `test/types.check.ts`, compiled with the native tests and never run, with
  `@ts-expect-error` lines for a getter form, a Promise read, a wrong argument, a stream of a
  function with parameters and an event of a number. The guide's JavaScript examples are checked
  against the server forms too, so their JSDoc workarounds went.
- **Goldens.** The JavaScript clientgen goldens grow by the server namespace and registries.

### Phase 7 as built

Done: links in the server forms, npm publishing. To do: a first Windows CI run, the submission.

- **Links in the server forms.** Clientgen parses each comment a second time for a server form,
  where a link to a property names the property: `{@link Vessel.mass}` in place of
  `{@link Vessel.getMass}`. The other links already resolve there. Folded into the 6c commit.
- **npm publishing.** Release step `69-release-npm.py` publishes the release tarball as
  `@krpc-org/krpc` with public access, using `NPM_TOKEN` from the credentials file. The token is a
  granular one with write access to `@krpc-org` and 2FA bypass, and lasts at most 90 days, so
  each release makes a new one. Preflight checks the token with `/-/whoami`, and fails if the
  version is already on npm. The guide installs from npm, but does not link the package page:
  the release's linkcheck runs before the first publish.

## Pages and TLS

Browsers block an `https://` page from opening a `ws://` connection, as mixed content. Phase 1
supports `http://` pages only. Later server phases cover the rest.

| Page served from | Game on | `ws://` result |
| --- | --- | --- |
| `http://`, or a local file | any machine | Works in every browser |
| an `https://` site | the same machine (`127.0.0.1`) | Chrome and Firefox allow it. Safari blocked it for years; a March 2025 WebKit change allowed it, and its state since is unclear |
| an `https://` site | another machine on the network | Blocked in every browser |

Chrome also gates a public site's WebSocket to a loopback or private address behind a Local
Network Access permission prompt (Chrome 142 on). A page served from the game's own address
avoids the prompt.

### Server phase: pages served by the mod

The WebSockets server already parses the HTTP upgrade. It also serves static files from a folder,
such as `GameData/kRPC/web/`. The user opens `http://127.0.0.1:50000/`, or the game machine's
address from a tablet, and the page connects back to its own origin.

- Same origin, so no mixed content in any browser, Safari and iOS included.
- No Local Network Access prompt.
- No certificates.
- It settles the origin check: allow the server's own origin by default, and an allowlist for
  others.
- No help for a dashboard hosted on a public `https://` site.

### Server phase: TLS

`wss://` for a dashboard on a public `https://` site:

- **A user's certificate.** A PEM or PFX file named in the server settings, such as a Let's
  Encrypt certificate for the user's own domain.
- **A self-signed certificate the mod generates.** A failed `wss://` handshake shows no warning
  page, so the user first opens `https://host:port/` in a tab and accepts the certificate there.
  The server answers that request. Exceptions expire in some browsers, and iOS needs a trusted
  certificate profile. The guide documents the steps.
- Check first that Unity's Mono, in KSP, can run an `SslStream` server and generate a
  certificate. KSA runs on .NET 10, where both are standard.

Ruled out:

- **Per-user publicly trusted certificates**, as Plex does with `*.plex.direct`. The only seamless
  option for a hosted page and a game on another machine, but it needs a kRPC-run DNS and
  certificate service. One certificate shipped in the mod would be revoked once its key leaked.
- **A root certificate installed by the mod**, as mkcert does. It needs admin rights, Firefox
  keeps its own store, phones need manual steps, and a root key on disk is a risk.

## Open items

- **Local socket on Windows, unverified, not scheduled.** Node's `net.connect({ path })` takes only named pipes on
  Windows, and libuv has no Unix-domain sockets there. The server's local socket on Windows is a
  Unix-domain socket. A Node client on Windows may then get TCP and not the local socket, short of
  a native add-on. Check before the Node transports phase.
- **Origin check, not scheduled.** The server ignores the `Origin` header of a WebSocket upgrade, so any web page
  open in the player's browser can connect to the game. Until the pages phase, the guide
  recommends the server's connection approval for a game with a browser open.
- **Windows CI, phase 7.** The client's job is in the Windows matrix, but has not run yet.
  `rules_js` supports Windows with caveats.
