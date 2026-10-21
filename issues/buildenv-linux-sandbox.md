# Re-enable the Bazel sandbox in CI

`tools/buildenv/bazelrc` runs every CI action unsandboxed (`--spawn_strategy=standalone` and friends). This predates the hermetic build from #948. A local build is sandboxed and CI is not, so an action that reads an undeclared file can pass in one and fail in the other.

Drop the standalone lines. The linux sandbox needs user namespaces inside the buildenv container. If the GitHub runner does not allow them, try `--experimental_use_hermetic_linux_sandbox` or the `processwrapper-sandbox`. Targets tagged `local` stay unsandboxed. Compare CI wall time before and after.
