# C++: hold the client strongly, add `close()`, and take the client by reference

Services and objects store a raw `Client*` to one copy of `krpc::Client`:

```cpp
Vessel get_vessel() {
  auto conn = krpc::connect();
  SpaceCenter sc(&conn);
  return sc.active_vessel();
}
```

The returned vessel points at the destroyed `conn`, so its next call is undefined behavior. A moved
client, or one in a `std::vector` that grows, dangles the same way. A default-constructed object has
a null client, and a call through it dereferences null.

Two smaller problems sit beside it:

* The C++ client has no `close()`. A connection closes only when every copy of the client is
  destroyed, so six close requirements of the client spec are expected failures.
* The public API passes the client two ways: `SpaceCenter sc(&conn)` and
  `ReferenceFrame::create_relative(conn, ...)`.

Proposal:

* `Client` is one `shared_ptr` to its state. Copies, services, objects and streams hold it, so each
  keeps the connection open, as a Python or C# object does.
* Add `Client::close()`. Calls through any holder then throw `ConnectionError`, and streams and
  events end. It destroys the value and update callbacks, as a callback can hold its own stream or
  an object and form a cycle. A stream that ends, and a connection that fails, destroy them too.
* The release of a stream's last handle stops its callbacks and removes it from the server, whatever
  is queued for the dispatcher thread. A callback that is slower than its updates cannot then keep
  the connection open.
* The stream manager holds no client, which keeps the reference graph acyclic.
* An empty client throws `ConnectionError`, as does a default-constructed object.
* Service constructors take the client by reference, in a change of its own. Service and object
  constructors then take `const Client&`, and stream and event constructors take `Client&`. Only the
  decoders keep a pointer. A hard break in 0.8, with no `Client*` overload.
* Leave KSA alone. It is experimental and builds against the 0.7.0 client.
* A conformance requirement, `test_objects.py::test_call_after_close`. C# and Java fail it as they
  fail `test_call_after_end[close]`, and the websockets testee has no class types.

The design and the rejected alternatives go on the C++ client design page, with the client design docs.

Changelog `client/cpp`:

- Add `Client::close`, which closes the connection for every copy of the client
- **Breaking:** Services, objects, streams and events hold the connection open, so they stay valid once the client is destroyed
- **Breaking:** A client that is not connected throws `ConnectionError`, as does a default-constructed object
- **Breaking:** Service, object, stream and event constructors take the client by reference, as in `SpaceCenter sc(conn)` and `Vessel(conn, id)`

Related to #1195.
