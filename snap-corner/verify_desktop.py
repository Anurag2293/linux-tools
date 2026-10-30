#!/usr/bin/python3
"""Exercise real X11 input, capture pixels, clipboard, and cross-window DND.

Run on an idle desktop: briefly uses the pointer and opens two test windows.
Only screenshots created during this run are removed afterwards.
"""
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import unquote, urlparse

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

LAUNCHER = str(Path.home() / ".local/bin/snap-corner")
folder = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)) / "Screenshots"
before = set(folder.glob("*.png"))
received = []
windows = []
original_pointer = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()[1:]
original_focus = subprocess.check_output(["xdotool", "getactivewindow"], text=True).strip()


def pump(seconds=0.1):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.01)


def wait(predicate, description, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        pump(0.04)
    raise AssertionError("Timed out: " + description)


def xdo(*args):
    return subprocess.run(["xdotool", *map(str, args)], check=True,
                          text=True, stdout=subprocess.PIPE).stdout.strip()


def find(title):
    result = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "^" + title + "$"],
                            stdout=subprocess.PIPE, text=True)
    return result.stdout.splitlines()[-1] if result.returncode == 0 else None


def geometry(window):
    return {k: int(v) for k, v in
            (line.split("=", 1) for line in xdo("getwindowgeometry", "--shell", window).splitlines())}


def key(chord):
    xdo("key", "--clearmodifiers", chord)
    pump(0.35)


def drag(start, end):
    xdo("mousemove", "--sync", *start)
    xdo("mousedown", 1)
    for step in range(1, 17):
        xdo("mousemove", "--sync", round(start[0] + (end[0] - start[0]) * step / 16),
            round(start[1] + (end[1] - start[1]) * step / 16))
        pump(0.025)
    pump(0.15)
    xdo("mouseup", 1)
    pump(0.2)


def latest_new(previous):
    return wait(lambda: next(iter(set(folder.glob("*.png")) - previous), None), "new screenshot")


def thumbnail():
    return wait(lambda: find("Snap Corner — preview"), "preview")


def close_preview():
    geo = geometry(thumbnail())
    xdo("mousemove", "--sync", geo["X"] + geo["WIDTH"] - 32, geo["Y"] + 26)
    xdo("click", 1)
    wait(lambda: not find("Snap Corner — preview"), "dismiss preview")


try:
    # A known blue patch lets us detect selection-overlay contamination.
    patch = Gtk.Window(title="Snap Corner verification pattern")
    patch.set_default_size(500, 360)
    patch.move(320, 210)
    canvas = Gtk.DrawingArea()
    canvas.connect("draw", lambda w, cr: (cr.set_source_rgb(0.12, 0.48, 0.82), cr.paint(), False)[-1])
    patch.add(canvas)
    patch.show_all()
    windows.append(patch)
    receiver = Gtk.Window(title="Snap Corner verification drop target")
    receiver.set_default_size(420, 300)
    receiver.move(2500, 240)
    label = Gtk.Label(label="Screenshot drag-and-drop verification")
    receiver.add(label)
    windows.append(receiver)

    def receive(widget, context, x, y, selection, info, timestamp):
        if info == 0:
            received.append(("uri", selection.get_uris()))
        else:
            image = selection.get_pixbuf()
            received.append(("png", (image.get_width(), image.get_height()) if image else None))
        Gtk.drag_finish(context, True, False, timestamp)

    receiver.drag_dest_set(Gtk.DestDefaults.ALL,
                           [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
    receiver.connect("drag-data-received", receive)
    receiver.show_all()
    pump(0.5)
    patch_geo = geometry(find("Snap Corner verification pattern"))
    start = (patch_geo["X"] + 45, patch_geo["Y"] + 70)
    end = (start[0] + 240, start[1] + 130)
    xdo("windowactivate", "--sync", patch.get_window().get_xid())
    focus_before = xdo("getactivewindow")
    key("ctrl+alt+s")
    selector = wait(lambda: find("Snap Corner — select area"), "area shortcut")
    assert geometry(selector)["WIDTH"] == Gdk.get_default_root_window().get_width()
    drag(start, end)
    path = latest_new(before)
    image = GdkPixbuf.Pixbuf.new_from_file(str(path))
    assert (image.get_width(), image.get_height()) == (240, 130)
    assert tuple(image.get_pixels()[:3]) == (30, 122, 209), tuple(image.get_pixels()[:3])
    geo = geometry(thumbnail())
    assert geo["X"] < 1920 and geo["Y"] > 650, geo
    assert xdo("getactivewindow") == focus_before, "Preview stole keyboard focus"
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    copied = clipboard.wait_for_image()
    assert (copied.get_width(), copied.get_height()) == (240, 130)
    print("PASS: real area shortcut, exact pixels/dimensions, left-monitor preview, focus, clipboard", flush=True)

    receiver_geo = geometry(find("Snap Corner verification drop target"))
    target = (receiver_geo["X"] + 200, receiver_geo["Y"] + 150)
    source = (geo["X"] + geo["WIDTH"] // 2, geo["Y"] + 100)
    drag(source, target)
    wait(lambda: received, "file URI drop")
    assert received[-1][0] == "uri" and len(received[-1][1]) == 1, received
    dropped = Path(unquote(urlparse(received[-1][1][0]).path))
    assert dropped == path and dropped.exists(), received
    assert path.stat().st_mode & 0o777 == 0o600
    wait(lambda: not find("Snap Corner — preview"), "accepted file drop dismisses preview", timeout=1)
    print("PASS: real drag across monitors delivers the full-resolution PNG file URI", flush=True)

    previous = set(folder.glob("*.png"))
    key("ctrl+alt+s")
    wait(lambda: find("Snap Corner — select area"), "second area selection")
    drag(start, end)
    thumbnail()
    latest_new(previous)
    receiver.drag_dest_set(Gtk.DestDefaults.ALL,
                           [Gtk.TargetEntry.new("image/png", 0, 1)], Gdk.DragAction.COPY)
    drag(source, target)
    wait(lambda: len(received) == 2, "PNG image drop")
    assert received[-1] == ("png", (240, 130)), received
    wait(lambda: not find("Snap Corner — preview"), "accepted PNG drop dismisses preview", timeout=1)
    print("PASS: image-only drop target receives PNG pixel data", flush=True)
    key("ctrl+alt+s")
    wait(lambda: find("Snap Corner — select area"), "manual-dismiss area selection")
    drag(start, end)
    close_preview()
    copied = clipboard.wait_for_image()
    assert copied and copied.get_width() == 240
    print("PASS: dismiss button and clipboard survives dismissal", flush=True)

    previous = set(folder.glob("*.png"))
    key("ctrl+alt+s")
    wait(lambda: find("Snap Corner — select area"), "cancel selection")
    key("Escape")
    assert not find("Snap Corner — select area") and set(folder.glob("*.png")) == previous
    print("PASS: Escape cancels without saving", flush=True)

    for pointer, expected_x in [((2300, 400), 1920), ((600, 400), 0)]:
        previous = set(folder.glob("*.png"))
        xdo("mousemove", "--sync", *pointer)
        key("ctrl+alt+f")
        thumbnail()
        path = latest_new(previous)
        image = GdkPixbuf.Pixbuf.new_from_file(str(path))
        assert (image.get_width(), image.get_height()) == (1920, 1080)
        geo = geometry(thumbnail())
        assert expected_x <= geo["X"] < expected_x + 1920, geo
        close_preview()
    print("PASS: screen shortcut captures only the pointer's monitor on both screens", flush=True)
finally:
    # If verification fails mid-selection, always release the desktop input grab.
    if find("Snap Corner — select area"):
        key("Escape")
    for window in windows:
        window.destroy()
    pump()
    for path in set(folder.glob("*.png")) - before:
        path.unlink()
    xdo("mousemove", "--sync", *original_pointer)
    subprocess.run(["xdotool", "windowactivate", original_focus], check=False)
