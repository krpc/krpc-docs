# Release what a yielded call holds when its client disconnects

A procedure that yields keeps its state in the continuation it throws. `Core` drops a
continuation whose client has disconnected (`core/src/Core.cs`, "Ignore the continuation if the
client has disconnected"), and the procedure has no hook to run on that drop. A continuation that
holds a game resource leaks it.

* `ScanSat.Map` builds a `SCANmap` with its own `RenderTexture` over many frames. It destroys the
  map once the render completes or throws. A client that disconnects mid-render leaves the map and
  its texture behind until the game exits.
* The other yielding procedures hold nothing that needs releasing: the `Debug` teleport waits, the
  `AutoPilot` wait, staging, the EVA ladder and boarding waits, the editor and scene loads.

Proposal:

* A continuation that holds a resource is wrapped with a release action, such as
  `YieldException<T> (continuation, release)`. `Core` runs the action when it drops the
  continuation on client disconnect, and on any other path that drops it.
* Test the drop in `//core:test` with a continuation that counts its releases.
* Move `ScanSat.Map` to it.

Until then, a service can track its yielded state in a `ClientOwnedObjects` collection with a
release action, swept by a `ClientCleanupAddon`. It removes the entry when the call completes,
and the sweep releases the entries of a disconnected client.
