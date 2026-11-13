# Python: defects found writing the design doc

Writing the client's design doc turned up these defects. Paths are relative to `client/python/`, and known conformance failures are in `conformance/expected-failures.txt`.

* **`types._wrapped_subclasses` pins every client.** Its values are subclasses whose `_client` is the weak key, and each stub service adds one in `__init__`. With stubs installed, a closed and dropped client is never collected. Without them it is.
* **Passing an object between a stub and a dynamic client.** `Types.coerce_to` reads `_service_name`, which a stub class lacks, and `Client._encode_call` catches only `ValueError`. The call raises `AttributeError` in either direction.
* **A malformed size after a buffered message escapes.** `Connection.has_message` accepts a six byte prefix of value 0, and `Session._handle_buffered` then gets an uncaught `MalformedSize`. A call raises it raw. The reader thread dies with the connection not failed, so streams stop silently until the next call.
* **An update sent with a response is lost for an event inside a value.** `Session._stream_id` registers only a directly returned stream or event. `StreamManager.update` drops the update if the caller has not decoded the value yet, so a firing is lost. No bundled service returns such a value.
* **The first value failing to decode gives no signal.** `StreamManager._decode` drops it as the spec requires, but `Stream.__call__` then blocks until a decodable update arrives, and nothing is logged.
* **An enumeration only the server declares breaks a merged member.** `_stub_definitions` registers enumerations only from the stub, and `check_type_is_known` checks only structures. A class member using one is added at connect, and raises `TypeError: 'NoneType' object is not callable` when called.
* **Some member names fail the whole connect.** `service._construct_func` raises `SyntaxError` for a parameter named `cls`, and `_create_enum_type` raises `ValueError` for a value named `Mro`. `_skipping_unknown_types` catches only `UnknownTypeError`, so `connect()` fails.
* **An `ImportError` in any stub downgrades silently.** `services_init.py.tmpl` catches it around all the stub imports, so every service turns dynamic with no message.
* **Without stubs, a service the server lacks is `None`.** `services_init.py.tmpl` swaps each stub class for a function returning `None`, and `Client.__init__` assigns the result to an attribute for every shipped service. `_load_services` replaces only the services the server has, so a call through another fails with an error about `NoneType`. Declaring these attributes and `_services` entries only when the stubs import gives an `AttributeError` naming the service. `_load_services` already handles a missing `_services` entry, and no other code reads it.
* **A value is stored before it is announced.** A read between the reader's store and the dispatcher's announce sees the value, and the late announce then wakes a later wait. The `@flaky` entries for `test_held_stream_ending`, `test_wait_on_condition_object` and `test_spurious_wake[stream]` come from this gap.

## From the parity audit and the client guide rewrite

Still open from the client API parity audit (2026-07-21) and the client guide rewrite (2026-10-29), re-checked against `main` on 2026-11-09.

* **Any iterable coerces to a list,** so a string passed for a list becomes a list of characters (`test_wrong_collection[string-for-list]`).
* **Plain calls check only that an unsigned number is not negative.** `2**32+1` to a `uint32` arrives as 1. `run()` checks the range (`test_out_of_range[sint32-above]`).
* **Ordering a remote object against another type raises `NotImplementedError`** in `ClassBase.__lt__` and the other comparisons, in place of returning `NotImplemented`.
* **A procedure and a property with one name lose the procedure, and enumeration values that differ only in case collapse** (audit 38, 40). Not re-checked since the client naming contract (#1237).
* **Docstrings can be lost** when a type is first built from another service (audit 48). Not re-checked.

## From the client errors review

Found reviewing the `client-errors` branch (2026-11-11). Both predate it.

* **A string with a lone surrogate raises `UnicodeEncodeError`.** `Encoder.encode_string` calls `str.encode("utf-8")` unguarded. The error is a `ValueError`, so a program and the testee see an argument error. The client errors design names this case `EncodingError`, a value of the right type the client cannot write. No conformance test covers it.
* **`run()` turns every argument encoding failure into a `TypeError`.** `Connection._encode_argument` catches `Exception` around the coercion, the check and `Encoder.encode`, so an `EncodingError` and a `ValueError` for a value out of range both reach the program as `TypeError`. A plain call raises them as they are.
