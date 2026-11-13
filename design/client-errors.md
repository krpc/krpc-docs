# Client errors

**Status:** in progress. Phases E1 to E5 are built, with no PR yet, and the build departs from
this design as [Deviations](#deviations) lists. [Type ids](#type-ids), phase E0, merged in
#1324. Issue: [client-errors.md](../issues/client-errors.md).

The errors each client raises grew one client at a time. They differ in their names, their bases,
which situations raise which error, and whether a program can catch a whole category. The
conformance spec's five error kinds were written around what the clients did, so they are an
input here, not the answer.

This doc proposes one shape for every client: which errors exist, what each derives from, and
which situation raises which.

## Principles

1. **A mapped server exception is the language's own type.** A `KRPC.IndexOutOfRangeException`
   is Python's `IndexError`, C#'s `System.IndexOutOfRangeException` and so on, so it reads and is
   caught as the same failure in local code would be. It derives only that type, not `ServerError`,
   in every client. Two bases is multiple inheritance in Python and C++, and impossible in C# and
   Java. A program that handles every error uses the language's own catch-all.
2. **Every other error the client raises derives one base per client, `RemoteError`.** The name
   follows `RemoteObject` and `RemoteService`. C# and Java spell it `RemoteException`, as their
   conventions use the `Exception` suffix.
3. **One subclass per category a program handles differently.** A program reconnects on a
   connection error, gives up on an encoding error, and re-adds a stream on a stream error.
4. **Misuse is the language's own error.** An argument the client rejects is the native argument
   error, and a call made in the wrong state is the native state error, as from any local library.
   Neither derives `RemoteError`, as nothing remote has failed.
5. **No raw internal error escapes.** A decode that fails inside protobuf, a short read or a
   failed socket write is wrapped in the category it belongs to, with the original as its cause.
   The program's own errors, raised from its callbacks, are never wrapped.
6. **A clean break.** The renamed errors get no deprecated aliases. Most programs leave errors
   uncaught, and 0.8 breaks enough already that aliases would only muddy the API.

## Proposed errors

Python names. C++ uses the same names in `krpc::`. C# and Java swap `Error` for `Exception`.

`ServerError` replaces `RPCError`. RPC is the mechanism under calls, streams and events, and a
server error reaches the program through any of them. `CallError` names only calls, and reads as
a fault in a call object. `ProcedureError` uses the protocol's term, which the guides do not lead
with. `ServerError` is defined as an error the server reports, which may be the program's mistake,
such as `KRPC.ArgumentException`.

`CompilationError` replaces `FunctionCompilationError`. It is shorter, and covers any part of
compiling, not only a function.

| Error | Base | Raised for |
| --- | --- | --- |
| `RemoteError` | the language's runtime error, see below | Never raised itself. Catches every error the client raises that is not a native type |
| `ConnectionError` | `RemoteError` | Connecting fails, the server refuses the connection (`status`), the connection fails or ends (`reason`), and every call after it has |
| `ServerError` | `RemoteError` | An error the server reports, through a call, a stream or an event, with no mapped type in the language: an exception a service declares, a mapped exception the language has no type for, or an error with no type. Generated exception classes derive it, such as `KRPC.ObjectDestroyedException` and `KRPC.ObjectNotLoadedException` |
| `StreamError` | `RemoteError` | A stream or event that has been removed, read before its first value, or that cannot be added |
| `EncodingError` | `RemoteError` | A value of the right type that fails to encode, or a value that fails to decode |
| `CompilationError` | `RemoteError` | Code the client cannot compile into a server side function or expression (Python, C#) |
| native argument error | the language's | An argument the client rejects before it sends anything |
| native state error | the language's | A call the client rejects in the current state |
| native interrupt | the language's | A call or wait the thread is interrupted in |
| mapped server exception | the language's mapped type only | A server exception with a mapped type |

### Native errors per language

| Language | Argument error | State error | Interrupt |
| --- | --- | --- | --- |
| Python | `ValueError`, or `TypeError` for a value of the wrong type | `RuntimeError`, or `TypeError` for calling a declaration | `KeyboardInterrupt` passes through |
| C++ | `std::invalid_argument` | `std::logic_error`, and `std::system_error` for a misused lock | – |
| C# | `ArgumentException` and its subclasses | `InvalidOperationException` | `ThreadInterruptedException` |
| Java | `IllegalArgumentException` | `IllegalStateException` | `java.util.concurrent.CancellationException`, with the thread's interrupt flag set |
| Lua | a string in Lua's form, `bad argument #1 to 'run' (...)`, at the caller's level | a string, as for an argument | – |

- An interrupted call or wait leaves the connection open, so it is neither `ConnectionError` nor
  `StreamError`. Java's interrupt was a `ConnectionException` wrapped in `RPCException` for a call,
  and a `StreamException` for a wait. Java cannot throw the checked `InterruptedException` from an
  unchecked API, and `CancellationException` is the unchecked one the language has.
- Lua has no error types, so its misuse errors stay strings, in the form its own functions use.
  Only the errors in the table above are Lua error objects.
- Java's `NullPointerException` for a null object id is an argument error, so it becomes
  `IllegalArgumentException`.

### Mapped server exceptions

A mapped server exception is raised as the native type. What its generated name is depends on the
language:

| Client | Raised as | Generated name |
| --- | --- | --- |
| Python | A generated class with the native type as its one base, `class ArgumentException(ValueError)` | The class, so `except conn.krpc.ArgumentException` catches it |
| C++ | The native type itself, `std::invalid_argument` | An alias in the service class, `using ArgumentException = std::invalid_argument;` |
| C# | The native type itself, `System.ArgumentException` | None. A `using` alias is local to its file. The class generated today, which is never thrown, goes |
| Java | The native type itself, `IllegalArgumentException` | None. Java has no type aliases. The class generated today, which is never thrown, goes |

- **Python keeps a class per exception.** Its server side function compiler finds the server
  exception a Python class stands for from the class (`functionstatements.py`). An alias would
  compile `raise conn.krpc.ArgumentNullException(...)` as `ArgumentException`, and let
  `except conn.krpc.ArgumentOutOfRangeException` catch all three argument exceptions. It would
  also make `KRPC.InvalidOperationException` an alias of `RuntimeError`, the base of
  `RemoteError`, so `except conn.krpc.InvalidOperationException` would catch every kRPC error. A
  class per exception keeps the ruling of [client-codegen.md](client-codegen.md) that
  `ArgumentNull` stays distinct from `Argument`.
- **A generated class that is never raised is a trap:** a `catch` naming it never fires. Python had
  this as audit bug 26, and C# and Java have it today.
- **A mapped exception with no native type in a language** stays a generated class deriving
  `ServerError`. C++ has no type for `NullReferenceException`, `NotSupportedException` or
  `TimeoutException`. Java has none for `TimeoutException`, as
  `java.util.concurrent.TimeoutException` is checked.
- **Any service's mapped exceptions are covered,** not only those of `KRPC`. A service may set
  `MappedException` on any exception. clientgen reads `mapped_type` per exception, and C#'s table
  of `KRPC` exceptions in `Connection.cs` goes, in favor of a table in `lang/csharp.py` as the other
  languages have.
- In C++, C# and Java, mapped exceptions that share a native type cannot be told apart by type.
  The server's message says which.
- The reference docs of the `KRPC` exceptions name the type each is raised as in each language.

### Arguments that fail to encode

An argument the program got wrong raises the native argument error: a value of the wrong type, a
number out of the range of its type, a tuple or structure of the wrong length, or a null where the
type allows none. `EncodingError` is only for a value of the right type that the client still
cannot write, such as a Python string holding a lone surrogate, which has no UTF-8 form.

The encoder itself raises the argument error, not only the call path, as the conformance testees
call the encoder directly. The spec accepts either error today, and E1 narrows it to this split.

### Timeouts

A wait with a timeout returns false when the timeout passes, as each language's own waits for a
signal do: Python's `Event.wait`, C++'s `condition_variable::wait_for`, C#'s `WaitHandle.WaitOne`
and Java's `Condition.await`. kRPC's waits are of that kind, as the program reads the value
separately. Languages throw only when getting a value under a deadline, such as `Future.result`,
which no kRPC operation does.

Handshake and stall timeouts are connection errors. So no client raises a timeout error of its own,
and the testee protocol's unused `TIMEOUT` kind goes, in E1. A server's `KRPC.TimeoutException` is
a mapped exception like any other: Python's `TimeoutError`, an `OSError`, and C#'s
`System.TimeoutException`. An operation that gets a value under a deadline, if one is added,
raises the language's native timeout error.

### Streams

Every removal of a stream or event raises `StreamError`, whether the program or the server removed
it. A program has one thing to do about a removed stream, and the message says who removed it. The
other ways a stream ends keep their own errors:

- **Its procedure throws.** The error a call raises for that exception, so a program handles a
  failed procedure the same whether it calls or streams it.
- **The connection closes or fails.** `ConnectionError`, as for a call.

The server removes a stream only with `KRPC.StreamRemovedException`, which has no
`MappedException`. Each client translates it into `StreamError` by name, where it builds the error
of a stream's result: Python's stream manager, C++'s stream manager, C#'s `StreamManager.cs` and
Java's stream manager. clientgen generates no class for it in C# and Java, and an alias of
`StreamError` in Python and C++, from a special case in `lang/*.py`. Python's runtime builder of
exception types (`types.py`) has the same special case.

Two of `StreamError`'s situations are narrow:

- **A read before the first value** happens only on a thread that holds the stream's condition, as
  a read elsewhere blocks until the first value.
- **A stream that cannot be added** is one the client rejects before sending, such as a stream of a
  procedure that returns an event.

### The base of `RemoteError`

| Language | Base | Reason |
| --- | --- | --- |
| C++ | `std::runtime_error` | An error a program cannot prevent by checking its inputs. It stores the message, with a `noexcept` copy. The errors derive it today |
| Python | `RuntimeError` | As C++. The errors derive it today |
| Java | `RuntimeException` | The language's runtime error, and unchecked, see below |
| C# | `System.Exception` | .NET has no runtime and logic split, and its guidance is to derive `Exception`, not `ApplicationException` |
| JavaScript, planned | `Error` | Custom errors extend `Error` |
| Lua | none, a `pl.class` class | Lua errors are any value, see below |
| C-nano | none | Error codes, see [C-nano](#c-nano) |

Java's `krpc.client.RemoteException` shares its name with the checked `java.rmi.RemoteException`.
The package tells them apart, and kRPC programs do not use RMI.

### Python: `ConnectionError`

Python keeps the name `ConnectionError`, though it shadows the builtin, which is an `OSError`.

- A program meets it only by importing it, or as `krpc.ConnectionError`.
- The standard library does the same: `concurrent.futures.TimeoutError` and `asyncio.TimeoutError`
  shadowed the builtin `TimeoutError`, as `requests.exceptions.ConnectionError` shadows this one.
- Every client then has one name: `ConnectionError` in Python and C++, `ConnectionException` in C#
  and Java. `ServerConnectionError` was the alternative, in every client or in Python alone.
- It derives `RemoteError`, so `except OSError` does not catch it, though it catches a server's
  `KRPC.TimeoutException`. The Python guide says so.

### Lua: error objects

Lua raises any value with `error`, and `pcall` returns it. The client raises strings today, so a
program tells the categories apart only by matching the text. It raises objects instead:

- Each error is an instance of a `pl.class` class, the hierarchy of the other clients:
  `krpc.RemoteError` and its subclasses. `krpc.ConnectionError:class_of(err)` checks a category,
  and matches subclasses.
- Fields carry what the other clients' types carry: `message`, `cause`, and `status`, `reason`,
  `service` and `name` where they apply.
- `__tostring` gives the message, so `print(err)` and `tostring(err)` work as with a string.
  `__concat` lets `'failed: ' .. err` work too.
- Lua has no native error types, so every server error is a `ServerError`, carrying its service
  and name.
- The client raises with `error(value, 0)`. A message starts with the error, with no source
  position in front.
- A program that parses the error as a string, such as `err:find(...)`, breaks. Its text was never
  specified.
- An uncaught error prints through `__tostring` on Lua 5.2 and later. Lua 5.1 prints "(error
  object is not a string)", and 5.1 is supported on a best effort basis.
- Misuse stays a string in Lua's own form, see
  [Native errors per language](#native-errors-per-language).

Strings with a category prefix were the alternative. They keep string handling working, but leave
`status`, `reason` and the cause as text to parse.

### Messages

A client error's message is one sentence saying what failed. Where another error caused it, the
cause's own message follows after a colon, as in `Connection failed: Connection reset by peer`.
The cause is also attached by the language's own means: `__cause__`, a nested exception, an inner
exception, `getCause()`, or the Lua object's `cause` field. A server error keeps the format
[client-codegen.md](client-codegen.md) rules: its description, then the server's stack trace.

The spec checks that a message carries its cause's message, as the connection tests do already,
and nothing more of the text.

### Java: unchecked

`RemoteException` extends `RuntimeException`, so every Java error is unchecked, as in C# and in
current Java libraries such as gRPC and the AWS SDK.

- Generated methods drop `throws RPCException`. Javadoc `@throws` still documents each error.
- `Connection.newInstance` and `close` drop `throws IOException`. A program's `catch (IOException)`
  around them then fails to compile, as the exception is never thrown. Keeping the clause would
  declare an exception that is never thrown.
- A program's other `catch` blocks and `throws` clauses still compile, apart from the renamed types.
- A connection error during a call is no longer wrapped in `RPCException`, which the checked types
  forced.

### Situations

What each situation raises under this proposal, against the spec's kind today.

| Situation | Proposed | Spec today |
| --- | --- | --- |
| Connect fails, refused, handshake fails | `ConnectionError` | connection |
| A local socket path too long for a socket address | native argument error | connection or argument |
| No default local socket path, as the user name cannot be found | `ConnectionError` | not specified |
| Connection lost, closed, or a call after either | `ConnectionError` | connection |
| A wait or end callback, when the connection closes or fails | `ConnectionError` | connection |
| A call or wait the thread is interrupted in | native interrupt | any error |
| Server error with a mapped type | the mapped type | RPC, as the native type |
| Server error a service declares, or with no type | generated class or `ServerError` | RPC |
| A call on a null or default object | the server's `ArgumentException`, a mapped type | RPC, as the native type |
| A read or wait on a stream the program removed | `StreamError` | the stream error, or `KRPC.StreamRemovedException` |
| A stream whose procedure throws | the error a call raises for it: the mapped type, or a generated class deriving `ServerError` | the call's error, same type and message |
| A stream or event the server removes | `StreamError` | `KRPC.StreamRemovedException`, or the stream error |
| A read before the first value, on a thread holding the condition | `StreamError` | not specified |
| A stream of a procedure that returns an event | `StreamError` | stream |
| Streaming a function with arguments, or a compiled function that takes parameters | native argument error | argument |
| A run or stream at a type that cannot hold the function's value | native argument error | argument |
| An argument of the wrong type, out of range, of the wrong length, or null where none is allowed | native argument error | encoding or argument |
| An argument the client cannot represent on the wire, such as a Python string with a lone surrogate | `EncodingError` | encoding or argument |
| A result that fails to decode | `EncodingError` | encoding |
| A timeout, argument count or null the client rejects | native argument error | argument |
| A call in a state the client rejects, such as calling a declaration | native state error | not specified |
| A service definition the client cannot use, such as an unknown type code | the member is skipped, with a warning | not specified |
| A service definition that is malformed, such as a duplicate or a cycle | `ConnectionError` at connect | not specified |
| Code that fails to compile | `CompilationError` | not specified |
| An error a callback raises | printed, and the stream carries on | printed |
| A fatal error a callback raises, through the testee's `FATAL` behavior | passed out of the add, remove or close unchanged | the same |
| A wait that times out | returns false | returns false |
| A deprecated member | a warning, no error | a warning |

## C-nano

C-nano returns a `krpc_error_t` from every function. It follows the pattern above with codes in
place of types: one code per category, and a last-error record for what an error object carries.
Each detail costs flash or RAM on a microcontroller, so the program picks how much the library
keeps.

### What C-nano does today

- **Categories span several codes.** A connection error is any of four codes, and an encoding
  error either of two.
- **A server error is only text.** The service, name and description share one message buffer,
  kept only under `KRPC_ERROR_MESSAGES`. A program tells exceptions apart by parsing it.
- **Connection details are lost.** A refused status, a disconnect reason and the server's message
  go only to `KRPC_PRINT_ERROR`. A transport's failure carries no text.
- **Some situations take the wrong code.** A failed handshake write is `KRPC_ERROR_ENCODING_FAILED`,
  a local socket path too long is `KRPC_ERROR_IO`, and a failed allocation is an encoding or
  decoding failure.
- **Default builds still parse a server error.** With no messages, the `Error` is decoded with
  no callbacks, which links its descriptor for nothing.

### Codes

| Code | Category | Replaces |
| --- | --- | --- |
| `KRPC_ERROR_CONNECTION` | `ConnectionError` | `_CONNECTION_FAILED`, `_CONNECTION_REFUSED`, `_NO_RESULTS`, and `_IO` and `_EOF` from a library function |
| `KRPC_ERROR_SERVER` | `ServerError`, and every server exception, mapped or not | `_RPC_FAILED` |
| `KRPC_ERROR_ENCODING` | `EncodingError` | `_ENCODING_FAILED`, `_DECODING_FAILED` |
| `KRPC_ERROR_ARGUMENT` | native argument error | `_IO` for a path too long, `_ENCODING_FAILED` for a null or missing argument |
| `KRPC_ERROR_NO_MEMORY` | native out of memory error | `_ENCODING_FAILED` and `_DECODING_FAILED` for a failed allocation |
| `KRPC_ERROR_BUFFER_TOO_SMALL` | native argument error, kept apart | unchanged |
| `KRPC_ERROR_IO`, `KRPC_ERROR_EOF` | transport only | unchanged |

- **One code per category a program handles differently** (principle 3). A program reconnects on
  `KRPC_ERROR_CONNECTION`, in place of testing four codes.
- **`_IO` and `_EOF` belong to transports.** A transport's `read`, `write` and `close` return
  them, as do `krpc_read` and `krpc_write`. A library function that gets one returns
  `KRPC_ERROR_CONNECTION`, with the transport's code as the cause. Custom transports stay as they
  are.
- **A response without one result is a protocol error.** It ends the session as an unexpected
  message does, so `_NO_RESULTS` goes.
- **`_BUFFER_TOO_SMALL` stays apart from the argument error.** A program handles it by retrying
  with a larger buffer.
- **A mapped server exception is a server error.** C has no native error types, so its service
  and exception ids tell it apart, as for any other exception.
- **No remote error base.** Every code other than `KRPC_OK` is an error of the library, so the
  conventions file names no remote error type, as today.
- **A clean break** (principle 6). The old names go, with no aliases, and the values are
  renumbered from -2. Programs use the names. -1 is no code, so it can mark a field of the
  [last error](#the-last-error) that does not apply.

### The last error

```c
typedef struct {
  krpc_error_t code;   /* The code the failing function returned */
  krpc_error_t cause;  /* KRPC_ERROR_IO or KRPC_ERROR_EOF behind a connection error, else -1 */
  uint32_t service;    /* The id of the service of the server's exception, else 0 */
  uint32_t exception;  /* The id of the exception within its service, else 0 */
  int16_t status;      /* The ConnectionResponse status of a refused connection, else -1 */
  int16_t reason;      /* The Disconnect reason of an ended connection, else -1 */
} krpc_error_info_t;

const krpc_error_info_t* krpc_get_error_info(void);
const char* krpc_get_error_message(void);
```

- **One record, filled on each failure,** as `errno` is. A success leaves it as it was. C-nano
  runs one session at a time on the calling thread, so one static record serves.
- **The fields are those of the other clients' errors.** `status` and `reason` as they are,
  `service` and `exception` for the service and name, and `cause` for the chained error.
- **A field that does not apply is -1.** `KRPC_OK` and the `OK` status would read as a cause or a
  status of success, and `CLOSED`, the reason 0, is a real reason. `service` and `exception`
  are unsigned, and 0 is never an id, so they take 0.
- **Values the protocol does not define are kept,** so an unknown status or reason reaches the
  program as its number.

A program checks for one exception after a failed call:

```c
krpc_error_t error = krpc_SpaceCenter_Load(conn, "missing");
if (error == KRPC_ERROR_SERVER && KRPC_IS_EXCEPTION(KRPC_EXCEPTION_KRPC_ARGUMENTEXCEPTION))
  printf("No such save\n");
```

### Type ids

The server names an exception by its `service` and `exception` strings. Comparing them would put the
names in flash, which [procedure-ids.md](protocol/procedure-ids.md) avoided for calls. Exceptions
get ids by the same rule, and so do the other types of a service, so a later client or a later API
that needs them finds them in place:

- **id = the first 4 bytes of SHA-256 of the type's name,** read as a little-endian `uint32`, as
  for a procedure. An `Id` on `[KRPCClass]`, `[KRPCEnum]`, `[KRPCStruct]` and `[KRPCException]`
  sets one by hand.
- **The classes, enumerations, structures and exceptions of a service share one id space.** Third
  party services name types independently, so the service id scopes the type id. A clash within
  one service is fixed by that service's author.
- **The scanner enforces unique type names in a service,** compared case-insensitively. This is
  the type name rule of
  [service-definition-rules.md](protocol/service-definition-rules.md#service-and-type-names), which
  E0 builds. A shared id, or an id of 0, within a service is a scanner error, as for procedures.
- **Procedures keep their own id space.** A service level procedure often shares a class's name,
  such as `RemoteTech.Comms` and `DockingCamera.Camera`. An id is always read where its kind is
  known, so the two spaces never meet.
- **`GetServices` reports every type id:** `uint32 id` on `Class` (5), `Enumeration` (7), `Struct`
  (6) and `Exception` (6). **`Type` gains `uint32 service_id = 6` and `uint32 id = 7`** for a
  class, enumeration or structure type. clientgen never hashes.
- **`KRPC.Error` gains `uint32 service_id = 5` and `uint32 exception_id = 6`,** 0 for an error
  with no exception.
- **`KRPC.Error.name` is renamed `exception`,** as `ProcedureCall` names its `procedure`. The
  field number stays 2, so the wire is unchanged, and only code built from the `.proto` changes.
- **The other fields are additive under protocol version 2.** The other clients ignore them, and
  keep matching by name.
- **clientgen defines the ids per exception,** as the pair `service_id, exception_id` in
  `KRPC_EXCEPTION_<SERVICE>_<NAME>`. `KRPC_IS_EXCEPTION(KRPC_EXCEPTION_...)` compares the pair
  with the last error's `service` and `exception`.

Server side functions name types and exceptions by strings too, such as `Type.ClassType` and
`Expression.Throw`. Variants that take ids are separate work, in
[function-api-by-id.md](../issues/function-api-by-id.md).

Hashing the strings in the client, with a small hash such as FNV-1a, was the alternative. It needs
no protocol change, but puts a hash routine and two string callbacks in flash. It also adds a
second hash rule, against the ruling that consumers never hash.

### Detail levels

| Level | Define | The library keeps | Cost |
| --- | --- | --- | --- |
| Codes | `KRPC_ERROR_CODES_ONLY` | the returned code | none. A response's error is skipped unparsed, so the `Error` descriptor is not linked |
| Details | none, the default | the last-error record | the record, 16 bytes of RAM on AVR, and a few stores at each failure |
| Messages | `KRPC_ERROR_MESSAGES` | the record and the message | `KRPC_ERROR_MESSAGE_LENGTH` bytes of RAM, and each sentence in flash |

- **Details is the default.** An Uno sketch nearly always has 16 bytes to spare, and a sketch
  that needs them defines `KRPC_ERROR_CODES_ONLY`.
- **The library reads the level when it compiles,** as it reads `KRPC_ERROR_MESSAGES` today. The
  `KRPC_CHECK` options are unchanged.
- **One macro at each failure site,** `KRPC_FAIL(CONNECTION, "Connection failed")`, fills what
  the level keeps. Below Messages, the sentence is not compiled. `KRPC_PRINT_ERRORS_TO_STDERR`
  prints the same sentence, so the library has one set of strings.
- **On AVR, the sentences stay in flash.** A plain literal is copied to RAM at startup, so they
  are `PSTR` strings, copied into the buffer with `strcpy_P`.
- **The phase measures each level** in flash and RAM for an Uno build, and the guide states the
  figures.

### Messages in C-nano

Under `KRPC_ERROR_MESSAGES`, the [message rule](#messages) applies: a sentence, then the cause's
text after a colon.

- **A server error** is `Service.Name: description`, then the stack trace, as now. C has no type
  to name the exception, so the qualified name stays in front. An empty description keeps the
  `: ` after the name, which today is dropped.
- **A refused connection or a disconnect** is the sentence, then the server's message.
- **A transport gives its failure's text** with `krpc_set_error_cause(const char* message)`,
  before it returns `KRPC_ERROR_IO`. The bundled transports pass the system's text on hosted
  targets, from `strerror` or `FormatMessage`. The function is empty below Messages, and is
  always defined, as a custom transport compiles apart from the library.
- **The buffer cuts a long message,** as now. `test_whole_message` stays an expected failure for
  that reason.

### Situations in C-nano

| Situation | Code | Details |
| --- | --- | --- |
| An open fails: no address, no endpoint, a port that will not open | `KRPC_ERROR_CONNECTION` | `cause` |
| A local socket path too long for a socket address | `KRPC_ERROR_ARGUMENT` | – |
| The server refuses the connection | `KRPC_ERROR_CONNECTION` | `status` |
| A `disconnect` from the server, in the handshake or during a call | `KRPC_ERROR_CONNECTION` | `reason` |
| A read or write fails, or the connection ends, including in the handshake | `KRPC_ERROR_CONNECTION` | `cause` |
| A call after the session ended, or on a connection whose open failed | `KRPC_ERROR_CONNECTION` | – |
| An unexpected or malformed message, or a response without one result | `KRPC_ERROR_CONNECTION` | – |
| A server error | `KRPC_ERROR_SERVER` | `service` and `exception`, 0 for an error of the whole request |
| An argument or result that fails to encode or decode | `KRPC_ERROR_ENCODING` | – |
| A null string or bytes argument, or an argument index the call lacks or left unset | `KRPC_ERROR_ARGUMENT` | – |
| A failed allocation | `KRPC_ERROR_NO_MEMORY` | – |
| Bytes longer than the program's buffer | `KRPC_ERROR_BUFFER_TOO_SMALL` | – |

### Testing C-nano

- **The testee maps codes to kinds:** the connection, server and encoding codes to their kinds,
  and the argument and buffer codes to `ARGUMENT`. It reports `status` and `reason` from the
  record, and the service and name from a table of the generated `KRPC` and `TestService` macros.
- **C-nano takes the `error-types` profile.** The testee reports the generated macro of an
  exception as its type. A test the profile holds that C cannot express goes in
  `unsupported.txt`.
- **The testee builds at Messages,** as it does today. A native test builds the library at Codes,
  and checks the code of a failed call.
- **Expected failures this clears:** `test_exception_name`, `test_handshake_refused[*]`,
  `test_handshake_unknown_status`, `test_handshake_disconnect`, `test_lost[disconnect]`,
  `test_failed_write`, `test_handshake_failed_write`, `test_description[empty]` and
  `test_null_for_non_nullable[string]`.

## What each client does today

From an audit of the clients on 2026-11-10, and a review against the code. **Bold** is where a
client differs from the proposal.

| | Python | C++ | C# | Java |
| --- | --- | --- | --- | --- |
| Base of client errors | **none**, `RuntimeError` | **none**, `std::runtime_error` | **none**, `Exception` | **none**, mixed checked and unchecked |
| Mapped server exception | generated, derives the builtin | generated, derives the `std` type; **`RPCError` for `NullReference`, `NotSupported`, `Timeout`** | the .NET type itself, for `KRPC` only; **a generated class that is never thrown** | the JDK type itself; **a generated class that is never thrown**; `TimeoutException` generated |
| Declared server exception | generated, derives **`RuntimeError`, not `RPCError`** | generated, derives `RPCError` | generated, derives `RPCException` | generated, extends `RPCException` |
| Stream error type | `StreamError`, **also for streaming a function with arguments** | `StreamError` | **none**: the server's `StreamRemovedException`, and `InvalidOperationException` before the first value | `StreamException`, **also for an ending caused by the connection, and for an interrupted wait** |
| Connection failure during a call | `ConnectionError` | `ConnectionError` | `ConnectionException`; **`ObjectDisposedException`** after close | **`RPCException`** wrapping the connection error, for every failure during a call |
| Encode failure | `TypeError`/`ValueError`; **`EncodingError`** for a wrong length or a negative unsigned value; **`AttributeError`** for a null key or element | – | `ArgumentException` | **`EncodingException`** for a null and a wrong length |
| Decode failure | `EncodingError`; **leaks `IndexError`, `struct.error`, `UnicodeDecodeError` and protobuf `DecodeError`, and decodes some short data silently** | `EncodingError`; **`std::runtime_error`** for a null function result | **`ArgumentException`, `IOException`, `InvalidProtocolBufferException`**; `EncodingException` only for a null result | `EncodingException`, without its cause's message; **`ClassCastException`** for a short tuple |
| Mismatched function type | – | – | **`InvalidOperationException`** | – |
| Interrupt | `KeyboardInterrupt` | – | `ThreadInterruptedException` | **`ConnectionException` in `RPCException`, or `StreamException`** |
| Function compilation | `FunctionCompilationError` | – | `FunctionCompilationException` | – |
| Service definition problems | **`RuntimeError`**, and the public `UnknownTypeError` and `EnumerationValueError` | – | – | – |

Lua raises strings, which [Lua: error objects](#lua-error-objects) replaces. Its errors carry the
caller's source position in front, which about 30 expected failures list. C-nano returns error
codes, see [What C-nano does today](#what-c-nano-does-today).

## Phases

Each phase is one commit, with its conformance tests. E0 lands first, in a pull request of its
own off `main`. E1 to E5 land together with the work that makes the clients consistent in naming
and structure, in one pull request.

| Phase | Change |
| --- | --- |
| E0 | Type ids. The hash, the `Id` on each type attribute, the scanner's unique type names and its error for a shared or 0 id within a service. The ids in `GetServices` and `Type`, `KRPC.Error.service_id` and `exception_id` on every server error, `KRPC.Error.name` renamed `exception`, and the servicedefs JSON. The protocol and extending docs |
| E1 | Spec and testees. The categories, which situations raise which, the argument and encoding split, `StreamError` for every removal, the message rule, and no raw internal error. Tests narrowed from "encoding or argument" (`test_codec.py`, `test_values.py`), from "connection or argument" (`test_localsocket_path_too_long`), and from "a type of its own" in `test_mapped_exceptions`. A conventions section naming each client's `RemoteError` type, which the testees report in `native_types`; the Python testee reports kRPC types as well as builtins. Each testee classifies by the new types. The `TIMEOUT` kind goes, its number reserved. Clients that fail a narrowed test list it until their phase |
| E2 | Python and C++. `RemoteError` under `RuntimeError` and `std::runtime_error`. `RPCError` renamed `ServerError`, the base of every generated exception with no native type. `FunctionCompilationError` renamed `CompilationError`. C++ mapped exceptions raised as the native type, with an alias as the generated name; Python keeps its classes. `StreamRemovedException` translated to `StreamError`. Python's encoder raises the argument error for a wrong length, a negative unsigned value and a null key or element. Python's decoding leaks wrapped. Python's `StreamError` for a function with arguments becomes `ValueError`. Python's service definition errors as in the situations table. C++'s null function result as `EncodingError` |
| E3 | C# and Java. `RemoteException`, unchecked in Java, and `throws IOException` dropped. `RPCException` renamed `ServerException`, `FunctionCompilationException` renamed `CompilationException`, `StreamException` added in C#. The generated classes of mapped exceptions removed, except those with no native type; C#'s mapping moves to `lang/csharp.py`, for every service. C#'s "Stream has no value" and Java's connection endings and interrupts as above. The connection error during and after a call. Decoding errors as `EncodingException`, with their cause's message. C#'s mismatched function type and Java's null object id as the argument error |
| E4 | Lua. Error objects in place of strings, with no source position, and the `error-types` profile. Misuse stays a string in Lua's form |
| E5 | C-nano. The codes, the last-error record, the detail levels, `KRPC_FAIL`, `krpc_set_error_cause`, the `KRPC_EXCEPTION_` macros and `KRPC_IS_EXCEPTION`. The situations as tabled, the testee's mapping, the `error-types` profile, and a native test at the Codes level |

## Consequences

Each phase carries these for the clients it changes.

- **Changelog, all `**Breaking:**`.** The renames: `RPCError`/`RPCException` to `ServerError`/
  `ServerException`, `FunctionCompilationError`/`Exception` to `CompilationError`/`Exception`.
  Python's server exceptions and errors under new bases. C++ mapped exceptions becoming aliases.
  C# and Java generated classes of mapped exceptions removed. Java errors unchecked, and
  `throws IOException` dropped. Lua errors as objects. C-nano's renamed and merged codes, and
  its default level keeping the last error. Each change of the error a situation raises.
- **C-nano pages.** `doc/src/cnano.rst` (configuration, handling errors, the transport API and the
  code reference), `doc/src/client-design/cnano.rst` (errors and the spec mapping), and the
  examples `Errors.c` and `ConnectingCustom.c`. The C-nano row of `client-design.rst`.
- **Protocol and extending docs, for E0.** `communication-protocols/` for the new fields, and
  `extending/` for the type id rule, its `Id` and unique type names.
- **Client guides.** `doc/src/python.rst` (errors, server side functions, streams and the API
  reference), `doc/src/cpp.rst`, `doc/src/csharp.rst`, `doc/src/java.rst` and `doc/src/lua.rst`
  ("The error is a string").
- **Client design pages.** `doc/src/client-design/python.rst`, `java.rst` (interrupts, checked
  exceptions), `csharp.rst` and `lua.rst`, and the comparison table in `client-design.rst`.
- **Java doc examples.** About 60 files under `doc/src/scripts` declare or catch `RPCException`
  or `StreamException`, and the build compiles them.
- **clientgen and its goldens.** `python.tmpl`, `cpp.tmpl`, `csharp.tmpl`, `java.tmpl` and, for
  E5, `cnano.tmpl`, the `lang/*.py` tables, and the KRPC and TestService goldens.
- **docgen.** It ignores `mapped_type` today. Naming the raised type of each mapped exception is new
  work, and C# and Java need a reference target for an exception with no generated class.
- **Service tests.** `service/SpaceCenter/test/test_server_side_functions.py` asserts the type is
  exactly `RPCError`. The in-game framework catches broadly, and is unaffected.
- **Other design docs.** This doc supersedes the exception rulings of
  [client-codegen.md](client-codegen.md), including that the message prefix in Lua is every error,
  and leaves that record as it stands. [javascript-client.md](javascript-client.md) makes
  `instanceof RPCError` hold for every server error, and is updated to match before that client
  is built.

## Deviations

Where the build departs from the design above.

- **A read before the first value blocks.** On a thread holding the stream's condition too, a
  read waits on the condition, which lets it go, and returns once the first value arrives. Every
  client does this, and the spec tests it. `StreamError` with "Stream has no value" stays only for
  a read that races the first value, stored but not yet announced.
- **The testee's kinds.** `RPC` is renamed `SERVER`, and a new `INTERRUPT` kind reports the
  native interrupt. `TIMEOUT` goes, its number reserved, as planned.
- **The remote error test.** One test per category checks the base of the connection, server and
  encoding errors. The stream error has its own test under the `streams` profile, as Lua has no
  streams.
- **`StreamRemovedException` is translated where the exception is built,** not in each stream
  manager. Its generated name is an alias of `StreamError` in Python and C++. C# and Java register
  the stream exception for it, and Python's runtime builder of exception types returns
  `StreamError` for it.
- **C# registers a factory per exception.** `IConnection.AddExceptionType` takes a
  `Func<string, Exception>`, so a mapped exception needs no class. The argument exceptions take
  the parameter name first, which the factory passes as empty.
- **Reference docs.** docgen keeps an entry for each exception, as the target of references, and
  each entry says what the client raises for it: the builtin or `ServerError` base in Python, the
  alias or base in C++, the native type thrown in C# and Java, and a `ServerError` with its
  `service` and `name` in Lua.
- **Lua.** It has no `StreamError` class, as it has no streams. A server error names
  `Service.Name:` in its message when the service definitions leave the exception out, as the
  other clients do for an exception they have no type for. A local socket path too long is a
  string in Lua's form, from luasocket's own check.
- **Misuse.** Java throws `IllegalArgumentException` when `addStream` or `getCall` finds no method,
  and `IllegalStateException` when a stub's type information cannot be read. C# throws
  `ConnectionException` for a call after `Dispose`, in place of `ObjectDisposedException`.
- **Python service definitions.** A malformed set of definitions raises `ConnectionError` at
  connect, wrapping the error. `UnknownTypeError` and `EnumerationValueError` stay, as
  `ValueError` subclasses.
- **Java connection endings.** A stream or event that a close or a connection failure ends throws
  the connection's own `ConnectionException`, one instance for every stream.
- **C-nano takes `error-types` with no remote error type.** Its conventions set `remote_error` to
  `null`. The spec treats such a client as one whose errors are codes: `test_remote_error` skips
  it, a mapped exception is checked by its service and name, and the `Service.Name:` prefix
  stays on a server error's message, as for a client without error types.
- **C-nano's testee types.** It reports the `KRPC_EXCEPTION_` macro of a server error as its
  native type, and the code's name for every other error.
- **`KRPC_ERROR_CONNECTION_REFUSED` stays.** A program retries a garbled handshake on a serial
  line and gives up on a refusal, so the two take separate codes, at every detail level. A refusal
  is `DENIED`, `WRONG_PROTOCOL_VERSION`, or an unsupported protocol version in an `OK` response,
  and closes the connection. Any other status is `KRPC_ERROR_CONNECTION`, which leaves a resumable
  link open for a retry. The testee reports a refusal as the connection error.
- **A null address, path or port in a C-nano opener is `KRPC_ERROR_ARGUMENT`.** "No address" in
  the situations table is an address that does not resolve, which stays `KRPC_ERROR_CONNECTION`.
- **C-nano's sentences compile when the library prints errors,** as well as at Messages, so
  `KRPC_PRINT_ERRORS_TO_STDERR` prints them at every level.
- **A C-nano callback's code.** A nanopb callback returns only false, so it stores its code in
  `krpc_callback_error`. The function that ran nanopb returns it in place of
  `KRPC_ERROR_ENCODING`. This gives `KRPC_ERROR_ARGUMENT` for an unfilled argument and a null
  string, and `KRPC_ERROR_NO_MEMORY` for a result with no memory, which is skipped to the end of
  its message so the session survives.
- **No Uno measurement.** The guide states the 16 bytes of the record, from its layout. The flash
  of each level is not measured, as no AVR toolchain is set up.
- **The scripted serial line drains before it closes.** It stopped socat as its script ended,
  and the pty hangup discarded bytes the client had not read. C-nano, which reads a size prefix a
  byte at a time, lost a refusal or a disconnect now and then. The line now waits for the
  client's end to empty first.
