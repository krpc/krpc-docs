# Lua: `platform.sleep` busy-waits, to whole seconds

`krpc.platform.sleep(s)` spins on `os.time()` until the time has passed:

```lua
function platform.sleep(s)
  local ntime = os.time() + s
  repeat until os.time() > ntime
end
```

This has two problems:

* **It holds a CPU core for the whole sleep.** It is a loop with no wait in it.
* **It sleeps for whole seconds.** `os.time()` counts whole seconds, and the loop runs until it passes the target. `sleep(1)` takes one to two seconds, and `sleep(0.1)` takes up to a second instead of a tenth.

The docs examples use it, including `platform.sleep(0.1)` in a loop in the launch example on the home page (`doc/src/scripts/index/Launch.lua`), and in the drawing, launch into orbit and InfernalRobotics examples.

The client already depends on luasocket, which has `socket.sleep(s)` with sub-second resolution and no busy-wait. Make `platform.sleep` call it, keeping the module so existing scripts work, or point the examples at `socket.sleep` and deprecate `krpc.platform`.
