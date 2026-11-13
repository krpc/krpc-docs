# Server side functions: match and switch statements

The expression API has no switch. Add two statement factories to `KRPC.Expression`:

- `Match(value, cases, bodies)` runs the one matching case's body. A `Break` in it belongs to the enclosing loop. For Python's `match`.
- `Switch(value, cases, bodies)` runs from the matching case on, and a `Break` exits the switch. For JavaScript's `switch`, and for C, C++ and Java users of the expression API.

Test values compare by the rules of `Equal`, in order. A case with no test values is the default. Both lower to existing nodes, so the checker and the tree printer gain no node kinds.

This lands before phase 6b of the JavaScript client, which compiles `switch`. Python `match` follows in its own PR.

Design: [server-side-functions/switch.md](../design/server-side-functions/switch.md).
