# krpctools Test Results

**Status:** in progress.

"This crate" is the third-party Rust client [kladd/krpc-client](https://github.com/kladd/krpc-client),
in a local checkout on its `krpctools-testing` branch, which is not pushed. Paths such as
`tools/clientgen_rust/` and `conformance/testee` are in that checkout.

Results for [krpctools-test-plan.md](krpctools-test-plan.md). Tested against `krpc` main at
`a07f1a177`, krpctools 0.8.0, built with `bazel build //tools/krpctools:krpctools
//client/python:python-pypi`. From step 4, krpctools comes from the `krpctool-rust-test-fixes`
branch of `krpc`, which fixes the findings below. That branch is not pushed.

## krpc Branch

`krpctool-rust-test-fixes`, off main at `a07f1a177`. Each commit passes `bazel build //...` with
a clean log and `bazel test //:test`. The client conformance targets pass after each
conformance change. Each change has an entry in `changelog.d/krpctool-rust-test-fixes.md`.

| Commit | Change |
| --- | --- |
| `aebc0bf30` | Rename the LiDAR assembly, namespace, project and files to `KRPC.LIDAR` (breaking) |
| `946bea666` | Ship `TestService2.json` and `ConformanceService.json` in krpctools |
| `68aa6de0f` | Add `TestService.SparseEnum` and `test_values.py::test_enum_declared_values` |
| `41414259c` | Rename the `Rate` testee command to `GetRate` (breaking for testees) |

## Protocol Files Across Languages

Prompted by the `testee.proto` clash with rust-protobuf, `krpc.proto` and `testee.proto` were run
through each generator built into protoc 36.2, the version krpc pins. Main's `testee.proto`, with
`rate`, and the branch's, with `get_rate`, were both checked.

- Every generator runs with no error or warning: C++, C#, Java, Kotlin, Objective-C, PHP, Python
  (and `.pyi`), Ruby (and `.rbs`), and Rust.
- krpc's own build compiles both files in C++, C#, Java and Python, and `krpc.proto` with nanopb
  and its Lua generator.
- Protobuf's own Bazel rules, in a worktree of `protobuf` at `v36.2`, compile the rest:
  - Rust, with the upb and C++ kernels: all three files compile. protoc's Rust generator does not
    have rust-protobuf's `set_rate` clash.
  - Kotlin, and the Java and Java lite code under it: all three files compile.
  - Objective-C needs Apple's Foundation, so it was not compiled.
- Ruby 3.2 with the `google-protobuf` 4.36.2 gem, and PHP 8.3 with the pure PHP
  `google/protobuf` 5.36.2 runtime, load all three files. PHP lints every generated file. In
  both, every message (28 in `krpc.proto`, 62 in `testee.proto`) encodes, decodes and converts
  to and from JSON. Each file loads in a process of its own, as both testee files define one
  package.
- Where a field or class name is reserved in a language, protoc renames it: `hash_p`,
  `description_p` and others in Objective-C, `PBObject`, `PBList` and `PBClass` in PHP,
  `float_` and others in C++, `Items_` and `Entries_` in C#, and backticks for `null` and
  `object` in Kotlin. These compile.
- **krpctools gap** (minor): `Command` has fields named `hash` and `object_id`, which are methods
  of every Ruby object. Ruby's runtime skips the accessor for a field whose name an existing
  method has (`ruby/lib/google/protobuf/ffi/message.rb`). With the `hash` command set,
  `command.hash` gives Ruby's integer object hash, `command["hash"]` gives the `Hash` message,
  and JSON reads and writes the field as `hash`. `object_id` is the same. A Ruby testee works,
  but has to use `[]` for both.
- Generators outside protoc, such as rust-protobuf, prost, swift-protobuf, protobuf-es, Go's
  `protoc-gen-go` and Dart's, were not checked. rust-protobuf is the one that failed.

## Setup

- Both sdists install into a venv with pip. `krpc-testserver` runs on the system .NET runtime.
- Every entry point runs `--help`. `krpc-servicedefs`, `krpc-clientgen` and `krpc-docgen` print
  `v0.8.0` for `--version`.
- The package holds `bin/ServiceDefinitions`, `bin/TestServer/{linux-x64,win-x64}`,
  `conformance/testee.proto` and the conformance tests. It also ships `test/` with
  `TestService.json`, `KRPC.json` and the clientgen and docgen golden files.
- With `PATH` empty, the tools still find .NET in `/usr/lib/dotnet`. With no .NET found, the
  error names the runtime to install and `DOTNET_ROOT`, and exits 1.

### Findings

- **krpctools bug**: `krpc-conformance --version` is not an option. It fails with "the testee
  command is required".
- **krpctools bug**: `krpc-testserver --version` prints `TestServer.exe version 0.0.0`. The
  assembly version is not stamped, and the program name is the .NET one, not `krpc-testserver`.

## 0. Protocol Update

### Before the update

The unchanged crate (protocol version 1) against `krpc-testserver`:

```
connect error: Server protocol version 0 is not supported; this client requires protocol version 1
```

The server log has the real cause:

```
Refused a connection from 127.0.0.1: Failed to parse the connection request: While parsing a
protocol message, the input ended unexpectedly in the middle of a field.
```

- **client**: the server replies with a `MALFORMED_MESSAGE` connection response inside a `Message`
  envelope. The v1 crate parses the envelope as a bare `ConnectionResponse`, finds no status and
  protocol version 0, and reports the wrong error.
- **docs**: the protocol version table says an unaccepted version "may be refused with the status
  `WRONG_PROTOCOL_VERSION`, or may fail to connect". A v1 client gets `MALFORMED_MESSAGE` in an
  envelope it cannot read. The docs could say so, as this is what every existing third-party
  client sees on 0.8.

### After the update

Checked with scratch programs against `krpc-testserver`, with `TestService` stubs generated from
`krpctools/test/TestService.json`:

- Handshake at version 2, `KRPC.GetStatus` and `KRPC.Clients` structures.
- 1600 calls from 8 threads (8 tasks with `tokio`) on one connection, each response matched to
  its request by id.
- A `Counter` stream updating during those calls, `wait`, `wait_timeout`, and removal on drop.
- A server exception, and nullable arguments and results.
- Dropping the client sends `Disconnect`. The server logs `disconnected (Closed)`.
- Stopping the server fails the next call with `Disconnected (ConnectionLost)`, and wakes stream
  waiters.

In KSP, with main's mod from `bazel run //:run-ksp -- --load-game=krpctest`, both examples run.
`streams` prints 10 updates of `UT` at 1 Hz. `client` greets the crew of a launched `AutoPilot`.

`cargo clippy` reports only the `mutable_key_type` warnings it reported before the change: three,
and five with `tokio`. The doctests pass, including one that failed before.

### Findings

- **client**: `build.rs` only declared `proto/krpc.proto` as an input. A change to
  `service_definitions/` or to `KRPC_SERVICES` did not regenerate the services. Fixed.
- **client**: the crate cannot compile `TestService`. Object types lack `Hash` and `Eq`, so a set
  or dictionary key of objects fails to compile. Fixed: objects and enums now implement `Eq` and
  `Hash`, and a dictionary key no longer needs `Default`.
- **krpctools**: `krpc-testserver` exits on SIGINT without sending `Disconnect` to its clients, so
  a client sees a lost connection rather than `SERVER_STOPPED`. Check whether this is intended.
- **docs**: `krpctools/test/TestService.json` ships in the package, which is useful to a client
  author. No page mentions it.

## 1. servicedefs

Run against the DLLs in `KSP/GameData/kRPC`, from `bazel run //:run-ksp` at the tested commit,
with `--reference-dir=../KSP/KSP_Data/Managed`.

- Every service regenerates byte-identical to the `.json` shipped beside its DLL: `KRPC`,
  `SpaceCenter`, `UI`, `Drawing`, `InfernalRobotics`, `KerbalAlarmClock`, `RemoteTech`,
  `DockingCamera`, `LIDAR` and `Debug`. It also matches the committed `service_definitions/`, so
  the crate needs no rebuild here. Step 0 already took in the schema changes since v0.7.0.
- Every service except `KRPC` and `SpaceCenter` needs `KRPC.SpaceCenter.dll` passed as well.
  `Drawing` also needs `KRPC.UI.dll`. The order of the assemblies does not matter.
- `KRPC` from the `KRPC.Core.dll` bundled in `krpctools/bin` matches GameData's.
- `KRPC.Benchmark.dll` ships in GameData with no `.json`, and generates fine.
- `StdLib` has no DLL. GameData ships `KRPC.StdLib.json`, which a third party can copy.
- Documentation is present for all 1464 `SpaceCenter` procedures.
- `KRPC.MechJeb`: not tested, as the Genhis mod DLL is not to hand.

Errors:

| Case | Result |
| --- | --- |
| Unknown service | `Error: Service Nope not found`, exit 1 |
| Missing DLL | `Error: Assembly '.../Nope.dll' not found.`, exit 1 |
| Not an assembly | `Error: Failed to load assembly '...'. Bad image format.`, exit 1 |
| Reference directory does not exist | `Error: Reference directory '/nonexistent' does not exist.`, exit 1 |
| No `--reference-dir` | Unhandled `FileNotFoundException` for `Assembly-CSharp`, 13-line stack trace, exit 1 |
| Missing dependency assembly | Unhandled `ServiceException`: "In service UI: Service does not exist, when loading enumeration", stack trace, exit 1 |
| `-o` into a directory that does not exist | Python traceback ending in `FileNotFoundError`, exit 1 |

### Findings

- **krpctools bug**: a missing `--reference-dir` gives an unhandled .NET exception. The error
  should say that the service references game assemblies, and name the option.
- **krpctools bug**: a missing dependency service gives an unhandled exception. The message names
  the service but not the assembly to add. The `--help` hint ("any dependencies required to load
  it") is the only clue.
- **krpctools bug**: an unwritable `-o` path gives a Python traceback.
- **krpctools gap**: the `LiDAR` service has been named `LIDAR` since v0.7.0 (#1149), but its
  assembly and JSON are still `KRPC.LiDAR.*`. `krpc-servicedefs LiDAR KRPC.LiDAR.dll` fails with
  "Service LiDAR not found". The error could list the services the assemblies hold, or suggest a
  name that differs only in case. The `krpctool-rust-test-fixes` branch of `krpc` renames the
  assembly and its files to `KRPC.LIDAR.*`, and this crate's definition file to match.
- **krpctools gap**: without the `.xml` beside the DLL, the output has empty documentation and
  the tool gives no warning.
- **krpctools bug** (minor): stdout output ends with a newline that the `-o` file lacks.

## 2. clientgen

The generator is `tools/clientgen_rust/rust.py` and `rust.tmpl`, a plugin `krpc-clientgen`
loads by path. It writes the module of one service, with the API `krpc_build` generates, so the
crate can ship its stubs as source rather than generate them in `build.rs`. Each method is
generated for both the blocking and the `tokio` build, behind `#[cfg(feature = "tokio")]`, so
one set of files serves both. Unlike `krpc_build`'s, the stubs carry the documentation.

```sh
tools/clientgen_rust/generate.sh service_definitions out/clientgen
KRPC_STUBS=$PWD/out/clientgen cargo build
```

`generate.sh` runs `krpc-clientgen tools/clientgen_rust/rust.py <Service> <defs...>` for each
service, and `KRPC_STUBS` makes `build.rs` use those files in place of `krpc_build`.

Crate changes, on its `krpctools-testing` branch:

- `2307e27`: the streams call the internal procedures by hand, in `src/internal.rs`.
- `d1d5539`: the generator, `generate.sh`, `apidiff`, and `KRPC_STUBS` in `build.rs`.

- **Same API.** `tools/clientgen_rust/apidiff` lists every item and its tokens, without
  documentation and deprecation attributes. It was run on `krpc_build`'s output and on
  clientgen's, for both values of the `tokio` feature. Across all 12 services, about 8,900
  items each, they are token for token the same, apart from the 21 stubs of the internal
  procedures, below. These are `pub(crate)` in `krpc_build`, so the public API is unchanged.
- **Builds.** The crate and its examples build on the generated stubs. `cargo clippy` gives the
  same 3 warnings as with `krpc_build` (5 with `tokio`). `cargo doc` gives no warnings, so
  every `<see cref>` resolves as an intra-doc link.
- **Conformance.** The testee, built on stubs generated from `conformance/services`, gives the
  same result as with `krpc_build`: 220 passed and 37 expected failures.
- **Loading.** The plugin loads from a relative path, a path with `~`, and a path with an
  environment variable. A module beside it (`rust_naming.py`) imports, as the plugin's
  directory is put on the module path.
- **Hooks.** The base generator gives what the plugin needs: a `Language` for type names and
  casing, `DocParser` for the documentation, `parse_cref` and `format_cref` for links,
  `parse_deprecation_reason` for deprecation notes, and nullability on each type. Default values
  were not needed, as the crate's stubs take every argument.
- **Markup.** Unknown tags and crefs give `DocumentationMarkupWarning` through the plugin's
  parser, and `<math>` and `<unit>` render as text.
- **Cross-service types.** `SpaceCenter` generates with every definition file passed, or with
  only `KRPC.Core.json` beside it. With `SpaceCenter` alone, its crefs to `KRPC` types warn, as
  they do with the C# generator. `--include` does not apply, as Rust names the other services
  by path.
- **From a DLL.** `SpaceCenter` from `KRPC.SpaceCenter.dll` with `--output-defs` gives the same
  file as from the JSON, byte for byte, and the definitions it writes match the shipped JSON.

### Findings

- **krpctools gap**: the definitions clientgen hands a generator leave out every internal
  procedure (`krpctools/definitions.py`, from `85ec54795`), and a plugin cannot get them back.
  The crate's streams call `AddStream`, `SetStreamRate` and `RemoveStream` through the stubs
  `krpc_build` generates, so the crate did not compile on clientgen's stubs. The in-tree C#
  client calls them by hand (`InternalProcedures.cs`), and the crate now does the same
  (`src/internal.rs`). A middle ground: leave them out unless `--internal` is passed, which
  generates only the internal procedures, in a namespace that only the client reaches (in Rust,
  `pub(crate)`). Then they are hidden from user code, but a client need not write them by hand.
- **krpctools bug**: `load_generator` takes the module name with `rstrip(".py")`, which strips
  the characters `.`, `p` and `y`, not the suffix. `happy.py` loads as `ha`: "No module named
  'ha'".
- **krpctools bug**: `load_generator` appends the plugin's directory to `sys.path`, so a module
  of the same name earlier on the path wins. `token.py` loads the standard library's `token`:
  "module 'token' has no attribute 'generator'". It should insert the directory first, or load
  the file with `importlib.util.spec_from_file_location`.
- **krpctools gap**: the plugin's `tmpl` is opened relative to the working directory, not the
  plugin. `tmpl = "rust.tmpl"` fails with `FileNotFoundError` unless run from the plugin's
  directory, so the plugin builds the path from `__file__`. The Jinja loader also searches `./`,
  so an `{% include %}` or `{% import %}` in a plugin's template resolves against the working
  directory (by reading `generator.py`, not tested).
- **docs**: no page describes the plugin form. `clientgen.rst` shows it only in the `--help`
  text. An author has to read `generator.py` and a built-in generator to learn the module's
  `generator` and `tmpl` attributes, the methods to override (`parse_context`,
  `parse_documentation`, `format_cref`), the context keys, and that `Language.parse_type` is
  called with `None` for a procedure that returns nothing. The plugin's first run failed there
  with an `AttributeError` traceback.
- **krpctools gap** (minor): the context groups procedures by kind, keyed by the generated name.
  The crate's rule for a method whose name a property accessor already takes (`_by_<params>`)
  needs every procedure's definition name, so the plugin reads the private `_defs`.
- **client**: the crate's names come from `convert_case`, which splits at digits: `atan_2`,
  `log_10`, `string_to_u_int_32`, `custom_axis_01`. krpctools' `snake_case`, which the Python
  client uses, gives `atan2` and `string_to_u_int32`. 25 of 1927 names differ. The plugin keeps
  the crate's names, as changing them breaks the API.
- **client**: `krpc_build` puts the raw XML of a deprecation reason in the `note`: `Use <see
  cref="M:SpaceCenter.Orbit.SpeedAt" /> instead.` The plugin gives `Use Orbit.speed_at instead.`

## 3. docgen

Pages for `SpaceCenter`, `KRPC` and `StdLib`, one template each, with every class,
enumeration, structure and exception of the service on the service's page. The templates and
order file are in `out/docgen` (not committed). Sphinx 9.1.1, sphinx-csharp 1.0.0, sphinx-java
1.0.0 and sphinx-lua-ls 3.12.1, the versions krpc pins, in a venv of their own.

```sh
krpc-docgen python order.txt KRPC.SpaceCenter.json KRPC.Core.json KRPC.StdLib.json \
    --page space-center.tmpl python/space-center.rst --page krpc.tmpl python/krpc.rst \
    --page stdlib.tmpl python/stdlib.rst --documented python/documented.txt
sphinx-build -q -b html sphinx/python sphinx/python/_build
```

The Rust domain is `tools/docgen_rust/rust_domain.py` and `rust.tmpl`. krpc-docgen has no
plugin form, so `tools/docgen_rust/docgen.py` adds the domain to `DOMAINS`, replaces
`generate` to find the macros beside the domain, and then runs `krpc-docgen`'s `main`:

```sh
python tools/docgen_rust/docgen.py rust order.txt <defs...> --page space-center.tmpl rust/space-center.rst
```

The pages use the `rust` domain of sphinxcontrib-rust 1.3.0, with each item named by its path in
the crate: `krpc_client::services::space_center::Vessel::get_name`. The domain reuses the
clientgen plugin's naming and types, so the pages name what the stubs generate.

- **Ordering.** The doc's workflow works: an empty order file stops with every missing member
  (1401 for `SpaceCenter`), on stderr after an `Error: Don't know how to order:` line, and exits 1.
  An entry for a member that does not exist is accepted silently.
- **`--documented`.** Lists each member, type, enumeration value and structure field the pages
  cover, the same 1842 names for all seven languages. Checked against every name in the three
  definition files: none is left out.
- **`@FILE`.** Arguments read from a file give the same page, including a path with a space.
- **All six languages** generate with no warning.
- **Sphinx, default mode.** With the extensions the doc lists, C++, C, C# and Java build with
  no warning but sphinx-lua-ls's notice that its default backend will change (krpc sets
  `lua_ls_backend = 'disable'`). Python gives 1057 warnings, below.
- **Sphinx, nitpicky mode** (`-n`; krpc does not build its docs with it). Most warnings are
  types the pages never declare: builtins (`int32_t`, `number`, `boolean`) and the client's own
  types (`Client`, `IConnection`, `Connection`, `org.javatuples.Triplet`, `krpc_error_t`).
  krpc's `conf.py` lists the C, C# and Python ones in `nitpick_ignore`. One more set, in C++,
  is a bug, below.
- **Rust domain.** The pages generate with no warning and build with none, in default and
  nitpicky mode. All 6156 anchor links in the HTML resolve. The 1678 methods the pages document
  are exactly the public methods of the clientgen stubs for the three services. Properties give
  a `get_` and a `set_` method, as in the crate. Exceptions have no Rust type, so they render as
  text.
- **sphinxcontrib-rust** (not krpc) builds a Rust binary when installed, so needs `cargo` on
  `PATH`. It runs its `sphinx-rustdocgen` at every build, even with no crates configured, and
  fails without one. `rust_rustdocgen = '/usr/bin/true'` works around it.

### Findings

- **krpctools gap**: `krpc-docgen` takes a language only from its fixed `DOMAINS`, and finds
  a language's macros with `files(__name__)`, inside its own package. A Rust page needs both
  replaced (`tools/docgen_rust/docgen.py`, 30 lines). The proposed change: take a path to a
  module in place of a language, as clientgen does, with a `domain` class and a `macros` path.
  The base `Domain` (`krpctools.docgen.domain`) is enough to build on. A domain also needs
  every procedure to name methods as the clientgen plugin does (the `_by_<params>` rule), and
  `Domain` is built with only the macros path. The wrapper sets the services on the class
  first. Passing `services` to the domain would remove that. The clientgen fixes for
  `rstrip(".py")` and `sys.path.append` apply to the new loader too.
- **krpctools bug**: a `<see cref>` to a service whose definitions are not passed crashes with
  a `KeyError: 'M:KRPC.GameScene'` traceback (`docgen/utils.py`, `lookup_cref`). The doc says
  to pass every service the documentation links to, but the error should name the cref and the
  missing service. clientgen warns and carries on in the same case.
- **docs**: every service passed only for its links must be in the ordering file as well:
  passing `KRPC.Core.json` for `SpaceCenter`'s links stops docgen on 238 `KRPC` members. The
  doc does not say so. Either the doc says it, or docgen orders only the services a page
  documents.
- **krpctools bug**: Python types link to enumeration values. Each `:param float x:` and
  `:rtype: float` resolves to an attribute named `float`. With `SpaceCenter` alone, all 914
  link to `SpaceCenter.FieldType.float`, with no warning. With `KRPC` too, 912 link to
  `KRPC.TypeCode.float` and Sphinx warns 1056 times ("more than one target found for
  cross-reference 'float'"). krpc's own `conf.py` hides this with a `PythonDomain` subclass that
  refuses to resolve builtin names. The doc does not mention it, and a third party's pages link
  wrongly. The fix belongs in the generated text, for example `:rtype: :py:class:`~builtins.float``.
- **krpctools bug**: in Lua, a type named like a member of the class it is in links to that
  member. In `Stage`, the `number` type of `delta_v`, `vacuum_delta_v` and others links to
  `Stage.number`. krpc's own built docs have it: `lua/api/space-center/stage.html` has 19
  links to `#lua-SpaceCenter.Stage.number`.
- **krpctools bug**: in C++, a page with `macros.service` and the service's own types loses the
  links to those types. On one `SpaceCenter` page, 138 references to `AxisRange`,
  `MitigationMode`, `SASMode` and others do not resolve: plain text in default mode, warnings
  in nitpicky mode. Split into a service page and a types page, as krpc's docs are, they
  resolve. The service macro sets `.. namespace:: krpc::services` and declares the class
  `SpaceCenter`, and the types are then declared in a namespace of the same name. The doc says
  a page can hold any of the macros.
- **krpctools bug** (minor): with no services in the definitions, docgen prints "No services
  found in services definition files" to stdout, with no `Error:` prefix.

## 4. Conformance

Run with krpctools from the `krpctool-rust-test-fixes` branch of `krpc`, which has the fixes
below. The testee is in `conformance/`: a crate of its own, using the blocking API, with the
`core` profile over `tcpip`.

- `build.rs` generates the testee protocol types with `protobuf-codegen`. It reads and writes
  the proto3 JSON with `protobuf-json-mapping`.
- It also generates the dispatch from the same definitions the crate's stubs come from, with
  `krpc_build`'s naming rules, so each `Invoke` calls the stub method.
- A run takes 70 seconds: 220 passed, 37 expected failures (21 lines), and 4 unsupported tests.
  The other 456 skips are outside `core`.
- The testee replies `UNSUPPORTED` to `Order`, to `Close` with `interrupted`, to named arguments,
  to a call through an object, and to a missing argument, as the stubs take no defaults.
  `Members` replies null, as the testee cannot list the stubs' names. `FailWrite` replies with
  an error that is not `UNSUPPORTED`, as the proto asks of a client with no write fault.

```sh
krpc-conformance --testee conformance/testee/target/debug/testee \
    --expected-failures conformance/expected-failures.txt \
    --unsupported conformance/unsupported.txt
```

Crate changes made for the testee, on its `krpctools-testing` branch:

- `bb74a1e`: objects and enums implement `Eq` and `Hash`.
- `b0d031d`, `b206edd`: objects have `id()` and `from_id()`, and the codec is public with the
  `conformance` feature.
- `7af3e15`: each enumeration variant takes its declared value.

Not yet checked from the plan:

- Profiles past `core`, the `tokio` feature, and `--conventions`.
- Fixes for the client bugs below.

### Driver

Each check runs the Rust testee, or a Python proxy around it that breaks the protocol in one
way, over a `-k` selection. The lists are copies of the testee's with one line added.

What works as documented:

- **Expected failures:** a listed test that passes fails the run as `XPASS(strict)`. A line
  naming no test or no case stops the run before any test with `Listed tests name no test`.
  `@flaky` lets a listed test pass or fail. `@skip` skips it. `@<protocol>` applies a line only
  over that protocol, and an unknown protocol stops the run.
- **Unsupported:** a listed test that runs fails with "The test is listed as unsupported, but
  ran". An `UNSUPPORTED` reply in an unlisted test fails it, naming the reply. A test in both
  lists, or an unsupported line with a flag, stops the run. A listed test that fails for another
  reason fails normally.
- **pytest pass-through:** `-k`, `-x`, `-v`, `-rx` and `--co` all reach pytest.
- **`--server`:** both the bundled `TestServer.dll` and the `krpc-testserver` launcher work. A
  missing path gives `FileNotFoundError`, and a program that is not a server gives "the server
  exited with 0 before it was ready". The driver always starts the server itself. It has no
  option to use one already running, which the plan assumed.
- **Testee faults**, each a clear `TesteeFailed`, with the testee replaced for the next test:
  - Exits before `Hello`: "The testee exited before writing a Hello", at once, with its stderr.
  - Writes a log line before `Hello`: "The testee wrote a line that is not a message:
    b'Starting the testee...\n' before writing a Hello".
  - Writes nothing, even ignoring the close of stdin: "The testee wrote no Hello" after the
    60 second `Hello` timeout, and the process is killed.
  - Omits `Hello` and otherwise behaves: the same error after the same timeout.
  - Crashes on a call: "The testee exited". Every following test gets a new testee.
  - Writes junk after `Hello`: the line, as above.
  - Hangs on a call: "The testee did not reply within 10 seconds".
- **Hello:** an unknown profile stops the run with "rust reports unknown profiles
  teleportation".
- **`--profiles`:** a file whose profiles differ from the `Hello` stops the run, naming both.
- No run left a testee or server process behind.

### Findings

- **krpctools bug**: the package ships only `TestService.json`. A testee whose client generates
  its stubs ahead of time also needs `TestService2` and `ConformanceService`, which the tests
  call. Before the fix, the only way to get them was `KRPC.GetServices` on a running server,
  and krpctools has no tool that writes that result in the JSON format. The
  `krpctool-rust-test-fixes` branch of `krpc` now ships `TestService2.json` and
  `ConformanceService.json`. They match what the server sends. The rest of this section uses
  that package.
- **krpctools gap**: `test_class_extension_members` is a `core` test, but the shipped
  `TestService.json` leaves out the five extension members the server defines in `TestService`,
  such as `TestClass_ExtensionMethod`. The build leaves them out on purpose, so that a client
  that loads definitions from the server when it connects (Python) has to pick them up there. A
  client that generates its stubs ahead of time (C++, Java, C#, cnano, Rust) cannot pass the
  test, and each in-tree testee lists it as an expected failure. Both paths need a test:
  - Only the base definitions shipped, with the extensions from the server at connect. This only
    works for a client that builds its stubs at connect time, so the test belongs under the
    `dynamic` profile.
  - Every definition, extensions included, shipped as JSON. This works for every client and
    belongs in `core`. krpctools would need to ship a second, complete `TestService` definition.

  The Rust testee lists the test as an expected failure.
- **krpctools bug**: the same test calls the extension members on a service named
  `TestServiceExtensions`, which the server does not define. The server has them in
  `TestService`. The Python testee passes only because it finds an instance method on the
  object and ignores the service name. A testee that dispatches on the service name cannot find
  them.
- **krpctools gap**: the test server's `TestService` and `ConformanceService` definitions come
  from a separate net472 build, which matches the game's build of a service. The test server does
  not run in KSP, and `krpc-servicedefs` runs on net10.0 against its own net10 `KRPC.Core`. The
  server already compiles these sources for net10.0, so they could be built for net10.0
  against `KRPC.Core.net10` rather than kept in a separate net472 library. The C# client's
  netstandard2.0 is not an option without a netstandard build of `KRPC.Core`. The separate build
  also keeps the extension members out of `TestService.json`, so this change goes with the one
  above. Fixed: `TestService` builds for net10.0 against `KRPC.Core.net10`, and the definitions are
  byte-identical. It stays an assembly separate from the server, so the extension members stay out
  of `TestService.json` and the gap above stays open.
- **client**: the crate cannot carry out three `core` testee commands through its public API.
  Objects keep their id private, and have no way to be made from an id. That rules out
  `ObjectId` and an `Object` value with handle 0 (`test_get_object_id`,
  `test_object_id_range`, `test_unknown_object_id`). The encoder and decoder
  (`EncodeUntagged`, `DecodeUntagged`) are in the private `schema` module, which rules out
  `Encode` and `Decode`, so every test in `test_codec.py` fails. Fixed: objects have `id()`, as
  every other client has a helper for `Expression.ConstantObject` (#1160), and `from_id()`. The
  codec is public only with the `conformance` feature, as only the testee needs it.
- **docs**: the codec requirements are `core`, and test "the client's encoder". The docs do not
  say whether a client must make it public, or may give only its testee access, as this crate
  now does with a feature.
- **client**: the crate failed to compile `TestService`, as noted in step 0. Fixed.
- **client bug**: `krpc_build` ignores the values an enumeration declares, and `rpc_enum!` numbers
  the variants from 0 in order. Every enumeration whose values are not 0 to n encodes and decodes
  wrong: `KRPC.TypeCode` (1 to 303), `SpaceCenter.MapFilterType` (-1 and powers of two),
  `SpaceCenter.EditorFacility` (1, 2, 0), `InfernalRobotics.ServoMode` (1, 2) and
  `MechJeb.AscentLaunchMode` (0, 1, 2, 99). For example, `EditorFacility.VAB` is sent as 0, which
  the server reads as `None`. Fixed: each variant takes its declared value.
- **krpctools gap**: the conformance tests do not catch the bug above. Every enumeration in
  `TestService` has the values 0 to n, so a client that ignores the declared values passes.
  The `krpctool-rust-test-fixes` branch of `krpc` adds `TestService.SparseEnum`, with the values
  2, -1 and 100, and `test_values.py::test_enum_declared_values`, which sends and reads each one.
- **krpctools bug**: `testee.proto` does not compile with rust-protobuf 3.7 (`protobuf-codegen`,
  pure Rust). `Command` has the fields `set_rate` (`SetRate`) and `rate` (`Rate`). rust-protobuf
  gives a oneof field `foo` the getter `foo()` and the setter `set_foo()`, so `set_rate` is defined
  twice: `error[E0592]: duplicate definitions with name 'set_rate'`. The plan's check that the
  shipped proto is usable outside Python fails here. The branch renames the `Rate` command to
  `GetRate`, in the proto, the driver and the Python, C++, C# and Java testees. The cnano, Lua
  and websockets testees have no streams. With that, `protobuf-codegen` compiles the proto, and
  `protobuf-json-mapping` reads and writes the driver's JSON.
- **docs**: rust-protobuf's JSON parser rejects an escaped surrogate pair, such as `\ud83d\ude80`,
  which the driver writes for a character outside the Basic Multilingual Plane. The testee
  passes each line through `serde_json` first. `conformance.rst` could say that the driver
  escapes non-ASCII characters.
- **client bugs**, each in `conformance/expected-failures.txt`:
  - A message holding a case the protocol does not define ends the connection, where it should
    be skipped. This also fails reading a message whose read holds the start of the next one.
  - A malformed message, a message the client sends, a size prefix over five bytes, or a size
    over 32 bits each end the connection with a `Disconnect` reason of `CLOSED`. The reason
    should be `MALFORMED_MESSAGE` or `PROTOCOL_ERROR`. After a bad size prefix, the next call
    waits forever.
  - A response whose id matches no request is dropped, and the call waits forever. It should
    fail the connection.
  - The client has no handshake or stall timeout, so a server that stops sending hangs it.
  - Closing does not wait for the server to close the connection.
  - An error for the whole request has the message `.: Oops`, as it has no service or name.
  - A server error's message leaves out the stack trace.
  - A result with `is_null` set and a value decodes as null. Data after a null in a list
    decodes.
  - `krpc_build` generates a tuple of one item as the item alone. The codec has no 1-tuple.
- **client gap**: a static method of a class is generated as a method that takes an instance.
  The testee calls one on `Class::from_id(client, 0)`.
- **client gap**: Rust has no null for a type other than `Option`, so the null argument tests
  are unsupported. Generated structures do not implement `Hash`, as a field can be a float.
- **docs**: `krpc-conformance` has a `--profiles PATH` option, a file of the profiles and
  protocols the testee must report. `conformance.rst` does not mention it.
- **krpctools bug**: an expected failure is met by any failure, including a crash or hang of the
  testee. With a testee that exits on every call, `-k test_request_error` passes (exit 0) as
  `XFAIL`, and a whole `-k test_errors` run reports all 13 listed tests as `xfailed`. A
  regression that crashes the testee in a listed test goes unnoticed, though the list is meant
  to keep it honest. The driver could mark them `xfail(raises=...)` with the assertion and
  `TesteeError` types, so that `TesteeFailed` still fails the test.
- **krpctools bug**: a line whose file name matches no test file is never checked. With
  `test_error.py::test_request_error` (no `s`) or `test_nothing.py::test_x`, even a run with no
  `-k` accepts the list. Only files that were collected are checked, so that a run of some files
  leaves the others alone. The check could use the files in `tests/` instead. In the same way,
  a line for another protocol, such as `test_errors.py::test_no_such@websockets`, is checked
  only over that protocol.
- **krpctools bug**: the flags are read in one order only. `X @skip @flaky` works, but
  `X @flaky @skip` stops the run with "lists X for an unknown protocol flaky". `X @FLAKY` gives
  the same error. The docs give no order.
- **krpctools bug**: the driver does not check the protocols in `Hello`. A testee that reports
  the protocol `carrier-pigeon`, or no protocols at all, runs the `tcpip` tests. Without
  `--profiles`, the protocol under test is not checked against `Hello` either. With
  `--profiles`, the file's protocol lines are ignored: a file of `core` and `websockets` passes
  a `tcpip` run of a testee that reports only `tcpip`.
- **krpctools gap**: `core` tests have no profile marker, so they run whether or not the
  testee reports `core`. A testee with no profiles at all passes them. The driver could require
  `core`, or the docs could say it is implied.
- **krpctools bug**: in the `--profiles` file, an unknown name such as `teleport` is reported
  as a mismatch with the `Hello`, not as an unknown profile. A `#` comment is read as a profile
  name, though both list files take comments.
- **krpctools bug**: a missing `--expected-failures` or `--unsupported` file gives a 69-line
  `INTERNALERROR` traceback ending in `FileNotFoundError`, with exit 3. A missing conventions
  file is no better: its `UsageError` is raised in a fixture, so pytest reports it as a 52-line
  error against the test, and does not stop the run.
- **krpctools bug**: a server that fails to start does not stop the run. Each test reports the
  same error: 670 errors in a full run. The profiles check already stops the run with
  `pytest.exit`, which suits this too.
- **krpctools gap**: `krpc-conformance --help` does not say that other options go to pytest.
  `--protocol`, `--expected-failures`, `--unsupported`, `--profiles` and `--conventions` have no
  help text, and `--protocol` has no choices: `--protocol tcp` is rejected by pytest, as
  `pytest.main(): error: argument --protocol: invalid choice`.
- **krpctools gap**: a testee that hangs before `Hello`, or replies before it, takes the full 60
  second `Hello` timeout. A `Reply` before `Hello` could fail at once. "The testee exited" leaves
  out its exit status.
