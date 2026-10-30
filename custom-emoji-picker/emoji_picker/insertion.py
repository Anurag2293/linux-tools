"""X11 focus capture and clipboard-paste support."""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk


TERMINAL_CTRL_SHIFT_V = (
    "terminator",
    "gnome-terminal",
    "gnome-terminal-server",
    "tilix",
    "konsole",
    "kitty",
    "alacritty",
)
TERMINAL_SHIFT_INSERT = ("xterm", "uxterm", "rxvt", "urxvt")


@dataclass(frozen=True)
class TargetWindow:
    window_id: str
    window_class: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


def paste_accelerator(window_class: str) -> str:
    normalized = window_class.casefold()
    if any(name in normalized for name in TERMINAL_CTRL_SHIFT_V):
        return "ctrl+shift+v"
    if any(name in normalized for name in TERMINAL_SHIFT_INSERT):
        return "shift+Insert"
    return "ctrl+v"


def parse_geometry(output: str) -> Tuple[int, int, int, int]:
    values: Dict[str, int] = {}
    for line in output.splitlines():
        match = re.fullmatch(r"(X|Y|WIDTH|HEIGHT)=(-?\d+)", line.strip())
        if match:
            values[match.group(1)] = int(match.group(2))
    return (
        values.get("X", 0),
        values.get("Y", 0),
        values.get("WIDTH", 0),
        values.get("HEIGHT", 0),
    )


def parse_window_class(output: str) -> str:
    """Turn xprop's WM_CLASS output into a searchable class string."""

    return " ".join(re.findall(r'"([^"]+)"', output))


def paste_command(target: TargetWindow, settle_seconds: float = 0.14) -> Tuple[str, ...]:
    """Build one xdotool command sequence for activation, settling, and paste."""

    return (
        "windowactivate",
        "--sync",
        target.window_id,
        "sleep",
        "{:.3f}".format(settle_seconds),
        "key",
        "--clearmodifiers",
        paste_accelerator(target.window_class),
    )


class X11Inserter:
    def __init__(self, executable: Optional[str] = None):
        self.executable = executable or shutil.which("xdotool")
        self.last_error = ""

    @property
    def available(self) -> bool:
        return bool(self.executable) and os.environ.get("XDG_SESSION_TYPE", "x11").lower() == "x11"

    def _run(self, arguments: Sequence[str], timeout: float = 2.0) -> str:
        if not self.executable:
            raise RuntimeError("xdotool is not installed")
        result = subprocess.run(
            [self.executable] + list(arguments),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()

    def capture_active_window(self) -> Optional[TargetWindow]:
        if not self.available:
            self.last_error = "Automatic insertion requires an X11 session and xdotool."
            return None
        try:
            window_id = self._run(("getactivewindow",))
        except (RuntimeError, subprocess.SubprocessError, OSError) as error:
            self.last_error = str(error)
            return None

        window_class = ""
        xprop = shutil.which("xprop")
        if xprop:
            try:
                result = subprocess.run(
                    (xprop, "-id", window_id, "WM_CLASS"),
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=2.0,
                )
                window_class = parse_window_class(result.stdout)
            except (subprocess.SubprocessError, OSError):
                pass

        x = y = width = height = 0
        try:
            geometry_output = self._run(("getwindowgeometry", "--shell", window_id))
            x, y, width, height = parse_geometry(geometry_output)
        except (RuntimeError, subprocess.SubprocessError, OSError):
            pass

        self.last_error = ""
        target = TargetWindow(window_id, window_class, x, y, width, height)
        return target

    @staticmethod
    def copy_to_clipboard(value: str) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(value, -1)
        clipboard.store()

    def restore_focus(self, target: Optional[TargetWindow]) -> bool:
        if not target or not self.available:
            return False
        try:
            self._run(("windowactivate", "--sync", target.window_id))
            self.last_error = ""
            return True
        except (RuntimeError, subprocess.SubprocessError, OSError) as error:
            self.last_error = str(error)
            return False

    def insert_after_delay(
        self,
        value: str,
        target: Optional[TargetWindow],
        delay_ms: int = 110,
        focus_settle_ms: int = 150,
    ) -> None:
        self.copy_to_clipboard(value)
        if not target or not self.available:
            return

        def launch_paste() -> bool:
            try:
                command = [self.executable] + list(
                    paste_command(
                        target,
                        (delay_ms + focus_settle_ms) / 1000.0,
                    )
                )
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
            except (subprocess.SubprocessError, OSError) as error:
                self.last_error = str(error)
                return GLib.SOURCE_REMOVE

            def reap_process() -> bool:
                if process.poll() is None:
                    return GLib.SOURCE_CONTINUE
                _stdout, stderr = process.communicate()
                if process.returncode:
                    self.last_error = (stderr or "xdotool paste failed").strip()
                else:
                    self.last_error = ""
                return GLib.SOURCE_REMOVE

            GLib.timeout_add(100, reap_process)
            return GLib.SOURCE_REMOVE

        # Start the short-lived helper now and keep both delays in xdotool. This
        # makes insertion independent of GTK's window-withdraw lifecycle.
        launch_paste()
