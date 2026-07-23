# Protocol improvements overview (issue #906)

**Status:** reference — overview of meta-issue [#906](https://github.com/krpc/krpc/issues/906);
each in-scope feature now has its own linked design doc (2026-07-03). First feature implemented:
#904 (Obsolete in docs/clients) — [PR #926](https://github.com/krpc/krpc/pull/926). Sections 9
(request ids) and 10 (single connection) were added later as sketches, not agreed designs.

[Issue #906](https://github.com/krpc/krpc/issues/906) is a meta-issue collecting protocol
improvements. This document summarizes each linked issue as a starting point for designing
each feature precisely in follow-up sessions.

**Deliberately omitted** from this overview (out of scope for now):
constructors ([#898](https://github.com/krpc/krpc/issues/898)),
inheritance ([#905](https://github.com/krpc/krpc/issues/905)), and
more communication protocols ([#899](https://github.com/krpc/krpc/issues/899)).

---

## Service definition & types

### 1. Surface `Obsolete` in docs and generated clients — [#904](https://github.com/krpc/krpc/issues/904)

**Status: completed** — see [deprecation.md](deprecation.md); implemented
and opened as [PR #926](https://github.com/krpc/krpc/pull/926). Additive
`deprecated` + `deprecated_reason` fields on every service-definition entity, read from
the standard `System.ObsoleteAttribute`, rendered as warning admonitions in docs and
native deprecation markers in all generated clients, plus runtime `DeprecationWarning`s
in the dynamic Python client.

**Problem.** Marking a kRPC procedure/property with `[Obsolete("reason")]` has no visible
effect for users: the generated documentation does not indicate deprecation, and the
generated client code carries no deprecation marker. Users only find out via the changelog.

**Sketch.** Propagate the `Obsolete` annotation (flag + reason string) through the service
definition into (a) the docs generator — visually mark deprecated members and show the
reason — and (b) clientgen — emit each language's native deprecation idiom
(`@Deprecated` in Java, `[Obsolete]` in C#, `[[deprecated]]` in C++,
`warnings.warn(DeprecationWarning)` or docstring notes in Python) so users get compiler
warnings.

**Notes.** Requires extending the service-definition schema (e.g. a
`deprecated`/`obsolete` field on `Procedure`) — an additive proto3 change, backwards
compatible. Touches the scanner, docgen, and all clientgen templates, but each piece is
mechanical.

### 2. Nullable parameters and return values

#### Already completed

- [#678](https://github.com/krpc/krpc/issues/678) *(closed)* — parameters (not just return
  values) can be marked nullable, so e.g. the Python client can type them
  `Optional[MyClass]`. By convention, anything not marked nullable is never null.
- [#677](https://github.com/krpc/krpc/issues/677) *(closed)* — `KRPCDefaultValue` is now
  applied directly to the parameter rather than to the method with a name string; more
  concise and less error prone (breaking change, but the feature was unused outside this
  repo).

#### Remaining: presence for defaults and results — [#843](https://github.com/krpc/krpc/issues/843)

**Status: design agreed** — see [nullable-values.md](nullable-values.md). The detailed
design departs from the issue's proto3 `optional` proposal (blocked by the KSP/Unity
protobuf 3.10.1 pin and the protobuf-lua plugin): it uses additive `bool` presence/null
fields on `Parameter`, `ProcedureResult` and `Argument` instead, retires the legacy
id-0 null sentinel on the encode side, and extends null support to defaults, returns
and arguments for all types across all clients.

**Problem.** `Parameter.default_value` and `ProcedureResult.value` are plain proto3 `bytes`
fields, so an absent field and one explicitly set to `b""` are indistinguishable on the
wire. Two consequences: (a) optional parameters whose default encodes to zero/empty
(`int = 0`, `false`, empty list) appear *required* to the Python dynamic client — a
concrete bug, worked around for `LaunchVessel.crew` in #824 by making it required; and
(b) null return values need type-specific null sentinels (e.g. object ID 0) instead of a
clean type-agnostic encoding.

**Sketch.** The issue contains a fully worked fix: mark both fields `optional` in
`protobuf/krpc.proto` (proto3 `optional` adds a presence bit without changing the wire
format — a strict protocol extension), then use `HasField` in the Python client
(`service.py` param-required logic, `client.py` result decoding), and verify the C# server
sets the presence bit when encoding null/empty values. Absent = null / no default,
present = value (possibly empty).

**Notes.** Backwards compatible in both directions; no regression for old
client/server pairs. Once landed, revert the #824 `LaunchVessel.crew` workaround in
`service/SpaceCenter/src/Services/SpaceCenter.cs`. Check the Lua dynamic client's
`ProcedureResult.value` handling (its `default_value` path already uses `HasField`), and
whether static clients (C#, Java, C++, cnano) need presence handling for results — C++
may want `std::optional`.

### 3. Extension methods — [#305](https://github.com/krpc/krpc/issues/305) + [#900](https://github.com/krpc/krpc/issues/900)

**Status: design agreed** — see [extension-members.md](extension-members.md). C#
extension methods with `[KRPCMethod]`/`[KRPCProperty]` are grafted server-side into the
*target class's* service definition as ordinary `Class_Member` procedures — no schema
change, and all clients/clientgen/docgen work unchanged (except a Python
stub/definition merge step). #900 becomes a documented pattern: a mod-defined
`[KRPCClass]` wrapper plus a nullable extension property on `Part`; the issue's
`ISupportsKRPC` bridge is rejected as untypeable without inheritance (#905).

**Problem.** Third-party service authors cannot extend existing service classes. Two
requested flavors:

- **#305** — an extension service adding members to another service's classes, e.g. a
  TestFlight service adding `vessel.parts.with_failure("blah")` or `parts.failed` onto
  `SpaceCenter.Parts`.
- **#900** — mods exposing their `PartModule`s as first-class typed classes (like the
  stock `Engine`, `LandingLeg` wrappers) instead of forcing clients through the
  stringly-typed `Module.HasField`/`GetField` API. The issue suggests e.g. an
  `ISupportsKRPC` interface returning a typed representation, plus
  `Module.SupportsRepresentation`/`GetRepresentation`.

**Sketch.** Both reduce to letting one service attach procedures/classes to types owned by
another service. The scanner already maps C# extension-method-like patterns to class
members via attributes; the design work is deciding how cross-service class references and
clientgen output are organized (which client module the new members appear in, how the
dynamic clients merge them onto the existing class).

**Notes.** Mostly a service-scanner and clientgen design problem; likely little or no wire
change (the service definition already carries fully qualified class names). Needs a
concrete story for both static and dynamic clients.

### 4. Structure types — [#866](https://github.com/krpc/krpc/issues/866)

**Status: design agreed** — see [struct-types.md](struct-types.md). `[KRPCStruct]` C#
structs with `[KRPCProperty]` fields; wire encoding reuses the positional Tuple format
(tagged encoding rejected); `STRUCT = 102` TypeCode + `Struct`/`StructField` definition
messages; append-only field evolution; non-nullable fields in v1. First adoption in a
shipped service breaks old dynamic clients at connect time (accepted for 0.6.0); new
dynamic clients gain graceful unknown-type skipping to prevent a repeat.

**Problem.** Compound data today is either a KRPCClass (server-side handle, one RPC per
field access) or a positional tuple (by value, but no named fields). Read-heavy compound
values suffer: `SpaceCenter.launch_sites` costs 1 + 3n RPCs; pitch/roll/yaw is 3 RPCs.

**Sketch.** The issue has a fairly complete proposal: a `[KRPCStruct]` attribute on a C#
struct whose `[KRPCProperty]` members become named fields, serialized as a protobuf
message and passed inline in a single RPC — no server-side handle, usable as both return
values and arguments. E.g. `LaunchSiteInfo { Name, Body, EditorFacility }`, or a new
`Control.pitch_roll_yaw` property alongside the existing per-axis ones.

**Notes.** Wire protocol change — all clients (7+ clientgen templates) must learn the
struct encoding; third-party wire-level clients break on unknown encodings, so it must be
well documented. Migration policy from the issue: new struct-returning RPCs are additive;
class→struct migrations reserved for APIs already awkward enough to justify a version
bump. Guidance: use structs when callers almost always want all fields; keep classes for
lazily fetched data. All fields are always transmitted; struct fields are read-only from
the client.

---

## Streams

### 5. Client-to-server streams / batched calls — [#903](https://github.com/krpc/krpc/issues/903)

**Status: design agreed** — see [reverse-streams.md](reverse-streams.md). Three phased
rungs: batch client APIs (protocol/server already support multi-call requests — no
server work); a `no_response` flag on `Request` for fire-and-forget (version-gated
against old servers); and reverse streams — register a call, push latest-wins argument
updates applied at most once per tick, with errors delivered via the #877 stream
invalidation convention. Pushes ride `Request` on the RPC connection (zero transport
changes; the stream connection is one-way and absent on SerialIO).

**Problem.** Streams only exist server→client. Every control write (e.g.
`control.pitch = x; control.yaw = y`) is a blocking RPC round-trip — ~40ms for two
setters in the reporting user's measurement — which makes closed-loop control from a
client painfully slow.

**Sketch.** Two complementary directions from the issue: (a) a *reverse stream* — the
client registers a procedure call whose argument it then pushes repeatedly without
waiting for responses (fire-and-forget, analogous to receive streams); and/or (b)
*batching* — submit several calls in one request. Note the wire protocol's `Request`
already carries `repeated ProcedureCall`, so part of the batching story may be client API
work rather than protocol work.

**Notes.** The largest new protocol surface in this list; needs design for ordering,
error reporting for fire-and-forget calls, and rate semantics (every physics frame vs.
latest-value-wins). Related to stream freezing (#901) in that both are about
frame-coherent, low-latency exchange.

### 6. Reference-count duplicate streams — [#902](https://github.com/krpc/krpc/issues/902)

**Status: design agreed** — see [stream-refcounting.md](stream-refcounting.md).
Server-side refcount per (client, stream) with forced teardown bypassing it (error
invalidation, events, disconnect), plus wrapper-level removal in the bundled clients
(the shared-`StreamImpl` poisoning made this a client-side bug too). No wire change.

**Problem.** Two identical stream requests from the same client return the same stream id
(deduplication to minimize traffic). But `RemoveStream` by one consumer destroys the
stream for both — independent parts of a client program can silently break each other.

**Sketch.** Per the issue: keep the deduplication but add a server-side reference count
per (client, stream) — `AddStream` on an existing stream increments it, `RemoveStream`
decrements, and the stream is only destroyed at zero. Client libraries may want a
matching local refcount so their stream wrapper objects stay independent.

**Notes.** No wire change needed — purely server (and client-library) semantics. Interacts
with stream invalidation (#877): an error-invalidated stream is removed regardless of
refcount, and all consumers must be notified.

### 7. Stream invalidation on error — [#877](https://github.com/krpc/krpc/issues/877)

**Status: design already agreed** — see [stream-invalidation.md](stream-invalidation.md).

**Summary.** When a stream's underlying RPC throws (e.g. after a quickload destroys the
object), the server sends the error to the client once and removes the stream; clients
must treat an error result as invalidation (today they block/crash). The agreed design is
an implicit protocol convention (no `.proto` change), a server-side `EventStream`
exception fix, and error handling in all four stream-capable clients (Python, C#, Java,
C++). Not yet implemented.

### 8. Stream freezing — [#901](https://github.com/krpc/krpc/issues/901) — **out of scope**

**Status: superseded** — see [stream-freezing-removal.md](stream-freezing-removal.md).

**Problem.** Stream values update asynchronously, so two reads (e.g. `ut` and a vessel's
orbital anomaly, or position and velocity) can come from different physics frames —
originally reported in #357 as multi-kilometer errors in maneuver-node computations. The
C++ client solves this with stream *freezing* (`client.freeze_streams()` /
`thaw_streams()`): while frozen, all stream values are held at a consistent snapshot.

**Outcome.** The earlier design ported freezing to Python/C#/Java and redesigned the C++
semantics. It has been dropped in favor of **removing** the C++ feature, superseded by
server-side function streams (#679): a single expression stream returning a heterogeneous
tuple gives the same-tick guarantee with one stream to manage instead of N plus a freeze
scope, and no client-side machinery to maintain in five clients. Since removal is neither
a protocol change nor a client-parity improvement, it is no longer tracked under this
meta-issue.

---

## Connection semantics

### 9. Request ids and asynchronous RPCs — *no issue yet*

**Status: sketch** — see [request-ids.md](request-ids.md). Not part of the
#906 issue list; raised separately (2026-07-21) and needs an issue filing.

**Problem.** Nothing on the wire correlates a `Response` with its `Request` — the association
is positional, and the server refuses to read a second request from a client while one is in
flight. So there is no pipelining (every call is a round-trip), a yielding RPC such as
`WarpTo` stalls the whole connection, and a client interrupted between send and receive is
silently desynchronized for the life of the connection (Python bug 25 in
[client-api-parity-audit.md](../client-api-parity-audit.md)).

**Sketch.** Additive `uint64 id` on `Request`, echoed on `Response`, in three phases: echo and
validate only (fixes bug 25, no scheduling change); then per-client FIFO pipelining behind a
connection-time negotiated in-flight cap; then, optionally, opt-in out-of-order completion for
calls explicitly marked overtakeable. Execution order stays strictly FIFO throughout — kRPC
calls mutate shared game state, so reordering them would make pipelining useless for anything
but pure reads.

**Notes.** Backwards compatible in both directions. Does *not* supersede the `repeated
ProcedureCall` batching field, which uniquely guarantees same-frame execution — keep it.
Complementary to the `no_response` flag in
[reverse-streams.md](reverse-streams.md). Enables a demultiplexing reader in
the clients, and hence an asyncio-based Python client, though that is a separate (and larger)
clientgen question.

### 10. A single bidirectional connection — *no issue yet*

**Status: sketch** — see [single-connection.md](single-connection.md). Raised
separately (2026-07-21) alongside section 9 and needs an issue filing.

**Problem.** Clients open two TCP connections, one per port, for RPCs and for stream updates.
The split is a consequence of the same missing correlation described in section 9: with no id on
the wire, a `Response` and a server-initiated `StreamUpdate` cannot be told apart on one socket,
so each got a socket. The GUID handshake, `ConnectionRequest.Type`, the `WRONG_TYPE` status and
the second configured port all exist to serve that workaround. Websockets repeats the whole
arrangement despite being natively bidirectional.

**Sketch.** Deliver stream updates over the RPC connection inside the `MultiplexedResponse`
envelope that already exists for SerialIO and already reserves a `stream_update` field, opted
into at connection time so both paths coexist. The server side is nearly free — RPC and stream
updates are already written from the same game thread in the same `FixedUpdate`.

**Notes.** Shares its entire client-side cost with section 9: both need one socket owner that
demultiplexes to waiting callers, so they should be designed and landed together rather than
paying that concurrency rework twice across five clients. Also wants to precede section 5
(#903): client-to-server stream updates have nowhere to go but the RPC connection, so that
connection must learn to discriminate them from a `Request` regardless — doing this first makes
#903 a field in an existing envelope instead of a second, one-directional multiplexing
mechanism. Preserves the "no streams, no reader
thread" property that simple clients such as Lua rely on. Also unblocks streams over SerialIO,
which are documented but have never been implemented — a shipped-docs bug worth fixing
immediately and independently.

---

## Suggested order for detailed design

1. **[#843](https://github.com/krpc/krpc/issues/843) nullable/default presence** — fix is
   already worked out, backwards compatible, and unblocks reverting the #824 workaround.
2. **[#904](https://github.com/krpc/krpc/issues/904) obsolete annotations** — additive
   schema field plus mechanical docgen/clientgen work.
3. **Stream semantics** — [#902](https://github.com/krpc/krpc/issues/902) refcounting,
   designed alongside the already-agreed [#877](https://github.com/krpc/krpc/issues/877)
   implementation since both touch the same client stream managers.
4. **[#866](https://github.com/krpc/krpc/issues/866) structs** — biggest cross-client
   payoff; proposal in the issue is a solid starting point.
5. **[#305](https://github.com/krpc/krpc/issues/305)/[#900](https://github.com/krpc/krpc/issues/900)
   extension methods** — scanner/clientgen design work.
6. **[#903](https://github.com/krpc/krpc/issues/903) client-to-server streams** — largest
   new protocol surface; benefits from the struct encoding (#866) existing first (e.g.
   batched control updates as a struct argument).
