# Re-enable the Bazel sandbox in CI

**Status:** draft issue, not filed. Build only, can land in any release. Labels: `enhancement`,
`tools`.

`tools/buildenv/bazelrc` runs every action unsandboxed inside the buildenv container:

```
build --spawn_strategy=standalone --genrule_strategy=standalone
test --test_strategy=standalone
```

This dates from before the build was hermetic, when actions escaped the sandbox anyway. The build
system migration ([build-system-migration.md](../design/build-tools/build-system-migration.md),
[PR #948](https://github.com/krpc/krpc/pull/948)) removed those escapes and left this as an
optional follow-up, because it needed a real CI runner to validate.

A local build is sandboxed and CI is not. An action that reads an undeclared file then passes in
CI and fails locally, or the reverse.

## Proposal

* Drop the three standalone lines, so CI uses the default `linux-sandbox` strategy.
* The linux sandbox needs user namespaces inside the container. Check that the GitHub runner
  allows them for `ghcr.io/krpc/buildenv`. If not, try `--experimental_use_hermetic_linux_sandbox`
  or the `processwrapper-sandbox`. Keep standalone as the documented fallback.
* The targets tagged `local` (cnano, C# and serial IO client tests that need `socat` or the
  network) stay unsandboxed by their tag.
* Compare CI wall time before and after. Sandboxing adds a cost per action.

## Changelog impact

buildenv: one entry, if the bazelrc changes.
