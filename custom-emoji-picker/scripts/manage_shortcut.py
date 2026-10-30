#!/usr/bin/env python3
"""Install or remove the GNOME custom keybinding owned by this app."""

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio


MEDIA_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
BINDING_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
BINDING_ROOT = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
BINDING_NAME = "Custom Emoji Picker"
BINDING_VALUE = "<Super>period"


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "custom-emoji-picker"


def install_record_path() -> Path:
    return config_dir() / "install.json"


def binding_settings(path: str) -> Gio.Settings:
    return Gio.Settings.new_with_path(BINDING_SCHEMA, path)


def find_conflict(paths: List[str], command: str) -> Optional[str]:
    for path in paths:
        settings = binding_settings(path)
        binding = settings.get_string("binding")
        existing_command = settings.get_string("command")
        if binding == BINDING_VALUE and existing_command != command:
            return path
    return None


def choose_path(paths: List[str], command: str) -> str:
    for path in paths:
        settings = binding_settings(path)
        if settings.get_string("command") == command and settings.get_string("name") == BINDING_NAME:
            return path
    used = set(paths)
    index = 0
    while True:
        candidate = "{}custom{}/".format(BINDING_ROOT, index)
        if candidate not in used:
            return candidate
        index += 1


def install(command: str) -> None:
    media = Gio.Settings.new(MEDIA_SCHEMA)
    paths = list(media.get_strv("custom-keybindings"))
    conflict = find_conflict(paths, command)
    if conflict:
        settings = binding_settings(conflict)
        raise SystemExit(
            "Super + . is already assigned to {!r}. Remove that shortcut and rerun install.sh.".format(
                settings.get_string("name") or settings.get_string("command")
            )
        )

    path = choose_path(paths, command)
    settings = binding_settings(path)
    settings.set_string("name", BINDING_NAME)
    settings.set_string("command", command)
    settings.set_string("binding", BINDING_VALUE)
    if path not in paths:
        paths.append(path)
        media.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()

    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    record = {"version": 1, "binding_path": path, "command": command}
    install_record_path().write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Registered Super + . at {}".format(path))


def recorded_path() -> Optional[str]:
    try:
        record = json.loads(install_record_path().read_text(encoding="utf-8"))
        path = record.get("binding_path")
        return path if isinstance(path, str) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def uninstall(command: str) -> None:
    media = Gio.Settings.new(MEDIA_SCHEMA)
    paths = list(media.get_strv("custom-keybindings"))
    candidates = []
    path = recorded_path()
    if path:
        candidates.append(path)
    candidates.extend(item for item in paths if item not in candidates)

    removed = None
    for candidate in candidates:
        if candidate not in paths:
            continue
        settings = binding_settings(candidate)
        if settings.get_string("name") == BINDING_NAME and settings.get_string("command") == command:
            paths.remove(candidate)
            media.set_strv("custom-keybindings", paths)
            settings.reset("name")
            settings.reset("command")
            settings.reset("binding")
            removed = candidate
            break
    Gio.Settings.sync()
    try:
        install_record_path().unlink()
    except FileNotFoundError:
        pass
    if removed:
        print("Removed shortcut at {}".format(removed))
    else:
        print("No matching Custom Emoji Picker shortcut was installed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("--command", required=True)
    args = parser.parse_args()
    if args.action == "install":
        install(args.command)
    else:
        uninstall(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

