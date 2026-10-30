# Conformance: a driver helper for a callback that runs a command on itself

`test_threading.py::test_remove_callback_from_itself` builds its `Callback` by hand and sends
`AddCallback` itself. The callback's behavior is a command naming the callback's own id, and
`Stream.add_callback` assigns the id only as it sends the add.

* Let `Stream.add_callback` take the behavior as a function of the new callback's id.
* Use it in the test, and drop the hand-built `Callback`.
