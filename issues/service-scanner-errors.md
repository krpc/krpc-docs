# Disable only the broken service members, and list scanner problems in a popup

A service scanner error in any installed mod takes down all of kRPC. On KSP the server disables itself, and the popup only points to the log. On KSA the first error throws out of the server's startup.

kRPC should instead load every member that scans cleanly and disable the rest, including members whose types failed to scan. One popup should list the errors and warnings, such as id clashes, by service. kRPC then disables itself only when the `KRPC` service is broken. `tools/ServiceDefinitions` stays strict, so mod authors still get a hard failure at build time.

Design: [service-scanner-errors.md](https://github.com/krpc/krpc-docs/blob/main/design/server/service-scanner-errors.md).
