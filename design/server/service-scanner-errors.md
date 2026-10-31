# Service scanner errors

**Status:** in progress, for 0.8. Core and the KSP server implemented locally (2026-10-31), not yet
a PR. KSA waits for a kRPC release with the new core API. Issue: to file, draft
[issues/service-scanner-errors.md](../../issues/service-scanner-errors.md).

| Part | State |
| --- | --- |
| Scanner: partial load, type cascade, duplicates, service id warnings | Implemented |
| KSP popup listing errors and warnings | Implemented |
| KSA popup | Deferred: KSA builds against the released `KRPC.Core`, which has no `ServiceProblems` |
| Call to a disabled member returns its error | Dropped, see below |
| "Ignore" button | Dropped: the popup shows on each launch with a problem |

## Problem

The scanner checks every service, class, procedure, enumeration, struct and exception when the
server starts. One bad member, in any installed mod, takes all of kRPC down:

| Server | What a scanner error does today |
| --- | --- |
| KSP | `ServicesChecker` disables kRPC entirely. The popup says "plugin has been disabled. See the log for more information" and lists nothing. |
| KSA | `Services.Instance` calls `Scanner.GetServices ()` with no error list, so the first error throws out of the server's startup. |

The player sees kRPC gone, or the game failing to load, and has to search the log for the cause. The
cause is often a third-party mod the player cannot fix. A KSP or KSA update that breaks one service
member breaks every service.

The scanner already does most of the work for a gentler outcome. Given an error list, it catches each
member's error, records it and moves on, leaving the member out. Neither server uses that partial
result.

## Design

kRPC loads every member that scans cleanly, disables the rest, and lists both errors and warnings in
one popup. The game keeps loading.

### Errors and warnings

| Kind | Examples | Effect |
| --- | --- | --- |
| **Error** | Invalid parameter or return type, a procedure outside a service, a duplicate name, a struct containing itself | The member is disabled: absent from `KRPC.GetServices` and not callable |
| **Warning** | A shared id, a hashed id of 0 ([procedure-ids.md](../protocol/procedure-ids.md#collisions)), extension members in a class that is not public | kRPC keeps running. An id warning leaves the member callable by name only, and the class's extension members are skipped, as before |

`Scanner.GetServices` takes an error list and a warning list. A null warning list makes warnings
errors, and a null error list makes the first problem throw. The public `ServiceProblems` class gives
the server the lists from the scan `Services` ran.

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

**Duplicate names disable both members**, as a shared id leaves both without one. Keeping the first
one scanned would make the outcome depend on assembly load order. One exception: an extension member
that clashes with a member of the class itself is disabled, and the class keeps its own member. The
class's members are always scanned first, so the outcome is fixed, and a mod cannot remove a
member of another service by declaring a clashing extension.

**A removed class takes its static methods with it.** They have no parameter of the class type, so
the cascade also checks each procedure's declaring `KRPCClass`.

### Calling a disabled member

Dropped. A member that fails validation never gets a procedure name, so only the cascade and the
duplicate removals could report one. A call to a disabled member gets "procedure not found", and the
popup and the log give the reason.

### The popup

One popup per launch with a problem, listing every error and warning grouped by service, the
disabled members under each. It says what still works ("kRPC is running. These members are
unavailable:"). The full messages go to the log, and the popup gives the log's path.

| Server | Popup |
| --- | --- |
| KSP | `ServicesChecker` keeps its `PopupDialog`, now with a scrolling list. `OK` stays false only for the whole-kRPC failures above. |
| KSA | A popup of its own, beside `CompatibilityPopup`, once KSA builds against a core with `ServiceProblems`. Until then a scanner error still throws out of startup. |

### Mod authors

The players get the graceful path. A mod author gets a hard failure before release:

* `tools/ServiceDefinitions` calls `GetServices ()` with no list, so any error or warning fails the
  build. It stays strict, so the bundled services and any mod built with kRPC's tooling are checked.
* `core/test/Service/ScannerTest.cs` gains a test per row of the cascade table.

## Changes

One PR, after procedure ids, which adds the first warnings.

| Area | Change |
| --- | --- |
| `core` scanner | Errors and warnings with a severity; the type cascade; a whole-kRPC failure flag |
| `core` `Services` | Built from the partial scan; logs each problem; services without an id left out of `ServicesById`; public `ServiceProblems` |
| `server` (KSP) | `ServicesChecker` lists the problems in its popup and disables kRPC only on a whole-kRPC failure |
| KSA server | Later: a problems popup, once on a core release with `ServiceProblems` |
| `tools/ServiceDefinitions` | Unchanged: it passes no lists, so it fails on any error or warning |
| Docs | Extending kRPC: an Errors and Warnings section, and the reserved service id range |
| Changelogs | Server: a broken service member disables that member, with a popup naming it |

## Alternatives

**Disable a whole service on any of its errors.** Simpler, with no cascade. Rejected: one bad
SpaceCenter member, e.g. after a KSP or KSA update, would take out SpaceCenter, which nearly every
script uses.

**Keep the hard failure, improve only the popup.** Rejected: it still leaves the player with no kRPC
over a mod they cannot fix.
