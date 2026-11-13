# Partial loading

**Status:** proposal, for 0.8. Issue: [#1227](https://github.com/krpc/krpc/issues/1227). A first
implementation (2026-10-31, never a PR) is stale against this design. Follows the
[mod integration framework](../services/mod-integration-framework/README.md).

What kRPC does when a service definition breaks a
[service definition rule](../protocol/service-definition-rules.md), including a name clash. kRPC
disables as little as possible and keeps running. How the player and the mod author learn of it is
in [problem reporting](problem-reporting.md).

A mod integration that cannot bind to its mod is a separate failure, handled by
[`ModAPI`](../services/mod-integration-framework/mod-api.md). Both are reported together.

## Problem

The scanner checks every service, class, procedure, enumeration, struct and exception when the
server starts. One bad member, in any installed mod, takes all of kRPC down:

| Server | What a scanner error does today |
| --- | --- |
| KSP | `ServicesChecker` disables kRPC entirely. The popup says "plugin has been disabled. See the log for more information" and lists nothing. |
| KSA | `Services.Instance` calls `Scanner.GetServices ()` with no error list, so the first error throws out of the server's startup. |

The player sees kRPC gone, or the game failing to load. The cause is often a third-party mod the
player cannot fix. A KSP or KSA update that breaks one service member breaks every service.

The scanner already does most of the work for a gentler outcome. Given an error list, it catches each
member's error, records it and moves on, leaving the member out. Neither server uses that partial
result.

## Design

kRPC loads every member that scans cleanly, and disables the rest.
The game keeps loading.

### Errors and warnings

| Kind | Examples | Effect |
| --- | --- | --- |
| **Error** | Invalid parameter or return type, a procedure outside a service, a struct containing itself, a [clash](#clashes) | The member is disabled: absent from `KRPC.GetServices` and not callable |
| **Warning** | Extension members in a class that is not public | kRPC keeps running, and the class's extension members are skipped, as before |

`Scanner.GetServices` takes an error list and a warning list. A null warning list makes warnings
errors, and a null error list makes the first problem throw, which `tools/ServiceDefinitions` relies
on. The public `ServiceProblems` class gives the server the lists from the scan `Services` ran.

### What an error disables

The unit disabled is the smallest one that leaves a consistent service definition:

| Failure | Disabled |
| --- | --- |
| A procedure, method or property | That member |
| A class, enumeration, struct or exception | That type, and every member whose parameter, return type or struct field refers to it |
| A service (invalid attribute, not public static) | The service, its types, and extension members that target it |
| The `KRPC` service, or a scanner exception outside the per-member handlers | kRPC as a whole, as today. Clients cannot connect usefully without `KRPC`. |

**The type cascade runs to a fixed point.** `TypeUtils.IsAValidType` checks a type's attribute, not
whether the type scanned. A procedure returning a class whose scan failed would otherwise reach
clients pointing at a class that does not exist. Disabling a struct can disable a member that takes a
class, which can disable a struct field. So the pass repeats until nothing changes.

**A removed class takes its static methods with it.** They have no parameter of the class type, so
the cascade also checks each procedure's declaring `KRPCClass`.

### Clashes

Every [service definition rule](../protocol/service-definition-rules.md) that compares two names
leaves out each name of a clashing pair, exact duplicates included. Keeping the first one scanned
would make the outcome depend on assembly load order, so adding a member could remove an existing
one.

The one exception is an extension member that clashes with a member of the class itself. The
extension member is left out, and the class keeps its own. The class's members are always scanned
first, so the outcome is fixed, and a mod cannot remove a member of another service by declaring a
clashing extension.

| Clash | Left out |
| --- | --- |
| Two members of a scope that share a [member key](../protocol/service-definition-rules.md#member-keys) or a helper key | Both members |
| Two types of a service, compared case-insensitively | Both types, and the cascade |
| Two services, compared case-insensitively | Both services, their types, and extension members that target them |
| A type named as its service | That type, and the cascade |
| Two parameters of a procedure, or a parameter name that breaks the rule | That procedure |
| An enumeration value name that breaks the rule | The enumeration, and the cascade |
| A shared or 0 id | Both members, see [procedure ids](../protocol/procedure-ids.md#collisions) |

Two classes that declare one service name exactly still merge into one service, as they always have.

### Calling a disabled member

Dropped. A member that fails validation never gets a procedure name, so only the cascade and the
duplicate removals could report one. A call to a disabled member gets "procedure not found", and the
popup and the log give the reason.

## Tests

`core/test/Service/ScannerTest.cs` gains a test per row of the cascade and clash tables.

## Changes

One PR, after the [mod integration framework](../services/mod-integration-framework/README.md),
whose phase 4 adds `ServiceProblems.Mods`. [Problem reporting](problem-reporting.md#changes) lands
with it.

| Area | Change |
| --- | --- |
| `core` scanner | Errors and warnings with a severity; the type cascade; the clash removals; a whole-kRPC failure flag |
| `core` `Services` | Built from the partial scan; services without an id left out of `ServicesById`; the scan's errors and warnings in `ServiceProblems` |
| `server` (KSP) | `ServicesChecker` checks at startup and disables kRPC only on a whole-kRPC failure |
| `tools/ServiceDefinitions` | Unchanged: it passes no lists, so it fails on any error or warning |
| Changelogs | Server: a broken service member disables only that member |

## Alternatives

**Disable a whole service on any of its errors.** Simpler, with no cascade. Rejected: one bad
SpaceCenter member, e.g. after a KSP or KSA update, would take out SpaceCenter, which nearly every
script uses.

**Keep the hard failure, improve only the popup.** Rejected: it still leaves the player with no kRPC
over a mod they cannot fix.
