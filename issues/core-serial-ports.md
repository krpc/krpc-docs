# Build KRPC.IO.Ports from source in KRPC.Core

The KSP mod downloads `KRPC.IO.Ports.dll` as a prebuilt binary from a release of [krpc/krpc-io-ports](https://github.com/krpc/krpc-io-ports), and ships it as a separate DLL in `GameData/kRPC`. That repo is a fork of Mono's `System.IO.Ports`, last changed in 2017. The source should live in this repo, so that the mod is self-contained and the serial code can be changed with the code that uses it.

## Why the fork is still needed

The comment in `MODULE.bazel` says KSP's Mono has no `System.IO.Ports`. That is wrong for KSP 1.12.5: its `System.dll` has the types, and the Linux `libMonoPosixHelper.so` exports the native functions they call.

The fork makes two changes that matter:

| Fork change | KSP's stock class | Effect of switching to the stock class |
|---|---|---|
| Removes the `SetSignal` calls for DTR and RTS from the `SerialPortStream` constructor, for socat | Calls both. `SetSignal` throws when native `set_signal` returns -1, which it does when `TIOCMGET` fails, with no exception for pseudo-terminals | Opening a socat port is expected to fail. On a real port, DTR and RTS are set on open, and DTR drops by default, which may affect boards whose USB serial waits for DTR |
| Removes the `TryBaudRate` call, as it did not work on KSP's Mono in 2017 | Calls it. The helper now exports `is_baud_rate_legal` | Probably none, and the fork's change may no longer be needed |

This comes from reading the IL of KSP's `System.dll` and disassembling its native helper on Linux. None of it has been run, and the Windows and macOS installs have not been checked. The fork's Windows backend, `WinSerialStream`, has no such patch.

## Proposal

Compile the fork's sources into the net472 build of `KRPC.Core`, keeping the fork's behavior and the `KRPC.IO.Ports` namespace. They go in core and not the server DLL, because `core/src/Server/SerialIO` and `core/src/Configuration.cs` use them and the server depends on core. The net10 build keeps the `System.IO.Ports` package, so KSA is unaffected.

1. **Import.** Copy the 14 source files, all except `AssemblyInfo.cs`, unmodified to `core/src/IO/Ports/`, with the fork's MIT license. The commit message names the source repo and commit.
2. **Build.**
   * Add the files to the net472 build in `core/BUILD.bazel` and `core/src/KRPC.Core.csproj`, and exclude them from net10.
   * Enable unsafe blocks on the net472 build, for `WinSerialStream.cs`.
   * Suppress warnings for the imported files only. That build treats warnings as errors at level 4, with the culture analyzers and CS1591.
   * Check that `//:csproj-test` accepts the conditional items.
3. **Remove the download.**
   * Remove the `KRPC.IO.Ports` references from `server`, `tools/TestingTools` and every service `.csproj`.
   * Remove `csharp_krpc_io_ports` and its license from `MODULE.bazel`, and the import and copy from `tools/build/ksp/BUILD.bazel`.
   * Remove the DLL from `tools/release/genfiles.py` and root `BUILD.bazel`, and update `license_text`.
   * Remove the `KRPC.IO.Ports` lines from the `krpctest` saves.
   * Correct the `MODULE.bazel` comment.
   * Add a changelog fragment under `server`.

This builds on the .NET targets cleanup, which makes `KRPC.Core.csproj` multi-target and names the builds `KRPC.Core.net472` and `KRPC.Core.net10`.

## Things to watch

 * A leftover `KRPC.IO.Ports.dll` from a copy-over upgrade has no references, so it should be harmless. Confirm this in game.
 * Older release tags download the DLL from the fork's release, so that asset must stay even if the repo is archived.
 * Dropping the fork for KSP's stock class stays open as a later change, once the DTR and RTS behavior has been tested on real hardware.

## Verification

 * `monodis --typedef` shows the `KRPC.IO.Ports` types in the net472 `KRPC.Core.dll` only, and neither build references a `KRPC.IO.Ports` assembly.
 * The `//:krpc` zip's file list changes only by the removed DLL and the moved license.
 * `dotnet build KRPC.sln -warnaserror` passes in Debug and Release.
 * In game on Linux, a kRPC serial server over a socat pty accepts the Python client. No in-game test covers serial today, so this is a manual check, or a new test.
 * On Windows, the same check through `WinSerialStream`, or report it as unverified. macOS is unverified.
