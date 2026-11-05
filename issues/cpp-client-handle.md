# C++: hold the client by handle, and take it by reference in the public API

`krpc::Client` is a copyable handle. Its state is shared pointers, and the connection closes when
the last copy is released. Services and objects store a raw `Client*` to one particular copy:

```cpp
Vessel get_vessel() {
  auto conn = krpc::connect();
  SpaceCenter sc(&conn);
  return sc.active_vessel();
}
```

The returned vessel points at the destroyed `conn`, so its next call is undefined behavior. A
moved client, or one in a `std::vector` that grows, dangles the same way. A default-constructed
object has a null client, and a call through it dereferences null. The stream manager keeps its
own copy of the client, and streams and the objects they decode point at that copy. Those objects
dangle once the connection closes.

Two smaller problems sit beside it:

* The function type caches (`function_return_types`, `function_parameter_types`) are plain
  members, not shared. Each copy introspects a function again. The implicit copy constructor also
  reads them without taking the shared `function_types_lock`.
* The public API passes the client two ways. A service constructor takes `Client*`
  (`SpaceCenter sc(&conn)`), and a static method takes `Client&`
  (`ReferenceFrame::create_relative(conn, ...)`).

Proposal:

* Put the client's state, the function type caches included, behind one `shared_ptr`. A copy of
  `Client` shares all of it. The copy operations are defaulted explicitly, so a move copies and a
  moved-from client stays connected.
* A new public `krpc::WeakClient` holds a weak pointer to that state. Services, objects, streams
  and the stream manager hold one. `WeakClient::lock()` throws `ConnectionError` after the last
  copy is released, as the other clients raise a connection error after a close. It also throws
  for an empty handle, the handle of a default-constructed object. A strong handle would let a
  stray object keep the socket open, and the C++ client has no `close()`.
* The exception throwers move into their own shared struct. The stream manager holds it, as it
  throws stream errors while the client's state is being destroyed.
* The decoders take a `const WeakClient&`, as they only stamp it onto decoded objects. A stream
  read then needs no live client. An object's constructor and the stream constructors keep
  taking a pointer.
* `build_request` and `build_call` become static, as they use no state.
* The public API takes `Client&`: service constructors (`SpaceCenter sc(conn)`) and the `Service`
  base. Static methods already do. A hard break in 0.8, with no `Client*` overload.
* Update every C++ doc example, test, benchmark and testee that constructs a service (about 60
  files). Leave KSA alone. It is experimental and builds against the 0.7.0 client.
* Native tests in `//client/cpp:test`:
  * an object or a service that outlives its client throws `ConnectionError`;
  * a default-constructed object throws `ConnectionError`;
  * an object that outlives the copy of the client it came from works, as does one from a client
    in a `std::vector` that grows;
  * an object decoded from a stream throws `ConnectionError` once its client is gone.

  There is no test that two copies introspect a function once. The server updates
  `rpcs_executed` once per server update, so the count lags and cannot count the calls.
* A conformance requirement, `test_objects.py::test_call_after_close`: a call through an object
  after its connection is closed raises the connection error. The C++ testee keeps a
  `WeakClient` for each closed connection, as a program keeps its services. This also passes
  `test_call_after_end[close]` for C++. C# and Java fail it as they fail
  `test_call_after_end[close]`, and the websockets testee has no class types.

Changelog `client/cpp`:

- **Breaking:** Service constructors take the client by reference, as in `SpaceCenter sc(conn)`
- Fix objects calling through a destroyed client, which now throw `ConnectionError`

Related to #1195.
