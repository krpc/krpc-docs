# Client errors

**Status:** proposal, every question settled on 2026-11-10, and reviewed against the code. Issue:
[client-errors.md](../issues/client-errors.md).

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
| C-nano | none | Error codes, unchanged, see below |

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

### C-nano: no change

C-nano returns a distinct `krpc_error_t` per category already: the connection codes,
`KRPC_ERROR_RPC_FAILED` and the encoding and decoding codes. `KRPC_ERROR_BUFFER_TOO_SMALL` and
`KRPC_ERROR_NO_RESULTS` report the program's use of the API, and stay. It has no streams, so it
needs no stream error. Streams in C-nano would add a stream code, which is additive.

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
codes, which stay.

## Phases

Each phase is one commit, with its conformance tests. The phases land together with the work
that makes the clients consistent in naming and structure, in one pull request.

| Phase | Change |
| --- | --- |
| E1 | Spec and testees. The categories, which situations raise which, the argument and encoding split, `StreamError` for every removal, the message rule, and no raw internal error. Tests narrowed from "encoding or argument" (`test_codec.py`, `test_values.py`), from "connection or argument" (`test_localsocket_path_too_long`), and from "a type of its own" in `test_mapped_exceptions`. A conventions section naming each client's `RemoteError` type, which the testees report in `native_types`; the Python testee reports kRPC types as well as builtins. Each testee classifies by the new types. The `TIMEOUT` kind goes, its number reserved. Clients that fail a narrowed test list it until their phase |
| E2 | Python and C++. `RemoteError` under `RuntimeError` and `std::runtime_error`. `RPCError` renamed `ServerError`, the base of every generated exception with no native type. `FunctionCompilationError` renamed `CompilationError`. C++ mapped exceptions raised as the native type, with an alias as the generated name; Python keeps its classes. `StreamRemovedException` translated to `StreamError`. Python's encoder raises the argument error for a wrong length, a negative unsigned value and a null key or element. Python's decoding leaks wrapped. Python's `StreamError` for a function with arguments becomes `ValueError`. Python's service definition errors as in the situations table. C++'s null function result as `EncodingError` |
| E3 | C# and Java. `RemoteException`, unchecked in Java, and `throws IOException` dropped. `RPCException` renamed `ServerException`, `FunctionCompilationException` renamed `CompilationException`, `StreamException` added in C#. The generated classes of mapped exceptions removed, except those with no native type; C#'s mapping moves to `lang/csharp.py`, for every service. C#'s "Stream has no value" and Java's connection endings and interrupts as above. The connection error during and after a call. Decoding errors as `EncodingException`, with their cause's message. C#'s mismatched function type and Java's null object id as the argument error |
| E4 | Lua. Error objects in place of strings, with no source position, and the `error-types` profile. Misuse stays a string in Lua's form |

## Consequences

Each phase carries these for the clients it changes.

- **Changelog, all `**Breaking:**`.** The renames: `RPCError`/`RPCException` to `ServerError`/
  `ServerException`, `FunctionCompilationError`/`Exception` to `CompilationError`/`Exception`.
  Python's server exceptions and errors under new bases. C++ mapped exceptions becoming aliases.
  C# and Java generated classes of mapped exceptions removed. Java errors unchecked, and
  `throws IOException` dropped. Lua errors as objects. Each change of the error a situation raises.
- **Client guides.** `doc/src/python.rst` (errors, server side functions, streams and the API
  reference), `doc/src/cpp.rst`, `doc/src/csharp.rst`, `doc/src/java.rst` and `doc/src/lua.rst`
  ("The error is a string").
- **Client design pages.** `doc/src/client-design/python.rst`, `java.rst` (interrupts, checked
  exceptions), `csharp.rst` and `lua.rst`, and the comparison table in `client-design.rst`.
- **Java doc examples.** About 60 files under `doc/src/scripts` declare or catch `RPCException`
  or `StreamException`, and the build compiles them.
- **clientgen and its goldens.** `python.tmpl`, `cpp.tmpl`, `csharp.tmpl` and `java.tmpl`, the
  `lang/*.py` tables, and the KRPC and TestService goldens.
- **docgen.** It ignores `mapped_type` today. Naming the raised type of each mapped exception is new
  work, and C# and Java need a reference target for an exception with no generated class.
- **Service tests.** `service/SpaceCenter/test/test_server_side_functions.py` asserts the type is
  exactly `RPCError`. The in-game framework catches broadly, and is unaffected.
- **Other design docs.** This doc supersedes the exception rulings of
  [client-codegen.md](client-codegen.md), including that the message prefix in Lua is every error,
  and leaves that record as it stands. [javascript-client.md](javascript-client.md) makes
  `instanceof RPCError` hold for every server error, and is updated to match before that client
  is built.
