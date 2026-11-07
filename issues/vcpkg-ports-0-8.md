# Update the vcpkg ports for 0.8.0

The release steps `66-release-vcpkg-cpp.py` and `67-release-vcpkg-cnano.py` copy `client/*/vcpkg-port` over `ports/krpc` and `ports/krpc-cnano` in microsoft/vcpkg. They fill in the version and SHA-512, then open a pull request for each port.

The 0.8.0 ports differ from the published 0.7.0 ports in more than the version:

| Port | Change | Reason |
| --- | --- | --- |
| `krpc`, `krpc-cnano` | Remove `COPYING` and `COPYING.LESSER` from `vcpkg_install_copyright` | The 0.8.0 archives leave them out, and `vcpkg_install_copyright` stops on a missing path |
| `krpc` | `license` from `LGPL-3.0-or-later` to `MIT` | The C++ client moves to MIT |
| `krpc-cnano` | `license` from `LGPL-3.0-or-later AND Zlib` to `MIT AND Zlib` | The C-nano client moves to MIT |
| `krpc-cnano` | Remove `-DKRPC_COMMUNICATION_TCP=ON` and the patch to `communication.h` | #1275 compiles every transport in and chooses one at run time |

The ports in the repo already have these changes: the transport change from #1275 and the license changes from #1281.

To do at the 0.8.0 release:

- [ ] Run both release steps after the GitHub release, and check each pull request's diff against the table.
- [ ] Add the license and transport changes to each pull request's description. The release step writes only the version and a link to the release.
