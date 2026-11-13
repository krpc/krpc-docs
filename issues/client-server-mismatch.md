# Find out what users see with a mismatched client, server or service

kRPC supports a client and a server of the same release only. Users still mix versions: an old client against a new mod, a script's generated stubs against an updated mod, or a mod's service from one version beside another. We do not know what each mismatch looks like to them, so we cannot document it or say when a fix is needed.

Map each mismatch to what every client does with it. Each outcome is a clear error, a wrong result with no error, or a crash or hang.

**Version mismatches:**

| Mismatch | Example |
| --- | --- |
| Protocol version | A 0.7 client against a 0.8 server, and the reverse |
| Same protocol, older client | A 0.8.0 client against a 0.8.1 server, whose services gained members |
| Same protocol, newer client | The reverse |
| A mod's service from another version | A generated module or stub for RemoteTech 1.x against 2.x |
| A generated module newer than the shipped one | Python's replaced module, as in the Python declarations design |

**Service definition changes:**

| Change | To check |
| --- | --- |
| A procedure, class or service added or removed | The error for a call to a missing procedure, in each client |
| A parameter appended with a default | An old stub's call runs with the default, with no error |
| A parameter removed, reordered or retyped | Whether the server rejects the call, or decodes it as another value |
| A return type changed | Whether the client's decoder fails, or reads a wrong value |
| An enumeration value added, removed or renumbered | Values by number in static clients, a value the client lacks in a result |
| A structure field added or removed | The server ignores extra items, so a short structure may decode quietly |
| An exception added, or its mapped type changed | The client's generic error, as [protocol-compatibility.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol-compatibility.md) requires |

The static clients (C++, C#, Java, C-nano) and the dynamic ones (Python, Lua) differ here, and C-nano calls by id. Run every case against each client.

Outcome:
 * An analysis doc in the planning repo, with the table filled in per client.
 * A troubleshooting section in the docs, listing the symptoms a user is likely to hit and the fix: a client and server of the same release, or regenerated stubs.
 * An issue for each silent wrong result worth a check, given the ruling that a mismatch need not work.

Related: the ruling that a changed RPC signature should fail and not be tolerated, and the negative results in the release plan for detecting an old stub by a signature hash and for a Python warning at connect.
