# Reject a string argument holding invalid UTF-8 in the KSP mod

A string argument holding invalid UTF-8 reaches a KSP service with U+FFFD in place of the bad bytes, and the call succeeds. For example, the bytes `01 ff` decode to `"�"`. The other wrong values a call can pass fail with `ArgumentException` since strict argument decoding (#1280).

The behavior depends on the protobuf library, as `Encoder.DecodeValue` calls `CodedInputStream.ReadString`:

| Runtime | Google.Protobuf | Invalid UTF-8 |
| --- | --- | --- |
| KSP mod | 3.10.1, `lib/net45` | Replaced with U+FFFD: decodes with `Encoding.UTF8` |
| `core/test` | Current, on .NET | `ArgumentException`, wrapping "String is invalid UTF-8" |

The KSP result comes from reading the library's IL, and has not been run in game. The `core/test` result comes from running `01 ff` through `Encoder.Decode`.

## Proposal

Decode strings in `Encoder` with a `UTF8Encoding` that throws on invalid bytes, so each runtime gives the same `ArgumentException`.

`ReadString` cannot take an encoding, so the bytes come from `ReadBytes` first. This adds a copy to every string argument. Measure it on KSP's Mono before deciding, as strings are common on the hot path. A protobuf upgrade is an alternative only if a build runs on KSP's Mono.

## Tests

`core/test` and the conformance `TestServer` run the newer library, so they pass with or without this change. An in-game test sends `01 ff` to a string parameter with a raw call, and expects `ArgumentException`.
