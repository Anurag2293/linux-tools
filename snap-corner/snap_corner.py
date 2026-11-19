#!/usr/bin/python3
"""Native GNOME/X11 screenshots with a draggable, file-backed thumbnail."""

import datetime
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gdk, GdkPixbuf, GdkX11, Gio, GLib, Gtk, Pango

from editor import Editor


APP_ID = "com.anurag.SnapCorner"
MODES = ("--area", "--screen", "--background", "--quit")
STACK_GAP = 10
NAMING_PROMPT = ("Read image.png in the current directory. Reply with only a short descriptive "
                 "file name for it: 3 to 7 lowercase words joined by hyphens that say what the "
                 "picture shows, no extension, nothing else.")
USAGE = "Usage: snap-corner [--area|--screen|--background|--quit]"
CSS = b"""
#snap-card { background: #20232b; color: #f4f4f5; border-radius: 12px;
             border: 1px solid #555966; padding: 10px; }
#snap-card label { color: #f4f4f5; }
#snap-card .hint { color: #bec3cf; font-size: 11px; }
#snap-card .title { font-size: 12px; }
#snap-card button { background: #343945; color: #f4f4f5; border: none;
                    box-shadow: none; text-shadow: none; border-radius: 6px;
                    padding: 4px 10px; min-height: 22px; }
#snap-card button:hover { background: #4a5263; }
"""


def image_fit(image, width, height):
    factor = min(width / image.get_width(), height / image.get_height(), 1)
    return image.scale_simple(max(1, round(image.get_width() * factor)),
                              max(1, round(image.get_height() * factor)),
                              GdkPixbuf.InterpType.BILINEAR)


def close_shell_popups():
    try:
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            "org.gnome.Shell", "/com/anurag/SnapCorner", "com.anurag.SnapCorner.Shell",
            "ClosePopups", None, None, Gio.DBusCallFlags.NONE, 1000, None)
    except GLib.Error:
        pass


class Selection(Gtk.Window):
    def __init__(self, app, snapshot, root_width, root_height):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.app = app
        self.snapshot = snapshot
        self.root_width, self.root_height = root_width, root_height
        self.origin = None
        self.pointer = (0, 0)
        self.seat = None
        self.set_title("Snap Corner — select area")
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.move(0, 0)
        self.set_default_size(root_width, root_height)
        app.add_window(self)
        self.canvas = Gtk.DrawingArea()
        self.add(self.canvas)
        self.canvas.connect("draw", self.draw)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("button-press-event", self.press)
        self.connect("motion-notify-event", self.motion)
        self.connect("button-release-event", self.release)
        self.connect("key-press-event", self.key)
        self.connect("destroy", self.on_destroy)
        self.show_all()
        window = self.get_window()
        window.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "crosshair"))
        self.attempts = 0
        if not self.grab():
            # A Shell menu (e.g. the notification list) owns input; close it and retry.
            close_shell_popups()
            GLib.timeout_add(50, self.retry_grab)

    def grab(self):
        seat = self.get_display().get_default_seat()
        result = seat.grab(self.get_window(), Gdk.SeatCapabilities.POINTER |
                           Gdk.SeatCapabilities.KEYBOARD, False, None, None, None)
        if result == Gdk.GrabStatus.SUCCESS:
            self.seat = seat
        return self.seat is not None

    def retry_grab(self):
        if self.app.selector is not self or self.grab():
            return False
        self.attempts += 1
        if self.attempts < 30:
            return True
        self.destroy()
        self.app.report_error(RuntimeError("Desktop input is busy. Close open menus and try again."))
        return False

    def rectangle(self):
        x0, y0 = self.origin
        x1, y1 = self.pointer
        left = max(0, min(self.root_width, math.floor(min(x0, x1))))
        top = max(0, min(self.root_height, math.floor(min(y0, y1))))
        right = max(0, min(self.root_width, math.ceil(max(x0, x1))))
        bottom = max(0, min(self.root_height, math.ceil(max(y0, y1))))
        return left, top, right - left, bottom - top

    def draw(self, widget, cr):
        sx = self.root_width / self.snapshot.get_width()
        sy = self.root_height / self.snapshot.get_height()
        cr.save()
        cr.scale(sx, sy)
        Gdk.cairo_set_source_pixbuf(cr, self.snapshot, 0, 0)
        cr.paint()
        cr.restore()
        cr.set_source_rgba(0, 0, 0, 0.43)
        cr.rectangle(0, 0, self.root_width, self.root_height)
        if self.origin:
            x, y, w, h = self.rectangle()
            cr.rectangle(x, y, w, h)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.fill()
        if self.origin:
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1)
            cr.rectangle(x + 0.5, y + 0.5, max(0, w - 1), max(0, h - 1))
            cr.stroke()
            text = "{} × {}".format(round(w / sx), round(h / sy))
            self.caption(cr, text, min(x + 8, self.root_width - 180), max(34, y - 10))
        else:
            _, px, py = self.get_display().get_default_seat().get_pointer().get_position()
            monitor = self.get_display().get_monitor_at_point(px, py).get_geometry()
            self.caption(cr, "Drag to capture · Esc to cancel · Right-click to cancel",
                         monitor.x + 36, monitor.y + 64)
        return False

    @staticmethod
    def caption(cr, text, x, y):
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(16)
        width = cr.text_extents(text)[4]
        cr.set_source_rgba(0.08, 0.09, 0.12, 0.94)
        cr.rectangle(x - 10, y - 23, width + 20, 34)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x, y)
        cr.show_text(text)

    def press(self, widget, event):
        if event.button == 3:
            self.destroy()
        elif event.button == 1:
            self.origin = (event.x_root, event.y_root)
            self.pointer = self.origin
            self.canvas.queue_draw()
        return True

    def motion(self, widget, event):
        self.pointer = (event.x_root, event.y_root)
        self.canvas.queue_draw()
        return True

    def release(self, widget, event):
        if event.button != 1 or self.origin is None:
            return True
        self.pointer = (event.x_root, event.y_root)
        rect = self.rectangle()
        self.destroy()
        if rect[2] >= 3 and rect[3] >= 3:
            self.app.finish_capture(self.snapshot, rect, self.root_width, self.root_height)
        return True

    def key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
        return True

    def on_destroy(self, widget):
        if self.seat:
            self.seat.ungrab()
            self.seat = None
        if self.app.selector is self:
            self.app.selector = None
            self.app.show_previews()


class Thumbnail(Gtk.Window):
    def __init__(self, app, path, image, monitor, title="Screenshot saved"):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app, self.path, self.image = app, path, image
        self.monitor = monitor
        self.dragging = False
        self.drag_started = False
        self.drop_failed = False
        self.uri_exported = False
        self.timer = 0
        self.set_title("Snap Corner — preview")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.stick()
        app.add_window(self)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.connect("draw", self.clear_background)
        frame = Gtk.EventBox()
        frame.set_name("snap-card")
        frame.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        frame.connect("enter-notify-event", self.enter)
        frame.connect("leave-notify-event", self.leave)
        self.add(frame)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        frame.add(box)
        header = Gtk.Box(spacing=8)
        self.title = Gtk.Label(label=title, xalign=0)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.title.set_max_width_chars(28)
        self.title.get_style_context().add_class("title")
        header.pack_start(self.title, True, True, 0)
        close = Gtk.Button(label="×")
        close.set_tooltip_text("Dismiss preview; the saved screenshot is kept")
        close.connect("clicked", lambda _: self.destroy())
        header.pack_end(close, False, False, 0)
        box.pack_start(header, False, False, 0)
        self.drag_surface = Gtk.EventBox()
        self.small_image = image_fit(image, 288, 170)
        self.drag_surface.add(Gtk.Image.new_from_pixbuf(self.small_image))
        self.drag_surface.set_tooltip_text("Drag into a chat or another app · Click to edit")
        self.drag_surface.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                                     Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.drag_surface.connect("realize", lambda w: w.get_window().set_cursor(
            Gdk.Cursor.new_from_name(w.get_display(), "pointer")))
        self.drag_surface.connect("button-press-event", self.press)
        self.drag_surface.connect("button-release-event", self.release)
        self.drag_surface.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,
                                         [Gtk.TargetEntry.new("text/uri-list", 0, 0),
                                          Gtk.TargetEntry.new("image/png", 0, 1)],
                                         Gdk.DragAction.COPY)
        self.drag_surface.connect("drag-data-get", self.drag_data)
        self.drag_surface.connect("drag-begin", self.drag_begin)
        self.drag_surface.connect("drag-failed", self.drag_failed)
        self.drag_surface.connect("drag-end", self.drag_end)
        box.pack_start(self.drag_surface, False, False, 0)
        self.hint = Gtk.Label(label="Drag into an app · Click to edit · Copied")
        self.hint.get_style_context().add_class("hint")
        box.pack_start(self.hint, False, False, 0)
        actions = Gtk.Box(spacing=6)
        for title, action in (("Edit", self.edit), ("Copy", self.copy), ("Open", self.open),
                              ("Folder", self.folder)):
            button = Gtk.Button(label=title)
            button.connect("clicked", action)
            actions.pack_start(button, True, True, 0)
        box.pack_start(actions, False, False, 0)
        self.connect("size-allocate", lambda *a: app.layout())
        self.connect("destroy", self.cleanup)
        self.show_all()
        self.arm_timer()

    def clear_background(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        return False

    def cancel_timer(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def arm_timer(self):
        self.cancel_timer()
        if not self.app.hovered and not self.app.editing_on(self.monitor) and not self.dragging:
            self.timer = GLib.timeout_add_seconds(30, self.expire)

    def expire(self):
        self.timer = 0
        self.destroy()
        return False

    def enter(self, widget, event):
        self.app.set_hovered(True)
        return False

    def leave(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.app.set_hovered(False)
        return False

    def press(self, widget, event):
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.drag_started = False
        return False

    def release(self, widget, event):
        if event.button == 1 and not self.drag_started and not self.dragging:
            self.edit(timestamp=event.time)
        return False

    def edit(self, *args, timestamp=Gdk.CURRENT_TIME):
        self.app.edit(self.image, self.monitor, timestamp)

    def copy(self, *args):
        self.app.copy_image(self.image)
        self.hint.set_text("Copied · Paste with Ctrl+V")
        self.arm_timer()

    def open(self, *args):
        self.app.open_uri(self.path.as_uri())

    def folder(self, *args):
        self.app.open_uri(self.path.parent.as_uri())

    def drag_data(self, widget, context, selection, info, timestamp):
        if info == 0:
            self.uri_exported = True
            selection.set_uris([self.path.as_uri()])
        else:
            selection.set_pixbuf(self.image)

    def drag_begin(self, widget, context):
        self.dragging = True
        self.drag_started = True
        self.drop_failed = False
        self.cancel_timer()
        Gtk.drag_set_icon_pixbuf(context, image_fit(self.image, 160, 100), 24, 24)

    def drag_failed(self, widget, context, result):
        self.drop_failed = True
        return False

    def drag_end(self, widget, context):
        self.dragging = False
        # Cancelled drags have no drop result; GTK reports them via drag-failed.
        if not self.drop_failed and Gdk.drag_drop_succeeded(context):
            self.destroy()
        else:
            self.arm_timer()

    def cleanup(self, *args):
        self.cancel_timer()
        if self in self.app.previews:
            self.app.previews.remove(self)
            if self.app.hovered and not self.app.previews:
                self.app.hovered = False
            self.app.layout()


class SnapCorner(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.selector = None
        self.previews = []
        self.editors = []
        self.hovered = False
        self.pending = 0
        self.held = False

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_command_line(self, command):
        args = command.get_arguments()[1:]
        mode = args[0] if args else "--area"
        if len(args) > 1 or mode not in MODES:
            print(USAGE, file=sys.stderr, flush=True)
            return 2
        if mode == "--quit":
            self.quit()
            return 0
        if not self.held:
            # Own the clipboard after dismissal, but let invalid initial commands exit.
            self.hold()
            self.held = True
        if mode != "--background":
            if self.selector:
                self.selector.destroy()
            # Keep the stack out of the frozen desktop image; it returns after capture.
            for card in self.previews:
                card.hide()
            self.set_hovered(False)
            if self.pending:
                GLib.source_remove(self.pending)
            # Let the shortcut modifiers and compositor settle before grabbing input.
            self.pending = GLib.timeout_add(220, self.capture, mode)
        return 0

    def capture(self, mode):
        self.pending = 0
        try:
            display = Gdk.Display.get_default()
            if not isinstance(display, GdkX11.X11Display):
                raise RuntimeError("Snap Corner requires an X11 desktop session.")
            root = Gdk.get_default_root_window()
            width, height = root.get_width(), root.get_height()
            snapshot = Gdk.pixbuf_get_from_window(root, 0, 0, width, height)
            if snapshot is None:
                raise RuntimeError("The desktop could not be captured.")
            if mode == "--area":
                self.selector = Selection(self, snapshot, width, height)
            else:
                _, x, y = display.get_default_seat().get_pointer().get_position()
                area = display.get_monitor_at_point(x, y).get_geometry()
                self.finish_capture(snapshot, (area.x, area.y, area.width, area.height),
                                    width, height)
                self.show_previews()
        except Exception as exc:
            self.show_previews()
            self.report_error(exc)
        return False

    def editing_on(self, monitor):
        return any(editor.monitor == monitor for editor in self.editors)

    def show_previews(self):
        if self.selector:
            return
        for card in self.previews:
            if not self.editing_on(card.monitor):
                card.show()
        self.layout()

    def add_preview(self, card):
        self.previews.append(card)
        if self.editing_on(card.monitor):
            card.hide()
        self.layout()

    def layout(self):
        """Stack cards upward from each monitor's bottom-right corner, newest at the bottom."""
        bottoms = {}
        overflow = []
        for card in reversed(self.previews):
            if not card.get_visible():
                continue
            area = card.monitor.get_workarea()
            key = (area.x, area.y, area.width, area.height)
            width, height = card.get_size()
            bottom = bottoms.get(key, area.y + area.height - 22)
            top = bottom - height
            if top < area.y + 22 and bottom != area.y + area.height - 22:
                overflow.append(card)
                continue
            card.move(max(area.x, area.x + area.width - width - 22), max(area.y, top))
            bottoms[key] = top - STACK_GAP
        for card in overflow:
            card.destroy()

    def set_hovered(self, hovered):
        self.hovered = hovered
        for card in self.previews:
            card.arm_timer()

    @staticmethod
    def save_png(image, path):
        # Publish only a complete PNG so folder watchers never see a partial file.
        with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix=".snap-", delete=False) as out:
            temporary = Path(out.name)
        try:
            image.savev(str(temporary), "png", [], [])
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def pictures():
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        return Path(pictures or str(Path.home() / "Pictures"))

    def edit(self, image, monitor, timestamp):
        try:
            editor = Editor(image, monitor, lambda edited: self.save_edit(edited, monitor),
                            self.copy_image, timestamp)
        except Exception as exc:
            self.report_error(exc)
            return
        editor.monitor = monitor
        self.editors.append(editor)
        editor.connect("destroy", self.editor_closed)
        self.set_hovered(False)
        for card in self.previews:
            if card.monitor == monitor:
                card.hide()

    def editor_closed(self, editor):
        self.editors.remove(editor)
        self.show_previews()
        self.set_hovered(False)

    def save_edit(self, image, monitor):
        try:
            folder = self.pictures()
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = folder / "edited_{}.png".format(stamp)
            counter = 2
            while path.exists():
                path = folder / "edited_{}-{}.png".format(stamp, counter)
                counter += 1
            self.save_png(image, path)
            self.copy_image(image)
            card = Thumbnail(self, path, image, monitor, title="Edited · naming…")
            self.add_preview(card)
            print("Saved {} ({}x{})".format(path, image.get_width(), image.get_height()),
                  flush=True)
            self.name_with_haiku(card, image, stamp)
            return True
        except Exception as exc:
            self.report_error(exc)
            return False

    def name_with_haiku(self, card, image, stamp):
        claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
        work = Path(tempfile.mkdtemp(prefix="snap-corner-name-"))
        path = card.path

        def done(name):
            shutil.rmtree(str(work), ignore_errors=True)
            final = path
            if name and path.exists() and not card.uri_exported:
                target = path.with_name("{}_{}.png".format(name, stamp))
                counter = 2
                while target.exists():
                    target = path.with_name("{}_{}-{}.png".format(name, stamp, counter))
                    counter += 1
                path.rename(target)
                final = target
                print("Renamed {} -> {}".format(path.name, target.name), flush=True)
            if card in self.previews:
                card.path = final
                card.title.set_text(final.name)
                card.title.set_tooltip_text(str(final))

        def finished(process, result):
            try:
                ok, stdout, stderr = process.communicate_utf8_finish(result)
                lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
                name = re.sub(r"[^a-z0-9]+", "-", lines[-1].lower()).strip("-")[:70] if lines else ""
                if not process.get_successful() or not name:
                    print("Snap Corner: naming failed: {}".format((stderr or "").strip()[:300]),
                          file=sys.stderr, flush=True)
                    name = ""
            except GLib.Error as exc:
                print("Snap Corner: naming failed: {}".format(exc), file=sys.stderr, flush=True)
                name = ""
            done(name.strip("-"))

        try:
            image_fit(image, 1280, 1280).savev(str(work / "image.png"), "png", [], [])
            launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDIN_PIPE |
                                                  Gio.SubprocessFlags.STDOUT_PIPE |
                                                  Gio.SubprocessFlags.STDERR_PIPE)
            launcher.set_cwd(str(work))
            process = launcher.spawnv([claude, "-p", "--model", "haiku", "--tools", "Read",
                                       "--allowedTools", "Read", "--strict-mcp-config",
                                       "--no-session-persistence", "--disable-slash-commands",
                                       NAMING_PROMPT])
            cancel = Gio.Cancellable()
            GLib.timeout_add_seconds(120, lambda: (cancel.cancel(), process.force_exit(), False)[-1])
            process.communicate_utf8_async(None, cancel, finished)
        except (GLib.Error, OSError) as exc:
            print("Snap Corner: naming failed: {}".format(exc), file=sys.stderr, flush=True)
            done("")

    def finish_capture(self, snapshot, rect, root_width, root_height):
        try:
            x, y, w, h = rect
            sx, sy = snapshot.get_width() / root_width, snapshot.get_height() / root_height
            left, top = round(x * sx), round(y * sy)
            right, bottom = round((x + w) * sx), round((y + h) * sy)
            image = snapshot.new_subpixbuf(left, top, right - left, bottom - top).copy()
            folder = self.pictures() / "Screenshots"
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d at %H.%M.%S.%f")
            path = folder / ("Screenshot " + stamp + ".png")
            self.save_png(image, path)
            self.copy_image(image)
            display = Gdk.Display.get_default()
            monitor = display.get_monitor_at_point(x + w // 2, y + h // 2)
            self.add_preview(Thumbnail(self, path, image, monitor))
            print("Saved {} ({}x{})".format(path, image.get_width(), image.get_height()),
                  flush=True)
        except Exception as exc:
            self.report_error(exc)

    @staticmethod
    def copy_image(image):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_image(image)
        clipboard.set_can_store(None)

    def open_uri(self, uri):
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error as exc:
            self.report_error(exc)

    def report_error(self, exc):
        print("Snap Corner: {}".format(exc), file=sys.stderr, flush=True)
        notification = Gio.Notification.new("Snap Corner")
        notification.set_body(str(exc))
        self.send_notification("capture-error", notification)


if __name__ == "__main__":
    os.umask(0o077)
    # Validate locally, before forwarding to a resident instance. PyGObject does
    # not expose Gio's variadic print method for replying to a remote command.
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] not in MODES):
        print(USAGE)
        raise SystemExit(2)
    raise SystemExit(SnapCorner().run(sys.argv))
