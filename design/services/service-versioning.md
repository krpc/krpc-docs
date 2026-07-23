# Per-service version strings

**Status:** in progress — implemented but not merged; no GitHub issue or PR yet. Server side
and all six clients done and green; no changelog entries yet. The work is three commits:

* **"Add versioning for services"** — the original, incomplete work rebased from an old commit;
  carried a placeholder version and a broken protobuf field number.
* **"Complete service versioning implementation"** — server side finished + protobuf bug fixed.
* **"Surface the service version in all clients".**

## Problem

kRPC exposes a single server version through `KRPC.GetStatus().version`, but nothing per service. A
service is one C# DLL — SpaceCenter, Drawing, UI, and the third-party bridge services each build to
their own assembly. Third-party service authors version their DLL's RPC surface independently of the
kRPC release it is built against, and a client has no way to discover which version of that surface a
given server is running.

The aim of this work is to expose each service's DLL version over the protocol and surface it on the
client service objects.

## Is it worth doing?

Yes, as a small, additive, low-risk feature — with a clear-eyed view of who benefits.

* **Third-party services** are the real audience. A mod that ships its own kRPC service can bump its
  DLL version as its RPC surface evolves; a client can then read that version and adapt. This is the
  motivating case.
* **First-party services** all share the single `assembly_version` from `config.bzl` (SpaceCenter,
  Drawing, UI, … are built together at the kRPC version), so they all report the same string — the
  same value already available via `GetStatus().version`. Harmless and consistent, but redundant for
  those.

The mechanism (read the version from the service type's defining assembly) is simple and robust, so
the cost is low and the third-party benefit justifies it.

## The version value

The version is read from the assembly that defines the service type, in
`ServiceSignature`'s scanner constructor:

```csharp
var assemblyVersion = type.Assembly.GetName ().Version;
Version = assemblyVersion.Major + "." + assemblyVersion.Minor + "." + assemblyVersion.Build;
```

* **Source = the defining assembly.** For a first-party service the assembly is built with kRPC's
  `assembly_version`; for a third-party service it is that mod's own `AssemblyVersion`. One service =
  one DLL, so the service type's assembly is exactly the DLL whose version we want.
* **Format = `major.minor.build`.** This mirrors how the server formats its own version in
  `server/src/Addon.cs` (`core.Version = version.Major + "." + version.Minor + "." + version.Build`),
  so a first-party service's `version` string is identical to `GetStatus().version`. The fourth
  (revision) component of a four-part `AssemblyVersion` is dropped, exactly as the server drops it.
  A third-party DLL versioned `1.2.3.4` therefore reports `1.2.3`. If exposing the full four-part
  string for third parties is later preferred, it is a one-line change here.
* The name-based `ServiceSignature (string name, uint id)` constructor (used for synthetic services)
  sets `Version = string.Empty`.

## Protocol

The `Service` message in `protobuf/krpc.proto` gains a `version` field:

```proto
message Service {
  string name = 1;
  repeated Procedure procedures = 2;
  repeated Class classes = 3;
  repeated Enumeration enumerations = 4;
  repeated Exception exceptions = 5;
  string documentation = 6;
  bool deprecated = 7;
  string deprecated_reason = 8;
  string version = 9;
}
```

**Bug fixed here:** the original commit numbered `version = 7`, colliding with `deprecated = 7`.
`protoc` rejects duplicate field numbers, so the proto did not even compile. It is now `9` (the next
free number).

The value flows: scanner `ServiceSignature.Version` → `Messages.Service.Version`
(`core/src/Service/KRPC/KRPC.cs` constructs it) → the wire `Schema.KRPC.Service.Version`
(`core/src/Server/ProtocolBuffers/MessageExtensions.cs`). `ServiceSignature` also serializes the
version through `GetObjectData`, so it appears in the service-definitions JSON that clientgen/docgen
consume (Newtonsoft honors `ISerializable`). A first-party service now emits e.g.
`"version": "0.5.4"` where the placeholder `"????"` used to be.

## Client surface

Each client exposes the version as a read-only accessor on its service object, baked into the
generated stub from the service-definitions JSON. One shared change adds `service_version` to the
generator context (`tools/krpctools/krpctools/clientgen/generator.py`); each language template renders
it in its own idiom:

| Client  | Surface                              | Example                              |
|---------|--------------------------------------|--------------------------------------|
| Python  | class attribute `version: str`       | `conn.space_center.version`          |
| C#      | property `Version`                   | `connection.SpaceCenter().Version`   |
| C++     | method `version()`                   | `space_center.version()`             |
| Java    | method `getVersion()`                | `spaceCenter.getVersion()`           |
| C nano  | `#define KRPC_<SERVICE>_VERSION`     | `KRPC_SPACECENTER_VERSION`           |
| Lua     | `_version` field (dynamic client)    | `conn.space_center._version`         |

* **Lua** builds services at runtime from `GetServices`, so it reads the new proto field directly and
  stores it as `_version` next to the existing private `_name`. Lua has no public metadata surface —
  even the service name is `_name` — so an underscore field is the idiomatic match here, unlike the
  public accessors in the static clients.
* **Build-time, not runtime.** The static clients bake the version present in the service-definitions
  JSON at code-generation time — i.e. the version the client was generated against — consistent with
  how `service_id` and the entire stub surface are already baked. For first-party services, where the
  client library and server are the same kRPC build, this equals the runtime value. For a third-party
  service whose server build differs from the stubs, the baked constant can be stale; the authoritative
  runtime value is always available from `GetServices` (and directly on the dynamic Lua client). A
  runtime accessor on the static stubs would be a larger, architecturally different change and is out
  of scope here.

### docgen node fix

Both the real docgen and its tests pass the whole service-definition dict as keyword arguments into
the docgen `Service` node (`tools/krpctools/krpctools/docgen/nodes.py`). The new `version` key would
otherwise crash docgen with `TypeError: unexpected keyword argument 'version'` on any real service, so
the node now accepts `version=""` (stored, not yet rendered in docs).

## Testing

* `core/test/Service/ScannerTest.cs` asserts the scanned `TestService` reports its assembly version,
  computed from the test assembly itself (`GetType().Assembly.GetName().Version`) so it stays correct
  across releases rather than hard-coding a version string.
* The 10 clientgen golden files (`clientgen-{Empty,TestService}-{python,csharp,cpp,java,cnano}.txt`)
  were regenerated; the diffs are the version accessor only. The `Empty` fixture has no version and
  renders an empty string cleanly in every language.
* Two Python client tests (`test_krpc_service_members`, `test_test_service_service_members`) assert
  the exact set of public members on a service; `version` was added to both, since surfacing it
  publicly is the intended behavior. The C#/Java/C++ clients enumerate members by RPC-attribute
  reflection, so their new accessor is not counted and their suites were unaffected.

Green: `//core:test`, `//tools/krpctools:krpctoolstest` (clientgen + docgen goldens), all five static
client builds plus the C nano build, and all six client test suites (`//client/{python,csharp,java,
cpp,lua}`).

## Remaining

* **File a GitHub issue** for the feature (none exists) and link it here.
* **Changelog entries** in the final pre-merge commit: `server` + protobuf for the new field, and one
  `client:*` line per language for the accessor. (Nothing yet — per the repo's changelog-timing rule.)
* **Decide whether the client accessor should be runtime rather than build-time**, or whether the
  build-time constant plus the always-available `GetServices` value is sufficient. Documented above as
  build-time by default.
* **Optionally render the version in docs** — the docgen node now carries it but nothing displays it.
