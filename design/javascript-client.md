# JavaScript client for the browser

**Status:** in progress. Phases 1 to 3 are implemented on the local branch `js-client`, with
flags enumerations and deprecation signals, and not yet submitted. No GitHub issue yet. The
client's current design is on the docs site, in `doc/src/client-design/js.rst`, and the
"as built" sections below record how each phase landed.

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

Each phase is implementable and mergeable on its own.

| Phase | Adds | Conformance profiles |
| --- | --- | --- |
| 1 | Browser, WebSockets, unary calls, dynamic stubs | `core`, `dynamic`, `defaults`, `connections`, `concurrency`, `websockets` |
| 2 | Error types, named arguments. Structures become classes | `error-types`, `named-arguments` |
| 3 | Generated stubs with TypeScript declarations, docs API reference | — |
| 3b | Enumerations, structures and exceptions importable with no connection | — |
| 4 | Streams, events, callbacks, conditions | `streams`, `events`, `callbacks`, `conditions` |
| 5 | Server side functions built with the `KRPC.Expression` API: streams, events and runs | `functions`, `function-types` |
| 6 | A compiler from JavaScript functions to server side functions | — |
| later | Server: pages served by the mod, an origin check | — |
| later | Server: TLS (`wss://`), with a user's certificate or a generated one | — |
| later | Node.js transports (TCP, local socket) at `@krpc-org/krpc/node`, browser test runs | `tcpip`, `localsocket` |

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

### Phase 6: function compiler

Compiles a JavaScript function into a server side function, as the Python client's compiler does
for Python. It takes the function's source text, parses it, and builds the expression and
statement nodes:

```js
const high = await conn.compile(
  (vessel, limit) => vessel.flight().meanAltitude > limit,
  [SpaceCenter.Vessel, 70000],
);
```

| Python | JavaScript |
| --- | --- |
| `inspect.getsourcelines(func)` | `Function.prototype.toString()`, the exact source text since ES2019 |
| `ast` | `acorn` (MIT, about 20 KB gzipped, ES modules) |
| Statements: `if`, loops, assignment | `if`, `for`, `let`, `const`, `?:`, `&&`, `\|\|` |
| Free names through `__closure__`, `__globals__` | Explicit, as below |
| Parameter types from annotations | Explicit, as below |

Differences from Python:

- **Captured values are positional parameters.** JavaScript has no access to a function's closure
  from outside it. The caller passes each value after the parameter types. A named object such as
  `{ limit }` breaks under a minifier, which renames the body's `limit` and not the key.
- **Parameter types are explicit.** TypeScript erases its types, so there are no annotations to
  read at run time. A parameter takes a remote type, or the type of the value passed for it.
- **One number type.** `1` and `1.0` are the same value, so literals follow the protocol's numeric
  promotion. `1n` is a 64-bit integer.
- **Transpilers.** A compiler to an older target rewrites `?.` and `??` into helper calls. The
  guide asks for an ES2020 or later target for code holding compiled functions.
- **Synchronous member access.** The body runs on the server, so `vessel.flight()` returns a
  `Flight` there, where the client's API returns a `Promise`. This phase adds a second,
  synchronous set of declarations to the generated stubs, for function bodies.

Ruled out:

- **Tracing**, calling the function with placeholder objects that record each operation.
  JavaScript cannot overload `>`, `+` or `?:`, which expressions need most.
- **Tagged templates** as the main form, as in `` conn.fn`vessel.flight().meanAltitude > ${limit}` ``.
  They capture values and survive minifiers, but an editor cannot check or complete the string. A
  second form, if wanted.

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

- **Local socket on Windows, unverified.** Node's `net.connect({ path })` takes only named pipes on
  Windows, and libuv has no Unix-domain sockets there. The server's local socket on Windows is a
  Unix-domain socket. A Node client on Windows may then get TCP and not the local socket, short of
  a native add-on. Check before the Node transports phase.
- **Origin check.** The server ignores the `Origin` header of a WebSocket upgrade, so any web page
  open in the player's browser can connect to the game. Until the pages phase, the guide
  recommends the server's connection approval for a game with a browser open.
- **Windows CI.** The client's job is in the Windows matrix, but has not run yet. `rules_js`
  supports Windows with caveats.
- **npm publishing.** The release builds the tarball as a GitHub asset. Publishing it to npm under
  `@krpc-org` is a release step still to add.
