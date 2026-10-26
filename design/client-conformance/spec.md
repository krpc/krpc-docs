# Requirement inventory

Since C7 the requirements live in the conformance tests in `krpc` (`conformance/tests/`). Each
test is one requirement: its docstring is the text, its name gives the id, and its markers give
the level and profiles. The spec pages' requirement lists and the coverage page are generated
from the tests. This file keeps the naming rules, the profile rulings and the compatibility
mapping. The per-area tables that planned the pages are in git history.

Sources: the client testing standard's rubric, the single connection's client reader rules
([single-connection.md](../protocol/single-connection.md)), the stream and event design
([stream-and-event-improvements.md](../protocol/stream-and-event-improvements.md)), the client
rules in [protocol-compatibility.md](../protocol-compatibility.md), and the open defects
([defects.md](defects.md)).

## Naming

| Item | Form | Example |
| --- | --- | --- |
| Requirement id | `<area>-<name>`, kebab case | `streams-wait-timeout-short` |
| RST label in the spec | `spec-<id>` | `spec-streams-wait-timeout-short` |
| Test | `conformance/tests/test_<area>.py::test_<name>` | `test_streams.py::test_wait_timeout_short` |
| Variant | A pytest parameter | `test_values.py::test_scalar_arguments[uint64]` |

- The area is one spec page and one test file. The name is a short phrase, a sentence for a
  behavior (`a_callback_is_not_passed_an_older_value`) and a noun for a feature (`rate`).
- An id is never reused or renamed once published. A dropped requirement leaves a gap.
- A test checks one requirement. It is marked `@profile("<profile>")`, `@should` or `@may` for
  the level, and `@transport("<transport>")` for a transport-only test. A requirement with no
  test is a test marked `@untested("<reason>")`, which skips.
- Names come from the existing tests: the Python stream, event and object tests, which the other
  clients mirror, and the client testing standard's catalog for calls and values.

## Profiles

A testee reports its profiles in `Hello`. A test outside them is skipped, not failed. Each
client's profiles are listed in `conformance/profiles/<client>.txt`, which the driver checks
against `Hello`.

The `dynamic` profile holds the requirements a compiler enforces in a statically typed language:
wrong argument types, counts and ranges (C3 ruling). The server takes any enum number, as
`KRPC.GameScene` is a flags enum, so `values-invalid-enum` is a `dynamic` requirement too.

C# named arguments are compiler syntax over the stub's declared defaults, which `defaults` already
checks by leaving arguments off the end, so C# takes no `named-args` profile (C3 ruling).

C4 rulings: `streams-property-setters-are-invalid` is `dynamic`, as a compiler rejects such a
stream. `calls-request-ids` is `threads`, as it holds trivially with one call in flight. The
other C4 rewordings are listed in [harness.md](harness.md) "Built in C4".

Transports are reported separately: `tcpip` (all), `localsocket` (all but cnano, until cnano is built
with every transport at once), `serialio` (cnano). Lua has no streams in 0.8 ([defects.md](defects.md)
"Decisions").

## Compatibility rules

The client rules from [protocol-compatibility.md](../protocol-compatibility.md), each with its
requirement:

| Rule | Requirement |
| --- | --- |
| Skip a `Message` with no known case once the session has started | `connection-unknown-message-is-skipped` |
| Match responses by request id, never by position | `calls-responses-matched-by-id` |
| Map an unknown server exception to the generic error | `errors-unknown-exception-type` |
| Report an unknown `ConnectionResponse` status with its message | `connection-unknown-status` |
| A negotiated feature absent from the handshake is unsupported | No test until the first negotiated feature |
| The release version from `GetStatus` never gates a feature | Stated in the spec, not testable |
