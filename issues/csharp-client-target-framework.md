# Target .NET Standard 2.0 and modern .NET in the C# client

The C# client package targets .NET Framework 4.7.2 only, since 0.6.0 (#948). The requirement came from the build refactor, which put the client on the same framework as the server. The server needs it, because it loads into KSP's Mono. The client does not, since it runs in the user's own program.

A .NET 5 or later project can reference the package only through the .NET Framework compatibility mode, and NuGet warns about it (NU1701). The client also carries its own `UnixEndPoint`, because .NET Framework has no endpoint for a unix domain socket.

Proposal:

- Target `netstandard2.0`, which loads on .NET Framework 4.6.1 and later, Mono, Unity and .NET 5 and later. Google.Protobuf already ships a `netstandard2.0` build, which the client uses.
- Add a modern target, such as `net8.0`, that connects with the runtime's `UnixDomainSocketEndPoint`.
- Run the conformance tests against each target the package ships. The testee runs on .NET 10 only, so no test covers the .NET Framework or Mono build today.

`netstandard2.0` has no `UnixDomainSocketEndPoint`, so `UnixEndPoint` stays for that target. If the package drops every target without one, `UnixEndPoint` and `client/csharp/test/UnixEndPointTest.cs` can be deleted. Until then the unit tests cover `Create`, which no conformance test reaches.

Changing the frameworks the package supports needs a changelog entry.
