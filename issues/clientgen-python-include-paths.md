# clientgen: a Python `--include` given as a file path makes a wrong import

`krpc-clientgen python --include SERVICE=VALUE` names the module a generated module imports for another service's types. `VALUE` is a module name, or the path of a `.py` file, which clientgen turns into a module name by dropping `.py` and replacing `/` with `.`:

| `--include` value | Import written |
|---|---|
| `other_mod.other` | `other_mod.other` |
| `other_mod/other.py` | `other_mod.other` |
| `./other_mod/other.py` | `..other_mod.other`, a syntax error |
| `/home/me/project/other_mod/other.py` | `.home.me.project.other_mod.other`, a syntax error |
| `other_mod\other.py` on Windows | `other_mod\other`, a syntax error |
| `src/other_mod/other.py`, for a package rooted at `src` | `src.other_mod.other`, which fails to import |

clientgen accepts each of these without a warning. The generated module fails when it is imported.

The path form exists for the Bazel rule, which passes each dependency's output path, such as `krpc/ksp/spacecenter.py`. The C++ and C nano generators take a path there, and a user can follow the same pattern for Python.

Proposal:

 * `--include` for Python takes a dotted module name only, and clientgen rejects a value that is not a valid one, naming the expected form.
 * The Bazel rule passes the module name for Python, from the output path relative to the package root.
 * `extending/clientgen.rst` and the `--help` text say the Python value is a module name.

`--include` for Python is new in 0.8, so this changes no released behavior.
