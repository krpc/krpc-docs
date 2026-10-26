# Derive procedure ids from procedure names

C-nano calls procedures by id. The server numbers procedure ids with a counter per service, in reflection scan order, so nearly any added member renumbers the ids after it. A C-nano build then matches one exact server build, and a stale stub can call a different procedure with the same argument shape without any error.

Compute each procedure id as the first 4 bytes of SHA-256 of its name, little-endian, the rule service ids without an explicit `Id` already use. The scanner rejects a collision within a service and an id of 0. Ids are then as stable as names. The change renumbers every procedure, so it lands with protocol version 2 in 0.8.

Design: [procedure-ids.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/procedure-ids.md)
