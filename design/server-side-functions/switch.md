# Match and switch statements in server side functions

**Status:** in progress. `Match` and `Switch` are implemented as designed, in PR #1334, and the
JavaScript compiler compiles `switch` to `Switch`. They were first named `Switch` and
`SwitchWithFallThrough`, renamed before release as [Naming](#naming) explains. The Python
compiler compiles `match` on branch `python-match`, with the simple patterns only: literal, value,
`None`, `True`, `False`, or, wildcard, capture, `as` and guards. Sequence, mapping and class
patterns are a compile error, and wait for a later PR. A follow-up to server side functions, which merged in #1124 to #1130. Issue:
[switch-statements.md](../../issues/switch-statements.md). Needed by phase 6 of the
[JavaScript client](../javascript-client.md#phase-6-function-compiler), and lands before it.

The expression API has `IfThen`, `IfThenElse`, loops, `Break`, `Continue` and `Return`, and no
switch. A compiler can lower a switch to an `if` chain, but not every switch:

- **JavaScript, and the C, C++ and Java clients' languages,** fall through from one case into the
  next, and `break` exits the switch. The server's `Break` exits the enclosing loop, and has no
  form that exits a block.
- **Python's `match`** runs one case, and a `break` in it exits the enclosing loop.

The two need different nodes, as a node that binds `Break` to itself breaks Python's loops, and one
that does not leaves JavaScript no `break`.

## Design

Two factories with one shape:

```
Match(value, cases, bodies)
Switch(value, cases, bodies)
```

| Parameter | Type | Meaning |
| --- | --- | --- |
| `value` | `Expression` | Evaluated once |
| `cases` | `list<list<Expression>>` | The test values of each case. A case with none is the default, and there is at most one |
| `bodies` | `list<Expression>` | One statement per case. An empty `Block` is an empty body |

| | `Match` | `Switch` |
| --- | --- | --- |
| Runs | The matching case's body, or the default's | From the matching case's body on, through every later body |
| `Break` | Belongs to the enclosing loop | Exits the switch |
| `Continue` | Belongs to the enclosing loop | Belongs to the enclosing loop |
| Default position | Has no effect | Sets which bodies follow it |
| Used by | Python `match`, expression API users | JavaScript, expression API users in C, C++ and Java |

Shared rules:

- **Matching.** Test values compare with `value` by the rules of `Equal`, in order, and each is
  evaluated only when the earlier ones have not matched. The first match wins, so a repeated test
  value is allowed. A test value of an unrelated type is a `KRPC.ArgumentException` when the node
  is built, as for `Equal`. With no match and no default, no body runs.
- **Nulls.** A null `value` matches a null test value, as `Equal` does.
- **Statements only.** Both are statements with no value, as `IfThenElse` with statement branches.
  A switch with a value, like C#'s switch expression, has no compiler to emit it.
- **Errors.** `cases` and `bodies` of different lengths, or two defaults, are an
  `ArgumentException`.
- **`Return`** in a body belongs to the enclosing function, as in any statement.

## Implementation

Both lower to nodes the server already builds, so the checker, the node limit and the tree printer
need no new node kinds:

- **`Match`** holds `value` in a block variable, and builds an `IfThenElse` chain of the cases in
  order, with the default as the last `else`.
- **`Switch`** builds one `Block`: a variable for `value`, then a dispatch chain of
  conditions that each `Goto` a case's label, ending in a `Goto` to the default's label or the end
  label. Then each case's label and body, in order, and the end label. Each `Goto` targets a label
  of the same block. The `MarkerRewriter` binds the bodies' `Break` markers to the end label, with
  no continue target, so `Continue` passes to the enclosing loop.
- **Checker message.** A `Break` outside any loop or `Switch` says "A break statement must be
  inside a loop or a switch". A `Break` in a `Match` with no loop around it is still unbound.

## Clients

| Client | Uses |
| --- | --- |
| JavaScript | Phase 6b compiles `switch` to `Switch`, with JavaScript's full semantics. A case of a type the value does not compare with is a compile error |
| Python | Compiles `match`, below. Sequence, mapping and class patterns are not done yet |
| C# | No change. Its compiler emits no statements, see [csharp-statement-functions.md](csharp-statement-functions.md) |
| C++, C-nano, Java, Lua | The generated factories, with no client change |

### Python `match`

Python 3.10 is the client's minimum, so `match` is always available. A run of unguarded cases is
one `Match`. A guarded case is an `IfThenElse` whose condition assigns the bindings, then tests
the guard. The rows below for sequence, mapping and class patterns are not implemented yet. Only some patterns map onto
`Match`. The rest lower to an `if` chain over nodes the server has:

| Pattern | Lowers to |
| --- | --- |
| Literal, value (`SASMode.prograde`), or-pattern | `Match` test values |
| Wildcard `_` | `Match` default |
| Capture `x` | The default, with an `Assign` |
| Guard (`case x if x > 0`) | A condition in the `if` chain |
| Sequence (`[a, b, *rest]`) | `Count`, `Get`, `Skip` |
| Mapping (`{"k": v}`) | `ContainsKey`, `Get` |
| Class (`BoundingBox(min=m)`) | Field reads. A remote class's static type decides the match when compiling |
| `as` | An `Assign` |

The first matching case wins, so a run of simple cases is one `Match` whose default holds the
chain of the cases after it.

Python compares more loosely than `Match`, which rejects a test value of an unrelated type when
the node is built:

| Python | Compiles to |
| --- | --- |
| A literal of a type the subject does not compare with, such as `case "a":` on an `int` | A compile error, as in JavaScript. Python would never match it |
| `case 1:` on a `bool`, or `case True:` on an `int` | A compile error, as `Equal` rejects `bool` against `int`. Python matches it, as `True == 1` |
| `case None` | A test value of `ConstantNull`, on a nullable subject. A compile error otherwise |
| `case True`, `case False` | A test value on a `bool` subject. A compile error otherwise, where Python's `is` would never match |

A class pattern naming a subclass would need a run-time type test, which waits for class
inheritance ([#905](https://github.com/krpc/krpc/issues/905)).

## Testing and docs

- **Core tests** for each rule above: matching order and laziness, fall-through, `Break` in each
  form, `Continue` and `Return` from a body, a nested loop's `Break` inside a case, nulls, the
  default in every position, and the build errors.
- **Golden trees** in `ExpressionTreePrinterTest` for both forms.
- **Docs.** XML docs on both factories. A *Match and Switch Statements* section in the expression
  API half of the server side functions guide, after *Statements, Variables and Loops*, with an example per
  client that has the expression API.
- **Changelog**, under `core`.
- No conformance tests: the factories are server behavior, which every client calls through its
  generated stubs.

## PRs

1. Server: both factories, tests, docs.
2. Python `match`, independent of JavaScript.
3. JavaScript phase 6b, which compiles `switch`.

## Naming

The two differ in where `Break` goes, and the names follow the languages:

| Languages | Construct | `break` in a case ends | Compiles to |
| --- | --- | --- | --- |
| C, C++, Java, JavaScript | `switch`, falling through | The switch | `Switch` |
| C#, Go, Swift, Java's arrow form | `switch`, not falling through | The switch | `Switch`, with a `Break` closing each case |
| Python, Rust, Kotlin's `when` | `match` | The enclosing loop | `Match` |
| Haskell, OCaml, F#, Scala | `case`, `match` expressions | No `break` | Not covered: these yield a value and match patterns |

Every `switch` keyword binds `break` to the switch, so the fall-through node takes the name. `Match`
names the first-match form after Python's keyword. A value-yielding form for the functional
languages would be a later addition, such as an overload of `Match`.

## Ruled out

- **One factory with a `fallThrough` flag.** A flag that changes what `Break` means reads worse
  than two names, as `Block` and `BlockWithVariables` are two.
- **A case node**, `Case(values, body)`, passed to `Match` in a list. It reads like LINQ's
  `SwitchCase`, but adds an `Expression` that is invalid anywhere else, which the checker must
  reject.
- **LINQ's `SwitchExpression`.** It needs test values of the switch value's exact type and a
  comparison method, has no fall-through, and the printer does not render it. The `if` chain gives
  `Equal`'s widening and value comparison for free. A jump table matters little for a handful of
  cases.
- **Lowering in each client only.** Fall-through, and a `break` inside a case, need a flag per
  case and per `break`, and a `continue` routed through them.
