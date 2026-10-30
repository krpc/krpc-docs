# Publish the TestServer and ServiceDefinitions bundles for every platform

The .NET tools that krpctools bundles run only on Linux. `krpc-conformance` cannot start its bundled TestServer on Windows, and `krpctools servicedefs` cannot run its bundled ServiceDefinitions. `//tools/krpctools:conformance-test` therefore has `target_compatible_with` set to Linux. The TestServer release archive has the same limit.

Both tools are framework-dependent .NET 10 programs. Their managed DLLs are portable, and only two parts of each publish are specific to Linux:

| Part | Linux-specific because |
|---|---|
| `TestServer`, `ServiceDefinitions` | The apphost from `runtime_identifier = "linux-x64"`, an ELF executable. There is no `.exe`. |
| `System.IO.Ports.dll` (TestServer) | The Unix build, calling termios through `libSystem.IO.Ports.Native.so`. `runtimes/` holds `linux-x64` alone. |

Over TCP, websockets and local sockets, `dotnet TestServer.dll` should run on Windows as it is. Serial IO needs the Windows `System.IO.Ports`.

## Change

- Publish `//tools/TestServer:publish` and `//tools/ServiceDefinitions:publish` without a runtime identifier, so `runtimes/` carries `unix` and `win` and the runtime picks one at startup. Check that rules_dotnet's `publish_binary` supports this.
- Start the bundled tools with `dotnet <tool>.dll`: the conformance driver's default `--server` in `client/conformance/driver/main.py`, and `servicedefs` in `tools/krpctools/krpctools/servicedefs/__init__.py`.
- Drop `target_compatible_with` from `//tools/krpctools:conformance-test`, and add a servicedefs run on Windows.
- Repackage `TestServer-<version>.zip` from the portable publish, and remove the TODO beside it in `tools/TestServer/BUILD.bazel`.

## Serial IO

The conformance driver's serial tests link a pair of pseudo-terminals with `socat`, which has no Windows build. So even with a portable bundle, a client author on Windows cannot run the serial tests through `krpc-conformance`. #1200 proposes a named pipe in place of the serial port on Windows, served by the TestServer through a test-only `IPort`. That would give the bundled driver a serial line on Windows as well, so the two changes should land together or in that order.

Related to #1200
