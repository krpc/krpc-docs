# Run clang-format and clang-tidy over every C and C++ source

clang-tidy checks only the library sources of the C++ and C-nano clients (`src/`). clang-format covers more, and some C and C++ sources are checked by neither:

| Sources | clang-format | clang-tidy |
| --- | --- | --- |
| `client/cpp/src`, `client/cnano/src` | yes | yes |
| `include/`, the headers | yes | only through the sources that include them |
| `test/` in both clients, `cnano/benchmark` | yes | no |
| `conformance/`, the conformance testees | yes | no |
| `cpp/benchmark`, `test-consumer/` in both clients | no | no |
| `doc/src/scripts`, the C and C++ doc examples | no | no |

Add clang-format and clang-tidy targets for the remaining sources, and fix what they report. Their deps differ from the library's, so most need a target of their own. The C-nano testee is C++ calling the C API, and the C++ testee links the full protobuf runtime and the generated testee messages. The C-nano target compiles with `-std=c99`, so it cannot check them.

Related to #1123.
