# UI service: widget gap audit against MechJeb

**Status:** done — see the outcome at the end. Gaps 1 to 7 are implemented alongside the
[ui-controls-and-layout.md](ui-controls-and-layout.md) work (issue
[krpc/krpc#312](https://github.com/krpc/krpc/issues/312)), in the same PR; gap 8 was
rejected. This doc measured what was still missing for "any reasonable in-game
interface".

## Method

"Reasonable" is defined by what a heavily used mod interface actually draws. MechJeb 2's
IMGUI code was taken as the census: every `GUILayout`/`GUI` widget call in its source was
counted, along with the composite helpers in `GuiUtils.cs` that its windows are built from.
The widget *kinds* carry over even though MechJeb uses IMGUI and kRPC builds uGUI objects.

Census (calls in MechJeb 2 source): `Label` 391, `Button` 200, `Toggle` 170,
`BeginHorizontal`/`BeginVertical` 276, `TextField` 61, sliders 14, `SelectionGrid` 5,
`BeginScrollView` 5, `Box` 9, `Window` 4, `RepeatButton` 3, plus helpers for numeric
entry (`SimpleTextBox` over `EditableDouble`), steppers (`ArrowSelector`), combo boxes,
tooltips, color-tinted buttons, and a texture-drawn flight graph.

## Coverage

| MechJeb pattern | kRPC UI service | Status |
| --- | --- | --- |
| `Label` | `Text` | covered |
| `Button` | `Button` | covered |
| `Toggle` (check box) | `Toggle` | covered |
| Radio buttons, `SelectionGrid` | `ToggleGroup` + grid `Layout` | composable |
| `TextField` (numeric via `EditableDouble`) | `InputField` | **gap: no content filtering** |
| `HorizontalSlider` | `Slider` | covered |
| `VerticalSlider` | — | **gap: horizontal only** |
| `BeginHorizontal`/`Vertical`, `Space`, `FlexibleSpace`, `Width`/`Height` | `Layout`, `LayoutElement`, invisible `Panel` as spacer | covered |
| `BeginScrollView` | `ScrollView` | covered |
| `Box` (group frame) | `Panel.Style = Box` | covered |
| `Window` (drag, title, close) | `Panel.Draggable` + composed `Text`/`Button` | composable |
| `BringWindowToFront` | — | **gap: no draw-order control** |
| Combo box (`GuiUtils.ComboBox`) | `Dropdown` | covered |
| Stepper (`ArrowSelector`) | `Button` + `Text` + `Button` | composable |
| `RepeatButton` (hold to nudge) | `Button.Clicked` latches clicks only | **gap: no held state** |
| Tooltips (`RecordTooltip`/`ShowTooltip`) | — | **gap** |
| State shown by tinting (`GUI.color` on buttons) | `Panel.Color`, `Image.Color`, `Text.Color` only | **gap: controls have no color** |
| `GUI.enabled` | `Interactable` | covered |
| Flight graph (`DrawTextureWithTexCoords`) | `Image.Content`, PNG regenerated per update | workable |
| Skin, interface scale | game skin + `CanvasScale` | covered |
| `GUI.changed` | `Changed`/`Clicked` polling or streams | covered |

## Gaps, ranked

1. **`InputField` content filtering.** Numeric entry is the single most common mod input
   (all 61 MechJeb text fields edit numbers). A client can only validate after the fact,
   by which time the field already shows the rejected text. Unity's
   `InputField.contentType` (`IntegerNumber`, `DecimalNumber`, also `Password`),
   `characterLimit` and `readOnly` are one-line wraps. High value, low effort.
2. **A color on controls, at least `Button`.** MechJeb signals autopilot state by tinting
   buttons green/yellow/red; the service can tint panels, images and text but no control
   backgrounds. Tinting multiplies the background image color under the sprite-swap
   transition, so it composes with the skin. High value, low effort.
3. **Tooltips.** Needs a server-side hover component and a shared label; a
   `Control.Tooltip` string property would cover it. Medium value, medium effort.
4. **Bring a panel to the front.** Overlapping draggable windows keep creation order;
   uGUI draws by sibling order, so a `Panel.BringToFront()` calling
   `Transform.SetAsLastSibling` covers it. Medium value, low effort.
5. **Vertical slider.** Unity's `Slider.direction` plus swapped track/thumb styles.
   Low value, low effort.
6. **Button held state.** A `Pressed` property from pointer-down/up handlers enables the
   hold-to-repeat pattern. Low value, low effort.
7. **`Text` word wrap.** Unity wraps by default; MechJeb turns it off for value labels so
   the layout does not reflow. `horizontalOverflow` as a bool property. Low value, low
   effort.
8. **`InputField` commit signal.** `Changed` fires per keystroke; `onEndEdit` would tell a
   client the user finished (focus lost or return pressed). Low value, low effort.

Not worth chasing from this census: progress bars (a non-interactable `Slider` or a
sized `Panel` serves), image buttons, color pickers, raw-pixel textures (regenerated PNG
via `Image.Content` serves until profiling says otherwise), multi-line input fields.

## Outcome

Gaps 1 to 7 are implemented, in the same PR as the #312 work:

1. `InputField.ContentType` (enum `InputContentType`: standard, integer, decimal,
   alphanumeric, password), `CharacterLimit`, `ReadOnly`. Only user input is filtered.
2. `Color` on the `Control` base, so every control has it. Tints the part that responds
   to the user: the body of a button, dropdown or input field, a toggle's box, a
   slider's handle.
3. `Tooltip` on every control. Shown by a server-side hover handler, skin box style,
   follows the pointer, built on pointer enter and destroyed on exit so nothing outlives
   its scene.
4. `Panel.BringToFront`; a draggable panel also raises itself on pointer down. Presses
   on controls inside the panel do not raise it: Unity gives the press to the topmost
   element that takes one.
5. `AddSlider(vertical, visible)` — direction is fixed at creation, as the track and
   handle are laid out for one orientation.
6. `Button.Pressed`, true while the pointer holds the button down.
7. `Text.WordWrap`, default on, matching Unity.

Gap 8 (an input commit signal) was **rejected**: a client can detect the end of typing
from the per-keystroke `Changed` events and a timeout of its own choosing.

Beyond the audit, `Image.SetPixels(data, width, height)` draws a picture from raw RGBA
bytes, rows top to bottom, reusing the texture when the size is unchanged so a graph can
be redrawn every update without building textures and sprites each time, and
`Image.UpdatePixels(data, x, y, width, height)` redraws one block of it so an
incremental change only sends what changed. Both supersede the "regenerated PNG" advice
above for anything redrawn often. `UpdatePixels` is refused on a file-loaded picture:
the file contents a client reads back would no longer match the screen. The GPU upload
is the whole texture either way (`Texture2D.Apply`); it is the RPC payload that shrinks.
