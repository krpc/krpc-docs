# Raster Prop Monitor service

**Status:** proposal. Issues [#375](https://github.com/krpc/krpc/issues/375) (RPM integration) and
[#424](https://github.com/krpc/krpc/issues/424) (camera views), from the
[mod integrations index](../../issues/mod-integrations-index.md).

## Goals

* A script drives the IVA displays: values that props show, the pages of the MFDs, and pages of
  its own.
* The IVA feeds the script: values, switch positions and button presses, as streams and events.
* A script reads what a display shows, and the camera views, as images (#424).

## Context

RPM (1.1.0.1, assembly `RasterPropMonitor`, namespace `JSI`, maintained at
FirstPersonKSP/RasterPropMonitor) builds IVAs from props. The pieces kRPC can reach:

| RPM member | Gives | Access |
| --- | --- | --- |
| `RasterPropMonitorComputer` | Part module on each RPM part. Owns the part's variables and per-part persistent variables | Public class |
| `RPMVesselComputer` | Vessel module. Vessel data and the vessel-global persistent variables | Public class |
| `Get/Set/HasPersistentVariable (name, value, global)` | Named doubles, saved with the part. `PERSISTENT_<name>` reads the part's value, else the vessel's | Internal |
| `InstantiateVariableOrNumber (name)` | Any RPM variable by name: `ALTITUDE`, `CUSTOM_`, `MATH_`, `PLUGIN_` and mod variables. `VariableOrNumber.Update`, `AsDouble`, `Get` | Public |
| `JSIActionGroupSwitch` with `actionName = dummy`, `perPodPersistenceName` | A switch that toggles a persistent variable. `momentarySwitch` sets it on press and clears it on release, `switchGroupIdentifier` makes radio groups | Prop config |
| `JSINumericInput` | Writes a number into a persistent variable | Prop config |
| `RasterPropMonitor` | Internal module of an MFD prop. Pages, `globalButtons`, private `screenTexture` | Public class |
| `RasterPropMonitor.GlobalButtonClick/Release (id)`, `PageButtonClick (page)` | Presses an MFD button, switches page. The active page is the persistent variable `activePage<propID>` | Public |
| `MonitorPage.ProcessedText` | The text of a page, after variable substitution | Public |
| `PAGEHANDLER`, `BACKGROUNDHANDLER` | Page config naming a module and methods by name. RPM instantiates the module with `internalProp.AddModule` and binds `string (int, int)`, `bool (RenderTexture, float)`, `void (int)` button and `void (bool, int)` activation methods | Prop config |
| `IJSIModule` | Plugin methods for `PLUGIN_` variables and `PLUGINACTION` switches | Needs a compile-time subclass |
| `JSIExternalCameraSelector`, `FlyingCamera (part, aspect)`, `PointCamera (name, fov)`, `Render (texture, yaw, pitch)` | Camera parts (`ExtCam1`, ...) and the renderer the MFD camera pages use | Public |

Two constraints shape the design:

* **RPM renders only for the player's pod.** `RasterPropMonitorShouldUpdate` is true only on the
  active vessel, while the player is in that pod's IVA or the IVA overlay is on. Monitor text,
  screen images and per-part variable updates stop otherwise. The vessel computer updates on the
  active vessel in every camera mode.
* **Internal models exist only on the active vessel.** Monitors are props inside
  `part.internalModel`, so the monitor API works on the active vessel only. Persistent variables
  live on the part module and work on any loaded vessel.

## Decisions

* **Service `RasterPropMonitor`**, in `service/RasterPropMonitor/`, gives `raster_prop_monitor`.
  `Available` reports whether RPM is installed and its members bound.
* **Binding by reflection** with `Accessor`, as every mod service. The service never references
  RPM at compile time.
* **No `IJSIModule`.** A subclass would need RPM at compile time. The page handler below and the
  persistent variables cover what plugin methods would give.
* **Persistent variables are the data channel**, both ways. A script sets one and props show it
  through `PERSISTENT_<name>`. A switch or numeric input sets one and the script streams it. Stock
  RPM switches do this already, so an IVA needs no kRPC config. Values are doubles, as in RPM.
* **Switch presses are changes of a persistent variable.** `PersistentVariableChanged (name)` is a
  polled event that fires on each change. A momentary switch fires twice, on press and release,
  because RPM sets and clears it frames apart.
* **Events carry no value**, as all kRPC events. A button event is one event per button id, so
  the id is the event. A script that wants each new value of a variable streams it, with a
  callback. [events-with-values](../../issues/events-with-values.md) proposes typed events.
* **The script's own page is a page handler module in the service DLL.** `KRPCDisplay` derives
  from KSP's `InternalModule`, so RPM instantiates it from page config by name. A page names a
  display with `display = <name>`. Each monitor page showing that name shows the same content:

  ```
  PAGE
  {
      name = krpc
      button = buttonR8
      PAGEHANDLER
      {
          name = KRPCDisplay
          method = Text
          buttonClickMethod = ButtonClick
          buttonReleaseMethod = ButtonRelease
          pageActiveMethod = PageActive
          display = main
      }
      BACKGROUNDHANDLER
      {
          name = KRPCDisplay
          method = RenderBackground
          display = main
      }
  }
  ```

* **Display text is RPM page text.** RPM runs a handler's text through its formatter, so the
  script can embed variables (`{0:F0}$&$ALTITUDE`) and color tags, and RPM updates them each text
  refresh without a call from the script.
* **Display image is a PNG**, decoded once into a texture and drawn as the page background,
  scaled to the screen. Text draws over it.
* **Display buttons are the page's button ids**, after RPM's per-page redirects. A page handler
  receives the presses of its page only.
* **kRPC ships an optional Module Manager patch** that adds a `krpc` page, display `main` and no
  button, to every prop with a `RasterPropMonitor` module, `:NEEDS[RasterPropMonitor]`. The
  script reaches it through `Monitor.ActivePage`. Its buttons go to the display. RPM's bundled
  MFD config is documented as removable, so the patch matches the module and no prop name. The
  patch goes in its own file so a player can delete it.
* **A script presses the monitor's buttons as the player does.** `PressButton` calls `GlobalButtonClick` then
  `GlobalButtonRelease` on the next frame. `ActivePage` sets through `PageButtonClick`, which
  keeps RPM's locking and redirect rules. A script can drive any existing page, such as the
  MechJeb or SCANsat pages, this way.
* **Monitor readback needs the IVA.** `Monitor.Text` and `Monitor.Image` throw an exception unless
  RPM is updating that monitor. A stale frame would read as a valid one.
* **Cameras render through RPM's own `FlyingCamera`**, with a texture kRPC owns. This works in any
  camera mode, which the monitor readback does not, and matches the MFD camera pages. The
  DockingCamera service's `Camera.Image` is the model.
* **`Variable (name)` reads any RPM variable.** It instantiates the variable on the part's
  computer, calls `Update`, and returns the value. Numeric only in phase 1. It covers what kRPC
  lacks, such as `CUSTOM_` and `MATH_` variables from IVA packs and RPM's own mod bridges. Values
  that depend on the vessel computer need the active vessel.

## API

Persistent variables and RPM variables:

| Member | Kind |
| --- | --- |
| `Available` | Property |
| `Computer (part)`, `Computers (vessel)` | `Computer`: `Part` |
| `Computer.PersistentVariable (name)` | Procedure, nullable double: the part's value, else the vessel's, as `PERSISTENT_<name>` |
| `Computer.SetPersistentVariable (name, value)`, `RemovePersistentVariable (name)` | Procedures. Set fires RPM's update of the variable |
| `Computer.PersistentVariableChanged (name)` | Event |
| `GlobalPersistentVariable (vessel, name)`, `SetGlobalPersistentVariable`, `GlobalPersistentVariableChanged` | The vessel-global equivalents |
| `Computer.Variable (name)` | Procedure, double. Throws an exception for an unknown or non-numeric variable |

Monitors and displays, active vessel only:

| Member | Kind |
| --- | --- |
| `Monitors (vessel)` | List of `Monitor` |
| `Monitor` | `Part`, `PropName`, `Pages` (names), `ActivePage` (get, set), `Buttons` (global button names, by id), `PressButton (id)`, `ScreenWidth`, `ScreenHeight` (characters), `Text`, `Image` (PNG) |
| `Display (vessel, name)` | `Display`: `Name`, `Text` (get, set), `Image` (set, PNG, null clears), `Clear ()`, `Shown` (whether a monitor shows it now) |
| `Display.ButtonPressed (id)`, `ButtonReleased (id)` | Events |

Cameras:

| Member | Kind |
| --- | --- |
| `Cameras (vessel)` | List of `ExternalCamera` |
| `ExternalCamera` | `Part`, `Name` (`ExtCam1`, ...), `FieldOfView` (get, set), `Image (width, height)` (PNG) |

The display's text and image are held by the service per vessel and name. They outlive the IVA,
so a script can set them before the player enters the pod. They are not saved with the game.

## Phases

Each phase is a pull request with its own in-game tests.

| Phase | Adds | Needs in game |
| --- | --- | --- |
| 1 | Service skeleton, `Available`, `Computer`, persistent variables and their events, `Variable` | A pod with an RPM IVA. Tests set variables and read them back through `PERSISTENT_` on a prop |
| 2 | `Monitor`: pages, `ActivePage`, `PressButton`, `Text`, `Image` | The IVA camera mode, through `SpaceCenter.Camera` |
| 3 | `KRPCDisplay`, `Display`, button events, the optional Module Manager patch | Phase 2, plus a test that presses a display button with `PressButton` |
| 4 | `ExternalCamera` (#424) | A part with `JSIExternalCameraSelector`. Works outside the IVA |

Phase 3 depends on phase 2 for its tests. Phase 4 is independent of 2 and 3. The test mod pin
needs RPM and Module Manager, and the full RPM package so the stock pods have RPM IVAs.

## Open Questions

* String variables, such as `TARGETNAME`. `VariableOrNumber.Get` returns an object. Phase 1
  could add `VariableString (name)` if the need is real.
* Whether `Monitor.Text` is useful beyond tests. It gives the raw text with RPM's color tags.
* Player presses on pages kRPC does not own. RPM binds global buttons to the page's handler, so
  kRPC sees them only by wrapping the `SmarterButton` callbacks. Not planned.

## Considered and Not Planned

| Option | Reason |
| --- | --- |
| A kRPC `IJSIModule` for `PLUGIN_` variables and `PLUGINACTION` switches | Needs RPM at compile time. Persistent variables give the same channel |
| A `KRPCSwitch` prop module for button events | Switches on persistent variables already give events, with no kRPC config in the IVA |
| Streaming monitor images at frame rate | A PNG per call is enough for a browser view. A video transport is a separate protocol feature |
