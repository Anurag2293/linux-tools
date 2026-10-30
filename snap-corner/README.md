# Snap Corner

A small, native screenshot tool for Ubuntu 20.04 GNOME on X11. Uses the system's
Python 3, PyGObject, GTK 3, and Cairo; no pip packages, browser, or root access.

- **Ctrl+Alt+S**: freeze the desktop, then drag to select an area. Escape or
  right-click cancels.
- **Ctrl+Alt+F**: capture the monitor under the mouse pointer.
- A preview appears at the bottom right of the captured monitor. Drag the
  **picture** into T3 Code's message input, Slack, a file manager, or another app
  that accepts image files. It offers both a PNG file URI and PNG image data.
- Each screenshot is copied to the clipboard for **Ctrl+V**, and saved under
  the Pictures directory's **Screenshots** folder, using unique timestamp names.
- Preview buttons: **Copy**, **Open**, **Folder**, and **×** to dismiss.
- Previews dismiss after 30 seconds. Hovering or dragging pauses dismissal;
  a successful drop dismisses the preview immediately. Cancelled or rejected
  drops keep it available for another 30 seconds. Saved files are kept.
- Taking a new screenshot replaces the preview. The previous PNG remains saved.
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
Screenshots are saved with owner-only file permissions. Nothing is uploaded.

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
