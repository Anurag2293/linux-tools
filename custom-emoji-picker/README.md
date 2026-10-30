# Custom Emoji Picker

A compact, keyboard-first Unicode emoji picker for Ubuntu 20.04, GNOME, and X11.

## Features

- Toggle globally with **Super + .**
- Search Ubuntu's installed IBus emoji catalog by name or keyword
- Browse categories, favorites, and the 30 most recent emoji
- Choose skin tones by right-clicking an emoji that has variants
- Insert into the previously focused application
- Terminal-aware paste shortcuts for Terminator, GNOME Terminal, and XTerm
- No network access or external emoji database

## Install

The GTK and IBus Python bindings are already included in a normal Ubuntu 20.04 desktop install. Install the X11 automation helper, then run the user-level installer:

```bash
sudo apt install xdotool
cd custom-emoji-picker
./install.sh
```

Press **Super + .** to open or close the picker. Start typing to search, use the arrow keys to select, and press **Enter** to insert. **Escape** closes without inserting.

The process starts the first time the shortcut is pressed and stays lightweight and hidden for the rest of the login session. It does not create an autostart entry.

## Commands

```bash
custom-emoji-picker --toggle
custom-emoji-picker --show
custom-emoji-picker --hide
custom-emoji-picker --quit
custom-emoji-picker --version
```

## State

Favorites and recents are stored in:

```text
~/.config/custom-emoji-picker/state.json
```

The selected emoji remains on the clipboard, providing a manual paste fallback for applications that block synthetic input.

## Uninstall

```bash
cd custom-emoji-picker
./uninstall.sh
```

Add `--purge` to also remove favorites and recents.

## Development

Run the non-visual tests with:

```bash
python3 -m pytest -q
```

The insertion feature intentionally targets X11. `xdotool` cannot reliably control native Wayland windows.

