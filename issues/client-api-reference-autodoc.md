# Generate the client API references from the client sources

Each client guide (`doc/src/<client>/client.rst`) ends with a reference to the client's own API:
`connect`, the client and stream classes, the error types. The reference is written by hand with
plain Sphinx directives, so nothing keeps it in step with the code. A review of the Python
reference found a class that does not exist (`krpc.client.KRPC`), and incomplete lists of the
errors two functions raise.

| Guide | Hand-written entries |
|---|---|
| C++ | 58 |
| Java | 50 |
| Python | 42 |
| C# | 39 |
| Lua | 7 |
| C-nano | 7 |

The service references are already generated, by `krpctools docgen` from the service definitions.
The client APIs need the same, from each client's own doc comments.

Generate each reference from the client's source:

* **Python:** `sphinx.ext.autodoc` over `krpc`, `krpc.client`, `krpc.stream`, `krpc.event`,
  `krpc.error` and `krpc.limits`. The docstrings exist, and need a pass to the doc style.
* **C#:** the XML doc comments of `client/csharp/src`. `sphinx_csharp` has no autodoc, so this
  needs a generator, such as one built into docgen.
* **C++:** Doxygen comments in `client/cpp/include/krpc`, through Breathe or a docgen backend.
* **Java:** the Javadoc of `client/java/src/krpc/client`, through `javasphinx` or its replacement.
* **Lua and C-nano:** the references are short. Generating them is optional.

Keep the guides' prose and examples hand-written. Only the reference sections move to generated
output. A check in `//doc:html` should fail when a public member has no doc comment, as
`//doc:check-documented` does for the services.
