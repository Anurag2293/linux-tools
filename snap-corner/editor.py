"""Annotation editor for Snap Corner: crop, pen, marker, arrow, box, text, pixelate."""

import copy
import math
import shutil
import subprocess

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, GdkX11, GLib, Gtk, Pango, PangoCairo


TOOLS = [("select", "Move", "v", "Select, move, or delete annotations; double-click text to edit"),
         ("crop", "Crop", "c", "Drag the area to keep"),
         ("pen", "Pen", "p", "Freehand drawing"),
         ("marker", "Marker", "m", "Translucent highlighter"),
         ("arrow", "Arrow", "a", "Drag from tail to tip"),
         ("rect", "Box", "r", "Rectangle outline"),
         ("text", "Text", "t", "Click to type; Enter for a new line, Esc or click outside to finish"),
         ("pixelate", "Pixelate", "x", "Hide sensitive content")]
COLORS = [("Red", (0.89, 0.12, 0.14)), ("Orange", (0.96, 0.45, 0.08)),
          ("Yellow", (0.99, 0.82, 0.15)), ("Green", (0.18, 0.72, 0.29)),
          ("Blue", (0.16, 0.47, 0.95)), ("Purple", (0.58, 0.29, 0.86)),
          ("Black", (0.07, 0.07, 0.08)), ("White", (1.0, 1.0, 1.0))]
SIZES = [(2, 16, 6), (4, 22, 10), (7, 30, 16), (12, 44, 24)]
CURSORS = {"select": "default", "crop": "crosshair", "pen": "crosshair", "marker": "crosshair",
           "arrow": "crosshair", "rect": "crosshair", "text": "text", "pixelate": "crosshair"}
HINTS = {"select": "Drag an annotation to move it · Delete removes it · Double-click text to edit",
         "crop": "Drag the area to keep · Ctrl+Z restores",
         "text": "Click to place text · Enter adds a line · Esc finishes"}
CSS = b"""
#snap-editor { background: #111216; }
#snap-editor .topbar { background: #1b1c22; border-bottom: 1px solid #2a2b33; padding: 6px 10px; }
#snap-editor .rail { background: #1b1c22; border-right: 1px solid #2a2b33; padding: 8px 6px; }
#snap-editor .status { color: #8d8f99; padding: 6px 14px; font-size: 11px; }
#snap-editor button { background: transparent; color: #c9cad1; border: none; box-shadow: none;
                      text-shadow: none; -gtk-icon-shadow: none; border-radius: 8px;
                      padding: 4px 8px; min-height: 26px; min-width: 0; }
#snap-editor button:hover { background: rgba(255, 255, 255, 0.08); color: #ffffff; }
#snap-editor button:checked { background: rgba(255, 255, 255, 0.14); color: #ffffff; }
#snap-editor button:disabled { color: #4f515b; }
#snap-editor button.tool { padding: 6px 2px 5px 2px; min-width: 56px; }
#snap-editor button.tool label { font-size: 10px; color: #a9abb4; }
#snap-editor button.tool:hover label { color: #ffffff; }
#snap-editor button.tool:checked { background: #e8590c; }
#snap-editor button.tool:checked label { color: #ffffff; }
#snap-editor button.swatch { padding: 2px; border-radius: 99px; min-height: 0; }
#snap-editor button.swatch:checked { background: transparent; }
#snap-editor button.size { padding: 2px; min-width: 26px; }
#snap-editor button.primary { background: #e8590c; color: #ffffff; font-weight: bold;
                              padding: 4px 16px; }
#snap-editor button.primary:hover { background: #f06d22; }
#snap-editor separator { background: #2f3039; min-width: 1px; min-height: 1px; margin: 6px 8px; }
"""


def luminance(color):
    return 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]


def normalized(a, b):
    return min(a[0], b[0]), min(a[1], b[1]), abs(a[0] - b[0]), abs(a[1] - b[1])


class Editor(Gtk.Window):
    def __init__(self, image, monitor, on_save, on_copy, timestamp=Gdk.CURRENT_TIME):
        super().__init__(title="Snap Corner — edit")
        self.base = image
        self.on_save, self.on_copy = on_save, on_copy
        self.surface = Gdk.cairo_surface_create_from_pixbuf(image, 1, None)
        self.pixelated = {}
        self.state = {"items": [], "crop": (0, 0, image.get_width(), image.get_height())}
        self.undo_stack, self.redo_stack = [], []
        self.tool = "pen"
        self.color = COLORS[0][1]
        self.level = 1
        self.active = None
        self.selected = None
        self.editing = None
        self.editing_new = False
        self.crop_drag = None
        self.moving = None
        self.view = (1.0, 0.0, 0.0)
        self.set_name("snap-editor")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.im = Gtk.IMMulticontext()
        self.im.connect("commit", self.im_commit)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        bar = Gtk.Box(spacing=2)
        bar.get_style_context().add_class("topbar")
        root.pack_start(bar, False, False, 0)
        body = Gtk.Box()
        root.pack_start(body, True, True, 0)
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rail.get_style_context().add_class("rail")
        body.pack_start(rail, False, False, 0)
        self.tool_buttons = {}
        group = None
        for name, label, key, tip in TOOLS:
            button = Gtk.RadioButton.new_from_widget(group)
            group = group or button
            button.set_mode(False)
            button.set_can_focus(False)
            button.set_tooltip_text("{} ({})".format(tip, key.upper()))
            button.get_style_context().add_class("tool")
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            icon = Gtk.DrawingArea()
            icon.set_size_request(20, 20)
            icon.set_halign(Gtk.Align.CENTER)
            icon.connect("draw", self.draw_tool_icon, name)
            content.pack_start(icon, False, False, 0)
            content.pack_start(Gtk.Label(label=label), False, False, 0)
            button.add(content)
            button.connect("toggled", self.tool_toggled, name)
            self.tool_buttons[name] = button
            rail.pack_start(button, False, False, 0)
        group = None
        self.swatches = []
        for name, color in COLORS:
            button = Gtk.RadioButton.new_from_widget(group)
            group = group or button
            button.set_mode(False)
            button.set_can_focus(False)
            button.set_tooltip_text(name)
            button.get_style_context().add_class("swatch")
            dot = Gtk.DrawingArea()
            dot.set_size_request(22, 22)
            dot.connect("draw", self.draw_swatch, color, button)
            button.add(dot)
            button.connect("toggled", self.color_toggled, color)
            button.connect("toggled", lambda b: self.queue_draw())
            self.swatches.append(button)
            bar.pack_start(button, False, False, 0)
        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        group = None
        self.size_buttons = []
        for index, (width, _, _) in enumerate(SIZES):
            button = Gtk.RadioButton.new_from_widget(group)
            group = group or button
            button.set_mode(False)
            button.set_can_focus(False)
            button.set_tooltip_text("Size {} ({})".format(index + 1, index + 1))
            button.get_style_context().add_class("size")
            dot = Gtk.DrawingArea()
            dot.set_size_request(18, 18)
            dot.connect("draw", self.draw_size, width)
            button.add(dot)
            button.connect("toggled", self.size_toggled, index)
            self.size_buttons.append(button)
            bar.pack_start(button, False, False, 0)
        self.size_buttons[self.level].set_active(True)
        save = Gtk.Button(label="Save")
        save.set_can_focus(False)
        save.set_tooltip_text("Save to Pictures and add it to the corner stack (Ctrl+S)")
        save.get_style_context().add_class("primary")
        save.connect("clicked", lambda _: self.save())
        bar.pack_end(save, False, False, 0)
        self.action_button(bar, "Copy", "Copy the edited image (Ctrl+C)", self.copy, end=True)
        self.action_button(bar, "Cancel", "Close without saving (Esc)", self.cancel, end=True)
        bar.pack_end(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        self.redo_button = self.action_button(bar, None, "Redo (Ctrl+Shift+Z)", self.redo,
                                              end=True, icon="edit-redo-symbolic")
        self.undo_button = self.action_button(bar, None, "Undo (Ctrl+Z)", self.undo,
                                              end=True, icon="edit-undo-symbolic")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.pack_start(content, True, True, 0)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_can_focus(True)
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                               Gdk.EventMask.POINTER_MOTION_MASK)
        self.canvas.connect("draw", self.draw)
        self.canvas.connect("button-press-event", self.press)
        self.canvas.connect("motion-notify-event", self.motion)
        self.canvas.connect("button-release-event", self.release)
        self.canvas.connect("realize", lambda w: self.update_cursor())
        content.pack_start(self.canvas, True, True, 0)
        self.status = Gtk.Label(xalign=0)
        self.status.get_style_context().add_class("status")
        content.pack_start(self.status, False, False, 0)
        self.connect("key-press-event", self.key)
        self.connect("delete-event", lambda *a: not self.confirm_discard())
        self.connect("focus-out-event", lambda *a: self.im.focus_out())
        self.connect("focus-in-event", lambda *a: self.editing and self.im.focus_in())

        area = monitor.get_workarea()
        width = min(round(area.width * 0.9), max(980, image.get_width() + 48))
        height = min(round(area.height * 0.9), max(560, image.get_height() + 120))
        self.set_default_size(width, height)
        self.move(area.x + (area.width - width) // 2, area.y + (area.height - height) // 2)
        self.tool_buttons[self.tool].set_active(True)
        self.refresh()
        self.connect("map-event", lambda *a: GLib.timeout_add(60, self.bring_to_front) and False)
        self.show_all()
        self.present_with_time(GdkX11.x11_get_server_time(self.get_window()))

    def bring_to_front(self):
        if not self.get_window():
            return False
        xid = self.get_window().get_xid()
        if shutil.which("xdotool"):
            subprocess.Popen(["xdotool", "windowactivate", str(xid)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.set_keep_above(True)
            self.present_with_time(GdkX11.x11_get_server_time(self.get_window()))
            GLib.timeout_add(800, lambda: self.set_keep_above(False))
        return False

    def action_button(self, bar, label, tip, callback, end=False, icon=None):
        if icon:
            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.MENU)
        else:
            button = Gtk.Button(label=label)
        button.set_can_focus(False)
        button.set_tooltip_text(tip)
        button.connect("clicked", lambda _: callback())
        (bar.pack_end if end else bar.pack_start)(button, False, False, 0)
        return button

    @staticmethod
    def draw_swatch(widget, cr, color, button):
        if button.get_active():
            cr.arc(11, 11, 10, 0, 2 * math.pi)
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1.6)
            cr.stroke()
        cr.arc(11, 11, 7, 0, 2 * math.pi)
        cr.set_source_rgb(*color)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.25)
        cr.set_line_width(1)
        cr.stroke()

    @staticmethod
    def draw_size(widget, cr, width):
        cr.arc(9, 9, max(1.5, width / 2 * 0.75 + 1), 0, 2 * math.pi)
        cr.set_source_rgb(0.9, 0.9, 0.92)
        cr.fill()

    @staticmethod
    def draw_tool_icon(widget, cr, name):
        color = widget.get_style_context().get_color(widget.get_state_flags())
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        cr.scale(20 / 24, 20 / 24)
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        def poly(*points, close=False):
            cr.move_to(*points[0])
            for point in points[1:]:
                cr.line_to(*point)
            if close:
                cr.close_path()
        if name == "select":
            poly((6, 3), (19, 11), (13, 12.5), (10, 19), close=True)
        elif name == "crop":
            poly((7, 2), (7, 17), (22, 17))
            poly((2, 7), (17, 7), (17, 22))
        elif name == "pen":
            poly((4, 20), (8, 19), (19, 8), (16, 5), (5, 16), close=True)
        elif name == "marker":
            poly((9, 14), (16, 4), (20, 7), (13, 17), close=True)
            poly((9, 14), (6, 20), (14, 20), (13, 17))
        elif name == "arrow":
            poly((5, 19), (19, 5))
            poly((10, 5), (19, 5), (19, 14))
        elif name == "rect":
            cr.rectangle(4, 5, 16, 14)
        elif name == "text":
            poly((5, 7), (5, 4), (19, 4), (19, 7))
            poly((12, 4), (12, 20))
            poly((9, 20), (15, 20))
        elif name == "pixelate":
            for x, y in ((4, 4), (14, 4), (4, 14), (14, 14)):
                cr.rectangle(x, y, 6, 6)
        cr.stroke()
        return False

    # ----- state and history -----

    def checkpoint(self):
        self.undo_stack.append(copy.deepcopy(self.state))
        self.redo_stack.clear()
        self.refresh()

    def discard_checkpoint(self):
        if self.undo_stack:
            self.state = self.undo_stack.pop()
        self.refresh()

    def undo(self):
        self.finish_text()
        if self.undo_stack:
            self.redo_stack.append(copy.deepcopy(self.state))
            self.state = self.undo_stack.pop()
            self.selected = None
            self.refresh()

    def redo(self):
        self.finish_text()
        if self.redo_stack:
            self.undo_stack.append(copy.deepcopy(self.state))
            self.state = self.redo_stack.pop()
            self.selected = None
            self.refresh()

    def refresh(self):
        self.undo_button.set_sensitive(bool(self.undo_stack))
        self.redo_button.set_sensitive(bool(self.redo_stack))
        x, y, w, h = self.state["crop"]
        hint = HINTS.get(self.tool, "Drag on the image to draw · Ctrl+Z undo · Ctrl+S save")
        self.status.set_text("{} × {} px   ·   {}".format(w, h, hint))
        self.canvas.queue_draw()

    # ----- toolbar -----

    def tool_toggled(self, button, name):
        if button.get_active():
            self.finish_text()
            self.tool = name
            if name != "select":
                self.selected = None
            self.update_cursor()
            self.refresh()

    def update_cursor(self):
        window = self.canvas.get_window()
        if window:
            window.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), CURSORS[self.tool]))

    def color_toggled(self, button, color):
        if not button.get_active():
            return
        self.color = color
        target = self.editing or self.selected
        if target and "color" in target and target["color"] != color:
            if target is not self.editing:
                self.checkpoint()
            target["color"] = color
            self.canvas.queue_draw()

    def size_toggled(self, button, index):
        if not button.get_active():
            return
        self.level = index
        target = self.editing or self.selected
        if target and target["kind"] != "pixelate":
            if target is not self.editing:
                self.checkpoint()
            scale = self.view[0]
            if target["kind"] == "text":
                target["size"] = SIZES[index][1] / scale
            else:
                factor = 4 if target["kind"] == "marker" else 1
                target["width"] = SIZES[index][0] * factor / scale
            self.canvas.queue_draw()

    # ----- coordinates -----

    def compute_view(self):
        alloc = self.canvas.get_allocation()
        x, y, w, h = self.state["crop"]
        pad = 24
        scale = min((alloc.width - 2 * pad) / w, (alloc.height - 2 * pad) / h, 2.0)
        scale = max(scale, 0.02)
        ox = (alloc.width - w * scale) / 2
        oy = (alloc.height - h * scale) / 2
        self.view = (scale, ox, oy)
        return self.view

    def to_image(self, wx, wy):
        scale, ox, oy = self.view
        cx, cy = self.state["crop"][:2]
        return cx + (wx - ox) / scale, cy + (wy - oy) / scale

    # ----- rendering -----

    def pixel_surface(self, block):
        block = max(2, int(round(block)))
        if block not in self.pixelated:
            w, h = self.base.get_width(), self.base.get_height()
            small = self.base.scale_simple(max(1, w // block), max(1, h // block),
                                           GdkPixbuf.InterpType.BILINEAR)
            big = small.scale_simple(w, h, GdkPixbuf.InterpType.NEAREST)
            self.pixelated[block] = Gdk.cairo_surface_create_from_pixbuf(big, 1, None)
        return self.pixelated[block]

    def text_layout(self, cr, item):
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription("Sans Bold")
        font.set_absolute_size(item["size"] * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text(item["text"] or " ", -1)
        return layout

    def paint_item(self, cr, item, caret=False):
        kind = item["kind"]
        cr.save()
        if kind == "pixelate":
            x, y, w, h = normalized(item["a"], item["b"])
            cr.rectangle(x, y, w, h)
            cr.clip()
            cr.set_source_surface(self.pixel_surface(item["block"]), 0, 0)
            cr.get_source().set_filter(cairo.FILTER_NEAREST)
            cr.paint()
        elif kind in ("pen", "marker"):
            points = item["points"]
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.set_line_width(item["width"])
            if kind == "marker":
                cr.set_source_rgba(*item["color"], 0.4)
            else:
                cr.set_source_rgb(*item["color"])
            cr.move_to(*points[0])
            if len(points) == 1:
                cr.line_to(points[0][0] + 0.01, points[0][1])
            for point in points[1:]:
                cr.line_to(*point)
            cr.stroke()
        elif kind == "rect":
            x, y, w, h = normalized(item["a"], item["b"])
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.set_line_width(item["width"])
            cr.set_source_rgb(*item["color"])
            cr.rectangle(x, y, w, h)
            cr.stroke()
        elif kind == "arrow":
            (x0, y0), (x1, y1) = item["a"], item["b"]
            length = math.hypot(x1 - x0, y1 - y0)
            if length > 0.5:
                width = item["width"]
                head = min(max(14 / self.view[0], width * 4), length)
                angle = math.atan2(y1 - y0, x1 - x0)
                bx, by = x1 - head * 0.8 * math.cos(angle), y1 - head * 0.8 * math.sin(angle)
                cr.set_source_rgb(*item["color"])
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.set_line_width(width)
                cr.move_to(x0, y0)
                cr.line_to(bx, by)
                cr.stroke()
                spread = math.radians(26)
                cr.move_to(x1, y1)
                cr.line_to(x1 - head * math.cos(angle - spread), y1 - head * math.sin(angle - spread))
                cr.line_to(x1 - head * math.cos(angle + spread), y1 - head * math.sin(angle + spread))
                cr.close_path()
                cr.fill()
        elif kind == "text":
            layout = self.text_layout(cr, item)
            cr.move_to(*item["pos"])
            PangoCairo.layout_path(cr, layout)
            halo = (0, 0, 0) if luminance(item["color"]) > 0.55 else (1, 1, 1)
            cr.set_source_rgba(*halo, 0.85)
            cr.set_line_width(max(1.5, item["size"] / 7))
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.stroke()
            cr.move_to(*item["pos"])
            cr.set_source_rgb(*item["color"])
            PangoCairo.show_layout(cr, layout)
            if caret:
                index = len(item["text"].encode("utf-8"))
                strong, _ = layout.get_cursor_pos(index)
                x = item["pos"][0] + strong.x / Pango.SCALE
                y = item["pos"][1] + strong.y / Pango.SCALE
                cr.set_source_rgb(*item["color"])
                cr.set_line_width(max(1, 2 / self.view[0]))
                cr.move_to(x + 1 / self.view[0], y)
                cr.line_to(x + 1 / self.view[0], y + strong.height / Pango.SCALE)
                cr.stroke()
        cr.restore()

    def paint(self, cr, interactive):
        x, y, w, h = self.state["crop"]
        cr.rectangle(x, y, w, h)
        cr.clip()
        cr.set_source_surface(self.surface, 0, 0)
        if interactive and self.view[0] < 1:
            cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        for item in self.state["items"]:
            self.paint_item(cr, item, caret=interactive and item is self.editing)

    def bbox(self, item):
        kind = item["kind"]
        if kind in ("pen", "marker"):
            xs = [p[0] for p in item["points"]]
            ys = [p[1] for p in item["points"]]
            pad = item["width"] / 2
            return min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad
        if kind == "text":
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
            layout = self.text_layout(cairo.Context(surface), item)
            _, logical = layout.get_pixel_extents()
            return item["pos"][0], item["pos"][1], logical.width, logical.height
        x, y, w, h = normalized(item["a"], item["b"])
        pad = item.get("width", 0) * (3 if kind == "arrow" else 0.5)
        return x - pad, y - pad, w + 2 * pad, h + 2 * pad

    def hit(self, point):
        slack = 6 / self.view[0]
        for item in reversed(self.state["items"]):
            x, y, w, h = self.bbox(item)
            if x - slack <= point[0] <= x + w + slack and y - slack <= point[1] <= y + h + slack:
                return item
        return None

    def draw(self, widget, cr):
        scale, ox, oy = self.compute_view()
        cx, cy, cw, ch = self.state["crop"]
        cr.set_source_rgb(0.08, 0.09, 0.11)
        cr.paint()
        cr.save()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        cr.translate(-cx, -cy)
        self.paint(cr, True)
        if self.crop_drag:
            x, y, w, h = normalized(*self.crop_drag)
            cr.set_source_rgba(0, 0, 0, 0.55)
            cr.rectangle(cx, cy, cw, ch)
            cr.rectangle(x, y, w, h)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1 / scale)
            cr.rectangle(x, y, w, h)
            cr.stroke()
        if self.selected is not None:
            x, y, w, h = self.bbox(self.selected)
            pad = 4 / scale
            cr.set_source_rgb(0.95, 0.64, 0.23)
            cr.set_line_width(1.5 / scale)
            cr.set_dash([5 / scale, 4 / scale])
            cr.rectangle(x - pad, y - pad, w + 2 * pad, h + 2 * pad)
            cr.stroke()
        cr.restore()
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.set_line_width(1)
        cr.rectangle(ox - 0.5, oy - 0.5, cw * scale + 1, ch * scale + 1)
        cr.stroke()
        if self.crop_drag:
            x, y, w, h = normalized(*self.crop_drag)
            text = "{} × {}".format(round(w), round(h))
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(13)
            tx = ox + (x - cx) * scale
            ty = max(16, oy + (y - cy) * scale - 8)
            extent = cr.text_extents(text)[4]
            cr.set_source_rgba(0.08, 0.09, 0.12, 0.9)
            cr.rectangle(tx - 6, ty - 15, extent + 12, 21)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(tx, ty)
            cr.show_text(text)
        return False

    # ----- pointer -----

    def press(self, widget, event):
        if event.button != 1:
            return False
        point = self.to_image(event.x, event.y)
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            item = self.hit(point)
            if self.tool == "select" and item and item["kind"] == "text":
                self.moving = None
                self.start_text(item, new=False)
            return True
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return True
        self.canvas.grab_focus()
        scale = self.view[0]
        width = SIZES[self.level][0] / scale
        if self.editing is not None:
            inside = self.hit(point) is self.editing
            self.finish_text()
            if inside or self.tool == "text":
                return True
        if self.tool == "select":
            item = self.hit(point)
            self.selected = item
            if item is not None:
                self.moving = [item, point, False]
            self.canvas.queue_draw()
        elif self.tool == "crop":
            point = self.clamp_to_crop(point)
            self.crop_drag = [point, point]
        elif self.tool in ("pen", "marker"):
            self.checkpoint()
            self.active = {"kind": self.tool, "points": [point], "color": self.color,
                           "width": width * (4 if self.tool == "marker" else 1)}
            self.state["items"].append(self.active)
        elif self.tool in ("arrow", "rect", "pixelate"):
            self.checkpoint()
            self.active = {"kind": self.tool, "a": point, "b": point, "color": self.color,
                           "width": width, "block": SIZES[self.level][2] / scale}
            self.state["items"].append(self.active)
        elif self.tool == "text":
            item = self.hit(point)
            if item is not None and item["kind"] == "text":
                self.start_text(item, new=False)
            else:
                size = SIZES[self.level][1] / scale
                item = {"kind": "text", "pos": (point[0], point[1] - size * 0.6), "text": "",
                        "color": self.color, "size": size}
                self.start_text(item, new=True)
        self.canvas.queue_draw()
        return True

    def motion(self, widget, event):
        if not event.state & Gdk.ModifierType.BUTTON1_MASK:
            return False
        point = self.to_image(event.x, event.y)
        if self.moving:
            item, last, _ = self.moving
            dx, dy = point[0] - last[0], point[1] - last[1]
            if not dx and not dy:
                return True
            if not self.moving[2]:
                self.checkpoint()
            self.moving[1] = point
            self.moving[2] = True
            self.translate(item, dx, dy)
        elif self.crop_drag:
            self.crop_drag[1] = self.clamp_to_crop(point)
        elif self.active is not None:
            if self.active["kind"] in ("pen", "marker"):
                last = self.active["points"][-1]
                if math.hypot(point[0] - last[0], point[1] - last[1]) * self.view[0] >= 1.5:
                    self.active["points"].append(point)
            else:
                self.active["b"] = point
        else:
            return False
        self.canvas.queue_draw()
        return True

    def release(self, widget, event):
        if event.button != 1:
            return False
        if self.moving:
            self.moving = None
        elif self.crop_drag:
            x, y, w, h = normalized(*self.crop_drag)
            self.crop_drag = None
            left, top = math.floor(x), math.floor(y)
            right, bottom = math.ceil(x + w), math.ceil(y + h)
            if right - left >= 4 and bottom - top >= 4:
                self.checkpoint()
                self.state["crop"] = (left, top, right - left, bottom - top)
        elif self.active is not None:
            item, self.active = self.active, None
            if item["kind"] in ("arrow", "rect", "pixelate"):
                x, y, w, h = normalized(item["a"], item["b"])
                if max(w, h) * self.view[0] < 4:
                    self.discard_checkpoint()
        self.refresh()
        return True

    def clamp_to_crop(self, point):
        cx, cy, cw, ch = self.state["crop"]
        return min(max(point[0], cx), cx + cw), min(max(point[1], cy), cy + ch)

    @staticmethod
    def translate(item, dx, dy):
        if "points" in item:
            item["points"] = [(x + dx, y + dy) for x, y in item["points"]]
        if "pos" in item:
            item["pos"] = (item["pos"][0] + dx, item["pos"][1] + dy)
        for key in ("a", "b"):
            if key in item:
                item[key] = (item[key][0] + dx, item[key][1] + dy)

    # ----- text -----

    def start_text(self, item, new):
        self.checkpoint()
        if new:
            self.state["items"].append(item)
        self.editing, self.editing_new = item, new
        self.selected = None
        self.im.set_client_window(self.canvas.get_window())
        self.im.focus_in()
        self.canvas.queue_draw()

    def finish_text(self):
        item = self.editing
        if item is None:
            return
        self.editing = None
        self.im.focus_out()
        self.im.reset()
        if not item["text"].strip():
            self.discard_checkpoint()
        elif not self.editing_new and self.undo_stack and self.undo_stack[-1] == self.state:
            self.undo_stack.pop()
        self.refresh()

    def im_commit(self, context, text):
        if self.editing is not None:
            self.editing["text"] += text
            self.canvas.queue_draw()

    # ----- keyboard -----

    def key(self, widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        keyval = Gdk.keyval_to_lower(event.keyval)
        if self.editing is not None and not ctrl:
            if event.keyval == Gdk.KEY_Escape:
                self.finish_text()
            elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self.editing["text"] += "\n"
            elif event.keyval == Gdk.KEY_BackSpace:
                self.editing["text"] = self.editing["text"][:-1]
            elif not self.im.filter_keypress(event):
                return True
            self.canvas.queue_draw()
            return True
        if ctrl:
            if keyval == Gdk.KEY_z:
                self.redo() if shift else self.undo()
            elif keyval == Gdk.KEY_y:
                self.redo()
            elif keyval == Gdk.KEY_s:
                self.save()
            elif keyval == Gdk.KEY_c:
                self.copy()
            elif keyval == Gdk.KEY_w:
                self.cancel()
            else:
                return False
            return True
        if event.keyval == Gdk.KEY_Escape:
            if self.crop_drag:
                self.crop_drag = None
                self.canvas.queue_draw()
            elif self.selected is not None:
                self.selected = None
                self.canvas.queue_draw()
            else:
                self.cancel()
            return True
        if event.keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace) and self.selected is not None:
            self.checkpoint()
            self.state["items"] = [x for x in self.state["items"] if x is not self.selected]
            self.selected = None
            self.refresh()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.save()
            return True
        for name, _, shortcut, _ in TOOLS:
            if keyval == Gdk.unicode_to_keyval(ord(shortcut)):
                self.tool_buttons[name].set_active(True)
                return True
        if Gdk.KEY_1 <= event.keyval <= Gdk.KEY_4:
            self.size_buttons[event.keyval - Gdk.KEY_1].set_active(True)
            return True
        return False

    # ----- output -----

    def render(self):
        self.finish_text()
        x, y, w, h = self.state["crop"]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)
        cr.translate(-x, -y)
        self.paint(cr, False)
        surface.flush()
        return Gdk.pixbuf_get_from_surface(surface, 0, 0, w, h)

    def save(self):
        if self.on_save(self.render()):
            self.destroy()

    def copy(self):
        self.on_copy(self.render())
        self.status.set_text("Copied to the clipboard · Paste with Ctrl+V")

    def confirm_discard(self):
        self.finish_text()
        if not self.undo_stack:
            return True
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                                   message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text="Discard your edits?")
        dialog.add_buttons("Keep editing", Gtk.ResponseType.CANCEL,
                           "Discard", Gtk.ResponseType.REJECT)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.REJECT

    def cancel(self):
        if self.confirm_discard():
            self.destroy()
