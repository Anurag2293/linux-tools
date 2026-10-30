"""GTK widgets for the compact picker window."""

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from .catalog import CATEGORY_ORDER, EmojiCatalog, EmojiRecord
from .insertion import TargetWindow
from .state import PickerState


CATEGORY_BUTTONS = (
    ("Favorites", "★", "Favorites"),
    ("Recent", "◷", "Recently used"),
    ("Smileys & Emotion", "😀", "Smileys & Emotion"),
    ("People & Body", "🧑", "People & Body"),
    ("Animals & Nature", "🐻", "Animals & Nature"),
    ("Food & Drink", "🍎", "Food & Drink"),
    ("Travel & Places", "🚗", "Travel & Places"),
    ("Activities", "⚽", "Activities"),
    ("Objects", "💡", "Objects"),
    ("Symbols", "♥", "Symbols"),
    ("Flags", "⚑", "Flags"),
)

BATCH_SIZE = 120


class EmojiCell(Gtk.FlowBoxChild):
    def __init__(
        self,
        record: EmojiRecord,
        state: PickerState,
        on_select: Callable[[str], None],
        on_favorite: Callable[[str], None],
        catalog: EmojiCatalog,
    ):
        super().__init__()
        self.record = record
        self._state = state
        self._on_select = on_select
        self._on_favorite = on_favorite
        self._catalog = catalog
        self.set_can_focus(True)
        self.set_tooltip_text(record.description)
        self.get_style_context().add_class("emoji-flow-child")

        overlay = Gtk.Overlay()
        self.add(overlay)

        emoji_button = Gtk.Button(label=record.value)
        emoji_button.set_relief(Gtk.ReliefStyle.NONE)
        emoji_button.set_can_focus(False)
        emoji_button.set_size_request(54, 50)
        emoji_button.get_style_context().add_class("emoji-cell")
        emoji_button.connect("clicked", lambda _button: self._on_select(record.value))
        emoji_button.connect("button-press-event", self._on_button_press)
        overlay.add(emoji_button)

        self.star_button = Gtk.Button(label="★" if state.is_favorite(record.value) else "☆")
        self.star_button.set_relief(Gtk.ReliefStyle.NONE)
        self.star_button.set_can_focus(False)
        self.star_button.set_halign(Gtk.Align.END)
        self.star_button.set_valign(Gtk.Align.START)
        self.star_button.set_tooltip_text("Remove favorite" if state.is_favorite(record.value) else "Add favorite")
        self.star_button.get_style_context().add_class("favorite-toggle")
        self.star_button.connect("clicked", self._favorite_clicked)
        overlay.add_overlay(self.star_button)

        self.connect("key-press-event", self._on_key_press)

    def _favorite_clicked(self, _button: Gtk.Button) -> None:
        self._on_favorite(self.record.value)

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._on_select(self.record.value)
            return True
        return False

    def _on_button_press(self, _button: Gtk.Button, event: Gdk.EventButton) -> bool:
        if event.button != 3 or not self.record.variants:
            return False
        self._show_variants()
        return True

    def _show_variants(self) -> None:
        popover = Gtk.Popover.new(self)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        row.set_border_width(6)
        values = (self.record.value,) + self.record.variants
        for value in values:
            record = self._catalog.get(value)
            button = Gtk.Button(label=value)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_tooltip_text(record.description if record else value)
            button.connect("clicked", lambda _button, selected=value: self._choose_variant(popover, selected))
            row.pack_start(button, False, False, 0)
        popover.add(row)
        popover.show_all()
        popover.popup()

    def _choose_variant(self, popover: Gtk.Popover, value: str) -> None:
        popover.popdown()
        self._on_select(value)


class PickerWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        application: Gtk.Application,
        catalog: EmojiCatalog,
        state: PickerState,
        on_select: Callable[[str], None],
        on_dismiss: Callable[[bool], None],
    ):
        super().__init__(application=application, title="Emoji Picker")
        self.catalog = catalog
        self.state = state
        self.on_select = on_select
        self.on_dismiss = on_dismiss
        self.current_category = "Recent" if state.recents else CATEGORY_ORDER[0]
        self.current_records: List[EmojiRecord] = []
        self.rendered_count = 0
        self.search_source_id = 0
        self.shown_at = 0.0
        self.variant_popover_visible = False

        self.set_default_size(600, 440)
        self.set_size_request(520, 360)
        self.set_decorated(False)
        self.set_resizable(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.get_style_context().add_class("emoji-picker-window")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_border_width(12)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(header, False, False, 0)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search emoji…")
        self.search.set_hexpand(True)
        self.search.connect("search-changed", self._on_search_changed)
        self.search.connect("key-press-event", self._on_search_key_press)
        header.pack_start(self.search, True, True, 0)

        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON)
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.set_tooltip_text("Close (Esc)")
        close_button.connect("clicked", lambda _button: self.on_dismiss(False))
        header.pack_start(close_button, False, False, 0)

        categories = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        categories.set_margin_top(10)
        categories.set_homogeneous(True)
        outer.pack_start(categories, False, False, 0)
        self.category_buttons: Dict[str, Gtk.ToggleButton] = {}
        group: Optional[Gtk.RadioButton] = None
        for category, label, tooltip in CATEGORY_BUTTONS:
            button = Gtk.RadioButton.new_from_widget(group)
            if group is None:
                group = button
            button.set_mode(False)
            button.set_label(label)
            button.set_tooltip_text(tooltip)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.get_style_context().add_class("category-button")
            button.connect("toggled", self._on_category_toggled, category)
            categories.pack_start(button, True, True, 0)
            self.category_buttons[category] = button

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)
        outer.pack_start(separator, False, False, 0)

        content = Gtk.Overlay()
        content.set_margin_top(6)
        outer.pack_start(content, True, True, 0)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content.add(self.scrolled)

        self.flow = Gtk.FlowBox()
        self.flow.set_homogeneous(True)
        self.flow.set_row_spacing(4)
        self.flow.set_column_spacing(4)
        self.flow.set_min_children_per_line(6)
        self.flow.set_max_children_per_line(10)
        self.flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow.connect("child-activated", self._on_child_activated)
        self.scrolled.add(self.flow)

        self.empty_label = Gtk.Label(label="No emoji found")
        self.empty_label.set_halign(Gtk.Align.CENTER)
        self.empty_label.set_valign(Gtk.Align.CENTER)
        self.empty_label.get_style_context().add_class("empty-label")
        content.add_overlay(self.empty_label)

        self.footer = Gtk.Label()
        self.footer.set_halign(Gtk.Align.START)
        self.footer.set_margin_top(6)
        self.footer.set_ellipsize(Pango.EllipsizeMode.END)
        self.footer.get_style_context().add_class("picker-footer")
        outer.pack_start(self.footer, False, False, 0)

        adjustment = self.scrolled.get_vadjustment()
        adjustment.connect("value-changed", self._on_scroll)
        self.connect("key-press-event", self._on_window_key_press)
        self.connect("focus-out-event", self._on_focus_out)

        self._load_css()
        self.category_buttons[self.current_category].set_active(True)
        self.refresh()

    @staticmethod
    def _load_css() -> None:
        css_path = Path(__file__).resolve().parent.parent / "data" / "style.css"
        if not css_path.is_file():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def _records_for_current_view(self) -> List[EmojiRecord]:
        query = self.search.get_text().strip()
        if query:
            return self.catalog.search(query, self.state.favorites, self.state.recents)
        if self.current_category == "Favorites":
            return self.catalog.records_for_values(self.state.favorites)
        if self.current_category == "Recent":
            return self.catalog.records_for_values(self.state.recents)
        return list(self.catalog.for_category(self.current_category))

    def refresh(self) -> None:
        self.current_records = self._records_for_current_view()
        self.rendered_count = 0
        for child in self.flow.get_children():
            self.flow.remove(child)
        self.empty_label.set_visible(not self.current_records)
        self._append_batch()
        label = "Search results" if self.search.get_text().strip() else self.current_category
        self.footer.set_text("{} · {} emoji · Right-click an emoji for skin tones".format(label, len(self.current_records)))
        adjustment = self.scrolled.get_vadjustment()
        adjustment.set_value(adjustment.get_lower())

    def _append_batch(self) -> None:
        end = min(self.rendered_count + BATCH_SIZE, len(self.current_records))
        for record in self.current_records[self.rendered_count:end]:
            self.flow.add(
                EmojiCell(
                    record,
                    self.state,
                    self.on_select,
                    self._toggle_favorite,
                    self.catalog,
                )
            )
        self.rendered_count = end
        self.flow.show_all()

    def _toggle_favorite(self, value: str) -> None:
        self.state.toggle_favorite(value)
        self.refresh()

    def _on_scroll(self, adjustment: Gtk.Adjustment) -> None:
        if self.rendered_count >= len(self.current_records):
            return
        if adjustment.get_value() + adjustment.get_page_size() >= adjustment.get_upper() - 100:
            self._append_batch()

    def _on_category_toggled(self, button: Gtk.ToggleButton, category: str) -> None:
        if not button.get_active():
            return
        self.current_category = category
        if self.search.get_text():
            self.search.set_text("")
        else:
            self.refresh()

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        if self.search_source_id:
            GLib.source_remove(self.search_source_id)
        self.search_source_id = GLib.timeout_add(80, self._apply_search)

    def _apply_search(self) -> bool:
        self.search_source_id = 0
        self.refresh()
        return GLib.SOURCE_REMOVE

    def _on_search_key_press(self, _entry: Gtk.SearchEntry, event: Gdk.EventKey) -> bool:
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_Page_Down) and self.flow.get_children():
            first = self.flow.get_child_at_index(0)
            self.flow.select_child(first)
            first.grab_focus()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self.on_dismiss(False)
            return True
        return False

    def _on_window_key_press(self, _window: Gtk.Window, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.on_dismiss(False)
            return True
        if event.keyval in (Gdk.KEY_f, Gdk.KEY_F) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
            return True
        return False

    def _on_child_activated(self, _flow: Gtk.FlowBox, child: EmojiCell) -> None:
        self.on_select(child.record.value)

    def _on_focus_out(self, _window: Gtk.Window, _event: Gdk.EventFocus) -> bool:
        def dismiss_if_inactive() -> bool:
            if self.get_visible() and not self.is_active():
                self.on_dismiss(False, focus_lost=True)
            return GLib.SOURCE_REMOVE

        if time.monotonic() - self.shown_at > 0.25:
            GLib.timeout_add(90, dismiss_if_inactive)
        return False

    def show_for_target(self, target: Optional[TargetWindow]) -> None:
        self.search.set_text("")
        self.refresh()
        self.show_all()
        self.empty_label.set_visible(not self.current_records)
        self._center_on_target_monitor(target)
        self.present()
        self.search.grab_focus()
        self.shown_at = time.monotonic()

    def _center_on_target_monitor(self, target: Optional[TargetWindow]) -> None:
        display = Gdk.Display.get_default()
        if not display:
            return
        monitor = None
        if target and target.width and target.height:
            monitor = display.get_monitor_at_point(
                target.x + target.width // 2,
                target.y + target.height // 2,
            )
        if monitor is None:
            monitor = display.get_primary_monitor()
        if monitor is None and display.get_n_monitors():
            monitor = display.get_monitor(0)
        if monitor is None:
            return
        workarea = monitor.get_workarea()
        width, height = self.get_size()
        self.move(
            workarea.x + max(0, (workarea.width - width) // 2),
            workarea.y + max(0, (workarea.height - height) // 2),
        )

