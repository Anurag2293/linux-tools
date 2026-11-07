#!/usr/bin/env python3
"""lens: translate everything on screen in place (Ubuntu, GNOME on X11).

Double-tap right Alt: the monitor under the pointer is captured, read with PP-OCRv5 (RapidOCR on
OpenVINO, on this machine), translated with Google Translate, and the translation is painted
over the original text in a full-screen overlay, matching each block's background and text color.

  lens                     show or dismiss the overlay in the running daemon
  lens daemon              the resident daemon (what the systemd user service runs)
  lens file IMG [--out PNG]
                           OCR and translate an image, print the blocks, optionally render them
  lens status | logs       service state, follow the log

Overlay: Esc, a click, a scroll or the trigger again dismisses it; hold Shift to see the
original; Ctrl+C copies the whole translation.

Environment: LENS_FROM (default ja), LENS_TO (default en), LENS_HOTKEY (default double:ralt;
also double:rctrl, double:rsuper, double:rshift, double:lalt, ...).
"""
import os
import sys
from pathlib import Path

HOME = Path.home()
VENV = HOME / ".local/share/lens/venv"
# The OCR stack lives in a venv (with system site packages for gi and cairo): re-exec into it.
if Path(sys.prefix).resolve() != VENV.resolve() and (VENV / "bin/python").exists():
    py = str(VENV / "bin/python")
    os.execv(py, [py, os.path.realpath(__file__)] + sys.argv[1:])

import html
import json
import re
import socket
import subprocess
import threading
import time
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cairo
import gi
import numpy as np

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

FROM = os.environ.get("LENS_FROM", "ja")
TO = os.environ.get("LENS_TO", "en")
HOTKEY = os.environ.get("LENS_HOTKEY", "double:ralt")
SOCK = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "lens.sock"
FONT = "Ubuntu"
TAP_WINDOW = 0.35  # max hold for a tap, and max gap between the two taps (s)
PAD = 0.12         # of the line height, around each painted block


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------
# OCR

@dataclass
class Line:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    score: float

    @property
    def h(self):
        return self.y1 - self.y0


_engine = None
_engine_lock = threading.Lock()


def engine():
    """PP-OCRv5 mobile detection and recognition (reads Japanese, Chinese and English).
    OpenVINO is about 1.7x faster than onnxruntime on this Intel CPU."""
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr import EngineType, ModelType, OCRVersion, RapidOCR
            params = {"Det.ocr_version": OCRVersion.PPOCRV5, "Rec.ocr_version": OCRVersion.PPOCRV5,
                      "Det.model_type": ModelType.MOBILE, "Rec.model_type": ModelType.MOBILE,
                      "Global.use_cls": False, "Global.log_level": "error"}
            try:
                _engine = RapidOCR(params=dict(params, **{"Det.engine_type": EngineType.OPENVINO,
                                                          "Rec.engine_type": EngineType.OPENVINO}))
            except Exception as e:  # noqa: BLE001
                log(f"OpenVINO unavailable ({e}); using onnxruntime")
                _engine = RapidOCR(params=params)
        return _engine


def recognize(rgb) -> List[Line]:
    r = engine()(np.ascontiguousarray(rgb[:, :, ::-1]))  # RapidOCR takes BGR
    if r.boxes is None:
        return []
    out = []
    for box, text, score in zip(r.boxes, r.txts, r.scores):
        xs, ys = box[:, 0], box[:, 1]
        out.append(Line(float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()), text, float(score)))
    return out


# ---------------------------------------------------------------------------------------------
# Paragraphs

def is_cjk(ch):
    o = ord(ch)
    return (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF
            or 0xFF66 <= o <= 0xFF9F or 0xAC00 <= o <= 0xD7AF)


def is_cjk_letter(ch):
    """Kana, kanji and hangul letters (not CJK punctuation such as ・ or ー)."""
    o = ord(ch)
    return (0x3041 <= o <= 0x3096 or 0x30A1 <= o <= 0x30FA or 0x3400 <= o <= 0x4DBF
            or 0x4E00 <= o <= 0x9FFF or 0xFF66 <= o <= 0xFF9D or 0xAC00 <= o <= 0xD7AF)


def ends_sentence(s):
    s = s.strip()
    return not s or s[-1] in "。．.!?！？:："


def starts_bullet(s):
    s = s.strip()
    return bool(s) and s[0] in "•・●○■□◆◇▪-–*※★→·。"


def paragraphs(lines: List[Line]) -> List[List[Line]]:
    """Stacked, left-aligned lines of similar height form a block; a block splits where a line
    stops short of the block's right edge (it did not wrap), ends a sentence, or the next line
    starts with a bullet."""
    blocks: List[List[Line]] = []
    for l in sorted(lines, key=lambda l: l.y0):
        target = None
        for i in range(len(blocks) - 1, -1, -1):
            p = blocks[i][-1]
            hmax = max(l.h, p.h)
            gap = l.y0 - p.y1
            if (-0.3 * hmax < gap < 0.8 * hmax and abs(l.x0 - p.x0) < 1.2 * hmax
                    and abs(l.h - p.h) < 0.35 * hmax):
                target = i
                break
        if target is None:
            blocks.append([l])
        else:
            blocks[target].append(l)
    out = []
    for b in blocks:
        right = max(l.x1 for l in b)
        left = min(l.x0 for l in b)
        cur: List[Line] = []
        for l in b:
            if cur:
                p = cur[-1]
                wide = right - left > 20 * p.h
                wrapped = (wide and p.x1 >= right - 2.5 * p.h and not ends_sentence(p.text)
                           and not starts_bullet(l.text))
                if not wrapped:
                    out.append(cur)
                    cur = []
            cur.append(l)
        out.append(cur)
    return out


def join_lines(lines: List[Line]) -> str:
    s = ""
    for l in lines:
        t = l.text.strip()
        if s and t and not (is_cjk(s[-1]) and is_cjk(t[0])):
            s += " "
        s += t
    # PP-OCR sometimes reads a bullet as 。 at the start of a line.
    return re.sub(r"^。\s*", "• ", s)


def needs_translation(s):
    if len(s) < 2:
        return False
    if FROM in ("ja", "zh", "ko"):
        # One stray CJK glyph next to Latin text is usually an icon or emoji misread by OCR.
        cjk = sum(1 for c in s if is_cjk_letter(c))
        latin = sum(1 for c in s if c.isascii() and c.isalpha())
        return cjk >= 2 or (cjk == 1 and latin == 0)
    return any(unicodedata.category(c).startswith("L") and not c.isascii() for c in s)


# ---------------------------------------------------------------------------------------------
# Colors

def luminance(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def sample_colors(rgb, x0, y0, x1, y1):
    """Background = median of a ring just outside the box; text = mean of the pixels inside that
    differ most from it, falling back to black or white when that has too little contrast."""
    h, w = rgb.shape[:2]
    X0, Y0 = max(int(x0) - 3, 0), max(int(y0) - 3, 0)
    X1, Y1 = min(int(x1) + 3, w - 1), min(int(y1) + 3, h - 1)
    ring = np.concatenate([rgb[Y0, X0:X1 + 1], rgb[Y1, X0:X1 + 1], rgb[Y0:Y1 + 1, X0], rgb[Y0:Y1 + 1, X1]])
    bg = np.median(ring.astype(float), axis=0) / 255
    inside = rgb[max(int(y0), 0):int(y1) + 1, max(int(x0), 0):int(x1) + 1].reshape(-1, 3).astype(float) / 255
    if len(inside) == 0:
        return tuple(bg), (0.0, 0.0, 0.0) if luminance(bg) > 0.5 else (1.0, 1.0, 1.0)
    d = ((inside - bg) ** 2).sum(axis=1)
    k = max(1, len(d) // 12)
    fg = inside[np.argpartition(-d, k - 1)[:k]].mean(axis=0)
    if abs(luminance(fg) - luminance(bg)) < 0.35:
        fg = np.zeros(3) if luminance(bg) > 0.5 else np.ones(3)
    return tuple(bg), tuple(fg)


# ---------------------------------------------------------------------------------------------
# Blocks

@dataclass
class Block:
    area: Tuple[float, float, float, float]  # x0, y0, x1, y1 of the original text, image pixels
    line_h: float
    original: str
    bg: tuple
    fg: tuple
    translated: Optional[str] = None
    rect: Tuple[float, float, float, float] = (0, 0, 0, 0)  # painted box x, y, w, h
    font_px: float = 0
    lines: list = field(default_factory=list)


def prepare(rgb, focus=None) -> List[Block]:
    """OCR, paragraphs and colors for everything that needs translating, nearest to `focus` first."""
    blocks = []
    for lines in paragraphs(recognize(rgb)):
        text = join_lines(lines)
        if not needs_translation(text):
            continue
        x0, y0 = min(l.x0 for l in lines), min(l.y0 for l in lines)
        x1, y1 = max(l.x1 for l in lines), max(l.y1 for l in lines)
        bg, fg = sample_colors(rgb, x0, y0, x1, y1)
        hs = sorted(l.h for l in lines)
        blocks.append(Block((x0, y0, x1, y1), hs[len(hs) // 2], text, bg, fg))
    if focus:
        fx, fy = focus

        def dist(b):
            x0, y0, x1, y1 = b.area
            dx, dy = max(x0 - fx, 0, fx - x1), max(y0 - fy, 0, fy - y1)
            return dx * dx + 4 * dy * dy
        blocks.sort(key=dist)
    return blocks


# ---------------------------------------------------------------------------------------------
# Translation: the endpoint Chrome's built-in page translation uses. One request carries the
# whole screen (about 0.3 s) and takes HTML, so text is escaped going in and unescaped back.

GOOGLE_URL = "https://translate-pa.googleapis.com/v1/translateHtml"
GOOGLE_KEY = "AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520"  # Chrome's public translate key
cache = {}


def google_translate(texts):
    out = []
    start = 0
    while start < len(texts):  # chunks of at most 100 texts / ~8000 characters
        end, chars = start, 0
        while end < len(texts) and end - start < 100 and (end == start or chars + len(texts[end]) < 8000):
            chars += len(texts[end])
            end += 1
        chunk = texts[start:end]
        body = json.dumps([[[html.escape(t, quote=False) for t in chunk], FROM, TO], "te_lib"]).encode()
        req = urllib.request.Request(GOOGLE_URL, data=body, headers={
            "Content-Type": "application/json+protobuf", "X-Goog-API-Key": GOOGLE_KEY})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        got = data[0] if data and isinstance(data[0], list) else None
        if not got or len(got) != len(chunk):
            raise RuntimeError(f"Google Translate returned {str(data)[:200]}")
        out += [html.unescape(t) for t in got]
        start = end
    return out


def translate(blocks: List[Block]):
    if len(cache) > 5000:
        cache.clear()
    pending = [b for b in blocks if b.original not in cache]
    if pending:
        for b, t in zip(pending, google_translate([b.original for b in pending])):
            cache[b.original] = t
    for b in blocks:
        b.translated = cache[b.original]


# ---------------------------------------------------------------------------------------------
# Layout and drawing

_measure_cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))


def layout_for(cr, text, px, width):
    layout = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription(FONT)
    fd.set_absolute_size(px * Pango.SCALE)
    layout.set_font_description(fd)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_width(int(width * Pango.SCALE) if width else -1)
    layout.set_text(text, -1)
    return layout


def fit(b: Block, max_right, others):
    """Font from 74% down to 62% of the OCR box height (PP-OCR boxes include some padding); if
    it still overflows, a single-line box widens (up to 2.5x, never past `max_right` or into
    other text on the same row), then the font goes down to 52%, then the box grows downward."""
    text = b.translated or ""
    pad = b.line_h * PAD
    x0, y0, x1, y1 = b.area
    bx, by, bw, bh = x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad

    def needed(px, w):
        return layout_for(_measure_cr, text, px, (w - 2 * pad) if w else None).get_pixel_size()

    def fits(px):
        return needed(px, bw)[1] <= bh - 2 * pad

    size = b.line_h * 0.74
    while size > b.line_h * 0.62 and not fits(size):
        size -= 0.5
    if not fits(size):
        if y1 - y0 < 1.6 * b.line_h:
            right = min(bx + bw * 2.5, max_right)
            for o in others:
                if o[0] > x1 - 1 and o[1] < y1 and o[3] > y0:
                    right = min(right, o[0] - pad)
            one_line = needed(size, None)[0] + 2 * pad + 2
            bw = min(max(bw, one_line), max(bw, right - bx))
        while size > b.line_h * 0.52 and not fits(size):
            size -= 0.5
        if not fits(size):
            bh = needed(size, bw)[1] + 2 * pad
    b.rect = (bx, by, bw, bh)
    b.font_px = size


def rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -1.5708, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
    cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    cr.arc(x + r, y + r, r, 3.1416, 4.7124)
    cr.close_path()


def draw_blocks(cr, blocks: List[Block]):
    for b in reversed(blocks):  # nearest-first order, so the pointer's block ends up on top
        if not b.translated or b.translated == b.original:
            continue
        x, y, w, h = b.rect
        cr.set_source_rgb(*b.bg)
        rounded(cr, x, y, w, h, 3)
        cr.fill()
        pad = b.line_h * PAD
        cr.set_source_rgb(*b.fg)
        cr.move_to(x + pad, y + pad)
        PangoCairo.show_layout(cr, layout_for(cr, b.translated, b.font_px, w - 2 * pad))


def finish(blocks: List[Block], width):
    areas = [b.area for b in blocks]
    for b in blocks:
        fit(b, width, areas)


# ---------------------------------------------------------------------------------------------
# File mode (testing without the screen)

def run_file(args):
    import cv2
    path = args[0]
    out = args[args.index("--out") + 1] if "--out" in args else None
    bgr = cv2.imread(path)
    if bgr is None:
        sys.exit(f"cannot read {path}")
    rgb = bgr[:, :, ::-1]
    engine()
    t0 = time.time()
    blocks = prepare(rgb)
    t1 = time.time()
    translate(blocks)
    t2 = time.time()
    finish(blocks, rgb.shape[1])
    log(f"{len(blocks)} blocks: ocr {t1 - t0:.2f}s, translate {t2 - t1:.2f}s")
    for b in blocks:
        x, y, w, h = b.rect
        print(f"[{x:.0f},{y:.0f} {w:.0f}x{h:.0f} {b.font_px:.0f}px] {b.original}\n    → {b.translated}")
    if out:
        rgba = np.dstack([bgr, np.full(bgr.shape[:2], 255, np.uint8)])  # BGRA = cairo ARGB32 (LE)
        surface = cairo.ImageSurface.create_for_data(memoryview(np.ascontiguousarray(rgba)),
                                                     cairo.FORMAT_ARGB32, rgb.shape[1], rgb.shape[0])
        draw_blocks(cairo.Context(surface), blocks)
        surface.write_to_png(out)


# ---------------------------------------------------------------------------------------------
# Double-tap trigger, seen through the X RECORD extension (no root, nothing is grabbed).

TAP_KEYS = {"ralt": ["Alt_R", "ISO_Level3_Shift"], "lalt": ["Alt_L"], "rctrl": ["Control_R"],
            "lctrl": ["Control_L"], "rshift": ["Shift_R"], "lshift": ["Shift_L"],
            "rsuper": ["Super_R"], "lsuper": ["Super_L"]}


class DoubleTap(threading.Thread):
    """A tap is a press and release within TAP_WINDOW with no other key or button in between,
    so shortcuts using the key never count; two taps within TAP_WINDOW fire."""

    def __init__(self, name, fire):
        super().__init__(daemon=True)
        from Xlib import XK, display
        self.fire = fire
        self.local = display.Display()
        self.rec = display.Display()
        codes = set()
        for sym in TAP_KEYS[name]:
            code = self.local.keysym_to_keycode(XK.string_to_keysym(sym))
            if code:
                codes.add(code)
        if name == "ralt":
            codes.add(108)  # evdev keycode of the physical right Alt key
        self.codes = codes
        self.held = set()
        self.down_at = None
        self.last_tap = 0.0

    def run(self):
        from Xlib import X
        from Xlib.ext import record
        ctx = self.rec.record_create_context(0, [record.AllClients], [{
            "core_requests": (0, 0), "core_replies": (0, 0), "ext_requests": (0, 0, 0, 0),
            "ext_replies": (0, 0, 0, 0), "delivered_events": (0, 0),
            "device_events": (X.KeyPress, X.ButtonPress), "errors": (0, 0),
            "client_started": False, "client_died": False}])
        self.rec.record_enable_context(ctx, self.handler)

    def handler(self, reply):
        from Xlib import X
        from Xlib.ext import record
        from Xlib.protocol import rq
        if reply.category != record.FromServer or reply.client_swapped or not reply.data:
            return
        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(data, self.rec.display, None, None)
            self.on(event.type, event.detail, X)

    def on(self, kind, code, X):
        now = time.monotonic()
        if kind == X.KeyPress:
            if code in self.held:  # autorepeat
                return
            others = bool(self.held)
            self.held.add(code)
            if code in self.codes and not others:
                self.down_at = now
            else:
                self.down_at, self.last_tap = None, 0.0
        elif kind == X.KeyRelease:
            self.held.discard(code)
            if code in self.codes and self.down_at is not None:
                held_for, self.down_at = now - self.down_at, None
                if held_for >= TAP_WINDOW:
                    self.last_tap = 0.0
                elif now - self.last_tap < TAP_WINDOW:
                    self.last_tap = 0.0
                    self.fire()
                else:
                    self.last_tap = now
        elif kind == X.ButtonPress:
            self.down_at, self.last_tap = None, 0.0


# ---------------------------------------------------------------------------------------------
# Daemon: overlay, HUD and control socket

def run_daemon():
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk

    def rgba_window(win):
        visual = win.get_screen().get_rgba_visual()
        if visual:
            win.set_visual(visual)
        win.set_app_paintable(True)
        win.set_decorated(False)
        win.set_keep_above(True)
        win.set_skip_taskbar_hint(True)

    class HUD(Gtk.Window):
        """A small pill at the top of the screen for progress and errors."""

        def __init__(self):
            super().__init__(type=Gtk.WindowType.POPUP)
            rgba_window(self)
            self.text = ""
            self.timer = None
            self.connect("draw", self.draw)

        def show_text(self, text, geom, seconds=None):
            self.text = text
            layout = layout_for(_measure_cr, text, 13, None)
            w = layout.get_pixel_size()[0] + 36
            self.resize(w, 30)
            self.move(geom.x + (geom.width - w) // 2, geom.y + 40)
            self.show_all()
            self.queue_draw()
            if self.timer:
                GLib.source_remove(self.timer)
                self.timer = None
            if seconds:
                self.timer = GLib.timeout_add(int(seconds * 1000), self.hide_hud)

        def hide_hud(self):
            self.timer = None
            self.hide()
            return False

        def draw(self, _w, cr):
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            w, h = self.get_size()
            cr.set_source_rgba(0.12, 0.12, 0.12, 0.92)
            rounded(cr, 0, 0, w, h, 15)
            cr.fill()
            layout = layout_for(cr, self.text, 13, None)
            tw, th = layout.get_pixel_size()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to((w - tw) / 2, (h - th) / 2)
            PangoCairo.show_layout(cr, layout)

    class Overlay(Gtk.Window):
        def __init__(self, app, geom):
            super().__init__(type=Gtk.WindowType.POPUP)
            rgba_window(self)
            self.app = app
            self.blocks: List[Block] = []
            self.show_original = False
            self.move(geom.x, geom.y)
            self.resize(geom.width, geom.height)
            self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK
                            | Gdk.EventMask.KEY_RELEASE_MASK | Gdk.EventMask.SCROLL_MASK
                            | Gdk.EventMask.SMOOTH_SCROLL_MASK)
            self.connect("draw", self.draw)
            self.connect("button-press-event", lambda *_: app.dismiss())
            self.connect("scroll-event", lambda *_: app.dismiss())
            self.connect("key-press-event", self.key_press)
            self.connect("key-release-event", self.key_release)
            self.show_all()
            self.seat = self.get_display().get_default_seat()
            status = self.seat.grab(self.get_window(), Gdk.SeatCapabilities.POINTER
                                    | Gdk.SeatCapabilities.KEYBOARD, False, None, None, None)
            self.grabbed = status == Gdk.GrabStatus.SUCCESS
            if not self.grabbed:
                self.seat = None

        def draw(self, _w, cr):
            cr.set_operator(cairo.OPERATOR_SOURCE)
            cr.set_source_rgba(0, 0, 0, 0.06)  # also signals that the screen is in lens mode
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
            if not self.show_original:
                draw_blocks(cr, self.blocks)

        def key_press(self, _w, ev):
            name = Gdk.keyval_name(ev.keyval) or ""
            if name.startswith("Shift"):
                self.show_original = True
                self.queue_draw()
            elif ev.state & Gdk.ModifierType.CONTROL_MASK and name.lower() == "c":
                text = "\n\n".join(b.translated for b in sorted(self.blocks, key=lambda b: (b.area[1], b.area[0]))
                                   if b.translated)
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
                self.app.dismiss()
            elif name.startswith(("Control", "Alt", "Super", "ISO_Level3", "Meta")):
                pass  # modifiers alone: the double-tap trigger and Ctrl+C start here
            else:
                self.app.dismiss()
            return True

        def key_release(self, _w, ev):
            if (Gdk.keyval_name(ev.keyval) or "").startswith("Shift"):
                self.show_original = False
                self.queue_draw()
            return True

        def close(self):
            if self.seat:
                self.seat.ungrab()
                self.seat = None
            self.destroy()

    class App:
        def __init__(self):
            self.overlay: Optional[Overlay] = None
            self.job = None
            self.hud = HUD()

        def toggle(self):
            if self.overlay or self.job:
                self.dismiss()
                return False
            display = Gdk.Display.get_default()
            _, px, py = display.get_default_seat().get_pointer().get_position()
            geom = display.get_monitor_at_point(px, py).get_geometry()
            self.hud.hide()
            pb = Gdk.pixbuf_get_from_window(Gdk.get_default_root_window(), geom.x, geom.y, geom.width, geom.height)
            n, stride = pb.get_n_channels(), pb.get_rowstride()
            rgb = np.frombuffer(pb.get_pixels(), np.uint8)
            rgb = np.lib.stride_tricks.as_strided(rgb, (geom.height, geom.width, 3), (stride, n, 1)).copy()
            log(f"triggered on monitor {geom.x},{geom.y} {geom.width}x{geom.height}")
            self.overlay = Overlay(self, geom)
            if not self.overlay.grabbed:
                # The lock screen or an open menu holds the input: an overlay Esc cannot close
                # would only get in the way.
                self.dismiss()
                log("input is grabbed elsewhere (screen locked or a menu open)")
                self.hud.show_text("Screen is locked or input is busy", geom, 2)
                return False
            self.hud.show_text("Reading…", geom)
            job = self.job = {"cancelled": False, "geom": geom}
            threading.Thread(target=self.work, args=(job, rgb, (px - geom.x, py - geom.y)), daemon=True).start()
            return False

        def work(self, job, rgb, focus):
            try:
                t0 = time.time()
                blocks = prepare(rgb, focus)
                t1 = time.time()
                if job["cancelled"]:
                    return
                if not blocks:
                    GLib.idle_add(self.nothing, job)
                    return
                GLib.idle_add(self.progress, job, "Translating…")
                translate(blocks)
                log(f"{len(blocks)} blocks: ocr {t1 - t0:.2f}s, translate {time.time() - t1:.2f}s")
                GLib.idle_add(self.present, job, blocks, rgb.shape[1])
            except Exception as e:  # noqa: BLE001
                log(f"error: {e!r}")
                GLib.idle_add(self.failed, job, str(e))

        def progress(self, job, text):
            if job is self.job:
                self.hud.show_text(text, job["geom"])

        def nothing(self, job):
            if job is self.job:
                self.dismiss()
                self.hud.show_text("No Japanese text on screen" if FROM == "ja" else "No text to translate",
                                   job["geom"], 1.8)

        def failed(self, job, msg):
            if job is self.job:
                self.dismiss()
                self.hud.show_text(msg[:120], job["geom"], 4)

        def present(self, job, blocks, width):
            if job is not self.job or not self.overlay:
                return
            finish(blocks, width)
            self.overlay.blocks = blocks
            self.overlay.queue_draw()
            self.job = None
            self.hud.hide()

        def dismiss(self):
            if self.job:
                self.job["cancelled"] = True
                self.job = None
            self.hud.hide()
            if self.overlay:
                self.overlay.close()
                self.overlay = None

    app = App()

    def serve():
        try:
            SOCK.unlink()
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(SOCK))
        srv.listen(4)
        while True:
            conn, _ = srv.accept()
            with conn:
                if conn.recv(64).strip() == b"toggle":
                    GLib.idle_add(app.toggle)
                    conn.sendall(b"ok\n")

    threading.Thread(target=serve, daemon=True).start()
    threading.Thread(target=lambda: engine()(np.zeros((64, 256, 3), np.uint8)), daemon=True).start()  # warm up
    if HOTKEY.startswith("double:") and HOTKEY[7:] in TAP_KEYS:
        DoubleTap(HOTKEY[7:], lambda: GLib.idle_add(app.toggle)).start()
        log(f"trigger: double-tap {HOTKEY[7:]}, {FROM}→{TO}")
    else:
        log(f"LENS_HOTKEY={HOTKEY} not understood; use double: plus one of {', '.join(TAP_KEYS)}. "
            "Only `lens` (the socket) triggers it now.")
    Gtk.main()


# ---------------------------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "toggle"
    if cmd == "toggle":
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(str(SOCK))
                s.sendall(b"toggle\n")
                s.recv(16)
        except OSError:
            sys.exit("lens: the daemon is not running (systemctl --user start lens)")
    elif cmd == "daemon":
        run_daemon()
    elif cmd == "warmup":  # used by install.py: downloads and compiles the OCR models
        engine()(np.zeros((64, 256, 3), np.uint8))
    elif cmd == "file" and len(args) > 1:
        run_file(args[1:])
    elif cmd == "status":
        subprocess.call(["systemctl", "--user", "--no-pager", "status", "lens"])
    elif cmd == "logs":
        os.execvp("journalctl", ["journalctl", "--user", "-u", "lens", "-f", "-n", "50"])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
