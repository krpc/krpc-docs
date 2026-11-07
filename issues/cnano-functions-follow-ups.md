# C-nano: follow-ups to server side functions

Reviews of #1267 turned up these items, left out of it to keep its scope. Paths are relative to `client/cnano/` unless they say otherwise.

## Client

* **Generate `krpc_compile_function` and `krpc_run_function`.** `include/krpc_cnano/functions.h` holds the ids of `KRPC.CompileFunction` and `KRPC.RunFunction`, copied by hand. `clientgen/cnano.py` adds `krpc_list_nullable_bytes_t` to the `KRPC` header with a special case for that service. Generating both functions from the service definitions would remove the copied ids and the special case. A renamed procedure or a changed signature would then fail to compile, where today only the conformance tests catch it. The design page, `doc/src/client-design/cnano.rst`, records the hand-written form as a decision.
* **`krpc_run_function` holds the value twice.** `krpc_decode_bytes` copies the value out of the result buffer before `krpc_free_result` frees it, so a value of N bytes needs about 2N bytes of heap. Handing the result buffer to the caller, or decoding from it in place, needs one copy.
* **A `_call` function makes 2 + N allocations.** `krpc_procedure_call` in `src/procedure_call.c` allocates the arguments header and its array separately, then one block per argument. One block for the header and the array saves an allocation, an error path and a free per call, which matters on a small heap.
* **No opt-out for the `_call` functions.** Each procedure in every service header has a `_call` function, about doubling the header text. A program without server side functions still parses them. A macro such as `KRPC_NO_PROCEDURE_CALLS` around them would make the cost opt-in. The design page records the cost as compile time and no code. [calls-a-function-cannot-make.md](calls-a-function-cannot-make.md) removes the `_call` functions that can never succeed, which covers the `KRPC` header.

## Documentation examples

The C examples skip error checks and leave decode targets uninitialized, by decision, as real code checks errors and the checks would make C verbose next to the other clients. The first two items may fall under the same decision.

* **Examples index a list without a length check.** `CollectionEvent.c`, `StructureField.c` and `TargetEvent.c` under `doc/src/scripts/user-guide/server-side-functions/` read `items[0]`, which dereferences `NULL` for an empty list. The C++ examples index the same way.
* **Examples leave call messages uninitialized.** `doc/src/scripts/cnano/RunFunction.c` and the server side functions examples declare `krpc_schema_ProcedureCall` without `krpc_schema_ProcedureCall_init_default`. Freeing a call that was never filled in is only defined from `init_default`, which the native tests and the testee use.
* **The first C tab comes before its note.** On `doc/src/user-guide/server-side-functions.rst`, the note that C-nano runs each function in place of an event or stream is in The Expression API section. The `NotLoadedEvent` tab comes earlier, in the section on errors, and only the script's own comment explains it.

## Conformance testee and driver

* **`call_<service>` repeats `invoke_<service>`.** In `tools/krpctools/krpctools/clientgen/cnano-dispatch.tmpl`, both repeat the member condition and the argument unpacking. A Jinja macro would keep the two in step.
* **`call_function` frees by hand on two paths.** `conformance/main.cpp` frees the call in a `catch (...)` and after the `try`. A small RAII guard would free it in one place.
* **The scripted server matches a call by id on its procedure alone.** `_is_service_call` in `client/conformance/driver/scripted.py` ignores the service of a call by id. As ids come from procedure names, a `TestService` procedure that shares a name with a `KRPC` procedure would get the canned `KRPC` value. Comparing the `service_id` with the id of `KRPC` removes the clash.
