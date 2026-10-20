# Changes to existing GitHub issues

Edits to issues already on [`krpc/krpc`](https://github.com/krpc/krpc/issues), to match
[RELEASE_PLAN.md](../RELEASE_PLAN.md). Delete each line once done.

## Milestones

| Issue | Now | Change |
| --- | --- | --- |
| [#1123](https://github.com/krpc/krpc/issues/1123) Client conformance tests | 1.0.0 | 0.8.0 |
| [#903](https://github.com/krpc/krpc/issues/903) Reverse stream / non-blocking control | none | 1.0.0 |
| [#251](https://github.com/krpc/krpc/issues/251) Execute one RPC per frame | none | 1.0.0 |
| [#526](https://github.com/krpc/krpc/issues/526) Autopilot with large planes | 1.0.0 | Decide: the release plan has it not scheduled, maybe deferred to a MechJeb integration |

## Comment on #1123

Decisions for the conformance work, left open by the client audits:

```markdown
Client decisions to settle as part of this work:

* Whether the Lua client gets streams.
* C++: dropping a `Stream` handle never removes the server stream (parity audit bug 11). Rule it intended under the explicit removal model of #1122, or fix it.
* `TestService`: rename `EnumDefaultArg` and `AddMultipleValues`, and add `UInt32ToString`, `HexStringToBytes` and `StaticOptionalArguments`.
* The open Python client bugs from the parity audit's Python sweep.

Background: [client-api-parity-audit.md](https://github.com/krpc/krpc-docs/blob/main/design/client-api-parity-audit.md), [client-testing.md](https://github.com/krpc/krpc-docs/blob/main/design/client-testing.md)
```

## Later

* [#1107](https://github.com/krpc/krpc/issues/1107) Release server side functions: closed as
  premature. Reopen it when [function-release.md](../design/server-side-functions/function-release.md)
  is picked up.
