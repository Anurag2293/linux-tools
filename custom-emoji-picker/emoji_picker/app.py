"""Single-instance GTK application and toggle lifecycle."""

import time
from typing import Optional

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from .catalog import EmojiCatalog
from .insertion import TargetWindow, X11Inserter
from .state import PickerState
from .ui import PickerWindow


APPLICATION_ID = "com.anurag.EmojiPicker"


class EmojiPickerApplication(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.catalog: Optional[EmojiCatalog] = None
        self.state: Optional[PickerState] = None
        self.inserter = X11Inserter()
        self.window: Optional[PickerWindow] = None
        self.target: Optional[TargetWindow] = None
        self.last_toggle_at = 0.0

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        self.hold()
        self.catalog = EmojiCatalog.load()
        self.state = PickerState()
        self.window = PickerWindow(
            self,
            self.catalog,
            self.state,
            self._select_emoji,
            self._dismiss,
        )

    def do_activate(self) -> None:
        self.show_picker()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        arguments = list(command_line.get_arguments())[1:]
        command = arguments[0] if arguments else "--toggle"
        if command == "--quit":
            self.quit()
        elif command == "--show":
            self.show_picker()
        elif command == "--hide":
            self.hide_picker(restore_focus=True)
        elif command == "--toggle":
            self.toggle_picker()
        else:
            command_line.set_exit_status(2)
            return 2
        command_line.set_exit_status(0)
        return 0

    def toggle_picker(self) -> None:
        now = time.monotonic()
        if now - self.last_toggle_at < 0.15:
            return
        self.last_toggle_at = now
        if self.window and self.window.get_visible():
            self.hide_picker(restore_focus=True)
        else:
            self.show_picker()

    def show_picker(self) -> None:
        if not self.window:
            return
        self.target = self.inserter.capture_active_window()
        self.window.show_for_target(self.target)

    def hide_picker(self, restore_focus: bool = False) -> None:
        if not self.window or not self.window.get_visible():
            return
        self.window.hide()
        if restore_focus and self.target:
            GLib.timeout_add(70, self._restore_target_once)

    def _restore_target_once(self) -> bool:
        self.inserter.restore_focus(self.target)
        return GLib.SOURCE_REMOVE

    def _dismiss(self, _inserted: bool = False, focus_lost: bool = False) -> None:
        self.hide_picker(restore_focus=not focus_lost)

    def _select_emoji(self, value: str) -> None:
        if self.state:
            self.state.add_recent(value)
        if self.window:
            self.window.hide()
        self.inserter.insert_after_delay(value, self.target)


def run(arguments: list) -> int:
    return EmojiPickerApplication().run(arguments)

