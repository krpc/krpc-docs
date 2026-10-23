# Generate the conformance testee stubs from the full TestServer definitions

The TestServer extension members (`TestServiceExtensions`) and `TestService2` are built into the server but not into the assembly that `TestService.json` is generated from. The bundled stubs therefore lack them, which is what the Python stub merge tests (`test_extension_members*`) rely on.

The conformance testees for C#, Java, C++ and cnano call the server through generated stubs, so they cannot reach these members. `calls-extension-members` and `streams-extension-member` would then fail on those clients through a gap in the fixture, not a client defect. Stubs for `TestService2` alone do not help: its only class is reached through an extension member.

Add a second definitions target, built from the TestService sources plus `TestService2.cs` and `TestServiceExtensions.cs`. Generate the testee stubs and dispatch from it, for `TestService` and `TestService2`. Keep `TestService.json`, the krpctools and docgen goldens, and each client's own test stubs as they are, so the Python merge tests keep their subject.

Part of #1123.

Design: [harness.md](https://github.com/krpc/krpc-docs/blob/main/design/client-conformance/harness.md)
