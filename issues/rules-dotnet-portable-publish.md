# Support a portable (RID-agnostic) framework-dependent publish

For [bazel-contrib/rules_dotnet](https://github.com/bazel-contrib/rules_dotnet), not kRPC. Design:
[design/build-tools/rules-dotnet-portable-publish.md](../design/build-tools/rules-dotnet-portable-publish.md).

---

`dotnet publish` without `-r` produces a portable app. Every RID's assets go under
`runtimes/<rid>/`, deps.json lists them in `runtimeTargets`, and the host picks the platform's
at startup. One layout then runs as `dotnet app.dll` on every platform.

`publish_binary` always publishes for one RID, as each dependency's `libs` and `native` are
selected on `//dotnet:rid`. An app using `System.IO.Ports` therefore needs a publish per platform
that differ only in that assembly and its native shim.

Proposal: `publish_binary(runtime_identifier = "any", self_contained = False)` produces the
portable layout. Dependencies carry their `runtimes/` assets for every RID in a new
`runtime_targets` field. NuGet imports fill it from the package, and `import_library` takes a
`runtime_targets` attribute. deps.json lists each asset in `runtimeTargets` under its path, and
the publish copies it there. No apphost is made for `any`.

Reference: deps.json and layout from `dotnet publish` of a `System.IO.Ports` app (attached).
Related: #594.

Would a PR along these lines be welcome, and is `runtime_identifier = "any"` the right API?
