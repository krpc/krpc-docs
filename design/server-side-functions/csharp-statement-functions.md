# Compiling C# functions with statements

**Status:** proposal, postponed. A follow-up to server side functions, to be built once that stack
merges. No GitHub issue filed yet.

The C# client compiles only single-expression lambdas. Python compiles whole functions, with
statements, loops and exception handlers. This doc records the options for closing that gap. It is a
sketch, not a design yet.

## The problem

The C# compiler turns a lambda into an `Expression<Func<T>>` tree only when its body is a single
expression. A statement body is error CS0834, and assignments and `throw` are rejected in the tree
as well. `System.Linq.Expressions` can represent blocks, loops and try/catch, but the C# language
does not produce them from a lambda.

| Construct | Python client | C# client |
|---|---|---|
| Single expression | compiled | compiled |
| Statements, local variables, loops | compiled | expression API only |
| Raising and handling exceptions | compiled | expression API only |

Nothing on the server blocks this. The expression API already has every node a full function
needs, and the Python compiler uses all of them. The gap is in the client: it has no view of a
statement lambda's structure at runtime. Python has one because it reads a function's source and
parses it.

## Options

| | Source text at runtime | Source generator | IL decompilation |
|---|---|---|---|
| Mechanism | `[CallerArgumentExpression]` hands `Run` the lambda's source; Roslyn parses it; captured values come from `f.Target` | A Roslyn generator or interceptor rewrites the call site at build time into tree-building code | Read the delegate's IL and rebuild its control flow, as DelegateDecompiler does |
| Type information | none from the parse; resolve by reflection | full semantic model | from the IL |
| Unsupported construct | runtime error | compile-time error | runtime error |
| Cost | large Roslyn dependency in the client | users add the generator package; interceptors depend on the SDK version | fragile across compiler versions and optimization levels |
| Fails on | callers below C# 10 | builds without the generator | AOT builds such as IL2CPP, which have no IL |

The runtime-source and IL options can both produce a `System.Linq.Expressions` tree with blocks
and loops. The existing `FunctionCompiler` walks that type of tree, so most of it carries over. The
generator gives the best user experience, as errors surface in the IDE.

## Open questions

- Which option, or whether a generator with a runtime fallback is worth the two code paths.
- How captured variables are named and fetched in each option.
- Whether the C# construct list should match Python's, or the subset C# programs reach for.

## Related

- [`server-side-functions.md`](server-side-functions.md) records the single-expression limit of
  the current compiler.
