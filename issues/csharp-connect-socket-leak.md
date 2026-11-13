# C#: close the socket when a TCP/IP connect fails

`TCPIPTransport.Open` (`client/csharp/src/TCPIPTransport.cs`) creates a `Socket` and connects it.
It closes the socket only when the timed wait runs out:

* With no timeout, `socket.Connect` throws a `SocketException` for a refused or unreachable server,
  and the socket is not closed.
* With a timeout, `socket.EndConnect` throws for a connection refused before the timeout, and the
  socket is not closed either.

The handle stays open until the garbage collector finalizes the socket. A program that retries a
connect in a loop, such as until the game starts, holds one socket per failed attempt in the
meantime. `LocalTransport.Open` closes its socket on a failed connect.

Proposal:

* Close the socket on any exception from the connect, as `LocalTransport.Open` does, and rethrow.
* Test it in the C# client's tests: connect to a port with no listener in a loop, and check that the
  process's open handles do not grow.

The code moved from `Connection.Connect` to `TCPIPTransport` on the `client-consistency` branch
unchanged. The leak predates it.
