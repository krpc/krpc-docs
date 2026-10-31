# Service scanner errors

**Status:** proposal, for 0.8 with [procedure ids from names](../protocol/procedure-ids.md).
Issue: to file, draft [issues/service-scanner-errors.md](../../issues/service-scanner-errors.md).

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
| **Warning** | A shared id, a hashed id of 0 ([procedure-ids.md](../protocol/procedure-ids.md#collisions)) | The member loads, callable by name only |

`Scanner.GetServices` returns both lists. `HandleError` becomes `HandleProblem` with a severity.

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
one scanned would make the outcome depend on assembly load order.

### Calling a disabled member

A call to a disabled member returns its scanner error, e.g. "`SpaceCenter.Vessel_get_Foo` is
disabled: `Foo` is not a valid Procedure return type". `Services` keeps the disabled members' names
and errors for this. A name that never existed still gets the existing "procedure not found" error.

### The popup

One popup per launch with a problem, listing every error and warning grouped by service, the
disabled members under each. It says what still works ("kRPC is running. These members are
unavailable:"). The full messages go to the log, and the popup gives the log's path.

| Server | Popup |
| --- | --- |
| KSP | `ServicesChecker` keeps its `PopupDialog`, now with a scrolling list. `OK` stays false only for the whole-kRPC failures above. |
| KSA | The scanner problems join the game compatibility breakages in `CompatibilityPopup`, which becomes the one problems popup. Its "ignore" button records a hash of the problem list, so the popup returns when the list changes. |

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
| `core` `Services` | Built from the partial scan; keeps disabled members and their errors for the call error |
| `server` (KSP) | `ServicesChecker` lists the problems in its popup and disables kRPC only on a whole-kRPC failure |
| KSA server | `Services` initialized with the problem list; problems merged into `CompatibilityPopup` |
| `tools/ServiceDefinitions` | Fails on warnings too |
| Docs | Extending kRPC: what a player sees for a broken service, and that servicedefs is the author's check |
| Changelogs | Server: a broken service member disables that member, with a popup naming it |

## Alternatives

**Disable a whole service on any of its errors.** Simpler, with no cascade. Rejected: one bad
SpaceCenter member, e.g. after a KSP or KSA update, would take out SpaceCenter, which nearly every
script uses.

**Keep the hard failure, improve only the popup.** Rejected: it still leaves the player with no kRPC
over a mod they cannot fix.
