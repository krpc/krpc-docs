# C-nano: retry POSIX serial reads and writes interrupted by a signal

The POSIX serial transport (`client/cnano/src/serial.c`) fails a read or write with
`KRPC_ERROR_IO` when a signal interrupts it. The socket transport beside it retries on `EINTR`.

* A program with a signal handler installed without `SA_RESTART`, such as a `SIGALRM` timer, can
  have `read` return -1 with `EINTR` while it waits for a response. The call fails with part of
  the message still on the line. The next call reads that remainder as its own response.
* `krpc_serial_write` makes one `write` call, and fails on a short write as well as on `EINTR`. A
  serial port in blocking mode rarely writes short, but a pipe or pty can.

Proposal:

* Retry `read` and `write` on `EINTR`, as `socket.c` does with `KRPC_INTERRUPTED`.
* Loop `write` until every byte is written, as `krpc_socket_write` does.
* Test both in `//client/cnano:communication-*` over a pty pair or pipe, with a timer signal and no
  `SA_RESTART`, as `test_socket.cpp` tests the socket read.

The Windows serial transport is unaffected: `ReadFile` and `WriteFile` are not interrupted by
signals.
