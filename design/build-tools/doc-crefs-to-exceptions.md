# Allow XML doc crefs to exceptions

**Status:** done in PR [#1185](https://github.com/krpc/krpc/pull/1185). Issue
[#1183](https://github.com/krpc/krpc/issues/1183). The PR grew into a general pass over the
client API docs: crefs link in the generated code of every client, and Doxygen, javadoc and
Sphinx check each client's docs in its test suite.

Where the implementation differs from the proposal:

* A cref to a .NET exception that a kRPC exception maps, such as
  `System.InvalidOperationException`, resolves to the kRPC exception. Service code throws the
  .NET type, so its docs can name the type they throw.
* C-nano renders a cref to an exception as the literal full name, e.g. `KRPC.Error`.
* docgen has no `<seealso>`, so the two object exceptions cross-reference each other in a
  `<remarks>` sentence.
* Also linked: the `Stage` remarks, and `Antenna.Deployed` and `Leg.Deployed`, as Camera.
  `doc/src/extending.rst` documents crefs, with an example.
* The core changelog has an entry, as service authors can now link exceptions.

A service's XML documentation cannot link to a kRPC exception. Writing
`<see cref="ObjectNotLoadedException"/>` fails the service definitions build:

```
DocumentationException: Documentation error: Type 'ObjectNotLoadedException' is not a kRPC service, class, enumeration or structure
```

Docs that should name an exception have to describe it in words. The two types closest to the
user, `ObjectDestroyedException` and `ObjectNotLoadedException`, are the ones the docs need to
name most often.

## Where it fails

| Layer | File | Gap |
| --- | --- | --- |
| Scanner | `core/src/Service/DocumentationUtils.cs` | `FindType` matches types with the service, class, enum and struct attributes only. `FormatTypeCref` has no `KRPCException` branch, and raises the error above |
| Docgen lookup | `tools/krpctools/krpctools/docgen/utils.py` | `lookup_cref` already includes `service.exceptions`. Nothing needed |
| Docgen per language | `python.py`, `lua.py`, `cpp.py`, `csharp.py`, `java.py`, `cnano.py` in `tools/krpctools/krpctools/docgen/` | each `see ()` has no `Exception` case, and raises `RuntimeError` |
| C-nano template | `cnano.tmpl`, `exception` macro | renders "Exception class X" as plain text, with no target to link to |

## Proposal

* **Scanner.** Add `KRPCExceptionAttribute` to the `FindType` filter, and a branch to
  `FormatTypeCref` that calls `TypeUtils.ValidateKRPCException` and returns
  `"T:" + TypeUtils.GetExceptionServiceName (type) + "." + name`. Exception nodes in docgen already
  carry that cref (`nodes.py`).
* **Docgen.** Add an `Exception` case to each language's `see ()`. It uses the role the
  template declares: `class` in Python, Lua, C# and C++, and `type` in Java. Check what `ref ()`
  gives for an exception in each language.
* **C-nano.** Give the `exception` macro a target, or render a cref to an exception as a literal
  name.
* **Tests.** In `core/test/Service/DocumentationUtilsTest.cs`, a cref to an exception resolves
  to `T:Service.Name`. In the krpctools docgen tests, add a golden for a member whose
  documentation links to an exception, for each language.

## Where to use it

Once crefs to exceptions work, link from these docs:

| Doc | Now | With a cref |
| --- | --- | --- |
| `KRPC.cs`, `AddFunctionStream` and `AddEvent` remarks | "including one for an object that is not loaded" | link `ObjectNotLoadedException` |
| `ObjectDestroyedException.cs` and `ObjectNotLoadedException.cs` summaries | none | a `<seealso>` to each other |
| `Expression.Exceptions.cs`, `Throw` | "raises the named exception" | an example cref, e.g. to `Error` |
| `service/SpaceCenter/src/Services/Camera.cs`, three map mode members | "Returns an error is the camera is not in map mode." | the type it throws, plus the typo fix (`is` for `if`) |

Leave the "Throws an exception if ..." formula in the 26 files that use it alone. It is the
house style, and naming the type at every site is a separate decision.

## Changelog impact

None for the scanner and docgen, as internal. The doc changes are wording only.
