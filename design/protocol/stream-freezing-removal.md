# Removing C++ stream freezing in favor of expression streams (issue #357 follow-up)

**Status:** proposal — direction agreed, no action in v0.6.0 (2026-07-21); supersedes the earlier [#901](https://github.com/krpc/krpc/issues/901) freezing design, which #901 is to be repurposed for.

Supersedes the earlier design for issue #901 ("stream freezing in all clients", agreed 2026-07-03),
which proposed porting freezing to Python, C# and Java and redesigning the C++ implementation. That
approach is dropped in favor of removal; #901 is to be repurposed as the removal issue. The parts of
its analysis that still stand are folded in below.

Depends on: server-side functions (issue #679), then a C++
server-side function translator comparable to the Python and C# ones. Deprecation is deliberately
deferred until the latter lands — see "Plan".

## Context

`krpc::Client::freeze_streams()` / `thaw_streams()` (`client/cpp/include/krpc/client.hpp:48-49`)
temporarily stop stream values from updating, so that a computation reading several streams sees
values that all came from the same physics tick. Added in Oct 2016 for
[issue #357](https://github.com/krpc/krpc/issues/357).

It is implemented **entirely client-side**. There is no `Freeze`/`Thaw` RPC, no protobuf field, and
no server-side concept: the server keeps sending `StreamUpdate` messages at the normal rate
throughout, and the client stops applying them. The mechanism lives in the socket reader thread
(`client/cpp/src/stream_manager.cpp:115-187`) and consists of two `atomic_bool`s handshaking with
the caller:

```cpp
void StreamManager::freeze() {
  should_freeze->store(true);
  while (!frozen->load()) {}
}
```

While frozen, the reader thread keeps draining whole messages off the socket but discards all but
the last, applying that one on thaw. The drain is load-bearing: without it the client would stop
reading, TCP backpressure would build, and the server's send loop — and hence the game — could
stall.

**No other client has this feature, under any name.** Python, C#, Java have nothing equivalent;
Lua has no stream client at all. This has been true since 2016.

## Why remove rather than port

### The implementation is defective, not merely limited

`doc/src/cpp/client.rst:154` promises that "all streams will have their values frozen to values from
the same physics tick". Three confirmed defects stand between that promise and the code (the first
two identified in the #901 analysis):

1. **Coalescing keeps the last *message*, but `StreamUpdate` carries only *changed* streams.** If
   stream A changes early in a freeze and only stream B appears in the final message, A's update is
   silently dropped at thaw and A stays stale until it next changes — potentially a long time for a
   rate-limited or rarely-changing stream. This is a lost update, not just a stale one.
2. **`freeze()` blocks until the *next* `StreamUpdate` arrives**, because the flag is only checked
   after applying a message. With no started streams, or none changing, it spun forever. Fixed
   (Jul 2026) by acknowledging the freeze when a receive poll times out with no partial
   data buffered.
3. **Both handshake loops are busy-waits**, burning a core for up to a receive-poll interval.

Defect 1 is inherent to the message-level design; fixing it properly means a per-stream-id pending
map applied atomically at thaw, which is what #901 proposed. That is real machinery to build and
maintain in four clients, which is the cost this design avoids.

### Expression streams give the guarantee properly

An expression stream evaluates all of its sub-calls in a single server-side pass, so its values
genuinely come from one tick. It is a strictly stronger guarantee than freeze can offer, obtained
without any client-side machinery.

The decisive capability is heterogeneous tuple construction, and it is fully supported.
`Expression.CreateTuple` (`core/src/Service/KRPC/Expression.cs:716-731`) takes each element's type
independently:

```csharp
var elementTypes = elements.Select (e => e.Type).ToArray ();
var method = typeof (Tuple)
    .GetMethods ()
    .Single (m => m.Name == "Create" && m.GetGenericArguments ().Length == elements.Count);
method = method.MakeGenericMethod (elementTypes);
```

`TypeUtils.IsATupleCollectionType` (`core/src/Service/TypeUtils.cs:103-106`) validates per element,
`Expression.ReturnType` reports the nested type tree, and clients rebuild that tree recursively to
decode. So a bundle of `(double, Vector3, string)` round-trips correctly.

Note that lists, sets and dictionaries are **homogeneous** — `CreateList`
(`Expression.cs:734-741`) uses `values.First().Type` for the whole array and throws on mixed
elements. Heterogeneous bundles must use `CreateTuple`.

In Python this is simply:

```python
stream = conn.add_expression_stream(
    lambda: (flight.mean_altitude, vessel.position(rf), vessel.name)
)
```

### Removal simplifies the reader thread

Dropping the feature deletes the `should_freeze`/`frozen` atomics, both spin-wait loops, the drain
loop, and the partial-receive edge case since fixed — the case where a freeze must be
acknowledged without waiting for an update message, because an idle stream would otherwise block
`freeze()` forever.

### One stream, not several

A bundle expressed as a single expression stream is one object with one lifetime, created and
removed in one place. Freezing requires managing N stream objects plus a freeze/thaw scope around
every read site, and the correctness of each read depends on that scope being entered — a
requirement invisible at the read itself. The expression form makes the consistency guarantee a
property of the stream rather than of the caller's discipline.

## Timing gap: C++ expression ergonomics

Freeze exists only in C++, and C++ has the weakest expression support of any client.
`client/cpp/include/krpc/expression_stream.hpp` is 42 lines providing `add_expression_stream<T>` and
`run_function<T>` with **no `return_type` introspection** — the caller must name the result type
themselves — and there is no lambda compiler (Python and C# have one; Java and C++ do not).

This is a sequencing constraint, not an objection: Python and C# are simply the first clients to
have been prototyped, and C++ is expected to get an equivalent translator. But until it does, the
migration asked of a C++ user is to replace two method calls with a hand-built expression tree plus
a hand-written `std::tuple<double, std::tuple<double,double,double>, std::string>` — which would
place the entire cost of the removal on the only audience that ever had the feature.

**Therefore the C++ translator is a prerequisite for deprecation.** The minimum bar is
`Expression::return_type` introspection so the result type is derived rather than transcribed; the
type tree is already exposed server-side via `KRPC.Type` (`core/src/Service/KRPC/Type.cs`, nested
`Types` at `:277`) and both Python (`client.py::_expression_return_type`) and Java
(`Connection.java::buildType`) already walk it. Parity with the Python and C# lambda compilers is
the target.

## Plan

Deprecation is gated on capability, not on a release number. `[[deprecated]]` fires at every call
site whether or not the user can act on it, so attaching it while the C++ replacement is
impractical would produce warning spam that affected users can only silence by pinning an old
version. Shipping server-side functions is necessary but not sufficient: the alternative has to be
usable *from C++* first.

1. **v0.6.0 — no change to the API.** Land server-side functions. Independently of this design,
   correct the overpromise at `doc/src/cpp/client.rst:154` — it claims same-physics-tick
   consistency the implementation cannot deliver (see above) — and fix the `CreateTuple` arity
   guard. Neither depends on the removal decision.
2. **Gate — C++ server-side function translator.** At minimum `Expression::return_type`
   introspection, so an expression stream's result type is derived rather than hand-written;
   ideally parity with the Python and C# translators. Until this lands, freeze/thaw stays as-is and
   undeprecated.
3. **First release after the gate — deprecation.** Mark `freeze_streams`/`thaw_streams` with
   `[[deprecated]]`; the C++ client is C++17 and already adopted this attribute for deprecated
   members (`client/cpp/CHANGES.txt:11`, #904). Rewrite `doc/src/cpp/client.rst:154-158` and
   `:267-275` to present the expression-stream form, with the freeze form shown as superseded.
   Changelog entry under `client/cpp` with a `**Deprecated:**` marker.
4. **The release after that — removal.** Delete the API, the `StreamManager` freeze machinery, and
   the three tests (`client/cpp/test/test_stream.cpp:443,463,481`). Changelog entry with a
   `**Breaking:**` marker.

Users still get a full release cycle of notice, just measured from the point the replacement is
genuinely available rather than from the point it nominally exists.

## Known gaps and loose ends

* **Eight-element ceiling.** `Tuple.Create` has a maximum generic arity of 8; beyond that,
  `CreateTuple`'s `.Single(...)` lookup throws a raw `InvalidOperationException` rather than the
  intended `ArgumentException`, since `Single` throws instead of returning null and the
  `if (method == null)` guard below it is dead code. Worth fixing independently of this work;
  callers needing more than 8 values nest tuples.
* **Streams you did not create.** Expressions require owning the construction site, so freeze's
  ability to hold *existing* stream objects steady — e.g. streams handed to you by library code —
  has no direct replacement. This is the one genuine capability loss. It is believed to be
  unused, and is the only argument for retaining a client-side snapshot primitive instead; the
  decision here is to accept the loss rather than carry that machinery in five clients.
* **Callback and condition-variable semantics.** While frozen, per-stream callbacks and condition
  variables do not fire, and fire once on thaw for the final message. Nothing depends on this
  outside the feature itself, but it should be mentioned in the deprecation note for anyone using
  freeze as a crude callback suppressor.
