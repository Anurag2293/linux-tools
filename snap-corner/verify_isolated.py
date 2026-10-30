#!/usr/bin/python3
"""Black-box GTK/X11 checks on a private virtual display, bus, and home.

Usage: /usr/bin/python3 verify_isolated.py [--xvfb /path/to/Xvfb]
Never sends input to the real desktop. Requires Xvfb, xrandr, and xdotool.
"""
import argparse
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parent


def outside(xvfb):
    if not xvfb:
        raise SystemExit("Xvfb is required; provide --xvfb or install xvfb.")
    with tempfile.TemporaryDirectory(prefix="snap-corner-isolated-") as directory:
        root = Path(directory)
        home = root / "home"
        home.mkdir()
        runtime = root / "run"
        runtime.mkdir(mode=0o700)
        env = dict(os.environ)
        for name in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "SESSION_MANAGER",
                     "WAYLAND_DISPLAY", "GDK_BACKEND", "GDK_SCALE", "GDK_DPI_SCALE"):
            env.pop(name, None)
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_DATA_HOME=str(home / ".local/share"), XDG_CACHE_HOME=str(home / ".cache"),
                   XDG_RUNTIME_DIR=str(runtime), XDG_SESSION_TYPE="x11", GDK_BACKEND="x11",
                   NO_AT_BRIDGE="1", GTK_USE_PORTAL="0", GIO_USE_VFS="local",
                   GSETTINGS_BACKEND="memory", XDG_CURRENT_DESKTOP="SnapCornerTest",
                   SNAP_CORNER_ISOLATED="1")
        # A private bus with no service directories prevents unrelated desktop
        # daemons (portals, file managers, keyrings) from being auto-started.
        bus_config = root / "dbus.conf"
        bus_config.write_text('''<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth>
<policy context="default"><allow send_destination="*"/><allow receive_sender="*"/>
<allow own="*"/></policy></busconfig>''')
        read_fd, write_fd = os.pipe()
        with (root / "xvfb.log").open("w+") as log:
            server = subprocess.Popen([xvfb, "-displayfd", str(write_fd), "-screen", "0",
                                       "3840x1080x24", "-nolisten", "tcp", "-noreset"],
                                      pass_fds=(write_fd,), env=env, stdout=log, stderr=log)
            os.close(write_fd)
            try:
                if not select.select([read_fd], [], [], 10)[0]:
                    raise RuntimeError("Xvfb did not start")
                number = os.read(read_fd, 64).decode().strip()
                if not number.isdigit() or number == "0":
                    log.seek(0)
                    raise RuntimeError("Invalid virtual display: " + number + "\n" + log.read())
                env["DISPLAY"] = ":" + number
                print("ISOLATION: display={}, private HOME, private D-Bus; no real desktop input".format(
                    env["DISPLAY"]), flush=True)
                result = subprocess.run(["dbus-run-session", "--config-file=" + str(bus_config),
                                         "--", "/usr/bin/python3", str(__file__),
                                         "--inside"], env=env)
                return result.returncode
            finally:
                os.close(read_fd)
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


def inside():
    if os.environ.get("SNAP_CORNER_ISOLATED") != "1" or os.environ.get("DISPLAY") in (None, ":0", ":0.0"):
        raise SystemExit("Refusing to test outside the isolated runner")
    def run(*args):
        return subprocess.run(list(map(str, args)), check=True, capture_output=True, text=True,
                              timeout=15).stdout.strip()

    run("xrandr", "--setmonitor", "LEFT", "1920/508x1080/286+0+0", "screen")
    run("xrandr", "--setmonitor", "RIGHT", "1920/508x1080/286+1920+0", "none")
    # GTK caches monitors when its display first opens: configure RandR first.
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkX11", "3.0")
    from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk
    from urllib.parse import unquote, urlparse
    display = Gdk.Display.get_default()
    print("MONITORS: " + run("xrandr", "--listmonitors").replace("\n", " | "), flush=True)
    monitors = [display.get_monitor(i).get_geometry() for i in range(display.get_n_monitors())]
    print("GTK monitors: " + str([(r.x, r.y, r.width, r.height) for r in monitors]), flush=True)

    def pump(seconds=0.08):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            time.sleep(0.01)

    def wait(predicate, description, timeout=6):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            value = predicate()
            if value:
                return value
            pump(0.035)
        raise AssertionError("Timed out: " + description)

    def find(title):
        result = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "^" + title + "$"],
                                capture_output=True, text=True)
        return result.stdout.splitlines() if result.returncode == 0 else []

    def geo(window):
        return {k: int(v) for k, v in
                (line.split("=", 1) for line in run("xdotool", "getwindowgeometry", "--shell", window).splitlines())}

    def preview():
        return wait(lambda: find("Snap Corner — preview"), "preview")[0]

    def selector():
        return wait(lambda: find("Snap Corner — select area"), "area selection")[0]

    def invoke(mode="--area"):
        run("/usr/bin/python3", SOURCE / "snap_corner.py", mode)

    def move(x, y):
        run("xdotool", "mousemove", x, y)
        pump()

    def key(chord):
        run("xdotool", "key", chord)
        pump()

    def start_drag(start, end):
        move(*start)
        run("xdotool", "mousedown", "1")
        for step in range(1, 17):
            run("xdotool", "mousemove", round(start[0] + (end[0] - start[0]) * step / 16),
                round(start[1] + (end[1] - start[1]) * step / 16))
            pump(0.02)
        pump(0.15)

    def drag(start, end):
        start_drag(start, end)
        run("xdotool", "mouseup", "1")
        pump(0.15)

    folder = Path.home() / "Pictures/Screenshots"

    def files():
        return set(folder.glob("*.png"))

    def captured(previous, size):
        preview()
        new = files() - previous
        assert len(new) == 1, new
        path = new.pop()
        image = GdkPixbuf.Pixbuf.new_from_file(str(path))
        assert (image.get_width(), image.get_height()) == size
        assert path.stat().st_mode & 0o777 == 0o600
        assert not list(folder.glob(".snap-*"))
        return path, image

    def close_preview():
        g = geo(preview())
        move(g["X"] + g["WIDTH"] - 32, g["Y"] + 26)
        run("xdotool", "click", "1")
        wait(lambda: not find("Snap Corner — preview"), "dismiss preview")

    app_log = (Path.home() / "app.log").open("w+")
    app = subprocess.Popen(["/usr/bin/python3", str(SOURCE / "snap_corner.py"), "--background"],
                           stdout=app_log, stderr=app_log)
    windows = []
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        def owns_name():
            return bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                 "NameHasOwner", GLib.Variant("(s)", ("com.anurag.SnapCorner",)),
                                 None, Gio.DBusCallFlags.NONE,
                                 2000, None).unpack()[0]
        wait(owns_name, "application bus registration")
        patch = Gtk.Window(title="Isolated pattern")
        patch.move(320, 210)
        patch.set_default_size(500, 360)
        canvas = Gtk.DrawingArea()
        color = [0.12, 0.48, 0.82]
        canvas.connect("draw", lambda w, cr: (cr.set_source_rgb(*color), cr.paint(), False)[-1])
        patch.add(canvas)
        patch.show_all()
        windows.append(patch)
        receiver = Gtk.Window(title="Isolated drop target")
        receiver.move(2500, 240)
        receiver.set_default_size(420, 300)
        receiver.add(Gtk.Label(label="PNG drop target"))
        received = []
        accept_drop = [True]
        def receive(widget, context, x, y, selection, info, timestamp):
            if info == 0:
                received.append(("uri", selection.get_uris()))
            else:
                image = selection.get_pixbuf()
                received.append(("png", (image.get_width(), image.get_height()) if image else None))
            Gtk.drag_finish(context, accept_drop[0], False, timestamp)
        def request_drop(widget, context, x, y, timestamp):
            target = widget.drag_dest_find_target(context, None)
            if target is None:
                return False
            widget.drag_get_data(context, target, timestamp)
            return True
        # Handle completion ourselves; DestDefaults.DROP would also finish the
        # transfer and could override a deliberately rejected test drop.
        drop_defaults = Gtk.DestDefaults.MOTION | Gtk.DestDefaults.HIGHLIGHT
        receiver.drag_dest_set(drop_defaults, [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
        receiver.connect("drag-drop", request_drop)
        receiver.connect("drag-data-received", receive)
        receiver.show_all()
        windows.append(receiver)
        pump(0.3)
        pg = geo(find("Isolated pattern")[0])
        start = pg["X"] + 45, pg["Y"] + 70
        end = start[0] + 240, start[1] + 130
        run("xdotool", "windowfocus", patch.get_window().get_xid())
        focused = run("xdotool", "getwindowfocus")
        previous = files()
        invoke()
        assert geo(selector())["WIDTH"] == 3840
        color[:] = [0.8, 0.2, 0.1]
        canvas.queue_draw()
        pump()
        drag(start, end)
        path, image = captured(previous, (240, 130))
        assert tuple(image.get_pixels()[:3]) == (30, 122, 209)
        assert run("xdotool", "getwindowfocus") == focused, "Preview stole focus"
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        copied = clipboard.wait_for_image()
        assert (copied.get_width(), copied.get_height()) == (240, 130)
        g = geo(preview())
        expected = display.get_monitor_at_point(*start).get_workarea()
        assert g["X"] + g["WIDTH"] == expected.x + expected.width - 22, g
        assert g["Y"] + g["HEIGHT"] == expected.y + expected.height - 22, g
        print("PASS: area capture, frozen pixels, private complete PNG, bottom-right placement, focus, clipboard", flush=True)

        rg = geo(find("Isolated drop target")[0])
        target = rg["X"] + 200, rg["Y"] + 150
        source = g["X"] + g["WIDTH"] // 2, g["Y"] + 100
        drag(source, target)
        wait(lambda: received, "file URI drag/drop")
        assert received[0][0] == "uri" and len(received[0][1]) == 1
        assert Path(unquote(urlparse(received[0][1][0]).path)) == path
        wait(lambda: not find("Snap Corner — preview"), "accepted file drop dismisses preview", timeout=1)
        assert path.exists() and clipboard.wait_for_image().get_width() == 240

        previous = files()
        invoke()
        selector()
        drag(start, end)
        captured(previous, (240, 130))
        receiver.drag_dest_set(drop_defaults, [Gtk.TargetEntry.new("image/png", 0, 1)], Gdk.DragAction.COPY)
        drag(source, target)
        wait(lambda: len(received) == 2, "image PNG drag/drop")
        assert received[1] == ("png", (240, 130))
        wait(lambda: not find("Snap Corner — preview"), "accepted PNG drop dismisses preview", timeout=1)
        assert clipboard.wait_for_image().get_width() == 240
        print("PASS: accepted file and PNG drops dismiss immediately; saved PNG and clipboard remain", flush=True)

        previous = files()
        invoke()
        selector()
        drag(start, end)
        path, _ = captured(previous, (240, 130))
        accept_drop[0] = False
        drag(source, target)
        wait(lambda: len(received) == 3, "rejected PNG drop")
        pump(0.8)
        assert find("Snap Corner — preview") and path.exists()
        start_drag(source, (100, 100))
        key("Escape")
        run("xdotool", "mouseup", "1")
        pump(0.8)
        assert find("Snap Corner — preview") and len(received) == 3, (find("Snap Corner — preview"), received)
        accept_drop[0] = True
        close_preview()
        assert clipboard.wait_for_image().get_width() == 240
        print("PASS: rejected and cancelled drags retain the preview; manual dismissal preserves clipboard", flush=True)

        for cancel in ("Escape", "right-click", "tiny"):
            previous = files()
            invoke()
            selector()
            if cancel == "Escape":
                key("Escape")
            elif cancel == "right-click":
                run("xdotool", "click", "3")
            else:
                drag(start, (start[0] + 1, start[1] + 1))
            wait(lambda: not find("Snap Corner — select area"), "cancel selection")
            assert files() == previous and not find("Snap Corner — preview")
        previous = files()
        invoke()
        selector()
        invoke()
        selector()
        assert len(find("Snap Corner — select area")) == 1
        drag(end, start)
        captured(previous, (240, 130))
        close_preview()
        print("PASS: Escape, right-click, tiny selection, reverse selection, repeated area invocation", flush=True)

        for x in (600, 2300):
            previous = files()
            move(x, 400)
            invoke("--screen")
            monitor = display.get_monitor_at_point(x, 400)
            bounds = monitor.get_geometry()
            captured(previous, (bounds.width, bounds.height))
            g = geo(preview())
            work = monitor.get_workarea()
            assert g["X"] + g["WIDTH"] == work.x + work.width - 22
            close_preview()
        print("PASS: screen capture dimensions and preview on the pointer's virtual monitor", flush=True)

        previous = files()
        invoke("--screen")
        invoke("--area")
        selector()
        key("Escape")
        assert files() == previous, "Pending screen request was not replaced"
        bad = subprocess.run(["/usr/bin/python3", str(SOURCE / "snap_corner.py"), "--invalid"],
                             capture_output=True, text=True, timeout=5)
        assert bad.returncode == 2 and "Usage:" in bad.stdout, (bad.returncode, bad.stdout, bad.stderr)
        print("PASS: pending request replacement and command-line validation", flush=True)

        invoke("--area")
        selector()
        drag(start, end)
        g = geo(preview())
        source = g["X"] + g["WIDTH"] // 2, g["Y"] + 100
        move(*source)
        print("CHECKING: preview remains while hovered for over 30 seconds", flush=True)
        pump(31.5)
        assert find("Snap Corner — preview"), "Preview expired while hovered"
        start_drag(source, target)
        print("CHECKING: preview remains during a drag for over 30 seconds", flush=True)
        pump(31.5)
        assert find("Snap Corner — preview"), "Preview expired during drag"
        run("xdotool", "mouseup", "1")
        wait(lambda: len(received) == 4, "long drag finishes")
        wait(lambda: not find("Snap Corner — preview"), "accepted long drop dismisses immediately", timeout=1)
        invoke("--area")
        selector()
        drag(start, end)
        preview()
        move(100, 100)
        print("CHECKING: preview dismisses after leaving; PNG and clipboard remain", flush=True)
        saved = files()
        wait(lambda: not find("Snap Corner — preview"), "30-second preview expiration", timeout=33)
        assert files() == saved and clipboard.wait_for_image().get_width() == 240
        print("PASS: hover pause, drag pause, 30-second dismissal, persistent file and clipboard", flush=True)
        app_log.flush()
        app_log.seek(0)
        log = app_log.read()
        assert "Traceback" not in log and "Snap Corner:" not in log, log
        print("PASS: application log contains no runtime errors", flush=True)
        invoke("--quit")
        assert app.wait(timeout=5) == 0
        bad = subprocess.run(["/usr/bin/python3", str(SOURCE / "snap_corner.py"), "--invalid"],
                             capture_output=True, text=True, timeout=5)
        assert bad.returncode == 2 and "Usage:" in bad.stdout, (bad.returncode, bad.stdout, bad.stderr)
        print("PASS: clean quit and invalid initial command exits without leaving a resident process", flush=True)
        print("LIMIT: virtual-display results do not verify real GNOME global shortcuts or a locked real session.", flush=True)
    finally:
        if app.poll() is None:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait()
        for window in windows:
            window.destroy()
        app_log.seek(0)
        print("APPLICATION LOG:\n" + app_log.read(), flush=True)
        app_log.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xvfb", default=shutil.which("Xvfb"))
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    raise SystemExit(inside() if args.inside else outside(args.xvfb))
