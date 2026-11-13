# krpctools Test Plan

**Status:** in progress.

"This crate" is the third-party Rust client [kladd/krpc-client](https://github.com/kladd/krpc-client),
in a local checkout on its `krpctools-testing` branch, which is not pushed. Paths such as
`tools/clientgen_rust/` and `conformance/testee` are in that checkout.

This crate is a third-party kRPC client. It serves here as a test bed for `krpctools` from
`krpc` main, used the way an outside client author would use it: installed with pip, driven from
the command line, with no Bazel and no access to the `krpc` source tree.

The goal is to find defects and gaps in `krpctools` itself. Defects found in this crate are
recorded too, but fixing them is secondary.

## Scope

| Tool | What it does | Test here |
| --- | --- | --- |
| `krpc-servicedefs` | Service definition JSON from service assemblies | Regenerate `service_definitions/*.json` |
| `krpc-clientgen` | Client stubs from service definitions | Write a Rust generator plugin |
| `krpc-docgen` | API reference pages, as reStructuredText | Generate pages for the services this crate wraps |
| `krpc-conformance` | Conformance suite against a client, through a testee | Write a Rust testee and run the suite |
| `krpc-testserver` | Game-less server | Used by the conformance step, and by hand |

## Setup

### Rust toolchain

Install with rustup, which puts `cargo` and `rustc` in `~/.cargo/bin`:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --component clippy,rustfmt
. "$HOME/.cargo/env"
cargo --version
```

`protoc` is not needed, as `build.rs` uses the pure Rust `protobuf-codegen`. The `flake.nix` dev
shell is an alternative, but this machine has no nix.

### Build the package

`krpctools` is published as an sdist (`py_sdist` in `tools/krpctools/BUILD.bazel`). pip builds a
wheel from it with hatchling. It requires `krpc >= 0.8.0.dev0`, which is not on PyPI, so the Python
client built from the same commit is installed first.

The `krpc` checkout is on a feature branch, so build in a worktree of `origin/main`:

```sh
cd ../krpc
git fetch origin
git worktree add ../krpc-main origin/main
cd ../krpc-main
bazel build //tools/krpctools:krpctools //client/python:python-pypi
```

Record the `krpc` commit hash in the results. Before removing the worktree, run
`bazel clean --expunge` in it.

### Install

Use a venv local to this crate. `.venv` and `out` are ignored by git:

```sh
python3 -m venv .venv
.venv/bin/pip install ../krpc-main/bazel-bin/client/python/krpc-*.tar.gz
.venv/bin/pip install ../krpc-main/bazel-bin/tools/krpctools/krpctools-*.tar.gz
```

Check:

- [ ] Both packages install from the sdists with no network access beyond PyPI dependencies.
- [ ] Every entry point runs `--version` and `--help`: `krpc-servicedefs`, `krpc-clientgen`,
  `krpc-docgen`, `krpc-conformance`, `krpc-testserver`.
- [ ] The versions match each other and the `krpc` commit.
- [ ] The installed package holds the bundled .NET tools (`krpctools/bin/`), `testee.proto` and
  the conformance tests.
- [ ] The tools that need .NET 10 find the system runtime (`/usr/bin/dotnet`), and give a clear
  error when `dotnet` is off `PATH`.

## 0. Protocol Update

The crate speaks protocol version 1 (kRPC 0.7). The server on main speaks version 2 and accepts
only version 2, so the crate cannot connect to `krpc-testserver` until it is updated. This comes
before every tool test. It is kept on its own commits, as the basis of a later pull request to
the crate.

Before changing anything, connect the crate unchanged to `krpc-testserver` and record the error
it gets. This is the first contact a third party has with a new server.

The changes, from `protobuf/krpc.proto` and `doc/src/communication-protocols/` on main:

- **One connection.** The separate stream connection is gone, with `ConnectionRequest.type` and
  `client_identifier`. `Client::new` drops `stream_port`, an API break.
- **Envelope.** Every frame is a varint-length-prefixed `Message`, a oneof of the handshake,
  `Request`, `Response`, `StreamUpdate` and `Disconnect`.
- **Request ids.** `Request.id` and `Response.id` match a response to its request. Stream updates
  arrive between responses on the same socket, so the crate needs one reader that routes each
  message. This replaces the mutex-per-socket design in `src/client.rs`, for both the blocking
  and the `tokio` builds.
- **Disconnect.** The server sends a reason before it closes the connection. Map it to an
  `RpcError`.
- **Handshake status.** `WRONG_TYPE` is gone and `DENIED` is new.
- **Streams and events.** A `STREAM` or `EVENT` value is now a bare `uint64` stream id. The
  `Stream`, `Event` and `Status` messages are gone. `krpc_build` and the codec in `src/lib.rs`
  map these types to `schema::Stream`, `schema::Event` and `schema::Status`, and need changing.
- **Status.** `KRPC.GetStatus` returns a structure from the service definitions, which
  `krpc_build` already generates for structures.
- **Ids.** Services and procedures have numeric ids, and `ProcedureCall` takes `service_id` and
  `procedure_id`. Names still work. Using ids is optional, and comes later.
- **Definitions.** The JSON gains `id`, `internal` on procedures and `mapped_type` on exceptions.
  `krpc_build` must accept them, and should hide internal procedures.

Steps:

1. Copy `protobuf/krpc.proto` from main into `proto/`, and set the protocol version to 2.
2. Rework the connection and the stream reader in `src/client.rs` and `src/stream.rs`.
3. Update `krpc_build` and the codec for the type changes.
4. Regenerate `service_definitions/` from main. The servicedefs tests check these.
5. Run `examples/client.rs` and `examples/streams.rs` against `krpc-testserver`, then against KSP.
   Use `TestService` from the TestServer for anything the examples do not reach.

The conformance suite is the real test of this work. Until the testee exists, the
examples and `cargo clippy` are the check.

## 1. servicedefs

`service_definitions/` holds JSON copied from a kRPC v0.7.0 release. Regenerate it from the
assemblies in the KSP install, which `bazel run //:test-ingame` keeps at the `main` build:

```sh
GD=../KSP/GameData/kRPC
krpc-servicedefs --reference-dir=../KSP/KSP_Data/Managed \
    -o out/KRPC.SpaceCenter.json KRPC.SpaceCenter $GD/KRPC.SpaceCenter.dll
```

Cases:

- [ ] Each service in `GameData/kRPC`: `KRPC` (from `KRPC.Core.dll`), `SpaceCenter`, `Drawing`,
  `UI`, `InfernalRobotics`, `KerbalAlarmClock`, `RemoteTech`, `DockingCamera`, `LIDAR`, `Debug`.
- [ ] Output matches the `.json` the mod build ships beside each DLL in `GameData/kRPC`.
- [ ] Documentation is present, read from the `.xml` beside each DLL. Then remove the `.xml` from
  a copy and check the result is a clear warning or empty docs, not a crash.
- [ ] `StdLib`: find out how a third party gets its definitions. It has no DLL of its own.
- [ ] Errors: unknown service name, missing DLL, missing `--reference-dir`, a reference directory
  that does not exist. Each gives a one-line error and a nonzero exit.
- [ ] Output to stdout and with `-o` is identical.
- [ ] `KRPC.MechJeb`: only if the Genhis mod DLL is to hand. Otherwise out of scope.

Then build this crate against the regenerated set (`KRPC_SERVICES=<dir> cargo build`) and diff
the generated `services.rs` against the committed set. Differences show schema changes since
v0.7.0 that `krpc_build` must handle.

## 2. clientgen

`krpc-clientgen` has no Rust generator. It accepts a path to a Python module in place of a
language name, with a `generator` class and a `tmpl` template path. This crate already generates
its stubs in `krpc_build/mod.rs`, which gives a reference output to compare against.

Steps:

1. Read the built-in generators (`krpctools/clientgen/generator.py`, `csharp.py`) as installed
   in the venv, without using the `krpc` sources. Record what an outside author needs to learn
   and where the docs fall short. `doc/src/extending/clientgen.rst` mentions the plugin form only
   in the `--help` text.
2. Write `tools/clientgen_rust/rust.py` and `rust.tmpl` in the crate's repo, producing the same API as
   `krpc_build` for the `KRPC` and `SpaceCenter` services.
3. Generate with `krpc-clientgen tools/clientgen_rust/rust.py SpaceCenter <defs...>`, build the
   crate against it, and run the examples against the TestServer.

Check:

- [ ] The plugin loads by path, including a path with `~` and environment variables.
- [ ] The base generator gives a plugin what it needs: type mapping hooks, name casing,
  documentation conversion, default values, nullable types, deprecation.
- [ ] Documentation markup (`<math>`, `<unit>`, `<see cref>`) converts through a plugin hook, and
  unknown markup gives the `DocumentationMarkupWarning`.
- [ ] Cross-service types (`SpaceCenter` uses `KRPC` and `StdLib` types) resolve with several
  JSON inputs. Check whether `--include` applies to a plugin.
- [ ] Generating from a DLL input, with `--output-defs`, gives the same code as from JSON.
- [ ] The plugin's module name is taken from the file name. Check the handling of a name ending
  in `p` or `y`: `load_generator` strips `.py` with `rstrip`, which strips characters, not a
  suffix.

## 3. docgen

`krpc-docgen` takes a language from a fixed list (`cnano`, `cpp`, `csharp`, `java`, `lua`,
`python`), with no plugin form. A Rust page cannot be generated without changing `krpctools`.

Steps:

1. Follow `doc/src/extending/docgen.rst` as written: an empty ordering file, run to get the list
   of missing members, fill the order file, and generate a `python` page for `SpaceCenter`.
2. Build the page with Sphinx, with the extensions the doc lists.
3. Try a Rust domain. Write the smallest domain that would work, and record the changes to
   `krpctools` it needs (a plugin path as in clientgen, or a public domain base class).

Check:

- [ ] The empty ordering file workflow lists every missing member and exits nonzero.
- [ ] `--documented` lists each member the page covers.
- [ ] Arguments from a file with `@FILE`.
- [ ] Every language builds under Sphinx with no warnings for `SpaceCenter`.
- [ ] A finding for the missing plugin form, with the proposed change.

## 4. Conformance

The suite runs this crate through a testee: a program that reads `Command` messages as JSON lines
on stdin and writes `Output` messages on stdout (`krpctools/conformance/testee.proto`). The
contract is in `doc/src/client-spec/conformance.rst`.

### Testee

Write it as a binary in the crate's repo, `conformance/testee`, using the crate's blocking API first.

- [ ] Generate Rust types from `testee.proto` with `protobuf-codegen`, and use its JSON mapping.
  This tests that the shipped proto is usable outside Python.
- [ ] The crate needs stubs for `TestService`, `TestService2` and `ConformanceService`. Get their
  definitions from `KRPC.GetServices` on a running `krpc-testserver`, or check whether the package
  ships them as JSON. Generate with `krpc_build`, or with the step 2 plugin once it works.
- [ ] Start with profile `core` over `tcpip`. Add `streams`, `events`, `error-types`,
  `defaults`, `concurrency` and the `tokio` feature as the crate supports them.

### Runs

```sh
krpc-conformance --testee "target/debug/testee" \
    --expected-failures conformance/expected-failures.txt \
    --unsupported conformance/unsupported.txt
```

- [ ] Each protocol the crate supports: `tcpip` first. `websockets`, `localsocket` and
  `serialio` (needs `socat`) only if added to the crate.
- [ ] Expected failures and unsupported files: a stale line fails the run, `@flaky` and `@skip`
  behave as documented.
- [ ] Pytest pass-through, such as `-k`, `-x` and `-v`.
- [ ] `--server` with a separately started `krpc-testserver`.
- [ ] A testee that crashes, hangs, writes junk to stdout, or omits `Hello`. Each gives a clear
  driver error, and the run does not hang.
- [ ] A testee that reports an unknown profile or protocol in `Hello`.
- [ ] `--conventions` once the testee claims `error-types`.

## Recording Results

Results go in [krpctools-test-results.md](krpctools-test-results.md), one section per tool, with the
`krpc` commit tested. Each finding states the tool, the command, what happened and what was
expected. Tag each finding:

- **krpctools bug**: wrong behavior in a tool.
- **krpctools gap**: a missing feature an outside author needs, such as the docgen plugin form.
- **docs**: the docs are wrong or missing a step.
- **client**: a defect in this crate, found through the tools.

Findings for `krpc` become issues in [`issues/`](../issues/), not GitHub issues.

## Order

1. Setup.
2. Protocol update, on its own commits.
3. servicedefs, as it feeds the other tools.
4. Conformance with a `core` testee. The testee also finds defects in the protocol update.
5. clientgen plugin, used to generate the testee's stubs.
6. docgen.
7. Widen conformance profiles.
