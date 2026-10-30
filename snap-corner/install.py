#!/usr/bin/python3
"""Install or remove Snap Corner for the current GNOME user; no sudo needed."""
import json
from pathlib import Path
import shlex
import sys

from gi.repository import Gio

HOME = Path.home()
SOURCE = Path(__file__).resolve().parent
LAUNCHER = HOME / ".local/bin/snap-corner"
DESKTOP = HOME / ".local/share/applications/com.anurag.SnapCorner.desktop"
AUTOSTART = HOME / ".config/autostart/com.anurag.SnapCorner.desktop"
BACKUP = HOME / ".local/share/snap-corner/install-backup.json"
SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM = SCHEMA + ".custom-keybinding"
PREFIX = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
BINDINGS = [(PREFIX + "snap-corner-area/", "Snap Corner: capture area", "<Control><Alt>s", "--area"),
            (PREFIX + "snap-corner-screen/", "Snap Corner: capture screen", "<Control><Alt>f", "--screen")]


def write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)


def install():
    settings = Gio.Settings.new(SCHEMA)
    paths = list(settings.get_strv("custom-keybindings"))
    if not BACKUP.exists():
        previous = {}
        for path, _, _, _ in BINDINGS:
            binding = Gio.Settings.new_with_path(CUSTOM, path)
            previous[path] = {"listed": path in paths,
                              "values": {key: binding.get_string(key)
                                         for key in ("name", "binding", "command")}}
        for path in (LAUNCHER, DESKTOP, AUTOSTART):
            if path.exists():
                raise SystemExit("Refusing to overwrite an existing installation file: " + str(path))
        write(BACKUP, json.dumps(previous, indent=2) + "\n", 0o600)
    write(LAUNCHER, "#!/bin/sh\nexec /usr/bin/python3 " +
          shlex.quote(str(SOURCE / "snap_corner.py")) + ' "$@"\n', 0o755)
    entry = ("[Desktop Entry]\nType=Application\nName=Snap Corner\n"
             "Comment=Capture an area and drag the screenshot into another app\n"
             "Exec=" + str(LAUNCHER) + " --area\nIcon=applets-screenshooter\n"
             "Terminal=false\nCategories=Utility;Graphics;\nStartupNotify=false\n")
    write(DESKTOP, entry)
    write(AUTOSTART, entry.replace(" --area\n", " --background\n") +
          "X-GNOME-Autostart-enabled=true\nNoDisplay=true\n")
    for path, name, accelerator, argument in BINDINGS:
        binding = Gio.Settings.new_with_path(CUSTOM, path)
        binding.set_string("name", name)
        binding.set_string("binding", accelerator)
        binding.set_string("command", str(LAUNCHER) + " " + argument)
        if path not in paths:
            paths.append(path)
    settings.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()
    print("Installed Snap Corner. Ctrl+Alt+S: area; Ctrl+Alt+F: current screen.")


def uninstall():
    if not BACKUP.exists():
        raise SystemExit("No Snap Corner installation backup found.")
    import subprocess
    subprocess.run([str(LAUNCHER), "--quit"], check=False)
    previous = json.loads(BACKUP.read_text())
    settings = Gio.Settings.new(SCHEMA)
    paths = list(settings.get_strv("custom-keybindings"))
    for path, _, _, _ in BINDINGS:
        old = previous[path]
        binding = Gio.Settings.new_with_path(CUSTOM, path)
        for key, value in old["values"].items():
            binding.set_string(key, value)
        if not old["listed"] and path in paths:
            paths.remove(path)
    settings.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()
    for path in (LAUNCHER, DESKTOP, AUTOSTART, BACKUP):
        path.unlink(missing_ok=True)
    print("Removed Snap Corner launcher, shortcuts, and autostart. Screenshots are kept.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--uninstall"]:
        uninstall()
    elif not sys.argv[1:]:
        install()
    else:
        raise SystemExit("Usage: install.py [--uninstall]")
