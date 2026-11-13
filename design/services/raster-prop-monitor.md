# Raster Prop Monitor service

**Status:** implemented on branch `raster-prop-monitor`, unmerged. Issues [#375](https://github.com/krpc/krpc/issues/375) (RPM integration) and
[#424](https://github.com/krpc/krpc/issues/424) (camera views), from the
[mod integrations index](../../issues/mod-integrations-index.md).

## Goals

* A script drives the IVA displays: values that props show, the pages of the MFDs, and pages of
  its own.
* The IVA feeds the script: values, switch positions and button presses, as streams and events.
* A script reads what a display shows as images, and the camera views as images or video (#424).

## Context

RPM (1.1.0.1, assembly `RasterPropMonitor`, namespace `JSI`, maintained at
FirstPersonKSP/RasterPropMonitor) builds IVAs from props. The pieces kRPC can reach:

| RPM member | Gives | Access |
| --- | --- | --- |
| `RasterPropMonitorComputer` | Part module on each RPM part. Owns the part's variables and per-part persistent variables | Public class |
| `RPMVesselComputer` | Vessel module. Vessel data and the vessel-global persistent variables | Public class |
| `Get/Set/HasPersistentVariable (name, value, global)` | Named doubles, saved with the part. `PERSISTENT_<name>` reads the part's value, else the vessel's | Internal |
| `InstantiateVariableOrNumber (name)` | Any RPM variable by name: `ALTITUDE`, `CUSTOM_`, `MATH_`, `PLUGIN_` and mod variables. `VariableOrNumber.Update`, `Get`: a string, or a number boxed as any numeric type or `bool` | Public |
| `JSIActionGroupSwitch` with `actionName = dummy`, `perPodPersistenceName` | A switch that toggles a persistent variable. `momentarySwitch` sets it on press and clears it on release, `switchGroupIdentifier` makes radio groups | Prop config |
| `JSINumericInput` | Writes a number into a persistent variable | Prop config |
| `RasterPropMonitor` | Internal module of an MFD prop. Pages, `globalButtons`, private `screenTexture` | Public class |
| `RasterPropMonitor.GlobalButtonClick/Release (id)`, `PageButtonClick (page)` | Presses an MFD button, switches page. The active page is the persistent variable `activePage<propID>` | Public |
| `MonitorPage.ProcessedText` | The text of a page, after variable substitution, with RPM's markup | Public |
| `MonitorPage.text`, `textOverlay`, `screenXMin`, `screenYMin`, `defaultColor` | The page's source text before formatting, its text overlay, its margins and its default color | Private and public fields |
| `MonitorPage.pageHandlerModule`, `backgroundHandlerModule` | The handler modules RPM created for the page | Private |
| `TextRenderer.fontCharacters` | The characters the monitor's fonts can draw | Private |
| `JUtil.RasterPropMonitorShouldUpdate (part)` | Whether RPM draws the part's monitors now | Public |
| `RasterPropMonitorComputer.UpdateVariables`, `RasterPropMonitor.FillScreenBuffer`, `RenderScreen`, `rpmComp` | The steps of RPM's update of a monitor, and the monitor's computer | Private |
| `PAGEHANDLER`, `BACKGROUNDHANDLER` | Page config naming a module and methods by name. RPM instantiates the module with `internalProp.AddModule` and binds `string (int, int)`, `bool (RenderTexture, float)`, `void (int)` button and `void (bool, int)` activation methods | Prop config |
| `IJSIModule` | Plugin methods for `PLUGIN_` variables and `PLUGINACTION` switches | Needs a compile-time subclass |
| `SmarterButton.pageTriggers`, `clickHandlers`, `PageTriggerSet.selector`, `OnMouseDown`, `OnMouseUp` | A button's page triggers per monitor, its other click handlers, and the click itself | Private, except the mouse methods |
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
  polled event that fires when the value differs from the last update's. A momentary switch fires
  twice, on press and release, because RPM sets and clears it frames apart. A change that is
  undone within one server update does not fire.
* **Events carry no value**, as all kRPC events. A button event is one event per button id, so
  the id is the event. A script that wants each new value of a variable streams it, with a
  callback. [events-with-values](../../issues/events-with-values.md) proposes typed events.
* **The script takes over an existing screen, and does not create one.** A screen is a prop the
  IVA's author placed: a model, a screen surface and button transforms. KSP rebuilds the IVA from
  the part's config on each vessel switch and IVA entry, so a prop added at run time would not
  last.
* **The script's own page is a page handler module in the service DLL.** `KRPCDisplay` derives
  from KSP's `InternalModule`, so RPM instantiates it from page config by name. The script acts
  as the computer behind the page: it sets the text and the background, and answers the button
  presses.
* **Each monitor has its own display.** A page whose handlers have no `display` value binds to
  its own monitor, and the script reaches it as `Monitor.Display`. Presses on it come from that
  screen only. Handlers with `display = <name>` bind to a named display instead, shared by every
  page that names it, for an IVA author who wants several screens to show one display. The value
  goes in both handler nodes, as RPM passes each handler its own node only. RPM creates one
  module per handler node, and the module finds its monitor through the pages'
  `pageHandlerModule` and `backgroundHandlerModule`. A page config for a named display, with a
  button to select it. Without the two `display` lines, the page shows its monitor's own display:

  ```
  PAGE
  {
      name = krpc
      button = buttonR8
      PAGEHANDLER
      {
          name = KRPCDisplay
          method = Text
          display = flightplan
          buttonClickMethod = ButtonClick
          buttonReleaseMethod = ButtonRelease
          pageActiveMethod = PageActive
      }
      BACKGROUNDHANDLER
      {
          name = KRPCDisplay
          method = RenderBackground
          display = flightplan
      }
  }
  ```

* **Display text is RPM page text.** RPM runs a handler's text through its formatter, so the
  script can embed variables (`{0:F0}$&$ALTITUDE`) and color tags, and RPM updates them each text
  refresh without a call from the script.
* **Display image is a PNG or JPEG**, decoded once into a texture and drawn as the page
  background, scaled to the screen. Text draws over it. The service checks the file signature,
  as Unity's `LoadImage` decodes other data as a placeholder texture.
* **Display buttons are the monitor's global buttons**, by their index in `Monitor.Buttons`,
  after RPM's per-page redirects. A page handler receives the presses of its page only. On RPM's
  bundled MFD these are UP, DOWN, ENTER, ESC, HOME, LEFT, RIGHT, R9 and R10.
* **Page buttons are RPM's until a script captures one.** The buttons that select pages, R1 to
  R7, A to G and STBY on the bundled MFD, switch the monitor away and never reach the display.
  The `krpc` page has no button, so a script brings the player back to it by capturing one:
  `CaptureButton (name, page)` makes a press of that button show the script's page, such as
  `krpc`, in place of RPM's, and fires `ButtonCaptured (name)`. A script that captures several
  buttons draws its own screen for each, as the event names the button. The player can still
  leave through the buttons the script leaves to RPM, and `ReleaseButton` gives one back.
  RPM's `lockingPage` would keep the player on the page, but it is fixed in config and would
  trap the player, so the service does not use it.
* **A capture takes the monitor's trigger out of the button.** RPM's `SmarterButton` runs, on a
  click, one private `PageTriggerSet` per monitor, whose `selector` is the monitor's
  `PageButtonClick`. The service removes the triggers whose selector targets the monitor, and
  adds a click handler of its own to the button's private `clickHandlers`. The handler calls
  `PageButtonClick` with the captured page, so RPM's locking and redirect rules still apply.
  Release puts the triggers back. Other monitors on the same button keep theirs.
* **Captures outlive the IVA.** KSP builds new buttons on vessel switch and IVA entry. The
  service keeps the captures per monitor, as it does display content, and a flight scene addon
  applies them to the new buttons in its `Update`. They are not saved with the game.
* **`PressPageButton (name)` clicks a page button as the player does**, through the button's
  `OnMouseDown`, then `OnMouseUp` on the next frame. It follows captures, and a button with
  several pages cycles through them, as RPM does. `PageButtons` names the prop's buttons that
  select the monitor's pages, captured ones included.
* **Button labels are drawn by the script.** The labels on the buttons are part of the model's
  texture. A script that gives a button its own meaning draws a label at the screen edge next to
  it, as RPM's own pages do.
* **kRPC ships an optional Module Manager patch** that adds a `krpc` page with no display name
  and no button to every prop with a `RasterPropMonitor` module, `:NEEDS[RasterPropMonitor]`.
  Every MFD then has its own `Monitor.Display`. RPM's bundled MFD config is documented as
  removable, so the patch matches the module and no prop name. The patch goes in its own file so
  a player can delete it: `RasterPropMonitorDisplay.cfg` in `GameData/kRPC/`.
* **Display content lives in the service**, per monitor, or per vessel and name. KSP rebuilds
  the IVA's modules on IVA entry, and a new handler takes the stored content. A script can set it
  before the player enters the pod. It is not saved with the game.
* **Button events count presses.** The display counts the presses and releases of each button,
  and each event is polled, firing when its count has grown. Presses within one update fire once.

A menu on one screen, with the script as its computer:

```python
monitor = conn.raster_prop_monitor.monitors(vessel)[0]
display = monitor.display
up, down, enter = (monitor.buttons.index(name) for name in ("button_UP", "button_DOWN", "button_ENTER"))
items = ["Lights", "Gear", "Brakes"]
cursor = 0

def draw():
    display.text = "\n".join(("> " if i == cursor else "  ") + item for i, item in enumerate(items))

def move(step):
    global cursor
    cursor = (cursor + step) % len(items)
    draw()

draw()
monitor.active_page = "krpc"
# The NAV button brings the player back to the menu
monitor.capture_button("buttonR1", "krpc")
display.button_pressed(up).add_callback(lambda: move(-1))
display.button_pressed(down).add_callback(lambda: move(1))
display.button_pressed(enter).add_callback(lambda: toggle(items[cursor]))
```
* **A script presses the monitor's buttons as the player does.** `PressButton` calls
  `GlobalButtonClick` then `GlobalButtonRelease` on the next frame. `ActivePage` sets through `PageButtonClick`, which
  keeps RPM's locking and redirect rules. A script can drive any existing page, such as the
  MechJeb or SCANsat pages, this way.
* **`Monitor.Text` is the page in one call**, as the player sees it, and streams. It covers pages
  whose text comes from a handler, such as MechJeb's, which a script cannot rebuild from
  variables. It is plain text, one line per screen line, holding exactly the characters RPM
  draws. Only the tags RPM consumes are removed, so every character the screen shows stays.
* **The tag rules are RPM's renderer, ported as is.** `TextRenderer.Render` parses tags inline
  as it draws, with no separate parser to call. Its rules have quirks, and the port keeps them:

  | Tag text | RPM draws |
  | --- | --- |
  | `[hw]`, `[dw]`, `[sup]`, `[sub]` and their closing tags | Nothing. The text they enclose is drawn |
  | `[@` anything `]`, even an invalid number | Nothing |
  | `[#` and 6 or 8 characters `]` | Nothing |
  | `[font` anything `]` | Nothing |
  | Any other bracketed text, such as `[abc]` or `[#12]` | The text, brackets included |
  | `[` with an empty or one-character tag, such as `[]` or `[a]`, or with no `]` after it | The rest without the `[`: `]`, `a]` |
  | `[[]` | `[]`, by the row above |
  | `[[` and a tag of 5 or more characters that matches no row above, such as `[[abcde]` | `[`. This is RPM's escape, which only a longer tag reaches |

  A `]` on a later line closes a tag, as RPM searches the whole text. Tests check `Text` against
  each row, with the expected text traced from `TextRenderer.ParseText`.
  Text in `[hw]` or `[dw]` takes one character per column in `Text`, so such a line loses its
  alignment. `RawText` keeps it. `Text` also follows the renderer's layout: the page text sits
  inside the page's margins, the page's text overlay replaces the characters under it, and a
  character past the screen edge or missing from the font is not drawn.
* **`Monitor.RawText` keeps the markup**, for a client that draws the screen itself. The tags are
  color `[#rrggbb]` and `[#rrggbbaa]`, pixel nudges `[@xN]` and `[@yN]`, half and double width
  `[hw]` and `[dw]`, `[sup]`, `[sub]` and `[fontN]`. The monitor gives the layout the tags need:
  the screen size in characters and pixels, the letter size in pixels, and the page's default
  color. `RawText` is the page text without the text overlay, which no bundled page uses.
  This recreates the text layer only. Camera views, graphs and textures are drawn under
  the text, and come only with `Image`.
* **`Monitor.Variables` names the variables the active page shows**, parsed from the page's
  source text as RPM's formatter reads it. RPM drops the formatters of lines whose variables
  are constants, such as `RPMVERSION`, so the formatters miss them. The source text of a fixed
  page is set when RPM builds the page, so `Variables` needs no IVA. A script that wants exact values reads them by name through `Computer`, with no
  knowledge of the IVA's page files.
* **Monitor readback works in any camera mode.** RPM updates a monitor only while
  `RasterPropMonitorShouldUpdate` holds for its part. Reading `Text`, `RawText`, `Variables` or
  `Image` of any other monitor runs the steps of RPM's own update for it: the computer's private
  `UpdateVariables`, then the monitor's private `FillScreenBuffer`, and for `Image` its
  `RenderScreen`. Each runs at most once a frame per computer or monitor, so a read in the frame
  of a change can give the text from before it. This serves a script that shows a pod's screens
  in a window of its own with the flight camera on, and reaches the pods the kerbal is not in.
  The vessel computer that the variables read updates on the active vessel in every camera mode.
* **`Monitors` takes the active vessel only**, and throws an exception for another. A monitor
  finds its module again on each call, by part, prop id and its place among the prop's monitor
  modules, as KSP rebuilds the IVA. It is dormant while its part has no IVA.
* **`PressButton` releases once the frame count moves on.** The server updates in
  `FixedUpdate`, which can run more than once a frame.
* **Cameras render through RPM's own `FlyingCamera`**, with a texture kRPC owns. This works in any
  camera mode, which the monitor readback does not, and matches the MFD camera pages. The
  DockingCamera service's `Camera.Image` is the model. `FlyingCamera.Render` only sets its Unity
  cameras up to render at the end of the frame, so `Image` renders them itself, farthest out
  first, and cleans them up. `FlyingCamera.Render` needs the camera on the active vessel.
* **Video is a stream of JPEG frames**, from `Frame`. Unity 2019.4 encodes JPEG and has no video
  codec, so the video is motion JPEG, and the stream's rate is the frame rate. A 640x480 frame
  is about 24 KB against 166 KB as PNG, and takes about 8 ms. A stream sustains 30 frames a
  second, or 50 with no rate limit, with the game at real time. A loop that holds each tick and
  calls `Frame` gets every tick's frame, with the game waiting for the script.
* **The field of view starts at the camera's largest**, as on an MFD camera page, and a value
  set is clamped to the camera's range, which `MinFieldOfView` and `MaxFieldOfView` give. The
  service keeps it per part, and does not save it.
* **RPM variables are read by name**, on the part's computer. The service instantiates the
  variable, calls `Update`, and reads the value. This covers what kRPC lacks, such as `CUSTOM_`
  and `MATH_` variables from IVA packs and RPM's own mod bridges. Values that depend on the vessel
  computer need the active vessel.
* **A variable is a number or a string**, the two kinds RPM has. RPM stores booleans and integers
  as doubles, a boolean as 0 or 1. The kind can change between updates, as RPM decides it from
  each evaluated value. The reads follow `PartField` in SpaceCenter, a typed property per kind
  with a string form for any:

  | Read | Returns |
  | --- | --- |
  | `VariableType (name)` | `VariableType.Number` or `VariableType.String` |
  | `NumberVariable (name)` | The double. Throws an exception for a string |
  | `StringVariable (name)` | The string. A number gives its invariant culture string |
  | `FormatVariables (text)` | The text with each variable formatted as a panel shows it, such as `{0:SIP6.1}m$&$ALTITUDE` |

  The script knows the kind ahead of time, as with `PartField`, or asks `VariableType`. Each read
  throws an exception for a name RPM does not recognize. RPM itself shows such a name as literal
  text. `FormatVariables` gives a value with RPM's own formats, such as `SIP` and `KDT`.
* **Persistent variables are numbers only**, as RPM stores them. RPM has no removal, so
  `RemovePersistentVariable` removes the entry and updates the `PERSISTENT_` variables as RPM's
  setter does.

## API

Persistent variables and RPM variables:

| Member | Kind |
| --- | --- |
| `Available` | Property |
| `Computer (part)`, `Computers (vessel)` | `Computer`: `Part` |
| `Computer.PersistentVariable (name)` | Procedure, nullable double: the part's value, else the vessel's, as `PERSISTENT_<name>` |
| `Computer.SetPersistentVariable (name, value)`, `RemovePersistentVariable (name)` | Procedures. Set fires RPM's update of the variable |
| `Computer.PersistentVariableChanged (name)` | Event |
| `GlobalPersistentVariable (vessel, name)`, `SetGlobalPersistentVariable`, `RemoveGlobalPersistentVariable`, `GlobalPersistentVariableChanged` | The vessel-global equivalents. Throw an exception for a vessel with no RPM computer |
| `Computer.VariableType (name)` | Procedure, `VariableType`: `Number`, `String` |
| `Computer.NumberVariable (name)`, `StringVariable (name)` | Procedures, double and string |
| `Computer.FormatVariables (text)` | Procedure, string |

Monitors and displays. A monitor works on the active vessel only, and a display on any vessel:

| Member | Kind |
| --- | --- |
| `Monitors (vessel)` | List of `Monitor` |
| `Monitor` | `Part`, `PropName`, `Pages` (names), `ActivePage` (get, set), `Buttons` (global button names, by id), `PressButton (id)`, `PageButtons`, `PressPageButton (name)`, `CaptureButton (name, page)`, `ReleaseButton (name)`, `ButtonCaptured (name)` (event), `ScreenWidth`, `ScreenHeight` (characters), `ScreenPixelWidth`, `ScreenPixelHeight`, `LetterWidth`, `LetterHeight` (pixels), `DefaultColor` (of the active page), `Text`, `RawText`, `Variables`, `Image` (PNG) |
| `Monitor.Display`, `Display (vessel, name)` | `Display`: `Name` (null for a monitor's own), `Text` (get, set), `Image` (get, set, PNG or JPEG, null clears), `Clear ()`, `Shown` (whether a monitor shows it now) |
| `Display.ButtonPressed (id)`, `ButtonReleased (id)` | Events |

Cameras:

| Member | Kind |
| --- | --- |
| `Cameras (vessel)` | List of `ExternalCamera` |
| `ExternalCamera` | `Part`, `Name` (`ExtCam1`, ...), `MinFieldOfView`, `MaxFieldOfView`, `FieldOfView` (get, set), `Image (width, height)` (PNG, active vessel only), `Frame (width, height, quality)` (JPEG, for video) |

## Phases

The service is one pull request. Each phase is a sequence of commits on its branch, with its own
in-game tests, built in the order below.

| Phase | Adds | Needs in game |
| --- | --- | --- |
| 1 | Service skeleton, `Available`, `Computer`, persistent variables and their events, variable reads | Two Mk1 lander cans, which RPM patches with a computer. RPM leaves the stock Mk1 pod (`mk1pod_IVA`) unpatched. Tests set variables and read them back through `PERSISTENT_` |
| 2 | `Monitor`: pages, `ActivePage`, `PressButton`, `Text`, `RawText`, `Variables`, `Image` | The IVA camera mode, through `SpaceCenter.Camera`, set once the launched vessel settles. KSP ignores it straight after a launch |
| 3 | `KRPCDisplay`, `Display`, button events, the optional Module Manager patch | Phase 2, plus a test that presses a display button with `PressButton`. A test overlay, `mods/JSI/KRPCTestDisplay.cfg`, adds a page for a named display |
| 4 | `ExternalCamera` (#424) | Two JSI External Radial-mount Cameras on the test craft, as `ExtCam1` and `ExtCam2`. Works outside the IVA |

Phase 3 depends on phase 2 for its tests. Phase 4 depends only on phase 1. Phase 1 adds the
test mod pin, which needs RPM and Module Manager, and the full RPM package so the stock pods have
RPM IVAs.

Commits on the same branch follow the phases, from trying the service in game: monitor
readback in any camera mode, page button captures with `PressPageButton`, `ExternalCamera.Frame`
for video, and a Python tutorial with a screen menu and a camera video window.

Video exposed a core bug: a rate limited stream updated at as little as half its rate, as
physics ticks run in bursts. Its fix is a separate pull request, merged before this one.

## Open Questions

* Player presses of global buttons on pages kRPC does not own. RPM binds them to the page's
  handler, and the click handler hook that captures use could report them too. Not planned.

## Considered and Not Planned

| Option | Reason |
| --- | --- |
| A kRPC `IJSIModule` for `PLUGIN_` variables and `PLUGINACTION` switches | Needs RPM at compile time. Persistent variables give the same channel |
| A `KRPCSwitch` prop module for button events | Switches on persistent variables already give events, with no kRPC config in the IVA |
| A video codec or a video transport | Unity 2019.4 has no video encoder. A stream of JPEG frames carries video with no protocol change |
| Video of monitor screens | A PNG per call is enough for a view of a screen. `Monitor.Image` streams at a rate if a script needs it |
