# Protocol version

**Status:** in progress (2026-10-22). Phase 1 is in #1162 for 0.7. Version 2 is implemented
locally for 0.8 with the [single connection](single-connection.md), not yet in a PR. Issue drafted in
[issues/protocol-version.md](../../issues/protocol-version.md).

## Problem

The protocol has no version of its own. `config.bzl` holds one release version, reported by
`KRPC.GetStatus`. `ConnectionRequest` and `ConnectionResponse` carry no version, and no client
checks one. This works only while the server and every client ship under one number.

0.7 already breaks 0.6 clients: the `KRPC` procedures are renumbered, so a client calling by id
needs stubs for 0.7. 0.8 breaks the protocol again with the single connection. A mismatched client
and server need to fail at the handshake with a clear error, and the release versions of the server
and clients should be free to move apart.

## Design

One integer, the protocol version, carried in the handshake of every transport:

* `ConnectionRequest` gains `uint32 protocol_version`. Absent reads as `0`, a client from before
  0.7.
* The server accepts a version it supports. Otherwise it rejects the connection with a new
  `ConnectionResponse` status, `WRONG_PROTOCOL_VERSION`, and a message naming the versions it
  supports.
* `ConnectionResponse` gains `uint32 protocol_version`, the version the server accepted. A client
  that reads `0` is talking to a server from before 0.7, and closes the connection with an error.
* `KRPC.Status` gains `protocol_version`, the version of the connection, for scripts and bug
  reports.
* Later changes are additive where possible, and leave the version alone. A breaking change bumps
  it. A server may then support more than one version during a transition.
* `ConnectionRequest` and `ConnectionResponse` gain `repeated string features`, the additive
  features the client asks for and the ones the server granted. It lands with the first feature
  that needs it, which is additive. See "Additive changes".

### Versions

| Version | Release | Server accepts | Change |
| --- | --- | --- | --- |
| 0 | before 0.7 | | No version in the handshake |
| 1 | 0.7 | 0 and 1 | The version itself. Renumbered `KRPC` procedures, structures, nullable values |
| 2 | 0.8 | 2 | Single connection, request ids |

**A 0.7 server serves version 0 as version 1.** The messages are the same, so the two differ only in
what they record: `0` is a client that did not say, which may not understand everything 0.7 sends.
The server logs a warning naming the client, and `GetStatus` reports `0`. Rejecting `0` would leave
a 0.6 client nothing to do to comply, and stop the ones that work today.

**A 0.8 server accepts only version 2**, since 0.8 is a hard break. Versions 0 and 1 get the same
`WRONG_PROTOCOL_VERSION` error.

The version replaces one negotiated flag per protocol change, such as the `single_connection` flag
an earlier sketch of [single-connection.md](single-connection.md) proposed.

### Per transport

| Transport | Handshake | Version carried in |
| --- | --- | --- |
| TCP, local socket | A bare `ConnectionRequest` in versions 0 and 1. A `Message` holding a `connection_request` from version 2. | The `ConnectionRequest` field |
| Serial IO | A `MultiplexedRequest` holding a `ConnectionRequest` in versions 0 and 1. A `Message` holding a `connection_request` from version 2. | The same field |
| WebSockets | HTTP upgrade, `name` and `id` in the query string, in versions 0 and 1. From version 2, the upgrade alone, then a `Message` holding a `connection_request`. | A subprotocol, `Sec-WebSocket-Protocol: krpc.1`, in version 1. The `ConnectionRequest` field from version 2. |

**A client of any version fails to connect with an error.** Version 2 puts the handshake in a
`Message` on every transport (see [single-connection.md](single-connection.md) "Handshake"), so
every transport changes framing at version 2. The server has no special case for an older client,
and the error an older or newer client reports is often misleading. Each pairing still fails:

| Client | Server | What the server reads | What the client reads |
| --- | --- | --- | --- |
| 0.7 TCP, local socket | 0.8 | The bare request as a `Message`: no case, a `response` (from the client name), or a parse error. Refused. | The refusal `Message` as a `ConnectionResponse` with status `OK` and version 0, which it refuses |
| 0.8 TCP, local socket | 0.7 | The `Message` as a `ConnectionRequest` with no version, accepted as version 0 | The `OK` response as a `Message`. Usually it fails to parse. For a few GUIDs it parses as a `stream_update`, which a client on a new connection refuses during the handshake. |
| 0.7 serial IO | 0.8 | The wrapped request as a `Message` holding a `request`. Refused. | As 0.7 TCP |
| 0.8 serial IO | 0.7 | The `Message` as a `MultiplexedRequest` with no `ConnectionRequest`. Refused. | The refusal as a `Message`, which fails to parse |
| 0.7 WebSockets | 0.8 | The upgrade. The `krpc.1` subprotocol is ignored and none returned. | No subprotocol, so it reports a server from before 0.7 |
| 0.8 WebSockets | 0.7 | No subprotocol, so version 0, accepted. The `Message` as a `Request` with no calls. | An empty `Response`, as a `Message` with no case, which is an error during the handshake |

Every row but the 0.7 WebSockets server's reply to a call-less request was checked by parsing the
encoded messages with the server's protobuf 3.10.1 runtime. Check that one against a 0.7 server
when building version 2.

A client that reads version `0` reports that the server does not support its protocol version. It
does not name a release, since a 0.7 client also reads it from a 0.8 server.

A 0.7 WebSockets server rejects an upgrade with an unsupported subprotocol, with an HTTP 400 and the
same message in the body. A missing subprotocol is version `0`, which it accepts. A 0.7 client that
gets no subprotocol back is talking to a server from before 0.7.

### What is versioned

Only the protocol version decides compatibility.

| Area | Versioned | Reason |
| --- | --- | --- |
| Protocol | Yes, one integer in the handshake | Changes are rare, and each one breaks every client |
| Protobuf schema | No, part of the protocol version | Protobuf handles additive fields. A breaking schema change is a protocol change. |
| Transports | No | They carry the same messages. A transport difference, such as serial IO having no streams, is a capability. |
| Server | Release version, informational | Reported by `GetStatus`, never used for compatibility. |
| Clients | Release version, informational | A client declares the protocol version it speaks. |
| Services | No | See below. |

**Services are not versioned.** `GetServices` says whether a procedure exists, and a static client
calling a missing one gets "procedure not found". Extension members
([PR #1077](https://github.com/krpc/krpc/pull/1077)) make a service version inaccurate: a service's
surface is its own DLL plus every installed extension member. The rule from
[deprecation.md](deprecation.md) covers a change of behavior: a member never changes meaning, and a
new member replaces it. [service-versioning.md](../services/service-versioning.md) records per-service
version strings as a negative result.

### Additive changes

An additive change leaves the protocol version alone. A client older than the change keeps working,
without the feature. [protocol-compatibility.md](../protocol-compatibility.md) checks the 1.0 plan
against these rules.

**A feature that changes how a request is read is negotiated in the handshake.** An older server
ignores an unknown field without an error. It would send a response to a `no_response` request, and
drop a reverse stream push.

* The client lists the features it wants in `ConnectionRequest.features`. The server lists the ones
  it granted in `ConnectionResponse.features`.
* Absent means unsupported, so an older server reads as granting none.
* A client uses a feature only once it is granted, and raises a clear error otherwise.
* A feature with a value, such as the pipelining depth in [request-ids.md](request-ids.md), keeps a
  field of its own with the same rule: the server reports what it granted.
* A new procedure needs no negotiation, since `GetServices` lists it.
* The release version reported by `GetStatus` never gates a feature.

**The server sends a new message kind only to a client granted it.** A client never sees a
message it cannot handle.

**A client tolerates what it does not know.** The conformance suite
([client-conformance/spec.md](../client-conformance/spec.md)) pins each of these:

* Once a session has started, it skips a `Message` with no known case set. Proto3 parses a newer message kind that way,
  including as a `oneof` with no case set.
* It matches a response to its request by id, never by position.
* It maps a server exception it does not know to its generic error.
* It reports a `ConnectionResponse` status it does not know, with the message.

## Work

| Phase | Release | Work |
| --- | --- | --- |
| 1 | 0.7 | Protobuf: the version fields and the status. Server: the check on every transport, version `0` served as `1` with a warning, and the version in `GetStatus`. Every bundled client sends version 1, checks the response, and raises a clear error on a mismatch. The docs: the handshake in `doc/src/communication-protocols/`, and a short compatibility table keyed on protocol version. |
| 2 | 0.8 | Bump to version 2 in the same client rework as the single connection. The server accepts 2 alone from the first step. See "Phases" in [single-connection.md](single-connection.md). |
| 3 | 1.0 | The features lists, with the first feature that needs them. |

### Phase 1 as built

Phase 1 follows the design, apart from these points:

| Point | As built |
| --- | --- |
| Stream connection | Clients send the version on it, and the server denies an unsupported one. Clients check only the RPC response's version. |
| Version 0 warning | Logged for RPC connections only. A stream connection follows its RPC connection. |
| WebSockets subprotocol | The server uses the first `krpc.N` entry. A malformed one, such as `krpc.x`, gets HTTP 400. |
| Stream reported | `GetStatus` reports the version of the RPC connection. |
| cnano | A mismatch returns `KRPC_ERROR_CONNECTION_FAILED`, as a denied connection does. |
| Tests | Server tests cover no version, version 1 and an unsupported version, for TCP and WebSockets. There are no client tests against a server that reports version 0. These wait for the [conformance suite](../client-conformance/README.md) in 0.8. |

The phase also fixes a SerialIO bug: a `MultiplexedRequest` with no `ConnectionRequest` got its error response, then dereferenced null.

Tests, per transport where the handshake differs:

* A handshake with no version, which a 0.7 server serves and a 0.8 server rejects.
* An unsupported version, rejected with `WRONG_PROTOCOL_VERSION`.
* A client against a server that reports version `0`.
* From phase 3, a client against a server that grants no features.

## Later

With compatibility keyed on the protocol version, the server and each client can take their own
release version numbers. That needs one version per component in `config.bzl` and
`tools/krpc-version.sh`, and per-component tags in the release scripts. It is out of scope here.

## Open questions

None.
