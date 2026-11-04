# Portable Framework-Dependent Publish in rules_dotnet

Status: proposal. This is an upstream change to rules_dotnet. Nothing in kRPC depends on it yet.

## Problem

krpctools bundles the TestServer as a framework-dependent app, run with `dotnet TestServer.dll`.
Serial IO needs the platform build of `System.IO.Ports`, so the package ships one publish per RID
(`linux-x64`, `win-x64`), and `krpctools/dotnet.py` picks one at run time. The two layouts differ
only in `System.IO.Ports.dll` and the native shim. Everything else is duplicated.

`dotnet publish` with no `-r` produces a **portable** publish instead. One layout runs on every
platform, and the dotnet host picks the platform assets at startup. rules_dotnet cannot produce
one. kRPC supports only linux-x64 and win-x64, and will not work around this locally. A portable
publish is wanted only once rules_dotnet supports it.

## What the SDK Produces

Reference: a console app referencing `System.IO.Ports` 10.0.14, `dotnet publish -c Release` with
no RID (.NET SDK 10.0.1xx). Layout:

```
app.dll  app.deps.json  app.runtimeconfig.json  app (apphost for the build host)
System.IO.Ports.dll                                   # lib/net10.0, throws PlatformNotSupported
runtimes/unix/lib/net10.0/System.IO.Ports.dll
runtimes/win/lib/net10.0/System.IO.Ports.dll
runtimes/<rid>/native/libSystem.IO.Ports.Native.so    # one per RID the native packages ship
```

The `deps.json` has no `runtimes` section, and the runtime target is `.NETCoreApp,Version=v10.0`
with no RID. Each platform asset is a `runtimeTargets` entry keyed by its path in the layout:

```json
"System.IO.Ports/10.0.14": {
  "dependencies": { "runtime.native.System.IO.Ports": "10.0.14" },
  "runtime": { "lib/net10.0/System.IO.Ports.dll": { "assemblyVersion": "10.0.0.14" } },
  "runtimeTargets": {
    "runtimes/unix/lib/net10.0/System.IO.Ports.dll": { "rid": "unix", "assetType": "runtime" },
    "runtimes/win/lib/net10.0/System.IO.Ports.dll": { "rid": "win", "assetType": "runtime" }
  }
},
"runtime.linux-x64.runtime.native.System.IO.Ports/10.0.14": {
  "runtimeTargets": {
    "runtimes/linux-x64/native/libSystem.IO.Ports.Native.so": { "rid": "linux-x64", "assetType": "native" }
  }
}
```

`dotnet app.dll` runs on Linux and loads the unix assembly and the linux-x64 shim.

## How rules_dotnet Works Today

Read at 0.22.2 and at `main` (2026-11-04). `main` added NativeAOT, ReadyToRun and output groups,
but the RID model is unchanged.

| Piece | Behavior | Where |
| --- | --- | --- |
| RID | A build setting, `//dotnet:rid`. `publish_binary` sets it through `tfm_transition`, and the whole dependency graph builds for that one RID | `transitions/tfm_transition.bzl` |
| NuGet assets | `nuget_archive` writes a `select` on `rid_compatible_*` for `libs` and `native`. A target sees only the files for the configured RID | `rules/nuget/nuget_archive.bzl` (`_create_rid_native_select`, `tfm_filegroup`) |
| Provider | `DotnetAssemblyRuntimeInfo` has `libs` and `native`, both already narrowed to one RID | `providers.bzl` |
| deps.json | RID-specific `libs` go in `runtime` at the app root. NuGet `native` goes in `runtimeTargets`. Non-NuGet `native` goes in `native` at the root | `common.bzl` `generate_depsjson` |
| Layout | Always `<name>/publish/<rid>/`. Native files are copied to `runtimes/<rid>/native/` when framework-dependent | `publish_binary.bzl` `_copy_to_publish` |
| apphost | Always made, for the publish RID | `publish_binary.bzl` `_create_shim_exe` |

`any` is in the RID graph, so `runtime_identifier = "any"` is a valid setting value. The
`select`s would then take the RID-agnostic `lib/` assemblies and no native files, and there is no
apphost pack for `any`. This was read from the source, not tried. The missing piece is a way to
carry **every** RID's assets to the publish, alongside the one RID-agnostic asset.

The non-NuGet `native` row is the bug behind
[bazel-contrib/rules_dotnet#594](https://github.com/bazel-contrib/rules_dotnet/issues/594). The
file is copied to `runtimes/<rid>/native/`, but deps.json lists it at the root. kRPC works around
this with a `path_map` in `tools/krpctools/BUILD.bazel`.

## Proposed Change

A portable publish is `publish_binary(runtime_identifier = "any", self_contained = False)`.

1. **Provider.** Add `runtime_targets` to `DotnetAssemblyRuntimeInfo`: a list of
   `struct(file, rid, asset_type, path)`, where `path` is the asset's path in the layout
   (`runtimes/<rid>/lib/<tfm>/<file>` or `runtimes/<rid>/native/<file>`). It holds every RID's
   assets, independent of the configured RID.
2. **NuGet.** `nuget_archive` writes an unconditional `runtime_targets` filegroup of everything
   under `runtimes/`, for the best TFM of each RID. The import rule turns it into the structs, with
   the RID and asset type taken from the path.
3. **`import_library`.** A `runtime_targets` attribute (label list) with the same
   path-derived meaning, for hand-written imports such as kRPC's `System.IO.Ports`.
4. **deps.json.** When the RID is `any`, `runtime` lists only the RID-agnostic `libs`, and every
   entry of `runtime_targets` goes in `runtimeTargets` under its `path`, with its `rid` and
   `assetType`. No `runtimes` section.
5. **Layout.** Each `runtime_targets` file is copied to its `path`. The output directory is
   `<name>/publish/any/`, or a new name if upstream prefers.
6. **apphost.** None for `any`. A portable app runs as `dotnet app.dll`. Making the build host's
   apphost, as the SDK does, can follow.

The RID-specific publish keeps its behavior. Managed RID-specific assemblies in step 1 need the
TFM in the path. `main`'s `runtime_target_path` helper covers only `runtimes/<rid>/native/<file>`.

## Upstream Plan

| Step | Change | Notes |
| --- | --- | --- |
| 1 | Fix #594 | Small and independent. A non-NuGet native file goes where deps.json lists it. kRPC then drops its `path_map` |
| 2 | Open an issue for the portable publish | Draft: [issues/rules-dotnet-portable-publish.md](../../issues/rules-dotnet-portable-publish.md). Ask whether `runtime_identifier = "any"` is the API the maintainers want before writing the PR |
| 3 | PR for the portable publish | Steps 1-6 above, with a test in `dotnet/private/tests/publish/` that checks deps.json and layout against the SDK's |

Once released, kRPC replaces `publish-linux-x64` and `publish-win-x64` with one `publish-any`,
and drops the RID choice in `krpctools/dotnet.py`.
