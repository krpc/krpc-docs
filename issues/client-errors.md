# Clients: one shape for the errors every client raises

The clients name their errors differently, derive them from different bases, and raise different
errors for the same situation. A program cannot catch every server error with `RPCError` in
Python or C++, C# has no stream error, Java wraps a connection error in `RPCException`, and
decoding leaks raw errors in Python, C# and Java.

[client-errors.md](../design/client-errors.md) proposes the shape: mapped server exceptions as the
language's own types, every other error under a `RemoteError` (`RemoteException`) base, and one
subclass per category a program handles differently. It lists what each client does today and
the open questions.
