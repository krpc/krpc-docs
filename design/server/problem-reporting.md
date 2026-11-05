# Problem reporting

**Status:** in progress, for 0.8, with [partial loading](partial-loading.md). Issue:
[#1227](https://github.com/krpc/krpc/issues/1227). A first KSP popup (2026-10-31, never a PR) is
stale against this design.

| Part | State |
| --- | --- |
| KSP popup listing scanner problems and disabled mods | Designed; first implementation stale |
| KSA popup | Deferred: KSA builds against the released `KRPC.Core`, which has no `ServiceProblems` |
| Log entries for every problem | Designed. Stub warnings implemented with best-effort binding, no PR |
| Strict checks for mod authors | Implemented: `tools/ServiceDefinitions` fails on any problem |
| "Ignore" button | Dropped: the popup shows on each launch with a problem |

How the player, the script author and the mod author learn what [partial loading](partial-loading.md)
left out, and why.

## Problem

Today a scanner error disables kRPC on KSP behind a popup that says "plugin has been disabled. See
the log for more information" and lists nothing. On KSA it throws out of the server's startup. A mod
integration that fails reports in a popup of its own (`APILoader`), or only when an RPC is called.
The player has to search the log for the cause, and for which part of kRPC still works.

## What is reported

| Problem | Popup | Log | Client |
| --- | --- | --- | --- |
| Scanner error, a [clash](partial-loading.md#clashes) included | Yes, under its service, with the members it disabled | Error, the full message | "procedure not found" for a left-out member |
| Scanner warning | Yes | Warning | Nothing |
| A whole-kRPC failure: `KRPC` service, or a scanner exception | Yes, saying kRPC is disabled | Error, with the stack trace | No server |
| Mod installed, integration failed to load | Yes, in a group of its own | Error | The integration's "not available" error |
| Mod not installed | No | Info | The integration's "not available" error |
| Missing non-essential mod member, bound as a stub | No | Warning, at load | `MissingMemberException`, naming the mod and the member, from an RPC that uses it |

A popup cannot name the RPCs a stub affects, because the link from a reflected member to an RPC is
not known statically. The exception reaching the client is the notification, and its message is the
stub's.

## The popup

One popup per launch with a problem, listing every error and warning grouped by service, the disabled
members under each, then each mod whose integration failed to load. It says what still works ("kRPC
is running. These members are unavailable:"). The full messages go to the log, and the popup gives
the log's path.

| Server | Popup |
| --- | --- |
| KSP | `ServicesChecker` keeps its `PopupDialog`, now with a scrolling list. `OK` stays false only for the whole-kRPC failures |
| KSA | A popup of its own, beside `CompatibilityPopup`, once KSA builds against a core with `ServiceProblems`. Until then a scanner error still throws out of startup |

**The check and the popup run at different times on KSP:**

* **Check at startup.** The scan and the mod loaders run at `Startup.Instantly`, or lazily on the
  first read of `ServicesChecker.OK`. They need only the loaded assemblies. The server addons read
  `OK` in `Awake`, and `NoGameAddon` runs at `Startup.MainMenu`. A check at `MainMenu` could run
  after that read, as KSP does not order the addons of a scene.
* **Popup at the first main menu.** A `MainMenu` addon shows the popup once per launch, in the
  `LoadOnceAddon` pattern. A popup at `Instantly` competes with the loading screen. The main menu is
  where a player expects warnings about installed mods. Showing it on loading a save would interrupt
  play, and the problems concern the install, not the save.

`APILoader` stops showing a popup of its own.

## Mod failures

A failed integration is listed in its own group, one line per mod: "Kerbal Alarm Clock support is
disabled: KerbalAlarmClock.APIReady is not available in the installed version".

The exception type of the failure ([partial loading](partial-loading.md#exceptions)) decides how it
is reported:

| Exception (`KRPC.Utils`) | Popup | Log |
| --- | --- | --- |
| `ModNotInstalledException` | No | Info |
| `ModVersionException`, `ModTypeMissingException` | Yes | Error |
| `ModMemberMissingException`, at load | Yes | Error |
| `ModMemberMissingException`, from a stub at a call | No | Warning at load. The client sees the exception |
| Any other exception from `Bind` | Yes, with the type name | Error, with the stack trace |

`ModMemberMissingException` carries `Mod` and `Member`, so core logs and lists it without parsing the
message.

## Mod authors

The players get the graceful path. A mod author gets a hard failure before release:

* `tools/ServiceDefinitions` calls `GetServices ()` with no list, so any error or warning fails the
  build. It stays strict, so the bundled services and any mod built with kRPC's tooling are checked
  against every [service definition rule](../protocol/service-definition-rules.md).
* clientgen fails on a member or helper key clash, naming both members.
* The extending docs gain an Errors and Warnings section: what each problem disables, and where it is
  reported.

A clash between two mods is one no single author can see. It reaches the player through the popup.

## Changes

With the [partial loading](partial-loading.md#changes) PR.

| Area | Change |
| --- | --- |
| `core` `Services` | Logs each problem at its level |
| `server` (KSP) | A `MainMenu` addon shows the popup once per launch, with a group for disabled mods |
| KSA server | Later: a problems popup, once on a core release with `ServiceProblems` |
| Docs | Extending kRPC: an Errors and Warnings section, and the reserved service id range |
| Changelogs | Server: a popup names the disabled members and mods |

## Alternatives

**A call-time "disabled" error naming the reason.** Dropped. A member that fails validation never
gets a procedure name, so only the cascade and the duplicate removals could report one. The popup and
the log give the reason, and a stub carries its own message.

**An "Ignore" button.** Dropped. A problem shows on each launch until the install is fixed.
