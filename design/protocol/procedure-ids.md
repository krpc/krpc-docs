# Procedure ids from names

**Status:** done, for 0.8 with [protocol version 2](protocol-version.md). Merged as
[PR #1265](https://github.com/krpc/krpc/pull/1265), fixing
[#1196](https://github.com/krpc/krpc/issues/1196). Diverged from the design: a shared or 0
procedure id is a scanner error, not left unassigned with a warning.

| Part | State |
| --- | --- |
| Hashed procedure ids, shared hash with service ids | Implemented |
| `Id` on `KRPCProcedure` and `KRPCMethod`; `GetterId` and `SetterId` on `KRPCProperty` | Implemented. An id for an accessor the property lacks, or on a struct field, is an error |
| Shared or 0 procedure ids | Scanner error, in place of the planned warning |
| C-nano clientgen goldens, protocol and extending docs | Done |
| Reserved service id range | Documented only, not enforced. The protocol and extending docs state the range, with no table of assigned ids |
| Service and procedure ids in `KRPC.GetServices` | Implemented: every id, hashed or set by hand |
| Test services (`TestService`, `TestService2`, `ConformanceService`, `Benchmark`) | Hashed ids, in place of 9996 to 9999 |
| A service id of 0 | Scanner error. A service id clash already was one |
| Conformance test: a call by id reaches the named procedure | C-nano's conformance run calls `TestService` by its hashed id |

## Problem

A `ProcedureCall` names its target by string (`service`, `procedure`) or by id (`service_id`,
`procedure_id`). Only C-nano calls by id, to keep strings out of microcontroller flash and off the
wire. Every other client sends names.

Service ids are stable. The bundled services declare one (`[KRPCService (Id = 2)]`), and a service
without one gets a hash of its name (`TypeUtils.GetServiceId`).

Procedure ids are not. `ServiceSignature.NextProcedureId` is a counter per service, handed out in
scan order:

1. the service's procedures, then its properties,
2. every class of the service, type by type, methods then properties,
3. extension members from other assemblies.

| Consequence | Effect on C-nano |
| --- | --- |
| A member added anywhere but the end of the last class renumbers every later id | Nearly every SpaceCenter addition invalidates the stubs |
| The order comes from `Type.GetMethods`, `GetProperties` and the assembly type order, which .NET documents as unspecified | Ids may differ between Mono (KSP) and .NET 10 (KSA) |
| Extension members take ids in the target service's counter, in assembly load order | Installing an optional mod can shift another mod's extension ids |
| A stub's id can name a different procedure with the same argument shape, e.g. two float setters | The call succeeds on the wrong procedure, silently |

C-nano stubs therefore match one server build exactly, and nothing checks the match. This already
bit 0.7: the `KRPC` procedures renumbered when the server-side functions landed
([server-side-functions.md](../server-side-functions/server-side-functions.md)). It also blocks
shipping C-nano stubs apart from an exact mod build, for KSP or KSA.

## Design

A procedure id is a hash of the procedure's name, by the rule service ids already use:

* **id = the first 4 bytes of SHA-256 of the UTF-8 procedure name, read as a little-endian
  `uint32`.** The name is the wire name, e.g. `GetStatus` or `Vessel_get_Flight`.
* **Ids are per service**, as now (`Services.ProceduresById`). Names are unique within a service,
  so the hash input is the name alone.
* **An author can set an id by hand**, with `Id` on `[KRPCProcedure]`, `[KRPCMethod]` and
  `[KRPCProperty]`, as `[KRPCService]` already allows. This is the fallback for a collision the
  author finds before release.
* **A shared id, or a hashed id of 0, leaves the members callable by name only**
  ([Collisions](#collisions)). 0 means "use the name".
* **Explicit service ids stay.** Only the procedure counter changes.
* **Every id reaches clients.** The service definitions JSON, which clientgen reads, holds each
  id. `KRPC.GetServices` reports each service and procedure id too (`id` on `Service` and
  `Procedure`), hashed or set by hand. A consumer never computes the hash, and an id set by hand
  to resolve a clash reaches every client. C-nano cannot fall back to a name.

An id is then as stable as the name, which is exactly the guarantee the string-based clients have.
Renaming a procedure breaks both kinds of client, and adding, removing or reordering members breaks
neither.

### Collisions

Services and procedures follow one rule: **an id that is 0, or shared by two members, is not
assigned. Those members are callable by name only.** The scanner records a warning naming both, and
the server keeps running ([partial loading](../server/partial-loading.md)).

| Case | Outcome |
| --- | --- |
| Two procedures of one service share an id, e.g. an extension member from another mod | Neither has an id |
| Two services share an id, hashed or explicit | Neither service has an id, so C-nano cannot call either |
| A hashed id is 0 | That member has no id |
| A C-nano stub calls an id that is not assigned | "No procedure with this id" error, naming the clash when the id is a known one |

**Neither member keeps the id.** Suppose a stub for mod B sends id X, and mod A also hashes to X.
If A kept X, B's stub would call A's procedure, and succeed when the argument shapes match. Which
member kept it would also depend on assembly load order. With neither keeping it, the stale stub
gets an error, and every name-based client is unaffected.

**Gaps closed in the service id code:**

* `Services` builds `ServicesById` with `ServicesById [service.Id] = service`, so on a clash the last
  service scanned wins. It now leaves both out.
* A hashed service id of 0 is not checked today. It gets the same warning.
* **Explicit ids 1 to 255 are reserved for the services that ship with kRPC.** They keep the
  official service ids to one byte on the wire. There are few official services, so each takes a
  hand-set id. Procedures are too many for that. The extending docs tell mod authors to leave `Id`
  unset. A hashed id lands in that range with odds of about 2^-24, and the clash rule covers it if
  it does.

  Assigned ids, audited 2026-11-03 and kept as they are (all one varint byte):

  | Id | Service | Id | Service |
  | --- | --- | --- | --- |
  | 1 | KRPC | 7 | UI |
  | 2 | SpaceCenter | 8 | StdLib |
  | 3 | Drawing | 9 | never assigned |
  | 4 | InfernalRobotics | 10 | LIDAR (deprecated, #1233; not reused) |
  | 5 | KerbalAlarmClock | 11 | DockingCamera |
  | 6 | RemoteTech | 12 | Debug |

  `KSA` is left hashed while experimental. It will likely take 2, in the KSA server's own id space.
  The test services' ids 9996 to 9999 predate hashing, and they now take hashed ids.

`tools/ServiceDefinitions` treats every warning as an error, so an author finds a clash within their
own mod at build time. The graceful path covers clashes between mods, which no one author can see.

### Size and collision odds

Checked against the current service definitions (2419 procedures, 1464 of them in SpaceCenter):

| Measure | Result |
| --- | --- |
| Collisions within a service | none |
| Ids of 0 | none |
| Chance of any collision in a 1500-procedure service | about 0.03% |
| Varint size of an id | 5 bytes for about 93% of ids, up from 1 or 2 |

The extra 3 or 4 bytes per call are small next to the arguments. Flash use is unchanged, since a
stub holds the id as a constant either way.

### Compatibility

Every procedure id changes, so C-nano stubs from 0.7 call the wrong procedures on a 0.8 server.
Protocol version 2 already rejects 0.7 clients at the handshake, so this lands under it with no new
version number. The C-nano stubs are regenerated by the build.

## Changes

One PR.

| Area | Change |
| --- | --- |
| `core` | `ServiceSignature` computes the id from the name, sharing the hash with `TypeUtils.GetServiceId`; `Id` on the member attributes; shared and 0 ids, service and procedure, left unassigned with a warning |
| `core` tests | Pin a few known ids, e.g. `KRPC.GetStatus` is `2007570979`, so a change to the hash fails a test |
| `protobuf`, `core` | `id` on the `Service` and `Procedure` messages, filled by `KRPC.GetServices` |
| `tools/TestServer`, `tools/benchmarks` | The test services take hashed ids |
| `tools/krpctools` | Regenerate the C-nano clientgen goldens |
| Extending docs | The reserved service id range, the member `Id` override, and what a clash does |
| `doc/src/communication-protocols/messages.rst` | Under Anatomy of a Request, state the id rule, and drop the sentence "They can change between server versions." that follows the integer identifiers' size advantage |
| Changelogs | Server and C-nano: procedure ids are stable across releases that add procedures |
| [Protocol version 2](protocol-version.md) | Listed in its change column |

The conformance suite gains a C-nano-relevant test later: a call by id reaches the procedure the
name gives.

## Alternatives

**A golden file per service**, like `doc/order.txt`, listing names in id order. Rejected. Ids stay
small, and the file records removals, but every service needs one, third-party services included.
Extension members from another assembly need ids coordinated with the target's file.

**An explicit `Id` on every `[KRPCProcedure]`, `[KRPCMethod]` and `[KRPCProperty]`.** Rejected as
the source of ids: about 2400 hand-assigned numbers, with the same coordination problem for extension
members. It stays as an optional override.

**The first member scanned keeps a shared id.** Rejected: a stale stub for the other member calls the
wrong procedure silently, and the winner depends on assembly load order.

**A collision as a scanner error.** Rejected: today one scanner error disables all of kRPC, and a
clash between two mods is one the player cannot fix.

**Every client calls by id.** Rejected. Names stay on the wire for the dynamic, websockets and
hand-written clients, so ids would add a second path to test in every client and remove nothing. A
call's size and lookup are not the bottleneck, and names keep wire captures readable. Only C-nano
calls by id.

**A 28-bit hash, for 4-byte varints.** Rejected. It saves one byte per call and raises the collision
chance in SpaceCenter to about 0.4%.

**A fingerprint of the service definitions, checked at connect.** Rejected as the fix. It detects a
mismatch but leaves the stubs tied to one build.
