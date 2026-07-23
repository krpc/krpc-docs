# Release plan

Planned features per release, with pointers to design docs where they exist. Work status
lives on GitHub ([`krpc/krpc`](https://github.com/krpc/krpc) issues and PRs); this is the
roadmap, not a status index.

## 0.7 — server-side functions, extensibility, service improvements

| Feature | Design doc |
| --- | --- |
| Server-side functions (incl. arbitrary server-side code) | [protocol/server-side-functions.md](design/protocol/server-side-functions.md), [protocol/server-side-arbitrary-expressions.md](design/protocol/server-side-arbitrary-expressions.md) |
| Extension methods (adding RPCs to existing `KRPCClass` etc.) | [protocol/extension-members.md](design/protocol/extension-members.md) |
| Structure / named-tuple types | [protocol/struct-types.md](design/protocol/struct-types.md) |
| Protocol fixes with limited blast radius (nullable parameters/returns) | [protocol/nullable-values.md](design/protocol/nullable-values.md) |
| Object lifetime and object-cache improvements | [#771](https://github.com/krpc/krpc/issues/771) / [PR #894](https://github.com/krpc/krpc/pull/894) |
| Service versioning | [services/service-versioning.md](design/services/service-versioning.md) |
| Debug service | [#955](https://github.com/krpc/krpc/issues/955) |
| Editor part API | [PR #788](https://github.com/krpc/krpc/pull/788) |

## 1.0 — protocol rewrite

A single breaking wire format carrying the components below; they land together because they
share the format. Overview: [protocol/single-connection.md](design/protocol/single-connection.md),
meta-issue [#906](https://github.com/krpc/krpc/issues/906) ([protocol/improvements.md](design/protocol/improvements.md)).

| Feature | Design doc |
| --- | --- |
| Single bidirectional connection | [protocol/single-connection.md](design/protocol/single-connection.md) |
| Message ids (async messages) | [protocol/request-ids.md](design/protocol/request-ids.md) |
| Client → server streams | [protocol/reverse-streams.md](design/protocol/reverse-streams.md) |
| Batching / transactions | [protocol/reverse-streams.md](design/protocol/reverse-streams.md) (#903) |
| Tick control — guaranteed one RPC/batch per physics update (#251) | — |
| Stream freezing removal | [protocol/stream-freezing-removal.md](design/protocol/stream-freezing-removal.md) |
| Stream refcounting / invalidation | [protocol/stream-refcounting.md](design/protocol/stream-refcounting.md), [protocol/stream-invalidation.md](design/protocol/stream-invalidation.md) |

## Unknown / maybe don't do

| Feature | Notes |
| --- | --- |
| Inheritance support | Just a nicety; skipping keeps the OOP model simple — clients translate their OOP to procedures. |
| Constructor calls | Objects are wrappers of game objects, GC'd when unreferenced by the game; constructors add a new refcounted object kind. |
| Autopilot aero | Maybe ignore, defer to MechJeb integration. |
| Client thread safety | Pointless before the 1.0 rewrite — the changes would be lost. |
| SSL / encryption | Likely out of scope; use a proxy / tunnel. |
