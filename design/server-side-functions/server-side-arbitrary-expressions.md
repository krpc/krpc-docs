# Unrestricted server side functions: calling arbitrary CLR members

**Status:** proposal — design sketch; no GitHub issue filed yet.

Follow-on to [`design/protocol/server-side-functions.md`](server-side-functions.md). That work lets a client build and run a function on
the server, but the function can only call *RPCs* — the curated surface kRPC chose to expose. This
proposal adds an opt-in mode in which a function can call arbitrary CLR members, so a client can
reach game and mod state that no kRPC service wraps.

## Motivation

The driving case is **mods that ship no kRPC service**. Today the only way to reach one is for kRPC
itself to ship a C# wrapper, and the repo has two patterns for it:

* `service/InfernalRobotics/src/IRWrapper.cs` — 1236 lines of hand-written reflection: locate types
  via `AssemblyLoader.loadedAssemblies.TypeOperation`, cache `MethodInfo`s in fields, `Invoke` them.
* `service/RemoteTech/src/API.cs` — an `APILoader` binding `Func<>`/`Action<>` properties to a
  named API type, with a version check.

Both require a kRPC-maintained, kRPC-shipped, kRPC-version-chased DLL per mod. That is
justifiable for a handful of large mods and cannot scale to the long tail: any mod without enough
demand to warrant a service is simply unreachable, and every mod update is a maintenance event for
this repo.

The same reflection binding, built by the *client* at runtime, moves that cost to the person who
actually wants the integration and needs no kRPC release to land.

## Goal

With the feature enabled, a client can build a function that reads a field, sets a property or
calls a method on any type loaded in the game, using the existing expression node algebra, and get
back a value of a type kRPC can already serialize.

Non-goal: making this safe to expose to an untrusted network. See "Security model".

## What this builds on

Most of the machinery already exists:

* **The boundary check.** `ExpressionStream` validates at creation and `RunFunction` calls
  `GetValidReturnType()`, both via `TypeUtils.IsAValidType`. Values of types kRPC cannot serialize
  are already rejected at the wire boundary, which is exactly the restriction this feature needs —
  arbitrary CLR values may exist *inside* a function as intermediate values and simply cannot
  leave it. No new enforcement is required for this.
* **Direct call emission.** `Call`/`CallWithArguments` already compile to a statically typed
  `LinqExpression.Call` of the target's `MethodInfo`. An arbitrary CLR call is the same node with
  the `MethodInfo` obtained by reflection instead of from a procedure signature, minus the
  kRPC-specific scene and null-return checks.
* **Statements and control flow**, so a client-built binding can loop over a mod's collections and
  reduce them to a serializable result inside a single tick.

## Design

### 1. Enabling the feature

New configuration setting, **default off**. When off, every factory below throws, so the feature
is inert rather than merely undocumented.

Open question: global (`Configuration`, alongside `MaxTimePerUpdate`) or per-server. Per-server is
more useful and safer — a localhost server could allow it while a server bound to `0.0.0.0` for
remote control does not — but expression objects live in the global `ObjectStore` and are not
currently attributed to the connection that built them, so per-server enforcement needs that link
established first. Global is proposed for a first pass, with per-server recorded as the intended
end state.

Clients need to discover the setting rather than fail on the first factory call, so it should also
be readable through the KRPC service.

### 2. Naming CLR types

`Type.ForeignType(string assembly, string fullName)` resolves a type from the loaded assemblies.

`KRPC.Utils.Reflection.GetType(name)` looks like the obvious helper to reuse but **cannot be used
as-is**: it deliberately skips `Assembly-CSharp` because enumerating it crashes the NUnit test run,
and `Assembly-CSharp` is precisely where KSP's own types live. Resolution here needs its own path,
taking the assembly name explicitly — which is also what disambiguates two mods declaring the same
type name.

`Type.Code` needs a value for these. A new `TypeCode.Foreign` is proposed, used for introspection
and error messages only; it has no protocol type code and can never be encoded, which is what makes
`ReturnType` fail correctly for a foreign-typed expression.

### 3. Calling members

* `Expression.CallMethod(Type type, string name, IList<Type> parameterTypes, IList<Expression> arguments)`
* `Expression.CallStaticMethod(...)` — same, without an instance argument
* `Expression.GetField` / `SetField`, `GetProperty` / `SetProperty`

Parameter types are given **explicitly** rather than inferred from the arguments. Overload
resolution over reflected members is otherwise ambiguous, and an implicit rule would let a mod
update silently rebind a tree to a different overload. Explicit types fail loudly instead, which is
the correct behavior for a binding the client wrote against a specific mod version.

Static types propagate from the reflected member, so the rest of the algebra — operators, numeric
promotion, collection operations, statements — composes over foreign values unchanged.

### 4. Getting values out

Nothing new. A foreign type is not a valid kRPC type, so `ReturnType` throws and both
`AddExpressionStream` and `RunFunction` reject it. To get data out, the function reduces to
something serializable inside the tree — read a `double` field, call a method returning a string,
build a list of primitives.

Returning opaque handles to foreign objects (an `ObjectStore`-like id the client can pass back into
later expressions but cannot inspect) would remove the need to do everything in one function. It is
deliberately out of scope for a first pass: `ObjectStore` is keyed on `KRPCClass` types, the
lifetime rules for foreign handles are not obvious, and the feature is useful without it.

### 5. Errors

The failure modes are all "the client's assumption about the target no longer holds", and each
needs a message naming what was looked for: assembly not loaded, type not found in assembly, no
member of that name, no overload with those parameter types, argument type not assignable. These
are the errors users will actually hit whenever a mod updates, so they are worth treating as a
feature rather than as exception plumbing.

## Security model

**With this enabled there is no sandbox, and the design does not pretend otherwise.** Arbitrary CLR
calls reach `System.IO`, `System.Diagnostics.Process` and everything else the game process can do.
kRPC has **no authentication** — a client supplies a name and connects — so the only thing
separating a kRPC server from remote code execution is the node algebra being a whitelist, which is
exactly what this feature removes. The default bind address is `127.0.0.1`, but binding to
`0.0.0.0` is a documented and common setup for controlling the game from another machine.

The feature is therefore:

* off by default;
* documented in plain terms — enabling it is equivalent to letting anyone who can reach the port
  run code on the machine;
* worth pairing with a visible indication in the server window while it is on.

**Allowlisting assemblies was considered and rejected.** Restricting calls to `Assembly-CSharp`,
`UnityEngine` and mod assemblies sounds like it preserves safety, but any path that yields a
`System.Type` or reaches `System.Reflection` reopens everything, so the check must be transitive
over the types flowing through the tree, not just the member being called. That is a real sandbox
with a real ongoing maintenance burden, and a leaky one presented as a boundary is worse than an
honest switch: it invites people to enable it on untrusted networks.

## Related existing risk

`MaxTimePerUpdate` is checked *between* continuations in the execution loop (`core/src/Core.cs:428`),
never inside a single evaluation. An infinite `While` in a server side function already hangs KSP's
main thread with no recovery, before this feature exists. Arbitrary calls make it easier to reach
accidentally (a blocking call, a mod method that waits), so the hang should be addressed on its own
rather than as part of this work.

## Client support

Factory API only, for a first pass. Neither client compiler can help: the Python client has no
knowledge of CLR types, and the C# compiler works from `Expression<Func<T>>` lambdas whose types
must resolve at client compile time, which would mean referencing the mod's assembly and pinning
the client to a game version. A C# client that *does* reference a mod DLL could plausibly compile
foreign calls, and that is a reasonable later extension.

This makes the ergonomics noticeably worse than the compiled path — the binding is written as
explicit factory calls, closer to `IRWrapper` than to a lambda. That is the honest cost, and it is
still lower than shipping a service.

## Alternatives considered

* **A read-only reflective accessor RPC** — read fields and properties by path, no method
  invocation, no writes. Much smaller blast radius and no sandbox to maintain. Rejected as the
  primary design because mod interop needs to *call* things (trigger an action, invoke an API
  method), not just observe them. Still a reasonable narrower feature if the unrestricted mode is
  judged too risky.
* **Keep writing a kRPC service per mod** — the status quo. Best experience where it exists, and
  the right answer for major mods; does not scale to the long tail, which is the gap here.

## Testing

* Core tests against a fixture type standing in for a mod assembly: field/property read and write,
  method calls including overload selection by parameter type, and each error case.
* Boundary tests: a function whose result is a foreign type is rejected by both
  `AddExpressionStream` and `RunFunction`; one that reduces to a serializable value is accepted.
* Enablement tests: every factory throws while the setting is off.
* Golden expression-tree tests for the emitted nodes, following the existing
  `ExpressionTreePrinter` suites.
