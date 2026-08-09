# UI service: code-built controls, layout and new widgets

**Status:** in progress. Issue [krpc/krpc#312](https://github.com/krpc/krpc/issues/312).
All seven phases are implemented, as one PR rather than one each; PR to follow. The
follow-ups from [ui-widget-gap-audit.md](ui-widget-gap-audit.md) land in the same PR, and
the class hierarchy below includes them.

## Context

Issue #312 asks for enough UI to rebuild a control panel that the reporter was running as a separate
win32 window, because KSP in true fullscreen cannot host a child window. The attached screenshot is a
"Launch Control" dialog. Mapping its widgets against the service as it stands today:

| Widget in the screenshot | UI service today |
| --- | --- |
| Labels | `Text` |
| Push buttons | `Button` |
| Editable numeric fields | `InputField` |
| Check boxes | missing |
| Radio buttons, six mutually exclusive columns of three | missing |
| Disabled controls (greyed check box, read-only fields) | missing |
| Table of stage data, 5 rows by 6 columns, in a scrolling area | missing |
| Group boxes with captions | missing |
| Window with a title bar, close box and dragging | missing |
| Any layout other than absolute pixel positioning | missing |

The issue names check boxes and enable/disable explicitly. Those two alone do not make the screenshot
buildable: the stage table is 30 cells and the radio matrix is 18 controls plus headers, and every
element today is placed by hand through `RectTransform`, so the arithmetic falls on the client.

Two problems are therefore in scope: **how controls are built** (the first decision, which unblocks
everything else), and **which controls exist**.

## Decisions

1. **Build every control in C#. Delete the prefabs and the asset bundle.**
2. **Skin from KSP's own `UISkinManager.defaultSkin`**, giving the stock KSP look.
3. **Introduce two internal base classes**, `Control` (carries `Interactable`) and `Container`
   (carries the `AddX` methods, shared by `Canvas` and `Panel`).
4. **One `Toggle` class covers both check box and radio button**, the difference being membership of a
   `ToggleGroup`.
5. **Layout groups ship alongside the new controls**, not as a later nicety.
6. **UI works in every game scene**, not just flight.
7. **`Text.Font` keeps taking an OS font name string.** The default is the built-in Arial, at the
   size the skin gives, and the existing `Font.CreateDynamicFontFromOSFont` escape hatch stays. The
   skin's own font is not followed: the game picks it for the language it is being played in, so a
   script would get different text at a different size depending on who runs it.
8. **UI objects have value equality**, and colors carry an alpha channel. Both are breaking, and this
   release is the cheapest time to take them.

## Why code-only

`service/UI/KRPC.UI.ksp` is a binary Unity AssetBundle checked into the `krpc` repo, with
`service/UI/prefabs/*.prefab` as its Unity sources. It was built with **Unity 5.2.4f1 through KSP
PartTools**, outside Bazel. Every control comes from `Addon.Instantiate(parent, "<PrefabName>")`,
which loads that bundle over a deprecated `WWW` call.

Consequences of keeping it:

- Adding any control requires a Unity editor of the right version. The step is not reproducible from
  the repo and cannot run in CI.
- The bundle is opaque to review and to diffs.
- The service is pinned to whatever a 2015-era editor emitted, while the game is Unity 2019.4.

Nothing in the bundle is irreplaceable. The prefabs are plain `UnityEngine.UI` component graphs
(`Image`, `Text`, `Button`, `InputField`, `CanvasRenderer`, `RectTransform`) plus sprite and font
references. All of it can be assembled at runtime.

**Verified available.** The mod compiles against the `@ksp` stub assemblies, so the required types
must be present there, and they are:

- `UnityEngine.UI.dll`: `Image`, `Selectable`, `Toggle`, `ToggleGroup`, `Slider`, `Dropdown`,
  `ScrollRect`, `Scrollbar`, `RectMask2D`, `HorizontalLayoutGroup`, `VerticalLayoutGroup`,
  `GridLayoutGroup`, `LayoutElement`, `ContentSizeFitter`.
- `Assembly-CSharp.dll`: `UISkinManager`, `UISkinDef`, `UIStyle`, `UIStyleState`,
  `KSP.UI.KSPGraphicRaycaster`.

`UISkinManager.defaultSkin` is a `UISkinDef` exposing a `UIStyle` per widget kind (`window`, `box`,
`button`, `toggle`, `label`, `textField`, `textArea`, `scrollView`, `horizontalScrollbar` and thumb,
`verticalScrollbar` and thumb, `horizontalSlider` and thumb, `verticalSlider` and thumb) plus a
`Font`. Each `UIStyle` carries `normal`, `highlight`, `active` and `disabled` `UIStyleState`s, each
with a `background` sprite and a `textColor`, along with `font`, `fontSize`, `fontStyle`,
`alignment`, `wordWrap` and `richText`. That covers sprite-swap transitions and the greyed disabled
state the screenshot needs, for free.

Every part of the skin is treated as optional: a missing style leaves a control unstyled rather than
failing to create it, so a scene that does not provide one still gives a working interface.
`UISkinManager.GetSkin(string)` reaches the other named skins if a per-control skin choice is ever
wanted. Not proposed now.

Dropping the bundle also drops the two assemblies only it needed,
`UnityEngine.AssetBundleModule` and `UnityEngine.UnityWebRequestWWWModule`, from
`tools/build/ksp/` and from the list `tools/krpctools/krpctools/servicedefs/` copies out of a KSP
install. The two lists have to be kept in step; `Image` adds `UnityEngine.ImageConversionModule` to
both.

### Appearance changes, deliberately

The current prefabs reference Unity's built-in editor resources (`resources/unity_builtin_extra` for
the panel sprite, `library/unity default resources` for Arial). Those built-ins are not reliably
loadable at runtime in a player build, so the existing look **cannot** be reproduced exactly in code.

Adopting the KSP skin is the better outcome anyway: controls created by a script will match the rest
of the game rather than looking like a default Unity canvas. It is still a user-visible change and
needs a changelog entry. The `Panel` styling properties (below) give scripts a way to override it.

## Prefab to code

| Prefab | Replacement |
| --- | --- |
| `Panel` | `GameObject` with `RectTransform`, `CanvasRenderer`, `Image`; sprite `defaultSkin.window.normal.background`, `Image.Type.Sliced` |
| `Text` | `RectTransform`, `CanvasRenderer`, `Text`; font and size from `defaultSkin.label`, color from `defaultSkin.label.normal.textColor` |
| `Button` | Panel-like `Image` from `defaultSkin.button.normal.background`, plus `UnityEngine.UI.Button` with `transition = SpriteSwap` and a `SpriteState` filled from the style's `highlight`/`active`/`disabled` states, plus a child `Text` stretched to fill |
| `InputField` | `Image` from `defaultSkin.textField.normal.background`, child text and placeholder `Text` objects, `UnityEngine.UI.InputField` with `textComponent` and `placeholder` wired up |

A single internal helper (`Widgets.cs`) owns sprite lookup, sprite-state construction, font lookup and
the "create a child `RectTransform` stretched to fill its parent" step, so each control class stays
short.

Fonts are made once and shared there, keyed by name. `Text.Font` otherwise makes a font per label and
leaves it behind when the label goes, and freeing per label would have to reach the labels inside a
button, a toggle and an input field, which a client can set the font of but cannot remove.

One behavior note: `InputField.Text` currently returns a `Text` built from the input field's own
`GameObject`, which only works because the prefab happens to put the `Text` component there. The
code-built version puts it on a child, so the property returns the child's component instead. The
client-visible API is unchanged.

The placeholder is a second child, and `InputField.Placeholder` hands it to a client as a `Text` the
same way. Unity shows it only while the field is empty, so it is the one part of a dialog a script
cannot build for itself: a label of its own laid over the field would stay put as the user types. It
is drawn at half the alpha of the field's own text, so a hint does not read as a value.

## Object identity and lifetime

The objects handed to a client are wrappers around Unity components, created fresh on each call, so
every one of them would get its own identifier in the object store: reading `RectTransform`
repeatedly would grow the store without bound and the objects would never compare equal.

- **`Object` derives from `Equatable<Object>`**, comparing the game object it wraps, as the other
  services do. No wrapper needs caching to be handed out as the same object.
- **`Remove` decides whether a client may take an object away; `Destroy` is the teardown.** The
  parts a control is built from, such as the label of a button or the contents of a scroll view, and
  the stock canvas, are not removable, and asking says so rather than reporting that the object could
  not be found. `Destroy` also runs from the addon sweeping up after a client or a scene, where
  refusing would abandon whatever is left in the sweep. It is virtual, for objects holding something
  Unity does not destroy with the game object: a texture and a sprite are assets, not children, so
  `Image` frees both.
- **A destroyed object records that it was destroyed.** Unity carries out a destroy at the end of the
  frame it was asked for in, and the server answers more than one call per frame, so the game object
  alone cannot say whether an object is gone.

## Game scenes

The `UI` service is already declared `[KRPCService(Id = 7, GameScene = GameScene.All)]`, so the RPCs
are callable everywhere. What is flight-only is the addon behind them:
`[KSPAddon(KSPAddon.Startup.Flight, false)]`.

**Change it to `KSPAddon.Startup.AllGameScenes`**, matching `server/src/Addon.cs` and the
KerbalAlarmClock, RemoteTech, LiDAR and DockingCamera services, which already use it.

- **`Canvas.StockCanvas` is built on each access** and reports "The stock UI canvas is not available
  in the current game scene" when `UIMasterController.Instance` or its `appCanvas` is missing.
- **`UI.AddCanvas()` creates a bare `GameObject` with no `DontDestroyOnLoad`**, so a client-created
  canvas dies with its scene like everything else. Worth stating in the docs rather than fixing: a
  canvas that outlived its scene would also outlive the `Clear()` that owns it. It carries a
  `CanvasScale` component so that it follows the interface scale the player has set, which the game
  applies by setting the scale factor of each of its own canvases. The scale is followed rather than
  read once, as the player can change it at any time.
- **UI objects do not survive a scene change**, by design. A client that builds a panel in the space
  center and then launches must rebuild it in flight.

### Releasing the elements of a scene

Elements have to be taken away deliberately. They are parented to `AppCanvas`, which is in the
`DontDestroyOnLoad` scene, so the scene unload never touches them, and **a destroy asked for while a
scene is loading does not take effect during that load**: the object lives on through the whole of
the scene being entered and is only collected by the change after that. `Awake` and `OnDestroy` both
run while the scene is loading, and `DestroyImmediate` makes no difference.

`IClientOwnedCollection` therefore splits the two halves, and `ClientCleanupAddon` uses them:

| Half | When | What it does |
| --- | --- | --- |
| `Detach` | a scene is entered | empties the collections, so a client cannot reach the old state |
| `ReleaseDetached` | that scene's first sweep | releases the detached entries, the first frame the scene is actually running |

Keeping them apart also means anything a client adds to the new scene before the first sweep is not
swept away with the old, which is the obvious way to get this wrong and is covered by a test.

`ClientCleanupAddon` no longer releases from `OnDestroy` at all, so **an addon that never sweeps
would never release**. Every subclass sweeps today. The release actions all tolerate being run a
scene later: `PartHighlightAddon.Unhighlight` null-guards its part and `ResourceTransfer.Cancel` only
sets a flag. The base class is shared with the Drawing addon and four SpaceCenter ones, all
`KSPAddon.Startup.Flight`, where the release now happens on the first sweep of the next flight scene
rather than on leaving flight. Nothing is observable in that: those game objects are the ordinary
kind, taken away by the scene unload regardless.

## New API surface

`Canvas` and `Panel` today duplicate `AddPanel`/`AddText`/`AddInputField`/`AddButton` verbatim.
Adding four more controls would make that sixteen duplicated methods, so the `AddX` methods move to an
internal `Container` base class.

kRPC's scanner uses `Type.GetMethods()` with `IsDefined(..., inherit: false)`, so public members
declared on a non-`[KRPCClass]` base are flattened into every derived `[KRPCClass]`. This is how
`Object.Visible` and `Object.Remove` already reach `Panel` and friends. **The base members must not be
`virtual` and overridden**, or the attribute lookup on the override will miss them. Doc comments
cannot cross-reference an inherited member either: `<see cref="Panel.AddText" />` does not compile
once `AddText` is declared on `Container`, and pointing it at `Container` fails the service
definition generator's check that every cref names a kRPC member. Class-level crefs are used instead.

### Class hierarchy

```
Object                      Visible, Remove, RectTransform, LayoutElement
├── Container               AddPanel, AddText, AddButton, AddInputField,
│   │                       AddToggle, AddToggleGroup, AddScrollView,
│   │                       AddSlider, AddDropdown, AddImage
│   ├── Canvas
│   └── Panel               Color, Style, Draggable, Layout, SizeFitter,
│                           BringToFront
├── Control                 Interactable, Color, Tooltip
│   ├── Button              Text, Clicked, Pressed
│   ├── InputField          Value, Text, Placeholder, Changed, ContentType,
│   │                       CharacterLimit, ReadOnly
│   ├── Toggle              Checked, Changed, Text, Group
│   ├── Slider              Value, Min, Max, Changed
│   └── Dropdown            Options, SelectedIndex, Changed
├── Text                    WordWrap
├── Image                   Content, SetPixels, UpdatePixels, Color
├── ToggleGroup             Selected, AllowSwitchOff
└── ScrollView              Content, Horizontal, Vertical
```

`RectTransform` and `LayoutElement` sit on `Object` rather than on `Control` and `Panel`: every
element has a rect transform, and a label in a table needs a layout element as much as a button does.
A canvas is the exception, and says so rather than being given a layout element: it is not inside
anything that would lay it out, and the stock canvas is the game's own object, which kRPC would never
take the component back off.

`Layout`, `LayoutElement` and `SizeFitter` do not derive from `Object`. They wrap a component on an
object that already exists, so inheriting `Remove` would offer to destroy the panel they belong to.
They follow `RectTransform`, which is a plain `[KRPCClass]` for the same reason.

`Interactable` maps to `Selectable.interactable`, which drives both input blocking and the greyed
disabled sprite. Putting it on `Control` means it lands on every interactive widget at once, which is
the "control enable\disable function is missing" half of the issue.

### What a client is told, and when

- **`Changed` reports only what the user did.** Unity notifies a control's listeners whether the user
  or a client made the change, so a client that set a value saw it reported back as the user's.
  `Set*WithoutNotify` covers the direct cases; a slider needs a flag as well, because Unity clamps the
  value when the range changes.
- **`Visible` is the element's own setting**, read from `activeSelf`, so it round-trips through a
  hidden parent. An element is only drawn when everything it is inside is visible as well, which is
  what a client wanting to know whether something is on screen has to ask for itself. Building a
  dialog hidden and showing it once it is assembled is the obvious way to use this API.
- **Colors are `(red, green, blue, alpha)` throughout the service.** An element is drawn over what is
  behind it and often has to let some show through: RGB cannot express a translucent panel, and
  reading back a transparent element gives an opaque color. The other services draw in the world and
  keep RGB, so the UI conversion is named apart from theirs, or a file reaching for both is left with
  an ambiguous call.
- **A property that can return null needs `Nullable = true` on the procedure**, or kRPC rejects the
  return. `Toggle.Group`, `ToggleGroup.Selected` and `Panel.Layout` all legitimately return null.
  Nothing outside the game catches a missing attribute: the service definitions generate, the docs
  build and `//:test` passes; only the in-game tests fail, with "not marked as nullable".
- **An index or a value out of range is refused**, rather than silently clamped as Unity would.
  A slider range whose ends would cross is refused on the same principle, so a range is moved by
  growing it from the end that is moving away before bringing the other end up to it. The one clamp
  that stays is Unity moving a slider's value into a narrowed range: the old value has to go
  somewhere, and this is what the `Changed`-suppression flag covers.

### Toggles and grouping

`Toggle` wraps `UnityEngine.UI.Toggle`: a background `Image` from `defaultSkin.toggle.normal`, a
checkmark `Image` from `defaultSkin.toggle.active` assigned to `Toggle.graphic`, and a child `Text`
label. `Checked`/`Changed` follow the existing polling idiom of `Button.Clicked` and
`InputField.Changed`.

Assigning `Toggle.Group` makes a set mutually exclusive, which is the radio button. **Unity's
`ToggleGroup` does not have to be an ancestor of its toggles**, only referenced by them. That matters
here: the screenshot groups by *column* while laying out by *row*, so grouping has to be independent
of parenting. `ToggleGroup` is therefore a standalone object from `AddToggleGroup()`, not a property
of a container. `ToggleGroup.Selected` returns the checked member, so the six-column radio matrix is
six streams rather than eighteen.

**The group applies exclusivity itself rather than leaving it to Unity.** Unity reaches
`ToggleGroup.NotifyToggleOn` only `if (m_Group != null && IsActive ())`, and `IsActive` is false for
anything inside a hidden parent, so a group built hidden would let every one of its toggles be
checked at once and then put itself right when shown, reporting the toggle it cleared as a change the
user made. `ToggleGroup` already holds its members, so `Toggle.Checked` goes through
`ToggleGroup.Check`, which unchecks the siblings whether or not anything is on the screen. With the
group already consistent, Unity's repair on enable finds nothing to change.

Two consequences of the same gating:

- **A toggle joins and leaves a group unchecked**, and is checked again once it is a member, which is
  also what unchecks the rest of the new group. Unity otherwise notifies the listeners of a group's
  toggles when an already checked toggle joins it, so grouping controls after setting their initial
  state would report a change nobody made.
- **`AllowSwitchOff` stops the user clearing the checked toggle**, and a client setting
  `Toggle.Checked` is obeyed either way. `Check` allows switch off for the duration of its own writes
  to get this, and the property says so.

### Layout

Without this the rest is usable in principle and painful in practice.

| Class | Wraps | Key members |
| --- | --- | --- |
| `Layout` | `HorizontalLayoutGroup`, `VerticalLayoutGroup`, `GridLayoutGroup` | `Spacing`, `Padding`, `ChildAlignment`, `CellSize`, `Constraint`, `ConstraintCount` |
| `LayoutElement` | `LayoutElement` | `MinSize`, `PreferredSize`, `FlexibleSize`, `IgnoreLayout` |
| `SizeFitter` | `ContentSizeFitter` | `HorizontalFit`, `VerticalFit` |

Obtained through `Panel.AddHorizontalLayout()` / `AddVerticalLayout()` / `AddGridLayout()`, with
`Panel.Layout` returning the existing group or null. `Object.LayoutElement` and `Panel.SizeFitter`
add their component on first access. The size fitter is what makes the contents of a scroll view grow
to hold what is put in them.

`Layout.Padding` is a tuple of ints, as Unity measures it in whole pixels and a fractional value would
be silently truncated. It is the first `Tuple<int,int,int,int>` in the API, so the C client's docgen
emits a type Sphinx cannot resolve: `doc/conf.py.tmpl` needs `krpc_tuple_int32_int32_int32_int32_t` in
`nitpick_ignore` or `bazel build //doc:html` fails under `-W`, which CI runs and `//:test` does not.
Setters taking a size convert the tuple through `ToVector`, which is where the null check lives.

With these, the stage table is a `ScrollView` whose content panel has a grid layout of six columns,
and the radio matrix is a vertical layout of horizontal layouts.

### Group boxes and windows

- Group box: a `Panel` with `Style` set to `PanelStyle.Box`, plus a `Text` caption. A sprite cannot
  cross the wire, so the style is an enumeration of `Window`, `Box` and `None`, which is what a group
  box actually needs. `None` disables the background rather than clearing the sprite, as Unity fills
  an image that has no sprite with its color; such a panel takes no pointer events and can only be
  dragged by what it contains.
- Window: `Panel.Draggable`. Dragging needs an `IDragHandler` MonoBehaviour, which a client cannot
  supply, so it has to be a server-side property. Title bar and close button are then just a `Text`
  and a `Button` composed by the script.

### Images

`Image.Content` takes the bytes of a PNG or JPEG file. `Texture2D.LoadImage` cannot be used to
validate them: it returns true for arbitrary bytes and hands back a placeholder texture, so the file
signature is checked before loading. With no picture set, an image is a plain colored rectangle.

## Phases

Each is independently implementable and mergeable.

| Phase | Content | Closes |
| --- | --- | --- |
| 1 | `AllGameScenes`, release the elements of a scene on the next scene's first sweep, canvas scale | |
| 2 | Code-built `Panel`, `Text`, `Button`, `InputField`. Delete `prefabs/`, `KRPC.UI.ksp` and `Addon.Instantiate`. Add `Control` and `Container` bases, `Interactable`, value equality | half of #312 |
| 3 | `Toggle`, `ToggleGroup` | rest of #312 |
| 4 | `Layout`, `LayoutElement`, `SizeFitter` | |
| 5 | `ScrollView` | |
| 6 | `Panel.Style`/`Color`/`Draggable` | |
| 7 | `Slider`, `Dropdown`, `Image` | |

Phase 1 is small, independent of everything else, and worth landing first: it is a user-facing fix on
its own, and doing it before the rewrite means the code-built controls are exercised in every scene
from the start rather than being retro-fitted.

Phase 2 carries all the risk and no new API, so it is worth landing and testing in-game on its own.
Phase 3 is what the issue literally asks for. Phases 4 and 5 are what make the screenshot buildable.

## Files

Per new source file, remember the checklist that `//:csproj-test` and `//doc:check-documented` gate:

- `service/UI/src/<Name>.cs`, plus `<Compile Include="…" />` in `service/UI/src/KRPC.UI.csproj`.
- `doc/api/ui/<name>.tmpl` and an entry in the `doc/api/ui.tmpl` toctree.
- Every new member listed in `doc/order.txt`, or the doc build fails with "Don't know how to order",
  and any word the spell checker does not know in `doc/src/dictionary.txt`.
- An entry in `service/UI/CHANGELOG.md` under `## [0.7.0] - unreleased`.
- Tests in `service/UI/test/test_<name>.py`.

Phase 2 also removes `service/UI/prefabs/`, `service/UI/KRPC.UI.ksp` and its entry in the `UI`
filegroup in `service/UI/BUILD.bazel`. That drops the `#pragma warning disable 618` around the
deprecated `WWW` load with it.

## Testing

The existing `service/UI/test/*.py` are in-game tests run by `bazel run //:test-ingame`, not part of
`//:test`. They can assert state round-trips but not appearance, so:

- `test_game_scenes.py` sets `krpc.game_scene` the way `service/SpaceCenter/test/test_game_scene.py`
  does and builds an interface in the space center, the tracking station and both editors. It covers
  the scene change itself as well: the elements of the previous scene go, and an element added to the
  new one before the sweep happens is kept.
- Every control is covered for `Interactable`, and per-control tests follow `test_button.py`: create,
  set, read back, remove.
- A `ToggleGroup` test asserts that checking one member unchecks its siblings, that toggles in
  *different* groups under the same parent do not interact, and that a group built hidden is
  exclusive and reports no change when it is shown.
- Appearance and layout need eyeballing in-game. A throwaway script that reproduces the #312
  screenshot's dialog is the honest acceptance test for phases 3 to 5.

**The in-game tests are the only gate that matters here.** `bazel test //:test` passes whether or not
the service works at all in the game. Run `bazel run //:test-ingame -- service/UI/test/ -v` before
believing any of this works.

**A green in-game suite is not enough either.** Write each assertion from what a property claims, not
from what the code does: a test written from the code agrees with whatever the code does, which is how
`Changed` came to be tested for the wrong behavior rather than for none. Two defects that no test
reached, a toggle group built hidden and an element shown one part at a time, were both found by
using the API the way a client would, hidden until assembled.

Two false signals to avoid when testing lifetime:

- `Text.Content` reads `UnityEngine.UI.Text.text`, a plain managed field, which keeps returning the
  old string after the object behind it has been destroyed. Ask for something that reaches the
  engine, such as the visibility.
- A static frame counter in a probe, on a machine with a low frame rate, can make the addons look as
  though they stopped updating after the first scene change. They do not.

`test_canvas.py::TestCanvas::test_rect_transform` asserted the stock canvas has a scale of `1.0`. It
is whatever the player's KSP interface scale setting is, so the test failed on `main` as well. The
assertion is dropped: comparing it against the game's setting would only restate what the property
returns.

## Open questions

1. **Construction cost.** A 30-cell table is 30 RPCs. Left as it is, to be revisited only if it
   turns out to matter in practice. A script builds its interface once at startup, and streams
   cover the reading side. If it does matter, a batch helper such as
   `Panel.AddTextGrid(rows, columns)` returning a list is the cheapest fix.

Resolved by building it: **per-scene availability of `UISkinManager.defaultSkin` and
`UIMasterController.appCanvas`**. Both fallbacks are in the code and the scene tests cover them.
`Widgets.Style` returns null when the skin is missing and every control is built unstyled rather than
failing, and `Canvas.StockCanvas` throws when the game has no canvas to give. In practice both are
present in the space center, the tracking station and both editors.
