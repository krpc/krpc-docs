# Allow XML documentation crefs to kRPC exceptions

A service's XML documentation cannot link to a kRPC exception. `<see cref="ObjectNotLoadedException"/>` fails the service definitions build with "Type 'ObjectNotLoadedException' is not a kRPC service, class, enumeration or structure". Docs that should name `ObjectDestroyedException` or `ObjectNotLoadedException` describe them in words instead.

The fix spans `DocumentationUtils.cs`, each language's docgen `see ()`, and the cnano `exception` macro.

Design: [doc-crefs-to-exceptions.md](https://github.com/krpc/krpc-docs/blob/main/design/build-tools/doc-crefs-to-exceptions.md)
