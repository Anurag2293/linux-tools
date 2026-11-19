# Snap Corner

A small, native screenshot tool for Ubuntu 20.04 GNOME on X11. Uses the system's
Python 3, PyGObject, GTK 3, and Cairo; no pip packages, browser, or root access.

- **Ctrl+Alt+S**: freeze the desktop, then drag to select an area. Escape or
  right-click cancels.
- **Ctrl+Alt+F**: capture the monitor under the mouse pointer.
- Both shortcuts also work while a Shell menu (such as the notification list) is
  open. A small Shell extension in `extension/` owns the keys; for area capture
  it closes the menu after the freeze so you can select.
- A preview appears at the bottom right of the captured monitor. Drag the
  **picture** into T3 Code's message input, Slack, a file manager, or another app
  that accepts image files. It offers both a PNG file URI and PNG image data.
- Each screenshot is copied to the clipboard for **Ctrl+V**, and saved under
  the Pictures directory's **Screenshots** folder, using unique timestamp names.
- Preview buttons: **Edit**, **Copy**, **Open**, **Folder**, and **×** to dismiss.
- Previews stack upward from the corner, newest at the bottom. Cards that no
  longer fit on the monitor are dropped, oldest first. The stack is hidden while
  a capture or an editor is open, so it never appears in screenshots.
- Previews dismiss after 30 seconds. Hovering any card or dragging pauses
  dismissal; a successful drop dismisses that card immediately. Cancelled or
  rejected drops keep it available for another 30 seconds. Saved files are kept.

## Editor

Click a preview's picture (or **Edit**) to open the editor on that monitor.

- Tools: **Move** (V), **Crop** (C), **Pen** (P), **Marker** (M), **Arrow** (A),
  **Box** (R), **Text** (T), **Pixelate** (X). Sizes 1 to 4, eight colors.
- Move drags an annotation; Delete removes it; double-click text to edit it.
  With an annotation selected, a color or size click restyles it.
- Crop is non-destructive and undoable. Ctrl+Z / Ctrl+Shift+Z undo and redo.
- **Save** (Ctrl+S or Enter) writes a PNG to the Pictures folder, copies it to
  the clipboard, and adds it to the corner stack for dragging. **Copy** (Ctrl+C)
  copies without saving. Esc or **Cancel** closes, asking first if there are edits.
- Saved edits start as `edited_<date>_<time>.png`. In the background, `claude -p
  --model haiku` looks at a downscaled copy and the file is renamed to
  `<description>_<date>_<time>.png`; the card's title shows the new name. If the
  CLI is missing or fails, the original name is kept.
- The preview does not take keyboard focus. Dragging copies the file; it never
  moves or deletes the original. Images keep their original captured resolution.

Install (or reinstall) for the current user:

```sh
/usr/bin/python3 install.py
```

Launch from the application menu as **Snap Corner**, or use the shortcuts.
It starts silently at login, uses one shared process, and remains available to
serve the image clipboard after the thumbnail closes. Running `snap-corner`
defaults to area capture. Options: `--area`, `--screen`, `--background`, `--quit`.

Remove the launcher, shortcuts, and login entry; keep screenshots and source:

```sh
/usr/bin/python3 install.py --uninstall
```

The installer preserves other shortcuts. Original values for its two shortcut
slots are saved in the user's local share directory and restored on uninstall.
Screenshots are saved with owner-only file permissions. Only edited images are
sent anywhere: a downscaled copy goes to Claude Haiku for naming.

The capture backend requires an X11 session; Wayland capture is not implemented.

## Verification

For tests that leave the real desktop untouched, run:

```sh
/usr/bin/python3 verify_isolated.py
```

This requires `Xvfb`, `xdotool`, and `xrandr`. An extracted Xvfb executable can
also be supplied with `--xvfb /path/to/Xvfb`. The runner creates its own display,
D-Bus session, home, clipboard, and screenshot directory, and removes them on
exit. Its private bus does not auto-start other desktop applications.

The checks exercise real X11 input and separate GTK processes: frozen capture
pixels, reverse selection, cancellation, repeated commands, file and PNG drag
formats, clipboard persistence, private PNG files, preview placement, hover and
drag pauses, dismissal, and process shutdown. The lifetime checks take roughly
two minutes. GTK may expose only one active monitor on Xvfb, even when RandR
lists two logical monitors; this is printed in the test output.

Virtual tests invoke capture commands directly. They do not establish that the
real GNOME shortcuts work, that actual dual-monitor geometry is correct, or that
the tool can be operated from a locked desktop. The separate `verify_desktop.py`
script uses the real mouse and keyboard and is only for an explicitly available,
unlocked, idle desktop with the original two 1920×1080 monitors.
