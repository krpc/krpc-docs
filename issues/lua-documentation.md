# Lua: documentation for the dynamically built services

The Lua client builds its service classes at runtime from `GetServices`, but drops the documentation the definitions carry. The Python client turns it into docstrings, rendering `<math>` and `<unit>` markup as Unicode text with `krpc.docmath.to_text` (#1169).

Give the Lua classes and members their documentation, for interactive help. The options for the markup:

* Port `to_text` to Lua, about 150 lines plus the superscript and subscript tables. The strict checks are unneeded, because docgen rejects invalid markup at build time.
* Strip the tags and show the markup source, such as `m/s^2`.
* Render the text on the server, in a plain-text form of each doc in the service definitions. Every dynamic client could use it unchanged, at the cost of a C# port of `to_text` and a larger `GetServices` response.

Stripping the tags is enough for Lua alone. Rendering on the server pays off once a second dynamic client needs it.
