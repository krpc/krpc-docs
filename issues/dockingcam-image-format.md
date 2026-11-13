# DockingCamera: take an image format in Camera.Image

`DockingCamera.Camera.Image` is a property that always returns a PNG. A JPEG is several times
smaller and quicker to encode, which matters when a script reads frames at a rate.

* Make `Camera.Image` a method taking an `ImageFormat`, `PNG` or `JPEG`, and a JPEG quality, checked
  only for JPEG.
* Breaking: clients that read `Image` as a property must call it.
* Extend the in-game test to cover both formats.
