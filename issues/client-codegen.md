# Generate the exception mapping and the service list for every client

Only the service stubs are generated. Each client hand-copies the rest, and the copies disagree. Python and C# map 11 server exceptions to native types, Java maps 10 with different choices, and C++ maps none. The error message format differs in all six clients: C# adds a trailing space and C++ drops the server stack trace. The list of services is repeated across the client builds. In Python, `except conn.krpc.ArgumentException` never fires, because the stub declares its own class and the client raises `ValueError`.

Generate the exception mapping from the service definitions, and the build from one list of services. Bring every client's error message to one format. Add goldens for the `KRPC` service's generated stubs. This lands before the conformance suite (#1123), so the suite's error tests start out passing.
