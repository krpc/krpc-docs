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
object has a null client, and a call through it dereferences null.

Two smaller problems sit beside it:

* The function type caches (`function_return_types`, `function_parameter_types`) are plain
  members, not shared. Each copy introspects a function again. The implicit copy constructor also
  reads them without taking the shared `function_types_lock`.
* The public API passes the client two ways. A service constructor takes `Client*`
  (`SpaceCenter sc(&conn)`), and a static method takes `Client&`
  (`ReferenceFrame::create_relative(conn, ...)`).

Proposal:

* Put the client's state, the function type caches included, behind one `shared_ptr`. A copy of
  `Client` shares all of it.
* Services and objects hold a weak handle to that state. A call after the last copy is released
  throws `ConnectionError`, as the other clients raise a connection error after a close. A call
  through a default-constructed object throws as well. A strong handle would let a stray object
  keep the socket open, and the C++ client has no `close()`.
* The public API takes `Client&`: service constructors (`SpaceCenter sc(conn)`) and the `Service`
  base. Static methods already do. A hard break in 0.8, with no `Client*` overload. Internals,
  such as the decoders and an object's constructor, keep passing a pointer.
* Update every C++ doc example, test and testee that constructs a service (about 58 files). The
  KSA C++ stubs come from the same template and change with it.
* Native tests in `//client/cpp:test`: an object that outlives its client throws
  `ConnectionError`; an object from a moved client works; two copies introspect a function once.

Changelog `client/cpp`:

- **Breaking:** Service constructors take the client by reference, as in `SpaceCenter sc(conn)`
- Fix objects calling through a destroyed client, which now throw `ConnectionError`

Related to #1195.
