# Events that carry a value

An event is a stream of `bool` whose `true` results are firings. A firing carries no data, and firings in one stream update coalesce: five `Trigger` calls before an update reach the client as one firing. A service with discrete occurrences that carry data has two workarounds, and both lose something:

- One event per value, such as `ButtonPressed (id)`. This works only for a small, known set of values.
- An event, then a read of the state. The state may have changed again by the time the script reads it.

A stream of `(counter, payload)` does not close the gap either. A stream sends only its latest value in each update, so two occurrences between updates send one payload. The counter shows the loss but cannot recover the payload. A client callback receives values in order, but a script that polls the stream coalesces them again.

The gap is occurrences that must each arrive with their data, such as a log of button presses, contract completions or part failures.

## Proposal

A core stream class that queues firings and sends the unsent ones as a list. Each update sends a `list<T>` of the firings since the last update that was sent, and `Sent` clears the queue. An update with no new firing sends nothing.

- **No protocol change.** The wire carries a list stream, which every client already decodes.
- **No loss and no duplicates.** Streams are per client, the server tells each stream when its result is sent, and TCP drops no update. So each firing arrives once.
- **No counter.** Each result holds only new firings.

The server side mirrors `EventStream`, which already resets its value in `Sent`. A service creates the stream with a constructor that takes the element type, as `Service.Event` does, and calls `Trigger (value)` from the thread that updates the server.

The remaining work is in the service definitions and the clients:

- A typed event in the service definitions, so `clientgen` and the dynamic clients know the element type. Or a procedure returning a plain list stream, if the client API stays a stream.
- The client API: a callback called once per element, and `wait` returning the next value. A client keeps the elements its script has not yet seen.
- Conformance tests: firings in one update all arrive, in order, and none arrives twice.

To decide:

- Whether a typed event is a new type in the service definitions, or a stream of `list<T>` with client helpers.
- The queue bound on the server, and what happens when a client falls behind. A rate limit holds firings longer.
- Whether `KRPC.AddEvent` gains a typed form, firing with the value of an expression.

## Workaround Without Core Changes

A service can do this today with a property of type `(counter, list<T>)`, holding the counter and the last N payloads in a ring buffer per source. The client keeps the last counter it handled and takes the entries after it. Nothing is lost while fewer than N firings happen per update, and a larger gap shows as `counter - seen > N`. Each change resends all N payloads, and each script unpacks the tuple itself.

No current service needs either. The Raster Prop Monitor service ([design](../design/services/raster-prop-monitor.md)) uses one event per button and streams for state. A service that needs a value per firing is the time to schedule it.
