# Declare the mod a service, class or member requires, and check it in the server

A service that wraps a mod needs each RPC to check that the mod is available. Today that check is a
call at the top of each RPC:

```csharp
static void CheckAPI ()
{
    if (!API.IsAvailable)
        throw new InvalidOperationException ("RemoteTech is not available");
}

[KRPCProcedure]
public static Comms Comms (SpaceCenter.Services.Vessel vessel)
{
    CheckAPI ();
    return new Comms (vessel);
}
```

* A forgotten call reaches the mod's unbound delegates and throws a `NullReferenceException`. The
  Trajectories service in #1253 has 24 RPCs and no checks.
* Each service writes its own helper. The messages differ, with "is not installed" in some and "is
  not available" in others.
* Members of `KRPCClass` types have no check. They rely on an instance only being available from a
  checked RPC.

Proposal:

A new attribute, inherited from the service to its classes and members in the same way as
`GameScene`. The nearest attribute applies:

```csharp
[KRPCService (GameScene = GameScene.Flight)]
[RequiresMod ("Trajectories", typeof (API))]
public static class Trajectories
{
```

* **Binding.** The scanner binds the type's static `bool IsAvailable` with `Accessor.StaticGetter`,
  once per procedure. An optional argument names a different member. A member that is missing or
  has the wrong type is a scanner error.
* **The check.** One helper in `Services` throws `InvalidOperationException`, with the message "X
  is not available". `Invoke`, `ExecuteCallInto` and `CheckExpressionGameScene` call it, so server
  side functions are covered. It runs before the game scene check, as the missing mod is the more
  useful error. Clients and the wire protocol do not change.
* **Evaluated per call.** Availability can change during a game: the Kerbal Alarm Clock service
  reports `KACWrapper.APIReady`.
* **`Available` is exempt.** A static property named `Available` on a tagged service skips the
  check, as it reports whether the mod is present. `krpctest` already relies on this name.
* **Member level.** `SpaceCenter` tags the individual RPCs that fail without FAR or another mod.
  RPCs that fall back, such as the `FAR.IsAvailable` branches in `Flight.cs`, keep their explicit
  code.

Existing services move to the attribute and drop their helpers. This needs care in two services:

* **Kerbal Alarm Clock** names `KACWrapper.APIReady` as its member.
* **Infernal Robotics** has an `Available` getter that runs `IRWrapper.InitWrapper` when the
  assembly has not been found. The tag points at a static member that does the same.

The check covers availability only. A failed binding on an available mod is covered by the stubs in
#1227.

With #1227, the attribute takes a `ModAPI` type (`[RequiresMod (typeof (KerbalAlarmClockAPI))]`),
which supplies the name, the availability and the reason in the message. The first argument goes away.

Design: [partial-loading.md](https://github.com/krpc/krpc-docs/blob/main/design/server/partial-loading.md)
