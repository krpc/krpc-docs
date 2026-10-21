# Python: Ctrl-C during a call on Windows

With the single connection (#<single-connection>), a Python caller waits on its pending slot for the reader to fill it, where it used to block in its own socket `recv`. On Windows a blocking lock acquire or `Event.wait()` with no timeout may not be interrupted by Ctrl-C, so a Ctrl-C during a long call such as `WarpTo` would wait until the response arrives.

Check the behavior on the Python versions the client supports. If the wait is not interruptible, wait on the slot in short timed slices so `KeyboardInterrupt` is delivered, then abandon the slot as the design specifies.

Design: [single-connection.md](https://github.com/krpc/krpc-docs/blob/main/design/protocol/single-connection.md), "Calls" and "Follow-ups"
